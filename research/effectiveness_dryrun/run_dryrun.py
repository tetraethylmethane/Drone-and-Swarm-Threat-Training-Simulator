"""Dry run of the training-effectiveness study (docs/research/training-effectiveness-study-protocol.md).

SYNTHETIC. No person took part, and nothing here shows that training with Drikr improves human
performance. Simulated participants have a *skill* that changes by an amount this script assumes.
The dry run checks the study machinery, not the training:

  D1 procedure     the protocol can be executed as written: stratified block randomisation, parallel
                   test forms with counterbalanced order, attrition, the pre-registered analysis
  D2 detection     with an assumed real effect (training gains twice as much skill as plain practice),
                   how often the primary analysis detects it at n = 36 per group (power of the whole
                   pipeline, including the real simulation and scoring engines' measurement noise)
  D3 false alarms  with no effect (both groups gain the same), how often the primary analysis
                   wrongly reports one (type I error; should be close to 5%)

Test sessions are played by the agents of research/assessment_validation (same skill model) through
the real engines, at difficulty level 3, two scenarios per time point. Practice sessions are not
played: in this model learning is the assumed skill change, so playing them would add nothing.

Run:  .venv/Scripts/python research/effectiveness_dryrun/run_dryrun.py [--replicates 20] [--workers 8]
Writes research/effectiveness_dryrun/results.json.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assessment_validation"))

from run_validation import DIMS, Job, play

from drikr_scoring import stats
from drikr_simcore.rng import Rng

OUT_JSON = Path(__file__).with_name("results.json")
MASTER_SEED = 20261019
PER_GROUP = 36  # protocol §3: 32 for 90% power plus 10% attrition
LEVEL = 3  # protocol §2: level-3 test scenarios
TEST_SCENARIOS = ("demo-perimeter-basics", "demo-night-loiter")
# Parallel forms: the same scenarios and level, different (fixed) seeds per form.
FORMS = {"T1": (7101, 7102), "T2": (7201, 7202), "T3": (7301, 7302)}
ATTRITION_POST = 0.05
ATTRITION_RETENTION = 0.10
# Assumed skill changes over the six practice sessions (the "worlds" being tested).
WORLDS = {
    "effect": {"training": 0.30, "control": 0.15},  # structured programme doubles the gain
    "null": {"training": 0.15, "control": 0.15},  # programme adds nothing over practice
}
RETAINED = 0.7  # share of the gain still present at the week-7 retention test


# --- design -----------------------------------------------------------------------------------


def participants(rep: int) -> list[dict[str, Any]]:
    rng = Rng.stream(MASTER_SEED, "participants", rep)
    people = []
    for i in range(2 * PER_GROUP):
        experienced = rng.chance(0.4)
        s0 = min(0.75, max(0.1, rng.gauss(0.45 if experienced else 0.32, 0.1)))
        people.append({"id": f"P{i:03d}", "experienced": experienced, "s0": round(s0, 4)})
    return people


def randomise(people: list[dict[str, Any]], pre: dict[str, float], rep: int) -> None:
    """Stratified block randomisation (blocks of 4) by pre-test above/below median and experience."""
    rng = Rng.stream(MASTER_SEED, "allocation", rep)
    med = sorted(pre.values())[len(pre) // 2]
    strata: dict[tuple[bool, bool], list[dict[str, Any]]] = {}
    for p in people:
        strata.setdefault((pre[p["id"]] >= med, p["experienced"]), []).append(p)
    for key in sorted(strata):
        members = strata[key]
        for b in range(0, len(members), 4):
            block = ["training", "control", "training", "control"]
            for j in range(len(block) - 1, 0, -1):  # Fisher-Yates with the project's RNG
                k = int(rng.uniform(0, j + 1))
                block[j], block[k] = block[k], block[j]
            for p, arm in zip(members[b : b + 4], block, strict=False):
                p["arm"] = arm


def jobs_for(p: dict[str, Any], form: str, skill: float, rep: int) -> list[Job]:
    return [
        Job(
            scenario=scn,
            seed=seed,
            level=LEVEL,
            skill=round(min(1.0, skill), 4),
            behaviour_seed=Rng.stream(MASTER_SEED, "behaviour", rep, p["id"], form, scn).next_u64() >> 12,
        )
        for scn, seed in zip(TEST_SCENARIOS, FORMS[form], strict=True)
    ]


def summarise_test(results: list[dict[str, Any]]) -> dict[str, Any]:
    vals = [r["overall"] for r in results if r["overall"] is not None]
    dims = {}
    for d in DIMS:
        xs = [r["dims"][d] for r in results if r["dims"].get(d) is not None]
        dims[d] = sum(xs) / len(xs) if xs else None
    return {"overall": sum(vals) / len(vals) if vals else None, "dims": dims}


# --- analysis (pre-registered: protocol §6) ------------------------------------------------------


def _solve3(a: list[list[float]], b: list[float]) -> list[float]:
    m = [row[:] + [v] for row, v in zip(a, b, strict=True)]
    for c in range(3):
        piv = max(range(c, 3), key=lambda r: abs(m[r][c]))
        m[c], m[piv] = m[piv], m[c]
        for r in range(3):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c], strict=True)]
    return [m[i][3] / m[i][i] for i in range(3)]


def _t_quantile(p: float, df: int) -> float:
    """Upper quantile of Student's t (Cornish-Fisher expansion; accurate to ~1e-3 for df > 30)."""
    # Acklam-style rational approximation of the normal quantile
    q = p - 0.5
    r = q * q
    z = (
        q
        * (2.50662823884 + r * (-18.61500062529 + r * (41.39119773534 + r * -25.44106049637)))
        / (1 + r * (-8.47351093090 + r * (23.08336743743 + r * (-21.06224101826 + r * 3.13082909833))))
    )
    if abs(q) > 0.42:  # tails: refine with Newton steps on the normal CDF
        for _ in range(6):
            z -= (0.5 * math.erfc(-z / math.sqrt(2)) - p) / (math.exp(-z * z / 2) / math.sqrt(2 * math.pi))
    return z + (z**3 + z) / (4 * df) + (5 * z**5 + 16 * z**3 + 3 * z) / (96 * df**2)


