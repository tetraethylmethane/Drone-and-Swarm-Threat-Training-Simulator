# Adaptive difficulty: rationale, retune and test results (Sprint 10, workstream F)

Status: **retuned and tested against synthetic agents; not validated with trainees.** The retune
is a hypothesis about policy behaviour. It is not evidence that adaptive training improves
learning (docs/research/training-effectiveness-study-protocol.md).

| Item | Status |
|---|---|
| Inspection of the existing policy | Done |
| Selection criteria fixed before the retune | Done (`research/adaptive_retune/run_retune.py`, C1–C5) |
| Retune on synthetic agents (7 candidates, 2,785 sessions) | Done, 2026-10-16 (`research/adaptive_retune/results.json`) |
| Hypothesis that a retuned policy meets every criterion | **Partly supported**: C1–C3 met by the chosen policy; **C4 and C5 not met by any candidate** |
| Instructor inspection and override in the interface | Done (usability finding U-01) |
| Unit and integration tests | Pass (see section 6) |
| Behaviour with real trainees | **Not tested**: needs the pilot study |

## 1. How the policy works

`packages/scoring/drikr_scoring/adaptive.py`, called by the API after each scored session of an
adaptive assignment (`adaptive_service.record_after_session`):

- **Evidence:** the trainee's most recent scored sessions of the same scenario for that
  assignment (window of 3). Only recorded overall scores are used, with no other inputs or
  assumptions about the trainee.
- **Insufficient evidence:** fewer than 2 sessions → *hold*, with low confidence, and the reason
  says how many sessions are available.
- **Increase** (one level): mean ≥ 85 **and** every score in the window ≥ 75.
- **Decrease** (one level): with `robust_demotion` (the default since this sprint), a **full
  window** of 3 sessions whose **median** is below 55, so at least two of three must be poor.
- **Otherwise hold.** Every change is one step and stays within the **instructor's bounds**
  (`min_level`, `max_level` on the assignment).
- **Every evaluation is recorded**, including holds, with the reason text, confidence and the
  evidence used (session ids, scores, bounds and policy settings) in `difficulty_adjustments`. A
  database CHECK refuses a row without a reason.

No machine-learning model is involved, and the policy is deterministic: the same history gives the
same recommendation.

**Upgrade note.** Each adjustment stores the full policy it used (`evidence.policy`), so earlier
decisions stay explainable. An installation where an administrator **saved** a custom adaptive
policy before this release has it stored without the new fields. It therefore gets
`robust_demotion: true` (and `demote_max_each: 100`, `same_level_only: false`) on upgrade. To keep
the old rule, an administrator sets `robust_demotion` to `false`.

### What adaptation changes, and what it does not

- It changes **only the difficulty level** of the next session (sensor noise, latency, missed
  detections and clutter; scoring-model.md). The level is stored on the session with the seed, so
  every session still regenerates exactly (reproducibility report).
- It **never changes the rubric.** The rubric key and version come from the scenario version,
  and each result stores the rubric version and digest it was scored with, so the scoring rules
  cannot silently change between sessions. Scores at different levels are therefore on the same
  rubric, but they are not equally hard; analytics offer `same_difficulty_only` for comparisons.

### Instructor control

- The instructor sets the bounds when assigning.
- The **Difficulty** page for each adaptive assignment (linked from **Assignments**) shows every
  evaluation with its reason, confidence and triggering session.
