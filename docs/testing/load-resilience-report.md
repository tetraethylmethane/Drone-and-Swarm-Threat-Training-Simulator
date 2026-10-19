# Load and resilience report (Sprint 10, workstream C)

Status: **complete for one development laptop** (2026-10-16/17). Section 2 (workload assumptions
and acceptance criteria) was written on 2026-10-16 at 22:00 IST, **before** the acceptance runs in
section 5, so that the results could not shape the criteria. The exploratory runs in section 4 were
made before any criteria existed and are not judged against them.

| Criterion | Verdict on this laptop |
|---|---|
| A1, A2, A4 latency at the design load (30) | **Met in 4 of 5 runs**; failed in the first run after a host restart (5.3). Little headroom |
| A3 server-caused pauses | Met (0 in every acceptance run) |
| A5 errors | Met (0 at 30 and at 60) |
| A6 consistency and reproducibility | Met (955 of 955 sessions reproduce; 0 mismatches) |
| A7 memory | **Not met as defined** (+21% between 5-minute runs). The soak (5.9) shows why: the class-start peak (742 MiB) is released over about 3 h and memory then holds at about 295 MiB. **No leak over the 4 h observed**; 8 h not completed |
| A8 recovery | Met (API kill, database outage, unplanned host restart) |

**All results here are local development results** on one laptop (section 3). They are not a
measurement of a representative deployment and must not be quoted as deployment capacity.

## 1. Architecture under test

One API process (uvicorn, FastAPI; synchronous routes run in Starlette's 40-thread pool) behind
nginx, with PostgreSQL 17, deployed with the production images and settings
(`deploy/loadtest/docker-compose.yml`: own volume, own secrets, API as the least-privilege role).
The only setting that differs from production is the per-IP sign-in rate limit, because all
simulated trainees sign in from one address. The server is authoritative (ADR-001): each session
creation generates and stores the full timeline (about 3,700 events for Perimeter basics v2), each
feed poll reads newly available events, and completion scores the stored log.

## 2. Workload assumptions and acceptance criteria

### 2.1 Workload (assumptions to be confirmed by the deploying organisation)

No document states a concurrency requirement (roadmap item 10.6 asks for one to be established).
Assumed for this sprint:

- **Design load: 30 concurrent trainees** on one offline server, which is one classroom with one
  instructor. **Stress levels: 60 and 100.**
- Each trainee behaves like the web and Unity clients: sign in once, create a session, start, poll
  the feed every 1 s, classify each new track, finish, read the result, and repeat
  (`tests/load/k6/exercise.js`).
- **Worst case: synchronised start.** All trainees create and start sessions at the same moment,
  because an instructor tells the room to begin.

### 2.2 Why latency is a validity issue, not only a comfort issue

The server stamps a decision when the request handler starts (`routers/sessions.py`,
`now = utcnow()`), and the trainee sees a track only when a feed poll returns it. Server delay
therefore adds directly to the trainee's measured response time. Under the demo rubric, timing
credit is full at 20 s and zero at 90 s, with a timing weight of 0.15, so each second of server
delay costs about **0.2 overall points** on an affected item. Delay also pushes clients past the
15 s connection grace, and the server then pauses their exercises.

### 2.3 Acceptance criteria (fixed 2026-10-16 22:00 IST)

| ID | Criterion | Threshold at design load (30) | At stress (60) | Basis |
|---|---|---|---|---|
| A1 | Feed latency | p95 ≤ 1,000 ms; p99 ≤ 2,000 ms | reported | The client polls every 1 s; slower than that and the picture lags by more than one poll |
| A2 | Decision latency | p95 ≤ 1,000 ms | reported | With A1, keeps timing bias at p95 to ≤ 2 s (≤ about 0.4 points), far below the scenario's SEM of 8.4 points |
| A3 | Server-caused pauses | **0** sessions paused because of server delay | reported | A pause caused by the server interrupts training unfairly |
| A4 | Create session; finish and score | p95 ≤ 10 s each | reported | A one-off wait at start and end, with a progress indicator |
| A5 | Errors and timeouts (5xx, status 0) | **0** | ≤ 1% | |
| A6 | Consistency | 0 inconsistent results; **100%** of sessions reproducible after the run; audit chain valid | same | Records must stay trustworthy at any load |
| A7 | Memory | API peak RSS in a second identical run within +10% of the first; below 2 GiB | reported | Distinguishes retention from a leak |
| A8 | Recovery | API ready ≤ 60 s after being killed and ≤ 60 s after the database returns; no completed result lost; every interrupted session ends completed or resumable; 100% reproducible; audit chain valid | — | Interrupted-session rules (ADR-001) |

Criteria A5 and A6 at stress, and every reported item, describe behaviour beyond the design point.
They do not pass or fail the release.

## 3. Test environment

| Item | Value |
|---|---|
| Host | Intel Core i7-1355U (10 cores, 12 threads), 15.7 GB RAM, Windows 11 10.0.26200, on mains power with the Windows "Balanced" power plan (checked 2026-10-16 before the acceptance runs) |
| Containers | Docker Desktop 27.3.1 (WSL 2), 12 CPUs and 7.6 GiB available to containers |
| Images | `drikr-api:1.0.0` (Python 3.12.14), `drikr-web:1.0.0` (nginx 1.30.4), `postgres:17.11-alpine3.24` |
| Load generator | k6 2.3.0 (`grafana/k6:2.3.0` container on the same host and Docker network) |
| Raw results | `tests/load/results/<date>/`: k6 summaries and stdout, resource samples, database connections, reproducibility reports |

The load generator runs on the same machine as the system under test, so it competes for CPU.
Measured capacity is therefore a lower bound for this hardware.

## 4. Exploratory runs (before criteria; 2026-10-16)

Image built 14:19 UTC (after the L-01 fix, before the L-02 fix). Each run lasted 5 min with
90 s exercises, back to back on one stack without restarting the API. Latencies are client-side
from k6, in ms. "Errors" counts responses with status 5xx or 0 (timeout).

| Run | Feed med / p95 / p99 | Decision med / p95 / p99 | Create session med / p95 | Finish and score med / p95 | Errors | Sessions scored | Reproducible after the run |
|---|---|---|---|---|---|---|---|
| 10 VU | 43 / 142 / 699 | 48 / 163 / 265 | 3,648 / 5,887 | 1,226 / 4,042 | 0 of 3,567 | 38 | 42 of 42 |
| 30 VU | 263 / 1,705 / 5,035 | 487 / 1,714 / 6,432 | 9,777 / 15,950 | 3,625 / 15,143 | 0 of 6,137 | 90 | 132 of 132 |
| 60 VU | 906 / 3,771 / 9,545 | 1,079 / 5,374 / 13,756 | 15,900 / 26,503 | 6,957 / 18,310 | 1 of 7,894 | 167 | 300 of 300 |
| 100 VU | 367 / 1,844 / 7,086 | 425 / 1,294 / 1,369 | 628 / 29,999 | 5,505 / 29,999 | 609 of 5,977 (10.2%) | 30 | 355 of 355 |

| Run | API CPU max / mean | API memory max | Database CPU max | API database connections max (pool limit 40) |
|---|---|---|---|---|
| 10 VU | 268% / 43% | 332 MiB | 64% | 12 |
| 30 VU | 180% / 112% | 760 MiB | 200% | 33 |
| 60 VU | 448% / 124% | 1,057 MiB | 158% | **40** |
| 100 VU | 751% / 63% | 1,264 MiB | 92% | **40** |

Observations:

- **Mean API CPU stays near 100–125%** however many trainees there are. The single API process is
  bound by Python's interpreter lock. Session creation (timeline generation, about 0.45 s of pure
  Python) and scoring compete with every other trainee's feed polls.
