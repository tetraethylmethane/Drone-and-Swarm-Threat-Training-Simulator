#!/usr/bin/env bash
# Synchronised class start with and without pre-generated first attempts (backlog B-17;
# docs/testing/load-resilience-report.md 5.10). Runs alternate between the two settings, so that
# drift in the host (the cause of large run-to-run variation on this laptop) affects both alike.
#
#   bash tests/load/class_start.sh [trainees, default 30] [pairs, default 3]
#
# Each run restarts the API (empty cache), assigns one exercise to every trainee, waits PREP_S
# seconds (default 30), starts all trainees at once and runs one 90 s exercise each.
# Uses the isolated load-test stack (deploy/loadtest); set LT_API_IMAGE / LT_WEB_IMAGE to test a
# candidate build.
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/../.."
VUS="${1:-30}"; PAIRS="${2:-3}"
ROOT="$(pwd)"; [ -n "${WINDIR:-}" ] && ROOT="$(cygpath -m "$ROOT")"
ENVF=deploy/loadtest/loadtest.env
DC=(docker compose -p drikrload -f deploy/loadtest/docker-compose.yml --env-file "$ENVF")
OUT="tests/load/results/$(date -u +%Y-%m-%d)"; mkdir -p "$OUT"
set -a; . "$ENVF"; set +a
export LT_MAX_ACTIVE_SESSIONS=0

run() { # $1 = cache MiB (0 = pre-generation off), $2 = label
  export LT_TIMELINE_CACHE_MB="$1"
  "${DC[@]}" up -d --no-build >/dev/null
  "${DC[@]}" restart api >/dev/null
  for _ in $(seq 1 90); do docker inspect -f '{{.State.Health.Status}}' drikrload-api-1 | grep -q healthy && break; sleep 2; done
  "${DC[@]}" exec -T api drikr-api seed-demo >/dev/null
  "${DC[@]}" exec -T -e LT_USERS=100 api python - <tests/load/create_users.py >/dev/null
  timeout 30 docker version >/dev/null || { echo "$2: docker unresponsive before the run" >&2; return 1; }
  local start; start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  local f="$OUT/$2-resources.csv"; echo "ts,container,cpu_pct,mem_mib" >"$f"
  ( while true; do
      docker stats --no-stream --format '{{.Name}},{{.CPUPerc}},{{.MemUsage}}' drikrload-api-1 drikrload-db-1 2>/dev/null |
        sed -E 's/%//; s/ *\/.*//; s/MiB//; s/GiB/*1024/' | while IFS=, read -r n c m; do echo "$(date -u +%H:%M:%S),$n,$c,$m" >>"$f"; done
      sleep 2
    done ) & local sp=$!
  docker run --rm --network drikrload_frontend -v "$ROOT/tests/load/k6:/scripts:ro" -v "$ROOT/$OUT:/out" \
    -e BASE_URL=http://web:8080/api/v1 -e LT_USER_PASSWORD -e VUS="$VUS" -e PREP_S="${PREP_S:-30}" \
    grafana/k6:2.3.0 run --quiet --summary-export "/out/$2-k6-summary.json" /scripts/class_start.js >"$OUT/$2-k6-stdout.txt" 2>&1 || true
  kill "$sp" 2>/dev/null || true
  timeout 30 docker version >/dev/null || echo "$2: docker unresponsive after the run" >&2
  # This run's sessions, and any server errors in the API log.
  "${DC[@]}" logs --no-color api 2>/dev/null | grep -c "Traceback" >"$OUT/$2-api-tracebacks.txt" || true
  docker exec -i drikrload-db-1 psql -U drikr -d drikr -A -F, -P footer=off >"$OUT/$2-sessions.csv" <<SQL
SELECT count(*) AS sessions,
       count(*) FILTER (WHERE status = 'completed') AS completed,
       count(*) FILTER (WHERE status IN ('created', 'running', 'paused')) AS open,
       (SELECT count(*) FROM score_results r JOIN training_sessions t ON t.id = r.session_id
         WHERE t.created_at >= '$start' AND r.result->>'status' = 'scored') AS scored,
       (SELECT count(DISTINCT e.session_id) FROM session_events e JOIN training_sessions t ON t.id = e.session_id
         WHERE t.created_at >= '$start' AND e.type = 'session_paused') AS sessions_paused
FROM training_sessions WHERE created_at >= '$start';
SQL
  local n; n=$(tail -1 "$OUT/$2-sessions.csv" | cut -d, -f1)
  if [ "$n" != "$VUS" ]; then
    echo "INVALID: $2 created $n of $VUS sessions (see $2-k6-stdout.txt); stopping" >&2
    exit 1
  fi
  echo "done: $2 (cache ${1} MiB, $(tail -1 "$OUT/$2-sessions.csv"))"
}

for i in $(seq 1 "$PAIRS"); do
  run 0  "class-${VUS}-off-$i"
  run 64 "class-${VUS}-on-$i"
done
docker exec drikrload-api-1 drikr-api reproducibility-report --limit "$((VUS * PAIRS * 2))" </dev/null >"$OUT/class-${VUS}-reproducibility.json" 2>"$OUT/class-${VUS}-reproducibility.err" || true
docker exec drikrload-api-1 drikr-api verify-audit </dev/null >"$OUT/class-${VUS}-audit.json" 2>&1 || true
