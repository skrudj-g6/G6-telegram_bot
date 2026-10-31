# Импорт всех моделей: таблицы регистрируются в Base.metadata (нужно Alembic и тестам).
from app.models.club import Club
from app.models.poker_account import PokerAccount, PokerAccountStatus
from app.models.user import User, UserStatus

__all__ = ["Club", "PokerAccount", "PokerAccountStatus", "User", "UserStatus"]
