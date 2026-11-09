#!/usr/bin/env bash
# Ежедневный бэкап PostgreSQL. Запуск из корня проекта: ./scripts/backup.sh
# Файлы чеков не копируются: они хранятся неделю и не критичны (MIGRATION_PLAN, Q-23).
set -euo pipefail

cd "$(dirname "$0")/.."
[ -f .env ] || { echo "Нет файла .env в $(pwd)" >&2; exit 1; }
set -a; . ./.env; set +a

DIR="${BACKUP_DIR:-backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
COMPOSE="${COMPOSE_CMD:-docker compose}"
STAMP="$(date +%Y%m%d-%H%M%S)"
FILE="$DIR/altyn-$STAMP.dump"

mkdir -p "$DIR"
umask 077

# Сначала во временный файл: оборванный дамп не должен выглядеть как годный бэкап.
if ! $COMPOSE exec -T db pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > "$FILE.tmp"; then
  rm -f "$FILE.tmp"
  echo "pg_dump завершился с ошибкой" >&2
  exit 1
fi
# Проверка, что архив читается.
if ! $COMPOSE exec -T db pg_restore --list < "$FILE.tmp" > /dev/null; then
  rm -f "$FILE.tmp"
  echo "Дамп не читается, бэкап отброшен" >&2
  exit 1
fi
mv "$FILE.tmp" "$FILE"
echo "Бэкап создан: $FILE ($(wc -c < "$FILE") байт)"

# Удаляем старые копии.
find "$DIR" -maxdepth 1 -name 'altyn-*.dump' -mtime +"$KEEP_DAYS" -print -delete

# Копия на другой сервер: без неё потеря диска VPS означает потерю всего.
if [ -n "${BACKUP_REMOTE:-}" ]; then
  rsync -a --chmod=F600 "$FILE" "$BACKUP_REMOTE"
  echo "Скопировано на $BACKUP_REMOTE"
fi
