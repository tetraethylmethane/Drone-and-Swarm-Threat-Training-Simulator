#!/usr/bin/env bash
# Soak test for backlog B-03 (docs/testing/load-resilience-report.md): one long run at the design
# load with the operational settings, sampling every few minutes:
#   - resident memory of each Python process in the API container (a leak keeps growing; allocator
#     retention levels off),
#   - database connections of the API role,
#   - whether the Docker daemon still answers (two runs on 2026-10-16 stalled with it; any gap in
#     the samples or a "docker_unresponsive" row makes the run invalid).
#
#   bash tests/load/soak.sh [hours, default 8] [vus, default 30] [sample interval s, default 300]
#
# Uses the isolated load-test stack (deploy/loadtest); never the deployment.
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/../.."
HOURS="${1:-8}"; VUS="${2:-30}"; EVERY="${3:-300}"
ROOT="$(pwd)"; [ -n "${WINDIR:-}" ] && ROOT="$(cygpath -m "$ROOT")"
ENVF=deploy/loadtest/loadtest.env
DC=(docker compose -p drikrload -f deploy/loadtest/docker-compose.yml --env-file "$ENVF")
OUT="tests/load/results/$(date -u +%Y-%m-%d)"; mkdir -p "$OUT"
LABEL="soak-${VUS}vu-${HOURS}h"
F="$OUT/$LABEL-rss.csv"; C="$OUT/$LABEL-db-connections.csv"; T="$OUT/$LABEL-timeline.txt"
echo "ts,pid,process,rss_kib" >"$F"; echo "ts,connections" >"$C"
log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" >>"$T"; }

export LT_MAX_ACTIVE_SESSIONS="${LT_MAX_ACTIVE_SESSIONS:-$VUS}"
"${DC[@]}" up -d >/dev/null
"${DC[@]}" restart api >/dev/null
for _ in $(seq 1 90); do docker inspect -f '{{.State.Health.Status}}' drikrload-api-1 | grep -q healthy && break; sleep 2; done
log "start: ${VUS} VU for ${HOURS} h; max_active_sessions=${LT_MAX_ACTIVE_SESSIONS}; image $(docker inspect -f '{{.Image}}' drikrload-api-1 | cut -c8-19)"
start=$(date -u +%Y-%m-%dT%H:%M:%SZ)

snap() {
  local ts; ts=$(date -u +%H:%M:%S)
  if ! timeout 30 docker version >/dev/null 2>&1; then log "docker_unresponsive"; return; fi
  timeout 60 docker exec drikrload-api-1 sh -c 'for p in $(ls /proc | grep -E "^[0-9]+$"); do
      [ -r /proc/$p/status ] || continue
      c=$(tr "\0" " " </proc/$p/cmdline | cut -c1-60); r=$(awk "/VmRSS/{print \$2}" /proc/$p/status)
      case "$c" in *python3*) echo "$p,$c,$r";; esac
    done' 2>/dev/null | grep -av "sh -c" | while IFS= read -r line; do echo "$ts,$line" >>"$F"; done || log "rss_sample_failed"
  n=$(timeout 30 docker exec drikrload-db-1 psql -U drikr -d drikr -At -c \
      "SELECT count(*) FROM pg_stat_activity WHERE usename = 'drikr_app'" 2>/dev/null || echo "")
  echo "$ts,$n" >>"$C"
}

set -a; . "$ENVF"; set +a
docker rm -f drikr-soak-k6 >/dev/null 2>&1 || true
docker run -d --name drikr-soak-k6 --network drikrload_frontend -v "$ROOT/tests/load/k6:/scripts:ro" -v "$ROOT/$OUT:/out" \
  -e BASE_URL=http://web:8080/api/v1 -e LT_USER_PASSWORD -e VUS="$VUS" -e DURATION="${HOURS}h" -e EXERCISE_S=90 \
  grafana/k6:2.3.0 run --quiet --summary-export "/out/$LABEL-k6-summary.json" /scripts/exercise.js >/dev/null
snap
while [ "$(docker inspect -f '{{.State.Running}}' drikr-soak-k6 2>/dev/null || echo false)" = "true" ]; do
  sleep "$EVERY"
  snap
done
docker logs drikr-soak-k6 >"$OUT/$LABEL-k6-stdout.txt" 2>&1 || true
docker rm drikr-soak-k6 >/dev/null 2>&1 || true
log "k6 finished"
sleep 60; snap; log "idle sample taken"

# Records after the run: sessions of this run, reproducibility of the whole database, audit chain.
docker exec -i drikrload-db-1 psql -U drikr -d drikr -A -F, -P footer=off >"$OUT/$LABEL-sessions.csv" <<SQL
SELECT count(*) AS sessions,
       count(*) FILTER (WHERE status = 'completed') AS completed,
       count(*) FILTER (WHERE status IN ('created', 'running', 'paused')) AS open,
       (SELECT count(*) FROM score_results r JOIN training_sessions t ON t.id = r.session_id
         WHERE t.created_at >= '$start') AS scored,
       (SELECT count(DISTINCT e.session_id) FROM session_events e JOIN training_sessions t ON t.id = e.session_id
         WHERE t.created_at >= '$start' AND e.type = 'session_paused' AND e.payload->>'reason' = 'connection_lost')
         AS sessions_paused_connection_lost
FROM training_sessions WHERE created_at >= '$start';
SQL
docker exec drikrload-api-1 drikr-api reproducibility-report --limit 100000 </dev/null >"$OUT/$LABEL-reproducibility.json" 2>"$OUT/$LABEL-reproducibility.err" || true
docker exec drikrload-api-1 drikr-api verify-audit </dev/null >"$OUT/$LABEL-audit.json" 2>&1 || true
log "done"
