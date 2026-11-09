# Развёртывание на VPS (Ubuntu 22.04/24.04)

Минимум: 1 vCPU, 2 ГБ RAM, 20 ГБ диска. Нужен домен, A-запись которого указывает на сервер (для HTTPS).

## 1. Подготовка сервера
```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git rsync ufw
sudo ufw allow OpenSSH && sudo ufw allow 80 && sudo ufw allow 443 && sudo ufw enable
```
Порт PostgreSQL и порты backend наружу не открываются.

## 2. Код и настройки
```bash
sudo git clone https://github.com/skrudj-g6/G6-telegram_bot.git /opt/altyn && cd /opt/altyn
sudo git checkout main        # или ветка последнего этапа
sudo cp .env.example .env && sudo nano .env
```
Обязательно в `.env`:
- `APP_ENV=production` (включает `Secure` для cookie; в production не работает `/docs`);
- `POSTGRES_PASSWORD`, `BOT_SERVICE_TOKEN`, `JWT_SECRET` — длинные случайные: `openssl rand -hex 32`;
- `BOT_TOKEN` — **новый** токен из @BotFather (прежний был опубликован в git и должен быть перевыпущен);
- `SUPPORT_URL` — ссылка на Telegram админа, `CLUB_INVITE_URL`;
- `DOMAIN=panel.example.com`.

`.env` содержит секреты: `chmod 600 .env`, в git не коммитить.

## 3. Запуск
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose ps
curl -s https://panel.example.com/admin/v1/auth/me   # 401 — значит, всё работает
```
Миграции применяются автоматически при старте backend. Сертификат Caddy получает сам (первые минуты возможны ошибки, пока DNS не обновился).

## 4. Первый владелец
```bash
docker compose exec backend python -m app.cli create-staff --login owner --name "Имя" --role owner
```
Пароль (10–128 символов) спросят в терминале. Дальше сотрудников создаёт владелец в панели («Сотрудники»).

## 5. Бэкап
Настройте cron и копию на другой сервер по [BACKUP.md](BACKUP.md).

## 6. Обновление
```bash
cd /opt/altyn && ./scripts/backup.sh && git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```
Логи: `docker compose logs -f backend bot`.

## Проверка перед запуском
1. Вход в панель, смена пароля владельца.
2. В «Настройках» заданы лимиты, проценты клуба и курс USDT (или автокурс работает).
3. Бот отвечает на `/start`, тестовая заявка доходит до панели, «Выполнено» присылает игроку уведомление.
4. `./scripts/backup.sh` создаёт файл, `restore.sh` проверен на тестовой копии.
