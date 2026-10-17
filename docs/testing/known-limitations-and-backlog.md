# Known limitations and remediation backlog (Sprint 10)

Last updated 2026-10-16. This consolidates what is **not** done or not proven at the end of
Sprint 10. Each item names its source, so it can be traced to evidence. The longer-standing open
items O1–O13 remain in `docs/SPRINT_STATUS.md`; the items below add to them or refine them.

Priority: **P1** must be resolved, or explicitly accepted by the deploying organisation, before
operational training use; **P2** should be resolved in the next sprint; **P3** improvement.

## 1. Known limitations

| Area | Limitation | Consequence | Source |
|---|---|---|---|
| Evidence base | All reliability, adaptive-policy and load evidence comes from **synthetic agents and one development laptop** | No claim about trainees, learning or deployed capacity can be made | Every Sprint 10 report |
| Training effectiveness | **No human study has been run**; ethics approval has not been sought | It is unknown whether the simulator improves training | study protocol §10 |
| Usability | **No instructor has taken part** in the usability test; only a developer walkthrough exists | Usability is unproven | usability protocol §6–7 |
| Assessment reliability | *Perimeter basics* v2 reaches ICC 0.85–0.87 on synthetic agents; human reliability is unknown, and a narrower cohort will show lower values | Judge individuals on several sessions | perimeter-basics-report.md |
| Adaptive difficulty | Improving trainees are not promoted within 10 sessions under any tested policy (C4); "single outlier" criterion C5 not met as measured | Instructors should review adaptive assignments and use the override | adaptive-difficulty.md |
| Determinism | Logical equivalence, not bit-for-bit; verified on Windows/CPython 3.12.4 and Linux/CPython 3.12.14 only | Other platforms expected but unverified | reproducibility-report.md §4 |
| Capacity | One API process; no admission control; capacity measured on one laptop only (30 trainees within the latency criteria in 4 of 5 runs, with little headroom; 60 without errors but slow) | Overload slows every trainee and biases timing scores | load-resilience-report.md |
| Security assurance | Internal review only; no penetration test or formal risk assessment; not certified or accredited | No assurance claim may be made | security-findings.md R8 |
| Tamper evidence | A database superuser can rewrite records consistently; the application can delete raw logs and mark them purged (F-09) | Keep audit head hashes off-host | security-findings.md R2, R9 |
| Competitors | Verification used public pages only, with no demonstrations or brochures; most `Unknown` cells stay unknown | Differentiation claims rest partly on absence of public evidence | competitive-evidence.md |

## 2. Backlog

