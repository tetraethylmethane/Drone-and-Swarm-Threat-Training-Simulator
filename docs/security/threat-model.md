# Threat model

Method: STRIDE over the deployed components (browser, nginx, API, PostgreSQL, backup files).
Assets: training records and scores (integrity), user credentials (confidentiality), audit trail
(integrity), scenario/rubric definitions (integrity), availability of exercises during training.

The system holds **no classified or operational data** and controls nothing outside itself.
Impact is therefore mainly *integrity of training records* and *personal data of trainees*.

## Trust boundaries

1. Browser or Unity client ↔ nginx (untrusted network; HTTPS via `docker-compose.tls.yml`).
2. nginx ↔ API (internal Docker network; API not published to the host).
3. API ↔ PostgreSQL (internal network; credentials from `.env`). Since Sprint 10 the API connects
   as the least-privilege role `drikr_app`; the owner credentials are used only for migrations and
   to provision that role (security-findings.md F-01).
4. Operator ↔ host (Docker, `.env`, backups) — fully trusted.

## Threats and mitigations

| ID | STRIDE | Threat | Mitigation | Verified by |
|---|---|---|---|---|
| T1 | Spoofing | Password guessing or a stolen password | Optional or role-required TOTP second factor; Argon2id; lockout after 5 failures for 15 min; per-IP and per-username rate limit; generic failure message | `test_auth.py` (lockout, rate limit, generic errors) |
| T2 | Spoofing | Session theft via XSS | HttpOnly cookie scoped to `/api`; strict CSP (`script-src 'self'`); React escaping; no `dangerouslySetInnerHTML` | CSP in `apps/web/nginx.conf`; code review |
| T3 | Tampering | CSRF | SameSite=Strict cookie and double-submit CSRF token on all unsafe methods | `test_auth.py::test_csrf_required_for_cookie_sessions`, E2E |
| T4 | Elevation | Trainee calls staff endpoints | Backend `require()` permission checks; object-level ownership checks returning 404 | `test_rbac.py` role matrix, E2E `security-and-access` |
| T5 | Information disclosure | Trainee reads ground truth during an exercise | Feed excludes ground-truth events; briefing omits entity groups; timeline and preview blocked | `test_session_flow.py`, `test_rbac.py` |
| T6 | Tampering | Trainee manipulates timing or submits for invisible tracks | Server clock stamps all actions; tracks must be visible at server time; client time ignored | `test_session_flow.py` |
| T7 | Tampering | Duplicate or replayed actions | `client_action_id` uniqueness constraint; idempotent completion; one result per session | `test_session_flow.py` (concurrency test) |
| T8 | Repudiation | Privileged change without trace | Hash-chained audit log in the same transaction; append-only trigger | `test_audit_and_constraints.py` |
| T9 | Tampering | Direct database edit of audit or scores | The API's role cannot UPDATE or DELETE audit rows or scores, or UPDATE events (F-01); triggers refuse those edits for every role, including the owner (migration `0004`, F-02); chain verification and score `verify` detect edits. A superuser can still rewrite consistently (R2) | `test_tampering_is_detected`, `test_integrity.py::test_database_refuses_edits_to_records`, `test_db_role.py::test_app_role_cannot_rewrite_history_or_the_schema` |
| T10 | Information disclosure | Secrets in logs or source | Structured logs without bodies, headers or query strings; validation errors never echo values; `.env` git-ignored; gitleaks in CI | `test_passwords_hashed_and_never_logged` |
| T11 | Denial of service | Request flooding, or more concurrent trainees than the host can serve | Login and action rate limits; 1 MB body limit; pagination limits; event cap per scenario (120 k). Measured capacity on one laptop: 30 trainees within the latency criteria in 4 of 5 runs (little headroom), 60 without errors but slower (load-resilience-report.md). **No admission control**: overload degrades every trainee (O-L2) | unit and integration tests; load report |
| T12 | Tampering | Malicious scenario JSON (resource exhaustion) | Strict schema with bounds (≤ 60 entities, ≤ 1800 s, ≤ 50 events); generation check before saving | `test_contracts.py` |
| T13 | Information disclosure | CSV formula injection in exports | Cells starting with `= + - @` are prefixed with `'` | `test_reports_analytics.py` |
| T14 | Supply chain | Vulnerable dependency or image | Exact version pins and lockfiles; `pip-audit`, `npm audit`, Trivy image scan in CI | CI workflow (results in `SPRINT_STATUS.md`) |
| T15 | Information disclosure | Plain-HTTP access on a network | Bundled HTTPS configuration (TLS 1.2+, HSTS, HTTP redirect) with a certificate script; Secure cookies by default; only `127.0.0.1` published by default | Verification record in `docs/operations/offline-deployment.md`; Unity `SecurityTests` (pinned CA, untrusted rejected) |
| T16 | Spoofing | Replay or guessing of MFA codes | Last accepted time step stored, so codes are single-use; challenge token single-use, 5 minutes, 5 attempts; failures count towards lockout; recovery codes single-use and stored as HMAC digests | `test_mfa.py` |
| T17 | Information disclosure | MFA secrets read from the database or a backup | Sealed with AES-256-GCM under a key derived from `DRIKR_SECRET_KEY` (not stored in the database), bound to the user id | `test_mfa.py::test_secret_is_encrypted_at_rest`, `test_totp_secretbox.py` |
| T18 | Information disclosure | Personal data kept longer than needed | Retention policy with preview and audited runs; anonymisation of departed users; pseudonymised research export | `test_retention.py`, `test_study.py` |
| T19 | Tampering, elevation | A defect or injection in the API used to rewrite history or the schema | API runs as `drikr_app`: no superuser, CREATEDB, CREATEROLE, REPLICATION or BYPASSRLS; no schema rights; INSERT and SELECT only on audit and scores; no UPDATE on events; cannot disable triggers or change `session_replication_role`. Residual: it can still DELETE raw event logs (needed for retention) and mark them purged (F-09) | `test_db_role.py` (11 forbidden statements, role attributes, full workflow as the role) |
| T20 | Elevation | A new route added without authentication | Every operation in the OpenAPI schema is called anonymously and must return 401, except an explicit list of 5 public routes | `test_route_security.py::test_every_non_public_operation_rejects_anonymous_calls` |
| T21 | Information disclosure, elevation | A trainee reads another trainee's records, or an instructor changes administrator configuration | Object-level ownership checks (404, so existence is not revealed); permission checks on 6 administrator configuration operations | `test_route_security.py::test_trainees_cannot_reach_other_trainees_records`, `…::test_instructors_cannot_change_administrator_configuration` |
| T22 | Tampering | Misuse of the instructor difficulty override | Requires `ASSIGNMENTS_MANAGE`; one step at a time, within the assignment's bounds; reason required; audited (`assignment.difficulty_override`); trainees get 403 | `test_adaptive_override.py` |
| T23 | Tampering | A client (web or Unity) invents or alters exercise state, for example after a reconnect | The server is authoritative (ADR-001): clients receive only trainee-visible events and rebuild their picture from the server; the server stamps decisions and checks that tracks were visible at *server* time | `test_integrity.py::test_reconnecting_client_rebuilds_the_same_state_from_the_server`, `test_session_flow.py` |

