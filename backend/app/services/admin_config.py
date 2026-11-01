"""Настройки клуба и список банков, которые владелец меняет в панели (Q-6, Q-28, Q-30, Q-33).

Каждое изменение проверяется целиком (все значения или ни одно) и пишется в аудит со
старым и новым значением.
"""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Bank, StaffUser
from app.services import app_settings, audit
from app.services.errors import ServiceError

MAX_AMOUNT = 10**9

INT_RANGES: dict[str, tuple[int, int]] = {
    "deposit_min_amount": (1, MAX_AMOUNT),
    "deposit_max_amount": (1, MAX_AMOUNT),
    "withdrawal_min_amount": (1, MAX_AMOUNT),
    "withdrawal_max_amount": (1, MAX_AMOUNT),
    "deposit_receipt_timeout_minutes": (1, 24 * 60),
    "receipt_retention_days": (1, 365),
    "usdt_rate_max_age_minutes": (1, 24 * 60),
}
PERCENT_KEYS = ("deposit_commission_percent", "withdrawal_commission_percent")
MODE_KEY = app_settings.USDT_RATE_MODE_KEY
MANUAL_RATE_KEY = "usdt_manual_rate"  # не хранится как есть: пишется в usdt_kzt_rate
EDITABLE = set(INT_RANGES) | set(PERCENT_KEYS) | {MODE_KEY, MANUAL_RATE_KEY}


def _int(key: str, value) -> int:
    low, high = INT_RANGES[key]
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ServiceError("invalid_setting", key=key, min=low, max=high)
    return value


def _decimal(key: str, value, low: Decimal, high: Decimal) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ServiceError("invalid_setting", key=key)
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        raise ServiceError("invalid_setting", key=key) from None
    if not number.is_finite() or not low <= number <= high or number.as_tuple().exponent < -2:
        raise ServiceError("invalid_setting", key=key, min=str(low), max=str(high))
    return number


def view(db: Session, now: datetime | None = None) -> dict:
    """Все настройки для формы в панели и состояние курса USDT."""
    values: dict = {key: app_settings.get_int(db, key) for key in INT_RANGES}
    for key in PERCENT_KEYS:
        direction = "deposit" if key.startswith("deposit") else "withdrawal"
        values[key] = format(app_settings.get_commission_percent(db, direction).normalize(), "f")
    effective = app_settings.get_usdt_rate(db, now)
    values[MODE_KEY] = app_settings.get_usdt_rate_mode(db)
    values["usdt_rate"] = {
        "current": app_settings.get_str(db, app_settings.USDT_RATE_KEY),
        "source": app_settings.get_str(db, app_settings.USDT_RATE_SOURCE_KEY),
        "updated_at": app_settings.get_str(db, app_settings.USDT_RATE_UPDATED_KEY) or None,
        # None — курса нет или он устарел: пополнение криптой сейчас недоступно.
        "usable": None if effective is None else format(effective.normalize(), "f"),
    }
    return values


