# Training-effectiveness study protocol

**Status: draft protocol. No participant has been enrolled and no human data exists.** This document
describes how to find out whether training with the simulator improves recognition and
decision-making. It must be reviewed and approved by the organisation's research-ethics or
equivalent body before any participant is recruited.

Related: [assessment-validation.md](assessment-validation.md) (synthetic validation of the
measurement and the source of the sample-size estimates below).

## 1. Questions

**Primary.** Do trainees who complete the structured simulator programme improve their assessment
score on *unseen* scenarios more than trainees who receive the same amount of unstructured exposure?

**Secondary.**
1. Which dimensions change (recognition, timing, consistency, uncertainty handling, procedure)?
2. Are gains retained four weeks later?
3. Does adaptive difficulty change gains compared with fixed difficulty? (Exploratory; the pilot
   decides whether it is included.)
4. How do instructors and trainees rate usability and workload? (System Usability Scale, NASA-TLX)

**Out of scope.** Whether simulator performance transfers to real operations. Measuring transfer
needs a separate study with an operational criterion measure, which this product does not provide.

## 2. Design

A randomised, controlled, pre-test and post-test design with a delayed retention test, in two
stages.

```
Stage A  Pilot (n ≈ 12)        → re-estimate score SD and test–retest reliability with people,
                                 check the procedure, timings and materials
Stage B  Main study            → randomise, train, test, retest
```

| Session | Training group | Control group |
|---|---|---|
| Week 0: pre-test | Two scenarios from test set T1 (unseen) | Same |
| Weeks 1 to 3: six sessions | Assigned programme: practice scenarios with AAR review and instructor feedback | Same practice time and scenarios, but no AAR review, no feedback and no adaptive difficulty: the score only |
| Week 3: post-test | Two scenarios from test set T2 (unseen) | Same |
| Week 7: retention | Two scenarios from test set T3 (unseen) | Same |

The control group is an *active* control: equal time on the simulator. This separates the effect of
the structured programme (feedback, AAR, adaptation) from plain practice and familiarity with the
interface.

**Test sets.** T1, T2 and T3 are built with the scenario editor before the study starts. They are
parallel forms: the same entity mix, difficulty level and duration, with different seeds and
layouts. None of their scenarios is used in practice. The order of T1 and T2 is counterbalanced
across participants, so differences between the forms do not look like learning. Use level-3
scenarios: the synthetic study found the level-2 Perimeter basics scenario too unreliable for this
(ICC 0.62).

**Allocation.** Stratified block randomisation by pre-test score (above or below the median) and by
prior experience, done by someone who does not run training sessions. Instructors cannot be blind
to group. Scoring is automated, so outcome assessment is blind by construction. The study export
holds only pseudonymous codes.

## 3. Participants

**Inclusion.** Adults in the organisation's training population who give informed consent.

**Exclusion.** Prior use of the simulator beyond the induction, or involvement in building the
scenarios.

**Sample size.** From the synthetic power analysis (E6), detecting a 13-point difference in mean
gain between groups needs 24 per group for 80% power, or 32 for 90% power, at α = 0.05 two-sided.
Allowing 10% attrition, the target is **36 per group (72 in total)**.

The pilot recalculates this. If the human score SD at pre-test exceeds 13 points, or test–retest ICC
on T1 versus T2 falls below 0.7, the sample size is increased before Stage B starts. If the
organisation cannot reach the target, the study is reported as a feasibility study, not as a test
of effectiveness.

## 4. Measures

| Measure | Source | When |
|---|---|---|
| **Primary: overall assessment score** (mean of the two test scenarios) | Scoring engine current when the study starts (`scoring-1.2.0` at the time of writing), rubric `standard-assessment v1`. Both are frozen for the whole study. | Pre, post, retention |
| Dimension scores | Same | Pre, post, retention |
| Track counts (observable, classified) and objectives met | Study CSV export | Pre, post, retention |
| Classification accuracy and decision time per track | Each session's scored result (`GET /sessions/{id}/result`, item table), looked up by session, not by name | Pre, post, retention |
| Usability | System Usability Scale (10 items) | Post |
| Workload | NASA-TLX (raw) | After the first and last practice session |
| Prior experience | Short questionnaire | Enrolment |

Engine and rubric versions are recorded with every result. If either changes during the study, the
affected sessions are re-scored with the frozen version before analysis, using
`POST /sessions/{id}/verify` to confirm reproducibility.

## 5. Procedure

1. Administrator creates participant accounts. Usernames are not names, for example `s01` to `s72`.
2. Induction (20 minutes, both groups): the interface, a demo scenario, the synthetic-only notice.
3. Pre-test under standard conditions: same room or workstation type, no instructor help, and the
   session timer is not paused.
4. Practice programme as assigned. Instructors follow a written feedback script to keep delivery
   consistent.