- At 30 VU, against the criteria later fixed in section 2.3, this image fails A1 (feed p95
  1,705 ms), A2 and A4 (create p95 16 s). This is defect L-02 (section 6).
- At 60 and 100 VU the connection pool is saturated (40 of 40). At 100 VU, 10% of requests time
  out at 30 s: mostly session creations (p95 30 s), so most iterations end without an exercise.
  The 100 VU median of 628 ms is not an improvement: it is dominated by fast `409` responses to
  repeated creation attempts.
- **API memory rose with each run** (332 → 760 → 1,057 → 1,264 MiB) and stayed at 1,209 MiB at idle
  before the next run. There is no unbounded in-process state in the code: the rate limiter is
  keyed per user and per IP, metrics use a bounded deque, and the only cache is the settings
  object. This pattern fits allocator retention of the peak working set across 40 threads better
  than a leak, but that is a hypothesis. Criterion A7 tests it.
- **Consistency:** 100% of stored sessions reproduced after every run. The 60 VU run reported
  `drikr_inconsistent_results = 3`. A database check of every scored session at the time (333 of
  333) found the classified-track count in each result equal to the number of distinct tracks
  classified in the stored log, with no ignored decisions. So the stored record and its score
  agree. The harness then counted a track as "accepted" when its classification request failed
  (refused while paused, or timed out), which can produce exactly this report. The check was
  corrected to count only `200` responses, and it now logs the session id so any further case can
  be traced. The acceptance runs (section 5) check this again.

### 4.1 Runs excluded from the analysis

| Label | What happened | Treatment |
|---|---|---|
| `load-30vu-300s` (started 15:05 UTC; 10 min, 300 s exercises) | k6 should have stopped by about 15:17. The resource sampler recorded nothing from 15:06:26 to 15:43:21, while the Docker CLI was hanging (the daemon later stopped responding entirely). k6 was still running at 15:49 and was stopped with `docker stop`; its stdout ends "test run was aborted because k6 received a 'terminated' signal" | **Anomalous.** The duration, rates and resource series are invalid. The latencies are retained for reference only: feed p95 608 ms, create p95 22.9 s, 0 errors, 60 scored. All 30 sessions were auto-paused once (`resumed = 30`). That is consistent with L-02 at a synchronised start but could not be separated from the Docker hang. The reproducibility check afterwards is valid as a check of stored data: 423 of 423 |
| `load-30vu-300s-fixed` (16:0x UTC, image with the L-02 fix) | Ran during the Docker hang: every session creation (270) and completion (30) timed out at 30 s; 0 sessions scored. Its summary file was rewritten 4 minutes after its stdout closed; the reproducibility output is empty | **Invalid.** Says nothing about L-02 |

Docker Desktop was restarted (WSL shut down and relaunched) at 21:49 IST, with the user's approval.

## 5. Acceptance runs (2026-10-16 16:33–17:17 UTC; 2026-10-17 06:29–07:24 UTC)

**Image:** `drikr-api:1.0.0` (`288221e39d7c`, built 22:02 IST, after the L-01 and L-02 fixes and
the final adaptive policy). Before the runs, the sources that decide the results (`adaptive.py`,
`cpu.py`, `session_service.py`, `scoring_service.py`, the Perimeter basics definition) were checked
to be hash-identical inside the image and in the working tree. Default `cpu_workers = 2`.

**Procedure:** `bash tests/load/run.sh down` (empty database volume), then the runs below in
sequence with no other CPU-heavy work on the host (a coordinating development session agreed to
pause). Each run lasted 5 min with 90 s exercises and k6 `constant-vus`, so every trainee starts at
the same moment (the synchronised start in 2.1). Run 1 restarted the API first (`FRESH_API=1`);
run 2 followed immediately on the same process. The session statistics come from the database
(`*-sessions.csv`, written by `stats` in `run.sh`); the latencies are client-side from k6
(`*-k6-stdout.txt`, `*-k6-summary.json`).

