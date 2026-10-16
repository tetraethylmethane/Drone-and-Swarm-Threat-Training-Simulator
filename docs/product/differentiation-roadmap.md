# Differentiation roadmap

Built on the actual project state (`docs/SPRINT_STATUS.md`). The original eight sprints are
complete, so this work is not repeated. Each approved improvement maps to **Sprint 9: Evidence
and differentiation** (done in this pass) or to a justified follow-up sprint (proposed).
Priorities follow the criteria: user value, evidence of an unmet need, engineering effort,
integration risk, validation cost, and importance to the core workflow. Features were not added
because a competitor advertises them.

## Backlog

**Status:**
- **Done**: implemented and tested in this pass.
- **Existing**: built in earlier sprints and verified again now.
- **Proposed**: not started.

**Evidence of unmet need** is weak throughout: no user research has been done. Each item
therefore carries a validation step.

### P0: Core credibility

| ID | Item | Status | Evidence |
|---|---|---|---|
| P0-1 | Complete trainee workflow (browser and desktop) | Existing | E2E `full-workflow.spec.ts`; Unity smoke tests (Windows, Linux) |
| P0-2 | Validated scenario configuration | Existing | Two-layer validation; `test_invalid_scenarios_are_rejected` |
| P0-3 | Reproducible scoring, including across engine versions | **Done** (cross-version check added) | `test_traceability.py`, `tests/reproducibility`, live 22 of 22 |
| P0-4 | Accurate, traceable AAR reports | **Done** (evidence events) | R-A1 |
| P0-5 | Role-based access control | Existing; new endpoints covered | `test_role_matrix`, new 403 and 404 tests |
| P0-6 | Offline deployment and recovery | Existing; **re-validated** backup, verification and restart | R-D3 |
| P0-7 | Automated end-to-end testing | Existing; extended for new screens | E2E suite |

### P1: Meaningful differentiation

| ID | Item | Effort | Risk | Status |
|---|---|---|---|---|
| P1-1 | Longitudinal competency tracking with recurring errors | Medium | Low | **Done** |
| P1-2 | Attempt comparison (identical exercises compared track by track) | Medium | Low | **Done** |
| P1-3 | Retune the adaptive policy (it lags improving learners; mid-skill drift) and re-run the synthetic validation | Small | Medium (changes trainee experience) | Proposed (Sprint 10) |
| P1-4 | Unit-level reporting | Small to medium | Low (additive migration) | **Done** |
| P1-5 | Reproducibility reports (bulk, CLI, UI) | Small | Low | **Done** |
| P1-6 | Explainable performance feedback: evidence per item, method stated for trends | Small | Low | **Done** |
| P1-7 | Measured performance on System health | Small | Low | **Done** |
| P1-8 | Instructor workflow improvements driven by a usability test | Unknown until tested | Low | Proposed (Sprint 10) |
| P1-9 | Make Perimeter basics reliable or mark it as a warm-up | Small | Low | Proposed (Sprint 10) |

### P2: Optional extensions (not scheduled)

VR client (via the adapter protocol); optional locally hosted AI assistance (for example, drafting
debrief text from the stored evidence, always labelled and editable); additional environment packs;
configurable report templates; advanced visualisation. Revisit after user research.

## Sprint 9: Evidence and differentiation (done in this pass)

### 9.1 Traceable assessments across engine versions
- **Objective:** every score can be traced to recorded events and a specific rubric and engine
  version. Upgrading the engine never silently changes or rewrites a stored result.
- **Tasks:**
  - add `evidence_events` per item, which bumps the scoring engine to `scoring-1.2.0`;
  - compare the assessment across versions in `verify`;
  - add an Evidence column to the AAR.
- **Files:** `packages/scoring/drikr_scoring/engine.py`, `apps/api/drikr_api/services/scoring_service.py`,
  `apps/web/src/features/aar/AarSections.tsx`, `apps/web/src/lib/types.ts`.
- **Dependencies:** none.
- **Tests:**
  - unit: reproducibility suite (evidence resolves);
  - integration: `test_traceability.py` (3);
  - end-to-end: existing AAR flows.
- **Acceptance:** every reference resolves to a stored event of the right type; an older-engine
  result with the same assessment verifies; a changed score is flagged.
- **Risks:** the result JSON grows slightly per item.
- **Definition of done:** the tests above pass, and the live deployment reproduces 22 of 22.
  **Met.**

### 9.2 Reproducibility suite and reports
- **Objective:** make reproducibility a standing, checkable property rather than a one-off claim.
- **Tasks:**
  - `tests/reproducibility` (golden digests, all demo scenarios at every level, two seeds, fresh
    interpreters with different hash seeds, scoring order independence);
  - `reproducibility_service`, `/admin/reproducibility`, `drikr-api reproducibility-report`;
  - a System health panel.
- **Files:** `tests/reproducibility/`, `apps/api/drikr_api/services/reproducibility_service.py`,
  `routers/admin.py`, `cli.py`, `AdminPages.tsx`, `pyproject.toml`.
- **Tests:**
  - unit: 40;
  - integration: `test_reproducibility_report.py`;
  - command line: run in the container.
- **Acceptance:** a tampered log is reported with its reason, and the run is audited. **Met.**
- **Risks:** a bulk check of many sessions takes time (22 sessions took 6.7 s), so the API run is
  limited to 500.

