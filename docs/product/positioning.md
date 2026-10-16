# Product positioning

## Proposed positioning statement

> **Drikr Systems is developing an accessible, desktop-first drone-threat training and assessment
> platform designed to make virtual exercises repeatable, performance measurable and instructor
> feedback actionable.**

This is a **proposition to test**, not a claim of superiority. The competitor review
([competitor-landscape.md](../research/competitor-landscape.md)) found that public material
concentrates on immersion (VR, AR, motion platforms, real controllers), operational counter-drone
hardware and broad simulator portfolios. Public material says little about how assessments are
produced, checked and audited. That gap in *public documentation* is not evidence that competitors
lack those capabilities.

## What Drikr is not trying to be

- A high-fidelity flight or sensor-physics simulator. Established simulation vendors lead here, and
  a reproducible synthetic sensor picture is enough for recognition training (ADR-001).
- An operational counter-drone system, or a source of engagement guidance. This is excluded by the
  product's safety boundaries.
- A VR-first product. VR stays an optional future client (P2), so standard desktops can be used.

## Intended users

- **Instructors** at training establishments: build exercises, assign them, review and report.
- **Trainees**: practise recognising drone and swarm threats and choosing a procedural response.
- **Administrators**: run the system offline, manage accounts, keep records trustworthy.

No user research has been done yet. These roles come from the original brief, not from interviews.

## Candidate differentiators: status and evidence

Each is a hypothesis. "Built" means implemented and covered by automated tests; it does not mean
users value it.

| | Differentiator | Built? | Evidence today | What would show it matters (not yet done) |
|---|---|---|---|---|
| A | **Evidence-driven training**: every score traceable to recorded events and a versioned rubric; competencies, recurring errors and evidence shown | Built | Evidence events per scored item (`scoring-1.2.0`); competency trends and recurring errors; `test_traceability.py`, `test_competency.py` | Instructors use the evidence in debriefs; usability study task success |
| B | **Reproducible assessment**: same configuration and seed give the same events and scores; equivalent attempts comparable | Built | 40-test reproducibility suite; cross-platform digest check; bulk report; on the live deployment, 22 of 22 sessions reproduced (2026-10-16) | Instructors rely on comparisons when making decisions |
| C | **Useful adaptive training**: transparent rules, bounded, every change explained | Built; **known weakness** | Bounds never exceeded in 960 synthetic decisions; reasons recorded. It lags improving learners (assessment validation E5) | Retune and re-validate; pilot with people |
| D | **Low-friction deployment**: desktop, offline, no special hardware | Built; measured on one machine only | See measurements below | Repeat on target hardware; time an installation by a non-developer |
| E | **Instructor-centred usability** | Partly: workflows exist, plus an in-app guide for trainees | Automated E2E for the full instructor workflow; no usability data | Structured usability test (see requirements-to-tests) |
| F | **Trustworthy records**: RBAC, MFA, validated inputs, versioned rules, audit, backup, retention | Built | Security and retention test suites; backup restored and verified 2026-10-16; audit chain intact. Tamper-*evident*, not tamper-proof | Independent security review (not done) |

## Measured deployment footprint (2026-10-16)

Measured on **one development laptop**: Intel Core i7-1355U (10 cores, 12 threads), 15.7 GB RAM,
Windows 11, Docker Desktop 27.3.1 with 12 CPUs and 7.6 GiB available to containers. These are
observations from a single machine, not guarantees for other hardware.

| Item | Measured |
|---|---|
| Container images | API 309 MB, web 72 MB, PostgreSQL 297 MB |
| Memory at idle after use | API 140 MiB, web 14 MiB, database 38 MiB |
| Restart of all containers to API ready | 10 s |
| Desktop client size | Windows 88 MB, Linux 83 MB, macOS 105 MB (Unity players) |
| Web client download | 2.8 MB built assets |
| Sign-in (password, second request) | 99 ms |
| Create session (generates the full timeline) | 516 ms |
| Feed poll during an exercise | median 46 ms, 95th percentile 64 ms (60 polls) |
| Decision submission | median 37 ms (4 decisions) |
| Finish and score (4 tracks) | 218 ms |
| PDF report | 230 ms |
| Reproducibility check of 22 sessions | 6.7 s |

The timings are client-side over HTTPS on the same machine (`scripts/measure-performance.py`). The
first request of a new client took 2.2 s, which includes connection setup. The live API reports
its own server-side figures on **System health**.

**Minimum and recommended requirements: not yet established.** Only one machine has been measured.
The figures above suggest a modest footprint (under 300 MiB of memory for the three services at
idle). Requirements should be set after measuring the intended deployment hardware and a realistic
number of concurrent trainees. No load test has been run.

## How to validate the position

1. **Demonstrations and interviews with instructors** (5 to 8): do they value reproducibility,
   traceable scoring and comparisons more than immersion? What do they use today?
2. **Structured usability test** of the instructor workflow (`requirements-to-tests.md`, R-E1).
3. **Direct verification of competitor capabilities** listed as unknown, through demonstrations or
   procurement documents (`competitive-evidence.md`, unresolved questions).
4. **Human pilot of training effectiveness** (`docs/research/training-effectiveness-study-protocol.md`).

Until these are done, the differentiators are engineering capabilities, not proven market
advantages.
