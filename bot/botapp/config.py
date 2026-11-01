"""Настройки бота из окружения. Токены в коде и в логах не хранятся."""

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo


class ConfigError(RuntimeError):
    pass


def _required(env: dict, name: str) -> str:
    value = (env.get(name) or "").strip()
    if not value:
        raise ConfigError(f"Не задана переменная окружения {name}")
    return value


@dataclass(frozen=True)
class Config:
    bot_token: str
    backend_url: str
    service_token: str
    redis_url: str  # пусто — состояния в памяти (только для разработки)
    club_id: str
    club_invite_url: str
    support_url: str  # пусто — кнопка «Поддержка» без ссылки
    timezone: ZoneInfo

    @classmethod
    def from_env(cls, env: dict | None = None) -> "Config":
        env = dict(os.environ if env is None else env)
        token = _required(env, "BOT_TOKEN")
        service_token = _required(env, "BOT_SERVICE_TOKEN")
        if len(service_token) < 16:
            raise ConfigError("BOT_SERVICE_TOKEN слишком короткий (минимум 16 символов)")
        try:
            tz = ZoneInfo((env.get("APP_TIMEZONE") or "Asia/Almaty").strip())
        except Exception as exc:  # неизвестная зона
            raise ConfigError("Неизвестная таймзона APP_TIMEZONE") from exc
        return cls(
            bot_token=token,
            backend_url=(env.get("BACKEND_URL") or "http://backend:8000").strip().rstrip("/"),
            service_token=service_token,
            redis_url=(env.get("REDIS_URL") or "").strip(),
            club_id=(env.get("CLUB_ID") or "692609").strip(),
            club_invite_url=(env.get("CLUB_INVITE_URL") or "").strip(),
            support_url=(env.get("SUPPORT_URL") or "").strip(),
            timezone=tz,
        )
