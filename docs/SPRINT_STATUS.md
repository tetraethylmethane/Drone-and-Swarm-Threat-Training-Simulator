# Sprint status

Last updated 2026-10-17 (Sprint 10). This release was built in a single continuous development pass. The
eight-sprint structure from the brief is used below to report what each sprint's checklist covers
and the evidence for it. The sprints were not separate two-week calendar iterations.

**Environment used for verification:** Windows 11 (10.0.26200), Intel 12 logical CPUs, Python
3.12.4, Node 22.23.3 (portable, checksum-verified), PostgreSQL 17.5 (project-local cluster), Docker 27.3.1 (Linux containers:
Python 3.12.14, PostgreSQL 17.11, nginx 1.30.4 since 2026-10-15; earlier runs: Python 3.12.7, PostgreSQL 17.2, nginx 1.27). Unity 6000.3.26f1 with Windows standalone support was
located on 2026-10-15 (initially not found on `PATH`) and used for the Unity client.

## Test results (Sprint 10, final code, 2026-10-17)

All runs on the same Windows 11 laptop, against the uncommitted Sprint 10 working tree (rc4 plus
Sprint 10). Load and resilience tooling: k6 2.3.0 in Docker; Unity 6000.3.26f1.

| Suite | Result |
|---|---|
| Python unit, reproducibility and integration (`pytest`, PostgreSQL 17.5) | **328 passed**, 0 failed, **0 skipped** (361 s). Plus `test_dev_scripts.py` (D-01, added afterwards): 1 passed |
| Ruff lint and format, mypy strict (67 files) | Clean |
| Web: ESLint, Prettier, `tsc`, Vitest 5, production build | Clean; **40 passed** (7 files; new: instructor Difficulty page) |
| E2E (Playwright 1.63, Chromium, dev stack) | **24 passed**, 1 skipped (opt-in screenshots). The first run failed the full-workflow test on a stale "(v1)" scenario label; the test was fixed and the whole suite re-run |
| Unity EditMode (batch mode) | **18 passed**, 0 failed, 1 skipped (`LiveHttpsWithPinnedCa`, not enabled, to avoid writing to the main deployment). The live protocol test ran a full exercise against the final server |
| Load and resilience (k6) | See `docs/testing/load-resilience-report.md`. Design load of 30: latency criteria met in **4 of 5** runs; 0 errors; 0 server-caused pauses; **memory criterion A7 not met**; recovery from an API kill, a database outage and an unplanned host restart |
| Reproducibility of stored data | Load-test database: **955 of 955** sessions reproduce (uncapped report) |
| pip-audit; npm audit (web, E2E) | 0 known vulnerabilities |
| gitleaks 8.30.1 (history; all 169 uncommitted files) | No leaks |
| Trivy 0.66.0 (API and web images as load-tested) | 0 fixable HIGH/CRITICAL |
| Backup → verify → restore with the least-privilege role | Verified (security-findings.md 3.3) |
| Log scan with canary secrets at INFO | No credentials or tokens in API, nginx or audit records (F-07) |

### Previous results (2026-10-16, release candidate 4)

| Suite | Result |
|---|---|
| Python unit, reproducibility and integration (`pytest`) | **272 passed**, 0 failed (227 s). New in rc4: reproducibility suite (40), traceability (3), competency and comparison (3), units (2), reproducibility report and measured performance (2) |
| Ruff lint and format, mypy strict (65 files) | Clean |
| Web unit and component (Vitest 5) | **38 passed** (6 files; new: competency panel, compare page, unit summary) |
| ESLint, Prettier, `tsc` strict, production build | Clean |
| E2E (Playwright 1.63, Chromium), dev stack | **23 passed**, 1 skipped (opt-in screenshot capture; run separately: pass). New: competency on My progress; units, competency, evidence column and compare on Analytics and the AAR |
| Migration `0003` upgrade, downgrade, upgrade and `alembic check` | Clean |
| Docker stack upgraded in place to `0003` | Ready; backup restored into a scratch database at `0003` (134 audit events, chain valid); restart of all containers ready in 10 s with records unchanged |
| Reproducibility on stored data | Docker deployment: **22 of 22** sessions (all scored by `scoring-1.1.0`) reproduce under `scoring-1.2.0`. Dev database: **36 of 36** across `scoring-1.0.0`, `1.1.0` and `1.2.0` |
| Measured exercise (`scripts/measure-performance.py`, HTTPS, one laptop) | Feed median 46 ms (p95 64); decision 37 ms; finish and score 218 ms; PDF 230 ms; sign-in 99 ms (first request 2.2 s including connection setup). Full table in `docs/product/positioning.md` |
| Unity | No Unity changes in rc4; rc3 results below still apply |
| gitleaks on GitHub (gitleaks-action v3, full history) | First rc4 run flagged `verify=args.ca` in `scripts/measure-performance.py` as a "generic API key": a **false positive** (a CA certificate path). Code reworded; the fingerprint is listed in `.gitleaksignore`. Local scans now use gitleaks 8.30.1 (history and tree): no leaks |
| E2E on GitHub | First rc4 run failed: a new test assumed existing scored sessions, which a fresh CI database does not have. Tests restructured to work on an empty database; the evidence check moved into the self-contained full-workflow test |

