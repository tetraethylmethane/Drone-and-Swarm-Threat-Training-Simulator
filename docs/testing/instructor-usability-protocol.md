# Instructor usability protocol and results (Sprint 10, workstream E)

**Status: protocol ready; no participant sessions have been run.** No instructor has used the
system under this protocol, so there are **no participant results** in this document. Section 6 is a
heuristic walkthrough by the development team. It is a design review, not user data, and must not
be reported as usability evidence.

## 1. Purpose and questions

Can a qualified instructor, without help from developers, do the instructor's core work: prepare a
scenario, assign it, follow progress, review a result and act on it? We want to know:

- Q1: whether each core task can be completed unaided (effectiveness);
- Q2: how long each task takes and how many errors occur (efficiency);
- Q3: whether instructors understand and trust what the system says about scores, evidence,
  reproducibility and adaptive difficulty (comprehension);
- Q4: perceived usability (System Usability Scale, SUS).

## 2. Participants

- 5 to 8 instructors who run counter-UAS or air-defence awareness training, or similar
  procedural training. Five participants find most severe problems in a formative test; more are
  needed for stable SUS estimates.
- Exclude anyone who took part in development or saw a demonstration.
- Recruitment, consent and any approval follow the same route as the training-effectiveness study
  (docs/research/training-effectiveness-study-protocol.md). Participation is voluntary, and results
  are not used to assess the participants.
- Record only role, years instructing and self-rated computer confidence (1–5). No names go in the
  results.

## 3. Setup

- Offline Docker deployment on a laptop (docs/operations/offline-deployment.md), HTTPS profile,
  Chromium or Edge at 1920×1080, with seeded demo scenarios and a synthetic cohort of 6 trainees with
  completed sessions. The cohort is created by script before each session; it is fictitious and
  contains no real trainee data.
- The moderator reads a fixed script and does not demonstrate. A hint is given only after 3
  minutes without progress, and it is recorded.
- Screen and audio are recorded only with consent. Recordings are deleted after analysis.

## 4. Tasks

| # | Task given to the participant | Success criterion | Time limit |
|---|---|---|---|
| T1 | Sign in with the instructor account | home page reached | 3 min |
| T2 | Find the *Perimeter basics* scenario and preview it at difficulty level 3 | planning preview shown at level 3 | 5 min |
| T3 | Create a new version of *Night loiter* with fog, and save it | new version saved and valid | 10 min |
| T4 | Assign *Perimeter basics* to two trainees, adaptive between levels 1 and 3, two attempts, due in a week | two assignments with the right settings | 6 min |
| T5 | Find which trainee had the lowest score last week | correct trainee named | 4 min |
| T6 | Open that trainee's latest result and explain why one track was marked incorrect | correct track and reason given, using the evidence or decision table | 6 min |
| T7 | Check that this result can be reproduced | verification run, outcome stated correctly | 3 min |
| T8 | Write a review with one strength and one improvement, and share it with the trainee | review saved and shared, private note not shared | 5 min |
| T9 | For an adaptive assignment, find why the level changed, then move it up one level with a reason | reason stated; override recorded | 5 min |
| T10 | Export the PDF report for one session | PDF downloaded | 3 min |

Comprehension check after T6, T7 and T9: "In your own words, what does this score, *reproducible*,
or this level change mean?" Answers are scored against the documented meaning (scoring model,
ADR-001, docs/research/adaptive-difficulty.md) as correct, partly correct or incorrect.

## 5. Measures and analysis

- Per task: completion (unaided, with a hint, or failed), time on task, errors (wrong path,
  wrong result) and hints.
- SUS (10 items) after all tasks; a short interview of 3 questions: most difficult, most useful,
  anything you would not trust.
- Problems are rated for severity: 4 means it blocks the task or causes a wrong training
  judgement; 3 means a major delay or a misunderstanding of a score; 2 is minor; 1 is cosmetic.
- **Acceptance (set before testing):** every task completed unaided by at least 80% of
  participants; no open severity-4 problem; median SUS of at least 70; no incorrect answers about
  what *reproducible* means.
- Each severity 3 or 4 problem becomes a backlog item with a reproduction and, when fixed, a
  regression test (docs/testing/known-limitations-and-backlog.md).

## 6. Heuristic walkthrough by the development team (not user data)

Method: one developer walked T1–T10 against the dev stack on 2026-10-16, checking Nielsen's
heuristics and the documented instructor workflows. Findings:

