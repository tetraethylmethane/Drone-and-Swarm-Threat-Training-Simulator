# API contracts

Base path `/api/v1`. Machine-readable specification: `GET /api/v1/openapi.json` (the interactive
Swagger UI is disabled because it loads assets from a CDN). Shared schemas for scenarios, events and
actions: `packages/contracts/schemas/*.json`.

## Conventions

* JSON bodies; unknown fields are rejected (`422`).
* Errors: `{"error": {"code": "...", "message": "...", "details": ...}}`. Submitted values are never echoed.
* Authentication: cookie session (browser) with `X-CSRF-Token` header on POST/PUT/PATCH, or
  `Authorization: Bearer <token>` (adapters). `401` = not signed in / expired; `403` = not permitted
  or CSRF failure; `404` is also returned for objects the caller may not see.
* Lists: `{"items", "total", "limit", "offset"}`.

## Endpoints

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /health`, `GET /health/ready` | none | Liveness; readiness incl. database and migration revision |
| `POST /auth/login` | none (rate limited) | `{username, password, mode: cookie\|token}`. Returns the session (`mfa_required: false`), or `{mfa_required: true, mfa_token, expires_at}` when the account uses MFA |
| `POST /auth/mfa/verify` | none (rate limited) | `{mfa_token, code}`: TOTP or recovery code; returns the session as for login |
| `GET /auth/mfa`; `POST /auth/mfa/setup\|enable\|recovery-codes\|disable` | signed in (allowed before required enrolment) | MFA status, setup (current password; returns key and QR SVG), enable (code; returns recovery codes once), new recovery codes, disable (password and code; refused if the role requires MFA) |
| `POST /auth/logout`, `GET /auth/me`, `POST /auth/change-password` | signed in | Session management |
| `GET/POST /users`, `PATCH /users/{id}`, `POST /users/{id}/reset-password`, `POST /users/{id}/unlock`, `POST /users/{id}/reset-mfa`, `POST /users/{id}/anonymise` | administrator (instructors: read active trainees) | User management |
| `GET /scenarios`, `GET /scenarios/{id}` | all roles (trainees: self-guided library, briefing only) | Catalogue |
| `GET /scenarios/presets`, `POST /scenarios/validate`, `POST /scenarios/generate`, `GET /scenarios/{id}/preview` | instructor | Authoring tools |
| `POST /scenarios`, `POST /scenarios/key/{key}/versions`, `POST /scenarios/{id}/archive\|restore` | instructor | Create versions |
| `GET /rubrics`, `GET /rubrics/{id}` | instructor, administrator | Rubrics |
| `POST /rubrics/validate`, `POST /rubrics`, `POST /rubrics/key/{key}/versions` | instructor | Rubric versions |
| `GET/POST /assignments`, `GET /assignments/{id}`, `POST /assignments/{id}/cancel` | instructor; trainees read own | Assignments with progress |
| `POST /sessions` | trainee | Create an attempt (`assignment_id` or self-guided `scenario_id`, plus `selection`) |
| `GET /sessions?…&sort=newest\|score_asc\|score_desc`, `GET /sessions/{id}` | trainee own; instructor, administrator all | Session state. `sort` is applied before paging; unscored sessions come last |
| `POST /sessions/{id}/start\|pause\|resume\|complete` | owning trainee | Lifecycle (see transitions below) |
| `GET /sessions/{id}/feed?since_ms=` | owning trainee | Trainee-visible events + state; acts as heartbeat |
| `POST /sessions/{id}/actions` | owning trainee | Idempotent decision submission |
| `POST /sessions/{id}/abort` | instructor, administrator | Abort with reason (not scored) |
| `GET /sessions/{id}/result` | owner (filtered by feedback level), staff | Score result |
| `GET /sessions/{id}/timeline?category=&track_id=&limit=&offset=&around_seq=` | owner after completion, staff | AAR event log. `around_seq` returns the page holding that event under the same filters (ignored if the event is not visible to the caller) |
| `POST /sessions/{id}/verify` | instructor, administrator | Reproducibility check |
| `GET/PUT /sessions/{id}/review` | instructor writes; trainee reads if shared (no private notes) | Instructor review |
| `GET /analytics/progress\|filters\|difficulty` | staff all; trainee own | Persisted-results analytics |
| `GET /analytics/overview` | staff | Dashboard counts |
| `GET /reports/sessions.csv` | instructor, administrator | CSV export (same filters as `/sessions`) |
| `GET /reports/study.csv?scenario_key=&date_from=&date_to=` | instructor, administrator | Pseudonymised research dataset (audited) |
| `GET /analytics/learning-gains?trainee_id=&unit=&scenario_key=&same_difficulty_only=` | staff all; trainee own | First versus latest attempt with cohort statistics (observational) |
| `GET /analytics/competency?trainee_id=&scenario_key=` | staff (trainee required); trainee own | Dimension trends, recurring errors, identical-exercise groups, with the rule stated in `method` |
| `GET /analytics/compare?a=&b=` | staff; trainee own sessions only | Two scored attempts side by side, with `comparability` (`identical`, `same_scenario`, `different_scenarios`); track detail only when identical and permitted |
| `GET /analytics/units?scenario_key=&date_from=&date_to=` | staff | Unit-level summary |
| `GET /reports/sessions/{id}.pdf` | staff; trainee own when detailed feedback | PDF AAR |
| `GET /audit`, `GET /audit/verify` | administrator | Audit log and chain verification |
| `GET/PUT /admin/settings`, `GET /admin/system` | administrator | Settings (including `mfa_required_roles`, `retention_policy`), system health |
| `GET /admin/retention/preview`, `POST /admin/retention/run {dry_run}`, `GET /admin/retention/runs` | administrator | Data retention |
| `GET /admin/reproducibility?limit=` | administrator | Verify the latest completed sessions (1 to 500); audited |

When a signed-in user's role requires MFA and they have not enrolled, every endpoint except
`/auth/*` returns `403 mfa_enrollment_required`. `GET /sessions/{id}/timeline` adds
`events_purged_at` when the event log was removed by the retention policy.

**Assignments** accept `vary_seed` (default `true`) and `adaptive_adversary` (default `false`).
`GET /sessions/{id}/result` includes `adversary_plan` (the plan and reasons, or `null`); it is
available only after the exercise, like the result itself.

**Admission control.** When `DRIKR_MAX_ACTIVE_SESSIONS` is set and that many exercises are active,
`POST /sessions` and `POST /sessions/{id}/resume` return `503 capacity_reached` with a
`Retry-After: 30` header and a message for the trainee; nothing is stored. `GET /admin/system`
reports `capacity: {active_sessions, max_active_sessions}`.

## Simulation adapter protocol (browser adapter and future Unity client)

A visual client is a *presentation adapter*. It must not compute or alter simulation state.

1. Sign in (`mode: "token"` for non-browser clients) and obtain a session id from `POST /sessions`.
2. `POST /sessions/{id}/start` (or `resume`).
3. Loop about once per second: `GET /sessions/{id}/feed?since_ms=<last state.sim_time_ms>`.
   * The window is inclusive; de-duplicate by `event_id`.
   * On reconnect use `since_ms=0` to rebuild the full visible picture.
   * Polling more than `heartbeat_grace_s` (default 15 s) apart pauses the session
     (`pause_reason = connection_lost`); resume explicitly.
4. Render `track_observation` events (`x_m`, `y_m`, `alt_m` in metres, site at origin, +y north;
   RF observations carry `bearing_deg` only), `sensor_status`, `environment_update`,
   `exercise_message`, `track_lost` and `sensor_confirmation`.
5. Submit decisions with `POST /sessions/{id}/actions` and a fresh UUID `client_action_id`.
   Retry with the same id on network failure; the response flags `duplicate: true`.
6. `POST /sessions/{id}/complete`.

### Session transitions

| From | Operation | To |
|---|---|---|
| created | start | running |
| running | pause (if allowed) / connection lost | paused |
| paused | resume | running |
| running, paused | complete / time limit | completed (scored) |
| created, running, paused | abort (staff) | aborted (not scored) |

Any other transition returns `409 invalid_transition`.

### Action body

```json
{"client_action_id": "uuid", "kind": "classify", "track_ids": ["TRK-001"],
 "classification": "small_multirotor", "confidence": "low", "note": "optional"}
{"client_action_id": "uuid", "kind": "respond", "track_ids": ["TRK-001", "TRK-002"],
 "response": "report_to_exercise_control"}
```
