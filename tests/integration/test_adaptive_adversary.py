"""Adaptive adversary through the API: planned from recorded weaknesses, within the instructor's
ranges, stored with the session, reproducible, and revealed only after the exercise."""

from __future__ import annotations

import uuid

import pytest

from drikr_api.models import TrainingSession
from tests.integration.conftest import Api, FakeClock, World, assign
from tests.unit.helpers import demo

pytestmark = pytest.mark.integration


def classify_everything_as(trainee: Api, instructor: Api, clock: FakeClock, classification: str) -> None:
    """One full-length exercise (300 s) in which the trainee classifies every track the same way."""
    a = assign(instructor, trainee)
    sid = trainee.post("/sessions", {"assignment_id": a["id"]}).json()["id"]
    trainee.post(f"/sessions/{sid}/start")
    seen: set[str] = set()
    for _ in range(58):
        clock.advance(5)
        for e in trainee.get(f"/sessions/{sid}/feed").json()["events"]:
            tid = e["payload"].get("track_id") if e["type"] == "track_observation" else None
            if tid and tid not in seen:
                seen.add(tid)
                trainee.post(
                    f"/sessions/{sid}/actions",
                    {
                        "client_action_id": str(uuid.uuid4()),
                        "kind": "classify",
                        "track_ids": [tid],
                        "classification": classification,
                        "confidence": "low",
                    },
                )
    trainee.post(f"/sessions/{sid}/complete")


def _definition(world: World, sid: str) -> dict:  # type: ignore[type-arg]
    with world.app.state.ctx.database.session_factory() as db:
        s = db.get(TrainingSession, uuid.UUID(sid))
        assert s is not None
        return s.effective_definition


def test_the_adversary_targets_a_recorded_weakness(
    world: World, instructor: Api, trainee: Api, clock: FakeClock
) -> None:
    a = assign(instructor, trainee, adaptive_adversary=True, max_attempts=5)
    assert a["adaptive_adversary"] is True

    # Without history there is nothing to adapt to, and the plan says so.
    first = trainee.post("/sessions", {"assignment_id": a["id"]}).json()["id"]
    trainee.post(f"/sessions/{first}/start")
    clock.advance(5)
    trainee.post(f"/sessions/{first}/complete")
    plan = trainee.get(f"/sessions/{first}/result").json()["adversary_plan"]
    assert plan["tactics"] == [] and plan["summary"].startswith("No adaptation")

    # Three full exercises in which the trainee calls every track a bird.
    for _ in range(3):
        classify_everything_as(trainee, instructor, clock, "bird_or_clutter")

    sid = trainee.post("/sessions", {"assignment_id": a["id"]}).json()["id"]
    # During the exercise the plan is not revealed (it would tell the trainee how the drones behave).
    assert "adversary_plan" not in trainee.get(f"/sessions/{sid}").json()
    trainee.post(f"/sessions/{sid}/start")
    clock.advance(5)
    feed = trainee.get(f"/sessions/{sid}/feed").json()
    assert "adversary" not in str(feed)
    trainee.post(f"/sessions/{sid}/complete")

    plan = instructor.get(f"/sessions/{sid}/result").json()["adversary_plan"]
    assert "low_and_slow" in [t["tactic"] for t in plan["tactics"]]
    assert plan["method"] == "Rules-based tactics chosen by recorded weaknesses; no machine learning."
    low = next(t for t in plan["tactics"] if t["tactic"] == "low_and_slow")
    assert "classified as birds" in low["reason"] and low["evidence"] >= 4

    # Within the instructor's ranges: drone altitude is the lower half; birds are unchanged.
    base = {g["id"]: g for g in demo()["entities"]}
    for g in _definition(world, sid)["entities"]:
        b = base[g["id"]]
        if g["entity_class"] == "bird_or_clutter" or g.get("cooperative"):
            assert g["altitude_m"] == b["altitude_m"] and g["speed_mps"] == b["speed_mps"]
        elif g["entity_class"] != "coordinated_swarm":
            assert g["altitude_m"]["min"] == b["altitude_m"]["min"]
            assert g["altitude_m"]["max"] < b["altitude_m"]["max"]

    # The adapted exercise is what was stored, so it reproduces.
    assert instructor.post(f"/sessions/{sid}/verify").json()["reproducible"]
    # The trainee sees the plan too, once the exercise is over.
    assert trainee.get(f"/sessions/{sid}/result").json()["adversary_plan"]["tactics"]


def test_assignments_without_the_option_are_not_adapted(instructor: Api, trainee: Api, clock: FakeClock) -> None:
    for _ in range(3):
        classify_everything_as(trainee, instructor, clock, "bird_or_clutter")
    a = assign(instructor, trainee)
    sid = trainee.post("/sessions", {"assignment_id": a["id"]}).json()["id"]
    trainee.post(f"/sessions/{sid}/start")
    clock.advance(5)
    trainee.post(f"/sessions/{sid}/complete")
    assert trainee.get(f"/sessions/{sid}/result").json()["adversary_plan"] is None
