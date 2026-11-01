import logging
from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.models import AppSetting

logger = logging.getLogger(__name__)

# Курс USDT к тенге (сколько тенге за 1 USDT). Значения по умолчанию нет намеренно:
# выдуманный курс недопустим, пока он не получен от источника или не задан владельцем (ТЗ §17).
USDT_RATE_KEY = "usdt_kzt_rate"
# Когда курс получен от источника (ISO-8601, UTC) и откуда.
USDT_RATE_UPDATED_KEY = "usdt_kzt_rate_updated_at"
USDT_RATE_SOURCE_KEY = "usdt_kzt_rate_source"
# "auto" — курс обновляет backend (Q-30), "manual" — курс задан владельцем в панели и
# не устаревает. Незнакомое значение трактуется как "auto".
USDT_RATE_MODE_KEY = "usdt_rate_mode"
MODE_AUTO = "auto"
MODE_MANUAL = "manual"

# Значения по умолчанию на случай, если строки в app_settings нет. Те же значения
# записывает миграция, чтобы владелец мог менять их в панели (Q-6, Q-9, Q-23).
DEFAULTS: dict[str, int] = {
    "deposit_min_amount": 1000,
    "deposit_max_amount": 2_000_000,
    "withdrawal_min_amount": 1000,
    "withdrawal_max_amount": 2_000_000,
    "deposit_receipt_timeout_minutes": 10,
    "receipt_retention_days": 7,
    # Автоматический курс старше этого возраста не используется (источник мог отказать).
    "usdt_rate_max_age_minutes": 30,
}


def get_int(db: Session, key: str) -> int:
    row = db.get(AppSetting, key)
    if row is not None:
        try:
            return int(row.value)
        except ValueError:
            logger.error("Некорректное значение настройки %s, используется значение по умолчанию", key)
    return DEFAULTS[key]


def get_str(db: Session, key: str) -> str | None:
    row = db.get(AppSetting, key)
    return row.value if row is not None else None


def set_str(db: Session, key: str, value: str) -> None:
    """Записывает настройку. Коммит выполняет вызывающий."""
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value


def get_usdt_rate_mode(db: Session) -> str:
    mode = (get_str(db, USDT_RATE_MODE_KEY) or MODE_AUTO).strip().lower()
    return MODE_MANUAL if mode == MODE_MANUAL else MODE_AUTO


def parse_rate(raw: str | None) -> Decimal | None:
    """Строка → положительный конечный курс; иначе None."""
    if raw is None:
        return None
    try:
        rate = Decimal(raw.strip())
    except InvalidOperation:
        return None
    return rate if rate.is_finite() and rate > 0 else None


def _parse_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def get_usdt_rate(db: Session, now: datetime | None = None) -> Decimal | None:
    """Курс USDT/KZT, пригодный для расчётов, или None.

    manual: курс владельца действует без ограничения по возрасту.
    auto: курс действует, только если получен не раньше `usdt_rate_max_age_minutes` назад;
    при отказе источника пополнение криптой временно недоступно, а не считается по
    устаревшему курсу.
    """
    rate = parse_rate(get_str(db, USDT_RATE_KEY))
    if rate is None:
        if get_str(db, USDT_RATE_KEY) is not None:
            logger.error("Некорректный курс USDT в настройках")
        return None
    if get_usdt_rate_mode(db) == MODE_MANUAL:
        return rate

    updated = _parse_time(get_str(db, USDT_RATE_UPDATED_KEY))
    if updated is None:
        return None
    now = now or datetime.now(timezone.utc)
    max_age = timedelta(minutes=get_int(db, "usdt_rate_max_age_minutes"))
    if now - updated > max_age:
        return None
    return rate


COMMISSION_KEYS = {
    "deposit": "deposit_commission_percent",
    "withdrawal": "withdrawal_commission_percent",
}
MAX_COMMISSION_PERCENT = Decimal("50")  # допустимо от -50 до +50


def get_commission_percent(db: Session, direction: str) -> Decimal:
    """Процент клуба (in = deposit, out = withdrawal), от -50 до +50, до двух знаков.

    Плюс — бонус игроку (больше фишек / больше тенге), минус — комиссия (меньше).

    Значение задаёт владелец в панели. Некорректное значение считается нулём и пишется в лог.
    """
    raw = get_str(db, COMMISSION_KEYS[direction])
    if raw is None:
        return Decimal(0)
    try:
        value = Decimal(raw.strip())
        if (
            value.is_finite()
            and -MAX_COMMISSION_PERCENT <= value <= MAX_COMMISSION_PERCENT
            and value.as_tuple().exponent >= -2
        ):
            return value
    except InvalidOperation:
        pass
    logger.error("Некорректная комиссия %s, используется 0", COMMISSION_KEYS[direction])
    return Decimal(0)


def calc_commission(amount: int, percent: Decimal) -> int:
    """Корректировка суммы в целых тенге со знаком: итог = amount + результат.

    Итог округляется вниз (в пользу клуба): и бонус, и комиссия считаются в целых тенге.
    """
    credit = int((Decimal(amount) * (100 + percent) / 100).to_integral_value(rounding=ROUND_DOWN))
    return credit - amount


def _fmt_percent(value: Decimal) -> str:
    return format(value.normalize(), "f")


def get_limits(db: Session) -> dict[str, dict]:
    return {
        "deposit": {
            "min": get_int(db, "deposit_min_amount"),
            "max": get_int(db, "deposit_max_amount"),
        },
        "withdrawal": {
            "min": get_int(db, "withdrawal_min_amount"),
            "max": get_int(db, "withdrawal_max_amount"),
        },
        "commission": {
            "deposit": _fmt_percent(get_commission_percent(db, "deposit")),
            "withdrawal": _fmt_percent(get_commission_percent(db, "withdrawal")),
        },
    }
