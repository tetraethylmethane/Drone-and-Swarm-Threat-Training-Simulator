# Does the adaptive adversary target weaknesses? A synthetic evaluation

Status: **run once, 2026-10-18; hypotheses partly supported.** Synthetic agents only: this tests
the planner (ADR-012), not whether adversarial planning helps anyone learn.

Script and raw data: `research/adversary_eval/run_eval.py`, `research/adversary_eval/results.json`
(1,680 sessions; 461 s on Windows 11, CPython 3.12.4, 12 logical CPUs). It uses the real generator,
the real scoring engine and the planner unchanged.

## Method

Each agent has a base skill (attends 90% of tracks, classifies 85% correctly, decides after about
8 s) and **one planted weakness**:

| Agent | Weakness | Scenario | Matching tactic |
|---|---|---|---|
| `bird_low` | calls threat drones below 70 m birds (p = 0.75) | Perimeter basics | low-and-slow |
| `slow` | decides after about 40 s, and misses tracks that have gone | Perimeter basics | fast run-in |
| `crowd` | 30% correct when 3+ tracks appeared within 20 s | Swarm recognition | saturation |
| `swarm_blind` | calls swarm members small multirotors (p = 0.75) | Swarm recognition | larger swarm |
| `control` | none | both | none expected |

The saturation and larger-swarm tactics apply only to scenarios with overlapping threat groups or
a swarm, so those agents play Swarm recognition. Per agent (40 per type): 5 history sessions with
different seeds; the planner plans the next session from them; the agent then plays that session
twice with the same seed and the same decisions, once adapted and once not (a paired comparison).

**Criteria, fixed in the script before the first run:** H1 the matching tactic is chosen for ≥ 80% of
agents of each weakness; H2 control agents are adapted in ≤ 20% of cases; H3 the weakness-specific
error rate rises on the adapted session (paired mean difference > 0, 95% bootstrap interval
excluding 0).

## Results

| Agent | Adapted | Tactics chosen (of 40) | H1 matching | Weakness error rate: baseline → change [95% CI] | H3 | Overall score change |
|---|---|---|---|---|---|---|
| `bird_low` | 78% | low-and-slow 31 | **77.5% ❌** | 0.40 → **+0.113 [+0.025, +0.212]** | **✅** | −1.6 |
| `slow` | 100% | fast run-in 40 | **100% ✅** | 1.00 → 0.000 [0, 0] | ❌ (ceiling) | −0.1 |
| `crowd` | 100% | larger swarm 40, saturation 4 | **10% ❌** | 0.73 → −0.002 [−0.026, +0.028] | ❌ | −0.4 |
| `swarm_blind` | 100% | larger swarm 40, saturation 3 | **100% ✅** | 0.83 → −0.006 [−0.018, +0.006] | ❌ | −0.1 |
| `control` (Perimeter) | **0%** ✅ | none | — | 0.06 → 0 | — | 0.0 |
| `control` (Swarm) | **15%** ✅ | larger swarm 6 | — | 0.10 → 0 | — | 0.0 |

## Interpretation

- **Targeting works for clearly separable weaknesses:** slow decisions (100%), swarm blindness
  (100%) and, just below the criterion, bird confusion (77.5%: 9 of 40 agents were not adapted at
  all; why their histories fell below the evidence threshold was not analysed). Control agents were left
  alone (0% and 15%; H2 met).
- **Exposure was shown only for bird confusion:** the low-and-slow tactic raised the drone-as-bird
  rate by 11 points. For the slow agent the measure was already at its ceiling (every drone was
  decided late or missed even without adaptation), so this run cannot show an effect. For swarm
  blindness, a larger swarm adds misclassified members but leaves the *rate* unchanged: this tactic
  does not expose that weakness on a rate measure.
- **The planner cannot separate crowding from swarm weakness in swarm scenarios.** Swarm members
  always appear together, so a crowd-sensitive agent's errors look like swarm errors, and the
  larger-swarm tactic was chosen instead of saturation (H1 10%).

**Overall:** hypothesis partly supported. H1 met for 2 of 4 weaknesses (narrow miss for a third),
H2 met, H3 met for 1 of 4. These results come from agents built to have exactly these weaknesses;
real trainees' weaknesses are mixed and noisier.

## Follow-up (not done; changes must be re-evaluated against the same criteria)

- Measure crowding on non-swarm tracks only, so swarm errors do not count as crowding (backlog B-24).
- Replace or redefine larger-swarm with a tactic that raises the error *rate* of swarm-blind
  trainees, or measure swarm weakness per swarm rather than per member (B-24).
- Use a timing measure without a ceiling (for example, time to classify) for the fast run-in (B-24).
- Then repeat with trainees in the human study (B-09).
