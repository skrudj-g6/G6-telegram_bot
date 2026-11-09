#!/usr/bin/env bash
# Восстановление БД из дампа: ./scripts/restore.sh backups/altyn-20261110-040000.dump
# ВНИМАНИЕ: текущие данные базы будут заменены данными из файла.
set -euo pipefail

cd "$(dirname "$0")/.."
FILE="${1:-}"
[ -n "$FILE" ] && [ -f "$FILE" ] || { echo "Использование: $0 путь/к/дампу.dump" >&2; exit 1; }
[ -f .env ] || { echo "Нет файла .env в $(pwd)" >&2; exit 1; }
set -a; . ./.env; set +a

COMPOSE="${COMPOSE_CMD:-docker compose}"
if [ "${ASSUME_YES:-}" != "1" ]; then
  read -r -p "Заменить базу $POSTGRES_DB данными из $FILE? Введите yes: " answer
  [ "$answer" = "yes" ] || { echo "Отменено."; exit 1; }
fi

# Файл проверяем до остановки сервисов.
$COMPOSE exec -T db pg_restore --list < "$FILE" > /dev/null || { echo "Файл не является дампом" >&2; exit 1; }

echo "Останавливаю backend, бот и панель..."
$COMPOSE stop backend bot admin

echo "Пересоздаю базу..."
$COMPOSE exec -T db psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\" WITH (FORCE)" \
  -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\""

echo "Загружаю дамп..."
$COMPOSE exec -T db pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error < "$FILE"

echo "Запускаю сервисы (backend сам применит недостающие миграции)..."
$COMPOSE start backend bot admin
echo "Готово."
