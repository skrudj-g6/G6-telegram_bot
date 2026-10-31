# Импорт всех моделей: таблицы регистрируются в Base.metadata (нужно Alembic и тестам).
from app.models.app_setting import AppSetting
from app.models.club import Club
from app.models.deposit_request import DepositMethod, DepositRequest, DepositStatus
from app.models.deposit_status_history import DepositStatusHistory
from app.models.poker_account import PokerAccount, PokerAccountStatus
from app.models.user import User, UserStatus

__all__ = [
    "AppSetting",
    "Club",
    "DepositMethod",
    "DepositRequest",
    "DepositStatus",
    "DepositStatusHistory",
    "PokerAccount",
    "PokerAccountStatus",
    "User",
    "UserStatus",
]
