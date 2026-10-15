#!/usr/bin/env bash
# Restore a backup over the live database. DESTRUCTIVE: replaces all current data.
#
#   scripts/restore.sh backups/drikr-<stamp>.dump --yes
#
# Procedure: checksum -> stop API -> recreate database -> pg_restore -> start API
# (which applies any newer migrations) -> verify audit chain and readiness.
set -euo pipefail
cd "$(dirname "$0")/.."
FILE="${1:?usage: restore.sh <dump file> --yes}"
[ "${2:-}" = "--yes" ] || { echo "refusing to restore without --yes (this replaces all current data)" >&2; exit 2; }
set -a; . ./.env; set +a

( cd "$(dirname "$FILE")" && sha256sum -c "$(basename "$FILE").sha256" )

docker compose stop api web
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$POSTGRES_DB' AND pid <> pg_backend_pid()" \
  -c "DROP DATABASE IF EXISTS $POSTGRES_DB" -c "CREATE DATABASE $POSTGRES_DB"
docker compose exec -T db pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges --exit-on-error < "$FILE"
docker compose start api web

for _ in $(seq 1 30); do
  if docker compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready', timeout=2)" 2>/dev/null; then
    break
  fi
  sleep 2
done
docker compose exec -T api drikr-api verify-audit
echo "restore complete: $FILE"
