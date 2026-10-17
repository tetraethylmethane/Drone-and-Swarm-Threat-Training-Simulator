"""Adaptive difficulty retune: compare candidate policies on synthetic trainee profiles.

Uses the synthetic agent model and the real generator and scoring engine from
research/assessment_validation/run_validation.py (documented in docs/research/assessment-validation.md).
Synthetic agents are not trainees: this checks that a policy behaves as designed, not that it helps
anyone learn. Results and the selection criteria are in docs/research/adaptive-difficulty.md.

Selection criteria (fixed before any candidate was run):
  C1  no recommendation leaves the instructor bounds or moves more than one level;
  C2  a constant weak agent (skill 0.3) ends at the minimum, and a constant strong agent (0.9) at
      the maximum, for at least 90% of agents;
  C3  a constant mid agent (0.6) averages at most 1.5 level changes and at most 30% drift to level 1;
  C4  the improving agent reaches a higher level no later than under the current policy, and the
      declining agent is lowered no later than under the current policy;
  C5  a single failed session among adequate ones lowers the level in at most 5% of cases.

    python research/adaptive_retune/run_retune.py [--agents 40] [--sessions 10] [--workers N]
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assessment_validation"))
import run_validation as v

from drikr_scoring.adaptive import AdaptivePolicy, SessionOutcome, recommend_level

KEY = "demo-perimeter-basics"
OUT = Path(__file__).with_name("results.json")
OUTLIER_EVERY = 4  # the outlier profile fails every fourth session outright

CANDIDATES: dict[str, AdaptivePolicy] = {
    "A_current": AdaptivePolicy(demote_max_each=100, robust_demotion=False),
    "B_outlier_guard": AdaptivePolicy(demote_max_each=65, robust_demotion=False),
    "C_same_level": AdaptivePolicy(demote_max_each=100, robust_demotion=False, same_level_only=True),
    "D_guard_and_same_level": AdaptivePolicy(demote_max_each=65, robust_demotion=False, same_level_only=True),
    "E_D_with_three_sessions": AdaptivePolicy(
        demote_max_each=65, robust_demotion=False, same_level_only=True, min_sessions=3
    ),
    # Added after A-E were run and all failed C5 (post hoc; judged on the same criteria).
    "F_median_demotion": AdaptivePolicy(demote_max_each=100, robust_demotion=True),
    "G_F_and_same_level": AdaptivePolicy(demote_max_each=100, robust_demotion=True, same_level_only=True),
}


def profiles(sessions: int) -> dict[str, Callable[[int], float]]:
    span = max(1, sessions - 1)
    return {
        "constant_0.3": lambda k: 0.3,
        "constant_0.6": lambda k: 0.6,
        "constant_0.9": lambda k: 0.9,
        "improving_0.2_to_0.95": lambda k: 0.2 + 0.75 * k / span,
        "declining_0.95_to_0.2": lambda k: 0.95 - 0.75 * k / span,
        "constant_0.6_with_outliers": lambda k: 0.0 if k % OUTLIER_EVERY == OUTLIER_EVERY - 1 else 0.6,
    }


def simulate(
    policy: AdaptivePolicy,
    skill_at: Callable[[int], float],
    agents: int,
    sessions: int,
    ex: ProcessPoolExecutor,
    cache: dict[v.Job, dict[str, Any]],
) -> dict[str, Any]:
    lo, hi = v.bounds(KEY)
    levels = {a: [v.default_level(KEY)] for a in range(agents)}
    hist: dict[int, list[SessionOutcome]] = {a: [] for a in range(agents)}
    violations = 0
    outlier_decreases = outlier_cases = 0
    for k in range(sessions):
        jobs = [
            v.Job(
                KEY,
                80_000 + a * 1000 + k,
                levels[a][-1],
                round(skill_at(k), 3),
                v.MASTER_SEED + 9_000_000 + a * 1000 + k,
            )
            for a in range(agents)
        ]
        todo = [j for j in dict.fromkeys(jobs) if j not in cache]
        for j, r in zip(todo, ex.map(v.play, todo, chunksize=4), strict=True):
            cache[j] = r
        for a, j in enumerate(jobs):
            r = cache[j]
            if r["overall"] is not None:
                hist[a].append(SessionOutcome(f"{a}-{k}", r["overall"], r["level"], f"2026-01-01T00:{k:02d}:00Z"))
            rec = recommend_level(hist[a], levels[a][-1], lo, hi, policy)
            if not lo <= rec.recommended_level <= hi or abs(rec.recommended_level - levels[a][-1]) > 1:
                violations += 1
            if j.skill == 0.0 and levels[a][-1] > lo:
                outlier_cases += 1
                outlier_decreases += rec.change == "decrease"
            levels[a].append(rec.recommended_level)
    start = v.default_level(KEY)
    first_up = [next((i for i, x in enumerate(levels[a]) if x > start), None) for a in range(agents)]
    first_down = [next((i for i, x in enumerate(levels[a]) if x < start), None) for a in range(agents)]

    def med(xs: list[int | None]) -> float | None:
        got = [x for x in xs if x is not None]
        return statistics.median(got) if len(got) * 2 > len(xs) else None  # None: most agents never moved

    return {
        "median_level_by_session": [
            statistics.median(levels[a][k] for a in range(agents)) for k in range(sessions + 1)
        ],
        "final_level_distribution": {str(x): sum(levels[a][-1] == x for a in range(agents)) for x in range(lo, hi + 1)},
        "share_final_at_min": round(sum(levels[a][-1] == lo for a in range(agents)) / agents, 3),
        "share_final_at_max": round(sum(levels[a][-1] == hi for a in range(agents)) / agents, 3),
        "share_ever_at_level_1": round(sum(min(levels[a]) == 1 for a in range(agents)) / agents, 3),
        "level_changes_per_agent": round(
            statistics.fmean(
                sum(x != y for x, y in zip(levels[a], levels[a][1:], strict=False)) for a in range(agents)
            ),
            2,
        ),
        "median_session_of_first_increase": med(first_up),
        "median_session_of_first_decrease": med(first_down),
        "outlier_sessions_above_min": outlier_cases,
        "outlier_decrease_rate": round(outlier_decreases / outlier_cases, 3) if outlier_cases else None,
        "bound_or_step_violations": violations,
    }


def judge(res: dict[str, dict[str, Any]], base: dict[str, dict[str, Any]]) -> dict[str, bool | None]:
    def not_later(name: str, field: str) -> bool | None:
        mine, ref = res[name][field], base[name][field]
        if mine is None:
            return False if ref is not None else None
        return ref is None or mine <= ref

    return {
        "C1_bounds_and_steps": all(p["bound_or_step_violations"] == 0 for p in res.values()),
        "C2_weak_to_min_strong_to_max": res["constant_0.3"]["share_final_at_min"] >= 0.9
        and res["constant_0.9"]["share_final_at_max"] >= 0.9,
        "C3_mid_stable": res["constant_0.6"]["level_changes_per_agent"] <= 1.5
        and res["constant_0.6"]["share_ever_at_level_1"] <= 0.3,
        "C4_improving_not_later": not_later("improving_0.2_to_0.95", "median_session_of_first_increase"),
        "C4_declining_not_later": not_later("declining_0.95_to_0.2", "median_session_of_first_decrease"),
        "C5_single_outlier": (res["constant_0.6_with_outliers"]["outlier_decrease_rate"] or 0.0) <= 0.05,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--agents", type=int, default=40)
    ap.add_argument("--sessions", type=int, default=10)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    args = ap.parse_args(argv)
    t0 = time.time()
    cache: dict[v.Job, dict[str, Any]] = {}
    results: dict[str, Any] = {}
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for name, policy in CANDIDATES.items():
            results[name] = {
                "policy": policy.model_dump(),
                "profiles": {
                    p: simulate(policy, f, args.agents, args.sessions, ex, cache)
                    for p, f in profiles(args.sessions).items()
                },
            }
            print(f"{name}: done ({time.time() - t0:.0f} s)", flush=True)
    base = results["A_current"]["profiles"]
    for r in results.values():
        r["criteria"] = judge(r["profiles"], base)
    out = {
        "scenario": KEY,
        "bounds": list(v.bounds(KEY)),
        "start_level": v.default_level(KEY),
        "agents": args.agents,
        "sessions": args.sessions,
        "outlier_every": OUTLIER_EVERY,
        "sessions_played": len(cache),
        "seconds": round(time.time() - t0),
        "machine": {"platform": platform.platform(), "python": platform.python_version(), "cpus": os.cpu_count()},
        "candidates": results,
    }
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    for name, r in results.items():
        print(name, r["criteria"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
