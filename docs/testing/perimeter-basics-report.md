# Perimeter basics: root-cause report (Sprint 10, workstream A)

Status: **fixed and tested** (scenario version 2). Validated with synthetic agents only. No
trainee data is involved.

## Symptom

The assessment validation (docs/research/assessment-validation.md, E3) found that one session of
*Perimeter basics* was not a reliable measure. Test–retest ICC(A,1) was **0.62**, with a standard
error of measurement of **15.1 points**. The other three scenarios scored 0.82 to 0.88. Two attempts
by an agent of the same skill could differ by about 17 points. That is too noisy for an
instructor to judge an individual, or for the adaptive policy to act on, because adaptive
difficulty runs on this scenario.

## Reproduction

`research/assessment_validation/run_validation.py` uses the synthetic agent model: the real
generator, the real scoring engine and scripted agents of known skill. The comparison test
`tests/reproducibility/test_perimeter_basics.py::test_one_session_is_a_reliable_measure_in_version_2_but_not_version_1`
reproduces the symptom on version 1 for every sample run:

| Version 1, five independent samples of 60 agents | Min | Mean | Max |
|---|---|---|---|
| ICC(A,1) | 0.721 | 0.749 | 0.785 |
| SEM (points) | 11.2 | 11.8 | 12.2 |
| Assessable tracks per session | 4.5 | 4.5 | 4.6 |
| Sessions where the uncertainty dimension can be assessed | 23% | 27% | 28% |

Raw data: `research/assessment_validation/perimeter-basics-v1-v2.json`. These ICCs are higher than
the 0.62 in E3 because the samples use a different set of agents and seeds. Every sample is still
below the 0.80 required for an individual measure.

## Root cause

The cause is test length, not randomness or a code defect:

1. **Too few scored items.** A 240 s session at the default level contained about 4.5 assessable
   tracks (survey drone, intruder and bird groups). Each classification and response was therefore
   20–25% of the score, and one mistake moved the overall score by about 10 points.
2. **The uncertainty dimension applied only sometimes.** It needs at least one track that stays
   ambiguous long enough to judge. In version 1 that held in only about 27% of sessions, so the set
   of rubric dimensions changed from one session to the next. That added variance unrelated to
   skill.
3. **Ruled out:** generator nondeterminism (the v1 golden digest still reproduces exactly), seed
   choice (the shortage holds for every seed from 0 to 195 at every level) and scoring errors
   (verification reproduces every stored score).

The Spearman–Brown relation predicts the remedy. Roughly doubling the number of independent
decisions should raise reliability from about 0.75 to about 0.86.

## Fix (scenario version 2)

`packages/simcore/drikr_simcore/demo_scenarios/demo-perimeter-basics.json`, version 2:

- duration 240 s → **300 s**;
- **one or two** survey drones instead of one (spawn window 5–25 s → 5–60 s);
- **a second intruder** (a transit pass at 120–170 s, passing within 500–900 m);
- **a distant bird group** (90–200 s, 2,000–2,400 m) that stays ambiguous longer, so uncertainty
  can be assessed more often.

The rubric, the scoring engine and the generator are unchanged. Version 1 is archived in
`tests/fixtures/scenarios/demo-perimeter-basics-v1.json`, and sessions recorded against it still
verify, because every session stores its effective definition. `seed-demo` now publishes a changed
demo as a **new scenario version** instead of skipping it. Before this sprint, that seeding defect
meant an existing installation would never have received version 2.

## Evidence after the fix

| Version 2, same five samples | Min | Mean | Max |
|---|---|---|---|
| ICC(A,1) | 0.846 | 0.860 | 0.871 |
| SEM (points) | 8.1 | 8.4 | 8.6 |
| Assessable tracks per session | 8.4 | 8.5 | 8.6 |
| Uncertainty assessable | 40% | 44% | 48% |
| Mean score | 55.5 | 58.0 | 60.7 (v1: 55.7 to 61.0, so overall difficulty is unchanged) |

## Regression tests

| Test | What it pins |
|---|---|
| `tests/reproducibility/test_perimeter_basics.py::test_version_2_is_valid_and_versioned` | v2 validates and is version 2 |
| `…::test_archived_version_1_still_reproduces_its_golden_digest` | old records stay verifiable |
| `…::test_version_2_gives_enough_assessable_tracks_for_every_seed_and_level` | at least 7 tracks in v2 and at most 5 in v1, for seeds 0–195 at every level |
| `…::test_one_session_is_a_reliable_measure_in_version_2_but_not_version_1` (slow, two samples) | ICC v2 ≥ 0.80 and v1 < 0.80; SEM lower in v2 |
| `tests/integration/test_perimeter_basics.py::test_repeated_runs_with_interruption_persist_and_reproduce` | **repeated-run test**: eight complete runs through the API; every other run is interrupted for 120 s and resumed; event order, unique ids, scoring and verification are checked on each, and all eight produce one timeline digest |
| `tests/integration/test_perimeter_basics.py::test_seeding_publishes_a_changed_demo_as_a_new_version` | the upgrade path for existing installations |
| `tests/unit/test_simcore.py`, `tests/reproducibility/test_reproducibility.py` | the new golden digest `6a652ed2…80d1` |

## Limits

- The reliability evidence comes from synthetic agents. Human test–retest reliability is unknown
  until the pilot study runs (docs/research/training-effectiveness-study-protocol.md).
- ICCs depend on the spread of skill in the sample, which here is uniform from 0 to 1. A real
  cohort with a narrower range will show lower values.
- A five-minute exercise is still short. Instructors should judge an individual on more than one
  session; the AAR and analytics show trends across sessions for this reason.