- The instructor can **override** the next level: one step at a time, within the bounds, with a
  required reason (3–280 characters). The override is recorded as an adjustment ("Instructor
  override by …") and audited as `assignment.difficulty_override`. Trainees get 403.

## 2. Why it was retuned

The synthetic assessment validation (docs/research/assessment-validation.md, E5) found that the
original policy:

1. **lagged improving trainees**;
2. let **steady mid-skill trainees drift down** (about a third ended at level 1), because their
   scores sit near the 55 demotion line;
3. could **demote on one very poor session** among adequate ones: one failed session pulls a
   3-session mean below 55.

Point 3 conflicts directly with the requirement that a single unusually poor (or good) result must
not count as definitive evidence. Increases were already protected (every score ≥ 75); decreases
were not.

## 3. Method

`research/adaptive_retune/run_retune.py` uses the synthetic agent model from the assessment
validation (the real generator, scoring engine and scenario, *Perimeter basics* v2, scripted
agents of known skill). There were 40 agents per profile and 10 sessions each, with bounds 1–4 and
a start at level 2. The profiles were constant weak (0.3), mid (0.6) and strong (0.9); improving
(0.2 → 0.95); declining (0.95 → 0.2); and mid with a failed session every fourth time.

**Selection criteria, fixed before any candidate was run:**

| ID | Criterion |
|---|---|
| C1 | No recommendation leaves the bounds or moves more than one level |
| C2 | ≥ 90% of constant weak agents end at the minimum and ≥ 90% of constant strong agents at the maximum |
| C3 | Constant mid agents average ≤ 1.5 level changes, with ≤ 30% drifting to level 1 |
| C4 | The improving agent is raised, and the declining agent lowered, no later than under the current policy |
| C5 | A single failed session among adequate ones lowers the level in ≤ 5% of cases |

Candidates A–E were defined before the run. **F and G were added after A–E had all failed C5**.
They were judged on the same unchanged criteria, and `run_retune.py` records this.

## 4. Results (2026-10-16; Windows 11, CPython 3.12.4; 2,785 sessions in 245 s)

| Candidate | C1 | C2 (weak at min / strong at max) | C3 (changes / ever at level 1) | C4 (first raise / first lower) | C5 (outlier lowers) |
|---|---|---|---|---|---|
| A: original | ✓ 0 violations | ✓ 1.00 / 0.975 | ✗ 0.33 / 0.325 | never / 9 | ✗ 0.80 |
| B: outlier guard (every score < 65) | ✓ | ✓ 1.00 / 0.975 | ✓ 0.25 / 0.25 | never / 9 | ✗ 0.33 |
| C: same-level evidence only | ✓ | ✓ 1.00 / 0.925 | ✗ 0.33 / 0.325 | never / 9 | ✗ 0.80 |
| D: B + C | ✓ | ✓ 1.00 / 0.925 | ✓ 0.25 / 0.25 | never / 9 | ✗ 0.33 |
| E: D with 3 sessions minimum | ✓ | ✗ 1.00 / 0.85 | ✓ 0.20 / 0.20 | never / 9 | ✗ 0.33 |
| **F: median of a full window (chosen)** | ✓ | ✓ 1.00 / 0.975 | ✓ **0.17 / 0.175** | never / 9 | ✗ 0.33 |
| G: F + C (added post hoc) | ✓ | ✓ 1.00 / 0.925 | ✓ 0.17 / 0.175 | never / **never** | ✗ 0.33 |

### Interpretation

- **Chosen: F.** It meets C1–C3 with the fewest spurious changes for steady mid-skill agents
  (drift to level 1 falls from 32.5% to 17.5%). Its cost is that weak agents are lowered one
  session later (session 3 instead of 2).
- **C5 is not met by any candidate.** It fell from 80% to 33%, but the measure does not isolate
  single outliers. A 0.6-skill agent scores about 58 on this scenario, next to the 55 line, so
  windows that contain the failed session often also contain an ordinary score below 55. Those are
  two poor sessions, and lowering the level is then the intended behaviour. The literal
  requirement, that one failed session among adequate scores never lowers the level, holds for F
  by construction and is pinned by unit tests (section 6). The 33% is reported as measured.
- **C4 is not met by any candidate, including the original.** Over 10 sessions the improving agent
  is correctly lowered early (skill 0.2), and its skill reaches promotion-level scores only in
  sessions 9–10. A window of 3 with an every-score ≥ 75 rule cannot promote it within the horizon.
  The "lags improving trainees" finding (E5) is therefore **not fixed** by this retune. Faster
  promotion would trade against the protection from single good results, and that trade-off is
  left to instructors (override) until trainee data exists.
- G was rejected: same-level-only evidence stopped the declining agent from ever being lowered.

## 5. Limitations

- Synthetic agents are not trainees. Real learners differ in learning curves, variability,
  fatigue and motivation.
- One scenario and one bounds setting (1–4, starting at 2) were tested.
- Thresholds (85, 75, 55) are design choices, not values calibrated against competency.
- One policy applies to every assignment. It is an administrator setting (`adaptive_policy` in
  application settings; the defaults are in code). Instructors set bounds and can override a
  level, but they cannot change thresholds.
- Whether adaptation improves learning is unknown until the controlled study runs.

## 6. Tests (executed 2026-10-16 on the final code; all pass)

| Test | What it pins |
|---|---|
| `tests/unit/test_adaptive_retune.py::test_insufficient_evidence_holds_with_low_confidence` | No change without enough sessions |
| `…::test_one_unusual_result_is_not_enough` (parametrised) | One failed session among scores ≥ 58 or ≥ 65 holds |
| `…::test_a_decrease_needs_most_of_a_full_window_to_be_poor` (parametrised) | Two of three poor sessions lower the level; one does not |
| `…::test_results_at_another_level_do_not_count` | The `same_level_only` option behaves as documented |
| `…::test_sustained_evidence_at_the_current_level_changes_one_step_within_bounds` | One step, within bounds |
| `…::test_default_policy_uses_robust_demotion`, `…::test_policy_round_trips_and_validates` | Defaults and validation |
| `tests/unit/test_scoring.py::test_adaptive_never_leaves_bounds_and_always_explains` | 500-case property test: bounds, one step, a reason every time |
| `tests/unit/test_scoring.py::test_adaptive_*` (4 more) | Hold without evidence, increase, decrease, bounds and validation |
| `tests/integration/test_session_flow.py::test_adaptive_difficulty_records_reasons` | Repeated sessions through the API: hold after two poor sessions ("2 of 3 sessions are available"), lower after the third; every evaluation has a reason |
| `tests/integration/test_adaptive_override.py` (2 tests) | Override: bounds (422), one step (422), reason required, audited, used by the next session, refused to trainees (403); automatic adjustments still follow completed sessions |
| `apps/web/src/features/instructor/AssignmentDifficulty.test.tsx` | The instructor page shows the history and reasons and sends the override |
