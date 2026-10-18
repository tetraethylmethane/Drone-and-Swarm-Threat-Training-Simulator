# Architecture decision records

Status values: **Accepted** (implemented and tested), **Accepted with limitation**, **Deferred**.

---

## ADR-001 Simulation authority on the server; Unity and browser as visual clients

**Status:** Accepted. Revised 2026-10-15 (Unity client added) and **re-verified 2026-10-16**
(Sprint 10 audit of the code and tests).

### Decision

The server is the single source of truth for simulation state, event ordering, scenario execution,
timestamps, random seeds, scoring inputs and completed session records. Unity (and the browser
adapter) present the state and collect the trainee's decisions. Neither computes an authoritative
outcome or score.

### Why the server remains authoritative

- **One engine, one timeline, one score**, whichever client is used. The deterministic Python engine
  (`packages/simcore`) generates the whole event timeline from the scenario version, seed and
  difficulty, and the same process scores it (`packages/scoring`).
- **Integrity:** timing and ground truth never live on the trainee's machine, where they could be
  changed. The server stamps every decision with its own clock.
- **Testability:** generation, scoring and verification run without Unity, in CI, on every change.
- **Reproducibility:** a stored session can be regenerated and re-scored from its record alone
  (below). Achieving this inside a game engine would need its own determinism work, with no user
  need identified for it.

### How clients receive and present state (adapter protocol, ADR-003)

1. The client creates or opens a session and receives the session state (status, server simulation
   time, duration, seed and difficulty for display).
2. While running, it polls `GET /sessions/{id}/feed?since_ms=` once a second (every 4 s when idle).
   The server returns only **trainee-visible** events whose `available_at_ms` has passed, plus the
   authoritative state. Ground-truth events are never sent.
3. The client projects those events into its track picture (`TrackPicture.cs`, `trackPicture.ts`:
   order-independent and duplicate-tolerant).
4. Decisions go to `POST /sessions/{id}/actions` with a client-generated `client_action_id`
   (idempotency key). The server validates the decision against *its* state (tracks visible at
   *server* time), stamps it and appends it to the log.
5. Results are fetched from `GET /sessions/{id}/result`. The Unity client only displays them.

**Client-side behaviour found in the audit (all presentation-only, none authoritative):**
- the displayed clock is extrapolated between polls, capped at 2 s ahead of the last server time,
  and never sent back;
- `client_action_id` is generated on the client, but only to make retries idempotent;
- track selection, camera and the chosen classification before submission are local UI state;
- the Unity client displays the result from the server (`DrikrClientApp.cs` `ShowResult`).

No duplicated simulation authority was found, so nothing had to be removed.

### How events are recorded

- At session creation the full generated timeline is stored in `session_events` (sequence numbers
  0…n−1), with the scenario version, effective configuration, seed, difficulty, engine version and
  timeline digest on the session row.
- Trainee decisions and system events (pause, connection loss, sensor confirmations) are appended
  with the next sequence number in the same transaction as the state change.
- Sequence numbers are unique and contiguous; `(session, client_action_id)` is unique, so a
  retried action is recorded once.
- Since migration `0004`, the database refuses `UPDATE` on `session_events` and `UPDATE` or
  `DELETE` on `score_results`. The API's database role cannot do either at all (`docs/security/security-findings.md` F-01).

### How reproducibility is tested

`tests/reproducibility` (reproducibility marker), `tests/integration/test_integrity.py`,
`test_traceability.py`, `test_perimeter_basics.py`, the per-session `verify` endpoint and the bulk
report (`/admin/reproducibility`, `drikr-api reproducibility-report`). Results:
`docs/testing/reproducibility-report.md`.

### Disconnections and interrupted sessions

- **Client disappears:** with no poll for longer than the grace period (15 s), the server pauses the
  session at the last heartbeat plus grace (`pause_reason = connection_lost`). Exercise time does not
  run while nobody is watching. The trainee resumes explicitly.
- **Client reloads or reconnects:** it fetches the feed from time 0 and rebuilds the picture from
  the server. It never invents a new state (`test_reconnecting_client_rebuilds_the_same_state_from_the_server`).
  The Unity client discards its local picture when it opens a session.
- **API restart:** sessions continue from the database. No exercise state is held only in memory
  (`test_session_continues_after_the_api_restarts`, plus the resilience test in
  `docs/testing/load-resilience-report.md`).
- **Abandoned or timed-out sessions** are finalised by the sweeper. Completed results are written
  once and are idempotent under retries.

### Limits of deterministic replay

