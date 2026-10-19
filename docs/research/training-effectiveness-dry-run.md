# Training-effectiveness study: synthetic dry run (2026-10-19)

**SYNTHETIC. No person took part.** This is a rehearsal of the study protocol
(`training-effectiveness-study-protocol.md`) with simulated participants. It shows that the study
machinery works: the protocol can be executed, and the pre-registered analysis finds an effect when
one is built in and does not when none is. **It is not evidence that training with Drikr improves
anyone's performance.** The learning in this run is an assumption of the script, not a result.

Script: `research/effectiveness_dryrun/run_dryrun.py`; raw output: `research/effectiveness_dryrun/results.json`
(master seed 20261019, 904 s).

## Method

- **Participants:** 36 per group (the protocol's target), with a starting skill
  drawn per person (experienced participants higher) and an experience flag.
- **Tests:** two level-3 scenarios per time point (*Perimeter Awareness Basics* v2, *Night Loiter
  Assessment*), played by the skill-based agents of `research/assessment_validation` through the
  real simulation and scoring engines. Parallel forms T1, T2, T3 use the same scenarios with fixed,
  different seeds; the order of T1 and T2 is counterbalanced at random.
- **Allocation:** stratified block randomisation (blocks of 4) by pre-test score above or below the
  median and by experience, as in the protocol.
- **Attrition:** 5% before the post-test, a further 10% before retention.
- **Two assumed worlds:** *effect*, where the structured programme adds twice the skill that plain
  practice does (+0.30 against +0.15 on a 0–1 scale), and *null*, where both groups gain +0.15. At
  retention 70% of the gain remains. 20 replicates of each.
- **Analysis (protocol §6):** ANCOVA on the post-test score with pre-test as covariate (adjusted
  difference, 95% CI, Hedges' g); permutation test on gain scores; ANCOVA per dimension with Holm
  correction; ANCOVA at retention.

## Results

| | Effect world | Null world |
|---|---|---|
| Primary analysis significant (p < 0.05) | **100%** of 20 | **5%** of 20 (expected 5%) |
| Permutation test on gains significant | 100% | 5% |
| Mean adjusted difference (points) | 10.6 | -0.1 |
| Mean Hedges' g | 0.97 | 0.01 |
| Retention difference significant | 85% | 0% |
| Any dimension significant after Holm | 100% | 0% |
| Mean pre-test SD (points) | 10.2 | 10.2 |

First replicate of each world, as the study would report it:

| | Effect world | Null world |
|---|---|---|
| Allocated (training / control) | 37 / 35 | 35 / 37 |
| Analysed at post-test / retention | 70 / 68 | 67 / 61 |
| Adjusted difference, 95% CI | 11.3 [6.9, 15.6], p 0.0000 | 1.3 [-2.7, 5.4], p 0.51 |
| Mean gain, training / control | 23.4 / 12.3 | 10.6 / 10.9 |

## What the dry run found

1. **The procedure can be executed as written** and produces every quantity the analysis plan
   names, from sessions scored by the real engines.
2. **The primary analysis behaves correctly** in this model: it detected the built-in effect in
   20 of 20 replicates and reported a false effect in 1 of 20 when there was none, the nominal 5%.
3. **The pre-test spread (SD about 10 points) is below the protocol's 13-point trigger** for
   enlarging the sample. Real people will differ; the pilot must re-estimate it.
4. **Protocol corrections:** the secondary analysis said "five dimensions"; the rubric has six
   (recognition, timing, consistency, uncertainty, objectives, procedure). Corrected. Blocks of 4
   within small strata leave the groups slightly unequal (37 / 35); this is normal for stratified
   blocks and should be reported, not corrected.
5. **Gaps:** the protocol's robustness analysis (a linear mixed model over the three time points)
   and its intention-to-treat handling of missing data were **not run**: no statistics package is
   installed in this environment, and complete cases were analysed instead. The study must name its
   analysis software (for example R with `lme4`, or Python with `statsmodels`) before unblinding.
6. A defect in the dry-run script itself (the effect size had the wrong sign) was found while
   checking the first run and fixed; the reported figures are from the corrected rerun.

## Limits

The simulated participants follow a simple skill model (`docs/research/assessment-validation.md`),
learning is assumed, and the agents never get tired, distracted or confused by the interface.
Real participants will be noisier, so the power here is an upper bound. Only the real study, with
ethics approval and people, can show whether training with Drikr works.
