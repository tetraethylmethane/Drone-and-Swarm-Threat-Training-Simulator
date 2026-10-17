# Differentiators: requirements to tests

Every proposed differentiator, with the evidence that tests it. **Result** is what was observed,
on the date given. "Not run" means no evidence exists yet. Unit, integration and reproducibility
tests run on the development machine (Windows 11, CPython 3.12.4, PostgreSQL 17.5). Deployment
checks use the Docker Compose stack (Linux containers, CPython 3.12.14, PostgreSQL 17.11).
The full requirement-level traceability for the original brief is in
`docs/testing/traceability-matrix.md`.

## A. Evidence-driven training

| ID | User problem | Hypothesis | Implementation | Acceptance test | Metric | Environment | Result | Limitations |
|---|---|---|---|---|---|---|---|---|
| R-A1 | Instructors cannot tell what a score is based on | Every assessed item cites the recorded events behind it | `evidence_events` in each result item (`scoring-1.2.0`); AAR "Evidence" column | `test_traceability.py::test_every_item_points_to_recorded_events`; reproducibility suite (every reference resolves) | References that resolve to a stored event of the stated type: must be 100% | Integration (PostgreSQL) | Pass, 2026-10-16 | Results scored before 1.2.0 show "Not recorded for this engine version" |
| R-A2 | Old scores could silently change when the engine changes | Stored results keep their rubric and engine versions; never rewritten | Immutable result rows; verification compares the assessment across versions | `test_older_engine_result_still_verifies_when_scores_agree`, `…_with_a_different_score_is_flagged` | Changed score detected; stored result unchanged | Integration | Pass, 2026-10-16 | Byte-identical output is only expected within the same engine version |
| R-A3 | Trainees and instructors cannot see which competencies improve or which errors recur | Trends and recurrence computed from persisted results, with the rule stated | `/analytics/competency`; Competency panel on My progress and Analytics | `test_competency.py` (3 tests); web `analytics.test.tsx` | Every value traceable to a scored session; trainees see only their own | Integration, component | Pass, 2026-10-16 | Simple rule (first vs last 3 sessions, 5-point threshold); mixes scenarios unless filtered |
| R-A4 | Do instructors act on the evidence? | Evidence shortens debrief preparation | n/a | Usability study task "explain this trainee's score" | Task success and time | Representative instructors | **Not run** | No users yet |

## B. Reproducible assessment

| ID | User problem | Hypothesis | Implementation | Acceptance test | Metric | Environment | Result | Limitations |
|---|---|---|---|---|---|---|---|---|
| R-B1 | Re-running an exercise must give the same exercise | Same scenario version, seed and difficulty give an identical event sequence | Deterministic engine (`simcore-1.0.0`) | `tests/reproducibility`: all 4 demo scenarios × every allowed level × 2 seeds; fresh interpreters with different hash seeds | Identical digests and event sequences | Unit | 40 of 40 pass, 2026-10-16 | Logical sequence only; client-side rendering frames are not replayed |
| R-B2 | Same across machines | Digests are identical across operating systems and Python patch versions | Canonical JSON digests | Golden digests compared on Windows/CPython 3.12.4 and Linux/CPython 3.12.14 | All 4 equal | Dev machine and Docker | Equal, 2026-10-16 | Two platforms only |
| R-B3 | Scoring must not depend on storage order or reruns | Same events always give the same result | Engine sorts by sequence | `test_scoring_is_deterministic_and_order_independent` | Identical result digests | Unit | Pass | — |
| R-B4 | Administrators need assurance across many sessions | A bulk check finds any session that no longer reproduces, with the reason | `/admin/reproducibility`, `drikr-api reproducibility-report`, System health panel | `test_reproducibility_report.py` (tampered log detected as "stored log changed") | Detection of the change: 1 of 1 | Integration | Pass | Checks the latest N sessions (default 50) |
| R-B5 | Live deployment check | Real stored sessions reproduce after an engine upgrade | As above | `drikr-api reproducibility-report --limit 50` in the API container | Reproducible / checked | Docker stack, 2026-10-16 | **22 of 22** (all scored by `scoring-1.1.0`, same assessment under 1.2.0) | 22 sessions from development use |
| R-B6 | Comparing attempts is error-prone | The system states whether two attempts are the identical exercise and compares only what is comparable | `/analytics/compare`; Compare page; links from the AAR | `test_competency.py::test_compare_*`; component test | Track view only for identical exercises | Integration, component | Pass | — |

## C. Useful adaptive training