- The guarantee is **logical equivalence**: the same scenario version, configuration, seed and
  difficulty give the same canonical event records (positions rounded to 0.1 m, qualities to 0.01
  before hashing; ADR-011), so the timeline digest is identical. Identical stored events with the
  same rubric and engine version give byte-identical score output.
- Not replayed: rendering frames, camera movement, client frame timing, or the moment *within a
  100 ms tick* at which the trainee clicked. Decisions are quantised to the server tick.
- Across scoring-engine versions, the guarantee is that the **assessment** (scores, outcomes, error
  counts) is unchanged, not the byte output.
- Cross-platform equality is verified on Windows/CPython 3.12.4 and Linux/CPython 3.12.7 and
  3.12.14. Other platforms are expected but not verified.

### Conditions that would justify reconsidering

- A training requirement for real-time physics or sensor effects that the server cannot generate in
  advance (for example closed-loop flight control by the trainee). The timeline would then depend on
  continuous client input.
- Hard real-time multiplayer interaction where polling at 1 s cannot meet a measured latency
  requirement (ADR-003 lists push transport as the first step before moving authority).
- A measured scalability limit that server-side generation cannot meet with more API processes.
  The 2026-10-16 load test found a capacity limit in the **single API process** (it is CPU-bound in
  Python), not in server authority: generation and scoring run per session, and the per-request
  cost is what limits throughput. That limit is addressed inside this architecture
  (`docs/testing/load-resilience-report.md`), so it is not a reason to move authority to the client.

---

## ADR-002 Simulation timing model

**Status:** Accepted

* Fixed simulation step of **100 ms** (`TICK_MS`). Kinematics integrate every tick; all event
  times (`t_ms`, `available_at_ms`) are integer multiples of 100 ms (enforced by contract and by a
  database CHECK constraint).
* Ground-truth entity state is recorded once per simulated second.
* Each simulated sensor updates on its own interval with a seeded phase offset.
* `available_at_ms = ceil_to_tick(t_ms + latency + scripted extra delay)`; never earlier than `t_ms`.
* **Exercise clock (server-authoritative):** `sim_time = sim_elapsed_ms + (now - running_since)`,
  quantised down to the tick and capped at the duration. Paused time does not count.
* **Connection-loss rule:** time stops accruing at `last_heartbeat + heartbeat_grace_s` (default
  15 s). A running session whose client stays silent past the grace period is paused with
  `pause_reason = connection_lost` (or completed with `time_limit` if the limit was reached). The
  feed poll is the heartbeat. A background sweeper applies the same rule to abandoned sessions.

**Consequences.** Network jitter cannot change what a trainee could have seen or when; decisions are
time-stamped by the server, not the client. Recovery after a crash or restart is deterministic
because the clock is reconstructed from stored fields.

---

## ADR-003 Communication protocol between visual clients and backend

**Status:** Accepted

**Options considered.** WebSocket push; Server-Sent Events; HTTP polling.

**Decision.** JSON over HTTPS with **polling** (`GET /sessions/{id}/feed?since_ms=` about once per
second) and idempotent `POST /sessions/{id}/actions` carrying a client-generated
`client_action_id` (UUID).

**Rationale.** Works through the bundled reverse proxy with no extra infrastructure; trivially
recoverable after disconnects (re-request from `since_ms=0`); the server stays authoritative; a
Unity client can implement it with `UnityWebRequest`. The event volume (≤ ~10 events/s) does not
justify a push channel. Feed windows use an inclusive lower bound and clients de-duplicate by
`event_id`, so overlapping polls are safe.

**Revisit when** multiple observers per session or sub-second visual latency are required.

---

## ADR-004 Database: PostgreSQL only

**Status:** Accepted

PostgreSQL 17 is the single supported database (JSONB event payloads, advisory locks for the audit
chain, CHECK constraints, triggers). SQLite is **not** used anywhere: integration tests run against a
real PostgreSQL to avoid divergence. For local development without Docker, `scripts/local-postgres.ps1`
runs an isolated cluster from installed PostgreSQL binaries on port 55432 (deliberately scoped
development mode; data under `%LOCALAPPDATA%`, outside synced folders).

---

## ADR-005 Immutable versioning of scenarios and rubrics

**Status:** Accepted

Scenario and rubric rows are never updated in place. Saving creates `version = max + 1` with a
SHA-256 digest of the canonical definition. Sessions store a copy of the *effective* definition
(after permitted trainee selections), the seed, difficulty level, engine version, a configuration
digest and the timeline digest. Score results store rubric id/version, scoring-engine version,
input digest and result digest. Historical scores are therefore never silently recomputed; the
`verify` endpoint re-derives them on demand and reports any engine-version difference.

