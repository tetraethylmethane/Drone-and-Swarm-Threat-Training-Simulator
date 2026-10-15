# Offline deployment

The application needs **no internet access at runtime**: no CDNs, no external APIs, no telemetry,
fonts bundled. Internet access is needed only once, on a staging machine, to build or download the
container images.

## Requirements

| Item | Minimum tested |
|---|---|
| Docker Engine with Compose v2 | Docker 27.3 (Docker Desktop on Windows 11) |
| CPU / memory for the stack | 2 cores, 4 GB RAM available to Docker |
| Disk | ~1.5 GB for images; database grows by roughly 1–4 MB per completed session (event logs) |
| Browser | Current Chromium-based browser or Firefox with WebGL (the plan view works without WebGL) |

## 1. Prepare images on a connected staging machine

```bash
git clone <repository> drikr && cd drikr
docker compose build
docker pull postgres:17.2-alpine3.20
docker save -o drikr-images-1.0.0.tar drikr-api:1.0.0 drikr-web:1.0.0 postgres:17.2-alpine3.20
sha256sum drikr-images-1.0.0.tar > drikr-images-1.0.0.tar.sha256
```

Transfer the `.tar`, its checksum and a copy of the repository (or at least `docker-compose.yml`,
`.env.example`, `scripts/`) to the offline host using approved removable media.

## 2. Install on the offline host

```bash
sha256sum -c drikr-images-1.0.0.tar.sha256
docker load -i drikr-images-1.0.0.tar
cp .env.example .env
```

Edit `.env` and replace every value marked CHANGE:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # POSTGRES_PASSWORD (also in DRIKR_DATABASE_URL)
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # DRIKR_SECRET_KEY
```

Start without rebuilding (images are already loaded):

```bash
docker compose up -d --no-build
docker compose ps                       # db, api and web should become "healthy"
```

The API applies database migrations automatically at start (idempotent).

## 3. Create the first administrator

```bash
docker compose exec api drikr-api create-admin --username admin --display-name "Training Administrator"
```

Sign in at <http://localhost:8080> (or the HTTPS address from section 4). By default administrators
must use multi-factor authentication, so the first sign-in opens **Account and security** to set up
an authenticator app (any app supporting time-based codes) and to save ten recovery codes. The
administrator then creates instructor and trainee accounts under **Users**; each user must change the
temporary password at first sign-in. Which roles must use MFA is set under **Settings**.

If the only administrator loses both the authenticator and the recovery codes:

```bash
docker compose exec api drikr-api reset-mfa --username admin   # audited; signs the account out
```

### Optional: demonstration content

```bash
docker compose exec api drikr-api seed-demo                    # demo rubric and four demo scenarios only
docker compose exec -e DRIKR_DEMO_PASSWORD='<policy-compliant>' api drikr-api seed-demo --with-demo-users
```

Demo content is flagged `is_demo` and shown as *Demonstration* in the interface. Do not create demo
users in a production installation.

## 4. Network exposure and TLS

By default only `127.0.0.1:8080` is published over plain HTTP. `DRIKR_COOKIE_SECURE=true` requires
HTTPS, which browsers treat `localhost` as satisfying. To serve other machines on a training
network, use the bundled HTTPS configuration:

```bash
# 1. Certificates (once; re-run to renew the server certificate, the CA is reused)
bash scripts/generate-tls-cert.sh --host drikr-training.local --ip 192.168.10.20
#    Linux hosts: let the unprivileged web container read the key
sudo chown 101 deploy/tls/server.key

# 2. Publish HTTPS (and HTTP, which now only redirects) on the training-network interface
#    in .env:  DRIKR_WEB_BIND=192.168.10.20   DRIKR_HTTPS_PORT=8443
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --no-build

# 3. Check from a workstation that has the CA certificate
curl --cacert deploy/tls/ca.crt https://drikr-training.local:8443/healthz
```

* Install `deploy/tls/ca.crt` as a trusted root on each training workstation (and pass it to the
  Unity client with `-drikrCa`). Move `deploy/tls/ca.key` to offline storage.
* To use an organisation-issued certificate instead, put `server.crt` (with the chain) and
  `server.key` in a directory and set `DRIKR_TLS_DIR` to it.
* The HTTPS profile: TLS 1.2 and 1.3, forward-secret AEAD ciphers, HSTS for one year, HTTP
  redirected to HTTPS. Because of HSTS, do not later switch the same host name back to plain HTTP.
* Windows `curl` (Schannel) also tries to check revocation, which a private offline CA cannot
  answer; add `--ssl-no-revoke` there. Browsers do not need this.
* Running plain HTTP on a closed network requires `DRIKR_COOKIE_SECURE=false` and remains a
  documented risk (threat model T15).

## 5. Start, stop and update

```bash
docker compose stop                 # stop, keep data
docker compose start
docker compose down                 # remove containers, keep the pgdata volume
scripts/backup.sh                   # always back up before an update
docker load -i drikr-images-<new>.tar && docker compose up -d --no-build
```

Never run `docker compose down -v` on a live system: it deletes the database volume.

## 6. Health checks and logs

* `docker compose ps` shows container health (the API health check uses `/api/v1/health/ready`,
  which also confirms the migration revision).
* `docker compose logs api` emits JSON lines (request id, path, status, duration); no secrets or
  request bodies.
* **Administration → System health** shows versions, database latency and size, record counts,
  audit-chain status and confirms *no external runtime dependencies* and *no telemetry*.

## 7. Development mode without Docker (Windows)

```powershell
./scripts/local-postgres.ps1 init ; ./scripts/local-postgres.ps1 start   # isolated cluster on 127.0.0.1:55432
py -3.12 -m venv .venv
.venv\Scripts\pip install -e packages/contracts -e packages/simcore -e packages/scoring -e "apps/api[dev]"
bash scripts/dev-api.sh                                                  # API on 127.0.0.1:8000 (dev-only credentials)
cd apps/web ; npm ci ; npm run dev                                       # UI on http://127.0.0.1:5173 (Node >= 22.22)
```

## Verification record

On 2026-10-14 the stack was built and started with `docker compose up -d --build` on Windows 11 /
Docker 27.3.1 and exercised as described in `docs/SPRINT_STATUS.md` (Sprint 7–8 results). Offline
operation was verified as recorded there; repeat the check on the target hardware before go-live.

On 2026-10-15 the HTTPS configuration was verified on the same machine with a certificate from
`scripts/generate-tls-cert.sh`: HTTP redirected to HTTPS; TLS 1.1 refused; TLS 1.2
(ECDHE-RSA/AES-GCM) and TLS 1.3 negotiated; HSTS and CSP headers present; connections without the
CA, or to a name not in the certificate, rejected; sign-in over HTTPS set `Secure` cookies; the
Unity client completed an exercise over HTTPS with `-drikrCa`. The database was migrated from
revision 0001 to 0002 in place with its existing data.
