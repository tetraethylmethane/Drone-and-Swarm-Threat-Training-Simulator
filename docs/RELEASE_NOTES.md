# Release notes — 1.0.0-rc4 (2026-10-16)

Release candidate of the Drikr Systems drone and swarm threat training simulator.
Component versions: API 1.0.0, contracts 1.0.0, simulation engine `simcore-1.0.0`,
scoring engine `scoring-1.2.0`, database schema revision `0003`.

## What works end to end (automatically tested)

An instructor creates or selects a valid scenario, assigns it to a trainee; the trainee completes the
exercise in the browser; every event is recorded; the scoring engine produces a reproducible result;
the AAR shows the stored result; the instructor reviews it, verifies reproducibility and exports CSV
and PDF. The trainee step can be done in the browser or in the Unity desktop client (Windows, Linux, macOS); both are
tested against the same deployment. The browser path is covered by
`tests/e2e/specs/full-workflow.spec.ts` (dev stack and Docker deployment); the Unity path by the
Unity live protocol test and the built-player smoke test (Docker deployment over HTTPS).

New in rc4: traceable assessments (evidence events per scored item), reproducibility suite and
bulk reports, verification across scoring-engine versions, competency tracking with recurring
errors, attempt comparison, unit-level reporting, measured performance on System health, and the
research and product documents in `docs/research/` and `docs/product/`.

New in rc3: multi-factor authentication, HTTPS for network access, a data-retention workflow,
learning-gain analytics with a pseudonymised research export, the official Drikr logo, and
upgraded build and test tooling with no open advisories.

## Known limitations

| Area | Limitation |
|---|---|
| Simulation | The authoritative simulation is a deterministic Python engine on the server. The Unity 6 client (Windows x64, Linux x86_64, macOS universal) and the browser view are presentation-only clients (ADR-001). The Unity client shows the overall result; the full AAR is in the web app. Unity CI (`.github/workflows/unity.yml`) needs Unity licence secrets or a licensed self-hosted runner and has not run on GitHub yet (no remote). The macOS player is unsigned and has not been run on a Mac. Kinematics and sensor models are simplified synthetic training models with no physical validation. Tracks are associated by the generator (no fusion or tracker modelling). |
| VR | Not implemented (optional future extension: a Unity XR client can use the same adapter protocol). |
| Deployment | HTTPS is opt-in (`docker-compose.tls.yml`); the default file serves plain HTTP on `127.0.0.1`. Certificates from the bundled script come from a private CA that must be distributed to workstations; renewal is manual. Single API instance assumed (in-process rate limits). |
| Security | MFA uses TOTP, which is not phishing-resistant (no FIDO2/WebAuthn). Rotating `DRIKR_SECRET_KEY` invalidates enrolled MFA secrets. Tamper evidence, not prevention, for the audit log (see `docs/security`). Not certified or accredited by any body. |
| Data | The audit log is never deleted and keeps usernames and IP addresses after anonymisation; backups keep data until rotated (`docs/security/data-retention.md`). |
| Accessibility | Automated axe checks (WCAG 2 A/AA) and keyboard checks on key pages pass; the 3D canvas is not screen-reader accessible (the track table and plan view are the accessible equivalents). The Unity panel is exposed to screen readers: verified on Windows through UI Automation (a full exercise without pointer input); VoiceOver support is present in the macOS player but untested; Unity offers none on Linux. No manual screen-reader session with users has been performed. |
| Browsers | E2E tests run on Chromium only. |
| Evaluation | **No study with people has been conducted.** The assessment was validated only with synthetic trainees of known skill. Scores rank skill well, but the short Perimeter basics scenario is not reliable for judging an individual from one session, and the adaptive policy lags improving learners (`docs/research/assessment-validation.md`). Whether training improves human performance is untested; `docs/research/training-effectiveness-study-protocol.md` describes the controlled study required. |
| Brand | Official logo and mark are used. Interface colours are this product's own tokens; no official colour or typography guidelines were supplied. |

## Upgrade notes

From rc3: back up, load the new images and start them. The API applies migration `0003` (optional
`unit` per user). Existing data is kept, and stored results keep their scoring-engine version
(verified on 2026-10-16: 22 of 22 sessions reproduced afterwards).

From rc1 or rc2: as above. Migrations `0002` and `0003` are applied in order, and existing data is
kept (`0002` verified on 2026-10-15). After upgrading from rc1 or rc2:

1. Administrators must use MFA by default: each administrator is asked to set it up at the next
   sign-in. Change this under **Settings** if needed.
2. No data is deleted until an administrator sets a retention period.
3. For network access, follow the HTTPS steps in `docs/operations/offline-deployment.md`.