def _t_two_sided_p(t: float, df: int) -> float:
    lo, hi = 0.5, 1 - 1e-12
    for _ in range(80):  # invert the quantile function
        mid = (lo + hi) / 2
        if _t_quantile(mid, df) < abs(t):
            lo = mid
        else:
            hi = mid
    return 2 * (1 - lo)


def ancova(rows: list[tuple[int, float, float]]) -> dict[str, Any]:
    """y = b0 + b1*group + b2*pre; group 1 = training. Returns the adjusted difference b1."""
    n = len(rows)
    x = [(1.0, float(g), pre) for g, pre, _ in rows]
    y = [post for _, _, post in rows]
    xtx = [[sum(r[i] * r[j] for r in x) for j in range(3)] for i in range(3)]
    xty = [sum(r[i] * v for r, v in zip(x, y, strict=True)) for i in range(3)]
    b = _solve3(xtx, xty)
    resid = [v - sum(bi * xi for bi, xi in zip(b, r, strict=True)) for r, v in zip(x, y, strict=True)]
    df = n - 3
    s2 = sum(e * e for e in resid) / df
    inv_col = _solve3(xtx, [0.0, 1.0, 0.0])  # second column of (X'X)^-1
    se = math.sqrt(s2 * inv_col[1])
    t = b[1] / se
    tq = _t_quantile(0.975, df)
    return {"n": n, "diff": b[1], "ci": [b[1] - tq * se, b[1] + tq * se], "p": _t_two_sided_p(t, df)}


def hedges_g(training: list[float], control: list[float]) -> float:
    """Training minus control, in pooled SDs, small-sample corrected (stats.cohen_d is b - a)."""
    n = len(training) + len(control)
    return stats.cohen_d(control, training) * (1 - 3 / (4 * n - 9))


def permutation_p(gains_t: list[float], gains_c: list[float], rep: int, n_perm: int = 4000) -> float:
    obs = abs(stats.mean(gains_t) - stats.mean(gains_c))
    pooled = gains_t + gains_c
    rng = Rng.stream(MASTER_SEED, "perm", rep)
    hits = 0
    for _ in range(n_perm):
        xs = pooled[:]
        for j in range(len(xs) - 1, 0, -1):
            k = int(rng.uniform(0, j + 1))
            xs[j], xs[k] = xs[k], xs[j]
        if abs(stats.mean(xs[: len(gains_t)]) - stats.mean(xs[len(gains_t) :])) >= obs - 1e-12:
            hits += 1
    return (hits + 1) / (n_perm + 1)


def holm(ps: dict[str, float]) -> dict[str, float]:
    order = sorted(ps, key=ps.get)  # type: ignore[arg-type]
    out, running = {}, 0.0
    for i, k in enumerate(order):
        running = max(running, min(1.0, (len(order) - i) * ps[k]))
        out[k] = running
    return out


# --- one replicate --------------------------------------------------------------------------------


