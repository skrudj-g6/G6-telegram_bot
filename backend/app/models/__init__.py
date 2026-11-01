# Импорт всех моделей: таблицы регистрируются в Base.metadata (нужно Alembic и тестам).
from app.models.app_setting import AppSetting
from app.models.audit_log import AuditLog
from app.models.bank import Bank
from app.models.club import Club
from app.models.deposit_request import DepositMethod, DepositRequest, DepositStatus
from app.models.deposit_status_history import DepositStatusHistory
from app.models.poker_account import PokerAccount, PokerAccountStatus
from app.models.staff import StaffRole, StaffSession, StaffUser
from app.models.user import User, UserStatus
from app.models.withdrawal_request import WithdrawalMethod, WithdrawalRequest, WithdrawalStatus
from app.models.withdrawal_status_history import WithdrawalStatusHistory

__all__ = [
    "AppSetting",
    "AuditLog",
    "Bank",
    "Club",
    "DepositMethod",
    "DepositRequest",
    "DepositStatus",
    "DepositStatusHistory",
    "PokerAccount",
    "PokerAccountStatus",
    "StaffRole",
    "StaffSession",
    "StaffUser",
    "User",
    "UserStatus",
    "WithdrawalMethod",
    "WithdrawalRequest",
    "WithdrawalStatus",
    "WithdrawalStatusHistory",
]
