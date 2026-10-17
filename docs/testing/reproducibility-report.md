# Reproducibility and data-integrity report (Sprint 10, workstream B)

Date: 2026-10-16. Engine versions: `simcore-1.0.0` and `scoring-1.2.0`. Evidence comes from
automated tests in this repository and reports on stored data. All runs used one Windows 11
development laptop, plus the Linux containers built from this repository. **These are development
results, not results from a deployed installation.**

## 1. What is guaranteed

The same scenario version, effective configuration, seed and difficulty level produce the **same
canonical event records**, and therefore the same timeline digest. The same stored events, with
the same rubric version and scoring engine, produce **byte-identical score output**. A result
scored by an older scoring engine counts as reproducible when re-scoring gives the same scores,
outcomes and error counts (ADR-001, "Limits of deterministic replay").

## 2. Test matrix

| Property | Test | Result (2026-10-16) |
|---|---|---|
| Same configuration and seed give identical events, for every demo scenario, every allowed level and two seeds | `tests/reproducibility/test_reproducibility.py::test_same_configuration_and_seed_give_identical_events` | Pass |
| Golden digests per demo scenario (detects any unintended engine change) | `…::test_engine_version_matches_golden_digests` | Pass (Perimeter basics v2 golden `6a652ed2…80d1`; v1 golden still reproduces from the archived definition) |
| Independent of hash randomisation and dict ordering | `…::test_fresh_interpreters_with_different_hash_seeds_agree` | Pass |
| Scoring is deterministic and independent of event order | `…::test_scoring_is_deterministic_and_order_independent` | Pass |
| Generation in a worker process equals inline generation | `tests/integration/test_session_creation_load.py::test_generation_in_a_worker_process_matches_inline`, `…::test_api_with_worker_processes_stores_the_same_timeline` | Pass |
| Stored timeline equals the generated one, row for row (after the COPY change) | `…::test_stored_timeline_is_exactly_the_generated_one` | Pass |
| **Event ordering**: chronological by (t_ms, seq); seqs contiguous and unique; event ids unique | `tests/integration/test_perimeter_basics.py::test_repeated_runs_with_interruption_persist_and_reproduce` (8 runs) | Pass |
| **Duplicate actions** are idempotent (`client_action_id`); repeated completion returns the same result | `tests/integration/test_session_flow.py::test_duplicate_actions_and_completion_are_idempotent` | Pass |
| **Rule-version retention**: editing a scenario or rubric creates a new version; old sessions keep and verify against their own version | `tests/integration/test_catalog.py`, `test_perimeter_basics.py::test_seeding_publishes_a_changed_demo_as_a_new_version` | Pass |
| **Immutability**: the database refuses UPDATE on events and UPDATE or DELETE on score results; no API route edits them | `tests/integration/test_integrity.py::test_database_refuses_edits_to_records`, `…::test_no_api_route_can_edit_events_or_results` | Pass |
| **Reconnection**: a reloaded client rebuilds the identical event set from the server and never sees ground truth | `…::test_reconnecting_client_rebuilds_the_same_state_from_the_server` | Pass |
| **Interrupted sessions**: a 120 s disappearance pauses the session, and it resumes with the same final digest | `test_perimeter_basics.py` (4 of the 8 runs interrupted) | Pass |
| **Transactions and rollback**: a partly invalid action writes nothing; a failure midway through a request rolls back | `test_integrity.py::test_partially_invalid_action_writes_nothing`, `…::test_failure_midway_through_a_request_rolls_back` | Pass |
| **Restart recovery**: a new API process continues a running session from the database, completes and verifies it | `test_integrity.py::test_session_continues_after_the_api_restarts`; the container restart in the resilience run (docs/testing/load-resilience-report.md) | Pass |
| Least-privilege database role can still run the whole workflow, including verification | `tests/integration/test_db_role.py::test_full_workflow_runs_as_the_app_role` | Pass |
| **Purged event logs** count as reproducible only with a recorded purge from a real retention run or an anonymisation; the API role cannot delete events or mark a session purged (migration `0005`, F-09) | `tests/integration/test_purge_integrity.py` (6 tests) | Pass (2026-10-17) |

## 3. Stored-data reports (`drikr-api reproducibility-report`)

Each stored session is regenerated from its stored scenario version, seed and level, compared with
the stored log, and re-scored.

| Data set | Sessions checked | Reproducible | Notes |
|---|---|---|---|
| Load-test database after the 10, 30, 60 and 100-user runs (`tests/load/results/2026-10-16/post-sweep-reproducibility.json`) | 355 | **355** | All `scoring-1.2.0`; includes sessions paused and resumed under overload |
| Load-test database after the `load-30vu-300s` run (`load-30vu-300s-reproducibility.json`) | 423 | **423** | That load run was anomalous and terminated (load report, section 4.1). This figure is a valid check of the stored data, not a result of the load run |
| **Whole load-test database on 2026-10-17**, after the acceptance, stress, resilience and memory runs, two outages and an unplanned host restart (`tests/load/results/2026-10-17/full-reproducibility.json`, `--limit 100000`) | 955 | **955** | All `scoring-1.2.0`; exact score match 955; every completed session has a result (load report 5.7). Earlier reports used `--limit 500` and covered at most 500 sessions |

Under load, the server's count of classified tracks also equals the number of distinct tracks
classified in the stored log, for every scored result (333 of 333; SQL in the load report).

## 4. Known nondeterminism and tolerances

| Source | Treatment | Tolerance |
|---|---|---|
| Floating-point positions and qualities | Rounded before hashing (0.1 m, 0.01) | Logical equivalence; byte-level float output is not compared |
| Wall-clock time of trainee actions | Quantised to the server's 100 ms tick; the client clock is ignored | Within one tick |
| `recorded_at` timestamps, row ids, UUIDs of sessions | Not part of any digest | Not reproduced, by design |
| Rendering, camera and frame timing (web and Unity) | Client-only; never recorded | Not reproduced |
| Pause timing after connection loss | The session pauses at the last heartbeat plus the 15 s grace, so a pause under heavy load can occur earlier in wall time | Exercise time stops; the timeline and score are unaffected |
| Scoring-engine upgrades | Older results are never rewritten; verified by assessment equality | Same scores, outcomes and error counts |
| Platforms | Verified on Windows/CPython 3.12.4 and Linux/CPython 3.12.14 (container) | Other platforms are expected to match but are not verified |

## 5. Limits

- Reproducibility is about records. It says nothing about whether a score is a valid measure of
  skill (docs/research/assessment-validation.md) or whether training transfers (study protocol).
- A database superuser can still rewrite records consistently (residual risk R2). Verification
  then detects edits only to events, not a consistent rewrite of definitions, events and results.
- Sessions whose raw event logs were purged under the retention policy keep their scores and
  digests but can no longer be re-scored (`event_log_purged`). Since migration `0005` every purge
  must have a record, and an unrecorded one is reported as `purge_unrecorded`.