def replicate(world: str, rep: int, ex: ProcessPoolExecutor) -> dict[str, Any]:
    people = participants(rep)
    gain = WORLDS[world]
    rng = Rng.stream(MASTER_SEED, "order-attrition", world, rep)
    for p in people:
        p["pre_form"], p["post_form"] = ("T1", "T2") if rng.chance(0.5) else ("T2", "T1")
        p["drop_post"] = rng.chance(ATTRITION_POST)
        p["drop_ret"] = p["drop_post"] or rng.chance(ATTRITION_RETENTION)

    def run(spec: list[tuple[str, str, float]]) -> dict[tuple[str, str], dict[str, Any]]:
        all_jobs, keys = [], []
        for pid, form, skill in spec:
            pj = jobs_for(next(q for q in people if q["id"] == pid), form, skill, rep)
            all_jobs += pj
            keys += [(pid, form)] * len(pj)
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for k, r in zip(keys, ex.map(play, all_jobs, chunksize=4), strict=True):
            grouped.setdefault(k, []).append(r)
        return {k: summarise_test(v) for k, v in grouped.items()}

    pre_res = run([(p["id"], p["pre_form"], p["s0"]) for p in people])
    pre = {p["id"]: pre_res[(p["id"], p["pre_form"])]["overall"] for p in people}
    randomise(people, pre, rep)
    later = []
    for p in people:
        g = gain[p["arm"]]
        if not p["drop_post"]:
            later.append((p["id"], p["post_form"], p["s0"] + g))
        if not p["drop_ret"]:
            later.append((p["id"], "T3", p["s0"] + RETAINED * g))
    res = run(later)

    def rows(form_of: Any, dim: str | None = None) -> list[tuple[int, float, float]]:
        out = []
        for p in people:
            key = (p["id"], form_of(p))
            if key not in res:
                continue
            pre_v = pre_res[(p["id"], p["pre_form"])]
            pv = pre_v["overall"] if dim is None else pre_v["dims"][dim]
            yv = res[key]["overall"] if dim is None else res[key]["dims"][dim]
            if pv is not None and yv is not None:
                out.append((1 if p["arm"] == "training" else 0, pv, yv))
        return out

    primary_rows = rows(lambda p: p["post_form"])
    primary = ancova(primary_rows)
    post_t = [y for g, _, y in primary_rows if g == 1]
    post_c = [y for g, _, y in primary_rows if g == 0]
    gains_t = [y - x for g, x, y in primary_rows if g == 1]
    gains_c = [y - x for g, x, y in primary_rows if g == 0]
    dim_p = {}
    for d in DIMS:
        r = rows(lambda p: p["post_form"], d)
        if len(r) > 10:
            dim_p[d] = ancova(r)["p"]
    retention = ancova(rows(lambda p: "T3"))
    pre_vals = list(pre.values())
    return {
        "world": world,
        "rep": rep,
        "allocated": {a: sum(1 for p in people if p["arm"] == a) for a in ("training", "control")},
        "analysed_post": len(primary_rows),
        "analysed_retention": retention["n"],
        "pre_sd": stats.sd(pre_vals),
        "pre_balance_diff": stats.mean([pre[p["id"]] for p in people if p["arm"] == "training"])
        - stats.mean([pre[p["id"]] for p in people if p["arm"] == "control"]),
        "primary": primary,
        "hedges_g": hedges_g(post_t, post_c),
        "gain_means": {"training": stats.mean(gains_t), "control": stats.mean(gains_c)},
        "permutation_p": permutation_p(gains_t, gains_c, rep),
        "dimensions_holm_p": holm(dim_p),
        "retention": retention,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replicates", type=int, default=20)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = ap.parse_args(argv)
    t0 = time.time()
    reps: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for world in WORLDS:
            for rep in range(args.replicates):
                reps.append(replicate(world, rep, ex))
                r = reps[-1]
                print(f"{world} {rep}: diff {r['primary']['diff']:.1f} p {r['primary']['p']:.3f}", flush=True)
    summary = {}
    for world in WORLDS:
        rs = [r for r in reps if r["world"] == world]
        summary[world] = {
            "replicates": len(rs),
            "primary_significant_share": sum(r["primary"]["p"] < 0.05 for r in rs) / len(rs),
            "permutation_significant_share": sum(r["permutation_p"] < 0.05 for r in rs) / len(rs),
            "mean_adjusted_diff": stats.mean([r["primary"]["diff"] for r in rs]),
            "mean_hedges_g": stats.mean([r["hedges_g"] for r in rs]),
            "mean_pre_sd": stats.mean([r["pre_sd"] for r in rs]),
            "retention_significant_share": sum(r["retention"]["p"] < 0.05 for r in rs) / len(rs),
            "any_dimension_significant_share": sum(any(p < 0.05 for p in r["dimensions_holm_p"].values()) for r in rs)
            / len(rs),
        }
    out = {
        "synthetic": True,
        "note": "Simulated participants with assumed learning; not evidence about human training.",
        "design": {
            "per_group": PER_GROUP,
            "level": LEVEL,
            "test_scenarios": TEST_SCENARIOS,
            "forms": FORMS,
            "attrition_post": ATTRITION_POST,
            "attrition_retention": ATTRITION_RETENTION,
            "worlds": WORLDS,
            "retained": RETAINED,
            "master_seed": MASTER_SEED,
        },
        "summary": summary,
        "first_replicates": [r for r in reps if r["rep"] == 0],
        "duration_s": round(time.time() - t0, 1),
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, default=list) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