### 5.1 Results against the criteria

| | Run 1: 30 VU (fresh API) | Run 2: 30 VU (same process) | Stress: 60 VU |
|---|---|---|---|
| **A1** feed p95 / p99 (ms) | 648 / 1,004 ✅ | 622 / 1,009 ✅ | 1,981 / 3,414 (reported) |
| feed median (ms) | 202 | 125 | 1,117 |
| **A2** decision p95 / p99 (ms) | 755 / 1,009 ✅ | 820 / 917 ✅ | 1,996 / 2,357 (reported) |
| **A3** sessions paused by the server (`connection_lost`) | 0 of 120 ✅ | 0 of 109 ✅ | 0 of 182 |
| **A4** create session p95 (ms) | 4,860 ✅ | 3,740 ✅ | 8,020 (reported) |
| **A4** finish and score p95 (ms) | 3,700 ✅ | 4,650 ✅ | 7,730 (reported) |
| **A5** errors and timeouts | 0 of 9,639 ✅ | 0 of 9,086 ✅ | 0 of 8,873 ✅ (≤ 1%) |
| **A6** sessions created / completed / scored / left open | 120 / 120 / 120 / 0 | 109 / 109 / 109 / 0 | 182 / 182 / 182 / 0 |
| **A6** stored log vs result mismatches; k6 inconsistencies | 0; 0 ✅ | 0; 0 ✅ | 0; 0 ✅ |
| **A6** reproducible after the run (whole database) | 120 of 120 ✅ | 229 of 229 ✅ | 411 of 411 ✅ |
| **A6** audit chain | valid ✅ | valid ✅ | valid ✅ |
| API memory, first / max / last sample (MiB) | 674 / 798 / 787 | 845 / 884 / 869 | 1,030 / 1,100 / 1,070 |
| API CPU mean / max | 107% / 367% | 93% / 311% | 132% / 553% |
| Database CPU mean / max | 27% / 109% | 24% / 116% | 37% / 147% |
| API database connections, max (pool 40) | 32 | 33 | **40** |

**A7 (memory): not met.** Run 2 peaked 10.8% above run 1 (884 against 798 MiB, container
figures), against a +10% threshold; section 5.3 measures it per process.

### 5.2 Comparison with the exploratory runs (before L-02)

| 30 VU | Before L-02 (section 4) | After (runs 1 and 2) |
|---|---|---|
| Feed p95 | 1,705 ms | 622–648 ms |
| Decision p95 | 1,714 ms | 755–820 ms |
| Create session p95 | 15,950 ms | 3,740–4,860 ms |
| Finish and score p95 | 15,143 ms | 3,700–4,650 ms |

| 60 VU | Before L-02 | After |
|---|---|---|
| Feed p95 | 3,771 ms | 1,980 ms |
| Create session p95 | 26,503 ms | 8,020 ms |
| Errors | 1 | 0 |
| Sessions paused by the server and resumed | 19 | 0 |

At 60 VU the connection pool is fully used (40 of 40), while mean API CPU is only 132%. Beyond
about 60 trainees, the next limit on this host is the single API process: request handling stays
under one interpreter lock even though timeline generation now runs in worker processes. The 100 VU
level was not repeated in the acceptance runs, because it lies beyond the stress level fixed in
section 2.

### 5.3 Memory (criterion A7) and a further design-load run

`bash tests/load/memory.sh 3 30 5m` on 2026-10-17, 06:29–07:05 UTC, after the host restart in 5.6:
the API was restarted, then three identical 30 VU runs were made back to back. Resident memory
(`VmRSS`) of each Python process inside the API container was recorded after each run and after
60 s idle (`tests/load/results/2026-10-17/memory-30vu-rss.csv`).

| Phase | API process (PID 1) | Change | Generation workers (2) | Resource tracker |
|---|---|---|---|---|
| Fresh | 116 MiB | | not started (lazy) | not started |
| After run 1 / idle 60 s | 709 / 709 MiB | +593 | 46, 47 MiB | 16 MiB |
| After run 2 / idle | 859 / 859 MiB | +150 (+21%) | 46, 47 MiB | 16 MiB |
| After run 3 / idle | 885 / 887 MiB | +26 (+3%) | 46, 47 MiB | 16 MiB |

**A7 verdict: not met as written.** The second run peaked 21% above the first (on 2026-10-16: +10.8%),
against a +10% threshold, and memory is not returned when idle. The series levels off (+593, +150,
+26 MiB), which fits allocator retention of the peak working set across the 40 request threads
better than a leak. A leak over a longer horizon is **not excluded**: three 5-minute runs are not a
training day. The workers do not grow. Peak container memory stayed below 1 GiB (2 GiB limit met).
Follow-up: backlog B-03.

**The same runs at the design load:**

| | Memory run 1 | Memory run 2 | Memory run 3 |
|---|---|---|---|
| Feed p95 (A1 ≤ 1,000 ms) | **1,977 ❌** | 620 ✅ | 498 ✅ |
| Decision p95 (A2 ≤ 1,000 ms) | **1,811 ❌** | 473 ✅ | 534 ✅ |
| Create session p95 (A4 ≤ 10 s) | **10,516 ❌** | 4,946 ✅ | 4,120 ✅ |
| Finish and score p95 (A4 ≤ 10 s) | 8,897 ✅ | 4,088 ✅ | 3,936 ✅ |
| Errors; server-caused pauses; mismatches; k6 inconsistencies | 0; 0; 0; 0 | 0; 0; 0; 0 | 0; 0; 0; 0 |
| Sessions created and scored | 90 / 90 | 110 / 110 | 119 / 119 |
| API CPU mean; database CPU mean | 152%; 47% | 97%; 25% | 101%; 27% |

