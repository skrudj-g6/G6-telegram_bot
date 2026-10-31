import pytest
from pydantic import ValidationError

from app.core.config import Settings

TOKEN = "0123456789abcdef0123"


def make(**overrides) -> Settings:
    """Settings без чтения .env и окружения."""
    values = {"database_url": "sqlite://", "bot_service_token": TOKEN}
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_invalid_timezone_rejected():
    with pytest.raises(ValidationError):
        make(app_timezone="Mars/Olympus")


def test_invalid_log_level_rejected():
    with pytest.raises(ValidationError):
        make(log_level="LOUD")


def test_database_url_is_required(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, bot_service_token=TOKEN)


def test_bot_service_token_is_required(monkeypatch):
    monkeypatch.delenv("BOT_SERVICE_TOKEN", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="sqlite://")


def test_short_bot_service_token_rejected():
    with pytest.raises(ValidationError):
        make(bot_service_token="short")


def test_timezone_property():
    assert str(make(app_timezone="Asia/Almaty").timezone) == "Asia/Almaty"


def test_default_club_id():
    assert make().club_id == "692609"


def test_production_flag():
    assert make(app_env="production").is_production
    assert not make(app_env="development").is_production
