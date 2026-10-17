#!/usr/bin/env bash
# Load and resilience tests against the isolated stack in deploy/loadtest (see tests/load/README.md).
#
#   bash tests/load/run.sh load        [levels, default "10 30 60 100"] [duration, default 5m]
#   bash tests/load/run.sh resilience  [VUs, default 30]
#   bash tests/load/run.sh down        # stop and delete the load-test stack and its volume
#
# Raw outputs go to tests/load/results/<UTC date>/: k6 summaries, resource samples (CSV), API health
# probes (CSV) and reproducibility reports (JSON).
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/../.."
ROOT="$(pwd)"
[ -n "${WINDIR:-}" ] && ROOT="$(cygpath -m "$ROOT")"
ENVF=deploy/loadtest/loadtest.env
DC=(docker compose -p drikrload -f deploy/loadtest/docker-compose.yml --env-file "$ENVF")
K6_IMAGE=grafana/k6:2.3.0
OUT="tests/load/results/$(date -u +%Y-%m-%d)"
mkdir -p "$OUT"

gen() { "${PYTHON:-.venv/Scripts/python}" -c "import secrets; print(secrets.token_urlsafe(24))"; }

up() {
  if [ ! -f "$ENVF" ]; then
    umask 077
    {
      echo "LT_DB_PASSWORD=$(gen)"
      echo "LT_APP_PASSWORD=$(gen)"
      echo "LT_SECRET_KEY=$(gen)$(gen)"
      echo "LT_USER_PASSWORD=Lt-$(gen)-9a"
    } >"$ENVF"
  fi
  "${DC[@]}" up -d >/dev/null
  for _ in $(seq 1 90); do
    "${DC[@]}" ps api --format '{{.Status}}' | grep -q '(healthy)' && break
    sleep 2
  done
  "${DC[@]}" exec -T api drikr-api seed-demo >/dev/null
  "${DC[@]}" exec -T -e LT_USERS=100 api python - <tests/load/create_users.py
}

sample() { # $1 = label; runs until killed
  local f="$OUT/$1-resources.csv"
  echo "ts,container,cpu_pct,mem_mib" >"$f"
  local cf="$OUT/$1-db-connections.csv"
  echo "ts,role,state,connections" >"$cf"
  while true; do
    ts=$(date -u +%H:%M:%S)
    docker stats --no-stream --format '{{.Name}},{{.CPUPerc}},{{.MemUsage}}' drikrload-api-1 drikrload-db-1 drikrload-web-1 2>/dev/null |
      sed -E 's/%//; s/ *\/.*//; s/MiB//; s/GiB/*1024/' | while IFS=, read -r n c m; do echo "$ts,$n,$c,$m" >>"$f"; done
    "${DC[@]}" exec -T db psql -U drikr -d drikr -At -F, -c \
      "SELECT usename, coalesce(state,'none'), count(*) FROM pg_stat_activity WHERE datname='drikr' AND usename IS NOT NULL GROUP BY 1,2" 2>/dev/null |
      while read -r line; do echo "$ts,$line" >>"$cf"; done
    sleep 2
  done
}

k6run() { # $1 label, $2 VUs, $3 duration
  set -a; . "$ENVF"; set +a
  docker run --rm --network drikrload_frontend -v "$ROOT/tests/load/k6:/scripts:ro" -v "$ROOT/$OUT:/out" \
    -e BASE_URL=http://web:8080/api/v1 -e LT_USER_PASSWORD -e VUS="$2" -e DURATION="$3" -e EXERCISE_S="${EXERCISE_S:-90}" \
    "$K6_IMAGE" run --quiet --summary-export "/out/$1-k6-summary.json" /scripts/exercise.js >"$OUT/$1-k6-stdout.txt" 2>&1 || true
}

