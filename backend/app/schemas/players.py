from datetime import datetime

from pydantic import BaseModel, Field

from app.models import PokerAccount, User


class RegisterRequest(BaseModel):
    telegram_id: int = Field(gt=0)
    username: str | None = Field(default=None, max_length=64)
    first_name: str = Field(min_length=1, max_length=255)


class LinkAccountRequest(BaseModel):
    # Формат проверяет сервис: ответ об ошибке должен быть понятным боту.
    player_id: str = Field(max_length=64)


class PokerAccountOut(BaseModel):
    club_id: str
    player_id: str
    status: str
    reject_reason: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, account: PokerAccount) -> "PokerAccountOut":
        return cls(
            club_id=account.club.club_id,
            player_id=account.player_id,
            status=account.status,
            reject_reason=account.reject_reason,
            created_at=account.created_at,
        )


class UserOut(BaseModel):
    telegram_id: int
    username: str | None
    first_name: str
    status: str
    registered_at: datetime
    poker_account: PokerAccountOut | None

    @classmethod
    def from_model(cls, user: User) -> "UserOut":
        account = user.poker_account
        return cls(
            telegram_id=user.telegram_id,
            username=user.username,
            first_name=user.first_name,
            status=user.status,
            registered_at=user.created_at,
            poker_account=PokerAccountOut.from_model(account) if account else None,
        )


class RegisterOut(UserOut):
    # True — игрок зарегистрирован этим вызовом; False — уже был в системе.
    created: bool