---

## ADR-006 Scoring: transparent rules, no machine learning

**Status:** Accepted

The scoring engine (`packages/scoring`) is a deterministic function of recorded events, the scenario
and a versioned rubric (weights, timing thresholds, partial-credit table, uncertainty rules, a
configurable decision tree and procedure rules). Every credit carries a recorded reason. Adaptive
difficulty is a documented rules-based policy (`drikr_scoring.adaptive`). No ML model is used; none
is planned until a measurable need, data provenance, evaluation criteria and a fallback are
established (brief §6). See `docs/architecture/scoring-model.md`.

---

## ADR-007 Authentication and session tokens

**Status:** Accepted

Opaque random tokens (256-bit) stored server-side only as HMAC-SHA-256 digests keyed by
`DRIKR_SECRET_KEY`. Browser sessions use an HttpOnly, SameSite=Strict cookie scoped to `/api`, plus a
double-submit CSRF token required on every state-changing request. Adapter clients (e.g. Unity) may
request a bearer token (`mode: "token"`), which is not accepted as a cookie and vice versa.
Passwords use Argon2id. Absolute and idle session expiry, account lockout and login rate limiting
apply. Rationale: revocable sessions (sign-out, role change, password change take effect
immediately), no JWT key-management burden, no tokens readable by page scripts.

---

## ADR-008 Tamper-evident audit log

**Status:** Accepted

Each audit row stores `hash = SHA-256(prev_hash || canonical_json(record))`, appended under a
PostgreSQL transaction-scoped advisory lock inside the same transaction as the change it records.
A trigger rejects UPDATE/DELETE/TRUNCATE. `GET /audit/verify` and `drikr-api verify-audit` recompute
the chain. **This is tamper evidence, not tamper prevention**: a database superuser can disable the
trigger and rewrite the whole chain consistently. Mitigation: record the head hash outside the
database (backups write `*.audit.json`; operators should copy it to separate storage).

---

## ADR-009 Deployment: Docker Compose, offline-capable

**Status:** Accepted

Three services: `db` (postgres:17 alpine), `api` (Python 3.12 slim, non-root, read-only root FS) and
`web` (unprivileged nginx serving the static build and reverse-proxying `/api`). Only `web`
publishes a port, bound to 127.0.0.1 by default; `db` and `api` sit on an internal network. No
runtime internet access is required: fonts are bundled (`@fontsource/inter`), the API serves no
CDN-backed documentation UI, and there is no telemetry. Offline installation uses `docker save` /
`docker load` image archives (see `docs/operations/offline-deployment.md`).

---

## ADR-010 Frontend stack and component approach

**Status:** Accepted

React 18 + TypeScript (strict) + Vite, Tailwind CSS with design tokens as CSS variables, shadcn/ui
*patterns* (Radix primitives with Tailwind classes, owned in `src/components/ui`), Apache ECharts
(tree-shaken, SVG renderer), React Router 6, Zod for client-side form validation mirroring the
Python contract (drift is caught by `src/contracts/scenario.test.ts`). Native `<select>` elements are
used instead of custom listboxes for robustness and accessibility. Three.js and ECharts are split
into separately loaded chunks.

---

## ADR-011 Determinism across platforms

**Status:** Accepted with limitation

Random numbers come from a documented SplitMix64 generator with SHA-256-derived named streams
(`drikr_simcore.rng`), not Python's `random`, so a C# port can reproduce them (reference outputs are
in `tests/unit/test_simcore.py`). Outputs are rounded (0.1 m, 0.01 quality) before hashing to absorb
last-bit floating-point differences in `math.sin/cos`. Digests treat `-0.0` as `0.0`, because
PostgreSQL JSONB cannot store negative zero (defect D-03, 2026-10-18). A golden digest test pins the timeline of a
demo scenario. **Limitation:** bit-identical reproduction is verified on Windows (CPython 3.12.4) and
in the Linux API container (see `docs/SPRINT_STATUS.md` for the evidence); other platforms are
expected but not verified. Any intentional change to generation logic must bump `ENGINE_VERSION`.

## ADR-012 Per-attempt variation and an adaptive adversary, planned at session creation

**Status:** Accepted (2026-10-17). Mechanism tested; effect on learning untested.

