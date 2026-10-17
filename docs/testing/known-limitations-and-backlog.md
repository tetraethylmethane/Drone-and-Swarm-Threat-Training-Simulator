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
| Capacity | One API process; capacity measured on one laptop only (30 trainees within the latency criteria in 4 of 5 runs, little headroom; 60 without errors but slow). Admission control caps active exercises, but protects in-exercise latency only when set below measured capacity, and not the synchronised-start burst (load report 5.8) | Overload slows trainees and biases timing scores unless the limit is set with headroom | load-resilience-report.md |
| Security assurance | Internal review only; no penetration test or formal risk assessment; not certified or accredited | No assurance claim may be made | security-findings.md R8 |
| Tamper evidence | A database superuser can rewrite records consistently (R2). The application can no longer delete raw logs silently, but can still purge old ones visibly (R9) | Keep audit head hashes off-host; review `event_log_purges` | security-findings.md R2, R9 |
| Competitors | Verification used public pages only, with no demonstrations or brochures; most `Unknown` cells stay unknown | Differentiation claims rest partly on absence of public evidence | competitive-evidence.md |

## 2. Backlog

| ID | Item | Priority | Remediation and acceptance | Source |
|---|---|---|---|---|
| B-01 | **Admission control** | Done (2026-10-17), criteria partly met | `DRIKR_MAX_ACTIVE_SESSIONS`; exact under concurrency; refusals do no generation work (L-05). Protects in-exercise latency when set with headroom; not at measured capacity, and not the start burst (B-17) | load report 5.8; `test_admission_control.py` (6) |
| B-02 | **Server-delay bias in timing scores** | P2 | Reduced by B-01 when the limit has headroom. Still open: record client receive and send times as untrusted AAR evidence and flag sessions whose server delay exceeded a threshold | O-L1 |
| B-03 | **API memory after load** | Investigated (2026-10-17): **no leak over 4 h** | Soak at 30 trainees: the class-start peak (742 MiB) is released over about 3 h, then memory holds at about 295 MiB; workers stable. The peak is bounded by admission control. Remaining: a full 8-hour day with several class starts, on the target host (B-10) | load report 5.3, 5.9 |
| B-04 | **Purge cross-check** (F-09) | Done (2026-10-17) | Migration `0005`: owner-defined purge functions, append-only purge records, verification of every purge; residual R9 | `test_purge_integrity.py` (6) |
| B-05 | **Adaptive promotion lag** | P2 | Candidate rules (for example promotion on the median with a per-score floor) evaluated against C1–C5 unchanged; then confirmed with trainee data | adaptive-difficulty.md §4 |
| B-06 | Evidence ids link to the timeline | Done (2026-10-17) | Selecting an evidence id opens the Event timeline at the page holding the event (`around_seq`, filtered so hidden events cannot be located) and highlights it | `test_evidence_links.py` (2); `EvidenceLinks.test.tsx` (2) |
| B-07 | Sort the sessions list by score | Done (2026-10-17) | Server-side sort before paging (lowest or highest score; unscored last) and a Sort control | `test_session_sorting.py`; `SessionsSort.test.tsx` |
| B-08 | **Run the instructor usability test** with 5–8 instructors | P1 | Protocol as written; results reported against the pre-set acceptance criteria; fixes with regression tests | usability protocol |
| B-09 | **Ethics approval and human pilot** | P1 | Approval, then the pilot as protocolled; no effectiveness claim before the report | study protocol |
| B-10 | **Load test on representative deployment hardware**; set minimum and recommended requirements | P1 | `tests/load/run.sh` on the target host; criteria as in load report §2.3 | roadmap 10.6 |
| B-11 | Size `cpu_workers` on target hardware (the 1-vs-4 comparison was not measured; worker memory was: 46–47 MiB each, stable) | P3 | Compare 1, 2 and 4 on the target host | load report 5.3, 5.5 |
| B-12 | Untested failure modes: full disk; long nginx↔API partition; a *controlled* power-loss test (an unplanned host restart during a run recovered correctly, load report 5.6) | P2 | Resilience runs with recorded outcomes | load report 5.4, 5.6 |
| B-13 | Keep raw load-test results immutable (the L-01 reproduction output was deleted while resetting the stack) | P3 | `run.sh` writes to a new timestamped folder per run and never deletes results | L-01 |
| B-14 | Independent penetration test and formal risk assessment | P1 (before any assurance claim) | Deploying organisation | R8 |
| B-15 | Competitor demonstrations and brochures for the unresolved `Unknown` cells | P3 | Evidence register updated with dated sources | competitive-evidence.md |
| B-16 | Execute CI on GitHub, including Trivy and gitleaks (O2), and the Unity workflow (O1) | P2 | Recorded CI runs | SPRINT_STATUS O1, O2 |
| B-17 | **Synchronised-start burst**: when a whole class starts at once, sign-ins (Argon2) and timeline generation coincide; session creation p95 exceeded 10 s even with admission headroom | P2 | Options: stagger starts in the instructor workflow; more generation workers on larger hosts (B-11); pre-generate a class's timelines when an assignment is created. Re-test B1-2 | load report 5.8 |
| B-18 | Post-soak record checks (session states, full reproducibility, audit chain) for the 2026-10-17 soak; blocked by the Docker/WSL failure | P2 | After a host restart: `docker exec drikrload-api-1 drikr-api reproducibility-report --limit 100000`, `verify-audit`, and the session-state query in `tests/load/soak.sh` | load report 5.9 |
| B-19 | Docker Desktop failed three times during sustained runs on the development laptop (L-04) | P2 | Run the soak on the target host; if it recurs there, isolate the cause (load generator on a separate machine, WSL memory limit, Docker version) | load report L-04 |
| B-20 | **Test the VR view on headsets** (Meta Quest via Link, Valve Index, HTC Vive) | P2 | Tracking, sand-table height, controller selection and classification on each; comfort over a 5-minute exercise; fix and re-test | ADR-013 |
| B-21 | VR: training responses other than classification (report, confirm, clear) in the headset | P3 | Controller menu; EditMode tests | ADR-013 |
| B-22 | Adaptive adversary: evaluate whether it targets weaknesses with synthetic agents of known weaknesses, then with trainees | P2 | Synthetic agents with a planted weakness: error rate on that weakness with and without the adversary; then the human study | ADR-012 |
| B-23 | Adaptive adversary: reactions within an exercise (evasion when engaged) | P3 | Would need ADR-001 reconsidered (timeline depends on live input) | ADR-012 |

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
| F-09 | A compromised API could delete a raw event log and mark it purged undetected | Migration `0005`: recorded, owner-enforced purges | `test_purge_integrity.py` |
| L-05 | Admission control: refused requests generated a whole timeline first (and, at a synchronised start, every request did) | Creation slots held from before generation until commit | `test_admission_control.py::test_a_refused_request_does_no_generation_work`, `…::test_a_simultaneous_burst_generates_only_what_can_be_admitted` |
| U-02, U-03 | Evidence ids had to be searched for by hand; no sort by score | B-06, B-07 | see B-06, B-07 |
| D-02 | **Every attempt replayed the identical exercise** (same seed) unless the trainee typed a seed, against SIH26247's randomisation requirement | Per-attempt recorded seeds by default; instructors can require identical attempts (migration 0006, ADR-012) | `test_attempt_variation.py` (5) |
| E2E | The full-workflow E2E test selected "Perimeter Awareness Basics (v1)"; after v2 the form lists only the latest version, and the test waited until it timed out. It would also have failed in CI | Select Perimeter basics at its current version, asserting exactly one match | `tests/e2e/specs/full-workflow.spec.ts` (24 passed after the fix) |
