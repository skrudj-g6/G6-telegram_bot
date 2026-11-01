import pytest

from botapp.config import Config, ConfigError

BASE = {"BOT_TOKEN": "123:abc", "BOT_SERVICE_TOKEN": "x" * 20}


def test_defaults():
    config = Config.from_env(dict(BASE))
    assert config.backend_url == "http://backend:8000"
    assert config.club_id == "692609" and config.redis_url == "" and str(config.timezone) == "Asia/Almaty"


def test_required_values():
    with pytest.raises(ConfigError):
        Config.from_env({"BOT_SERVICE_TOKEN": "x" * 20})
    with pytest.raises(ConfigError):
        Config.from_env({"BOT_TOKEN": "123:abc"})


def test_short_service_token_and_bad_timezone_are_rejected():
    with pytest.raises(ConfigError):
        Config.from_env({**BASE, "BOT_SERVICE_TOKEN": "short"})
    with pytest.raises(ConfigError):
        Config.from_env({**BASE, "APP_TIMEZONE": "Mars/Base"})


def test_trailing_slash_is_removed_and_values_trimmed():
    config = Config.from_env({**BASE, "BACKEND_URL": " http://b:1/ ", "SUPPORT_URL": " https://t.me/x "})
    assert config.backend_url == "http://b:1" and config.support_url == "https://t.me/x"
