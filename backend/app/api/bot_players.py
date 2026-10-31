from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_bot_token
from app.db.session import get_db
from app.schemas.players import (
    LinkAccountRequest,
    PokerAccountOut,
    RegisterOut,
    RegisterRequest,
    UserOut,
)
from app.services import players

# Внутренний API: доступен только боту (service-token), наружу не публикуется.
router = APIRouter(
    prefix="/bot/v1",
    tags=["bot"],
    dependencies=[Depends(require_bot_token)],
)


@router.post("/users/register", response_model=RegisterOut)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    """Регистрация игрока. 201 — создан, 200 — уже был (бот не ведёт его по воронке повторно)."""
    user, created = players.register_user(
        db,
        telegram_id=payload.telegram_id,
        username=payload.username,
        first_name=payload.first_name,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return RegisterOut(**UserOut.from_model(user).model_dump(), created=created)


@router.get("/users/{telegram_id}", response_model=UserOut)
def get_profile(telegram_id: int, db: Session = Depends(get_db)):
    """Профиль для `/start` и раздела «Мой профиль»; 404 — игрок не зарегистрирован."""
    return UserOut.from_model(players.get_user(db, telegram_id))


@router.put("/users/{telegram_id}/poker-account", response_model=PokerAccountOut)
def link_poker_account(
    telegram_id: int, payload: LinkAccountRequest, db: Session = Depends(get_db)
):
    """Привязка игрового ID. Аккаунт получает статус pending до подтверждения админом."""
    account = players.link_poker_account(
        db, telegram_id=telegram_id, raw_player_id=payload.player_id
    )
    return PokerAccountOut.from_model(account)
