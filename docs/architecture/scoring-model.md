# Scoring model (scoring engine `scoring-1.1.0`)

Implementation: `packages/scoring/drikr_scoring/engine.py`. Demonstration rubric:
`packages/scoring/drikr_scoring/default_rubrics/standard-assessment.json`.

## Inputs

* The session's recorded event log (generated timeline + lifecycle + trainee + confirmation events).
* The session's effective scenario definition (learning objectives).
* The exact rubric version referenced by the session.
* `end_ms`: simulation time at which the session ended.

The engine reads nothing else. Input order does not matter (events are sorted by `seq`).

## Scoring items

An item is a **track the trainee could observe** before `end_ms` (at least one trainee-visible
observation with `available_at_ms ≤ end_ms`). Tracks never observed are not items, so trainees are
never penalised for invisible entities. Decisions on non-observable tracks are ignored and counted
in `counts.ignored_decisions`.

## Dimensions (each 0–100 %, mean credit over applicable rows)

| Dimension | Applicable rows | Credit per row |
|---|---|---|
| Recognition | Every item | 1 if the **final** classification equals ground truth; else the rubric partial-credit value (default table: swarm↔multirotor 0.25, fixed-wing↔multirotor 0.1); 0 if never classified (recorded as a *missed track*). |
| Timing | Items with at least one classification | Δ = first classification − first availability. 1 if Δ ≤ `target_s`; 0 if Δ ≥ `max_s`; linear between. Per-class overrides allowed (default: swarm 15/60 s, others 20/90 s). |
| Consistency | Every item | Decision tree → expected/acceptable responses for the item's ground-truth facts. Final response expected: 1; acceptable: 0.5; other or none: 0. |
| Uncertainty | Items first classified while classification evidence < threshold (default 0.5) | Confirmation requested before classifying: 1.0; low confidence: 1.0; medium: 0.6; high & correct: 0.3; high & wrong: 0 (recorded as *overconfident*). Evidence = best optical class-hint or confirmation quality visible at decision time. |
| Objectives | Each assessable learning objective | Met: 1, not met: 0. Objectives with no matching observable track are *not assessable* and excluded. |
| Procedure | Each rule with ≥ 1 opportunity | 1 − violations/opportunities. Rules: confirm before clearing weak evidence; minimum observations before clearing; classify before reporting or clearing. |

## Overall score

```
overall = Σ_d w_d · score_d / Σ_d w_d      over applicable dimensions d
```

Weights are the rubric weights (must sum to 1.0, recognition weight > 0). Weights of non-applicable
dimensions are redistributed proportionally; **non-applicable dimensions never award points**.
`passed = overall ≥ pass_mark`. If there are no items the status is `insufficient_data` and
`overall`/`passed` are null.

Every row stores its credit and a reason; every dimension stores its weight, effective weight and
contribution, so the displayed explanation equals the computation (tested in
`tests/unit/test_scoring.py::test_explanations_match_computed_scores`).

## Decision tree (demonstration rubric)

Facts available to conditions: `true_class`, `cooperative`, `behavior`, `closest_range_m`,
`beacon_observed`, `swarm_member`. Operators: `eq ne in not_in lt lte gt gte`.

1. Bird or clutter → expected *log as cleared*; acceptable *continue monitoring*.
2. Coordinated swarm → expected *report to exercise control*.
3. Cooperative and simulated beacon observed → *log as cleared* or *continue monitoring*; acceptable *report*.
4. Cooperative, beacon never observed → *continue monitoring* or *request confirmation*; acceptable *report*.
5. Non-cooperative, closest approach ≤ 1500 m → *report*; acceptable *request confirmation*.
6. Non-cooperative, distant → *continue monitoring* or *report*; acceptable *request confirmation*.

These are training rubric rules for a virtual exercise, not operational procedures.

## Versioning and reproducibility

* Each result records `scoring_engine_version`, rubric key/version/digest, `input_digest`
  (SHA-256 of the canonical event list) and the stored result's digest.
* Rubrics are immutable; editing creates a new version. Existing results keep their version.
* `POST /sessions/{id}/verify` re-scores stored events with the stored rubric and compares digests.
  If the running engine version differs from the recorded one, the response says so and the stored
  result is retained unchanged.
* Change log: `scoring-1.0.0` → `scoring-1.1.0` changed only the wording of explanations
  (human-readable class and response names). Numeric scoring is unchanged.

## Adaptive difficulty (rules-based, `drikr_scoring/adaptive.py`)

Evaluated after every scored session in an adaptive context (adaptive assignment, or self-guided
practice on a scenario that allows it). History = the trainee's scored sessions for the same
assignment (or same scenario key in self-guided mode), oldest first. Defaults (administrator
configurable): window 3, minimum sessions 2, increase when mean ≥ 85 and every score ≥ 75, decrease
when mean < 55, high confidence when ≥ window sessions and population SD ≤ 10.

* Fewer than `min_sessions` → **hold** (low confidence).
* Increase criteria met → +1 level, unless at the instructor maximum (hold, reason says so) or
  confidence is low (hold).
* Mean below the decrease threshold → −1 level, unless at the instructor minimum (hold).
* Otherwise hold.

Every evaluation, including *hold*, is stored in `difficulty_adjustments` with its reason, evidence
(sessions, scores, mean, SD, bounds, policy) and confidence. Changes are at most one level per
session (database constraint). Level effects are fixed per engine version
(`drikr_simcore/difficulty.py`): level 3 runs the scenario as authored; lower levels improve
simulated sensor reliability; higher levels add noise, latency, missed detections and clutter.
