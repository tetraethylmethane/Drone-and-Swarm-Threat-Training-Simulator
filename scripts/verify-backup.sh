#!/usr/bin/env bash
# Verify a backup WITHOUT touching the live database: restore it into a scratch
# database, then check the schema revision, record counts and the audit hash chain.
#
#   scripts/verify-backup.sh backups/drikr-<stamp>.dump
set -euo pipefail
cd "$(dirname "$0")/.."
FILE="${1:?usage: verify-backup.sh <dump file>}"
set -a; . ./.env; set +a
SCRATCH="drikr_restore_check"
PY="$(command -v python3 >/dev/null 2>&1 && python3 -c "" 2>/dev/null && echo python3 || echo python)"

( cd "$(dirname "$FILE")" && sha256sum -c "$(basename "$FILE").sha256" )

docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS $SCRATCH" -c "CREATE DATABASE $SCRATCH"
docker compose exec -T db pg_restore -U "$POSTGRES_USER" -d "$SCRATCH" --no-owner --no-privileges --exit-on-error < "$FILE"

echo "--- restored contents"
docker compose exec -T db psql -U "$POSTGRES_USER" -d "$SCRATCH" -At -c \
  "SELECT 'schema_revision=' || version_num FROM alembic_version
   UNION ALL SELECT 'users=' || count(*) FROM users
   UNION ALL SELECT 'scenarios=' || count(*) FROM scenarios
   UNION ALL SELECT 'sessions=' || count(*) FROM training_sessions
   UNION ALL SELECT 'score_results=' || count(*) FROM score_results
   UNION ALL SELECT 'audit_events=' || count(*) FROM audit_events"

echo "--- audit chain in restored copy"
SCRATCH_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${SCRATCH}"
RESULT="$(docker compose exec -T -e DRIKR_DATABASE_URL="$SCRATCH_URL" api drikr-api verify-audit)"
echo "$RESULT"
if [ -f "$FILE.audit.json" ]; then
  WANT="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("head_hash",""))' "$FILE.audit.json" 2>/dev/null || true)"
  GOT="$(echo "$RESULT" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("head_hash",""))' 2>/dev/null || true)"
  if [ -n "$WANT" ] && [ "$WANT" != "$GOT" ]; then
    echo "audit head hash differs from the value recorded at backup time" >&2
    exit 1
  fi
fi

docker compose exec -T db psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE $SCRATCH" > /dev/null
echo "backup verified: $FILE"
