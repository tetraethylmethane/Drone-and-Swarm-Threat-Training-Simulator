# Changelog

All notable changes to this project are documented here. Versions follow semantic versioning.
Engine versions are tracked separately because they affect reproducibility.

## [1.0.0-rc5] - 2026-10-19

Sprint 10 and the work after it. **Not ready for operational use:** the instructor usability study,
the human study, the load test on the deployment server and the independent security assessment
remain open (`docs/operations/operational-readiness.md`).

### Added
- Each attempt is a different, recorded and reproducible exercise (per-attempt seeds); instructors
  can require identical attempts. Existing assignments keep identical attempts (migration `0006`).
- Adaptive adversary (opt-in per assignment, ADR-012): rules-based tactics chosen from the trainee's
  recorded weaknesses, stored with the session and shown in the AAR. Not machine learning. A
  synthetic evaluation (1,680 sessions) found it targets clear weaknesses but only measurably
  exposes bird confusion (B-24).
- Optional OpenXR VR view in the Windows x64 player (`-drikrVr`, ADR-013), including training
  responses on the left controller. **Not tested on a headset.**
- Admission control (`DRIKR_MAX_ACTIVE_SESSIONS`); set it below measured capacity.
- Pre-generated first attempts when an assignment is created (`DRIKR_TIMELINE_CACHE_MB`): 30
  simultaneous starts went from 7.3–10.5 s to 3.9–7.1 s (p95) on the test laptop.
- Recorded, owner-defined purges of raw event logs (migration `0005`); least-privilege API database
  role and immutability triggers (migration `0004`).
- Load, soak and class-start test harnesses (`tests/load`), reports for reproducibility, load and
  resilience, security findings, threat model, and the operational readiness guide.

### Fixed
- D-03: about 1 seed in 15 produced a valid session that verification reported as not
  reproducible (`-0.0` stored as `0.0` by PostgreSQL); digests now treat them alike.
- D-02: every attempt replayed the identical exercise.
- Connection-pool exhaustion (L-01), feed starvation during generation (L-02), and refused sessions
  doing generation work (L-05).

### Security
- Web image: `libexpat` CVE-2026-77214 (HIGH) is fixed by rebuilding without the build cache;
  release images must be built with `docker compose build --no-cache --pull`. Existing
  `drikr-web:1.0.0` images need a rebuild.

### Known limitations
- A clean 8-hour soak has not been measured: two attempts were cut short (Docker failure; laptop
  standby) after about 4 hours each, with no leak seen in either. Accepted by the project owner for
  this release candidate (2026-10-19).
- Measured on one development laptop only; minimum hardware is not established.

### Changed
- Database schema revision `0006`.

## [1.0.0-rc4] - 2026-10-16

### Added
- Traceable assessments: every scored item lists the recorded events it rests on (scoring engine
  `scoring-1.2.0`), shown as an Evidence column in the AAR.
- Verification across scoring-engine versions compares the assessment (scores, outcomes, error
  counts). Stored results are never rewritten.
- Reproducibility suite (`tests/reproducibility`, 40 tests), bulk reproducibility report
  (`/admin/reproducibility`, `drikr-api reproducibility-report`, System health).
- Competency tracking (trends, recurring errors with evidence, identical-exercise groups) on
  My progress and Analytics; a Compare attempts page linked from the AAR.
- Units: optional `unit` per user (migration `0003`), a unit filter, and a unit summary in Analytics.
- Measured request performance on System health; `scripts/measure-performance.py`.
- Research and product documents: competitor landscape and evidence register, research and reuse,
  positioning, differentiation roadmap, requirements-to-tests.

### Changed
- Database schema revision `0003`.

## [1.0.0-rc3] - 2026-10-15

### Added
- In-app help for trainees: a first-visit welcome, a **How to play** guide page (steps, plain-language
  meaning of every classification and response, reading the Tracks table, scoring tips), a live
  **Next step** bar during exercises, and an explanation of the chosen classification in the
  Decision panel.
- Unity client for Linux (x86_64) and macOS (universal) in addition to Windows; `BuildLinux`,
  `BuildMacOS` and `BuildAll`; a Linux smoke test in Docker (`scripts/unity-linux-smoke.sh`).
- Unity CI workflow (`.github/workflows/unity.yml`): EditMode tests and players for all three
  platforms through GameCI with licence secrets, or on a licensed self-hosted runner; skipped with a
  notice when neither is configured.
- Screen-reader support in the Unity panel (Unity accessibility API; Narrator/NVDA/JAWS through UI
  Automation, VoiceOver on macOS), announcements, `-drikrScreenReader`, and a UI Automation check
  (`scripts/unity-a11y-check.ps1`).
