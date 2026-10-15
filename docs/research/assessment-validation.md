# Assessment validation with synthetic trainees

> **Synthetic study.** Every number below comes from scripted agents, not people. It shows how the
> *measurement* behaves when the true skill of the person being measured is known. It says nothing
> about whether training with this product improves human performance. That question needs the
> controlled human study in [training-effectiveness-study-protocol.md](training-effectiveness-study-protocol.md).

| | |
|---|---|
| Script | `research/assessment_validation/run_validation.py` |
| Raw output | `research/assessment_validation/results.json` |
| Engines | simulation `simcore-1.0.0`, scoring `scoring-1.1.0`, rubric `standard-assessment v1` |
| Scenarios | the four seeded demo scenarios, at their default difficulty unless stated |
| Master seed | 20261015 |
| Run | 2026-10-15, CPython 3.12.4, Windows 11. Two consecutive full runs produced identical `results.json` apart from the runtime field. |
| Reproduce | `.venv/Scripts/python research/assessment_validation/run_validation.py` (about 5 minutes with 11 worker processes on a 12-thread machine; `--quick` for a smoke run) |

## Method

Each synthetic session uses the production code end to end:

1. `generate_timeline` builds the exercise from the scenario, seed and difficulty level.
2. The agent sees only what a trainee sees: tracks become available at their recorded
   `available_at_ms`, and evidence quality comes from the observations visible at that moment.
3. Sensor-confirmation requests go through the production `sensor_confirmation_event`.
4. The agent's actions are written as `classification_submitted` and `response_submitted` events,
   exactly as the API records them, and `score_session` scores the resulting log.

The agent has one parameter, skill *s* between 0 and 1. The model is deliberately simple:

| Behaviour | Model |
|---|---|
| Attention | Ignores a track with probability 0.5(1 − *s*) |
| Decision delay | Log-normal around 6 + 60(1 − *s*) seconds after the track first becomes visible |
| Confirmation | When evidence is below the rubric threshold (0.5), requests confirmation with probability 0.8*s*, then uses the returned hint with probability 0.5 + 0.5*s* |
| Classification | Correct with probability 0.15 + 0.8*s*, reduced by a quarter on weak unconfirmed evidence |
| Confidence | On weak evidence, says "low" with probability *s*; otherwise "medium" (30%) or "high" |
| Response | The rubric's expected response with probability 0.25 + 0.7*s*, otherwise a random one |
| Procedural lapse | Before a report or clear, skips classifying first with probability 0.6(1 − *s*) and classifies a second later |

**Limitation of the agent.** Skill sets how good decisions are. The agent does not perceive the
picture: noise, clutter and dropouts affect it only through the weak-evidence branch. Results about
difficulty (E4) therefore test the scoring rules, not how hard the scenarios are for people.

## Results

### E1. Construct validity: does the score follow true skill?

90 agents with skill drawn uniformly from 0 to 1, one session per scenario. Spearman rank
correlation between skill and score:

| Scenario (level) | Overall | Recognition | Timing | Consistency | Uncertainty | Objectives | Procedure |
|---|---|---|---|---|---|---|---|
| Degraded picture (3) | **0.93** | 0.86 | 0.93 | 0.84 | 0.84 | 0.64 | 0.59 |
| Night loiter (3) | **0.90** | 0.79 | 0.90 | 0.79 | 0.72 | 0.51 | 0.48 |
| Perimeter basics (2) | **0.84** | 0.74 | 0.90 | 0.74 | 0.48 (n = 19) | 0.64 | 0.52 |
| Swarm recognition (3) | **0.95** | 0.88 | 0.94 | 0.87 | 0.80 | 0.82 | 0.63 |

Pooled across scenarios: ρ = 0.89. All 720 sessions produced a score; none were
"insufficient data".

The overall score ranks the agents by skill well. The **objectives** and **procedure** dimensions
follow skill less closely. They are built from few, coarse items: three objectives per
scenario, and procedural rules that only apply when a track is reported or cleared. In
**Perimeter basics**, the uncertainty dimension could be assessed in only 19 of 90 sessions,
because at level 2 the picture rarely gives weak evidence.

