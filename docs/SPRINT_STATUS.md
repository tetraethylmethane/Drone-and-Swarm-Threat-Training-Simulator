# Sprint status

Last updated 2026-10-15. This release was built in a single continuous development pass. The
eight-sprint structure from the brief is used below to report what each sprint's checklist covers
and the evidence for it. The sprints were not separate two-week calendar iterations.

**Environment used for verification:** Windows 11 (10.0.26200), Intel 12 logical CPUs, Python
3.12.4, Node 22.23.3 (portable, checksum-verified), PostgreSQL 17.5 (project-local cluster), Docker 27.3.1 (Linux containers:
Python 3.12.14, PostgreSQL 17.11, nginx 1.30.4 since 2026-10-15; earlier runs: Python 3.12.7, PostgreSQL 17.2, nginx 1.27). Unity 6000.3.26f1 with Windows standalone support was
located on 2026-10-15 (initially not found on `PATH`) and used for the Unity client.

## Test results (latest runs, 2026-10-15, release candidate 3)

| Suite | Result |
|---|---|
| Python unit + integration (`pytest`) | **222 passed**, 0 failed (180 s). New: TOTP and secret sealing (9, including the RFC 6238 test vectors), statistics (5), MFA (8), retention (6), study export and learning gains (2) |
| Ruff lint and format (packages, API, tests, migrations, research), mypy strict (62 files) | Clean |
| Web unit and component (Vitest 5) | **30 passed** (4 files; new: two-step sign-in, MFA enrolment, route guard, purged AAR timeline) |
| ESLint, Prettier, `tsc` strict, production build (Vite 8, Tailwind 4) | Clean |
| E2E (Playwright 1.63, Chromium) against the dev stack | **20 passed**, 1 skipped (opt-in screenshot capture, run separately: pass). Includes real administrator MFA enrolment, a rejected wrong code and code-based sign-ins |
| E2E against the Docker Compose deployment | Last run for rc2 (19 passed after rerun); **not repeated for rc3**. The rc3 Docker images were rebuilt and checked by the HTTPS checks and the Unity smoke test below |
| HTTPS (`docker-compose.tls.yml`, manual checks) | HTTP→HTTPS redirect; TLS 1.1 refused; TLS 1.2 (ECDHE-RSA-AES256-GCM) and 1.3 negotiated; HSTS and CSP present; untrusted CA and wrong host name rejected; `Secure` cookies on sign-in |
| Unity EditMode tests (batch mode, Unity 6000.3.26f1) | **19 passed**, including live protocol over HTTP (dev API) and over HTTPS with a pinned CA (Docker), rejection without the CA, and accessibility bookkeeping |
| Unity player builds (`BuildAll`) | Windows x64 (~91 MB), Linux x86_64 (~87 MB), macOS universal x86_64 + arm64 (~109 MB): all succeeded, 0 errors, 0 warnings |
| Linux player smoke test (Ubuntu 24.04 container, Xvfb, HTTPS with pinned CA) | Pass (`docs/design/screens/15-unity-client-linux.png`) |
| macOS player | Bundle, `Info.plist` (macOS 12+), icon and universal binary checked; **not run** (no Mac available); unsigned |
| Unity screen-reader check (Windows UI Automation, `scripts/unity-a11y-check.ps1`) | Pass: 16 steps, sign-in by focus and typing, full exercise by activation only, password exposed only as a length |
| Unity CI workflow | `actionlint` clean; **not run on GitHub** (no remote; needs Unity licence secrets or a licensed self-hosted runner) |
| Built-player smoke test over HTTPS (`-drikrCa`) against Docker | Pass (exit 0), official logo rendered (`docs/design/screens/14-unity-client.png`) |
| Database upgrade 0001 → 0002 | Up/down/up cycle and `alembic check` clean; Docker database with existing data upgraded in place |
| Assessment validation (synthetic) | 3,132 scored sessions; two full runs gave identical results (`docs/research/assessment-validation.md`) |
| `pip-audit` | No known vulnerabilities (local packages not on PyPI are skipped) |
| `npm audit` (web, **including dev tooling**) | **0 vulnerabilities** after Vite 8, Vitest 5, Tailwind 4, jsdom 30 and `@types/node` 22.20.4 |
| `npm audit` (E2E tooling) | **0 vulnerabilities** after Playwright 1.48.2 → 1.63.0 (advisory GHSA-7mvr-c777-76hp) and axe-core/playwright 4.13.0 |
| Trivy image scan (HIGH/CRITICAL, fixed only) | First CI run found 52 (API, Debian 12.8) and 38 (web, Alpine 3.20) OS-package findings from 2024 base images. Fixed by moving to python 3.12.14-slim-bookworm, nginx-unprivileged 1.30.4 (Alpine 3.24) and postgres 17.11, plus OS security updates at build time: **0 findings** in both images (Trivy 0.66.0 locally). The upstream postgres image still reports Go standard-library CVEs in its bundled `gosu` binary (not scanned in CI; tracked as O12) |
| gitleaks | Clean on the committed tree (one false positive, a C# property name, allow-listed) |

## Sprint 1 — Architecture and foundation: complete

- [x] Fresh checkout configurable from documented instructions (`README.md`, `offline-deployment.md`)
- [x] All services build (`docker compose build`: api, web; db image pulled)
- [x] Backend health check (`/health`, `/health/ready` with migration revision)
- [x] Database connection (dev cluster and container)
- [x] Environment variables validated (`test_invalid_configuration_rejected`)
- [x] Secrets not committed (`.env`, `backups/` git-ignored, verified with `git check-ignore`; gitleaks configured)
- [~] Linting and type-checking in CI: configured, **CI not yet run**
- [x] ADRs and known limitations documented

Decisions: ADR-001 to ADR-011. The repository was greenfield: no prior code, tests or brand assets.

## Sprint 2 — Identity, database and core APIs: complete

- [x] Authentication success/failure (`test_auth.py`)
- [x] Unauthorized requests rejected (401 matrix)
- [x] Role restrictions enforced by the backend (`test_role_matrix`, 22 endpoints × 3 roles)
- [x] Structured errors for invalid input
- [x] Database constraints reject invalid records (`test_database_rejects_invalid_records`, `test_event_and_score_constraints`)
- [x] Migrations on a clean database (fixtures recreate the schema each run; CI cycle)
- [x] Audit records for privileged actions
- [x] Passwords and secrets absent from logs, audit details and storage (`test_passwords_hashed_and_never_logged`)

## Sprint 3 — Scenario configuration and event engine: complete

- [x] Valid scenarios pass; invalid configurations rejected with paths
- [x] Identical version, configuration and seed reproduce the same logical sequence (unit, API `verify`, **cross-platform: all four demo digests identical on Windows/CPython 3.12.4 and Linux/CPython 3.12.7, re-checked on Linux/CPython 3.12.14 on 2026-10-15**)
- [x] Different seeds give valid variations
- [x] Event timestamps follow the tick rules
- [x] Version changes do not overwrite historical sessions (`test_versioning_never_overwrites_history`)
- [x] Synthetic data labelled (`synthetic: true`, UI notices)
- [x] Generation works without connectivity (`test_generation_needs_no_network`)

## Sprint 4 — 3D simulation and trainee workflow: complete

- [x] Unity project (`apps/simulator/DrikrUnityClient`, Unity 6): virtual environment, drone representations, playback of the session feed, environment look by terrain and time of day, decision controls; built for Windows x64 in batch mode. Presentation only; the server keeps simulation authority (ADR-001, revised)
- [x] Simulation-to-backend adapter in C# (`DrikrApi.cs`), tested live against the API
- [x] Browser adapter: R3F 3D view and SVG plan view, both projected from trainee-visible events only
- [x] Scenarios launch and terminate correctly
- [x] Timing follows the documented model (`test_timing_model_pause_resume_and_tick_quantisation`)
- [x] Pause and resume consistent
- [x] Event log agrees with displayed state (UI is a pure projection of feed events; `trackPicture.test.ts`)
- [x] Missing and delayed observations handled (`track_lost`, latency, degradation tests)
- [x] Reconnecting does not duplicate results (idempotency and concurrency test)
- [x] Invalid transitions rejected
- [x] Basic exercise completed start to finish (E2E)

Defect found and fixed: the exercise page initially fell back to the plan view because the feed
state did not carry the briefing (found in screenshot review). The 3D fog initially hid the scene
in low visibility; it was changed to presentation-only haze.

## Sprint 5 — Scoring and adaptive assessment: complete

- [x] Deterministic for identical inputs (input order independent)
- [x] Boundary conditions (timing boundaries, insufficient data, no free points)
- [x] Explanations match computed results
- [x] Historical scores keep their rubric version and engine version
- [x] Adaptive difficulty respects bounds (500-case property test, integration)
- [x] Every adaptive evaluation recorded with a reason (database CHECK + tests)
- [x] Rules-based only; no optional model exists

Change: scoring engine bumped to `scoring-1.1.0` (explanation wording only); `verify` reports engine-version differences.

## Sprint 6 — AAR dashboard and reporting: complete

- [x] Dashboard values match persisted results (API and E2E compare displayed overall to stored value)
- [x] Empty states do not invent data
- [x] Filters return correct records (trainee, scenario, objective, date)
- [x] Charts show units and labels (axis names, units footnote); layout overlap fixed after screenshot review
- [x] Reports respect permissions (CSV staff only; PDF own and detailed only for trainees)
- [x] Exports match selected filters
- [x] Long sessions usable (timeline pagination tested on a 7.2 k-event session)
- [x] Loading, error and retry states (component tests)

## Sprint 7 — Security, resilience and integration: complete except CI-only scans

- [x] Full trainee workflow passes automatically
- [x] Full instructor workflow passes automatically
- [x] Role isolation, input validation and authorisation tests pass
- [x] **Backup restored and verified (2026-10-14, Docker stack):** `scripts/backup.sh` → `scripts/verify-backup.sh` (checksum OK, schema `0001`, 4 users, 10 scenarios, 4 sessions, 4 results, audit chain valid over 96 events, head hash matched) → `scripts/restore.sh --yes` after inserting a post-backup user: user removed, sessions restored, chain valid with the same head hash, API ready
- [x] Interrupted sessions recover per documented rules
- [x] **No required runtime internet connection:** the API container has no route to the internet (connection to `1.1.1.1:443` fails, DNS fails) yet the full workflow passes; the browser makes no request outside the app origin (`offline.spec.ts`); no telemetry SDK or exporter installed (`test_offline.py`)
- [~] Dependency scans complete locally (pip-audit, npm audit); **secret and image scans configured but not executed**
- [x] Keyboard navigation and focus visibility verified (E2E); axe WCAG 2 A/AA: no serious or critical violations on seven key pages (two contrast failures found and fixed)
- [x] No critical known issue ignored without a documented decision (dev-tool advisories: decision O6)

Container hardening verified: API runs as uid 10001, web as uid 101, read-only root FS confirmed.

### Performance baseline (measured, not targets)

Same Windows host, local API (uvicorn, single worker), quiet machine:

| Operation | Median | p95 |
|---|---|---|
| Timeline generation (1.2 k–2 k events / 7.2 k-event swarm scenario) | 92–181 ms / 793 ms | — |
| `POST /sessions` (generate and store ~1.6–2 k events) | 617 ms | — |
| `GET /sessions/{id}/feed` incremental / full | 25.6 ms / 25.4 ms | 39.4 ms / 31.8 ms |
| `POST /sessions/{id}/actions` | 27.6 ms | 34.2 ms |
| `POST /complete` (scoring, ~1.6 k events) | 130 ms | — |
| `GET /analytics/progress` | 22.6 ms | 26.5 ms |
| `GET /sessions/{id}/timeline` (500 events) | 32.7 ms | 40.1 ms |
| PDF report | 64.2 ms | 75.1 ms |
| Sign-in (Argon2id, intentionally costly) | 727 ms | — |

Earlier measurements taken while Docker builds ran were 3–5× slower and are discarded. Targets must
be set on the intended deployment hardware.

## Sprint 8 — Acceptance, documentation and release: release candidate

- [x] Fresh environment deploys with the documented procedure (Compose build + up + seed, verified)
- [x] Migrations complete successfully
- [x] Every core workflow works without manual database edits
- [x] Randomisation and reproducibility tests pass
- [x] Scores and AAR results traceable to source events (digests, verify)
- [x] Backup and restore demonstrated
- [x] Offline operation demonstrated (see Sprint 7)
- [x] No broken navigation or non-functional primary controls found (E2E plus screenshot review of 12 screens)
- [x] No unresolved critical test failure (the one Docker-run E2E failure was a tooling artifact and passed on rerun)
- [x] Release documentation matches the implementation (reviewed against code on 2026-10-14)

## Release candidate 3 — follow-up requests: complete

| Request | Delivered | Evidence |
|---|---|---|
| Clear dev-tool advisories | Vite 8.3.2, Vitest 5.0.3, Tailwind 4.3.3 (CSS-first config), jsdom 30.1.1, Playwright 1.63.0; web image on Node 22.23.3 | `npm audit` 0 in web and E2E; all suites above; screenshots re-captured with no visual regressions found on review |
| Official brand | Logo and mark from the Drikr NIDAR ground station, unchanged originals with checksums | `docs/design/brand-and-design-system.md`, screenshots |
| TLS | Compose override, nginx template, certificate script, Unity CA pinning | HTTPS checks and Unity tests above |
| Multi-factor authentication | TOTP with encrypted secrets, recovery codes, role policy, resets, UI, Unity sign-in step | Python, web, E2E and Unity tests above |
| Data retention | Policy, preview, audited runs, CLI, anonymisation | `test_retention.py`, `docs/security/data-retention.md` |
| Whether the training works | Learning-gain analytics and pseudonymised export (observational); synthetic validation of the assessment; human study protocol | `docs/research/`. **No human study has been run**, so effectiveness remains unknown |

Findings from the synthetic validation that need decisions (not changed in this release):
- the Perimeter basics scenario is unreliable for individual decisions (ICC 0.62);
- the adaptive policy lags improving trainees and lets steady mid-skill trainees drift down;
- the objectives and procedure dimensions rest on few items.

## Open items

| ID | Item |
|---|---|
| O1 | Unity: run `.github/workflows/unity.yml` once a remote and licence secrets (or a self-hosted runner) exist; sign and notarise the macOS app and test it on a Mac; manual screen-reader sessions; full AAR inside Unity; VR |
| O2 | Execute the CI workflow on GitHub (no remote configured); confirm Trivy and gitleaks results |
| O3 | ~~TLS and MFA~~ done in rc3. Remaining: phishing-resistant MFA (WebAuthn) if required; automated certificate renewal |
| O4 | Run the human pilot and controlled study (`docs/research/training-effectiveness-study-protocol.md`); usability study |
| O5 | ~~Data retention~~ done in rc3. Remaining: organisation's retention schedule and DPIA |
| O6 | ~~Dev tooling upgrades~~ done in rc3. TypeScript 7 and ESLint 10 deferred until typescript-eslint and jsx-a11y support them |
| O7 | ~~Official logo~~ done in rc3. Remaining: official colour and typography guidelines, if they exist |
| O8 | Cross-browser E2E (Firefox, WebKit) and manual screen-reader audit |
| O9 | Move the repository out of OneDrive for development: sync locking slows npm and caused one E2E artifact failure |
| O10 | Replace `httpx` with the client Starlette now recommends for its TestClient (deprecation warning in tests) |
| O12 | Postgres image: Go stdlib CVEs reported in the upstream image's `gosu` helper; track upstream or build a derived image |
| O11 | Review the adaptive-policy thresholds and the Perimeter basics scenario using the synthetic-validation findings |
