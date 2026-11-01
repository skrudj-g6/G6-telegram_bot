"""Заявки на вывод (ТЗ §6) с поправками владельца (MIGRATION_PLAN, раздел 8).

Жизненный цикл на стороне игрока:
    pending --игрок--> cancelled      (пока оператор не взял в работу)
    pending --оператор--> processing --> completed / rejected   (этап 5)

Переходы выполняются условным UPDATE: отмена игроком и взятие в работу оператором не могут
оба оказаться успешными.
"""

import re

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Bank,
    PokerAccountStatus,
    UserStatus,
    WithdrawalMethod,
    WithdrawalRequest,
    WithdrawalStatus,
    WithdrawalStatusHistory,
)
from app.services import app_settings, crypto_payout, players
from app.services.errors import ServiceError

LIST_LIMIT = 20
# Имя получателя: буквы любых алфавитов, пробел, дефис, точка, апостроф; 2–100 символов.
_NAME_RE = re.compile(r"^[^\W\d_](?:[^\W\d_]|[ .'\-’]){1,99}$", re.UNICODE)


def normalize_holder_name(raw: str | None) -> str:
    name = " ".join((raw or "").split())
    if not _NAME_RE.match(name):
        raise ServiceError("invalid_holder_name")
    return name


def list_banks(db: Session) -> list[Bank]:
    return list(
        db.scalars(select(Bank).where(Bank.is_active.is_(True)).order_by(Bank.sort_order, Bank.id))
    )


def quote(db: Session, amount: int) -> dict:
    """Сколько игрок получит с учётом процента клуба (бот показывает до подтверждения)."""
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise ServiceError("invalid_amount")
    minimum = app_settings.get_int(db, "withdrawal_min_amount")
    maximum = app_settings.get_int(db, "withdrawal_max_amount")
    percent = app_settings.get_commission_percent(db, "withdrawal")
    adjustment = app_settings.calc_commission(amount, percent)
    return {
        "amount": amount,
        "min": minimum,
        "max": maximum,
        "within_limits": minimum <= amount <= maximum,
        "commission_percent": format(percent.normalize(), "f"),
        "commission_amount": adjustment,
        "payout_amount": amount + adjustment,
    }


def _history(db, request_id, from_status, to_status, actor_type, actor_id=None, comment=None):
    db.add(
        WithdrawalStatusHistory(
            request_id=request_id,
            from_status=from_status,
            to_status=to_status,
            actor_type=actor_type,
            actor_id=actor_id,
            comment=comment,
        )
    )


def _load(db: Session, request_id: int) -> WithdrawalRequest | None:
    return db.scalar(
        select(WithdrawalRequest)
        .where(WithdrawalRequest.id == request_id)
        .execution_options(populate_existing=True)
    )


def _active_user(db: Session, telegram_id: int):
    user = players.get_user(db, telegram_id)
    if user.status != UserStatus.ACTIVE:
        raise ServiceError("user_blocked")
    return user


def _owned(db: Session, user, request_id: int) -> WithdrawalRequest:
    request = _load(db, request_id)
    if request is None or request.user_id != user.id:
        raise ServiceError("request_not_found")
    return request


def _by_key(db: Session, user_id: int, key: str) -> WithdrawalRequest | None:
    return db.scalar(
        select(WithdrawalRequest).where(
            WithdrawalRequest.user_id == user_id, WithdrawalRequest.idempotency_key == key
        )
    )


