#!/usr/bin/env bash
# Start the API against the project-local development cluster (scripts/local-postgres.ps1).
# Development-only credentials; never use these values in production.
set -euo pipefail
cd "$(dirname "$0")/.."
export DRIKR_ENVIRONMENT=development
export DRIKR_DATABASE_URL="postgresql+psycopg://drikr:drikr_dev_only@127.0.0.1:55432/drikr"
export DRIKR_SECRET_KEY="dev_only-local-secret-key-please-change-0123456789"
export DRIKR_COOKIE_SECURE=false
export DRIKR_LOGIN_RATE_LIMIT_PER_MINUTE=${DRIKR_LOGIN_RATE_LIMIT_PER_MINUTE:-200}
PY=.venv/Scripts
[ -d "$PY" ] || PY=.venv/bin
"$PY/drikr-api" migrate
exec "$PY/uvicorn" --factory drikr_api.main:app_factory --host 127.0.0.1 --port 8000