- Multi-factor authentication: TOTP authenticator apps (QR code or key), ten single-use recovery
  codes, two-step sign-in for cookie and bearer clients, roles that must use MFA (administrators by
  default), administrator and command-line resets (`drikr-api reset-mfa`). Secrets are encrypted at rest.
- HTTPS for network access: `docker-compose.tls.yml`, an nginx TLS template (TLS 1.2/1.3, HSTS, HTTP
  redirect) and `scripts/generate-tls-cert.sh` for a private training-network CA.
- Data retention: administrator policy for exercise event logs, expired sign-in records and
  anonymisation of deactivated accounts; preview, audited runs and run history;
  `drikr-api retention-run` for schedules; anonymisation of individual accounts. The AAR explains
  removed event logs, and verification still works after a purge.
- Training-effectiveness evidence: learning-gain analytics (first versus latest attempt, with
  bootstrap interval, effect size and sign test), a pseudonymised research export
  (`/reports/study.csv`), a simulation-based validation of the assessment with synthetic trainees
  (`research/assessment_validation`), and a protocol for a controlled human study.
- Unity client: MFA sign-in step, optional pinned CA (`-drikrCa`) for HTTPS, official logo and
  application icon.

### Changed
- Official Drikr Systems logo and mark (from the Drikr NIDAR ground station) replace the
  provisional wordmark and favicon in the web app, PDF reports and Unity client.
- Toolchain: Vite 8, Vitest 5, Tailwind CSS 4 (CSS-first `@theme` configuration), jsdom 30,
  Playwright 1.63; Node.js 22.22 or later is required for development (web image builds on 22.23.3).
  `npm audit` reports no vulnerabilities, including development dependencies.
- Database schema revision `0002` (`0002_mfa_and_data_retention`).
- The account page is now **Account and security**.

## [1.0.0-rc2] - 2026-10-15

### Added
- Unity 6 (6000.3.26f1) Windows client `apps/simulator/DrikrUnityClient`: a presentation-only visual
  adapter with a procedural 3D tactical scene, track rendering with trails and selection, an IMGUI
  decision panel using the design tokens, idempotent action submission, a batch-mode build script,
  EditMode tests (track picture, JSON Schema agreement, live protocol) and an opt-in smoke mode for
  the built player.

### Changed
- ADR-001 revised: Unity is the 3D visual environment; simulation authority stays on the server.
- System health reports both visual clients.

## [1.0.0-rc1] - 2026-10-14

First release candidate.

### Added
- Versioned contracts for scenarios, simulation events and trainee actions, with exported JSON Schema.
- Deterministic simulation core `simcore-1.0.0`: seeded entity motion (transit, loiter, orbit, hover,
  erratic), coordinated swarms (line, wedge, cluster), synthetic radar/optical/RF sensor models with
  configurable quality, scripted degradation, visibility changes and messages, radar clutter, five
  difficulty levels, sensor confirmation requests, two-layer validation and procedural generation.
- Scoring engine with versioned rubrics, a configurable decision tree, six dimensions with explained
  credits, and rules-based adaptive difficulty with recorded reasons.
- FastAPI backend: authentication (Argon2id, server-side sessions, CSRF, lockout, rate limiting),
  role-based authorisation, immutable scenario and rubric versioning, assignments, a
  server-authoritative exercise clock with connection-loss handling, idempotent actions,
  after-action review data, analytics, CSV/PDF exports, a tamper-evident audit log, administrator
  settings and system health, and an operational CLI.
- PostgreSQL schema with integrity constraints and an append-only audit trigger (migration 0001).
- React web application for trainees, instructors and administrators, including a browser
  simulation adapter with 3D and plan views.
- Four demonstration scenarios and one demonstration rubric, clearly marked as demo content.
- Docker Compose deployment, backup, verify and restore scripts, and a CI workflow.
- Unit, integration, component and end-to-end tests; architecture, security, operations and user
  documentation.

### Changed
- Scoring engine `scoring-1.0.0` → `scoring-1.1.0`: explanation text now uses readable names
  (for example "small multirotor" instead of `small_multirotor`). Numeric scoring is unchanged.
  Results stored by 1.0.0 are kept as recorded; verification reports the version difference.
- Upgraded FastAPI 0.115.6 → 0.143.1 and Starlette → 1.8.0, React Router 6.28 → 7.18.4,
  ECharts 5.5 → 6.1, pytest 8.3 → 9.1.1 and several build-tool versions, to resolve published
  security advisories found by `pip-audit` and `npm audit`.

### Known limitations
See `docs/RELEASE_NOTES.md`.