**Memory run 1 failed A1, A2 and A4 at the design load.** Contributing factors, not separated:
(1) at the synchronised start the trainees also finished the 27 sessions left open by the host
restart (117 iterations for 90 new sessions), each with a full score; (2) a cold database after crash
recovery (database CPU twice that of runs 2 and 3); (3) probable host activity shortly after boot:
the resource sampler managed 44 samples against 72 in later runs, but host CPU was not measured.

**Consequence:** across the five design-load runs on the final image, the latency criteria were
met in **4 of 5**. Capacity of about 30 trainees on this laptop holds only with **little headroom**:
a burst of extra work at the start (returning trainees, a cold start) pushes it past the criteria.
Records stayed consistent in every run.

### 5.4 Resilience (criterion A8)

`bash tests/load/run.sh resilience 30`, run immediately after the stress run on the same stack: 30
trainees for 6 min; the API container was killed with `docker kill` at 90 s and restarted; the
database was stopped for 30 s two minutes later. A probe called `/health/ready` through nginx once
a second (`resilience-30vu-accept-health.csv`).

| Event (UTC) | Observed | Criterion |
|---|---|---|
| 17:01:44 API killed | `/health/ready` failed for 4 probes (502, 17:01:48–17:01:56), ready again after about 12 s | ✅ ≤ 60 s |
| 17:03:47 database stopped; 17:04:19 started | Readiness answered **503** for the whole outage (12 probes) and was **ready at the first probe after the database returned**. One client request (a session creation) did hang until its 30 s timeout | ✅ ≤ 60 s |
| End of run | 121 sessions created; **121 completed, 0 left open**; every completed session in the database has a result (0 without one) | ✅ none lost; none stuck |
| Interrupted sessions | 35 sessions were paused with `connection_lost` (clients could not poll through an outage), then resumed or finished. This is the documented interrupted-session behaviour, not a server-load pause (A3 does not apply to outages) | ✅ resumable |
| Results | 118 scored; 3 `insufficient_data`. These 3 were finished 0.5–0.8 s after starting by clients that, after an outage, found an interrupted session still open and finished it. With no track yet observable, "insufficient data" is the correct result | ✅ |
| Stored log vs result | 0 mismatches | ✅ |
| Audit chain | valid (159 events) | ✅ |
| Reproducibility | 500 of 500 checked reproduced. **The report's `--limit 500` did not cover all 532 sessions**; see the full check in 5.7 | see 5.7 |
| Client view | 822 of 9,692 requests failed (5xx or timeout), all during the two outages; 78 completions acknowledged to clients against 121 completed on the server. Requests in flight during an outage fail, and the server state stays consistent | Expected |

Not tested: a host power loss or a kill of the database container (PostgreSQL crash recovery
rather than a clean stop); a full disk; a network partition between nginx and the API that is
longer than the grace period.

### 5.5 Generation worker processes (1, 2 and 4): not measured

The comparison runs were planned after the resilience run. The `cpu_workers = 1` run
(`load-30vu-accept-w1`, started 17:11:43 UTC) was cut off at about 17:17 UTC, when the host stopped.
Its k6 summary and session statistics are empty, so it is **invalid**. The `cpu_workers = 4` run
never started. After the restart the comparison was deliberately not repeated, to limit exposure to
further Docker failures. `cpu_workers = 2` remains an unmeasured, conservative default (backlog
B-11).

### 5.6 Unplanned host restart during a run (power-loss case)

The host restarted while `load-30vu-accept-w1` was running (the last boot was 2026-10-17 09:54 IST).
Every load-test container exited with code 255, so the database was killed rather than stopped. On
`docker compose up` the next day:

| Check | Observed |
|---|---|
| PostgreSQL | Crash recovery: WAL redo for 14.3 s, end-of-recovery checkpoint, then "ready to accept connections" |
| API | Healthy 66 s after `up`, including database recovery, migrations and role provisioning |
| Sessions running at the crash | **26**, all `paused` with `connection_lost` after start-up (the sweeper backdates the pause to the last heartbeat plus grace); none left `running` |
| Atomicity | All 27 open sessions (26 paused and 1 created) hold their complete generated timeline; **0** completed sessions without a result; **0** results for an uncompleted session |
| After further use and the full reproducibility check | see 5.7 |

This partly covers backlog B-12 (host power loss and a PostgreSQL crash). It was not a controlled
test: the moment of failure was not chosen, and nothing was observed between the failure and the
restart.

### 5.7 Full reproducibility and record check of the load-test database (2026-10-17)

After all runs (including the memory runs, which also finished the 27 sessions left open by the
host restart), the whole database was checked:
`drikr-api reproducibility-report --limit 100000` (`tests/load/results/2026-10-17/full-reproducibility.json`;
394 s) plus SQL.

| Check | Result |
|---|---|
| Sessions | 955, **all completed** (none created, running or paused) |
| Completed sessions without a result | **0** |
| Results | 951 scored, 4 `insufficient_data` (sessions finished before any track was observable) |
| Reproducible: regenerated timeline equals the stored log, and re-scoring gives the stored result | **955 of 955** (exact score match 955; all `scoring-1.2.0`; 0 failures) |

This covers every session from the acceptance, stress, resilience and memory runs, the two outages
and the host restart.

### 5.8 Admission control (backlog B-01), criteria fixed 2026-10-17 15:00 IST before the run

