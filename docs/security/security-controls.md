# Security controls

This document lists implemented controls and their evidence. It is **not** a certification or
accreditation statement: the product has not been assessed by any certifying body and must not be
described as certified, accredited or military-grade. See *Evidence required for assurance* below.

## Identity and access

| Control | Implementation |
|---|---|
| Password storage | Argon2id (time 3, memory 19 MiB, parallelism 1), automatic rehash on sign-in if parameters change (`security/passwords.py`) |
| Password policy | ≥ 12 characters, three of four character classes, must not contain the username, must differ from the current password; temporary passwords force a change at first sign-in |
| Sessions | 256-bit random tokens; only HMAC-SHA-256 digests stored; absolute TTL (default 8 h) and idle timeout (default 60 min); revoked on sign-out, password change, password reset, role change and deactivation |
| CSRF | Double-submit token (readable cookie + `X-CSRF-Token` header) verified against a stored digest; SameSite=Strict |
| Brute force | Lockout after `DRIKR_LOCKOUT_THRESHOLD` failures for `DRIKR_LOCKOUT_MINUTES`; sliding-window limits per IP and per username |
| Multi-factor authentication | TOTP (RFC 6238, SHA-1, 6 digits, 30 s, ±1 step) with replay protection (the last accepted step is stored). Secrets are sealed with AES-256-GCM under a key derived by HKDF from `DRIKR_SECRET_KEY`, bound to the user id. Ten single-use recovery codes are stored only as HMAC digests. Enrolment needs the current password and a valid code; turning MFA on signs out other sessions. Sign-in becomes two steps: the password returns a challenge token (5 minutes, 5 attempts, single use), not a session. Failed codes count towards account lockout. Administrators choose which roles must use MFA (default: administrators); until a required user enrols, the API refuses everything except account endpoints (`mfa_enrollment_required`). An administrator cannot require MFA for administrators before enabling it on their own account. Resets by administrators (`POST /users/{id}/reset-mfa`) or on the host (`drikr-api reset-mfa`) are audited (`security/totp.py`, `security/secretbox.py`, `services/mfa_service.py`) |
| Authorisation | Role → permission map (`security/rbac.py`) checked on every endpoint; object-level checks for trainee-owned data; last-administrator and self-lockout protection |

## Input and output handling

* Pydantic models with `extra="forbid"` at every request boundary; bounded numeric ranges; regex
  formats for identifiers.
* Scenario definitions validated structurally and by a seeded generation check before storage.
* Structured error bodies that never echo submitted values; unhandled errors return a generic 500.
* CSV exports neutralise formula injection; PDFs are generated server-side from stored data.

## Transport and browser hardening

* TLS for network access (`docker-compose.tls.yml`): TLS 1.2 and 1.3 only, forward-secret AEAD
  ciphers (Mozilla "intermediate"), session tickets off, HSTS (one year), and plain HTTP redirected
  to HTTPS (except the container health check). `scripts/generate-tls-cert.sh` creates a private
  training-network CA and an RSA-3072 server certificate with the host names and addresses given.
  The Unity client can pin that CA (`-drikrCa`); host name checks always apply. An organisation
  CA can be used instead by placing its certificate and key in `DRIKR_TLS_DIR`.
* nginx: CSP (`default-src 'self'`; scripts self only; styles allow inline attributes for Radix and
  ECharts), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, COOP, Permissions-Policy.
* API responses: `Cache-Control: no-store`, `default-src 'none'` CSP.
* No third-party origins at runtime (fonts bundled, no CDN, no analytics or telemetry).

## Data integrity

* Database constraints listed in `docs/architecture/data-model.md`; critical updates in single
  transactions with row locks (`SELECT … FOR UPDATE`) on sessions.
* Immutable, digested scenario and rubric versions; digests on timelines, score inputs and results.
* Database triggers (migration `0004`) make `session_events` append-only (no UPDATE) and
  `score_results` immutable (no UPDATE or DELETE) for every role.
* **Recorded purges (migration `0005`).** Raw event logs are deleted only by the owner-defined
  functions `drikr_purge_session_events` (retention: finished sessions older than a real retention
  run's cutoff, minimum 30 days, database clock) and `drikr_purge_user_event_logs` (anonymisation of
  a deactivated account). Every purge is recorded in the append-only `event_log_purges` table;
  `events_purged_at` can be set once and only with a record; verification accepts a purge only with
  a matching record.
