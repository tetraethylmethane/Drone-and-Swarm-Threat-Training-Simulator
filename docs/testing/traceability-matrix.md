# Requirements-to-tests traceability

Status: **Tested** = automated test passes; **Implemented** = built and exercised manually or by
screenshot only; **Not implemented** = absent in this release.

| Req (brief §) | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| 1 | Scripted and procedurally randomised scenarios | Demo scenario JSON; `procedural.py`; `/scenarios/generate` | `test_procedural_generation_is_valid_and_deterministic`, `test_procedural_generation_returns_valid_unsaved_draft`, E2E generate spec | Tested |
| 1 | Single drone and multi-agent swarm | Entity groups; `SwarmConfig` formations | `test_swarm_members_move_together`, swarm demo scoring tests | Tested |
| 1 | Day/night, urban/rural, visibility, sensor quality | `EnvironmentConfig`, `SensorSuite`, presets, scheduled degradation | `test_scripted_degradation_reduces_detections`, `test_visibility_change_and_messages_emitted`, `test_difficulty_changes_sensor_quality` | Tested |
| 1 | Learning objectives | `LearningObjective` criteria; objective scoring | `test_false_clearance_objective_and_classify_before_report`, objective rows in perfect/idle tests | Tested |
| 1, 6 | Transparent configurable decision-tree scoring | `rubric.py`, `engine.py` | `test_decision_tree_paths`, `test_explanations_match_computed_scores` | Tested |
| 1 | Performance tracking across sessions | `/analytics/progress`, history page | `test_progress_matches_persisted_results_and_filters` | Tested |
| 1 | Instructor-led and self-guided | Assignments; `self_guided` sessions | `test_full_trainee_workflow...`, `test_self_guided_practice` | Tested |
| 1, 6 | Automatic difficulty adjustment within bounds with reasons | `adaptive.py`, `adaptive_service.py` | `test_adaptive_*` (unit), `test_adaptive_difficulty_records_reasons` | Tested |
| 1 | AAR | `AarPage` + timeline/result/review APIs | E2E full workflow | Tested |
| 1, 11 | Offline operation | No external runtime dependencies | `test_generation_needs_no_network`, `test_no_interactive_docs_or_cdn_assets`, system page; offline check in `SPRINT_STATUS.md` | Tested (see sprint 7 record) |
| 1 | Optional VR | Unity client: OpenXR sand-table view with controller selection and classification (`-drikrVr`; ADR-013) | `VrControlsTests` (4, EditMode); Windows player smoke test with `-drikrVr` and no headset: falls back to the desktop and completes a scored exercise | **Built; not tested on a headset** |
| 2 | Safety boundaries: no real control, no engagement guidance | Predefined procedural responses only; synthetic labels | `test_trainee_action_shapes` (rejects other responses), UI test asserting no engagement terms | Tested |
| 3 | Unity for environments, drone representations, playback | `apps/simulator/DrikrUnityClient` (visual client; server keeps simulation authority, ADR-001) | Unity EditMode tests (19, including live protocol over HTTP and over HTTPS with a pinned CA); smoke tests of the Windows player (HTTPS) and the Linux player (Docker, HTTPS); macOS bundle built and inspected, not run | Tested (Windows, Linux); built only (macOS) |
| 3 | Fixed steps, seeds, versioned configs, timestamps | ADR-002, digests | `test_events_follow_timing_and_contract_rules`, `test_golden_digest_regression` | Tested |
| 4 | RBAC enforced on backend | `rbac.py`, `require()` | `test_role_matrix` (22 endpoints × 3 roles), E2E | Tested |
| 4 | Trainee workflow steps 1–10 | Trainee pages and exercise runner | E2E full workflow | Tested |
| 4 | Instructor workflow steps 1–8 | Scenario editor, assignments, sessions, AAR, exports | E2E full workflow and content specs | Tested |
| 5 | Scenario schema fields and validation rules | `scenario.py` | `test_invalid_scenarios_are_rejected` and related | Tested |
| 5 | Reproducible seeded randomisation | `rng.py`, `generator.py` | `test_identical_inputs_reproduce_identical_timelines`, `test_different_seeds_produce_valid_variations` | Tested |
| 5 | Invalid configs rejected before execution | Two-layer validation | `test_unobservable_scenario_rejected_by_generation_check`, `test_missing_rubric_reference_rejected` | Tested |
| 5 | Replayable event log with stable ids | `session_events`; timeline API | `test_timeline_pagination_and_categories`, verify endpoint | Tested |
| 5 | Synthetic data labelled | `synthetic: true`; UI notices | contract test, E2E checks notice | Tested |
| 6 | Historical scores keep rubric version | Immutable rubrics; stored versions | `test_weight_change_changes_score_and_records_version`, `test_rubric_versioning_and_validation` | Tested |
| 6 | Missing data not misleading | Non-applicable dimensions; `insufficient_data` | `test_idle_trainee_gets_no_free_points`, `test_insufficient_data_when_nothing_observable` | Tested |
| 7 | AAR sections: overview, breakdown, timeline, errors, progress, review, export | AAR tabs, analytics | E2E full workflow; screenshots | Tested |
| 7 | Charts from persisted data; empty states | Analytics endpoints | `test_empty_states_do_not_invent_data`, component test | Tested |
| 7 | CSV and PDF with access control | `reports.py` | `test_csv_export_*`, `test_pdf_export_and_permissions` | Tested |
| 8 | Brand: official Drikr logo and mark, no monospace, accessible focus | `assets/brand/` (originals with checksums), web header and favicon, PDF, Unity header and icon | E2E axe, keyboard and monospace checks; PDF test; screenshots in `docs/design/screens` | Tested |
| 11 | Password hashing, sessions, rate limits, validation | `security/*` | `test_auth.py` | Tested |
| 8, 11 | Accessibility of the Unity panel | `PanelAccessibility.cs` (Unity accessibility API) | `scripts/unity-a11y-check.ps1`: full exercise through Windows UI Automation without pointer input; `AccessibilityTests` | Tested on Windows; macOS untested; Linux not supported by Unity |
| — | Unity CI | `.github/workflows/unity.yml` (GameCI or self-hosted) | `actionlint` clean; the self-hosted job's commands run locally | Implemented; not run on GitHub (no remote, no licence secrets) |
| 11 | Multi-factor authentication | TOTP with encrypted secrets, recovery codes, role policy, resets | `test_mfa.py` (8), `test_totp_secretbox.py` (RFC 6238 vectors), web `security.test.tsx`, E2E `administrators must use MFA…`, Unity `SecurityTests` | Tested |
| 11 | TLS for network access | `docker-compose.tls.yml`, `nginx-tls.conf.template`, `generate-tls-cert.sh` | Manual verification record in `offline-deployment.md`; Unity `LiveHttpsWithPinnedCa`, `PinnedCaValidation` | Tested (manual record plus Unity tests) |
| 11 | Data retention and anonymisation | `retention_service.py`, settings, CLI | `test_retention.py` (6), web AAR purge test, E2E retention preview | Tested |
| 1, 7 | Evidence of whether the training works | Learning-gain analytics, pseudonymised export, synthetic assessment validation, human study protocol | `test_study.py`, `test_stats.py`; `research/assessment_validation/results.json` (reproduced twice) | Measurement validated with synthetic agents only; **human effectiveness not tested** (protocol written) |
| 11 | Tamper-evident audit | `audit.py`, trigger | `test_audit_and_constraints.py` | Tested |
| 11 | Backup and restore | `scripts/backup.sh`, `verify-backup.sh`, `restore.sh` | Recorded run in `SPRINT_STATUS.md` | Tested (manual run, recorded) |
| 11 | No loss of completed results on interruption | Server clock, idempotency | `test_connection_loss_pauses_and_recovers`, `test_duplicate_actions_and_completion_are_idempotent` | Tested |
| 13 | Performance baseline | Measured | `SPRINT_STATUS.md` | Measured (no targets set) |
