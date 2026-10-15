# Architecture decision records

Status values: **Accepted** (implemented and tested), **Accepted with limitation**, **Deferred**.

---

## ADR-001 Simulation authority on the server; Unity and browser as visual clients

**Status:** Accepted (revised 2026-10-15 when Unity 6000.3.26f1 became available)

**Context.** The brief prefers Unity (C#) as the authoritative 3D simulation engine and also
requires simulation state and scoring to be separate from presentation, reproducible from seeds,
and testable without launching Unity. It forbids running a second full simulation alongside
Unity. The first build environment had no Unity; it was later found installed with Windows
standalone support and a working licence in batch mode.

**Decision.**

* The authoritative *logical* simulation remains `packages/simcore` (`drikr_simcore`): a
  deterministic, pure-Python engine that expands a scenario, seed and difficulty into the complete
  event timeline. The server stores it and releases trainee-visible events on its own clock.
* **Unity is the 3D visual environment** (`apps/simulator/DrikrUnityClient`, Unity 6; Windows x64, Linux x86_64, macOS universal):
  virtual environment, drone representations, environmental look, event playback and the trainee's
  decision controls. It implements the documented adapter protocol and holds no authoritative state.
* The browser adapter (`apps/web/src/features/exercise`) is a second visual client using the same
  protocol, used where installing a desktop client is not wanted.

**Why Unity is not the authoritative engine.** Making Unity authoritative would put timing and
ground truth on the trainee's machine, where they are not tamper-resistant. It would also require
Unity to run for every scoring, verification and test, and would duplicate the engine the backend
needs for validation and reproducibility checks. Server authority gives one engine, one timeline,
one score, whichever client is used. Bit-identical reproduction has been verified across Windows
and Linux (ADR-011).

**Consequences.** Logic, event schema, scoring and persistence are tested without Unity. The Unity
client is tested separately (EditMode unit and contract tests, a live protocol test, and a smoke
test of the built player). Visual fidelity is that of a flat tactical display, not physical flight
simulation. Unity builds need a licensed workstation and are not part of GitHub CI.

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
last-bit floating-point differences in `math.sin/cos`. A golden digest test pins the timeline of a
demo scenario. **Limitation:** bit-identical reproduction is verified on Windows (CPython 3.12.4) and
in the Linux API container (see `docs/SPRINT_STATUS.md` for the evidence); other platforms are
expected but not verified. Any intentional change to generation logic must bump `ENGINE_VERSION`.
