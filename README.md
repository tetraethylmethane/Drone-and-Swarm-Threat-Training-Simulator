# Drikr Systems — Drone and Swarm Threat Training Simulator

A software-only, offline-capable training and assessment platform. Trainees observe **synthetic**
sensor pictures of virtual drones and swarms, classify tracks under uncertainty, choose predefined
procedural training responses and review their performance. Instructors author versioned scenarios
and rubrics, assign exercises, review sessions and export reports. Administrators manage users,
settings, the audit log and system health.

> Training use only. The system controls no real equipment, connects to no operational system and
> provides no real-world engagement guidance. All tracks, readings and events are synthetic.

## Status

Release candidate `1.0.0-rc2`. What is implemented, tested and still open is listed in
[`docs/SPRINT_STATUS.md`](docs/SPRINT_STATUS.md) and [`docs/RELEASE_NOTES.md`](docs/RELEASE_NOTES.md).
The authoritative simulation is a deterministic Python engine on the server. Two visual clients
use the same adapter protocol: a **Unity 6 desktop client** for Windows, Linux and macOS (`apps/simulator`) and the browser
exercise view (ADR-001).

## Architecture

| Path | Contents |
|---|---|
| `packages/contracts` | Versioned Pydantic contracts and exported JSON Schemas |
| `packages/simcore` | Deterministic logical simulation, validation and demo scenarios |
| `packages/scoring` | Rubrics, decision-tree scoring and adaptive difficulty |
| `apps/api` | FastAPI backend, CLI and Dockerfile |
| `apps/web` | React + TypeScript web application, nginx config and Dockerfile |
| `apps/simulator` | Unity 6 Windows visual client (presentation only) |
| `database/migrations` | Alembic migrations |
| `tests/unit`, `tests/integration`, `tests/e2e` | Test suites |
| `docs/` | Architecture, security, operations, testing, design, guides and research |

See [`docs/architecture/system-overview.md`](docs/architecture/system-overview.md) and
[`docs/architecture/architecture-decisions.md`](docs/architecture/architecture-decisions.md).

## Quick start (Docker)

Prerequisites: Docker Engine with Compose v2.

```bash
cp .env.example .env                       # replace every CHANGE value (see comments in the file)
docker compose up -d --build
docker compose exec api drikr-api create-admin --username admin
docker compose exec api drikr-api seed-demo   # optional: demonstration rubric and scenarios
```

Open <http://localhost:8080>; the first administrator sign-in sets up multi-factor authentication.
For other machines on a training network, use HTTPS:

```bash
bash scripts/generate-tls-cert.sh --host <name> --ip <address>
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d
```

Offline installation, TLS and updates:
[`docs/operations/offline-deployment.md`](docs/operations/offline-deployment.md).
Backups: [`docs/operations/backup-and-recovery.md`](docs/operations/backup-and-recovery.md).

## Development

Prerequisites: Python 3.12, Node.js 22.22 or later (the test toolchain needs it), PostgreSQL 17 (or Docker).

```bash
py -3.12 -m venv .venv          # Linux/macOS: python3.12 -m venv .venv
.venv/Scripts/pip install -e packages/contracts -e packages/simcore -e packages/scoring -e "apps/api[dev]"
./scripts/local-postgres.ps1 init; ./scripts/local-postgres.ps1 start   # Windows: isolated dev cluster on :55432
bash scripts/dev-api.sh                                                  # API on 127.0.0.1:8000
cd apps/web && npm ci && npm run dev                                     # UI on 127.0.0.1:5173
```

For demo users in development: `DRIKR_DEMO_PASSWORD='<policy-compliant>' drikr-api seed-demo --with-demo-users`
(users `admin`, `instructor`, `trainee1`, `trainee2`).

### Checks

```bash
ruff check packages apps/api tests database research && ruff format --check packages apps/api tests database research
mypy packages/contracts/drikr_contracts packages/simcore/drikr_simcore packages/scoring/drikr_scoring apps/api/drikr_api
pytest                                       # needs TEST_DATABASE_URL or the local dev cluster
cd apps/web && npm run lint && npm run typecheck && npm test && npm run build
cd tests/e2e && npx playwright test          # with the stack running
```

## Documentation

* Guides: [trainee](docs/guides/user-guide.md), [instructor](docs/guides/instructor-guide.md),
  [administrator](docs/guides/administrator-guide.md)
* Architecture: [overview](docs/architecture/system-overview.md), [decisions](docs/architecture/architecture-decisions.md),
  [data model](docs/architecture/data-model.md), [API and adapter protocol](docs/architecture/api-contracts.md),
  [scoring model](docs/architecture/scoring-model.md)
* Security: [threat model](docs/security/threat-model.md), [controls](docs/security/security-controls.md),
  [data retention](docs/security/data-retention.md)
* Research: [assessment validation with synthetic trainees](docs/research/assessment-validation.md),
  [training-effectiveness study protocol](docs/research/training-effectiveness-study-protocol.md)
* Testing: [strategy](docs/testing/test-strategy.md), [traceability](docs/testing/traceability-matrix.md)
* Design: [brand and design system](docs/design/brand-and-design-system.md), [screens](docs/design/screens)
* [Research review](docs/research-review.md) · [Third-party notices](THIRD_PARTY_NOTICES.md) · [Changelog](CHANGELOG.md)

## Brand note

The Drikr Systems logo and mark are the official artwork from the Drikr NIDAR ground-station
project, kept unchanged in `assets/brand/source/` with checksums. Interface colours are this
product's own design tokens. See the design-system document.

## What has and has not been shown

The scoring has been checked with synthetic trainees of known skill: scores rank skill well
(ρ = 0.84 to 0.95), but one short scenario is not reliable enough to judge an individual from one
session. **Whether the training improves human performance has not been tested.** The study protocol
describes the controlled human study needed for that.
