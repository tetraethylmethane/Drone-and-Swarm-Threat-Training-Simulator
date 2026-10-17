"""Simulation core tests: determinism, timing rules, sensor models, validation and offline operation."""

from __future__ import annotations

import socket
import statistics
import uuid

import pytest

from drikr_contracts import Scenario, SimEvent
from drikr_simcore import (
    CONFIRMATION_DELAY_MS,
    ENGINE_VERSION,
    GroundTruthIndex,
    generate_timeline,
    sensor_confirmation_event,
    validate_definition,
)
from drikr_simcore.procedural import generate_scenario_definition
from drikr_simcore.rng import Rng, derive_seed
from tests.unit.helpers import DEMOS, demo, scenario


def test_splitmix64_reference_values() -> None:
    # Published SplitMix64 outputs for seed 0; any port (e.g. C#) must reproduce these.
    rng = Rng(0)
    assert rng.next_u64() == 0xE220A8397B1DCDAF
    assert rng.next_u64() == 0x6E789E6AA1B965F4
    assert derive_seed(42, "entity", "a") == derive_seed(42, "entity", "a")
    assert derive_seed(42, "entity", "a") != derive_seed(42, "entity", "b")


def test_rng_ranges() -> None:
    rng = Rng.stream(7, "t")
    vals = [rng.uniform(2, 3) for _ in range(2000)]
    assert min(vals) >= 2 and max(vals) < 3
    ints = {rng.randint(1, 3) for _ in range(500)}
    assert ints == {1, 2, 3}
    g = [rng.gauss(0, 1) for _ in range(4000)]
    assert abs(statistics.fmean(g)) < 0.1
    assert 0.9 < statistics.pstdev(g) < 1.1


@pytest.mark.parametrize("key", sorted(DEMOS))
def test_identical_inputs_reproduce_identical_timelines(key: str) -> None:
    scn = scenario(key)
    a = generate_timeline(scn)
    b = generate_timeline(Scenario.model_validate(demo(key)))
    assert a.digest == b.digest
    assert a.events == b.events
    assert a.engine_version == ENGINE_VERSION


def test_different_seeds_produce_valid_variations() -> None:
    scn = scenario("demo-swarm-recognition")
    digests = set()
    for seed in (1, 2, 3, 99, 123456789):
        tl = generate_timeline(scn, seed=seed)
        digests.add(tl.digest)
        report = validate_definition(
            {**demo("demo-swarm-recognition"), "randomization": {"seed": seed, "allow_seed_override": True}}
        )
        assert report.scenario is not None
        assert not [i for i in report.issues if i.severity == "error"], report.issues
    assert len(digests) == 5


def test_golden_digest_regression() -> None:
    """Guards against unintended engine changes. If this fails after an intentional
    change to generation logic, bump ENGINE_VERSION and update the expected digest."""
    tl = generate_timeline(scenario("demo-perimeter-basics"))
    assert ENGINE_VERSION == "simcore-1.0.0"
    assert tl.digest == GOLDEN_PERIMETER_DIGEST


GOLDEN_PERIMETER_DIGEST = "6a652ed253a706fedb56d1fd1053d0afdeb574823db5e594b0eccdbdda0e80d1"  # scenario version 2


@pytest.mark.parametrize("key", sorted(DEMOS))
def test_events_follow_timing_and_contract_rules(key: str) -> None:
    scn = scenario(key)
    tl = generate_timeline(scn)
    ids = set()
    prev_t = -1
    for i, ev in enumerate(tl.events):
        SimEvent.model_validate(ev)
        assert ev["seq"] == i
        assert ev["event_id"] not in ids
        ids.add(ev["event_id"])
        assert ev["t_ms"] >= prev_t, "events must be ordered by simulation time"
        prev_t = ev["t_ms"]
        assert ev["t_ms"] % 100 == 0
        assert ev["t_ms"] <= tl.duration_ms
        if ev["type"] == "track_observation":
            assert ev["payload"]["synthetic"] is True
            assert "entity_id" not in ev["payload"], "trainee-visible events must not leak ground truth"
        if ev["visibility"] == "trainee":
            assert "entity_class" not in ev["payload"]


def test_ground_truth_states_recorded_every_second() -> None:
    tl = generate_timeline(scenario())
    idx = GroundTruthIndex(tl.events)
    for ent in idx.entities.values():
        gaps = {b - a for a, b in zip(ent.state_times, ent.state_times[1:], strict=False)}
        assert gaps <= {1000}, (ent.entity_id, gaps)


def test_difficulty_changes_sensor_quality() -> None:
    scn = scenario("demo-night-loiter")
    easy = generate_timeline(scn, difficulty_level=1)
    hard = generate_timeline(scn, difficulty_level=5)

    def mean_radar_quality(tl) -> float:  # type: ignore[no-untyped-def]
        q = [
            e["payload"]["quality"]
            for e in tl.events
            if e["type"] == "track_observation" and e["payload"]["sensor"] == "radar"
        ]
        return statistics.fmean(q)

    assert mean_radar_quality(easy) > mean_radar_quality(hard)
    assert hard.stats["entities_by_class"].get("bird_or_clutter", 0) >= easy.stats["entities_by_class"].get(
        "bird_or_clutter", 0
    )
    assert easy.stats["observations"] > hard.stats["observations"]


