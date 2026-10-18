"""Does the adaptive adversary target a trainee's weakness? A synthetic check (backlog B-22, ADR-012).

SYNTHETIC STUDY. Scripted agents with one *planted* weakness each play real sessions (the real
generator, scoring engine and adversary planner). This tests the planner's targeting, not whether
adversarial planning helps anyone learn.

Agents (base skill: attend 90% of tracks, classify correctly 85%, decide after about 8 s):
  bird_low     calls threat drones flying below 70 m birds, with probability 0.75       (Perimeter basics)
  slow         decides after about 40 s; misses a track that is no longer visible     (Perimeter basics)
  crowd        classifies correctly only 30% of the time when 3+ tracks appeared
               within 20 s of each other                                              (Swarm recognition)
  swarm_blind  calls swarm members small multirotors, with probability 0.75           (Swarm recognition)
  control      no planted weakness                                                    (both)
The matching tactics are low_and_slow, fast_run_in, saturation and larger_swarm.

Procedure per agent: 5 history sessions (scenario seeds differ), then the planner plans the next
session from those results. The agent plays that session twice with the same seed and behaviour:
on the planned (adapted) scenario and on the unadapted one. The difference is paired.

Hypotheses and criteria, fixed before the first run:
  H1 targeting    the matching tactic is chosen for >= 80% of agents of each weakness type
  H2 specificity  control agents are adapted in <= 20% of cases
  H3 exposure     the weakness-specific error rate is higher on the adapted session: paired mean
                  difference > 0 with a 95% bootstrap interval excluding 0

    python research/adversary_eval/run_eval.py [--agents 40] [--workers N]
Writes research/adversary_eval/results.json; the report is docs/research/adaptive-adversary-evaluation.md.
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
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from drikr_contracts import Scenario
from drikr_scoring import Rubric, load_default_rubrics, score_session
from drikr_simcore import GroundTruthIndex, generate_timeline, load_demo_scenarios
from drikr_simcore.adversary import ADVERSARY_ENGINE_VERSION, plan_adversary
from drikr_simcore.rng import Rng

OUT = Path(__file__).with_name("results.json")
SCENARIOS = {d["key"]: d for d in load_demo_scenarios()}
RUBRIC = Rubric.model_validate(load_default_rubrics()[0])
LABELS = ["small_multirotor", "fixed_wing_uas", "coordinated_swarm", "bird_or_clutter", "unknown"]
DRONES = {"small_multirotor", "fixed_wing_uas", "coordinated_swarm"}
HISTORY = 5
LEVEL = 2
MATCH = {"bird_low": "low_and_slow", "slow": "fast_run_in", "crowd": "saturation", "swarm_blind": "larger_swarm"}
WHERE = {
    "bird_low": ["demo-perimeter-basics"],
    "slow": ["demo-perimeter-basics"],
    "crowd": ["demo-swarm-recognition"],
    "swarm_blind": ["demo-swarm-recognition"],
    "control": ["demo-perimeter-basics", "demo-swarm-recognition"],
}


def _visible(track: Any, t: int) -> bool:
    return any(t - 8000 < o["available_at_ms"] <= t for o in track.observations)


def play(scn: Scenario, seed: int, kind: str, behaviour_seed: int) -> dict[str, Any]:
    """One session by an agent with a planted weakness; returns the stored-result shape + metrics."""
    tl = generate_timeline(scn, seed=seed, difficulty_level=LEVEL)
    idx = GroundTruthIndex(tl.events)
    rng = Rng.stream(behaviour_seed, "agent", kind)
    end = tl.duration_ms
    tracks = sorted(idx.observable_tracks(end), key=lambda t: t.track_id)
    starts = [t.first_available_ms or 0 for t in tracks]
    added: list[dict[str, Any]] = []
    for tr in tracks:
        ent = idx.entities[tr.entity_id]
        if not rng.chance(0.9):
            continue
        t0 = tr.first_available_ms or 0
        delay = math.exp(rng.gauss(math.log(40.0 if kind == "slow" else 8.0), 0.3))
        t = (t0 + int(delay * 1000)) // 100 * 100
        if t >= end - 1000 or not _visible(tr, t):
            continue  # gone before the agent decided
        state = ent.state_at(t0) or {}
        threat = ent.entity_class in DRONES and not ent.cooperative
        crowded = sum(1 for s in starts if abs(s - t0) <= 20000) >= 3
        p_correct = 0.85
        cls: str | None = None
        if kind == "bird_low" and threat and ent.swarm_id is None and state.get("alt_m", 999) < 70 and rng.chance(0.75):
            cls = "bird_or_clutter"
        elif kind == "swarm_blind" and ent.swarm_id is not None and rng.chance(0.75):
            cls = "small_multirotor"
        elif kind == "crowd" and crowded:
            p_correct = 0.30
        if cls is None:
            cls = (
                ent.entity_class if rng.chance(p_correct) else rng.choice([x for x in LABELS if x != ent.entity_class])
            )
        added.append(
            {
                "t_ms": t,
                "available_at_ms": t,
                "type": "classification_submitted",
                "visibility": "trainee",
                "origin": "trainee",
                "payload": {
                    "client_action_id": f"00000000-0000-4000-8000-{len(added):012d}",
                    "track_ids": [tr.track_id],
                    "classification": cls,
                    "confidence": "medium",
                    "note": None,
                },
            }
        )
    events = [dict(e) for e in tl.events]
    seq = max(e["seq"] for e in events) + 1
    for i, e in enumerate(sorted(added, key=lambda e: e["t_ms"])):
        events.append({**e, "seq": seq + i, "event_id": f"SYN-{i:05d}"})
    res = score_session(events, scn, RUBRIC, end)
    return {"result": res, "metric": weakness_metric(kind, res)}


def weakness_metric(kind: str, res: dict[str, Any]) -> float | None:
    """Error rate on the tracks the weakness concerns (None when there are none)."""
    items = [i for i in res.get("items") or [] if i["true_class"] in DRONES and not i["cooperative"]]
    if kind in ("bird_low", "control"):
        rel = [i for i in items if not i["swarm_member"]]
        bad = [i for i in rel if i["final_classification"] == "bird_or_clutter"]
    elif kind == "slow":
        rel = items
        bad = [
            i
            for i in rel
            if i["first_classification_s"] is None or i["first_classification_s"] - i["first_available_s"] > 20
        ]
    elif kind == "crowd":
        rel = items
        bad = [i for i in rel if i["final_classification"] != i["true_class"]]
    else:  # swarm_blind
        rel = [i for i in items if i["swarm_member"]]
        bad = [i for i in rel if i["final_classification"] != i["true_class"]]
    return len(bad) / len(rel) if rel else None


def agent_run(task: tuple[str, str, int]) -> dict[str, Any]:
    kind, key, n = task
    base = Scenario.model_validate(SCENARIOS[key])
    order = Rng.stream(20261018, "eval", kind, key, n)
    history = [play(base, order.randint(0, 10**9), kind, order.randint(0, 10**9))["result"] for _ in range(HISTORY)]
    test_seed, behaviour = order.randint(0, 10**9), order.randint(0, 10**9)
    adapted, plan = plan_adversary(base, history[::-1], test_seed)  # newest first, as the server does
    a = play(adapted, test_seed, kind, behaviour)
    b = play(base, test_seed, kind, behaviour)
    return {
        "kind": kind,
        "scenario": key,
        "agent": n,
        "tactics": [t["tactic"] for t in plan["tactics"]],
        "metric_adapted": a["metric"],
        "metric_baseline": b["metric"],
        "overall_adapted": a["result"]["overall"],
        "overall_baseline": b["result"]["overall"],
    }


def bootstrap_ci(diffs: list[float], seed: int = 7, n: int = 4000) -> tuple[float, float]:
    rng = Rng.stream(seed, "bootstrap")
    means = sorted(statistics.fmean(rng.choice(diffs) for _ in diffs) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kind in WHERE:
        for key in WHERE[kind]:
            rs = [r for r in rows if r["kind"] == kind and r["scenario"] == key]
            adapted = [r for r in rs if r["tactics"]]
            tactic_counts: dict[str, int] = {}
            for r in rs:
                for t in r["tactics"]:
                    tactic_counts[t] = tactic_counts.get(t, 0) + 1
            pairs = [
                r["metric_adapted"] - r["metric_baseline"]
                for r in rs
                if r["metric_adapted"] is not None and r["metric_baseline"] is not None
            ]
            match = MATCH.get(kind)
            entry: dict[str, Any] = {
                "agents": len(rs),
                "adapted_share": round(len(adapted) / len(rs), 3) if rs else None,
                "tactic_counts": tactic_counts,
                "matching_tactic": match,
                "matching_share": round(sum(1 for r in rs if match in r["tactics"]) / len(rs), 3) if match else None,
                "metric_pairs": len(pairs),
                "metric_baseline_mean": round(
                    statistics.fmean(r["metric_baseline"] for r in rs if r["metric_baseline"] is not None), 3
                )
                if pairs
                else None,
                "metric_diff_mean": round(statistics.fmean(pairs), 3) if pairs else None,
                "metric_diff_ci95": [round(x, 3) for x in bootstrap_ci(pairs)] if len(pairs) >= 5 else None,
                "overall_diff_mean": round(
                    statistics.fmean(
                        r["overall_adapted"] - r["overall_baseline"]
                        for r in rs
                        if r["overall_adapted"] is not None and r["overall_baseline"] is not None
                    ),
                    2,
                )
                if rs
                else None,
            }
            if match:
                entry["H1_met"] = entry["matching_share"] >= 0.8
                ci = entry["metric_diff_ci95"]
                entry["H3_met"] = bool(ci and ci[0] > 0)
            else:
                entry["H2_met"] = entry["adapted_share"] <= 0.2
            out[f"{kind}@{key}"] = entry
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", type=int, default=40)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = ap.parse_args(argv)
    tasks = [(kind, key, n) for kind, keys in WHERE.items() for key in keys for n in range(args.agents)]
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(agent_run, tasks, chunksize=2))
    out = {
        "adversary_engine": ADVERSARY_ENGINE_VERSION,
        "agents_per_type": args.agents,
        "history_sessions": HISTORY,
        "level": LEVEL,
        "sessions_played": len(rows) * (HISTORY + 2),
        "seconds": round(time.perf_counter() - t0, 1),
        "machine": {"platform": platform.platform(), "python": sys.version.split()[0], "cpus": os.cpu_count()},
        "summary": summarise(rows),
        "rows": rows,
    }
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out["summary"], indent=1))


if __name__ == "__main__":
    main()
