#!/usr/bin/env bash
# Memory check for criterion A7 (docs/testing/load-resilience-report.md): restart the API, then run
# the same 30-trainee load RUNS times back to back, recording each process's resident memory inside
# the API container before, after each run, and after 60 s idle. A leak keeps growing from run to
# run; allocator retention of the peak working set levels off.
#
#   bash tests/load/memory.sh [runs, default 3] [vus, default 30] [duration, default 5m]
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/../.."
RUNS="${1:-3}"; VUS="${2:-30}"; DUR="${3:-5m}"
OUT="tests/load/results/$(date -u +%Y-%m-%d)"; mkdir -p "$OUT"
F="$OUT/memory-${VUS}vu-rss.csv"
echo "ts,phase,pid,process,rss_kib" >"$F"
snap() { # $1 phase
  docker exec drikrload-api-1 sh -c 'for p in $(ls /proc | grep -E "^[0-9]+$"); do
      [ -r /proc/$p/status ] || continue
      c=$(tr "\0" " " </proc/$p/cmdline | cut -c1-40); r=$(awk "/VmRSS/{print \$2}" /proc/$p/status)
      case "$c" in *python*) echo "$p,$c,$r";; esac
    done' | while IFS= read -r line; do echo "$(date -u +%H:%M:%S),$1,$line" >>"$F"; done
}
docker compose -p drikrload -f deploy/loadtest/docker-compose.yml --env-file deploy/loadtest/loadtest.env restart api >/dev/null
for _ in $(seq 1 60); do docker inspect -f '{{.State.Health.Status}}' drikrload-api-1 | grep -q healthy && break; sleep 2; done
snap fresh
for i in $(seq 1 "$RUNS"); do
  LABEL_SUFFIX="-mem-run$i" bash tests/load/run.sh load "$VUS" "$DUR"
  snap "after-run$i"
  sleep 60
  snap "idle-run$i"
done
echo "memory samples: $F"
