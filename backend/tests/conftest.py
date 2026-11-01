import os
import tempfile

# Тестам не нужен PostgreSQL: используется файловая SQLite во временной папке.
# Переменные задаются ДО импорта приложения.
_TMP_DIR = tempfile.mkdtemp(prefix="altyn-tests-")
BOT_TOKEN = "test-service-token-0123456789abcdef"

os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_TMP_DIR}/test.db"
os.environ["RECEIPTS_DIR"] = f"{_TMP_DIR}/receipts"
os.environ["BACKGROUND_JOBS_ENABLED"] = "false"  # таймер в тестах вызывается вручную
os.environ["BOT_SERVICE_TOKEN"] = BOT_TOKEN
os.environ["JWT_SECRET"] = "test-jwt-secret-0123456789abcdef0123456789"
os.environ["CLUB_ID"] = "692609"
os.environ["APP_ENV"] = "test"
os.environ["APP_TIMEZONE"] = "Asia/Almaty"
os.environ["LOG_LEVEL"] = "INFO"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.models  # noqa: E402,F401  (регистрирует таблицы в Base.metadata)
from app.db.base import Base  # noqa: E402
from app.db.session import get_engine, get_session_factory  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Club  # noqa: E402


@pytest.fixture(autouse=True)
def _database():
    """Чистая схема и клуб 692609 (как после миграции) для каждого теста."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    with get_session_factory()() as session:
        session.add(Club(club_id="692609", name="Altyn Crown"))
        session.commit()
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    with get_session_factory()() as session:
        yield session


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def bot_headers():
    return {"X-Service-Token": BOT_TOKEN}


class FakeRequisitesProvider:
    """Тестовая «платёжка»: выдаёт реквизиты, запоминает обращения."""

    def __init__(self):
        self.calls = []  # (способ, сумма в тенге)
        self.usdt_amounts = []  # сумма USDT для crypto, None для fiat

    def reserve(self, method, amount, usdt_amount=None):
        self.calls.append((method, amount))
        self.usdt_amounts.append(usdt_amount)
        return {"bank": "Тестовый банк", "card": "0000 0000 0000 0000", "method": method}


@pytest.fixture
def provider(monkeypatch):
    """Подключает платёжку с реквизитами; без этой фикстуры реквизитов нет (Q-22)."""
    from app.services import requisites

    fake = FakeRequisitesProvider()
    monkeypatch.setattr(requisites, "_provider", fake)
    return fake


@pytest.fixture
def usdt_rate(db):
    """Владелец задал курс в панели: 1 USDT = 500.50 тенге. Без фикстуры курса нет."""
    from app.models import AppSetting

    db.add(AppSetting(key="usdt_kzt_rate", value="500.50"))
    db.add(AppSetting(key="usdt_rate_mode", value="manual"))  # ручной курс не устаревает
    db.commit()
    return "500.50"


@pytest.fixture(autouse=True)
def _clean_receipts():
    import shutil
    from pathlib import Path

    yield
    shutil.rmtree(Path(os.environ["RECEIPTS_DIR"]), ignore_errors=True)


class FakeCryptoPayout:
    def __init__(self):
        self.calls = []

    def start(self, amount):
        self.calls.append(amount)
        return {"psp_ref": "TEST-1", "amount": amount}


@pytest.fixture
def crypto_payout(monkeypatch):
    """Подключает PSP для вывода криптой; без фикстуры PSP недоступен (Q-31)."""
    from app.services import crypto_payout as module

    fake = FakeCryptoPayout()
    monkeypatch.setattr(module, "_provider", fake)
    return fake


@pytest.fixture
def banks(db):
    """Банки как после миграции (Q-28); в тестах схема создаётся без миграций."""
    from app.models import Bank

    names = ["Kaspi Bank", "Halyk Bank", "Банк ЦентрКредит", "ForteBank", "Freedom Bank Kazakhstan"]
    rows = [Bank(name=n, sort_order=i) for i, n in enumerate(names, start=1)]
    db.add_all(rows)
    db.commit()
    return {row.name: row.id for row in rows}


PASSWORD = "correct-horse-battery"


@pytest.fixture
def make_staff(db):
    """Создаёт сотрудника напрямую (минуя API): make_staff("operator", login="op1")."""
    from app.models import StaffUser
    from app.core import security

    def factory(role="operator", login=None, password=PASSWORD, active=True):
        login = login or f"{role}-{db.query(StaffUser).count() + 1}"
        staff = StaffUser(
            login=login,
            display_name=login.title(),
            role=role,
            password_hash=security.hash_password(password),
            is_active=active,
        )
        db.add(staff)
        db.commit()
        return staff

    return factory


@pytest.fixture
def auth(client, make_staff):
    """Вход сотрудника: auth("admin") -> заголовки с access-токеном (и сам сотрудник)."""

    def login(role="operator", login=None):
        staff = make_staff(role, login=login)
        response = client.post(
            "/admin/v1/auth/login", json={"login": staff.login, "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        return headers, staff

    return login
