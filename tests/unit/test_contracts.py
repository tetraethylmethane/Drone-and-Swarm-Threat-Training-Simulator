"""Contract tests: scenario schema, trainee actions, event invariants and exported JSON Schemas."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from drikr_contracts import Scenario, SimEvent, TraineeAction, TraineeOptions, TraineeSelection
from drikr_contracts.export_schemas import render
from tests.unit.helpers import DEMOS, demo

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "packages" / "contracts" / "schemas"


@pytest.mark.parametrize("key", sorted(DEMOS))
def test_demo_scenarios_are_valid(key: str) -> None:
    scn = Scenario.model_validate(DEMOS[key])
    assert scn.key == key
    assert "DEMONSTRATION" in scn.description


def _mutate(path: list[str | int], value: object) -> dict:
    data = demo()
    target = data
    for p in path[:-1]:
        target = target[p]
    target[path[-1]] = value
    return data


@pytest.mark.parametrize(
    ("path", "value", "fragment"),
    [
        (["entities", 0, "speed_mps"], {"min": 20, "max": 5}, "min must be less than or equal to max"),
        (["environment", "weather"], "fog", "fog requires visibility_km"),
        (["entities", 0, "spawn_time_s"], {"min": 200, "max": 230}, "at least 30 s before the time limit"),
        (["entities", 0, "entity_class"], "coordinated_swarm", "require a swarm configuration"),
        (["entities", 2, "cooperative"], True, "cannot be cooperative"),
        (["time_limits", "duration_s"], 30, "greater than or equal to 60"),
        (["difficulty"], {"level": 5, "min_level": 1, "max_level": 3}, "within min_level..max_level"),
        (["randomization", "seed"], -1, "greater than or equal to 0"),
        (["key"], "Not A Slug", "String should match pattern"),
    ],
)
def test_invalid_scenarios_are_rejected(path: list[str | int], value: object, fragment: str) -> None:
    with pytest.raises(ValidationError) as exc:
        Scenario.model_validate(_mutate(path, value))
    assert fragment in str(exc.value)


def test_unknown_fields_are_rejected() -> None:
    data = demo()
    data["environment"]["sunlight"] = "bright"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Scenario.model_validate(data)


def test_duplicate_group_ids_rejected() -> None:
    data = demo()
    data["entities"][1]["id"] = data["entities"][0]["id"]
    with pytest.raises(ValidationError, match="entity group ids must be unique"):
        Scenario.model_validate(data)


def test_entity_cap_enforced() -> None:
    data = demo("demo-swarm-recognition")
    data["entities"][0]["count"] = {"min": 3, "max": 3}
    data["entities"][0]["swarm"]["size"] = {"min": 20, "max": 24}
    with pytest.raises(ValidationError, match="the maximum is 60"):
        Scenario.model_validate(data)


def test_objective_must_reference_present_class() -> None:
    data = demo()
    data["learning_objectives"].append(
        {
            "id": "swarm-x",
            "description": "Classify the swarm correctly.",
            "criterion": {"kind": "classify_correctly", "entity_class": "coordinated_swarm", "min_fraction": 1},
        }
    )
    with pytest.raises(ValidationError, match="which no entity group provides"):
        Scenario.model_validate(data)


def test_event_targeting_disabled_sensor_rejected() -> None:
    data = demo("demo-night-loiter")
    data["sensors"]["electro_optical"]["enabled"] = False
    with pytest.raises(ValidationError, match="targets disabled sensor"):
        Scenario.model_validate(data)


def test_positional_sensor_required() -> None:
    data = demo()
    data["sensors"]["radar"]["enabled"] = False
    data["sensors"]["electro_optical"]["enabled"] = False
    with pytest.raises(ValidationError, match="radar or electro_optical"):
        Scenario.model_validate(data)


def test_apply_selection_respects_permissions() -> None:
    scn = Scenario.model_validate(demo())
    options = TraineeOptions(time_of_day=["night"], weather=["fog"], allow_custom_seed=True)
    chosen = scn.apply_selection(options, TraineeSelection(time_of_day="night", weather="fog", seed=77))
    assert chosen.environment.time_of_day == "night"
    assert chosen.environment.weather == "fog"
    assert chosen.environment.visibility_km <= 1.5  # kept consistent with fog
    assert chosen.randomization.seed == 77
    assert scn.environment.time_of_day == "day"  # original untouched

    with pytest.raises(ValueError, match="not permitted"):
        scn.apply_selection(TraineeOptions(), TraineeSelection(time_of_day="night"))
    with pytest.raises(ValueError, match="custom seeds are not permitted"):
        scn.apply_selection(TraineeOptions(), TraineeSelection(seed=5))


def test_trainee_action_shapes() -> None:
    aid = uuid.uuid4()
    ok = TraineeAction(
        client_action_id=aid, kind="classify", track_ids=["TRK-001"], classification="bird_or_clutter", confidence="low"
    )
    assert ok.classification == "bird_or_clutter"
    TraineeAction(
        client_action_id=aid, kind="respond", track_ids=["TRK-001", "TRK-002"], response="continue_monitoring"
    )
    bad = [
        {"kind": "classify", "track_ids": ["TRK-001"], "classification": "bird_or_clutter"},
        {"kind": "classify", "track_ids": ["TRK-001"], "classification": "aircraft_carrier", "confidence": "low"},
        {"kind": "respond", "track_ids": ["TRK-001"]},
        {"kind": "respond", "track_ids": ["TRK-001"], "response": "engage"},
        {"kind": "respond", "track_ids": ["track-1"], "response": "continue_monitoring"},
        {"kind": "respond", "track_ids": ["TRK-001", "TRK-001"], "response": "continue_monitoring"},
        {"kind": "respond", "track_ids": [], "response": "continue_monitoring"},
    ]
    for b in bad:
        with pytest.raises(ValidationError):
            TraineeAction(client_action_id=aid, **b)


def _ev(**kw: object) -> dict:
    base = {
        "event_id": "G-000001",
        "seq": 1,
        "t_ms": 1000,
        "available_at_ms": 1500,
        "type": "track_observation",
        "visibility": "trainee",
        "origin": "generated",
        "payload": {"track_id": "TRK-001", "sensor": "radar", "synthetic": True, "quality": 0.5},
    }
    base.update(kw)
    return base


def test_sim_event_invariants() -> None:
    SimEvent.model_validate(_ev())
    with pytest.raises(ValidationError, match="quantised"):
        SimEvent.model_validate(_ev(t_ms=1050))
    with pytest.raises(ValidationError, match="must not precede"):
        SimEvent.model_validate(_ev(available_at_ms=900))
    with pytest.raises(ValidationError, match="ground_truth visibility"):
        SimEvent.model_validate(_ev(visibility="ground_truth"))
    with pytest.raises(ValidationError):
        # synthetic flag is mandatory and must be true
        SimEvent.model_validate(
            _ev(payload={"track_id": "TRK-001", "sensor": "radar", "synthetic": False, "quality": 0.5})
        )


def test_exported_json_schemas_are_current() -> None:
    rendered = render()
    for name, text in rendered.items():
        on_disk = (SCHEMA_DIR / name).read_text(encoding="utf-8")
        assert on_disk == text, f"{name} is stale; run python -m drikr_contracts.export_schemas"