## Residual risks (accepted or open)

* **R1 (addressed in 1.0.0-rc3):** HTTPS is available through `docker-compose.tls.yml`. It is
  opt-in: the default compose file still serves plain HTTP on `127.0.0.1`. Residual: a private CA
  must be distributed to workstations and protected by the operator; certificate renewal is
  manual (the server certificate is valid for 397 days).
* **R2 (accepted):** A database superuser or host administrator can rewrite records and the audit
  chain consistently. Mitigation is procedural: keep the exported audit head hash off-host. Since
  Sprint 10 the *application* no longer has this ability (T19).
* **R3 (accepted):** In-process rate limiting does not coordinate across multiple API replicas.
* **R4 (addressed in 1.0.0-rc3):** TOTP multi-factor authentication, required for administrators
  by default. Residual: TOTP can be phished in real time (it is not phishing-resistant like
  FIDO2/WebAuthn); rotating `DRIKR_SECRET_KEY` invalidates enrolled secrets.
* **R5 (addressed in 1.0.0-rc3):** Retention policy, scheduled or manual runs, and anonymisation
  (`docs/security/data-retention.md`). Residual (accepted): the audit log keeps usernames and IP
  addresses permanently to preserve its integrity; backups keep data until rotated.
* **R6–R9:** see the residual-risk register in `docs/security/security-findings.md` (load capacity,
  public API schema, absence of an independent assessment, disguised purge of raw event logs).

Last reviewed 2026-10-16 (Sprint 10).
