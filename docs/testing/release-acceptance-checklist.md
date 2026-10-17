# Release acceptance checklist (Sprint 10)

Release under review: the **uncommitted working tree of 2026-10-16/17** (1.0.0-rc4 plus the Sprint 10 changes; no new release tag has been assigned).
Every line gives one status and its evidence.

Status key: **Accepted** (tested; criterion met) · **Partially verified** (tested, but with a stated
gap) · **Not met** (tested; criterion failed) · **Blocked** (cannot be done in this environment;
blocker named) · **Planned** (not started).

**Overall decision: not ready for operational training use.** It is ready as a release candidate
for a supervised pilot on the target hardware, once the P1 items in
`known-limitations-and-backlog.md` are accepted or resolved by the deploying organisation.
Nothing here is a certification, accreditation or "military-grade" claim.

## 1. Definition of done (Sprint 10 brief)

| # | Requirement | Status | Evidence |
|---|---|---|---|
| D1 | The *Perimeter basics* defect is fixed and regression-tested | **Accepted** (synthetic evidence) | perimeter-basics-report.md: ICC 0.846–0.871 for v2 against 0.721–0.785 for v1 (5 samples); the repeated-run test (8 runs, 4 interrupted) passes |
| D2 | The authoritative simulation's reproducibility guarantees are documented and tested | **Accepted** | ADR-001 (re-verified 2026-10-16); reproducibility-report.md; tests in the reproducibility suite pass; stored-data reports reproduce 100% (section 3) |
| D3 | Load and recovery behaviour measured against explicit criteria | **Partially verified** | load-resilience-report.md: criteria fixed before the runs. On one laptop: latency criteria met in 4 of 5 design-load runs (little headroom); A3, A5, A6 and A8 met (955 of 955 sessions reproduce; API kill, database outage and an unplanned host restart recovered); **A7 memory not met** (levels off at about 0.9 GiB, not returned when idle). Not measured on deployment hardware (B-10) |
| D4 | Security findings triaged; no unresolved critical issue concealed | **Accepted** | security-findings.md: F-01 (High) and F-02, F-03, F-04 (Medium) fixed with tests; F-09 (Low) open with remediation; no Critical findings; residual risks R1–R9 recorded. Internal review only (R8) |
| D5 | Instructor usability evaluated honestly; outstanding work recorded | **Blocked** (participants and approval) | instructor-usability-protocol.md: protocol complete; developer walkthrough only; U-01 fixed with tests; no participant data |
| D6 | Adaptive difficulty evaluated honestly | **Partially verified** | adaptive-difficulty.md: criteria fixed in advance; C1–C3 met; **C4 and C5 not met by any candidate**; tests pass |
| D7 | Human training study completed or marked pending with a protocol | **Blocked**, marked pending | training-effectiveness-study-protocol.md §10: no participants; ethics approval not sought |
| D8 | Competitor unknowns stay unknown until supported by evidence | **Accepted** | competitive-evidence.md (verification table with sources and confidence); competitor-landscape.md (only two cells changed, both to "Partially documented") |
| D9 | The application still works: server authority, Unity visualisation, persistent records, existing architecture | **Accepted** (with the stated gaps) | Python 328 + 1 passed, Vitest 40, E2E 24 passed; Unity EditMode 18 passed, including a full exercise over the adapter protocol against the final server. Unity HTTPS live test not run (section 2) |

## 2. Test execution on the final code

| Suite | Result | Notes |
|---|---|---|
| Python unit, reproducibility, integration (`pytest`, PostgreSQL 17.5) | **328 passed, 0 failed, 0 skipped** (2026-10-17, 361 s, final code) | Plus `test_dev_scripts.py` (D-01), added after that run: 1 passed |
| Ruff lint and format; mypy strict (67 files) | Clean | 2026-10-16, final code |
| Web: ESLint, Prettier, `tsc`, Vitest, production build | **Clean; 40 passed** (7 files), 2026-10-17 | |
| E2E (Playwright 1.63, Chromium, dev stack) | **24 passed, 1 skipped** (opt-in screenshot capture), 2026-10-17 | The first run failed one test (stale v1 label, fixed); the counts are from the complete re-run |
| Unity EditMode (6000.3.26f1, batch mode) | **18 passed, 0 failed, 1 skipped**, 2026-10-17 | The live protocol test ran against the isolated load-test stack (final image). The skipped test, `LiveHttpsWithPinnedCa`, would create a session in the operator's main deployment, so it was not enabled; the offline certificate-pinning tests passed |
| Load acceptance (30 ×2, 60, resilience) | A1–A6, A8 met | load-resilience-report.md section 5 |
| Dependency audits; gitleaks | Clean (gitleaks re-run 2026-10-17 over all 169 uncommitted files) | security-findings.md 3.1 |
| Trivy image scan (0.66.0) | **0** fixable HIGH/CRITICAL in the API and web images that were load-tested | postgres image not scanned (O12) |
| Backup → verify → restore with the least-privilege role | **Verified** 2026-10-17 | security-findings.md 3.3 |

## 3. Data integrity

| Check | Status | Evidence |
|---|---|---|
| Identical inputs give identical events and scores | Accepted | reproducibility suite; golden digests |
| Records immutable through every API route and at database level | Accepted | `test_integrity.py`; `test_db_role.py` |
| Interrupted sessions recover; restart recovery | Accepted | `test_integrity.py`; resilience run; unplanned host restart (load report 5.6) |
| Every stored load-test session reproduces | Accepted: **955 of 955** | load report 5.7 |

## 4. Release notes items (for the operator)

- **Upgrade:** set `DRIKR_MIGRATION_DATABASE_URL` (owner) and `DRIKR_DATABASE_URL`
  (`drikr_app`, with its own password); the API provisions the role at every start. Migration
  `0004` adds the immutability triggers.
- *Perimeter basics* v2 is published as a **new version** on `seed-demo`. Sessions on v1 keep v1.
  Do not pool v1 and v2 scores in comparisons.
- Adaptive policy default changed to robust demotion; installations with a saved custom policy also
  get it (adaptive-difficulty.md, upgrade note).
- Capacity has been measured on a development laptop only. Measure the target host before a class
  uses it (B-10).
