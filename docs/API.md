# API

Интерактивная документация (Swagger) доступна на `/docs` только вне production.

## Здоровье
`GET /health` — процесс жив. `GET /health/ready` — backend видит БД.

## Бот → backend (`/bot/v1`, заголовок `X-Service-Token`)
Наружу не публикуется (nginx панели отвечает 404 на `/bot/`).

| Метод и путь | Назначение |
|---|---|
| `POST /users/register` | Регистрация игрока по Telegram ID |
| `GET /users/{tg}` | Профиль и статус |
| `PUT /users/{tg}/poker-account` | Привязка игрового ID `XXXX-XXXX` |
| `GET /settings/limits`, `GET /banks` | Лимиты и список банков |
| `GET /quotes/usdt-deposit`, `GET /quotes/withdrawal` | Расчёт суммы до подтверждения |
| `POST/GET /users/{tg}/deposits`, `GET …/{id}`, `POST …/{id}/cancel`, `POST …/{id}/receipt` | Пополнения и чек |
| `POST/GET /users/{tg}/withdrawals`, `GET …/{id}`, `POST …/{id}/cancel` | Выводы |
| `POST /notifications/claim`, `POST /notifications/{id}/sent`, `POST /notifications/{id}/failed` | Очередь уведомлений |

Создание заявок принимает в теле поле `idempotency_key`: повтор с тем же ключом возвращает 200 и ту же заявку, новая создаётся с кодом 201.

## Панель (`/admin/v1`, `Authorization: Bearer`)

| Метод и путь | Право |
|---|---|
| `POST /auth/login`, `/auth/refresh`, `/auth/logout`, `GET /auth/me`, `POST /auth/change-password` | — |
| `GET /deposits`, `/withdrawals` (фильтры `status`, `method`, `q`, `oldest_first`, `limit`, `offset`), `GET …/{id}` | `requests.view` |
| `POST …/{id}/take`, `/release`, `/complete`, `/reject` (`{"reason"}`) | `requests.process` |
| `GET /deposits/{id}/receipt` | `receipts.view` (пишется в аудит) |
| `GET /players`, `GET /players/{id}` | `players.view` |
| `POST /players/{id}/approve`, `/reject`, `/unblock` | `players.moderate` |
| `GET/PUT /settings`, `GET/POST /banks`, `PATCH /banks/{id}` | `settings.view` / `settings.edit` |
| `GET/POST /staff`, `PATCH /staff/{id}`, `POST /staff/{id}/reset-password` | `staff.manage` |
| `GET /audit` | `audit.view` |

Ошибки: `{"detail": {"code": "invalid_transition", ...}}`. Основные коды: `invalid_credentials`, `too_many_attempts`, `forbidden`, `invalid_transition`, `request_not_found`, `reason_required`, `receipt_not_available`, `amount_out_of_range`, `exchange_rate_unavailable`, `no_requisites_available`, `withdrawal_already_open`.
