"""Adaptive adversary planner (drikr_simcore.adversary): evidence thresholds, bounds, determinism."""

from __future__ import annotations

import random
from typing import Any

import pytest

from drikr_contracts import Scenario
from drikr_simcore import generate_timeline
from drikr_simcore.adversary import MAX_TACTICS, MIN_EVIDENCE, plan_adversary
from tests.unit.helpers import DEMOS


def track(
    true_class: str = "small_multirotor",
    final: str | None = "small_multirotor",
    t0: float = 10.0,
    delay: float | None = 5.0,
    swarm: bool = False,
    cooperative: bool = False,
) -> dict[str, Any]:
    return {
        "true_class": true_class,
        "final_classification": final,
        "first_available_s": t0,
        "first_classification_s": None if delay is None else t0 + delay,
        "swarm_member": swarm,
        "cooperative": cooperative,
    }


def results(*items: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"items": list(items)}]


def spaced(n: int, **kw: Any) -> list[dict[str, Any]]:
    """n tracks far apart in time (not a crowded picture)."""
    return [track(t0=10.0 + 60 * i, **kw) for i in range(n)]


PERIMETER = Scenario.model_validate(DEMOS["demo-perimeter-basics"])


def test_no_history_changes_nothing() -> None:
    adapted, plan = plan_adversary(PERIMETER, [], seed=1)
    assert adapted is PERIMETER and plan["tactics"] == [] and plan["summary"].startswith("No adaptation")
    assert plan["method"].endswith("no machine learning.")


def test_one_poor_session_with_few_tracks_is_not_enough() -> None:
    few = spaced(MIN_EVIDENCE - 1, final="bird_or_clutter")
    adapted, plan = plan_adversary(PERIMETER, results(*few), seed=1)
    assert adapted is PERIMETER and plan["tactics"] == []


def test_drones_taken_for_birds_bring_a_low_and_slow_approach_within_bounds() -> None:
    hist = results(*spaced(4, final="bird_or_clutter"), *spaced(2))
    adapted, plan = plan_adversary(PERIMETER, hist, seed=1)
    assert [t["tactic"] for t in plan["tactics"]] == ["low_and_slow"]
    before = {g.id: g for g in PERIMETER.entities}
    for g in adapted.entities:
        b = before[g.id]
        if g.cooperative or g.entity_class.value == "bird_or_clutter":
            assert g == b  # never touched
            continue
        mid = round((b.altitude_m.min + b.altitude_m.max) / 2, 2)
        assert (g.altitude_m.min, g.altitude_m.max) == (b.altitude_m.min, mid)
        assert g.speed_mps.max <= b.speed_mps.max and g.speed_mps.min == b.speed_mps.min


def test_slow_classification_brings_a_fast_run_in() -> None:
    hist = results(*spaced(5, delay=45.0))
    _, plan = plan_adversary(PERIMETER, hist, seed=1)
    assert [t["tactic"] for t in plan["tactics"]] == ["fast_run_in"]
    assert "more than 20 s" in plan["tactics"][0]["reason"]


def test_at_most_two_tactics_and_each_is_explained() -> None:
    hist = results(*spaced(8, final="bird_or_clutter", delay=None))
    _, plan = plan_adversary(PERIMETER, hist, seed=1)
    assert 1 <= len(plan["tactics"]) <= MAX_TACTICS
    for t in plan["tactics"]:
        assert t["reason"] and t["effect"] and t["changes"] and t["evidence"] >= MIN_EVIDENCE


def _random_history(rng: random.Random) -> list[dict[str, Any]]:
    classes = ["small_multirotor", "fixed_wing_uas", "coordinated_swarm", "bird_or_clutter"]
    out = []
    for _ in range(rng.randint(0, 6)):
        items = []
        for _ in range(rng.randint(0, 12)):
            true = rng.choice(classes)
            items.append(
                track(
                    true_class=true,
                    final=rng.choice([*classes, None, "unknown"]),
                    t0=rng.uniform(0, 300),
                    delay=rng.choice([None, rng.uniform(0, 90)]),
                    swarm=true == "coordinated_swarm",
                    cooperative=rng.random() < 0.15,
                )
            )
        out.append({"items": items})
    return out


@pytest.mark.parametrize("key", sorted(DEMOS))
def test_adapted_scenarios_stay_inside_the_instructor_ranges(key: str) -> None:
    base = Scenario.model_validate(DEMOS[key])
    rng = random.Random(f"adversary-{key}")
    used = 0
    for case in range(120):
        hist = _random_history(rng)
        adapted, plan = plan_adversary(base, hist, seed=case)
        again, plan2 = plan_adversary(base, hist, seed=case)
        assert again == adapted and plan2 == plan  # deterministic
        Scenario.model_validate(adapted.model_dump(mode="json"))  # still valid
        used += bool(plan["tactics"])
        for g, b in zip(adapted.entities, base.entities, strict=True):
            if b.cooperative or b.entity_class.value == "bird_or_clutter":
                assert g == b
                continue
            for f in ("count", "spawn_time_s", "speed_mps", "altitude_m", "closest_approach_m"):
                new, old = getattr(g, f), getattr(b, f)
                assert old.min <= new.min <= new.max <= old.max, (key, case, g.id, f)
            if b.swarm:
                assert b.swarm.size.min <= g.swarm.size.min <= g.swarm.size.max <= b.swarm.size.max  # type: ignore[union-attr]
                assert g.swarm.spacing_m == b.swarm.spacing_m  # type: ignore[union-attr]
        assert adapted.sensors == base.sensors and adapted.scoring == base.scoring
        assert adapted.time_limits == base.time_limits and adapted.event_schedule == base.event_schedule
    assert used > 0  # the property was exercised with real adaptations


def test_an_adapted_scenario_generates_a_reproducible_timeline() -> None:
    adapted, plan = plan_adversary(PERIMETER, results(*spaced(6, final="bird_or_clutter")), seed=7)
    assert plan["tactics"]
    a = generate_timeline(adapted, seed=7, difficulty_level=2)
    b = generate_timeline(Scenario.model_validate(adapted.model_dump(mode="json")), seed=7, difficulty_level=2)
    assert a.digest == b.digest and a.digest != generate_timeline(PERIMETER, seed=7, difficulty_level=2).digest