| ID | Item | Priority | Remediation and acceptance | Source |
|---|---|---|---|---|
| B-01 | **Admission control**: refuse new sessions above a configured number of running sessions, with a clear message | P2 | Configurable cap; integration test; a load run above the cap shows no degradation for admitted trainees | O-L2 |
| B-02 | **Server-delay bias in timing scores** | P2 | Record client receive and send times as untrusted AAR evidence and flag sessions whose server delay exceeds a threshold; or rely on B-01 | O-L1 |
| B-03 | **API memory is retained after load** (A7 not met: 116 MiB fresh → 709 → 859 → 887 MiB over three runs; not returned when idle) | P2 | An 8-hour soak test at the design load with per-process memory; if it keeps growing, find the source (tracemalloc in a test build); if it levels off, cap it (for example `MALLOC_ARENA_MAX`, or periodic restart of the generation workers) and re-test A7 | load report 5.3 |
| B-04 | **Purge cross-check** (F-09) | P2 | The reproducibility report flags purged sessions not covered by a recorded retention run; or move purging into an owner-defined `SECURITY DEFINER` function and revoke DELETE on `session_events` from the app role; regression test | security-findings.md F-09 |
| B-05 | **Adaptive promotion lag** | P2 | Candidate rules (for example promotion on the median with a per-score floor) evaluated against C1–C5 unchanged; then confirmed with trainee data | adaptive-difficulty.md §4 |
| B-06 | Evidence column shows event ids; link each to the timeline | P3 | Clickable evidence ids; component test | usability U-02 |
| B-07 | Sort the sessions list by score | P3 | Sortable column; component test | usability U-03 |
| B-08 | **Run the instructor usability test** with 5–8 instructors | P1 | Protocol as written; results reported against the pre-set acceptance criteria; fixes with regression tests | usability protocol |
| B-09 | **Ethics approval and human pilot** | P1 | Approval, then the pilot as protocolled; no effectiveness claim before the report | study protocol |
| B-10 | **Load test on representative deployment hardware**; set minimum and recommended requirements | P1 | `tests/load/run.sh` on the target host; criteria as in load report §2.3 | roadmap 10.6 |
| B-11 | Size `cpu_workers` on target hardware (the 1-vs-4 comparison was not measured; worker memory was: 46–47 MiB each, stable) | P3 | Compare 1, 2 and 4 on the target host | load report 5.3, 5.5 |
| B-12 | Untested failure modes: full disk; long nginx↔API partition; a *controlled* power-loss test (an unplanned host restart during a run recovered correctly, load report 5.6) | P2 | Resilience runs with recorded outcomes | load report 5.4, 5.6 |
| B-13 | Keep raw load-test results immutable (the L-01 reproduction output was deleted while resetting the stack) | P3 | `run.sh` writes to a new timestamped folder per run and never deletes results | L-01 |
| B-14 | Independent penetration test and formal risk assessment | P1 (before any assurance claim) | Deploying organisation | R8 |
| B-15 | Competitor demonstrations and brochures for the unresolved `Unknown` cells | P3 | Evidence register updated with dated sources | competitive-evidence.md |
| B-16 | Execute CI on GitHub, including Trivy and gitleaks (O2), and the Unity workflow (O1) | P2 | Recorded CI runs | SPRINT_STATUS O1, O2 |

## 3. Defects closed in Sprint 10

| ID | Defect | Fix | Regression test |
|---|---|---|---|
| Perimeter basics | One session was not a reliable measure (ICC < 0.80) | Scenario version 2 | `tests/reproducibility/test_perimeter_basics.py`, `tests/integration/test_perimeter_basics.py` |
| Seeding | A changed demo was never published to existing installations | `seed-demo` publishes a new version | `test_seeding_publishes_a_changed_demo_as_a_new_version` |
| F-01 | API connected as the database owner | Least-privilege role | `test_db_role.py` |
| F-02 | Events and scores editable in the database | Migration `0004` triggers | `test_integrity.py::test_database_refuses_edits_to_records` |
| F-03 | Route authentication coverage was a hand-written list | Every OpenAPI operation tested | `test_route_security.py` |
| L-01 | Connection-pool exhaustion at 10 trainees | COPY and pool sizing | `test_session_creation_load.py` |
| L-02 | Feed starvation and forced pauses at a synchronised start | Generation in worker processes; column reads | `test_session_creation_load.py`; load acceptance runs |
| L-03 | Load harness over-reported inconsistencies | Count only accepted classifications | Acceptance runs (0) |
| U-01 | Instructors could not see or override adaptive changes in the UI | Difficulty page | `AssignmentDifficulty.test.tsx`, `test_adaptive_override.py` |
| Adaptive | One poor session could lower the level | Robust (median) demotion | `test_adaptive_retune.py`, `test_session_flow.py::test_adaptive_difficulty_records_reasons` |
| Tests | Two contract tests depended on the demo's entity order and silently stopped testing rejection after v2 | Entities located by meaning | `test_contracts.py::test_invalid_scenarios_are_rejected` |
| D-01 | **Regression from F-01:** `scripts/dev-api.sh` failed to migrate on any machine with a deployment `.env`. Migrations now use the owner URL, which `Settings` read from `.env` (Docker host `db`), and the script set only `DRIKR_DATABASE_URL`. Found on 2026-10-17 when starting the dev stack for E2E | The script also sets `DRIKR_MIGRATION_DATABASE_URL` | `tests/unit/test_dev_scripts.py` (fails before the fix) |
| E2E | The full-workflow E2E test selected "Perimeter Awareness Basics (v1)"; after v2 the form lists only the latest version, and the test waited until it timed out. It would also have failed in CI | Select Perimeter basics at its current version, asserting exactly one match | `tests/e2e/specs/full-workflow.spec.ts` (24 passed after the fix) |
