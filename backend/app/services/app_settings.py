import logging

from sqlalchemy.orm import Session

from app.models import AppSetting

logger = logging.getLogger(__name__)

# Значения по умолчанию на случай, если строки в app_settings нет. Те же значения
# записывает миграция, чтобы владелец мог менять их в панели (Q-6, Q-9, Q-23).
DEFAULTS: dict[str, int] = {
    "deposit_min_amount": 1000,
    "deposit_max_amount": 2_000_000,
    "withdrawal_min_amount": 1000,
    "withdrawal_max_amount": 2_000_000,
    "deposit_receipt_timeout_minutes": 10,
    "receipt_retention_days": 7,
}


def get_int(db: Session, key: str) -> int:
    row = db.get(AppSetting, key)
    if row is not None:
        try:
            return int(row.value)
        except ValueError:
            logger.error("Некорректное значение настройки %s, используется значение по умолчанию", key)
    return DEFAULTS[key]


def get_limits(db: Session) -> dict[str, dict[str, int]]:
    return {
        "deposit": {
            "min": get_int(db, "deposit_min_amount"),
            "max": get_int(db, "deposit_max_amount"),
        },
        "withdrawal": {
            "min": get_int(db, "withdrawal_min_amount"),
            "max": get_int(db, "withdrawal_max_amount"),
        },
    }