def create_withdrawal(
    db: Session,
    *,
    telegram_id: int,
    method: str,
    amount: int,
    holder_name: str | None = None,
    bank_id: int | None = None,
    idempotency_key: str,
) -> tuple[WithdrawalRequest, bool]:
    """Возвращает (заявка, создана_ли_сейчас). Повтор с тем же ключом отдаёт прежнюю заявку."""
    user = _active_user(db, telegram_id)
    existing = _by_key(db, user.id, idempotency_key)
    if existing is not None:
        return existing, False

    account = user.poker_account
    if account is None or account.status != PokerAccountStatus.APPROVED:
        raise ServiceError("account_not_approved")
    if method not in WithdrawalMethod.ALL:
        raise ServiceError("invalid_method")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise ServiceError("invalid_amount")

    name = bank = None
    if method == WithdrawalMethod.FIAT:
        name = normalize_holder_name(holder_name)
        bank = db.get(Bank, bank_id) if bank_id is not None else None
        if bank is None or not bank.is_active:
            raise ServiceError("invalid_bank")
    elif holder_name is not None or bank_id is not None:
        # Для crypto имя и банк не нужны: всё необходимое запрашивает PSP (Q-31).
        raise ServiceError("invalid_method")

    minimum = app_settings.get_int(db, "withdrawal_min_amount")
    maximum = app_settings.get_int(db, "withdrawal_max_amount")
    if not minimum <= amount <= maximum:
        raise ServiceError("amount_out_of_range", min=minimum, max=maximum)

    # Одна открытая заявка на вывод на игрока: защита от дублей и спама оператору.
    if db.scalar(
        select(WithdrawalRequest.id).where(
            WithdrawalRequest.user_id == user.id,
            WithdrawalRequest.status.in_(WithdrawalStatus.OPEN),
        )
    ):
        raise ServiceError("withdrawal_already_open")

    details = None
    if method == WithdrawalMethod.CRYPTO:
        details = crypto_payout.get_provider().start(amount)
        if details is None:
            raise ServiceError("no_requisites_available")

    percent = app_settings.get_commission_percent(db, "withdrawal")
    request = WithdrawalRequest(
        user_id=user.id,
        poker_account_id=account.id,
        method=method,
        amount=amount,
        commission_percent=format(percent.normalize(), "f"),
        commission_amount=app_settings.calc_commission(amount, percent),
        holder_name=name,
        bank_id=bank.id if bank else None,
        bank_name=bank.name if bank else None,
        payment_details=details,
        status=WithdrawalStatus.PENDING,
        idempotency_key=idempotency_key,
    )
    db.add(request)
    try:
        db.flush()
        _history(db, request.id, None, WithdrawalStatus.PENDING, "player", user.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _by_key(db, user.id, idempotency_key)
        if existing is None:
            raise
        return existing, False
    db.refresh(request)
    return request, True


def cancel_withdrawal(db: Session, *, telegram_id: int, request_id: int) -> WithdrawalRequest:
    """Игрок отменяет заявку, пока оператор не взял её в работу. Повтор безвреден."""
    user = _active_user(db, telegram_id)
    request = _owned(db, user, request_id)
    if request.status == WithdrawalStatus.CANCELLED:
        return request
    result = db.execute(
        update(WithdrawalRequest)
        .where(
            WithdrawalRequest.id == request.id,
            WithdrawalRequest.status == WithdrawalStatus.PENDING,
        )
        .values(status=WithdrawalStatus.CANCELLED)
    )
    if result.rowcount == 0:
        db.rollback()
        raise ServiceError("invalid_transition")
    _history(
        db,
        request.id,
        WithdrawalStatus.PENDING,
        WithdrawalStatus.CANCELLED,
        "player",
        user.id,
        "Отмена игроком",
    )
    db.commit()
    return _load(db, request.id)  # type: ignore[return-value]


def get_withdrawal(db: Session, *, telegram_id: int, request_id: int) -> WithdrawalRequest:
    return _owned(db, _active_user(db, telegram_id), request_id)


def list_withdrawals(
    db: Session, *, telegram_id: int, limit: int = LIST_LIMIT
) -> list[WithdrawalRequest]:
    user = _active_user(db, telegram_id)
    return list(
        db.scalars(
            select(WithdrawalRequest)
            .where(WithdrawalRequest.user_id == user.id)
            .order_by(WithdrawalRequest.id.desc())
            .limit(limit)
        ).all()
    )