| ID | Task | Finding | Severity (estimate) | Status |
|---|---|---|---|---|
| U-01 | T9 | Instructors could not see why an adaptive assignment's level changed, because the adjustment history was shown only to the trainee, and they could not override the level from the interface (the override existed only in the API) | 4 (the task was impossible in the UI) | **Fixed**: a *Difficulty* page per adaptive assignment, linked from **Assignments**, with history, reason, confidence, the triggering session and a one-step override that requires a reason. Regression tests: `apps/web/src/features/instructor/AssignmentDifficulty.test.tsx` and `tests/integration/test_adaptive_override.py` |
| U-02 | T6 | The evidence column shows event ids; matching them to the timeline needs the Event timeline tab and a search by id | 2 | **Fixed** 2026-10-17 (B-06): evidence ids open the event in the timeline. Participant sessions will test the fixed version |
| U-03 | T5 | No sort by score on the sessions list; finding the lowest score needs Analytics or a CSV export | 2 | **Fixed** 2026-10-17 (B-07): sort by score. Participant sessions will test the fixed version |

U-01 was a defect with a clear expected behaviour and was fixed first. U-02 and U-03 were then
fixed as low-risk improvements (2026-10-17). Whether any of these mattered to instructors is for
the participant sessions to show; they are not evidence of usability.

## 6a. Scripted walkthrough, 2026-10-19 (not user data)

Method: a Playwright script (`tests/e2e/usability/walkthrough.spec.ts`) performed T1–T10 on the
development stack at 1920×1080, finding every control by its **visible label** as a newcomer would,
with a full-page screenshot at the end of each task; the screenshots were then reviewed against
Nielsen's heuristics. This shows that each task **can** be done through the interface and how many
actions it takes. It says nothing about whether instructors find the way, understand what they see,
or trust it (Q2–Q4), and it gives no SUS score. Selector mistakes in the script needed four reruns;
those were defects of the script, not of the interface, and are not counted as findings.

| Task | Through the interface | Actions |
|---|---|---|
| T1 | Completed | 3 |
| T2 | Completed | 4 |
| T3 | Completed | 5 |
| T4 | Completed | 13 |
| T5 | Completed | 2 |
| T6 | Completed | 2 |
| T7 | Completed | 2 |
| T8 | Completed | 6 |
| T9 | Completed | 4 |
| T10 | Completed | 2 |

Times are not reported: a script acts in milliseconds, and its timings say nothing about people.

| ID | Task | Finding | Severity (estimate) | Status |
|---|---|---|---|---|
| U-04 | T6 | The track-decision table in the after-action review labelled columns "**Your** classification" and "**Your** response" also in the instructor's view of a trainee's session, which reads as if the instructor made those decisions | 2 | **Fixed** 2026-10-19: "Classification given", "Response given" |
| U-05 | T9 | At the lowest allowed level the disabled button read "Lower to level **0**", a level that does not exist (likewise "Raise to level 6" at the top) | 2 | **Fixed** 2026-10-19: "Lower (level 1 is the minimum)"; unit test updated |
| U-06 | T5 | No date filter on Sessions and reviews: "lowest score last week" needs the score sort plus reading the Created column | 2 | Open (backlog B-26) |
| U-07 | T2, T3 | In the scenario list only the "Open" link opens a scenario; the scenario name is plain text | 1 | Open (backlog B-26) |
| — | T7 | Verification result is clear: "Reproduced" with three plain-language checks | — | No change |
| — | T4 | Choosing a scenario sets the level choices to its allowed range; the button names the number of trainees ("Assign to 2 trainees") | — | No change |

No severity 3 or 4 problem was found by this method. That is a weak statement: the protocol's
severity 4 ("causes a wrong training judgement") is about understanding, which a script cannot test.

## 7. Status

| Item | Status |
|---|---|
| Protocol, tasks, measures, acceptance criteria | Complete |
| Synthetic cohort script for sessions | Planned (uses `tests/load/create_users.py` patterns) |
| Participant recruitment and consent route | **Blocked**: needs the deploying organisation |
| Participant sessions and results | **Not run** |
| Heuristic walkthrough | Done (development team; not user data) |
| Scripted walkthrough of T1–T10 | Done 2026-10-19: all ten tasks possible through the interface; U-04, U-05 fixed; U-06, U-07 open (not user data) |
