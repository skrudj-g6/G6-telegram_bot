"""Заявки на пополнение (ТЗ §5) с поправками владельца (MIGRATION_PLAN, раздел 8).

Жизненный цикл на стороне игрока:
    awaiting_receipt --чек--> pending            (дальше работает оператор, этап 5)
    awaiting_receipt --игрок--> cancelled        (Q-5: только до чека)
    awaiting_receipt --таймер--> expired         (Q-9: 10 минут без чека)

Все переходы выполняются условным UPDATE: из нескольких одновременных действий
(чек и таймер, отмена и чек) успешным будет только одно.
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    DepositMethod,
    DepositRequest,
    DepositStatus,
    DepositStatusHistory,
    PokerAccountStatus,
    User,
    UserStatus,
)
from app.services import app_settings, players, receipt_storage, requisites
from app.services.errors import ServiceError

logger = logging.getLogger(__name__)

LIST_LIMIT = 20
MAX_USDT = Decimal("1000000000")


def _fmt(value: Decimal) -> str:
    """Decimal → строка без экспоненты и лишних нулей: Decimal('5E+2') → '500'."""
    return format(value.normalize(), "f")


def format_usdt(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def _normalize_usdt(value: Decimal | None) -> Decimal:
    """Сумма USDT: положительная, не более двух знаков после запятой."""
    if value is None or not value.is_finite() or value <= 0 or value > MAX_USDT:
        raise ServiceError("invalid_amount")
    if value.as_tuple().exponent < -2:
        raise ServiceError("invalid_amount")
    return value


def usdt_to_kzt(usdt: Decimal, rate: Decimal) -> int:
    """Эквивалент в целых тенге. Дробная часть отбрасывается (в пользу клуба)."""
    return int((usdt * rate).to_integral_value(rounding=ROUND_DOWN))


def _commission_fields(db: Session, amount: int) -> dict:
    percent = app_settings.get_commission_percent(db, "deposit")
    commission = app_settings.calc_commission(amount, percent)
    return {
        "commission_percent": format(percent.normalize(), "f"),
        "commission_amount": commission,
        "credit_amount": amount - commission,
    }


def quote_usdt(db: Session, usdt_amount: Decimal | None, now: datetime | None = None) -> dict:
    """Сколько тенге получится за введённые USDT (бот показывает это до подтверждения)."""
    usdt = _normalize_usdt(usdt_amount)
    rate = app_settings.get_usdt_rate(db, now)
    if rate is None:
        raise ServiceError("exchange_rate_unavailable")
    kzt = usdt_to_kzt(usdt, rate)
    minimum = app_settings.get_int(db, "deposit_min_amount")
    maximum = app_settings.get_int(db, "deposit_max_amount")
    return {
        "usdt_amount": format_usdt(int(usdt * 100)),
        "rate": _fmt(rate),
        "kzt_amount": kzt,
        "min": minimum,
        "max": maximum,
        "within_limits": minimum <= kzt <= maximum,
        **_commission_fields(db, kzt),
    }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _history(
    db: Session,
    request_id: int,
    from_status: str | None,
    to_status: str,
    actor_type: str,
    actor_id: int | None = None,
    comment: str | None = None,
) -> None:
    db.add(
        DepositStatusHistory(
            request_id=request_id,
            from_status=from_status,
            to_status=to_status,
            actor_type=actor_type,
            actor_id=actor_id,
            comment=comment,
        )
    )


def _load(db: Session, request_id: int) -> DepositRequest | None:
    return db.scalar(
        select(DepositRequest)
        .where(DepositRequest.id == request_id)
        .execution_options(populate_existing=True)
    )


def _active_user(db: Session, telegram_id: int) -> User:
    """Заблокированный игрок (в том числе по Q-27) не может пользоваться ботом."""
    user = players.get_user(db, telegram_id)
    if user.status != UserStatus.ACTIVE:
        raise ServiceError("user_blocked")
    return user


def _owned(db: Session, user: User, request_id: int) -> DepositRequest:
    request = _load(db, request_id)
    # Чужая заявка выглядит так же, как несуществующая: номера не подбираются.
    if request is None or request.user_id != user.id:
        raise ServiceError("request_not_found")
    return request


# --- Таймер -----------------------------------------------------------------------


def _expire_one(db: Session, request_id: int, now: datetime) -> bool:
    result = db.execute(
        update(DepositRequest)
        .where(
            DepositRequest.id == request_id,
            DepositRequest.status == DepositStatus.AWAITING_RECEIPT,
            DepositRequest.expires_at <= now,
        )
        .values(status=DepositStatus.EXPIRED)
    )
    if result.rowcount == 0:
        db.rollback()
        return False
    _history(
        db,
        request_id,
        DepositStatus.AWAITING_RECEIPT,
        DepositStatus.EXPIRED,
        "system",
        comment="Чек не прислан за отведённое время",
    )
    db.commit()
    return True


def expire_overdue(db: Session, now: datetime | None = None) -> int:
    """Закрывает заявки без чека, у которых вышло время (Q-9). Возвращает их число.

    Заявки с уже присланным чеком не затрагиваются: они не в статусе awaiting_receipt.
    """
    now = now or _utcnow()
    ids = db.scalars(
        select(DepositRequest.id).where(
            DepositRequest.status == DepositStatus.AWAITING_RECEIPT,
            DepositRequest.expires_at <= now,
        )
    ).all()
    return sum(1 for request_id in ids if _expire_one(db, request_id, now))


def cleanup_receipts(db: Session, now: datetime | None = None) -> int:
    """Удаляет файлы чеков старше срока хранения (Q-23: неделя). Заявки остаются."""
    now = now or _utcnow()
    cutoff = now - timedelta(days=app_settings.get_int(db, "receipt_retention_days"))
    rows = db.execute(
        select(DepositRequest.id, DepositRequest.receipt_filename).where(
            DepositRequest.receipt_filename.is_not(None),
            DepositRequest.receipt_uploaded_at <= cutoff,
        )
    ).all()
    for request_id, filename in rows:
        receipt_storage.delete(filename)
        db.execute(
            update(DepositRequest)
            .where(DepositRequest.id == request_id)
            .values(receipt_filename=None, receipt_deleted_at=now)
        )
        db.commit()
    return len(rows)


# --- Действия игрока ---------------------------------------------------------------


def create_deposit(
    db: Session,
    *,
    telegram_id: int,
    method: str,
    amount: int | None = None,
    usdt_amount: Decimal | None = None,
    idempotency_key: str,
    now: datetime | None = None,
) -> tuple[DepositRequest, bool]:
    """Создаёт заявку и выдаёт реквизиты. Возвращает (заявка, создана_ли_сейчас).

    fiat: игрок вводит `amount` (тенге). crypto: игрок вводит `usdt_amount`, а сумма
    в тенге считается по курсу из настроек; курс сохраняется в заявке. Лимиты
    проверяются по сумме в тенге в обоих случаях.
    """
    now = now or _utcnow()
    user = _active_user(db, telegram_id)

    # Повтор того же запроса возвращает уже созданную заявку (до всех остальных проверок).
    existing = db.scalar(
        select(DepositRequest).where(
            DepositRequest.user_id == user.id,
            DepositRequest.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        return existing, False

    account = user.poker_account
    if account is None or account.status != PokerAccountStatus.APPROVED:
        raise ServiceError("account_not_approved")  # Q-3: сначала админ подтверждает игрока
    if method not in DepositMethod.ALL:
        raise ServiceError("invalid_method")

    usdt: Decimal | None = None
    crypto_cents: int | None = None
    rate_text: str | None = None
    if method == DepositMethod.FIAT:
        if amount is None or usdt_amount is not None:
            raise ServiceError("invalid_amount")
        amount_kzt = amount
    else:
        if usdt_amount is None or amount is not None:
            raise ServiceError("invalid_amount")
        usdt = _normalize_usdt(usdt_amount)
        rate = app_settings.get_usdt_rate(db, now)
        if rate is None:
            raise ServiceError("exchange_rate_unavailable")
        amount_kzt = usdt_to_kzt(usdt, rate)
        crypto_cents = int(usdt * 100)
        rate_text = _fmt(rate)

    minimum = app_settings.get_int(db, "deposit_min_amount")
    maximum = app_settings.get_int(db, "deposit_max_amount")
    if not minimum <= amount_kzt <= maximum:
        extra = {"amount_kzt": amount_kzt} if method == DepositMethod.CRYPTO else {}
        raise ServiceError("amount_out_of_range", min=minimum, max=maximum, **extra)

    # Просроченные заявки игрока закрываем сразу: они не должны мешать новой.
    for request_id in db.scalars(
        select(DepositRequest.id).where(
            DepositRequest.user_id == user.id,
            DepositRequest.status == DepositStatus.AWAITING_RECEIPT,
            DepositRequest.expires_at <= now,
        )
    ).all():
        _expire_one(db, request_id, now)
    if db.scalar(
        select(DepositRequest.id).where(
            DepositRequest.user_id == user.id,
            DepositRequest.status == DepositStatus.AWAITING_RECEIPT,
        )
    ):
        raise ServiceError("deposit_awaiting_receipt")

    percent = app_settings.get_commission_percent(db, "deposit")
    details = requisites.get_provider().reserve(method, amount_kzt, usdt_amount=usdt)
    if details is None:
        raise ServiceError("no_requisites_available")

    timeout = app_settings.get_int(db, "deposit_receipt_timeout_minutes")
    request = DepositRequest(
        user_id=user.id,
        poker_account_id=account.id,
        method=method,
        amount=amount_kzt,
        crypto_amount=crypto_cents,
        exchange_rate=rate_text,
        commission_percent=format(percent.normalize(), "f"),
        commission_amount=app_settings.calc_commission(amount_kzt, percent),
        status=DepositStatus.AWAITING_RECEIPT,
        payment_details=details,
        idempotency_key=idempotency_key,
        expires_at=now + timedelta(minutes=timeout),
    )
    db.add(request)
    try:
        db.flush()  # нужен id для истории
        _history(db, request.id, None, DepositStatus.AWAITING_RECEIPT, "player", user.id)
        db.commit()
    except IntegrityError:
        # Параллельный повтор с тем же ключом успел раньше.
        db.rollback()
        existing = db.scalar(
            select(DepositRequest).where(
                DepositRequest.user_id == user.id,
                DepositRequest.idempotency_key == idempotency_key,
            )
        )
        if existing is None:
            raise
        return existing, False
    db.refresh(request)
    return request, True


def cancel_deposit(db: Session, *, telegram_id: int, request_id: int) -> DepositRequest:
    """Отмена игроком возможна только до чека (Q-5). Повторная отмена безвредна."""
    user = _active_user(db, telegram_id)
    request = _owned(db, user, request_id)
    if request.status == DepositStatus.CANCELLED:
        return request

    result = db.execute(
        update(DepositRequest)
        .where(
            DepositRequest.id == request.id,
            DepositRequest.status == DepositStatus.AWAITING_RECEIPT,
        )
        .values(status=DepositStatus.CANCELLED)
    )
    if result.rowcount == 0:
        db.rollback()
        raise ServiceError("invalid_transition")
    _history(
        db,
        request.id,
        DepositStatus.AWAITING_RECEIPT,
        DepositStatus.CANCELLED,
        "player",
        user.id,
        "Отмена игроком до отправки чека",
    )
    db.commit()
    return _load(db, request.id)  # type: ignore[return-value]


def attach_receipt(
    db: Session,
    *,
    telegram_id: int,
    request_id: int,
    data: bytes,
    now: datetime | None = None,
) -> DepositRequest:
    """Принимает чек (JPEG, PNG, PDF до 10 МБ) и передаёт заявку оператору."""
    now = now or _utcnow()
    user = _active_user(db, telegram_id)
    request = _owned(db, user, request_id)

    if len(data) > receipt_storage.MAX_RECEIPT_BYTES:
        raise ServiceError("receipt_too_large", max_bytes=receipt_storage.MAX_RECEIPT_BYTES)
    kind = receipt_storage.sniff(data) if data else None
    if kind is None:
        raise ServiceError("invalid_receipt")
    content_type, extension = kind

    if request.status != DepositStatus.AWAITING_RECEIPT:
        raise ServiceError(
            "request_expired" if request.status == DepositStatus.EXPIRED else "invalid_transition"
        )

    filename = receipt_storage.save(data, extension)
    result = db.execute(
        update(DepositRequest)
        .where(
            DepositRequest.id == request.id,
            DepositRequest.status == DepositStatus.AWAITING_RECEIPT,
            DepositRequest.expires_at > now,
        )
        .values(
            status=DepositStatus.PENDING,
            receipt_filename=filename,
            receipt_content_type=content_type,
            receipt_size=len(data),
            receipt_uploaded_at=now,
        )
    )
    if result.rowcount == 0:
        # Время вышло или заявку отменили между проверкой и записью: файл не нужен.
        db.rollback()
        receipt_storage.delete(filename)
        current = _load(db, request.id)
        late = current is not None and current.status in (
            DepositStatus.AWAITING_RECEIPT,
            DepositStatus.EXPIRED,
        )
        raise ServiceError("request_expired" if late else "invalid_transition")
    _history(
        db,
        request.id,
        DepositStatus.AWAITING_RECEIPT,
        DepositStatus.PENDING,
        "player",
        user.id,
        "Чек получен",
    )
    db.commit()
    return _load(db, request.id)  # type: ignore[return-value]


def get_deposit(db: Session, *, telegram_id: int, request_id: int) -> DepositRequest:
    return _owned(db, _active_user(db, telegram_id), request_id)


def list_deposits(db: Session, *, telegram_id: int, limit: int = LIST_LIMIT) -> list[DepositRequest]:
    user = _active_user(db, telegram_id)
    return list(
        db.scalars(
            select(DepositRequest)
            .where(DepositRequest.user_id == user.id)
            .order_by(DepositRequest.id.desc())
            .limit(limit)
        ).all()
    )
