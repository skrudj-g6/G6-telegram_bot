# Altyn Crown

Система управления покерным клубом: Telegram-бот, backend (FastAPI), PostgreSQL, админ-панель.
Подробности — в `AUDIT.md` и `MIGRATION_PLAN.md`.

**Статус:** этапы 0–1 (каркас). Работает только backend-скелет: `/health`, `/health/ready`, конфиг, логирование, Alembic. Бот, заявки и админка — следующие этапы.

## Структура

```
backend/            FastAPI + SQLAlchemy 2 + Alembic
  app/core/         config (pydantic-settings), logging
  app/db/           Base, engine, session
  app/api/          роутеры (пока только health)
  alembic/          миграции (0001 — пустая baseline)
  tests/
docker-compose.yml  PostgreSQL + backend
.env.example        шаблон переменных окружения
```

## Запуск через Docker (Windows / Linux)

Нужен Docker Desktop (Windows) или Docker Engine + Compose (Linux).

```powershell
copy .env.example .env      # Linux: cp .env.example .env
# откройте .env и задайте POSTGRES_PASSWORD
docker compose up --build
```

Проверка: <http://127.0.0.1:8000/health> → `{"status":"ok"}`, <http://127.0.0.1:8000/health/ready> → `{"status":"ok"}` (backend видит БД). Документация API (только не в production): <http://127.0.0.1:8000/docs>.

Миграции применяются автоматически при старте backend (`alembic upgrade head`). PostgreSQL наружу не публикуется, API слушает только `127.0.0.1`.

## Запуск тестов без Docker

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate          # Linux: source .venv/bin/activate
pip install -r requirements.txt
pytest
```

Тесты используют in-memory SQLite и не требуют PostgreSQL (переменные задаёт `tests/conftest.py`).

## Миграции

```powershell
cd backend
# нужен DATABASE_URL в окружении или в backend/.env
alembic upgrade head
alembic revision --autogenerate -m "описание"
```

## Секреты

Секреты хранятся только в `.env` (в `.gitignore`). Токены Telegram, пароли и ключи в репозиторий не попадают.