5. Post-test and retention test as for the pre-test.
6. Data export: `GET /reports/study.csv` (staff only, audited). The export identifies participants
   only by stable codes; the analyst never receives names. A separate key, held by the study lead,
   maps codes to group allocation.

## 6. Analysis plan (fixed before unblinding)

**Primary analysis.** ANCOVA on the post-test overall score, with group as the factor and pre-test
score as covariate. Report the adjusted mean difference with its 95% CI, and Hedges' *g*.

**Robustness.** Repeat with a linear mixed model over all three time points (random intercept per
participant), and with a permutation test on gain scores.

**Secondary analyses.** The same model for each dimension, with Holm correction across the five
dimensions. The retention effect comes from the group × time interaction at week 7.

**Missing data.** Intention to treat, using all randomised participants. The mixed model uses all
available observations. Report a per-protocol analysis (participants who completed at least five of
the six practice sessions) alongside it.

**Data quality.** The study export contains only completed sessions with a score; aborted and
`insufficient_data` sessions are absent by construction and are counted from the session list. Test
sessions that were paused for a lost connection are identified from their timeline, and the primary
analysis is repeated without them. Report every exclusion.

**Reporting.** Follow the CONSORT checklist for randomised trials, including the flow diagram.
Report null results with the same detail as positive ones.

The in-product "learning gains" view (first versus latest attempt) is **not** used for the study
analysis, because it has no control group.

## 7. Ethics and data protection

- **Consent.** Written informed consent. Participants are told that the content is synthetic, that
  scores are used for research only, and that they can withdraw at any time without consequence for
  their employment or assessment.
- **No consequences.** Study scores are not used for any personnel decision. Instructors see AAR
  results as normal, but the study dataset is analysed only in pseudonymised form.
- **Data minimisation.** The study export holds a participant code, scenario, date (no time), scores
  and difficulty, plus the session seed and engine versions. Free-text notes and decisions are not exported.
- **Retention.** At the end of the study, deactivate the participant accounts and anonymise them
  with the data-retention workflow (administrator guide). The pseudonymised dataset is kept for the
  period the ethics approval allows.
- **Withdrawal.** On request, the administrator anonymises the account and the participant's rows
  are removed from the analysis dataset, unless the analysis has already been published.
- **Safety.** The simulator contains no real targeting or engagement content. Participants can stop
  a session at any time.

## 8. Threats to validity and mitigations

| Threat | Mitigation |
|---|---|
| Test forms differ in difficulty | Parallel forms, counterbalanced order, pilot check |
| Practice effects on the test scenarios | Test scenarios are never used for practice |
| Instructor differences | Scripted feedback; record instructor per session; include as a covariate if needed |
| Contamination between groups | Schedule groups separately; ask participants not to share feedback |
| Measurement reliability lower in people than in the synthetic study | The pilot re-estimates it; increase the sample or the number of test scenarios per time point |
| Scoring changes mid-study | Engine and rubric frozen; reproducibility verified |
| Ceiling effects | Use level-3 test scenarios; no ceiling effect was seen at level 3 in the synthetic study (at most 2.2% of sessions scored 95% or more) |

## 9. Responsibilities and timeline

| Role | Responsibility |
|---|---|
| Study lead | Protocol, ethics submission, allocation key, final report |
| Administrator | Accounts, scenario freeze, exports, retention at study end |
| Instructors | Practice sessions following the feedback script |
| Analyst (independent of training) | Pre-registered analysis on the pseudonymised dataset |

Indicative timeline: ethics review, then pilot (2 weeks), then Stage B recruitment and training
(about 8 weeks including retention), then analysis and report (2 weeks).

## 10. Status (Sprint 10, 2026-10-16)

| Item | Status |
|---|---|
| Protocol, analysis plan, sample-size estimates | Complete (draft for ethics review) |
| Measurement prerequisites | **Partially verified with synthetic agents only.** *Perimeter basics* version 2 now gives a reliable single-session measure (ICC 0.85–0.87, docs/testing/perimeter-basics-report.md); records are reproducible and immutable at the database level (docs/testing/reproducibility-report.md) |
| Study export (`/reports/study.csv`, pseudonymised) | Implemented and tested (`test_study.py`) |
| Adaptive difficulty used by the adaptive arm | Retuned and tested as a policy (docs/research/adaptive-difficulty.md); its effect on learning is **a hypothesis** this study would test |
| Scenario freeze for the study | Planned: freeze the scenario and rubric versions at the start of the pilot; *Perimeter basics* v1 sessions must not be pooled with v2 |
| Ethics or equivalent approval | **Blocked**: needs the deploying organisation |
| Pilot | **Not run** |
| Stage B, analysis and report | **Not run** |

**No participant has been enrolled, and no human data exists.** No claim that the simulator
improves training may be made until this study, or an equivalent one, has been run and reported.
