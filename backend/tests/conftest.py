import os

# Тестам не нужен PostgreSQL: до этапа 2 достаточно легковесной БД для /health/ready.
# Переменные задаются ДО импорта приложения.
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["APP_ENV"] = "test"
os.environ["APP_TIMEZONE"] = "Asia/Almaty"
os.environ["LOG_LEVEL"] = "INFO"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
