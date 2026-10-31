import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_invalid_timezone_rejected():
    with pytest.raises(ValidationError):
        Settings(database_url="sqlite://", app_timezone="Mars/Olympus")


def test_invalid_log_level_rejected():
    with pytest.raises(ValidationError):
        Settings(database_url="sqlite://", log_level="LOUD")


def test_database_url_is_required(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_timezone_property():
    settings = Settings(database_url="sqlite://", app_timezone="Asia/Almaty")
    assert str(settings.timezone) == "Asia/Almaty"


def test_production_flag():
    assert Settings(database_url="sqlite://", app_env="production").is_production
    assert not Settings(database_url="sqlite://", app_env="development").is_production