An earlier version of the agent made its procedural lapse in the same 100 ms tick as the
classification. The engine counts a classification in the same tick as compliant, so the lapse was
never detected and procedure appeared unrelated to skill (ρ ≈ 0.15). The fix was to the agent, not
the engine. The tick-level tolerance is intended behaviour, but instructors should know about it.

### E2. Discrimination between skill bands

Mean overall score (SD) by skill band, and Cohen's *d* between adjacent bands:

| Scenario | Low (*s* < 0.33) | Mid | High (*s* ≥ 0.67) | *d* mid vs low | *d* high vs mid |
|---|---|---|---|---|---|
| Degraded picture | 30.3 (8.8) | 52.6 (11.7) | 73.2 (7.3) | 2.16 | 2.11 |
| Night loiter | 31.6 (9.4) | 51.6 (12.4) | 74.8 (9.3) | 1.82 | 2.11 |
| Perimeter basics | 35.4 (13.3) | 56.2 (18.4) | 83.7 (14.4) | 1.30 | 1.66 |
| Swarm recognition | 26.6 (7.9) | 45.3 (9.6) | 75.1 (11.3) | 2.14 | 2.84 |

All adjacent bands are separated by large effects. **No floor effect** was found: no session
scored 5% or below. **Perimeter basics shows some ceiling**: 8.9% of sessions scored 95% or more,
which limits how far it can show progress for strong trainees.

### E3. Test–retest reliability

Each agent played each scenario twice, with a different scenario seed and different behaviour
randomness.

| Scenario | ICC(A,1) | Standard error of measurement | Mean absolute difference |
|---|---|---|---|
| Degraded picture | 0.83 | 7.9 points | 8.7 |
| Night loiter | 0.82 | 8.8 points | 9.9 |
| Perimeter basics | **0.62** | **15.1 points** | 16.8 |
| Swarm recognition | 0.88 | 7.4 points | 8.5 |

The three level-3 scenarios are reliable enough to compare groups. **Perimeter basics is not
reliable enough to judge an individual from one session.** Two attempts can differ by about
17 points for the same skill, because the short scenario has few tracks, so each decision weighs
heavily.

These ICCs depend on the spread of skill in the sample, which was uniform from 0 to 1. A real
cohort with a narrower range of ability would show lower ICCs.

### E4. Sensitivity to difficulty level

Mean overall score at fixed skill across the allowed difficulty range (12 sessions per cell):

| Scenario | Skill 0.3 | Skill 0.6 | Skill 0.9 |
|---|---|---|---|
| Degraded picture (1 to 5) | 40.3 to 38.7 | 62.6 to 55.2 | 79.6 to 77.2 |
| Night loiter (2 to 5) | 39.3 to 42.2 | 59.7 to 59.9 | 77.8 to 79.0 |
| Perimeter basics (1 to 4) | 45.6 to 36.6 | 66.5 to 54.2 | 92.0 to 83.3 |
| Swarm recognition (2 to 5) | 32.9 to 30.9 | 57.9 to 48.8 | 82.9 to 77.0 |

Rank correlations between level and score at fixed skill range from −0.39 to +0.07. For an agent
whose decision quality is fixed, the scoring is fairly stable across levels, mostly within
10 points. The largest drops are at the hardest levels of Perimeter basics and Swarm recognition.
As noted under Method, this does not show how much harder the levels are *for people*; the pilot
study must measure that.

### E5. Adaptive difficulty with the production policy

Twenty agents per profile, twelve sessions of Perimeter basics, starting at level 2 with bounds 1
to 4. The production `recommend_level` was applied after each session.

| Profile | Median level after sessions 0, 2, 4, 8, 12 | Final level distribution (1/2/3/4) |
|---|---|---|
| Constant skill 0.3 | 2, 1, 1, 1, 1 | 20 / 0 / 0 / 0 |
| Constant skill 0.6 | 2, 2, 2, 2, 1 | 13 / 6 / 1 / 0 |
| Constant skill 0.9 | 2, 3, 4, 4, 4 | 0 / 0 / 0 / 20 |
| Skill rising 0.2 to 0.95 | 2, 1, 1, 1, 2 | 7 / 7 / 5 / 1 |

