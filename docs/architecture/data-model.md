# Data model

Source of truth: `apps/api/drikr_api/models.py` and migration `database/migrations/versions/0001_initial_schema.py`.
`alembic check` (run in CI) confirms the migration matches the models.

| Table | Purpose | Key integrity rules |
|---|---|---|
| `users` | Accounts with role `administrator`, `instructor` or `trainee`; Argon2id hash; lockout counters; `must_change_password`; MFA secret sealed with AES-GCM (`mfa_secret_enc`, pending secret during setup), `mfa_enabled_at`, last accepted TOTP step; `deactivated_at`, `anonymised_at`; optional `unit` (team or course, migration `0003`). | Unique username; username format CHECK; role is a PostgreSQL enum; `mfa_consistent` (secret present ⇔ enabled). |
| `auth_sessions` | Server-side sign-in sessions. Stores HMAC digests of the session and CSRF tokens only. | Unique token digest; `kind ∈ {cookie, bearer}`; revocation timestamp. |
| `mfa_recovery_codes` | Single-use recovery codes, HMAC digests only, with `used_at`. | FK to user (CASCADE). |
| `mfa_challenges` | Pending second sign-in step: token digest, mode, expiry, attempts, `used_at`. | `mode ∈ {cookie, token}`. |
| `retention_runs` | Each retention run: trigger, dry run flag, policy applied and summary. | `trigger ∈ {admin, cli}`. |
| `rubrics` | Immutable rubric versions (JSONB definition, SHA-256 digest, demo flag). | Unique `(key, version)`; `version ≥ 1`. |
| `scenarios` | Immutable scenario versions; status `published`/`archived`; references its rubric version. | Unique `(key, version)`; FK to rubric (RESTRICT). |
| `assignments` | Trainee ↔ scenario version, options, difficulty mode/level/bounds, attempts, feedback level, due date. | Level bounds CHECKs; attempts 1–50; FKs RESTRICT. |
| `training_sessions` | One attempt: effective definition, seed, level, digests, engine version, clock fields, status. | `mode = assigned ⇔ assignment_id NOT NULL`; `status = running ⇔ running_since NOT NULL`; elapsed within duration. |
| `session_events` | Append-only ordered event log per session (generated, system, trainee). | Unique `(session, seq)`, `(session, event_id)`, `(session, client_action_id)`; times tick-quantised and `available_at ≥ t`; visibility/origin enumerations. Indexed for feed and type queries. |
| `score_results` | One authoritative result per session with versions and digests. | Unique `session_id`; `status ∈ {scored, insufficient_data}`; overall 0–100. |
| `difficulty_adjustments` | Every adaptive recommendation with reason and evidence. | Non-empty reason; change ∈ {increase, decrease, hold}; at most one level step. |
| `instructor_reviews` | Review status, private notes, shared strengths/improvements, focus objectives. | Unique per session. |
| `audit_events` | Hash-chained audit records of privileged and security-relevant actions. | Append-only trigger; unique hash. |
| `app_settings` | Administrator settings (adaptive policy, self-guided switch, MFA-required roles, retention policy). | Primary key `key`. |

## Event payloads

Typed in `packages/contracts/drikr_contracts/events.py`; JSON Schema in
`packages/contracts/schemas/sim-event.schema.json`. Ground-truth types (`entity_spawned`,
`entity_state`, `entity_exited`, `track_assigned`, `observation_missed`) always carry
`visibility = ground_truth` and are never sent to trainees during an exercise. Every
`track_observation` and `sensor_confirmation` payload carries `synthetic: true`.

## Retention

Retention is set by an administrator policy (migration `0002`): raw `session_events` can be deleted
some days after completion (`training_sessions.events_purged_at` records it; scores and digests are
kept), expired `auth_sessions` and `mfa_challenges` are deleted, and deactivated accounts can be
anonymised. `audit_events` are never deleted. Details: `docs/security/data-retention.md`.

Migration `0006` adds `assignments.vary_seed` (each attempt gets its own recorded seed; existing
rows keep `false`), `assignments.adaptive_adversary`, and `training_sessions.adversary_plan` (JSONB:
the adaptive adversary's tactics, evidence and reasons; ADR-012).

Since migration `0005`, raw logs are deleted only by the owner-defined functions
`drikr_purge_session_events` (retention) and `drikr_purge_user_event_logs` (anonymisation). Each
purge is recorded in **`event_log_purges`** (one row per session: `reason ∈ {retention,
anonymisation, legacy}`, the retention run for `retention`, time, events deleted). The table is
append-only; `events_purged_at` can be set once and only when a purge record exists; the API's
database role can only read it (security finding F-09).
