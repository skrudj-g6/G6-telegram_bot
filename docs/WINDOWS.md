# Запуск на Windows (разработка и проверка)

1. Установите Docker Desktop (режим WSL 2) и Git.
2. В PowerShell:
```powershell
git clone https://github.com/skrudj-g6/G6-telegram_bot.git
cd G6-telegram_bot
copy .env.example .env
notepad .env        # задайте POSTGRES_PASSWORD, BOT_SERVICE_TOKEN, JWT_SECRET, BOT_TOKEN
docker compose up --build
```
3. Панель: <http://localhost:8080>, API: <http://127.0.0.1:8000/health>.
4. Первый владелец (в другом окне PowerShell):
```powershell
docker compose exec backend python -m app.cli create-staff --login owner --name "Имя" --role owner
```
5. Тесты без Docker:
```powershell
cd backend; python -m venv .venv; .venv\Scripts\activate; pip install -r requirements.txt; pytest
cd ..\bot; pip install -r requirements.txt; pytest
cd ..\admin; npm install; npm test; npm run build
```
Тесты на PostgreSQL (гонки) включаются переменной `TEST_POSTGRES_URL`; без неё пропускаются. Полный набор запускается в GitHub Actions на каждый push.

Скрипты бэкапа (`scripts/*.sh`) рассчитаны на Linux-сервер; на Windows запускайте их из WSL.