Configuration: `DRIKR_MAX_ACTIVE_SESSIONS=30` (the design load); 60 trainees for 5 min; image with
migration `0005` and admission control. A refused trainee waits 10 s and tries again, as the web
and Unity clients let a trainee do.

| ID | Criterion | Threshold |
|---|---|---|
| B1-1 | Admitted trainees: feed, decision p95 | ≤ 1,000 ms each (A1, A2) |
| B1-2 | Admitted trainees: create session and finish p95 | ≤ 10 s (A4) |
| B1-3 | Errors and timeouts (refusals excluded) | 0 |
| B1-4 | Refusals: `503 capacity_reached` p95 | ≤ 1,000 ms |
| B1-5 | Active sessions never above the limit | API role connections and session counts consistent; every session completed and reproducible; audit chain valid |
| B1-6 | Server-caused pauses among admitted trainees | 0 |

**Run 1 (`load-60vu-admission`, image `406ecb756978`): failed, defect L-05.**

| Criterion | Measured | |
|---|---|---|
| B1-1 feed / decision p95 | 2,620 / 2,875 ms | ❌ |
| B1-2 create / finish p95 | 11.9 / 11.4 s | ❌ |
| B1-3 errors | 0 of 4,627 | ✅ |
| B1-4 refusal p95 | 11.7 s (592 refusals) | ❌ |
| B1-5 limit held | max 30 active in 220 samples; 90 created, completed and scored; 0 open; reproducible; audit valid | ✅ |
| B1-6 server-caused pauses | 0 | ✅ |

The limit held, but it did not protect the admitted trainees: API CPU averaged 237% against about
100% in the uncapped 30-trainee runs. See L-05.

**Runs 2 and 3 (after the first and second fix for L-05) and an additional configuration with
headroom.** Same 60 trainees for 5 min each. Images are from the working tree at each step (hashes
of `session_service.py` checked inside each image).

| Criterion | Run 2: cap 30, pre-check | Run 3: cap 30, in-progress slots | Additional: **cap 20**, in-progress slots |
|---|---|---|---|
| B1-1 feed / decision p95 (≤ 1,000 ms) | 1,367 / 1,559 ❌ | 1,794 / 2,092 ❌ | **818 / 732 ✅** |
| Feed / decision median | 225 / 553 | 624 / 1,057 | 98 / 131 |
| B1-2 create / finish p95 (≤ 10 s) | 12.2 / 13.0 s ❌ | 15.3 / 6.2 s ❌ | **11.5 ❌ / 5.2 s ✅** |
| B1-3 errors | 0 of 7,280 ✅ | 0 of 6,179 ✅ | 0 of 6,703 ✅ |
| B1-4 refusal p95 (≤ 1,000 ms), median | 7,750 ❌, 219 | 2,412 ❌, 753 | **1,481 ❌, 162** |
| Refusals | 751 | 787 | 1,131 |
| B1-5 limit held; records | max 30 (221 samples); 90 of 90 scored; 0 open; 500 of 500 reproducible; audit valid ✅ | max 30 (263 samples); same ✅ | max **20** (243 samples); 67 of 67; 500 of 500; ✅ |
| B1-6 server-caused pauses | 0 ✅ | 0 ✅ | 0 ✅ |
| API CPU mean | 131% | 136% | 90% |

**Verdict on B-01: implemented; criteria partly met.**

- The limit is **exact**: active sessions never exceeded the limit in any run, no error occurred,
  and every record stayed consistent and reproducible.
- With the limit at the measured capacity (30 on this laptop), admitted trainees were **not**
  protected: their latency failed B1-1 and B1-2 in all three runs. The 30-trainee runs without a
  limit (section 5.1, 5.3) showed that 30 trainees alone sit at the edge of capacity here, with feed
  p95 from 498 to 1,977 ms between identical runs. The extra 30 clients, each signing in (Argon2 is
  costly by design) and retrying every 10 s, are enough to push past it. This variation between runs
  is as large as the effect, so the three cap-30 runs cannot be ranked against each other.
- With **headroom** (limit 20), the in-exercise latency that affects scoring met the criteria
  (feed p95 818 ms, decisions 732 ms). The one-off waits at a synchronised start still did not:
  session creation p95 11.5 s and refusal p95 1.5 s. Both occur in the opening burst, when 60
  sign-ins and 20 generations coincide; medians were 4.0 s and 162 ms.
- **Operational rule:** set `DRIKR_MAX_ACTIVE_SESSIONS` **below** the largest load that met all
  criteria on the deployment host (operational-readiness.md §3), not equal to it.
- Remaining: the synchronised-start burst (B-17: stagger starts in class, more generation workers,
  or queueing sign-ins).

### 5.9 Soak test (backlog B-03), 2026-10-17

`bash tests/load/soak.sh 8 30 300`: 30 trainees continuously, with the operational configuration
(`DRIKR_MAX_ACTIVE_SESSIONS=30`, image `2f1d9cee7379`), sampling every Python process's resident
memory in the API container every 5 min (`tests/load/results/2026-10-17/soak-30vu-8h-rss.csv`). A
first start at 10:22 UTC was stopped after 1 minute because the sampler wrote no rows (a `grep`
binary-mode bug, fixed); its files are in `discarded/`.

