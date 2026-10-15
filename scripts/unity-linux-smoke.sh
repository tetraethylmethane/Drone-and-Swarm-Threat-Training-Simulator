#!/usr/bin/env bash
# Run the Linux Unity player's smoke test headless in an Ubuntu container (Xvfb, software OpenGL)
# against the running Docker Compose stack over HTTPS.
#
#   DRIKR_SMOKE_PASSWORD=<demo password> bash scripts/unity-linux-smoke.sh
#
# Needs: Builds/Linux from BuildScript.BuildLinux, the TLS stack (docker-compose.tls.yml) with a
# server certificate that names "web" (scripts/generate-tls-cert.sh --host web ...).
# Writes the screenshot to apps/simulator/DrikrUnityClient/Builds/linux-smoke.png. Exit code 0 = pass.
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
: "${DRIKR_SMOKE_PASSWORD:?set DRIKR_SMOKE_PASSWORD}"
ROOT="$(pwd)"
[ -n "${WINDIR:-}" ] && ROOT="$(cygpath -m "$ROOT")"
BUILD="$ROOT/apps/simulator/DrikrUnityClient/Builds"
NETWORK="${DRIKR_NETWORK:-drikr_frontend}"

docker run --rm --network "$NETWORK" \
  -e DRIKR_SMOKE_USER="${DRIKR_SMOKE_USER:-trainee2}" -e DRIKR_SMOKE_PASSWORD \
  -v "$BUILD/Linux:/player:ro" -v "$ROOT/deploy/tls/ca.crt:/tls/ca.crt:ro" -v "$BUILD:/out" \
  ubuntu:24.04 bash -c '
    set -e
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq >/dev/null
    apt-get install -y -qq --no-install-recommends xvfb xauth libgl1 libglx-mesa0 libgl1-mesa-dri \
      libxcursor1 libxrandr2 libxi6 libxinerama1 libxkbcommon0 libgtk-3-0 ca-certificates >/dev/null
    cp -r /player /tmp/player && chmod +x /tmp/player/DrikrTrainingSimulator.x86_64
    xvfb-run -a -s "-screen 0 1440x900x24" /tmp/player/DrikrTrainingSimulator.x86_64 \
      -force-glcore -screen-fullscreen 0 -screen-width 1440 -screen-height 900 \
      -drikrApi https://web:8443/api/v1 -drikrCa /tls/ca.crt -drikrSmoke /out/linux-smoke.png -logFile /tmp/player.log
    code=$?
    grep -E "DRIKR_SMOKE|Exception" /tmp/player.log | head -20
    exit $code'
