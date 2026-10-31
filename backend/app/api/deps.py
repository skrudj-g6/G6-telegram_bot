import hmac

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


def require_bot_token(x_service_token: str | None = Header(default=None)) -> None:
    """Внутренняя авторизация бот → backend (D-3).

    Telegram ID принимается только от аутентифицированного бота, который берёт его
    из update, пришедшего от Telegram.
    """
    expected = get_settings().bot_service_token
    if not x_service_token or not hmac.compare_digest(
        x_service_token.encode(), expected.encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized"},
        )
