# Security findings and residual-risk register (Sprint 10, workstream D)

Review dates: 2026-10-16. Reviewer: the development team (an internal review, **not an
independent assessment or penetration test**). Nothing here is a certification, accreditation or
compliance claim. Scope: the API, web client, database, Docker deployment, backups and the Unity
client's use of the API. Evidence comes from tests in this repository and commands run on one
Windows 11 development laptop.

## 1. Findings

| ID | Area | Finding | Severity | Status | Evidence or regression test |
|---|---|---|---|---|---|
| F-01 | Database access | The API connected as the PostgreSQL **superuser** that owns the schema. A defect or injection in the API could therefore rewrite events, scores and the audit chain consistently, drop triggers, or read other databases | **High** | **Fixed** | New least-privilege role `drikr_app`, provisioned at API start (`drikr-api provision-app-role`, `db_roles.py`): LOGIN only (no superuser, CREATEDB, CREATEROLE, REPLICATION, BYPASSRLS); no rights on the schema or `alembic_version`; INSERT and SELECT only on `audit_events` and `score_results`; no UPDATE on `session_events`. Migrations use a separate owner URL (`DRIKR_MIGRATION_DATABASE_URL`). `tests/integration/test_db_role.py`: 11 forbidden statements refused, role attributes checked, full workflow run as the app role. *System health* shows the role and whether it is least-privilege |
| F-02 | Record integrity | Session events and score results could be edited by any role with table rights; only the audit table had a trigger | Medium | **Fixed** | Migration `0004`: statement-level triggers make `session_events` append-only and `score_results` immutable (UPDATE and DELETE refused). Deleting events is still allowed, because retention purges raw logs. `tests/integration/test_integrity.py::test_database_refuses_edits_to_records` |
| F-03 | Authorisation boundary | Route coverage was tested by a hand-written list, so a new route without authentication could go unnoticed | Medium (process) | **Fixed** | `tests/integration/test_route_security.py` calls **every** operation in the OpenAPI schema anonymously and expects 401, except an explicit list of 5 public routes. It also checks that instructors are refused 6 administrator configuration operations, and that a trainee gets 404 or 403 on another trainee's session, result, timeline, PDF, comparison, verification and exports |
| F-04 | Availability | Pool exhaustion under 10 concurrent trainees: requests failed after 30 s (load-test defect L-01) | Medium | **Fixed** | docs/testing/load-resilience-report.md; `tests/integration/test_session_creation_load.py` |
| F-05 | Adaptive difficulty | The instructor override is a new privileged write | Low | Controlled | Requires `ASSIGNMENTS_MANAGE`; bounded to the assignment's limits and one step; reason required (3–280 characters); audited as `assignment.difficulty_override`; trainees get 403. `tests/integration/test_adaptive_override.py` |
| F-06 | Information disclosure | `GET /api/v1/openapi.json` is served without signing in | Low | **Accepted** (R7) | The schema has no data or secrets, the source code is public, and `test_health_config.py` asserts this deliberately. Reverse proxies can block it if wanted |
| F-07 | Logging | API logs at INFO (703 request records), the nginx access log (about 44,000 lines) and the audit table were searched for 5 canary secrets, a live session token and every deployment secret. The load-test stack logs at WARNING by default, so an earlier claim of a scan over "about 70,000 API lines" could not be reproduced and is withdrawn | Info | **No issue found**. Note: a failed sign-in records the attempted *username* in the audit log (R5), so a password typed into the username field would be kept | Section 3.2 |
| F-09 | Record integrity | The app role could DELETE raw event logs (retention needs deletion) and UPDATE `training_sessions.events_purged_at`. A compromised API process could therefore delete a session's log and mark it purged, and verification would report `event_log_purged` rather than a failure | Low | **Fixed** (2026-10-17, migration `0005`) | Raw logs are deleted only by two owner-defined `SECURITY DEFINER` functions: retention (finished sessions older than a real retention run's cutoff, at least 30 days, measured by the database clock) and anonymisation (a deactivated trainee's finished sessions). Each purge is written to the append-only `event_log_purges` table, which the app role can only read. `events_purged_at` can be set only once, and only with a purge record. Verification accepts a purge only with a matching record. The app role has lost DELETE on `session_events`. Tests: `tests/integration/test_purge_integrity.py` (6). **Residual:** a compromised API can still purge *old* logs through a fabricated retention run, or a user's logs after deactivating the account. Such a purge is recorded permanently and never changes a score (R9) |
| F-08 | Backup and restore with the app role | Restore uses `--no-privileges`, which drops grants on the restored tables | Low | **Mitigated by design; verified 2026-10-17** | The API re-runs `provision-app-role` at every start, and `restore.sh` restarts it. Section 3.3 records the backup → verify → change → restore cycle, the role's privileges after the restore, and a write workflow as that role |

## 2. Review checklist

| Area | Result | Basis |
|---|---|---|
| RBAC | Pass | Permission map on every endpoint (`security/rbac.py`); `test_rbac.py` role matrix; F-03 |
| Authentication and session handling | Pass | Argon2id, hashed session tokens, idle and absolute timeouts, lockout, rate limits, TOTP MFA (`test_auth.py`, `test_mfa.py`) |
| Input validation | Pass | `extra="forbid"` models with bounds; partial invalid actions write nothing (`test_integrity.py`); scenario schema bounds (`test_contracts.py`) |
| Cross-trainee access | Pass | F-03 (404, so that existence is not revealed) |
| Instructor-only and administrator-only configuration | Pass | F-03 |
| Secrets | Pass | `.env` git-ignored; startup refuses placeholder secrets; gitleaks in CI; the load-test env file is generated and git-ignored |
| Dependencies | See section 3 | pip-audit and npm audit run on 2026-10-16 |
| Audit integrity | Pass | Hash chain with an append-only trigger, verified after the resilience run; the app role cannot UPDATE or DELETE audit rows (F-01) |
| Database access restrictions | Pass after F-01 | `test_db_role.py` |
| Backup and restore | Pass | F-08 |
| Offline operation | Pass | No runtime third-party origins; docs/operations/offline-deployment.md |
| Interrupted sessions | Pass | Pause after 15 s grace; resume; restart recovery (`test_integrity.py`, `test_perimeter_basics.py`, resilience run) |
| Logging | Pass | F-07 |

## 3. Verification records

Commands run on 2026-10-16 against the final Sprint 10 code (the working tree with every Sprint 10
change). Host: Windows 11 10.0.26200; Docker Desktop 27.3.1.

### 3.1 Dependencies and secrets

| Check | Command | Result |
|---|---|---|
| Python dependencies (16:28 UTC) | `pip-audit` 2.7.3 in the project environment | **0 known vulnerabilities.** The four local packages (`drikr-api`, `-contracts`, `-scoring`, `-simcore`) are not on PyPI and are skipped |
| Web dependencies, including dev tooling | `npm audit` in `apps/web` | **0 vulnerabilities** |
| E2E tooling | `npm audit` in `tests/e2e` | **0 vulnerabilities** |
| Secrets in history | `gitleaks` 8.30.1 (`zricethezav/gitleaks:v8.30.1`), `git` mode over the repository | 7 commits, **no leaks found** |
| Secrets in history (2026-10-18) | Same image and mode | 11 commits (to `a30c00c`), **no leaks found** |
| Secrets in uncommitted work | Same image, `dir` mode over a copy of every modified or untracked, non-ignored file (85 files; `git ls-files -mo --exclude-standard`), with `.gitleaksignore` | **No leaks found** |
| Private keys and generated secrets kept out of git | `git check-ignore -v` on `deploy/tls/ca.key`, `server.key`, `ca.crt`, `deploy/loadtest/loadtest.env` | All ignored (`.gitignore` lines 26 and 51) |
| Container images (Trivy, 2026-10-17) | `aquasec/trivy:0.66.0 image --severity HIGH,CRITICAL --ignore-unfixed` on the images that were load-tested: `drikr-api:1.0.0` (`288221e39d7c`, Debian 12.15 plus Python packages) and `drikr-web:1.0.0` (`13b56e554b5f`, Alpine 3.24.1) | **0** in both (JSON totals over every target). The `postgres` image was not scanned (O12) |
| Container images (Trivy, 2026-10-18) | Same command (database updated 2026-10-18 07:12 UTC) on images built from commit `a30c00c`: `drikr-api:rc-a30c00c` (Debian 12.15) and `drikr-web:rc-a30c00c` (Alpine 3.24.1) | api **0**. web: **1 HIGH**, CVE-2026-77214 in `libexpat` 2.8.5 (published after the previous scan). The Dockerfile's `apk upgrade` had been served from Docker's build cache; rebuilt with `--no-cache` it installs 2.9.0-r0 and the scan is **0**. Release images must be built without the cache (`--no-cache --pull`). The running deployment's `drikr-web:1.0.0` still has 2.8.5 until it is rebuilt |

### 3.2 Logging (F-07), 2026-10-17

The load-test API was restarted at `DRIKR_LOG_LEVEL=INFO` (`LT_LOG_LEVEL=INFO`; production default
INFO). Requests then sent: a sign-in with a wrong password (`CANARY-WrongPw-…`); a sign-in as an
unknown user with a canary password; a successful token sign-in (the 43-character token was kept
for the search); `GET /auth/me` with that bearer token; `change-password` with canary current and new
passwords; a request with a canary token in the query string; and a 2-minute k6 run with 5 trainees
(687 requests). The API log (709 lines, 703 structured request records), the nginx log and the
`audit_events` table were then searched for all 5 canaries, the live token, the user password, both
database passwords and the secret key, and the logs also for `Authorization`/`Bearer`, cookie and
CSRF headers and any 40+ character base64url string.

Result: **0 matches** for every value in both logs. No headers. Logs carry the path without the query
string. In the audit table, 0 canary passwords; the failed sign-in stored only the attempted
username.

### 3.3 Backup and restore with the least-privilege role (F-08), 2026-10-17

The unmodified `scripts/backup.sh`, `verify-backup.sh` and `restore.sh` ran against the isolated
load-test stack (`COMPOSE_PROJECT_NAME=drikrload`, `COMPOSE_FILE`, `COMPOSE_ENV_FILES`, and the new
`DRIKR_ENV_FILE` override, added in this sprint so the scripts can address another stack's
settings). Before anything destructive, the variables were checked to resolve only to the
`drikrload-*` containers.

| Step | Result |
|---|---|
| Backup | Dump, SHA-256 and audit head `7cad145f…` (297 events, valid) |
| Verify (scratch database) | Checksum OK; schema `0004`; 104 users, 4 scenarios, 971 sessions, 971 results, 297 audit events; chain valid with the **same head hash** |
| Change after the backup | A practice session created through the API (971 → 972 sessions) |
| Restore (`--yes`) | Chain valid, same head hash `7cad145f…`; **972 → 971 sessions** (the change is gone) |
| App role after the restore | Not superuser, CREATEROLE or BYPASSRLS; `UPDATE` on `score_results`, `DELETE` on `audit_events` and `UPDATE` on `session_events` all **false**; `INSERT` on `session_events` and `training_sessions` true |
| Workflow as the role after the restore | Sign-in, create, start, complete and result all succeeded (200); the chain extends validly (298 events) |

A first attempt to make the post-backup change with a direct SQL insert failed on a NOT NULL
column. It was replaced by the API change above, so it played no part in the result.

### 3.4 Static checks and tests

Full Python suite on the final code (adaptive policy F, L-02): see `docs/SPRINT_STATUS.md`. The
security-relevant tests (`test_db_role.py`, `test_route_security.py`, `test_integrity.py`,
`test_adaptive_override.py`, `test_auth.py`, `test_mfa.py`, `test_rbac.py`) all passed. Ruff
(including bandit `S` rules) and strict mypy are clean.

## 4. Residual-risk register

| ID | Risk | Likelihood | Impact | Treatment | Owner | Status |
|---|---|---|---|---|---|---|
| R1 | HTTPS is opt-in; private CA distribution and certificate renewal are manual | Medium | Medium | Use `docker-compose.tls.yml` on any network; renewal before 397 days | Operator | Open (accepted) |
| R2 | A host administrator or database superuser can rewrite records and the audit chain consistently | Low | High | Keep the exported audit head hash off-host. F-01 removes this ability from the **application**, not from the operator | Operator | Open (accepted) |
| R3 | In-process rate limits do not coordinate across API replicas | Low | Low | Run one API process (the supported deployment) | Development | Open (accepted) |
| R4 | TOTP is not phishing-resistant; rotating the secret key invalidates MFA | Low | Medium | WebAuthn on the backlog | Development | Open (accepted) |
| R5 | The audit log keeps usernames and IP addresses permanently; backups keep data until rotated | Certain | Low | Documented for the DPIA | Data controller | Open (accepted) |
| R6 | Single API process: beyond its capacity every trainee slows down, and server delay counts against trainees' response times. On the development laptop, 30 concurrent trainees met the latency criteria in 4 of 5 runs, with little headroom (the first run after a host restart failed them), and 60 ran without errors but outside them (feed p95 2.0 s); capacity on deployment hardware is **unmeasured** | Medium | Medium | Measure on the target host before use; set `DRIKR_MAX_ACTIVE_SESSIONS` below the measured capacity (admission control, load report 5.8); stagger class starts (B-17) | Development, operator | Open |
| R7 | Public API schema (F-06) | n/a | Low | Optional block at the proxy | Operator | Accepted |
| R8 | No independent penetration test or formal risk assessment | n/a | n/a | Required before any assurance claim (security-controls.md) | Deploying organisation | Open |
| R9 | A compromised API process can still destroy raw event logs that are past the retention minimum (30 days), or those of an account it deactivates, by calling the purge functions. Each purge is recorded permanently with its reason, and scores are unaffected | Low | Low | F-09 fixed the disguised purge. Audit reviews should compare `event_log_purges` with the audited retention runs and anonymisations | Operator | Open (accepted) |
