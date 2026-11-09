"""Уведомления игрокам о смене статусов (этап 7).

Постановка в очередь (`notify_*`) не коммитит: вызывающий коммитит вместе со сменой статуса.
Доставка — у бота: он забирает записи (`claim`), шлёт в Telegram и подтверждает
(`mark_sent`/`mark_failed`). Доставка «хотя бы один раз»: если бот упал между отправкой и
подтверждением, сообщение уйдёт повторно после окончания аренды.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import DepositRequest, Notification, User, WithdrawalRequest
from app.services.errors import ServiceError

LEASE_SECONDS = 120
MAX_ATTEMPTS = 5
# Пауза перед следующей попыткой после неудачи, по номеру выполненной попытки.
BACKOFF_SECONDS = {1: 60, 2: 300, 3: 900, 4: 3600}
RETENTION_DAYS = 30
MAX_ERROR = 100


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _enqueue(db: Session, user_id: int, telegram_id: int, kind: str, payload: dict) -> None:
    db.add(Notification(user_id=user_id, telegram_id=telegram_id, kind=kind, payload=payload))


def notify_deposit(db: Session, request: DepositRequest) -> None:
    """Пополнение выполнено, отклонено или закрыто по времени."""
    user = db.get(User, request.user_id)
    _enqueue(
        db,
        user.id,
        user.telegram_id,
        "deposit",
        {
            "id": request.id,
            "status": request.status,
            "amount": request.amount,
            "credit_amount": request.amount + request.commission_amount,
            "reason": request.reject_reason,
        },
    )


def notify_withdrawal(db: Session, request: WithdrawalRequest) -> None:
    user = db.get(User, request.user_id)
    _enqueue(
        db,
        user.id,
        user.telegram_id,
        "withdrawal",
        {
            "id": request.id,
            "status": request.status,
            "amount": request.amount,
            "payout_amount": request.amount + request.commission_amount,
            "reason": request.reject_reason,
        },
    )


def notify_account(db: Session, user_id: int, status: str, reason: str | None = None) -> None:
    """Решение по игроку: approved, rejected или unblocked."""
    user = db.get(User, user_id)
    _enqueue(db, user.id, user.telegram_id, "account", {"status": status, "reason": reason})


# --- Доставка ---------------------------------------------------------------------


def claim(db: Session, limit: int = 20, now: datetime | None = None) -> list[Notification]:
    """Выдаёт боту готовые к отправке записи и «арендует» их на LEASE_SECONDS.

    Два бота не получат одну запись: аренда берётся условным UPDATE.
    """
    now = now or _now()
    db.execute(  # записи, исчерпавшие попытки (бот падал во время отправки), закрываются
        update(Notification)
        .where(
            Notification.sent_at.is_(None),
            Notification.failed_at.is_(None),
            Notification.attempts >= MAX_ATTEMPTS,
            Notification.next_attempt_at <= now,
        )
        .values(failed_at=now, last_error="max_attempts")
        .execution_options(synchronize_session="fetch")
    )
    ids = db.scalars(
        select(Notification.id)
        .where(
            Notification.sent_at.is_(None),
            Notification.failed_at.is_(None),
            Notification.next_attempt_at <= now,
        )
        .order_by(Notification.id)
        .limit(max(1, min(limit, 100)))
    ).all()
    claimed = []
    for notification_id in ids:
        result = db.execute(
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.sent_at.is_(None),
                Notification.failed_at.is_(None),
                Notification.next_attempt_at <= now,
            )
            .values(
                next_attempt_at=now + timedelta(seconds=LEASE_SECONDS),
                attempts=Notification.attempts + 1,
            )
            .execution_options(synchronize_session="fetch")
        )
        if result.rowcount == 1:
            claimed.append(notification_id)
    db.commit()
    if not claimed:
        return []
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.id.in_(claimed))
            .order_by(Notification.id)
            .execution_options(populate_existing=True)
        ).all()
    )


def _exists(db: Session, notification_id: int) -> bool:
    return db.scalar(select(Notification.id).where(Notification.id == notification_id)) is not None


def mark_sent(db: Session, notification_id: int, now: datetime | None = None) -> None:
    """Идемпотентно: повторное подтверждение безвредно."""
    result = db.execute(
        update(Notification)
        .where(Notification.id == notification_id, Notification.sent_at.is_(None))
        .values(sent_at=now or _now(), last_error=None)
    )
    if result.rowcount == 0 and not _exists(db, notification_id):
        db.rollback()
        raise ServiceError("notification_not_found")
    db.commit()


def mark_failed(
    db: Session,
    notification_id: int,
    *,
    permanent: bool,
    error: str = "",
    retry_after: int | None = None,
    now: datetime | None = None,
) -> None:
    """Отправить не удалось. permanent — повторять бессмысленно (игрок заблокировал бота).
    Иначе следующая попытка по графику, но не раньше `retry_after` (лимиты Telegram)."""
    now = now or _now()
    row = db.get(Notification, notification_id, populate_existing=True)
    if row is None:
        raise ServiceError("notification_not_found")
    if row.sent_at is not None or row.failed_at is not None:
        return
    row.last_error = (error or "")[:MAX_ERROR] or None
    if permanent or row.attempts >= MAX_ATTEMPTS:
        row.failed_at = now
    else:
        delay = max(BACKOFF_SECONDS.get(row.attempts, 3600), retry_after or 0)
        row.next_attempt_at = now + timedelta(seconds=delay)
    db.commit()


def cleanup(db: Session, now: datetime | None = None) -> int:
    """Удаляет отправленные и окончательно неудавшиеся записи старше RETENTION_DAYS."""
    border = (now or _now()) - timedelta(days=RETENTION_DAYS)
    result = db.execute(
        delete(Notification).where(
            Notification.created_at < border,
            (Notification.sent_at.is_not(None)) | (Notification.failed_at.is_not(None)),
        )
        .execution_options(synchronize_session="fetch")
    )
    db.commit()
    return result.rowcount
