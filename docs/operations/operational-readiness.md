# Operational readiness: the four activities that need people or hardware

The software side of operational readiness is tracked in `docs/testing/release-acceptance-checklist.md`.
Four items cannot be completed by the development team alone. This guide says who does what, what
the team provides, and what "done" means for each. Start item 2 first: it has the longest lead time.

| # | Activity | Owner | Lead time | Done when |
|---|---|---|---|---|
| 1 | Instructor usability study | Training manager + development team | 1–2 weeks | Results reported against the pre-set criteria; severity 3–4 problems fixed with tests |
| 2 | Training-effectiveness study | Principal investigator; ethics committee | 1–3 months for approval, then 4–8 weeks | Pilot and study reported; claims limited to what the report shows |
| 3 | Load test on the deployment server | System owner + development team | 1 day | Pass or fail against the criteria on that server; `DRIKR_MAX_ACTIVE_SESSIONS` set; minimum and recommended hardware documented |
| 4 | Independent security assessment | Security owner; external tester | 2–6 weeks including contracting | Report received; findings triaged and fixed or accepted in the risk register |

## 1. Instructor usability study

**Decisions needed from the organisation:** a sponsor who can approve a voluntary staff evaluation;
5–8 instructors who have not seen the system; a quiet room with a laptop for about 75 minutes per
person. Results must not be used to assess the participants.

**Steps**

1. Agree that the study is a service evaluation and confirm whether ethics review is needed (some
   organisations require it for any study with staff). If needed, include it in the submission for
   item 2.
2. Send each participant the information sheet; obtain signed consent before the session (template
   below). Recording screen and audio is optional and needs separate consent.
3. Prepare the laptop: the offline deployment (`docs/operations/offline-deployment.md`) with the HTTPS
   profile; run `drikr-api seed-demo --with-demo-users`; create the fictitious cohort of 6 trainees
   with completed sessions (the protocol, section 3).
4. Run the session with the fixed script and tasks T1–T10 (`docs/testing/instructor-usability-protocol.md`).
   The moderator does not demonstrate; a hint is given only after 3 minutes without progress.
5. Record, per task: completion (unaided, with a hint, failed), time, errors, hints. After the tasks:
   SUS questionnaire and the 3 interview questions.
6. Give the anonymised results sheet to the development team. Problems rated severity 3 or 4 become
   backlog items, are fixed with regression tests, and the results are reported against the criteria
   that were set before testing (80% unaided completion per task, no open severity-4 problem, median
   SUS ≥ 70, no wrong answer about what "reproducible" means).

**Consent form (template).** "I agree to take part in an evaluation of the Drikr training
simulator's instructor workflows. I understand that: participation is voluntary and I may stop at
any time without giving a reason; the evaluation assesses the software, not me; only my role,
years instructing and self-rated computer confidence are recorded, and no names appear in results;
[if ticked] my screen and voice are recorded, and recordings are deleted after analysis; anonymised
results may be published in the project's reports. ☐ I agree to take part. ☐ I agree to screen and
audio recording. Name, signature, date."

## 2. Training-effectiveness study

**Decisions needed:** a principal investigator (independent of the development team, if possible);
the approving body (a university ethics committee, or the training organisation's research or
ethics board); the trainee population and the comparison condition (for example the current
training method).

**Steps**

1. Submit the protocol (`docs/research/training-effectiveness-study-protocol.md`) with: participant
   information sheet and consent form; data-management plan (pseudonymised export
   `/reports/study.csv`, storage location, retention, who has access); the statement that only
   synthetic scenarios are used; and the analysis plan already in the protocol.
2. While waiting for approval: freeze the scenario and rubric versions for the study (record their
   ids and digests), and agree the outcome measures and assessment schedule.
3. After approval, run the **pilot** with 8–12 trainees: check feasibility, timing and the variance of
   scores.
4. Re-estimate the sample size from the pilot (the protocol's estimate is about 24–32 trainees per
   group for a moderate effect) and run the main study.
5. The investigator analyses and reports. Until that report exists, describe the product as a
   training tool; do not claim that it improves training.

## 3. Load test on the deployment server

**Decisions needed:** the server the system will run on (CPU, memory, disk, operating system), and
the largest class that will train at once.

**Steps** (about 1 hour; the server needs Docker and the project's images, and no internet)

1. Copy the repository and images to the server (`docs/operations/offline-deployment.md`).
2. Run the design-load, stress and resilience tests on the isolated load-test stack, which never
   touches the deployment's data:
   ```
   bash tests/load/run.sh load "<class size> <2 x class size>" 5m
   bash tests/load/run.sh resilience <class size>
   bash tests/load/memory.sh 3 <class size> 5m
   ```
3. Judge the results against the criteria in `docs/testing/load-resilience-report.md` §2.3 (they
   were fixed before any measurement). Record the hardware and software versions.
4. Set `DRIKR_MAX_ACTIVE_SESSIONS` in the deployment's `.env` to the largest load that met the
   criteria, and confirm that admission control refuses above it (`load-resilience-report.md` §5.8).
5. Write the minimum and recommended hardware into `docs/product/positioning.md`.

## 4. Independent security assessment

**Decisions needed:** budget and a tester (an accredited penetration-testing company, or the
organisation's own security or accreditation team); the assurance framework that applies to the
deployment, if any.

**What the development team provides**

- Scope: the web application and API (all roles), the Unity client's use of the API, the Docker
  deployment (nginx, API, PostgreSQL), backups and restore, the offline installation procedure. Out
  of scope unless agreed: the host operating system and the organisation's network.
- Documents: `docs/security/threat-model.md`, `security-controls.md`, `security-findings.md`
  (findings F-01 to F-09 and residual risks R1–R9), `data-retention.md`, the architecture decisions.
- A dedicated test deployment with test accounts for each role (administrator with MFA, instructor,
  trainee) and synthetic data only; source code access for a white-box review if wanted.
- Rules of engagement: test window, contacts, no testing against the production deployment, how to
  report a critical finding immediately.

**Afterwards:** every finding gets an entry in `security-findings.md` with severity, a fix and a
regression test, or a documented acceptance in the residual-risk register. Only after this, and
the organisation's own risk acceptance, may any assurance or accreditation wording be used.