**Outcome: 3 h 58 min of the planned 8 h.** The Docker daemon stopped responding at 14:20 UTC,
the third such failure during a sustained run on this laptop (L-04). Afterwards the WSL virtual
machine could not be shut down without administrator rights, so the post-run record checks
(session states, full reproducibility, audit chain) **could not be run**. The sessions remain in the
load-test volume and can be checked after the host is restarted. **Checked 2026-10-18 (B-18):** of
4,457 sessions in the soak, 4,428 completed and scored, 29 were still open (in progress when Docker
stopped; resumable) and none was paused for a lost connection; 5,000 of 5,000 sessions checked are
reproducible with exact score matches (the report's maximum; 5,796 in the database); the audit
chain is valid (603 entries). The memory series up to 14:16 UTC
is complete: 92 samples, no gaps.

| Time (UTC) | API process | Generation workers |
|---|---|---|
| 10:23 class start | 678 MiB | 47, 47 MiB |
| 10:42 peak | **742 MiB** | 47, 47 |
| 11:23 | 632 | |
| 12:04 | 496 | |
| 12:44 | 401 | |
| 13:25 | 311 | |
| 13:46–14:16 (last 30 min) | **292–295 MiB** | 43, 43 |

**Verdict on B-03 for the period observed: no leak.** Under unchanged load the API process
returned 450 MiB of the class-start peak over about three hours and then held steady at about
295 MiB. The rise reported in section 5.3 was this peak: those runs lasted 5 minutes and ended before
the memory was released, so A7 as defined (run-to-run peak growth over short runs) measured the
start burst, not a leak. The peak comes from concurrent session creation (each generated timeline
of about 3,700 events passes through the API process) and is now bounded by admission control.
Not covered: the second half of a training day; several class starts in one day; hosts with less
memory.

### 5.10 Synchronised class start with pre-generated first attempts (backlog B-17)

Criteria fixed 2026-10-18 before the runs. `bash tests/load/class_start.sh 30 3`: an instructor
assigns one exercise to every trainee (lt-041 onwards), the trainees sign in, and 30 s later all of
them create and start their session at the same moment, then run one 90 s exercise. Sign-ins are
before the start, so the burst measured is session creation and the first exercise. Runs alternate
between pre-generation **off** (`DRIKR_TIMELINE_CACHE_MB=0`) and **on** (64 MiB), three of each,
each from a freshly restarted API; no admission limit. Image built from commit `a30c00c`.

| ID | Criterion | Threshold |
|---|---|---|
| C1 | Session creation at the start, pre-generation on: p95 | ≤ 10 s (A4) in each of the three runs |
| C2 | Improvement | Creation p95 lower with pre-generation on than off in every pair; otherwise no improvement is claimed |
| C3 | First exercise: feed and decision p95, pre-generation on | ≤ 1,000 ms (A1, A2), reported per run |
| C4 | Errors and records | 0 errors (5xx, status 0); every session completed and scored; 0 server-caused pauses; all sessions reproducible; audit chain valid |

**Results (2026-10-18, 09:35–10:00 UTC, image `drikr-api:rc-a30c00c`; on mains power).** Two
earlier attempts were invalid because of defects in the new test script (no sessions ran; files in
`results/2026-10-18/discarded/`).

| Run (in order) | Creation p95 / median | Feed p95 / p99 | Decision p95 | Finish p95 | API CPU peak |
|---|---|---|---|---|---|
| off-1 | 10,508 / 7,980 ms | 488 / 976 | 570 | 2,536 | 336% |
| **on-1** | **3,894 / 3,552** | 465 / 1,660 | 368 | 4,817 | 143% |
| off-2 | 7,296 / 4,786 | 418 / 939 | 344 | 1,768 | 403% |
| **on-2** | **4,579 / 4,011** | 423 / 1,380 | 429 | 5,780 | 179% |
| off-3 | 7,956 / 5,020 | 479 / 1,027 | 441 | 1,846 | 312% |
| **on-3** | **7,084 / 6,747** | 442 / 1,317 | 487 | 7,711 | 138% |

| Criterion | Outcome |
|---|---|
| C1 creation p95 ≤ 10 s with pre-generation | 3.9, 4.6, 7.1 s ✅ |
| C2 lower than without, in every pair | ✅ in all three pairs (by 6.6, 2.7 and 0.9 s); one run without it failed A4 (10.5 s) |
| C3 feed and decision p95 ≤ 1,000 ms | ✅ (≤ 465 and ≤ 487 ms) |
| C4 records | ✅ 0 errors; 180 of 180 sessions completed and scored; 0 paused; 180 of 180 reproducible; audit chain valid |

**Verdict on B-17: criteria met, with a smaller gain than expected.**

- Pre-generation removed the generation work from the start (API CPU peak 138–179% against
  312–403%) and brought creation p95 within A4 in every run.
- Creation still took 3.5 to 6.7 s at the median. A single start on the idle server took 165 ms from
  a pre-generated timeline against 415 ms when generated, so 30 starts handled one after another
  account for about 5 s. The remaining cost is per-session work in the API process, most likely
  unpacking the timeline and storing its ~3,900 events; this was not profiled. It is the next
  target (B-25).
- **Finishing got slower** (p95 4.8–7.7 s against 1.8–2.5 s), still within A4. A likely reason,
  not verified: with pre-generation the starts were closer together, so the 30 finishes also
  coincided. Feed p99 also rose (1.3–1.7 s against about 1.0 s); p95 was unaffected.
- Variation between runs of the same setting is large (on-3 against on-1), as in earlier sections.

### 5.11 Second soak attempt (B-03), 2026-10-18: invalid after 3 h 50 min

`bash tests/load/soak.sh 8 30 300`, image `drikr-api:rc-a30c00c` (commit `a30c00c`), started
09:50 UTC on mains power; 87 memory samples with no gap. **From 13:41 UTC the laptop repeatedly
entered Windows Modern Standby** (display off; Kernel-Power events 506/507), for up to 45 minutes at a
time, and it ran on battery from 16:49 UTC. The "never sleep" setting on mains power does not
prevent Modern Standby. Session throughput was steady at about 1,130 per hour until then and fell
afterwards. k6 ended 40 minutes late (18:29 UTC), because the suspended periods do not count towards
its duration. **Only the first 3 h 50 min are a valid measurement.**

| Period | API process memory |
|---|---|
| 09:50 start | 658 MiB |
| 10:30 peak | **778 MiB** |
| 11:50 / 12:31 / 13:11 | 652 / 577 / 477 |
| 13:51 (end of the valid period) | **440 MiB**, still falling |
| 13:51–17:28 (standby periods) | rose to about 545 MiB |
| 17:28–18:30 (last hour, under load) | **flat at 543–548 MiB** |

Records after the run: 8,841 sessions, 8,817 completed and scored, 24 open; 22 sessions paused for a
lost connection, **all at 17:50 UTC, inside the longest standby period** (17:22–18:07 UTC); 5,000
of 5,000 checked reproducible with exact score matches; audit chain valid (1,258 entries). The k6
latency summary covers the whole run including standby (feed p95 1,312 ms, finish p95 12 s, 4
failed requests of 675,479), so it cannot be judged against the criteria.

**Verdict:** the valid period repeats the first soak (peak released steadily, no growth), and the
records stayed consistent. The rise after 13:51 began with the standby periods and levelled off;
it is not evidence of a leak, but it is not explained either. A clean 8-hour day has still **not**
been measured. A repeat must keep the machine awake (for example a keep-awake request for the
duration) and on mains power.

### 5.12 Deployment-server procedure (operational readiness §3), 2026-10-19

The procedure in `docs/operations/operational-readiness.md` §3, run on the deployment host (this
laptop, which also runs the `drikr-*` deployment) with the release images (`1.0.0-rc5`, built
uncached). Class size **20** (the laptop guidance); stress at 40. Criteria are §2.3 unchanged, with
the design load set to 20, fixed before the runs:

```
bash tests/load/run.sh load "20 40" 5m
bash tests/load/run.sh resilience 20
bash tests/load/memory.sh 3 20 5m
```

The machine was kept awake for the duration (a keep-awake request, no settings changed). The
deployment stack was idle during the runs. **The charger was disconnected during part of the
procedure** (Kernel-Power 105: off at 06:27, on at 06:57, off at 07:02 UTC), so each run is marked
with its power state; runs on battery are not judged.

| Run (UTC) | Power | Feed p95 / p99 | Decision p95 | Create / finish p95 | Errors | Records |
|---|---|---|---|---|---|---|
| load-20 (05:57–06:04) | mains | **525 / 1,071** | **400** | **4.0 / 7.9 s** | 0 | 72 of 72 scored; 0 paused; 500 of 500 reproducible; audit valid |
| load-40 (06:09–06:16) | mains | 1,577 / 2,571 | 1,503 | 5.6 / 18.5 s | 0 | 132 of 132; 500 of 500; valid |
| resilience-20 (06:20–06:28) | mains (last 80 s on battery, after both recoveries) | 835 / 2,010 | 795 | 4.5 / 13.7 s | 361 during the outages (expected) | 80 of 80 completed, 0 open; 500 of 500; valid |
| memory runs 1 and 3 | **battery** | 1,108 and 1,166 | | | 0 | 500 of 500 each; valid |
| memory run 2 | mostly mains | 557 / 1,437 | 535 | 4.2 / 11.2 s | 0 | 500 of 500; valid |

| Criterion at 20 trainees | Outcome |
|---|---|
| A1 feed p95 ≤ 1,000 ms, p99 ≤ 2,000 ms | ✅ 525 / 1,071 |
| A2 decision p95 ≤ 1,000 ms | ✅ 400 |
| A3 server-caused pauses | ✅ 0 |
| A4 create and finish p95 ≤ 10 s | ✅ 4.0 / 7.9 s |
| A5 errors | ✅ 0 |
| A6 consistency | ✅ 0 inconsistent; 500 of 500 reproducible; audit valid |
| A7 memory (three identical runs) | **Not judged**: two of the three runs were on battery. Memory over time is covered by the soaks (5.9, 5.11) |
| A8 recovery | ✅ API ready 14 s after being killed and 2 s after the database returned; every session completed; reproducible; audit valid |

**Verdict: a class of 20 meets every judged criterion on this host; 40 does not (A1, A2).**
`DRIKR_MAX_ACTIVE_SESSIONS=20` was set in the deployment's `.env` on 2026-10-19. That is the level
met here; with the same limit, admitted trainees stayed within A1 and A2 while 60 tried to connect
(5.8). Loads between 20 and 40 were not tested.

## 6. Defects found

### L-01 Connection-pool exhaustion at 10 concurrent trainees (fixed)

- **Reproduction:** an earlier version of the harness, 10 VU, on an image built on 2026-10-16 with
  the pool at `pool_size=10, max_overflow=10` and a 30 s pool timeout. The API logged
  `sqlalchemy.exc.TimeoutError: QueuePool limit of size 10 overflow 10 reached … timeout 30.00`
  (around 13:44 and 13:49 UTC); 26 k6 requests timed out at 30 s, with 4 `unhandled_error` and
  several `session_sweep_failed` log entries.
- **Root cause:** a probe on a fresh stack (10 VU, 2 min, `pg_stat_activity` sampled every 3 s)
  was dominated by `active / ClientRead` on `INSERT INTO session_events` (193 samples). The
  database was waiting for the API, which was still sending rows. Each session writes about 3,700
  events; a parameterised multi-row INSERT took about 0.7 s and held a pooled connection
  throughout, while Starlette runs up to 40 synchronous requests at once against 20 connections.
- **Fix:** timeline rows are written with `COPY` in the same transaction, so the same constraints
  and triggers apply (`session_service._copy_events`), and the pool now matches the thread limit
  (20 + 20).
- **Regression tests:** `tests/integration/test_session_creation_load.py`:
  `test_connection_pool_covers_the_worker_threads` (fails with the old 10 + 10) and
  `test_stored_timeline_is_exactly_the_generated_one` (COPY stores every field and the append-only
  trigger still fires). `test_concurrent_trainees_all_create_and_poll_sessions` is a functional
  check; it has **not** been shown to fail on the old code.
- **Evidence gap: the raw output of the reproduction was not kept.** The results folder was deleted
  twice while the load-test stack was being reset. The description above comes from the
  developer's record of the logs. The post-fix evidence is retained (`load-10vu-*`: 0 failures in
  3,567 requests).

