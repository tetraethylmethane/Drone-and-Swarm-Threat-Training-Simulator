"""Simulation-based validation of the Drikr assessment instrument.

SYNTHETIC STUDY. This does not measure whether training improves human performance. It tests
whether the *measurement* behaves as an assessment should, using scripted agents whose skill is
known, run through the real simulation engine (drikr_simcore) and scoring engine (drikr_scoring):

  E1 construct validity     score rises with true skill (rank correlation, per scenario and dimension)
  E2 discrimination         adjacent skill bands are separated (Cohen's d)
  E3 test-retest            same agent, different scenario seed -> ICC(A,1) and standard error of measurement
  E4 difficulty sensitivity score falls as difficulty level rises, at fixed skill
  E5 adaptive difficulty    improving agents move up, weak agents do not, bounds always respected
  E6 power analysis         cohort size needed to detect a learning gain, single-arm and controlled

Agent model (deliberately simple, documented in docs/research/assessment-validation.md): skill s in
[0, 1] controls miss rate, decision delay, classification accuracy, use of the predefined response
the rubric expects, use of sensor confirmation and confidence calibration under weak evidence.

Run:  .venv/Scripts/python research/assessment_validation/run_validation.py [--quick]
Writes research/assessment_validation/results.json; the report in docs/research/ is written by hand
from that file.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import statistics
import sys
import time
import uuid
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from drikr_contracts import Scenario
from drikr_scoring import SCORING_ENGINE_VERSION, Rubric, load_default_rubrics, score_session, stats
from drikr_scoring.adaptive import SessionOutcome, recommend_level
from drikr_scoring.engine import evaluate_tree
from drikr_simcore import (
    ENGINE_VERSION,
    GroundTruthIndex,
    generate_timeline,
    load_demo_scenarios,
    sensor_confirmation_event,
)
from drikr_simcore.rng import Rng

OUT_JSON = Path(__file__).with_name("results.json")
SCENARIOS = {d["key"]: d for d in load_demo_scenarios()}
RUBRIC = Rubric.model_validate(load_default_rubrics()[0])
LABELS = ["small_multirotor", "fixed_wing_uas", "coordinated_swarm", "bird_or_clutter", "unknown"]
RESPONSES = ["continue_monitoring", "request_sensor_confirmation", "report_to_exercise_control", "log_as_cleared"]
DIMS = ["recognition", "timing", "consistency", "uncertainty", "objectives", "procedure"]
MASTER_SEED = 20261015


@dataclass(frozen=True)
class Job:
    scenario: str
    seed: int
    level: int
    skill: float
    behaviour_seed: int


def _evidence(track: Any, confirmations: list[dict[str, Any]], t_ms: int) -> float:
    best = 0.0
    for o in track.observations:
        if o["available_at_ms"] <= t_ms and o.get("class_hint") is not None:
            best = max(best, float(o["quality"]))
    for c in confirmations:
        if c["available_at_ms"] <= t_ms and c["payload"]["outcome"] == "hint_available":
            best = max(best, float(c["payload"]["quality"]))
    return best


def play(job: Job) -> dict[str, Any]:
    """One synthetic session: generate the timeline, act as the agent, score with the real engine."""
    scn = Scenario.model_validate(SCENARIOS[job.scenario])
    tl = generate_timeline(scn, seed=job.seed, difficulty_level=job.level)
    idx = GroundTruthIndex(tl.events)
    rng = Rng.stream(job.behaviour_seed, "agent")
    s = job.skill
    end = tl.duration_ms
    added: list[dict[str, Any]] = []  # trainee actions and the system events they cause

    def act(t: int, track_id: str, etype: str, body: dict[str, Any]) -> str:
        aid = str(uuid.UUID(int=Rng.stream(job.behaviour_seed, "action", len(added)).next_u64()))
        payload = {"client_action_id": aid, "track_ids": [track_id], **body, "note": None}
        added.append(
            {
                "t_ms": t,
                "available_at_ms": t,
                "type": etype,
                "visibility": "trainee",
                "origin": "trainee",
                "payload": payload,
            }
        )
        return aid

    for tr in sorted(idx.observable_tracks(end), key=lambda t: t.track_id):
        ent = idx.entities[tr.entity_id]
        if rng.chance(0.5 * (1 - s)):
            continue  # track never attended to
        delay_s = math.exp(rng.gauss(math.log(6 + 60 * (1 - s)), 0.35))
        t = ((tr.first_available_ms or 0) + int(delay_s * 1000)) // 100 * 100
        if t >= end - 1000:
            continue
        confs: list[dict[str, Any]] = []
        hint = None
        if _evidence(tr, confs, t) < RUBRIC.uncertainty.evidence_threshold and rng.chance(0.8 * s):
            aid = act(t, tr.track_id, "response_submitted", {"response": "request_sensor_confirmation"})
            c = sensor_confirmation_event(scn, job.seed, job.level, idx, tr.track_id, t, uuid.UUID(aid))
            added.append(c)
            confs.append(c)
            t = min(c["available_at_ms"] + 1000, end - 100)
            hint = c["payload"]["class_hint"]
        weak = _evidence(tr, confs, t) < RUBRIC.uncertainty.evidence_threshold
        if hint is not None and rng.chance(0.5 + 0.5 * s):
            cls = hint
        else:
            p_correct = (0.15 + 0.8 * s) * (0.75 if weak else 1.0)
            cls = (
                ent.entity_class if rng.chance(p_correct) else rng.choice([x for x in LABELS if x != ent.entity_class])
            )
        conf = "low" if weak and rng.chance(s) else ("medium" if rng.chance(0.3) else "high")
        facts = {
            "true_class": ent.entity_class,
            "cooperative": ent.cooperative,
            "behavior": ent.behavior,
            "closest_range_m": ent.closest_range_m,
            "beacon_observed": any(o.get("beacon") is True for o in tr.observations),
            "swarm_member": ent.swarm_id is not None,
        }
        leaf, _ = evaluate_tree(RUBRIC.decision_tree, facts)
        resp = leaf.expected[0].value if rng.chance(0.25 + 0.7 * s) else rng.choice(RESPONSES)
        # Procedural lapse: a less skilled agent sometimes reports or clears at once, before classifying.
        if resp in ("report_to_exercise_control", "log_as_cleared") and rng.chance(0.6 * (1 - s)):
            # The classification follows one second later: the engine treats a classification in the
            # same 100 ms tick as the report as compliant, so a same-tick lapse would go undetected.
            act(t, tr.track_id, "response_submitted", {"response": resp})
            if t + 1000 < end:
                act(t + 1000, tr.track_id, "classification_submitted", {"classification": cls, "confidence": conf})
            continue
        act(t, tr.track_id, "classification_submitted", {"classification": cls, "confidence": conf})
        t_resp = t + (12000 if resp == "log_as_cleared" else 2000)
        if t_resp < end:
            act(t_resp, tr.track_id, "response_submitted", {"response": resp})

    events = [dict(e) for e in tl.events]
    seq = max(e["seq"] for e in events) + 1
    for i, e in enumerate(sorted(added, key=lambda e: (e["t_ms"], e["origin"] != "trainee"))):
        events.append({**e, "seq": seq + i, "event_id": f"SYN-{i:05d}"})
    res = score_session(events, scn, RUBRIC, end)
    return {
        **asdict(job),
        "overall": res["overall"],
        "dims": {d: (res["dimensions"].get(d) or {}).get("score") for d in DIMS},
        "observable_tracks": res["counts"]["observable_tracks"],
    }


# --- helpers -----------------------------------------------------------------------------------


def run_all(jobs: list[Job], workers: int) -> list[dict[str, Any]]:
    if workers <= 1:
        return [play(j) for j in jobs]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(play, jobs, chunksize=4))


def r2(x: float | None, nd: int = 3) -> float | None:
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(x, nd)


def default_level(key: str) -> int:
    return int(SCENARIOS[key]["difficulty"]["level"])


def bounds(key: str) -> tuple[int, int]:
    d = SCENARIOS[key]["difficulty"]
    return int(d["min_level"]), int(d["max_level"])


def scored(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r["overall"] is not None]


def permutation_p(a: Sequence[float], b: Sequence[float], rng: Rng, n_perm: int = 2000) -> float:
    """Two-sided permutation test for a difference in means."""
    obs = abs(stats.mean(a) - stats.mean(b))
    pool = list(a) + list(b)
    hits = 0
    for _ in range(n_perm):
        sh = rng.shuffled(pool)
        if abs(stats.mean(sh[: len(a)]) - stats.mean(sh[len(a) :])) >= obs - 1e-12:
            hits += 1
    return (hits + 1) / (n_perm + 1)


# --- experiments -------------------------------------------------------------------------------


def experiment_1_2_3(n_agents: int, workers: int) -> dict[str, Any]:
    """Each agent (uniform skill) plays every scenario twice with different scenario seeds."""
    rng = Rng.stream(MASTER_SEED, "agents")
    skills = [round(rng.uniform(0, 1), 3) for _ in range(n_agents)]
    jobs = []
    for a, s in enumerate(skills):
        for key in SCENARIOS:
            for rep in (0, 1):
                jobs.append(Job(key, 10_000 + a * 10 + rep, default_level(key), s, MASTER_SEED + a * 100 + rep))
    rows = run_all(jobs, workers)

    out: dict[str, Any] = {"n_agents": n_agents, "sessions": len(rows), "scenarios": {}}
    for key in SCENARIOS:
        rs = [r for r in rows if r["scenario"] == key]
        first = scored([r for r in rs if (r["behaviour_seed"] - MASTER_SEED) % 100 == 0])
        sc: dict[str, Any] = {
            "level": default_level(key),
            "insufficient_data": len(rs) - len(scored(rs)),
            "mean": r2(stats.mean([r["overall"] for r in first]), 1),
            "spearman_skill_overall": r2(stats.spearman([r["skill"] for r in first], [r["overall"] for r in first])),
            "dimension_spearman": {},
            "floor_pct": r2(100 * sum(r["overall"] <= 5 for r in first) / len(first), 1),
            "ceiling_pct": r2(100 * sum(r["overall"] >= 95 for r in first) / len(first), 1),
        }
        for d in DIMS:
            pts = [(r["skill"], r["dims"][d]) for r in first if r["dims"][d] is not None]
            sc["dimension_spearman"][d] = {
                "n": len(pts),
                "rho": r2(stats.spearman([p[0] for p in pts], [p[1] for p in pts])) if len(pts) >= 5 else None,
            }
        bands = {"low": (0, 1 / 3), "mid": (1 / 3, 2 / 3), "high": (2 / 3, 1.01)}
        bscores = {b: [r["overall"] for r in first if lo <= r["skill"] < hi] for b, (lo, hi) in bands.items()}
        sc["bands"] = {
            b: {"n": len(v), "mean": r2(stats.mean(v), 1), "sd": r2(stats.sd(v), 1)} for b, v in bscores.items()
        }
        sc["cohen_d_mid_vs_low"] = r2(stats.cohen_d(bscores["low"], bscores["mid"]), 2)
        sc["cohen_d_high_vs_mid"] = r2(stats.cohen_d(bscores["mid"], bscores["high"]), 2)
        by_agent: dict[float, list[float]] = {}
        for r in sorted(scored(rs), key=lambda r: r["behaviour_seed"]):
            by_agent.setdefault((r["behaviour_seed"] - MASTER_SEED) // 100, []).append(r["overall"])
        pairs = [(v[0], v[1]) for v in by_agent.values() if len(v) == 2]
        icc = stats.icc_a1(pairs)
        diffs = [b - a for a, b in pairs]
        sc["retest"] = {
            "pairs": len(pairs),
            "icc_a1": r2(icc),
            "sem": r2(stats.sd(diffs) / math.sqrt(2), 1),  # standard error of measurement from pair differences
            "mean_abs_diff": r2(stats.mean([abs(d) for d in diffs]), 1),
        }
        out["scenarios"][key] = sc
    all_first = scored([r for r in rows if (r["behaviour_seed"] - MASTER_SEED) % 100 == 0])
    out["pooled_spearman_skill_overall"] = r2(
        stats.spearman([r["skill"] for r in all_first], [r["overall"] for r in all_first])
    )
    return out


def experiment_4(per_cell: int, workers: int) -> dict[str, Any]:
    jobs = []
    for key in SCENARIOS:
        lo, hi = bounds(key)
        for s in (0.3, 0.6, 0.9):
            for lvl in range(lo, hi + 1):
                for i in range(per_cell):
                    jobs.append(Job(key, 50_000 + i, lvl, s, MASTER_SEED + 7_000_000 + i * 31 + lvl))
    rows = scored(run_all(jobs, workers))
    out: dict[str, Any] = {"per_cell": per_cell, "scenarios": {}}
    for key in SCENARIOS:
        rs = [r for r in rows if r["scenario"] == key]
        cells = {}
        for s in (0.3, 0.6, 0.9):
            sub = [r for r in rs if r["skill"] == s]
            cells[str(s)] = {
                "mean_by_level": {
                    str(lv): r2(stats.mean([r["overall"] for r in sub if r["level"] == lv]), 1)
                    for lv in sorted({r["level"] for r in sub})
                },
                "spearman_level_overall": r2(stats.spearman([r["level"] for r in sub], [r["overall"] for r in sub])),
            }
        out["scenarios"][key] = cells
    return out


def experiment_5(n_agents: int, sessions: int, workers: int) -> dict[str, Any]:
    """Adaptive difficulty with the production policy. Sessions run sequentially per agent."""
    key = "demo-perimeter-basics"
    lo, hi = bounds(key)
    profiles: dict[str, Callable[[int], float]] = {
        "constant_0.3": lambda k: 0.3,
        "constant_0.6": lambda k: 0.6,
        "constant_0.9": lambda k: 0.9,
        "improving_0.2_to_0.95": lambda k: 0.2 + 0.75 * k / (sessions - 1),
    }
    out: dict[str, Any] = {"scenario": key, "bounds": [lo, hi], "sessions": sessions, "profiles": {}}
    violations = 0
    for name, skill_at in profiles.items():
        levels = {a: [default_level(key)] for a in range(n_agents)}
        hist: dict[int, list[SessionOutcome]] = {a: [] for a in range(n_agents)}
        for k in range(sessions):
            jobs = [
                Job(
                    key,
                    80_000 + a * 1000 + k,
                    levels[a][-1],
                    round(skill_at(k), 3),
                    MASTER_SEED + 9_000_000 + a * 1000 + k,
                )
                for a in range(n_agents)
            ]
            for a, r in enumerate(run_all(jobs, workers)):
                if r["overall"] is not None:
                    hist[a].append(SessionOutcome(f"{a}-{k}", r["overall"], r["level"], f"2026-01-01T00:{k:02d}:00Z"))
                rec = recommend_level(hist[a], levels[a][-1], lo, hi)
                if not lo <= rec.recommended_level <= hi or abs(rec.recommended_level - levels[a][-1]) > 1:
                    violations += 1
                levels[a].append(rec.recommended_level)
        traj = [statistics.median(levels[a][k] for a in range(n_agents)) for k in range(sessions + 1)]
        out["profiles"][name] = {
            "median_level_by_session": traj,
            "final_level_distribution": {
                str(v): sum(levels[a][-1] == v for a in range(n_agents)) for v in range(lo, hi + 1)
            },
            "level_changes_per_agent": r2(
                stats.mean(
                    [sum(x != y for x, y in zip(levels[a], levels[a][1:], strict=False)) for a in range(n_agents)]
                ),
                2,
            ),
        }
    out["bound_or_step_violations"] = violations
    return out


def build_pool(per_skill: int, workers: int) -> dict[float, list[float]]:
    """Scores at fixed skill points across all scenarios and many seeds, used to resample cohorts."""
    grid = [round(i / 20, 2) for i in range(21)]
    jobs = []
    keys = list(SCENARIOS)
    for s in grid:
        for i in range(per_skill):
            key = keys[i % len(keys)]
            jobs.append(
                Job(key, 120_000 + i, default_level(key), s, MASTER_SEED + 11_000_000 + int(s * 100) * 10_000 + i)
            )
    pool: dict[float, list[float]] = {s: [] for s in grid}
    for r in scored(run_all(jobs, workers)):
        pool[r["skill"]].append(r["overall"])
    return pool


def experiment_6(pool: dict[float, list[float]], replicates: int) -> dict[str, Any]:
    rng = Rng.stream(MASTER_SEED, "power")
    grid = sorted(pool)

    def draw(skill: float) -> float:
        nearest = min(grid, key=lambda g: abs(g - skill))
        return rng.choice(pool[nearest])

    def cohort(n: int, gain: float) -> list[float]:
        diffs = []
        for _ in range(n):
            base = rng.uniform(0.2, 0.6)
            diffs.append(draw(min(1.0, base + gain)) - draw(base))
        return diffs

    out: dict[str, Any] = {"replicates": replicates, "alpha": 0.05, "single_arm": {}, "controlled": {}}
    for gain in (0.1, 0.2, 0.3):
        row = {}
        for n in (8, 12, 16, 24, 32):
            hits = sum(stats.sign_test_p(cohort(n, gain)) < 0.05 for _ in range(replicates))
            row[str(n)] = round(hits / replicates, 3)
        out["single_arm"][f"skill_gain_{gain}"] = row
    # Controlled design: both arms practise (control gains a smaller, practice-only amount).
    for gain_t, gain_c in ((0.2, 0.05), (0.3, 0.1)):
        row = {}
        for n in (12, 16, 24, 32):
            hits = 0
            for _ in range(replicates):
                a, b = cohort(n, gain_t), cohort(n, gain_c)
                hits += permutation_p(a, b, rng, n_perm=400) < 0.05
            row[str(n)] = round(hits / replicates, 3)
        out["controlled"][f"treatment_{gain_t}_control_{gain_c}"] = row
    # Score-scale meaning of a skill gain: mean score difference per 0.1 skill, from the pool.
    means = {s: stats.mean(v) for s, v in pool.items() if v}
    out["mean_score_by_skill"] = {str(s): r2(m, 1) for s, m in means.items()}
    out["sd_score_by_skill"] = {str(s): r2(stats.sd(v), 1) for s, v in pool.items() if len(v) > 1}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quick", action="store_true", help="small run for smoke testing")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    args = ap.parse_args(argv)
    q = args.quick
    t0 = time.time()
    results: dict[str, Any] = {
        "synthetic": True,
        "note": "Synthetic agents with known skill; evaluates the measurement, not human learning.",
        "simulation_engine": ENGINE_VERSION,
        "scoring_engine": SCORING_ENGINE_VERSION,
        "rubric": f"{RUBRIC.key} v{RUBRIC.version}",
        "master_seed": MASTER_SEED,
        "python": platform.python_version(),
        "quick": q,
    }
    print("E1-E3 construct validity, discrimination, retest", flush=True)
    results["e1_e3"] = experiment_1_2_3(12 if q else 90, args.workers)
    print("E4 difficulty sensitivity", flush=True)
    results["e4"] = experiment_4(3 if q else 12, args.workers)
    print("E5 adaptive difficulty", flush=True)
    results["e5"] = experiment_5(4 if q else 20, 6 if q else 12, args.workers)
    print("E6 power", flush=True)
    pool = build_pool(6 if q else 40, args.workers)
    results["e6"] = experiment_6(pool, 40 if q else 400)
    results["runtime_s"] = round(time.time() - t0, 1)
    OUT_JSON.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT_JSON} in {results['runtime_s']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
