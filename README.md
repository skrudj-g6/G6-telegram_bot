# Altyn Crown

Система управления покерным клубом: Telegram-бот, backend (FastAPI), PostgreSQL, админ-панель.
Подробности — в `AUDIT.md` и `MIGRATION_PLAN.md`.

**Статус:** этапы 0–3. Backend: каркас, `/health`, конфиг, Alembic, игроки и игровые аккаунты с подтверждением админом, заявки на пополнение (чек, отмена, автозакрытие), внутренний API для бота. Вывод, роли сотрудников, бот и админка — следующие этапы.

Решения владельца и отклонения от ТЗ — в `MIGRATION_PLAN.md`, раздел 8.

## Внутренний API бота (`/bot/v1`)

Доступен только с заголовком `X-Service-Token` (значение `BOT_SERVICE_TOKEN` из `.env`). Telegram ID принимается только от аутентифицированного бота.

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/bot/v1/users/register` | Регистрация. 201 — создан, 200 — уже был |
| GET | `/bot/v1/users/{telegram_id}` | Профиль; 404 — не зарегистрирован (для `/start`) |
| PUT | `/bot/v1/users/{telegram_id}/poker-account` | Привязать игровой ID `XXXX-XXXX` (статус `pending`) |

Заявки на пополнение (игрок):

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/bot/v1/settings/limits` | Лимиты сумм (настраиваются в панели) |
| POST | `/bot/v1/users/{telegram_id}/deposits` | Создать заявку `{method: fiat/crypto, amount, idempotency_key}`; 201 новая, 200 повтор |
| GET | `/bot/v1/users/{telegram_id}/deposits` | «Мои заявки» |
| GET | `/bot/v1/users/{telegram_id}/deposits/{id}` | Одна заявка |
| POST | `/bot/v1/users/{telegram_id}/deposits/{id}/receipt` | Чек (multipart `file`: JPEG, PNG, PDF до 10 МБ) |
| POST | `/bot/v1/users/{telegram_id}/deposits/{id}/cancel` | Отмена, только до чека |

Пока платёжка не подключена, создание заявки отвечает 503 `no_requisites_available`. Игрок, который попытался привязать уже занятый игровой ID, блокируется (403 `user_blocked` на все запросы).

Ошибки: `{"detail": {"code": "..."}}`, коды — `invalid_player_id` (422), `player_id_taken` и `account_locked` (409), `user_not_found` (404), `user_blocked` (403), `unauthorized` (401).
Подтверждение/отклонение игрока админом реализовано в сервисе, HTTP-эндпоинты появятся на этапе 5 (с авторизацией сотрудников).

## Структура

```
backend/            FastAPI + SQLAlchemy 2 + Alembic
  app/core/         config (pydantic-settings), logging
  app/db/           Base, engine, session
  app/models/       модели (clubs, users, poker_accounts)
  app/services/     бизнес-логика
  app/schemas/      Pydantic-схемы
  app/api/          роутеры (health, bot_players)
  alembic/          миграции (0001 baseline, 0002 игроки)
  tests/
docker-compose.yml  PostgreSQL + backend
.env.example        шаблон переменных окружения
```

## Запуск через Docker (Windows / Linux)

Нужен Docker Desktop (Windows) или Docker Engine + Compose (Linux).

```powershell
copy .env.example .env      # Linux: cp .env.example .env
# откройте .env: задайте POSTGRES_PASSWORD и BOT_SERVICE_TOKEN
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

Тесты используют временную SQLite и не требуют PostgreSQL (переменные задаёт `tests/conftest.py`). Ограничения уникальности и CHECK проверяются на SQLite; поведение на PostgreSQL проверяйте через `docker compose up`.

## Миграции

```powershell
cd backend
# нужен DATABASE_URL в окружении или в backend/.env
alembic upgrade head
alembic revision --autogenerate -m "описание"
```

## Секреты

Секреты хранятся только в `.env` (в `.gitignore`). Токены Telegram, пароли и ключи в репозиторий не попадают.