### L-02 Session generation held the interpreter lock; feed polls starved and exercises paused (fixed)

- **Reproduction:** exploratory 30 VU run (section 4): create p95 16 s, feed p95 1.7 s. In the
  `load-30vu-300s` run every one of the 30 sessions was paused once by the server. That run is
  anomalous (section 4.1), so the pause count is supporting evidence only. The exploratory 60 VU
  run had 19 server-caused pauses.
- **Root cause:** on an unloaded API, generating a timeline is about 0.45 s of pure Python and
  finishing a session about 0.23 s, most of which went on building about 3,700 ORM objects to load
  the events. Scoring itself takes 21 ms. Under a synchronised start, generation for many trainees
  held the API process's interpreter lock long enough to delay other trainees' feed polls past the
  15 s grace, so the server paused their exercises.
- **Fix:** timeline generation (a pure, deterministic function) runs in a spawned process pool
  (`drikr_api/cpu.py`, `cpu_workers`, default 2), and scoring and verification read the events
  with a column select. Unloaded: create 0.49–0.52 s after the first call (the first call includes
  about 1.3 s to start the pool); finish 0.12–0.17 s (from 0.23 s).
- **Regression tests:** `test_generation_in_a_worker_process_matches_inline` and
  `test_api_with_worker_processes_stores_the_same_timeline` (the same digest wherever generation
  runs). The performance effect is shown by the acceptance runs (section 5.2), not by a unit test.