* **Least-privilege database role (Sprint 10).** The API connects as `drikr_app`, which is created
  and re-granted on every start by `drikr-api provision-app-role` using the owner connection
  (`DRIKR_MIGRATION_DATABASE_URL`). It has LOGIN only: no superuser, CREATEDB, CREATEROLE,
  REPLICATION or BYPASSRLS. It has no rights on the schema or `alembic_version`; only INSERT and
  SELECT on `audit_events`, `score_results` and `session_events`; only SELECT on `event_log_purges`;
  and EXECUTE on the two purge functions. **System
  health** shows the connected role and whether it is least-privilege. Setting `DRIKR_DATABASE_URL`
  to the owner URL keeps the old behaviour, and System health then reports it.
* Tamper-evident audit chain (ADR-008) with append-only trigger.
  **Tamper evidence is not tamper prevention.** Copy the `head_hash` from each backup's
  `*.audit.json` (or from `drikr-api verify-audit`) to storage the database administrator cannot
  modify; a later mismatch indicates a rewritten history.

## Personal data and retention

* Administrators set a retention policy (`docs/security/data-retention.md`): raw exercise event
  logs deleted after N days, scores kept; expired sign-in records deleted; deactivated accounts
  anonymised after N days. Preview and dry runs come before deletion; every run is recorded and
  audited. Individual accounts can be anonymised on request (typed confirmation; deactivated
  accounts only; irreversible).
* The audit log is never deleted. It keeps the previous username of anonymised accounts as part
  of the integrity record; this is documented for the data-protection impact assessment.
* The research export (`/reports/study.csv`) identifies participants only by a keyed HMAC code,
  with dates and no times, names or free text.

## Containers and secrets

* Non-root users in both images; read-only root filesystems; all Linux capabilities dropped;
  `no-new-privileges`; database and API on an internal network; only the web port published
  (default bind `127.0.0.1`).
* Rotating `DRIKR_SECRET_KEY` signs every user out **and invalidates all MFA secrets and recovery
  codes**. Their second sign-in step then fails with `mfa_unreadable` until MFA is reset: by another
  administrator in the UI, or on the host with `drikr-api reset-mfa --username <name>` for
  administrators. Plan a key rotation together with those resets.
* All secrets come from `.env` (git-ignored). Startup refuses short or placeholder secrets, non-
  PostgreSQL URLs and, in production, insecure cookies or development credentials.

## Logging

JSON logs to stdout: request id, method, path (no query string), status and duration; security
events go to the audit table. Passwords, tokens, cookies and request bodies are never logged
(tested).

## Availability

* One API process with a 40-thread request pool and a 40-connection database pool; timeline
  generation runs in worker processes (`cpu_workers`, default 2).
* Measured on one development laptop (docs/testing/load-resilience-report.md): 30 concurrent
  trainees met the latency criteria in 4 of 5 runs (little headroom); 60 ran without errors but
  slower. These are not deployment guarantees.
* **Admission control** (`DRIKR_MAX_ACTIVE_SESSIONS`): above the limit, new and resumed exercises are
  refused at once with `503 capacity_reached` and `Retry-After: 30`. Set it **below** the capacity
  measured on the deployment host (load report 5.8).
* An exercise whose client stops polling for 15 s is paused, not lost. After an API restart,
  sessions continue from the database.

## Scanning

| Scan | Tool | Where |
|---|---|---|
| Python dependency vulnerabilities | `pip-audit` | CI `python` job; local results in `SPRINT_STATUS.md` |
| JavaScript dependency vulnerabilities | `npm audit --omit=dev` | CI `web` job |
| Container images | Trivy (HIGH, CRITICAL, fixed only) | CI `containers` job |
| Secrets | gitleaks (`.gitleaks.toml` allow-lists documented dev/CI-only values) | CI `secrets` job |
| Static analysis | ruff (incl. bandit `S` rules), mypy strict, ESLint (incl. jsx-a11y) | CI |

## Evidence required for assurance (not yet available)

Before any accreditation or formal assurance claim, the deploying organisation would need, at minimum:
an independent penetration test; a formal risk assessment against the applicable framework;
evidence of the deployed host and TLS configuration (the bundled TLS profile is a starting point,
not an assessed configuration); vulnerability-management and patching procedures;
backup restoration exercises with records; access-review procedures; a data-protection impact
assessment for trainee data; and a security review of any optional components added later.
