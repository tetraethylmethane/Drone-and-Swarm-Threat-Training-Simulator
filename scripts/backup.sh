#!/usr/bin/env bash
# Create a consistent PostgreSQL backup of the Docker Compose deployment.
#
#   scripts/backup.sh [output_dir]
#
# Produces <output_dir>/drikr-<UTC timestamp>.dump (pg_dump custom format), a .sha256
# checksum and a .audit.json file recording the audit-chain head hash at backup time.
# Store the audit head hash separately from the backup: it lets you detect a restored
# database whose audit history was rewritten (docs/security/security-controls.md).
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="${1:-backups}"
mkdir -p "$OUT"
# DRIKR_ENV_FILE selects another stack's settings (default: the deployment's .env).
set -a; . "${DRIKR_ENV_FILE:-./.env}"; set +a
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="$OUT/drikr-$STAMP.dump"

docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-privileges > "$FILE"
if [ ! -s "$FILE" ]; then
  echo "backup failed: empty dump" >&2
  rm -f "$FILE"
  exit 1
fi
( cd "$OUT" && sha256sum "$(basename "$FILE")" > "$(basename "$FILE").sha256" )
docker compose exec -T api drikr-api verify-audit > "$FILE.audit.json" || {
  echo "warning: audit chain did not verify at backup time; see $FILE.audit.json" >&2
}
echo "backup written: $FILE"
echo "checksum:       $FILE.sha256"
echo "audit head:     $FILE.audit.json"
