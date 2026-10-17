"""Adaptive adversary: plan the threat against a trainee's recorded weaknesses.

When an instructor enables it on an assignment, the server plans each new session's threat from
the trainee's recent scored sessions, before the timeline is generated. This is game-AI tactics
selection (utility scoring over a fixed set of tactics), **not machine learning**:

* **Evidence** comes only from stored results: per track, the true class, the trainee's final
  classification, the time to classify, whether it was a swarm member, and how crowded the
  picture was when it appeared.
* **Tactics** each target one weakness; a tactic is used only with at least ``MIN_EVIDENCE``
  relevant tracks and an error rate of at least ``THRESHOLD``, so one poor session cannot drive it.
* **Bounds**: a tactic only narrows the instructor's own ranges for non-cooperative drone groups
  (for example the lower half of the altitude range). It never goes outside them and never changes
  birds, cooperative aircraft, sensors, timing rules or the rubric.
* **Reproducibility**: the result is a valid scenario that the server stores as the session's
  effective definition, with the plan and its reasons. The timeline is then generated from it as
  usual, so verification regenerates exactly what was played. The same inputs and seed always give
  the same plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from drikr_contracts import Scenario
from drikr_contracts.enums import EntityClass
from drikr_simcore.rng import Rng

ADVERSARY_ENGINE_VERSION = "adversary-1.0.0"
#: Relevant tracks needed before a tactic may be used.
MIN_EVIDENCE = 4
#: Error rate (or, for saturation, the drop in accuracy) needed before a tactic may be used.
THRESHOLD = 0.34
MAX_TACTICS = 2
#: Seconds; classifying slower than this counts as slow (the demonstration rubric's timing target).
SLOW_S = 20.0
#: Seconds; tracks first visible this close together count as a crowded picture.
CROWD_WINDOW_S = 20.0

DRONES = {EntityClass.SMALL_MULTIROTOR.value, EntityClass.FIXED_WING_UAS.value, EntityClass.COORDINATED_SWARM.value}

TACTICS: dict[str, str] = {
    "low_and_slow": "Drones fly in the lower half of their altitude and speed ranges, to look like birds",
    "fast_run_in": "Drones fly faster and pass closer, leaving less time to decide",
    "saturation": "Threat groups arrive in the same time window, to crowd the picture",
    "larger_swarm": "Swarms use the upper half of their size range",
}


@dataclass(frozen=True)
class Observation:
    """One scored track from a previous session, as the planner sees it."""

    true_class: str
    final_classification: str | None
    delay_s: float | None
    swarm_member: bool
    cooperative: bool
    crowded: bool

    @property
    def is_threat(self) -> bool:
        return self.true_class in DRONES and not self.cooperative

    @property
    def correct(self) -> bool:
        return self.final_classification == self.true_class


def observations(results: list[dict[str, Any]]) -> list[Observation]:
    """Planner inputs from stored score results (``result["items"]``), oldest first or any order."""
    out: list[Observation] = []
    for r in results:
        items = r.get("items") or []
        starts = [i.get("first_available_s") for i in items]
        for i in items:
            t0 = i.get("first_available_s")
            t1 = i.get("first_classification_s")
            crowded = t0 is not None and sum(1 for s in starts if s is not None and abs(s - t0) <= CROWD_WINDOW_S) >= 3
            out.append(
                Observation(
                    true_class=str(i.get("true_class")),
                    final_classification=i.get("final_classification"),
                    delay_s=(t1 - t0) if t0 is not None and t1 is not None else None,
                    swarm_member=bool(i.get("swarm_member")),
                    cooperative=bool(i.get("cooperative")),
                    crowded=crowded,
                )
            )
    return out


def _rate(hits: int, n: int) -> float:
    return hits / n if n else 0.0


def assess(obs: list[Observation]) -> dict[str, dict[str, Any]]:
    """Weakness per tactic: the error measure, the evidence count and a short reason."""
    threats = [o for o in obs if o.is_threat]
    singles = [o for o in threats if not o.swarm_member]
    as_bird = sum(1 for o in singles if o.final_classification == EntityClass.BIRD_OR_CLUTTER.value)
    slow = sum(1 for o in threats if o.delay_s is None or o.delay_s > SLOW_S)
    crowded = [o for o in threats if o.crowded]
    calm = [o for o in threats if not o.crowded]
    crowd_drop = _rate(sum(1 for o in calm if o.correct), len(calm)) - _rate(
        sum(1 for o in crowded if o.correct), len(crowded)
    )
    swarm = [o for o in threats if o.swarm_member]
    swarm_missed = sum(1 for o in swarm if not o.correct)
    return {
        "low_and_slow": {
            "measure": round(_rate(as_bird, len(singles)), 3),
            "evidence": len(singles),
            "reason": f"{as_bird} of {len(singles)} single drones were classified as birds or clutter",
        },
        "fast_run_in": {
            "measure": round(_rate(slow, len(threats)), 3),
            "evidence": len(threats),
            "reason": f"{slow} of {len(threats)} drones were classified after more than {SLOW_S:g} s, or not at all",
        },
        "saturation": {
            "measure": round(crowd_drop, 3) if crowded and calm else 0.0,
            "evidence": min(len(crowded), len(calm)),
            "reason": f"accuracy {_rate(sum(o.correct for o in calm), len(calm)):.0%} with few tracks against "
            f"{_rate(sum(o.correct for o in crowded), len(crowded)):.0%} in a crowded picture "
            f"({len(calm)} and {len(crowded)} drones)",
        },
        "larger_swarm": {
            "measure": round(_rate(swarm_missed, len(swarm)), 3),
            "evidence": len(swarm),
            "reason": f"{swarm_missed} of {len(swarm)} swarm members were misclassified or not classified",
        },
    }


def _half(lo: float, hi: float, upper: bool) -> tuple[float, float]:
    mid = round((lo + hi) / 2, 2)
    return (mid, hi) if upper else (lo, mid)


def _ihalf(lo: int, hi: int, upper: bool) -> tuple[int, int]:
    return ((lo + hi + 1) // 2, hi) if upper else (lo, (lo + hi) // 2)


def plan_adversary(scenario: Scenario, results: list[dict[str, Any]], seed: int) -> tuple[Scenario, dict[str, Any]]:
    """The adapted scenario and the recorded plan. With too little evidence the scenario is returned
    unchanged (and the plan says why)."""
    weaknesses = assess(observations(results))
    eligible = [
        (name, w) for name, w in weaknesses.items() if w["evidence"] >= MIN_EVIDENCE and w["measure"] >= THRESHOLD
    ]
    # Strongest weaknesses first; equal measures are ordered by the session seed, reproducibly.
    order = Rng.stream(seed, "adversary")
    eligible.sort(key=lambda nw: (-nw[1]["measure"], order.uniform()))
    data = scenario.model_dump(mode="json")
    targets = [g for g in data["entities"] if g["entity_class"] in DRONES and not g.get("cooperative", False)]
    chosen: list[dict[str, Any]] = []
    for name, w in eligible:
        if len(chosen) == MAX_TACTICS:
            break
        changes = _apply(name, targets)
        if changes:
            chosen.append(
                {
                    "tactic": name,
                    "effect": TACTICS[name],
                    "reason": w["reason"],
                    "measure": w["measure"],
                    "evidence": w["evidence"],
                    "changes": changes,
                }
            )
    plan: dict[str, Any] = {
        "engine": ADVERSARY_ENGINE_VERSION,
        "method": "Rules-based tactics chosen by recorded weaknesses; no machine learning.",
        "sessions_considered": len(results),
        "weaknesses": weaknesses,
        "tactics": chosen,
        "summary": (
            "; ".join(f"{c['effect']} ({c['reason']})" for c in chosen)
            if chosen
            else "No adaptation: no weakness had enough recorded evidence "
            f"(at least {MIN_EVIDENCE} relevant tracks and a measure of {THRESHOLD:.0%} or more)."
        ),
    }
    return (Scenario.model_validate(data) if chosen else scenario), plan


def _set(changes: list[dict[str, Any]], group: dict[str, Any], field: str, new: tuple[float, float]) -> None:
    old = (group[field]["min"], group[field]["max"])
    if tuple(new) != old:
        group[field] = {"min": new[0], "max": new[1]}
        changes.append({"group": group["id"], "field": field, "from": list(old), "to": list(new)})


def _apply(name: str, groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Narrow ranges in place; returns the changes (empty when the tactic has nothing to change)."""
    changes: list[dict[str, Any]] = []
    if name == "low_and_slow":
        for g in groups:
            if g["entity_class"] == EntityClass.COORDINATED_SWARM.value:
                continue
            _set(changes, g, "altitude_m", _half(g["altitude_m"]["min"], g["altitude_m"]["max"], upper=False))
            _set(changes, g, "speed_mps", _half(g["speed_mps"]["min"], g["speed_mps"]["max"], upper=False))
    elif name == "fast_run_in":
        for g in groups:
            _set(changes, g, "speed_mps", _half(g["speed_mps"]["min"], g["speed_mps"]["max"], upper=True))
            ca = g["closest_approach_m"]
            _set(changes, g, "closest_approach_m", _half(ca["min"], ca["max"], upper=False))
    elif name == "saturation" and len(groups) >= 2:
        lo = max(g["spawn_time_s"]["min"] for g in groups)
        hi = min(g["spawn_time_s"]["max"] for g in groups)
        if lo <= hi:  # a common window exists inside every group's own range
            for g in groups:
                _set(changes, g, "spawn_time_s", (lo, hi))
    elif name == "larger_swarm":
        for g in groups:
            sw = g.get("swarm")
            if g["entity_class"] == EntityClass.COORDINATED_SWARM.value and sw:
                old = (sw["size"]["min"], sw["size"]["max"])
                new = _ihalf(*old, upper=True)
                if new != old:
                    sw["size"] = {"min": new[0], "max": new[1]}
                    changes.append({"group": g["id"], "field": "swarm.size", "from": list(old), "to": list(new)})
    return changes
