# System overview

## Purpose and boundary

A software-only training, assessment and simulation platform in which authorised trainees practise
recognising and classifying **virtual** drone and swarm activity from **synthetic** sensor
observations, choose **predefined training responses**, and review their performance.

Out of scope by design (brief §2): control of real equipment, connection to operational or
surveillance systems, real-world interception guidance, operational engagement recommendations,
autonomous targeting, and use of classified or restricted data. The four training responses
(*continue monitoring*, *request sensor confirmation*, *report to exercise control*, *log as cleared*)
are procedural reporting steps inside the virtual exercise only.

## Components

```
                ┌──────────────────────────── browser ───────────────────────────┐
                │ React app: trainee workflow · instructor tools · AAR · admin    │
                │ Browser simulation adapter (R3F 3D view / SVG plan view)        │
                └───────────────┬─────────────────────────────────────────────────┘
                                │ HTTPS, same origin (/api/v1)
                ┌───────────────▼──────────────┐
                │ nginx (web container)        │  static assets, CSP, reverse proxy
                └───────────────┬──────────────┘
                                │ internal network
                ┌───────────────▼──────────────────────────────────────────────┐
                │ FastAPI (api container)                                       │
                │  routers ─ auth · users · catalog · assignments · sessions ·  │
                │            reviews · analytics · reports · admin              │
                │  services ─ session clock · scoring · adaptive · reports      │
                │  imports:  drikr_simcore   drikr_scoring   drikr_contracts    │
                └───────────────┬──────────────────────────────────────────────┘
                                │ SQLAlchemy / psycopg
                ┌───────────────▼──────────────┐
                │ PostgreSQL 17 (db container) │
                └──────────────────────────────┘
```

| Package | Responsibility | Depends on |
|---|---|---|
| `packages/contracts` (`drikr_contracts`) | Versioned Pydantic schemas: scenario, events, trainee actions. Exports JSON Schema to `packages/contracts/schemas`. | pydantic |
| `packages/simcore` (`drikr_simcore`) | Deterministic logical simulation: entity motion, synthetic sensors, scripted events, validation, procedural generation, sensor confirmation, ground-truth index. No I/O. | contracts |
| `packages/scoring` (`drikr_scoring`) | Rubric schema, decision-tree evaluation, scoring, rules-based adaptive difficulty. No I/O. | contracts, simcore |
| `apps/api` (`drikr_api`) | HTTP API, authentication, RBAC, persistence, session lifecycle and clock, audit, reports, CLI. | all packages |
| `apps/web` | User interface and browser simulation adapter. | API contract |
| `apps/simulator` | Unity 6 Windows visual client: 3D environment, track rendering, trainee decisions. Presentation only. | API contract |
| `database/migrations` | Alembic migrations (schema, constraints, audit trigger). | apps/api models |

## Data flow of an exercise

1. **Author.** An instructor saves a scenario version. Validation runs twice: structural/cross-field
   rules (Pydantic) and a seeded test generation (entities must be observable, objectives assessable).
2. **Assign.** An assignment binds a trainee to an exact scenario version with permitted options,
   difficulty mode and bounds, attempt limit and feedback level.
3. **Launch.** The trainee creates a session. The backend applies the permitted selections,
   determines the difficulty level (fixed or adaptive), generates the full timeline and stores it
   (typically 1–8 k events) with its digest.
4. **Run.** The client polls the feed; the server releases only trainee-visible events whose
   `available_at_ms` has passed on the server clock. Actions are validated (session running, tracks
   visible) and time-stamped by the server. *Request sensor confirmation* adds a deterministic
   `sensor_confirmation` event 4 s later.
5. **Complete.** On completion (trainee, time limit or sweeper) the scoring engine runs over the
   stored events and the session's rubric version; the result and an adaptive-difficulty
   recommendation (with reason) are stored in the same transaction.
6. **Review.** The AAR reads only persisted records: result, event timeline, review notes. The
   verify action regenerates the timeline and re-scores to demonstrate reproducibility. Exports are
   produced from the same records and audited.

## Key properties and where they are tested

| Property | Mechanism | Evidence |
|---|---|---|
| Reproducible scenarios | Seeded named RNG streams, canonical digests, golden digest | `tests/unit/test_simcore.py`, `test_session_flow.py::test_reproducibility_verification` |
| Trainee never sees ground truth live | Visibility filter in feed, briefing serializer | `test_session_flow.py`, `test_rbac.py` |
| Scores traceable to events | Input digest, rubric digest, verify endpoint | `test_scoring.py`, `test_session_flow.py` |
| Backend-enforced permissions | `require()` + object-level checks | `test_rbac.py` (role matrix) |
| No lost results on interruption | Server clock, idempotent actions/complete, unique score per session | `test_session_flow.py` |
| Tamper evidence | Hash chain + trigger | `test_audit_and_constraints.py` |

## Known architectural limitations

* Unity builds need an activated Unity licence: CI (`.github/workflows/unity.yml`) runs only once licence secrets or a licensed self-hosted runner are configured. macOS builds are unsigned and untested on a Mac; Linux has no screen-reader support in Unity.
* Single API instance assumed: login rate limiting and the action limiter are in-process.
* Polling feed (ADR-003) is adequate for one trainee per session; not designed for large
  observer audiences.
* Positional fusion is not modelled: each simulated sensor reports independently and tracks are
  associated by the generator (documented simplification for training purposes).
