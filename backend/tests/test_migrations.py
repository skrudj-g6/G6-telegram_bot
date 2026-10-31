from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

import app.models  # noqa: F401
from app.core.config import get_settings
from app.db.base import Base

ALEMBIC_DIR = Path(__file__).resolve().parents[1] / "alembic"


@pytest.fixture
def migration_db(monkeypatch, tmp_path):
    """Отдельная пустая БД: alembic/env.py берёт URL из настроек (DATABASE_URL)."""
    url = f"sqlite+pysqlite:///{tmp_path.as_posix()}/migration.db"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    yield url
    get_settings.cache_clear()


def alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    return config


def test_upgrade_creates_schema_and_club(migration_db):
    command.upgrade(alembic_config(), "head")
    engine = create_engine(migration_db)
    assert {
        "clubs",
        "users",
        "poker_accounts",
        "app_settings",
        "deposit_requests",
        "deposit_status_history",
    } <= set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT club_id, name FROM clubs")).all()
        settings = dict(conn.execute(text("SELECT key, value FROM app_settings")).all())
    assert [tuple(r) for r in rows] == [("692609", "Altyn Crown")]
    # Начальные лимиты и таймауты владельца (Q-6, Q-9, Q-23).
    assert settings == {
        "deposit_min_amount": "1000",
        "deposit_max_amount": "2000000",
        "withdrawal_min_amount": "1000",
        "withdrawal_max_amount": "2000000",
        "deposit_receipt_timeout_minutes": "10",
        "receipt_retention_days": "7",
    }


def test_downgrade_one_step_keeps_players(migration_db):
    """Откат этапа 3 не трогает игроков и клуб."""
    config = alembic_config()
    command.upgrade(config, "head")
    command.downgrade(config, "0002")
    tables = set(inspect(create_engine(migration_db)).get_table_names())
    assert {"clubs", "users", "poker_accounts"} <= tables
    assert not {"deposit_requests", "app_settings", "deposit_status_history"} & tables
    assert "block_reason" not in {
        c["name"] for c in inspect(create_engine(migration_db)).get_columns("users")
    }


def test_migrations_match_models(migration_db):
    """Схема после миграций совпадает с моделями (колонки, ключи, индексы, уникальные).

    Типы колонок не сравниваются: SQLite хранит их нестрого и дал бы ложные расхождения.
    """
    command.upgrade(alembic_config(), "head")
    engine = create_engine(migration_db)
    with engine.connect() as conn:
        context = MigrationContext.configure(
            conn,
            opts={
                "compare_type": False,
                "include_object": lambda obj, name, type_, reflected, compare_to: not (
                    type_ == "table" and name == "alembic_version"
                ),
            },
        )
        assert compare_metadata(context, Base.metadata) == []


def test_downgrade_removes_tables(migration_db):
    config = alembic_config()
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    engine = create_engine(migration_db)
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
