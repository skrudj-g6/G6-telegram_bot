from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация из переменных окружения (ТЗ §3, §13). Секретов в коде нет."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    app_timezone: str = "Asia/Almaty"
    # Без значения по умолчанию: пароль БД не должен жить в коде.
    database_url: str
    # Секрет внутренней авторизации бот → backend (D-3). Только из ENV.
    bot_service_token: str
    # Секрет подписи access-токенов сотрудников (D-4). Только из ENV, минимум 32 символа.
    jwt_secret: str
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    # Код клуба в покерном приложении (ТЗ §2).
    club_id: str = "692609"
    # Каталог для чеков игроков (Q-23). В Docker — отдельный том.
    receipts_dir: str = "./data/receipts"
    # Автозакрытие заявок без чека, удаление старых чеков, обновление курса USDT.
    # В тестах отключается.
    background_jobs_enabled: bool = True
    # Источник автоматического курса USDT/KZT (Q-30): "coingecko" или "none" (выключено,
    # тогда курс задаётся вручную в режиме manual).
    rate_source: str = "coingecko"
    rate_source_url: str = "https://api.coingecko.com/api/v3/simple/price"

    @field_validator("rate_source")
    @classmethod
    def _check_rate_source(cls, value: str) -> str:
        source = value.strip().lower()
        if source not in {"coingecko", "none"}:
            raise ValueError(f"Неизвестный источник курса: {value!r}")
        return source

    @field_validator("jwt_secret")
    @classmethod
    def _check_jwt_secret(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("JWT_SECRET слишком короткий (минимум 32 символа)")
        return value

    @field_validator("bot_service_token")
    @classmethod
    def _check_service_token(cls, value: str) -> str:
        if len(value) < 16:
            raise ValueError("BOT_SERVICE_TOKEN слишком короткий (минимум 16 символов)")
        return value

    @field_validator("app_timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Неизвестная таймзона: {value!r}") from exc
        return value

    @field_validator("log_level")
    @classmethod
    def _check_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"Неизвестный уровень логирования: {value!r}")
        return level

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)


@lru_cache
def get_settings() -> Settings:
    return Settings()
