# Test strategy

## Layers

| Layer | Location | Tooling | Runs against |
|---|---|---|---|
| Unit: contracts, simulation, scoring, adaptive | `tests/unit` | pytest | Pure Python, no database |
| Integration: API, PostgreSQL, migrations, transactions, audit, RBAC, reports | `tests/integration` | pytest + FastAPI TestClient | Real PostgreSQL (`TEST_DATABASE_URL`) |
| Frontend unit/component | `apps/web/src/**/*.test.ts(x)` | Vitest, React Testing Library, jsdom | Mocked `fetch` |
| Contract drift | `tests/unit/test_contracts.py::test_exported_json_schemas_are_current`, `apps/web/src/contracts/scenario.test.ts` | pytest, Vitest | Exported JSON Schema |
| End-to-end | `tests/e2e/specs` | Playwright (Chromium), axe-core | Running API + built web app |
| Unity client | `apps/simulator/DrikrUnityClient/Assets/Drikr/Tests/EditMode` | Unity Test Framework (NUnit), batch mode | Track picture, contract agreement with JSON Schema, MFA sign-in, pinned-CA validation, live protocol over HTTP and HTTPS |
| Unity player smoke test | `-drikrSmoke` on the Windows player; `scripts/unity-linux-smoke.sh` (Linux player in Ubuntu with Xvfb) | Built players | Sign in over HTTPS with a pinned CA, practice exercise, render, classify, finish, read result; exit code |
| Unity screen-reader check | `scripts/unity-a11y-check.ps1` | Windows UI Automation against the built player | Roles, names, states; sign-in by focus and typing; full exercise by activation only |
| Unity CI | `.github/workflows/unity.yml` | GameCI (licence secrets) or self-hosted runner | EditMode tests and Windows/Linux/macOS players |
| Reproducibility | `tests/unit/test_simcore.py`, `test_session_flow.py::test_reproducibility_verification` | pytest | Engine and stored sessions |
| Security | `test_auth.py`, `test_rbac.py`, `test_audit_and_constraints.py`, `test_mfa.py`, `test_totp_secretbox.py`, `test_retention.py`, web `security.test.tsx`, E2E security spec (including real MFA enrolment and code sign-in) | pytest, Vitest, Playwright | API and UI |
| Assessment validation | `research/assessment_validation/run_validation.py` | Synthetic agents through the real simulation and scoring engines | Validity, reliability, difficulty, adaptive policy, power (results in `docs/research/assessment-validation.md`) |
| Resilience | `test_session_flow.py` (connection loss, sweeper, idempotency, concurrency), `test_health_config.py` (database down) | pytest | API |
| Accessibility | E2E `security-and-access.spec.ts` (axe WCAG 2 A/AA, keyboard, focus, no monospace) | Playwright + axe | Built UI |
| Static analysis | ruff (incl. bandit rules), ruff format, mypy strict, ESLint (jsx-a11y), Prettier, `tsc --strict` | CI | Source |
| Dependency, secret and image scanning | pip-audit, npm audit, gitleaks, Trivy | CI | Dependencies, history, images |

## Running

```bash
# Python (PostgreSQL required for integration tests; see scripts/local-postgres.ps1)
pytest                                  # unit + integration
pytest tests/unit                       # no database needed

# Web
cd apps/web && npm test && npm run lint && npm run typecheck

# End-to-end (stack running: API on :8000 seeded with demo users, web on :4173)
cd tests/e2e && npm ci && npx playwright install chromium && npx playwright test
CAPTURE_SCREENS=1 npx playwright test screenshots      # refresh docs/design/screens

# Assessment validation (about 5 minutes; --quick for a smoke run)
.venv/Scripts/python research/assessment_validation/run_validation.py
```

E2E and MFA: administrators must use MFA by default, so the E2E helpers enrol the `admin` account
on first sign-in and keep its authenticator secret in the system temp directory
(`drikr-e2e-mfa-admin.json`). Later runs compute codes from it. If the file is lost while the
account still has MFA, run `drikr-api reset-mfa --username admin` against the E2E database.

The integration fixtures reset the test database schema at the start of a run, seed the demo
content once, and restore that baseline before every test.

## Time-dependent behaviour

The exercise clock uses `utcnow()` in `drikr_api.routers.sessions` and
`drikr_api.services.session_service`; integration tests replace it with a `FakeClock`
(`tests/integration/conftest.py`) so pausing, connection loss and time limits are tested without
waiting. E2E tests use the real clock.

## Performance baseline

Measured values (not targets) are recorded in `docs/SPRINT_STATUS.md` with the hardware they were
measured on. Targets must be set after measuring the intended deployment hardware (brief §13).

## Not automated

* Unity camera controls; manual sessions with Narrator, NVDA, JAWS and VoiceOver; running the macOS player.
* Formal usability study and training-effectiveness evaluation with people (protocol in `docs/research/`).
* TLS configuration checks (manual, recorded in `docs/operations/offline-deployment.md`).
* Load testing with many concurrent trainees.
* Cross-browser E2E beyond Chromium.