### Previous results (2026-10-15, release candidate 3)

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

## Sprint 9: Evidence and differentiation (follow-up brief): complete

The full plan, files and acceptance criteria are in `docs/product/differentiation-roadmap.md`. Every
claim is mapped to a test in `docs/product/requirements-to-tests.md`.

| Item | Status | Evidence |
|---|---|---|
| Competitor research (10 companies) and evidence register | Done (public sources, 2026-10-16) | `docs/research/competitor-landscape.md`, `competitive-evidence.md` |
| Repositories and papers re-verified | Done | `docs/research/research-and-reuse.md` |
| Positioning, roadmap, requirements-to-tests | Done | `docs/product/` |
| Traceable assessments (`scoring-1.2.0` evidence events) | Done | `test_traceability.py`; AAR Evidence column |
| Verification across engine versions | Done | Older results verify by assessment; changed scores flagged |
| Reproducibility suite and bulk report | Done | 40 tests; `/admin/reproducibility`; CLI |
| Competency tracking, recurring errors, attempt comparison | Done | `test_competency.py`; component and E2E tests |
| Unit-level reporting | Done | Migration `0003`; `test_units.py` |
| Measured performance and recovery validation | Done (one machine) | System health panel; measurements above |
| Instructor usability test, adaptive retune, Perimeter basics, load test, human pilot | **Proposed** (Sprint 10) | Roadmap |

Architecture note: the follow-up brief lists Unity as the authoritative engine. The project keeps
ADR-001 (authoritative deterministic Python engine, Unity as a presentation client), because the
reproducibility guarantees depend on it. See the roadmap for the reasoning.

## Sprint 10: Reliability, verification and validation (2026-10-16/17)

Work began in one development session and was completed and verified in a second one (the two
coordinated the split of files and runs). The status per workstream follows. The detail is in the
linked reports; known gaps are in `docs/testing/known-limitations-and-backlog.md`; the release
decision is in `docs/testing/release-acceptance-checklist.md` (**not ready for operational use**;
candidate for a supervised pilot).

| Workstream | Status | Evidence |
|---|---|---|
| Architecture: server authority (ADR-001) | **Verified**: no client computes outcomes or scores; the ADR now covers event recording, reconnection, interruption, replay limits and the conditions for reconsidering | ADR-001; `test_integrity.py`; Unity live protocol test |
| A. Perimeter basics | **Fixed and regression-tested** (synthetic evidence). Root cause: too few scored items. Version 2: ICC 0.85–0.87 against 0.72–0.79; repeated-run test of 8 runs, 4 interrupted. The seeding defect that would have kept v2 from existing installations is fixed | perimeter-basics-report.md |
| B. Determinism and data integrity | **Tested**: logical equivalence (not bit-for-bit) documented with tolerances; immutability triggers (`0004`); least-privilege role; duplicate, reconnect, rollback and restart tests | reproducibility-report.md |
| C. Load and resilience | **Measured on one laptop** against criteria fixed beforehand. Defects L-01 (pool exhaustion) and L-02 (feed starvation and forced pauses) fixed; L-03 harness defect fixed. Open: memory retention (B-03), little headroom at 30, no admission control, target hardware (B-10) | load-resilience-report.md |
| D. Security | **Triaged**: F-01 (High) to F-04 fixed with tests; F-09 (Low) open; no Critical; threat model and controls updated; residual risks R1–R9. Internal review, not a certification | security-findings.md, threat-model.md, security-controls.md |
| E. Instructor usability | **Protocol ready; blocked** (participants and approval). Developer walkthrough only; U-01 fixed with tests | instructor-usability-protocol.md |
| F. Adaptive difficulty | **Retuned; partly supported**: robust demotion adopted; C1–C3 met; C4 and C5 not met by any candidate | adaptive-difficulty.md |
| G. Training-effectiveness study | **Pending**: protocol complete; no approval; no participants. No effectiveness claim may be made | training-effectiveness-study-protocol.md §10 |
| H. Competitors | **Public sources verified**; two matrix cells changed; unknowns stay unknown | competitive-evidence.md, competitor-landscape.md, differentiation-roadmap.md |