def test_scripted_degradation_reduces_detections() -> None:
    scn = scenario("demo-night-loiter")  # EO degraded 110 s - 200 s
    tl = generate_timeline(scn)
    statuses = [e for e in tl.events if e["type"] == "sensor_status" and e["payload"]["sensor"] == "electro_optical"]
    assert [s["payload"]["status"] for s in statuses] == ["nominal", "degraded", "nominal"]
    assert statuses[1]["t_ms"] == 110_000

    def eo_rate(lo: int, hi: int) -> float:
        hits = sum(
            1
            for e in tl.events
            if e["type"] == "track_observation" and e["payload"]["sensor"] == "electro_optical" and lo <= e["t_ms"] < hi
        )
        misses = sum(
            1
            for e in tl.events
            if e["type"] == "observation_missed"
            and e["payload"]["sensor"] == "electro_optical"
            and e["payload"]["reason"] == "not_detected"
            and lo <= e["t_ms"] < hi
        )
        return hits / max(1, hits + misses)

    assert eo_rate(110_000, 200_000) < eo_rate(200_000, 300_000)
    delayed = [
        e
        for e in tl.events
        if e["type"] == "track_observation"
        and e["payload"]["sensor"] == "electro_optical"
        and 110_000 <= e["t_ms"] < 200_000
    ]
    normal = [
        e
        for e in tl.events
        if e["type"] == "track_observation" and e["payload"]["sensor"] == "electro_optical" and e["t_ms"] >= 200_000
    ]
    assert statistics.fmean(e["available_at_ms"] - e["t_ms"] for e in delayed) > statistics.fmean(
        e["available_at_ms"] - e["t_ms"] for e in normal
    )


def test_visibility_change_and_messages_emitted() -> None:
    tl = generate_timeline(scenario("demo-degraded-picture"))
    vis = [e for e in tl.events if e["type"] == "environment_update"]
    assert [v["payload"]["visibility_km"] for v in vis] == [1.2, 3.0]
    msgs = [e for e in tl.events if e["type"] == "exercise_message"]
    assert len(msgs) == 2


def test_tracks_lost_after_exit_or_silence() -> None:
    tl = generate_timeline(scenario("demo-degraded-picture"))
    idx = GroundTruthIndex(tl.events)
    lost = {e["payload"]["track_id"] for e in tl.events if e["type"] == "track_lost"}
    for ent in idx.entities.values():
        if ent.exit_ms is not None and ent.entity_id in idx.track_by_entity:
            assert idx.track_by_entity[ent.entity_id] in lost


def test_swarm_members_move_together() -> None:
    tl = generate_timeline(scenario("demo-swarm-recognition"))
    idx = GroundTruthIndex(tl.events)
    members = [e for e in idx.entities.values() if e.swarm_id]
    assert len(members) >= 6
    t = members[0].spawn_ms + 60_000
    pos = [m.state_at(t) for m in members]
    xs = [p["x_m"] for p in pos if p]
    ys = [p["y_m"] for p in pos if p]
    assert max(xs) - min(xs) < 400 and max(ys) - min(ys) < 400


def test_confirmation_is_deterministic_and_respects_ground_truth() -> None:
    scn = scenario("demo-degraded-picture")
    tl = generate_timeline(scn)
    idx = GroundTruthIndex(tl.events)
    tid, tr = sorted(idx.tracks.items())[0]
    ent = idx.entities[tr.entity_id]
    aid = uuid.UUID(int=1)
    t = (tr.first_available_ms or 0) + 1000
    a = sensor_confirmation_event(scn, tl.seed, tl.difficulty_level, idx, tid, t, aid)
    b = sensor_confirmation_event(scn, tl.seed, tl.difficulty_level, idx, tid, t, aid)
    assert a == b
    assert a["t_ms"] == t + CONFIRMATION_DELAY_MS
    assert a["payload"]["outcome"] == "hint_available"
    SimEvent.model_validate({**a, "event_id": "S-000001", "seq": 1})
    if ent.exit_ms is not None:
        gone = sensor_confirmation_event(scn, tl.seed, tl.difficulty_level, idx, tid, ent.exit_ms + 100, aid)
        assert gone["payload"]["outcome"] == "no_contact"


def test_unobservable_scenario_rejected_by_generation_check() -> None:
    data = demo()
    data["sensors"]["radar"]["range_m"] = 500
    data["sensors"]["electro_optical"]["range_m"] = 200
    data["sensors"]["rf"]["enabled"] = False
    for g in data["entities"]:
        g["closest_approach_m"] = {"min": 3000, "max": 3400}
        g.pop("dwell_s", None)
        g["behavior"] = "erratic"
    report = validate_definition(data)
    assert not report.valid
    assert any(i.code in ("no_observable_tracks", "objective_unobservable") for i in report.issues)


def test_structural_errors_reported_with_paths() -> None:
    data = demo()
    data["entities"][0]["count"] = {"min": 0, "max": 1}
    report = validate_definition(data)
    assert not report.valid
    assert report.issues[0].path.startswith("entities.0")


@pytest.mark.parametrize("seed", range(20))
def test_procedural_generation_is_valid_and_deterministic(seed: int) -> None:
    a = generate_scenario_definition(seed)
    b = generate_scenario_definition(seed)
    assert a == b
    assert validate_definition(a).valid


def test_generation_needs_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    for key in DEMOS:
        assert validate_definition(demo(key)).valid
    generate_scenario_definition(5)
