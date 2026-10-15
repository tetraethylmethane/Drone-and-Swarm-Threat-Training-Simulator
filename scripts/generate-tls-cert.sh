#!/usr/bin/env bash
# Create a private certificate authority and a server certificate for an offline training network.
#
#   bash scripts/generate-tls-cert.sh [--host NAME]... [--ip ADDRESS]... [--out DIR] [--days N]
#
# Defaults: --host localhost --ip 127.0.0.1 --out deploy/tls --days 397. The CA is created once and
# reused, so re-running the script only re-issues the server certificate. Distribute ca.crt to the
# training workstations (and to the Unity client with -drikrCa) and keep ca.key offline.
# Keys are RSA-3072: the Unity client's Mono runtime cannot validate ECDSA certificate chains.
set -euo pipefail
export MSYS_NO_PATHCONV=1 # Git Bash on Windows would otherwise rewrite "/CN=..." as a path

cd "$(dirname "$0")/.."
OUT=deploy/tls
DAYS=397
HOSTS=()
IPS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOSTS+=("$2"); shift 2 ;;
    --ip) IPS+=("$2"); shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --days) DAYS="$2"; shift 2 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ ${#HOSTS[@]} -gt 0 ] || HOSTS=(localhost)
[ ${#IPS[@]} -gt 0 ] || IPS=(127.0.0.1)
command -v openssl >/dev/null || { echo "openssl is required" >&2; exit 1; }
# A stale OPENSSL_CONF (some Windows installers set one) makes every openssl command fail.
if [ -n "${OPENSSL_CONF:-}" ] && [ ! -f "$OPENSSL_CONF" ]; then unset OPENSSL_CONF; fi

mkdir -p "$OUT"
umask 077
CN="${HOSTS[0]}"

if [ ! -f "$OUT/ca.crt" ] || [ ! -f "$OUT/ca.key" ]; then
  echo "Creating training-network CA in $OUT"
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$OUT/ca.key"
  openssl req -x509 -new -key "$OUT/ca.key" -sha256 -days 3650 \
    -subj "/O=Drikr Systems training network/CN=Drikr training CA" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -out "$OUT/ca.crt"
fi

SAN=""
for h in "${HOSTS[@]}"; do SAN="${SAN:+$SAN,}DNS:$h"; done
for ip in "${IPS[@]}"; do SAN="${SAN:+$SAN,}IP:$ip"; done

EXT="$OUT/server.ext" # inside OUT: native openssl on Windows cannot see MSYS /tmp paths
trap 'rm -f "$EXT" "$OUT/server.csr"' EXIT
cat >"$EXT" <<EOF
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=$SAN
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid
EOF

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$OUT/server.key"
openssl req -new -key "$OUT/server.key" -subj "/O=Drikr Systems training network/CN=$CN" -out "$OUT/server.csr"
openssl x509 -req -in "$OUT/server.csr" -CA "$OUT/ca.crt" -CAkey "$OUT/ca.key" -CAcreateserial \
  -days "$DAYS" -sha256 -extfile "$EXT" -out "$OUT/server.crt"
chmod 644 "$OUT/ca.crt" "$OUT/server.crt"

openssl verify -CAfile "$OUT/ca.crt" "$OUT/server.crt"
echo "Server certificate for: $SAN (valid $DAYS days)"
echo "SHA-256 fingerprint of the CA:"
openssl x509 -in "$OUT/ca.crt" -noout -fingerprint -sha256
cat <<EOF

Next:
  - Linux hosts: the web container runs as uid 101; allow it to read the key:
      sudo chown 101 $OUT/server.key
  - docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d
  - Install $OUT/ca.crt as a trusted root on each training workstation.
  - Move $OUT/ca.key to offline storage; it is only needed to issue the next certificate.
EOF