Defects found and fixed while verifying (each has a regression test): two contract tests that
stopped testing rejection after v2; lint failures in two new test files; D-01 (`dev-api.sh` broken
by the owner-URL change); a stale E2E scenario label. Process lapses recorded honestly: the raw
output of the L-01 reproduction was deleted; two load runs overlapped a Docker failure and were
excluded; one earlier security claim (F-07, "70,000 log lines") could not be reproduced and was
replaced by a new test.

## After Sprint 10: risk reduction toward operational use (2026-10-17)

Requested after the Sprint 10 commit: remove the measured engineering risks, and prepare the four
activities that need people or hardware (`docs/operations/operational-readiness.md`). Operational
readiness still depends on those four activities; nothing below replaces them.

| Item | Status | Evidence |
|---|---|---|
| F-09 / B-04 recorded purges | **Done**: migration `0005`; the app role can no longer delete raw logs or mark them purged; every purge is recorded and verified | `test_purge_integrity.py` (6); migration up/down/up and `alembic check` clean |
| B-01 admission control | **Done; criteria partly met**: exact limit, refusals do no work (defect L-05 found and fixed in two steps). Protects in-exercise latency only when set below measured capacity; the synchronised-start burst remains (B-17) | load report 5.8; `test_admission_control.py` (6) |
| B-03 memory | **No leak over 4 h** (peak 742 MiB at class start, settles at about 295 MiB); 8 h not completed because Docker failed a third time (B-18, B-19) | load report 5.9 |
| B-06 evidence links, B-07 sort by score | **Done** | API and component tests; E2E |
| D-01 `dev-api.sh` | **Fixed** (found while starting the E2E stack) | `test_dev_scripts.py` |

Final runs on this code (2026-10-17): Python **344 passed**, 0 failed, 0 skipped; web **43 passed**;
lint, types and build clean; E2E **24 passed**, 1 skipped (after one discarded run against stale
servers). Not re-run on the final code because Docker was unavailable: Unity live test, gitleaks,
Trivy and the post-soak record checks (B-18).

## SIH26247 alignment (2026-10-17)

Problem statement SIH26247 (Ministry of Defence, via MIC): *AI-Enabled Drone & Counter-Drone Threat
Simulation Trainer*. A review against its expected outcomes found three gaps, now addressed:

| Expected outcome | Before | Now | Evidence |
|---|---|---|---|
| Scenario randomisation to prevent rote learning | **Every attempt replayed the identical exercise** (defect D-02) | Each attempt gets its own recorded seed by default; instructors can require identical attempts | ADR-012; `test_attempt_variation.py` (5) |
| "AI-enabled" | No AI component | **Adaptive adversary**: plans each attempt against the trainee's recorded weaknesses (four tactics, within the instructor's ranges, reasons shown in the AAR). Game-AI tactics selection, **not machine learning** | ADR-012; `test_adversary.py` (10, incl. a property test over every demo scenario); `test_adaptive_adversary.py` (2); `AdversaryPlan.test.tsx` |
| Desktop or VR-capable simulator | Desktop only | **Optional VR sand-table view** in the Windows x64 player (OpenXR, `-drikrVr`) | ADR-013; `VrControlsTests` (4); smoke tests with and without `-drikrVr`. **Not tested on a headset** (B-20) |

The other outcomes were already covered: scripted and procedural scenarios (day, dusk, night;
degraded sensors; rural, urban, industrial, coastal; single drones and swarms), decision-tree
scoring of detection time, classification and response, an AAR with individual and unit tracking
over repeated sessions, and adjustable and adaptive difficulty.

Runs on the final code (2026-10-17): Python **361 passed**, 0 failed, 0 skipped; web **45 passed**;
E2E **24 passed**, 1 skipped; Unity EditMode **22 passed**, 0 failed, 1 skipped; Windows, Linux and
macOS players built with 0 errors.

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
| O13 | Sprint 10 done as recorded above. Remaining P1 items: usability test (B-08), human pilot (B-09), load test on target hardware (B-10), independent security assessment (B-14) |
| O11 | ~~Adaptive thresholds and Perimeter basics~~ done in Sprint 10. Remaining: adaptive promotion lag (B-05) |