| ID | User problem | Hypothesis | Implementation | Acceptance test | Metric | Environment | Result | Limitations |
|---|---|---|---|---|---|---|---|---|
| R-C1 | Difficulty must stay within instructor limits | Changes never exceed bounds, move at most one level, and always have a reason | `adaptive.py`; `difficulty_adjustments` table | Unit tests; `test_adaptive_difficulty_records_reasons`; synthetic validation E5 | Violations | Unit, integration, synthetic | 0 violations in 960 synthetic recommendations | — |
| R-C2 | Difficulty should follow competence | Improving trainees move up promptly | Same | Synthetic validation E5 | Sessions until promotion | Synthetic agents | **Lags**: the improving agent is promoted only near session 11; steady mid-skill agents drift down | Needs retuning (backlog P1-3); then a human pilot |

## D. Low-friction deployment

| ID | User problem | Hypothesis | Implementation | Acceptance test | Metric | Environment | Result | Limitations |
|---|---|---|---|---|---|---|---|---|
| R-D1 | No internet at training sites | Full workflow runs without external services | Docker Compose, bundled assets, no telemetry | Offline check (network isolation, full session, AAR, export) | External requests | Docker stack | Pass (recorded 2026-10-14) | Not repeated on target hardware |
| R-D2 | Hardware may be modest | Small footprint; capacity known | — | `scripts/measure-performance.py`; `docker stats`; `tests/load/run.sh`, `tests/load/memory.sh` (k6) | Memory, latency, errors, consistency at N trainees | One laptop (see positioning.md, load-resilience-report.md) | Idle: API 140 MiB, DB 38 MiB, web 14 MiB. Load: 30 trainees within the latency criteria in 4 of 5 runs; 60 without errors; memory about 0.9 GiB after load (A7 not met) | One machine; **target hardware not measured** (B-10) |
| R-D3 | Recovery after failure | Data survives restarts; backups restore | `backup.sh`, `verify-backup.sh`, `restore.sh` | Backup, restore into a scratch database, restart all containers | Records before and after; chain validity | Docker stack, 2026-10-16 | Backup restored at revision 0003, 134 audit events, chain valid; restart ready in 10 s with records unchanged | Full restore over the live database not repeated today (scratch restore only) |
| R-D4 | Clients without special hardware | Browser and desktop clients on common operating systems | Web app; Unity players | E2E (Chromium); Windows smoke test; Linux smoke test in Docker | Pass/fail | Windows, Ubuntu container | Pass | macOS player built but **not run** |

## E. Instructor-centred usability

| ID | User problem | Hypothesis | Implementation | Acceptance test | Metric | Environment | Result | Limitations |
|---|---|---|---|---|---|---|---|---|
| R-E1 | Instructors have little time | Create, assign, review and export an exercise without help | Scenario editor, assignments, AAR, exports | Structured usability test: 5 to 8 representative instructors, 5 tasks, think-aloud | Task completion, errors, time, SUS score | Representative workstation | **Not run** | Requires participants |
| R-E2 | Workflow must work end to end | Full instructor and trainee workflow | — | E2E `full-workflow.spec.ts` and others (21 tests) | Pass/fail | Chromium | Pass (2026-10-15) | Automation is not usability |
| R-E3 | Accessibility | No serious axe violations on key pages; screen-reader path in the Unity client | — | E2E axe; `scripts/unity-a11y-check.ps1` | Violations; task completion through UI Automation | Chromium; Windows UI Automation | Pass | No sessions with assistive-technology users |

## F. Trustworthy records

| ID | User problem | Hypothesis | Implementation | Acceptance test | Metric | Environment | Result | Limitations |
|---|---|---|---|---|---|---|---|---|
| R-F1 | Only the right people see and change records | Backend RBAC on every endpoint | `rbac.py`, `require()` | `test_role_matrix`; tests for the new endpoints (403s and 404s) | Unauthorised access | Integration | Pass | — |
| R-F2 | Edits to records must be detectable | Audit chain and verification detect tampering | Hash chain; verification | `test_tampering_is_detected`; R-B4 | Detection | Integration | Pass | Tamper-*evident*: a superuser can rewrite consistently (documented residual risk) |
| R-F3 | Units and organisation data must be valid and audited | Unit changes validated and audited | `users.unit` with CHECK constraint; `user.updated` audit | `test_units.py` | Blank values rejected by the database; change audited | Integration | Pass | — |

## G. Training effectiveness (all differentiators)

| ID | User problem | Hypothesis | Implementation | Acceptance test | Metric | Environment | Result | Limitations |
|---|---|---|---|---|---|---|---|---|
| R-G1 | Does training improve recognition decisions? | Structured training improves scores on unseen scenarios more than practice alone | Study protocol, pseudonymised export | Randomised pilot, then the main study | Adjusted post-test difference (ANCOVA) | Real trainees, with consent | **Not run** | Synthetic validation shows only that the measurement behaves sensibly |