stats() { # $1 label, $2 run start (UTC, ISO 8601): records the run's sessions for criteria A3 and A6
  local q="SELECT '$2'::timestamptz AS since"
  docker exec -i drikrload-db-1 psql -U drikr -d drikr -A -F, -P footer=off >"$OUT/$1-sessions.csv" <<SQL
WITH run AS (SELECT id, status FROM training_sessions WHERE created_at >= ('$2')::timestamptz),
pauses AS (
  SELECT e.session_id, count(*) FILTER (WHERE e.payload->>'reason' = 'connection_lost') AS lost
  FROM session_events e JOIN run ON run.id = e.session_id WHERE e.type = 'session_paused' GROUP BY 1),
cls AS (
  SELECT e.session_id, count(DISTINCT tid) AS n
  FROM session_events e JOIN run ON run.id = e.session_id, jsonb_array_elements_text(e.payload->'track_ids') tid
  WHERE e.type = 'classification_submitted' GROUP BY 1)
SELECT
  (SELECT count(*) FROM run) AS sessions,
  (SELECT count(*) FROM run WHERE status = 'completed') AS completed,
  (SELECT count(*) FROM run WHERE status IN ('created', 'running', 'paused')) AS open,
  (SELECT count(*) FROM pauses WHERE lost > 0) AS sessions_paused_connection_lost,
  (SELECT coalesce(sum(lost), 0) FROM pauses) AS connection_lost_pauses,
  (SELECT count(*) FROM score_results r JOIN run ON run.id = r.session_id WHERE r.result->>'status' = 'scored') AS scored,
  (SELECT count(*) FROM score_results r JOIN run ON run.id = r.session_id LEFT JOIN cls ON cls.session_id = r.session_id
     WHERE r.result->>'status' = 'scored'
       AND coalesce(cls.n, 0) <> (r.result->'counts'->>'classified_tracks')::int + (r.result->'counts'->>'ignored_decisions')::int)
    AS stored_vs_scored_mismatches;
SQL
  docker exec drikrload-api-1 drikr-api verify-audit </dev/null >"$OUT/$1-audit.json" 2>&1 || true
}

repro() { # $1 label, $2 limit
  # No stdin and stderr kept: inside the run, `compose exec` intermittently produced an empty file.
  docker exec drikrload-api-1 drikr-api reproducibility-report --limit "$2" </dev/null     >"$OUT/$1-reproducibility.json" 2>"$OUT/$1-reproducibility.err" || echo "reproducibility report failed: $?" >>"$OUT/$1-reproducibility.err"
}

case "${1:-load}" in
  load)
    up
    levels="${2:-10 30 60 100}"
    for vus in $levels; do
      label="load-${vus}vu${LABEL_SUFFIX:-}"
      if [ -n "${FRESH_API:-}" ]; then # restart the API so memory starts from a clean process (criterion A7)
        "${DC[@]}" restart api >/dev/null
        for _ in $(seq 1 60); do "${DC[@]}" ps api --format '{{.Status}}' | grep -q '(healthy)' && break; sleep 2; done
      fi
      start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
      sample "$label" & sp=$!
      k6run "$label" "$vus" "${3:-5m}"
      kill "$sp" 2>/dev/null || true
      stats "$label" "$start"
      repro "$label" 500
      echo "done: $label"
    done
    ;;
  resilience)
    up
    vus="${2:-30}"
    label="resilience-${vus}vu${LABEL_SUFFIX:-}"
    start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    sample "$label" & sp=$!
    probe="$OUT/$label-health.csv"; echo "ts,status_code" >"$probe"
    ( while true; do
        c=$(docker run --rm --network drikrload_frontend curlimages/curl:8.11.1 -s -o /dev/null -w '%{http_code}' -m 2 http://web:8080/api/v1/health/ready || echo 000)
        echo "$(date -u +%H:%M:%S),$c" >>"$probe"; sleep 1
      done ) & pp=$!
    k6run "$label" "$vus" 6m & kp=$!
    echo "$(date -u +%H:%M:%S) start" >"$OUT/$label-timeline.txt"
    sleep 90;  echo "$(date -u +%H:%M:%S) api: restart (kill)" >>"$OUT/$label-timeline.txt"; docker kill drikrload-api-1 >/dev/null; "${DC[@]}" up -d api >/dev/null
    sleep 120; echo "$(date -u +%H:%M:%S) db: stop for 30 s" >>"$OUT/$label-timeline.txt"; docker stop drikrload-db-1 >/dev/null
    sleep 30;  echo "$(date -u +%H:%M:%S) db: start" >>"$OUT/$label-timeline.txt"; docker start drikrload-db-1 >/dev/null
    wait "$kp" || true
    echo "$(date -u +%H:%M:%S) k6 finished" >>"$OUT/$label-timeline.txt"
    kill "$sp" "$pp" 2>/dev/null || true
    sleep 20 # past the 15 s grace, so the sweeper has paused any session whose client stopped
    stats "$label" "$start"
    repro "$label" 500
    "${DC[@]}" exec -T db psql -U drikr -d drikr -At -c \
      "SELECT status, count(*) FROM training_sessions GROUP BY status ORDER BY 1" >"$OUT/$label-session-states.txt"
    "${DC[@]}" exec -T api drikr-api verify-audit >"$OUT/$label-audit.json" || true
    ;;
  down)
    "${DC[@]}" down -v
    ;;
esac
