# Changelog

All notable changes to this project are documented here. Versions follow semantic versioning.
Engine versions are tracked separately because they affect reproducibility.

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