**Context.** SIH26247 asks for an *AI-enabled* trainer with scenario randomisation that prevents
rote learning. Until now every attempt at a scenario used the scenario's seed, so a trainee
repeating an assignment met the identical exercise. ADR-001 requires the server to generate each
session's whole timeline in advance, so that every session is reproducible from its record.

**Decision.**
* **Per-attempt seeds.** Each attempt's seed is derived from the scenario seed, the trainee, the
  assignment (or practice scenario) and the attempt number (`session_service.attempt_seed`), and
  stored with the session. New assignments vary by default; instructors can require identical
  attempts (`vary_seed: false`), a scenario with `allow_seed_override: false` keeps its seed, and a
  trainee's permitted custom seed is used as given. Assignments created before migration `0006` keep
  identical attempts.
* **Adaptive adversary** (`drikr_simcore.adversary`, opt-in per assignment). Before generation, the
  server scores four tactics (low-and-slow approach, fast run-in, saturation, larger swarm) against
  the trainee's last 10 scored results. A tactic needs at least 4 relevant tracks and an error
  measure of at least 34%, and at most two are used. Each only narrows the instructor's ranges for
  non-cooperative drone groups. The adapted scenario becomes the session's effective definition, and
  the plan, with its evidence and reasons, is stored in `training_sessions.adversary_plan` and shown
  with the result, never during the exercise.
* This is game-AI tactics selection, **not machine learning**, and it is described that way.

**Why at session creation, not during the exercise.** Reacting to the trainee mid-exercise would
make the timeline depend on live input. That is the condition ADR-001 names for reconsidering server
authority. Planning between sessions keeps one engine, one stored timeline and exact verification.

**Consequences.** Attempts are no longer "identical exercises" by default, so comparisons between
attempts show `same_scenario` rather than `identical` unless the instructor asked for identical
attempts. Five existing tests whose purpose is identical inputs now request identical attempts
explicitly, and one test helper now waits for the first track instead of assuming the old seed. Not
done: within-exercise reactions (evasion when engaged); learned models; evidence that adversarial
planning improves learning, which needs the human study.

**Revisit when** a learning study shows that within-exercise adaptation is needed, or trainees'
weaknesses need richer evidence than stored results provide.

## ADR-013 Optional VR: a sand-table view in the Unity client (OpenXR)

**Status:** Accepted with limitation (2026-10-17): built and tested without a headset; **not tested
on VR hardware**.

**Context.** SIH26247 asks for a "desktop or VR-capable simulator". The Unity client is desktop
only, and its control panel is IMGUI, which does not render inside a headset.

**Decision.**
* OpenXR through XR Plugin Management (packages bundled with Unity 6000.3: `com.unity.xr.openxr`
  1.16.1, `com.unity.xr.management` 4.6.1). The loader is **not** initialised at startup; VR starts
  only with `-drikrVr` (`VrSession`), and without a headset or OpenXR runtime the client says so and
  stays on the desktop. Profiles enabled: Khronos simple, Oculus Touch, Valve Index, HTC Vive
  (`Drikr.EditorTools.XrSetup`).
* **Sand table:** the whole 4 km picture is scaled to a 1 m-radius table at waist height in front
  of the trainee (`VrControls.TableScale`), with a floor-level tracking origin. This keeps tracks
  readable and avoids moving through kilometres of space.
* **Controls:** right hand: point at a track and pull the trigger to select it; A changes the
  classification and B submits it. Left hand: the trigger chooses the training response (continue
  monitoring, request sensor confirmation, report to exercise control, log as cleared) and X sends
  it to the selected tracks. A text panel above the table shows the selection, both choices and
  what was recorded. The desktop panel stays mirrored on the monitor for an instructor.
* **Server authority is unchanged (ADR-001):** VR adds input and presentation only. Every decision
  is the same API call as from the desktop panel.

**Consequences.** `activeInputHandler` is set to "Both", because the OpenXR plugin brings the Input
System, while the client keeps the legacy input API. The Windows player grows from about 91 MB to
96 MB. **VR is in the Windows x64 player only:** the OpenXR plugin supports only Windows x64 among
this project's players, and its build validation rejects the universal macOS player. Because XR
settings are shared by all standalone targets, `BuildScript` builds Linux and macOS with the OpenXR
loader removed and restores it afterwards (`XrSetup.ForBuild`). It also switches the editor's active
build target before each build, because OpenXR's checks read the active target. Without a runtime
installed, the OpenXR plugin logs `XR_ERROR_RUNTIME_UNAVAILABLE` lines at
startup while it queries extensions; it never creates an instance or session unless `-drikrVr` is
given. **Not done:** testing on any headset; VR in the Linux and macOS players.