def update(
    db: Session,
    *,
    staff: StaffUser,
    changes: dict,
    ip: str | None = None,
    now: datetime | None = None,
) -> dict:
    if not changes:
        raise ServiceError("invalid_setting")
    unknown = set(changes) - EDITABLE
    if unknown:
        raise ServiceError("unknown_setting", key=sorted(unknown)[0])
    now = now or datetime.now(timezone.utc)

    before = view(db, now)
    new: dict = {}
    for key, value in changes.items():
        if key in INT_RANGES:
            new[key] = _int(key, value)
        elif key in PERCENT_KEYS:
            new[key] = _decimal(key, value, Decimal(-50), Decimal(50))
        elif key == MODE_KEY:
            if value not in (app_settings.MODE_AUTO, app_settings.MODE_MANUAL):
                raise ServiceError("invalid_setting", key=key)
            new[key] = value
        else:  # MANUAL_RATE_KEY
            new[key] = _decimal(key, value, Decimal("0.01"), Decimal(1_000_000))

    # Границы не должны пересекаться: проверяем итоговые значения, а не только присланные.
    for prefix in ("deposit", "withdrawal"):
        low = new.get(f"{prefix}_min_amount", before[f"{prefix}_min_amount"])
        high = new.get(f"{prefix}_max_amount", before[f"{prefix}_max_amount"])
        if low > high:
            raise ServiceError("invalid_limits", min=low, max=high)

    mode_after = new.get(MODE_KEY, before[MODE_KEY])
    if MANUAL_RATE_KEY in new and mode_after != app_settings.MODE_MANUAL:
        raise ServiceError("manual_rate_requires_manual_mode")
    if (
        mode_after == app_settings.MODE_MANUAL
        and before[MODE_KEY] != app_settings.MODE_MANUAL
        and MANUAL_RATE_KEY not in new
        and app_settings.parse_rate(app_settings.get_str(db, app_settings.USDT_RATE_KEY)) is None
    ):
        # Ручной режим без курса оставил бы пополнение криптой без курса.
        raise ServiceError("manual_rate_required")

    audit_changes: dict = {}
    for key, value in new.items():
        if key == MANUAL_RATE_KEY:
            old = app_settings.get_str(db, app_settings.USDT_RATE_KEY)
            text = format(value, "f")
            app_settings.set_str(db, app_settings.USDT_RATE_KEY, text)
            app_settings.set_str(db, app_settings.USDT_RATE_UPDATED_KEY, now.isoformat())
            app_settings.set_str(db, app_settings.USDT_RATE_SOURCE_KEY, f"manual:{staff.login}")
            audit_changes["usdt_rate"] = {"from": old, "to": text}
            continue
        text = format(value.normalize(), "f") if isinstance(value, Decimal) else str(value)
        old = before[key]
        if str(old) != text:
            audit_changes[key] = {"from": old, "to": text}
        app_settings.set_str(db, key, text)

    if before[MODE_KEY] == app_settings.MODE_MANUAL and mode_after == app_settings.MODE_AUTO:
        # Ручной курс не должен выдавать себя за свежий автоматический.
        app_settings.set_str(db, app_settings.USDT_RATE_UPDATED_KEY, "")
        app_settings.set_str(db, app_settings.USDT_RATE_SOURCE_KEY, "")

    audit.record(
        db, staff_id=staff.id, action="settings.updated", entity_type="settings",
        details=audit_changes, ip=ip,
    )
    db.commit()
    return view(db, now)


# --- Банки -------------------------------------------------------------------------


def list_banks(db: Session) -> list[Bank]:
    return list(db.scalars(select(Bank).order_by(Bank.sort_order, Bank.id)).all())


def _bank_name(raw: str) -> str:
    name = " ".join((raw or "").split())
    if not 1 <= len(name) <= 100:
        raise ServiceError("invalid_bank_data")
    return name


def create_bank(db: Session, *, staff: StaffUser, name: str, ip: str | None = None) -> Bank:
    name = _bank_name(name)
    last = db.scalar(select(Bank.sort_order).order_by(Bank.sort_order.desc()).limit(1)) or 0
    bank = Bank(name=name, sort_order=last + 1)
    db.add(bank)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ServiceError("bank_exists") from None
    audit.record(
        db, staff_id=staff.id, action="bank.created", entity_type="bank", entity_id=bank.id,
        details={"name": name}, ip=ip,
    )
    db.commit()
    return bank


def update_bank(
    db: Session,
    *,
    staff: StaffUser,
    bank_id: int,
    name: str | None = None,
    is_active: bool | None = None,
    sort_order: int | None = None,
    ip: str | None = None,
) -> Bank:
    bank = db.get(Bank, bank_id)
    if bank is None:
        raise ServiceError("bank_not_found")
    changes: dict = {}
    if name is not None:
        new_name = _bank_name(name)
        if new_name != bank.name:
            changes["name"] = {"from": bank.name, "to": new_name}
            bank.name = new_name
    if is_active is not None and is_active != bank.is_active:
        changes["is_active"] = {"from": bank.is_active, "to": is_active}
        bank.is_active = is_active
    if sort_order is not None and sort_order != bank.sort_order:
        changes["sort_order"] = {"from": bank.sort_order, "to": sort_order}
        bank.sort_order = sort_order
    if not changes:
        return bank
    audit.record(
        db, staff_id=staff.id, action="bank.updated", entity_type="bank", entity_id=bank.id,
        details=changes, ip=ip,
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ServiceError("bank_exists") from None
    return bank