Across 960 recommendations there were **no bound violations and no jumps of more than one level**.
Weak and strong agents end at the expected extremes within four sessions.

Two behaviours need review before the policy is relied on:

- **Drift for mid-skill trainees.** A steady 0.6 agent scores about 59 ± 11. Random dips below the
  demotion threshold (mean below 55) eventually move most of them down. Promotion needs a mean of
  85 or more, which they never reach, so they don't move back. The hold band is wide and asymmetric
  under noise.
- **Lag for improving trainees.** The improving agent is demoted early, and is only promoted once
  its skill reaches about 0.9, near session 11. Its level trails its skill by several sessions.

Possible changes, not made in this release, include a narrower hold band, a longer window, or
needing two consecutive windows before demoting. Any change should be re-tested with this script.

### E6. Sample size needed to detect a learning gain

Cohorts were resampled from 840 additional sessions at fixed skill points (40 per point, all
scenarios). Mean score rises by about 6.5 points per 0.1 of skill in the middle of the range (for
example 45.8 at 0.4 and 58.8 at 0.6). Score SD at fixed skill is 7 to 13 points.

**Single group, first versus later attempt** (exact sign test, two-sided α = 0.05, 400 replicates):

| True skill gain | n = 8 | 12 | 16 | 24 | 32 |
|---|---|---|---|---|---|
| 0.1 (about 6 points) | 0.05 | 0.18 | 0.19 | 0.30 | 0.43 |
| 0.2 (about 13 points) | 0.17 | 0.59 | 0.65 | 0.86 | 0.92 |
| 0.3 (about 19 points) | 0.47 | 0.87 | 0.94 | 1.00 | 1.00 |

**Two groups, training versus practice-only control** (permutation test on the difference in mean
gain, α = 0.05, 400 replicates; n is per group):

| Gains (training / control) | n = 12 | 16 | 24 | 32 |
|---|---|---|---|---|
| 0.3 / 0.1 (difference about 13 points) | 0.47 | 0.65 | 0.84 | 0.92 |
| 0.2 / 0.05 (difference about 10 points) | 0.33 | 0.43 | 0.59 | 0.68 |

Under these assumptions, a controlled study needs **about 24 to 32 trainees per group** to detect a
13-point difference in gains with 80% to 90% power. A 10-point difference needs more than 32 per
group. Small cohorts (8 to 12) can only detect large effects.

The first-versus-latest analytics in the product are useful for monitoring, but they cannot show
that training works. With no control group they cannot separate learning from practice and
familiarity with the scenario.

## Conclusions for the product

1. The overall score is a valid ranking of known skill in all four scenarios (ρ = 0.84 to 0.95),
   with clear separation between skill bands and no floor effect.
2. The level-3 scenarios are reliable enough for group comparisons (ICC 0.82 to 0.88). Perimeter
   basics is not reliable for individual decisions from one session (ICC 0.62). Use it as an
   introduction, or base decisions on more than one session.
3. The objectives, procedure and (at low difficulty) uncertainty dimensions rest on few items. In
   the AAR they are useful as feedback, but they are weak as standalone measures.
4. The adaptive policy is safe (it respects its bounds and moves one level at a time) but
   conservative. It lags improving trainees and lets mid-skill trainees drift down.
5. A controlled human study needs roughly 24 to 32 participants per group. Those figures come from
   these synthetic score distributions. The pilot in the study protocol must re-estimate the score
   SD and test–retest reliability with people before the main study is sized.

## What this study does not show

- That people learn from the simulator, or that anything learned transfers outside it.
- That the agent's behaviour resembles how people make mistakes. If people err differently, for
  example by being consistently wrong about one class, the correlations above could be lower.
- That the difficulty levels are ordered correctly in how hard they are for people.
- Anything about scenarios other than the four demo scenarios, or rubrics other than
  `standard-assessment v1`.