### L-03 Load harness over-reported inconsistent results (fixed; test defect)

- **Symptom:** `drikr_inconsistent_results = 3` in the exploratory 60 VU run.
- **Root cause:** the check counted a track as "accepted" when its classification request had been
  refused (session paused) or had timed out. The stored records were consistent: every scored
  session's classified-track count equals the distinct tracks classified in its stored log (333 of
  333 then; 0 mismatches in every acceptance run).
- **Fix:** only `200` responses count as accepted, and any inconsistency now logs the session id
  and track ids for tracing. Acceptance runs: 0.

### L-04 Docker Desktop failures during sustained runs (environment)

The Docker daemon stopped responding three times, each during a sustained load run on this laptop:
on 2026-10-16 (afternoon and evening; the host also restarted overnight) and on 2026-10-17 at 14:20
UTC, 4 hours into the soak, after which the WSL virtual machine could not be shut down without
administrator rights. It is not known whether the cause is the laptop (Docker Desktop on WSL 2,
7.6 GiB for containers), the load generator running on the same host, or the system under test.
The target deployment host should be checked with the soak test (operational-readiness.md §3). On
2026-10-16, two runs were affected and
are excluded (section 4.1). Docker Desktop was restarted. The harness cannot detect this itself.
The report treats any run with a sampling gap, or a run that outlasts its configured duration, as
invalid.

### L-05 Refused sessions did the full generation work before being refused (fixed)

- **Found by:** the admission-control acceptance run (5.8, run 1).
- **Root cause:** to keep timeline generation outside the capacity lock, the check ran after the
  session had been generated and its about 3,700 events written, and then the transaction was rolled
  back. Each of the 592 refusals cost as much as an admitted session.
- **First fix (insufficient):** a database count before generation. Run 2 improved (API CPU 131%)
  but still failed B1-1, B1-2 and B1-4: at a synchronised start all 60 requests counted zero
  *committed* sessions, so all 60 still generated timelines and 30 were refused afterwards.
- **Fix:** `session_service.creation_slot` holds a place for each creation in progress, from before
  generation until commit, and refuses when committed plus in-progress sessions reach the limit.
  The supported deployment is one API process, so this in-process count is exact. The locked
  database check (`enforce_capacity`) remains the guarantee across processes.
- **Regression tests** (`tests/integration/test_admission_control.py`):
  `test_a_refused_request_does_no_generation_work` (failed before: three refusals, three
  generations) and `test_a_simultaneous_burst_generates_only_what_can_be_admitted` (failed before:
  two simultaneous requests, two generations). `test_concurrent_requests_cannot_both_take_the_last_place`
  bypasses the in-process slot and fails with `[201, 201]` when the database lock is removed.

### Observations for the backlog (not defects in this sprint)

- **O-L1 Server delay counts against the trainee.** A decision is stamped when its handler starts,
  and a track is "seen" when a feed poll returns it, so server queueing adds to measured response
  times (section 2.2). At design load this is bounded by A1 and A2 (≤ about 0.4 points at p95). On
  an overloaded server it is not. Candidate remedies are to record the client's receive and send
  times as untrusted evidence for the AAR, or to have the API refuse new sessions above a measured
  capacity.
- **O-L2 No admission control** (addressed after Sprint 10 by B-01, section 5.8). Nothing stopped a 100th trainee from degrading the other 99
  (section 4, 100 VU). A configurable cap on concurrent running sessions would make overload
  explicit instead of slow.
- **O-L3 Capacity is per host and per process.** The supported deployment is one API process (rate
  limits, metrics and the sweeper are in-process; residual risk R3). Scaling beyond about 60
  trainees on this class of hardware would need more API processes and shared rate limits.