### 9.3 Competency tracking and attempt comparison
- **Objective:** show which competencies improved, which errors recur, and the evidence; make
  equivalent attempts easy to compare.
- **Tasks:** a `competency_service` with the rules stated; `/analytics/competency` and
  `/analytics/compare`; a Competency panel on My progress and Analytics; a Compare page; links from
  the AAR.
- **Files:** `apps/api/drikr_api/services/competency_service.py`, `routers/analytics.py`,
  `apps/web/src/features/analytics/Competency.tsx`, `features/aar/ComparePage.tsx`, `AarPage.tsx`,
  `HistoryPage.tsx`.
- **Tests:** integration `test_competency.py` (3); component `analytics.test.tsx`; end-to-end
  (competency on My progress).
- **Acceptance:**
  - trends and recurrence follow the stated rule;
  - trainees see only their own data;
  - summary-level feedback reveals no ground truth;
  - track detail appears only for identical exercises.

  **Met.**
- **Risks:** the trend rule is simple and could be read as more than it is. The page states the
  rule.

### 9.4 Unit-level reporting
- **Objective:** support reporting by team, section or course.
- **Tasks:**
  - migration `0003` (`users.unit`, CHECK constraint, index);
  - unit on user create and update (audited);
  - unit filter on progress and learning gains;
  - `/analytics/units`;
  - a Users page dialog and an Analytics Units panel.
- **Files:** `models.py`, `database/migrations/versions/0003_user_units.py`, `schemas.py`,
  `routers/users.py`, `routers/analytics.py`, `AdminPages.tsx`, `OverviewPages.tsx`, `Units.tsx`.
- **Tests:** `test_units.py` (2); migration upgrade, downgrade, upgrade and `alembic check`;
  component test.
- **Acceptance:** blank values rejected by the database; changes audited; summary means match
  stored results. **Met.**
- **Risks:** a unit can identify a small group. Unit summaries are staff-only.

### 9.5 Measured performance and recovery validation
- **Objective:** replace assumptions with measurements.
- **Tasks:** in-process request timing (`metrics.py`, route templates only);
  `scripts/measure-performance.py`; a recorded backup, verification and restart drill.
- **Tests:** `test_system_health_reports_measured_request_times`; manual runs recorded in
  `positioning.md` and `SPRINT_STATUS.md`.
- **Risks:** one machine only.
- **Definition of done:** measurements recorded with their environment. **Met.**

### 9.6 Research and positioning
- **Deliverables:** competitor landscape and evidence register (10 companies, accessed
  2026-10-16), research and reuse, positioning, this roadmap, requirements-to-tests.
  **Done.**

## Sprint 10 (proposed): Validate with users

| Item | Objective | Tasks | Files or modules | Tests | Acceptance | Risks | Definition of done |
|---|---|---|---|---|---|---|---|
| 10.1 Adaptive retune (P1-3) | Promote improving learners sooner without promoting noise | Try a narrower hold band, two-window demotion, and a minimum per-dimension rule; run `run_validation.py` | `packages/scoring/drikr_scoring/adaptive.py`, settings defaults | Unit tests for the new rules; synthetic E5 before and after | Improving agent promoted earlier; steady agents stable; 0 bound violations | Changing defaults changes trainee experience | Validation report updated with before and after; instructors can still override |
| 10.2 Perimeter basics (P1-9) | Reach reliability of at least 0.8 or relabel as a warm-up | Lengthen and add tracks; re-run E3 | Demo scenario JSON, version 2 | Reproducibility golden digest for version 2; synthetic E3 | ICC of at least 0.8, or the "warm-up" label shown | New version changes comparisons with version 1 | New version published; old version kept |
| 10.3 Instructor usability test (R-E1) | Find real workflow problems | 5 to 8 instructors, 5 tasks, think-aloud, SUS | Protocol in this folder | n/a | Findings logged with severity | Recruiting | Report with observed data only |
| 10.4 Competitor verification | Settle the `Unknown` cells that matter | Demonstrations or brochures for DefenceVR, VR Astra, Zen, MAK, Althimis | `docs/research/` | n/a | Evidence register updated | Vendors may not share | Register updated with dates |
| 10.5 Human pilot (R-G1) | Re-estimate variance; test feasibility | Ethics approval, then the pilot | Study protocol | n/a | Pilot report | Approval time | Report with observed results only |
| 10.6 Load test | Establish requirements | Simulated concurrent trainees (polling plus decisions) on the target server | `scripts/` | Repeatable script | p95 latency and errors at N trainees recorded | Representative hardware needed | Minimum and recommended requirements documented |

## Scope and architecture changes

- **Added:** migration `0003` (`users.unit`); scoring engine `scoring-1.2.0` (additive output
  field); verification across engine versions now compares the assessment (scores, outcomes, error
  counts) instead of requiring byte-identical output.
- **Unchanged:** the stack (FastAPI, PostgreSQL, React, Unity as a presentation client, Docker
  Compose). No new services, engines or external dependencies.
- **Note on the Unity engine:** the follow-up brief lists "Unity + C# for the authoritative
  simulation engine". The project keeps the documented ADR-001 decision: the authoritative
  simulation is the deterministic Python engine on the server, and Unity is a presentation client.
  This is what makes the reproducibility guarantees above possible: identical digests across
  operating systems and re-scoring from stored logs. Moving authority into Unity would mean
  re-establishing determinism in a game engine. That change needs a demonstrated user need, which
  has not been found.
