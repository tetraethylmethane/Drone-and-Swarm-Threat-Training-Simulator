"""Each attempt is a different, recorded and reproducible exercise (SIH26247: scenario randomisation to
prevent rote learning; migration 0006). Instructors can still ask for identical attempts."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.integration.conftest import Api, FakeClock, assign, scenario_id
from tests.unit.helpers import demo

pytestmark = pytest.mark.integration

SCENARIO_SEED = demo()["randomization"]["seed"]


def attempt(trainee: Api, clock: FakeClock, body: dict[str, Any]) -> dict[str, Any]:
    s = trainee.post("/sessions", body)
    assert s.status_code == 201, s.text
    sid = s.json()["id"]
    trainee.post(f"/sessions/{sid}/start")
    clock.advance(5)
    trainee.post(f"/sessions/{sid}/complete")
    return trainee.get(f"/sessions/{sid}").json()


def test_attempts_vary_by_default_and_each_reproduces(instructor: Api, trainee: Api, clock: FakeClock) -> None:
    a = assign(instructor, trainee)
    assert a["vary_seed"] is True and a["adaptive_adversary"] is False
    runs = [attempt(trainee, clock, {"assignment_id": a["id"]}) for _ in range(3)]
    seeds = {r["seed"] for r in runs}
    assert len(seeds) == 3 and SCENARIO_SEED not in seeds
    assert len({r["timeline_digest"] for r in runs}) == 3
    for r in runs:
        assert instructor.post(f"/sessions/{r['id']}/verify").json()["reproducible"]


def test_instructors_can_require_identical_attempts(instructor: Api, trainee: Api, clock: FakeClock) -> None:
    a = assign(instructor, trainee, vary_seed=False)
    runs = [attempt(trainee, clock, {"assignment_id": a["id"]}) for _ in range(2)]
    assert [r["seed"] for r in runs] == [SCENARIO_SEED, SCENARIO_SEED]
    assert runs[0]["timeline_digest"] == runs[1]["timeline_digest"]
    cmp = instructor.get(f"/analytics/compare?a={runs[0]['id']}&b={runs[1]['id']}").json()
    assert cmp["comparability"] == "identical"


def test_trainees_get_different_exercises_and_a_chosen_seed_is_kept(
    trainee: Api, trainee2: Api, clock: FakeClock
) -> None:
    sid = scenario_id(trainee, "demo-perimeter-basics")
    first = attempt(trainee, clock, {"scenario_id": sid, "selection": {}})
    other = attempt(trainee2, clock, {"scenario_id": sid, "selection": {}})
    second = attempt(trainee, clock, {"scenario_id": sid, "selection": {}})
    assert len({first["seed"], other["seed"], second["seed"]}) == 3
    chosen = attempt(trainee, clock, {"scenario_id": sid, "selection": {"seed": 4242}})
    assert chosen["seed"] == 4242


def test_a_scenario_that_fixes_its_seed_keeps_it(instructor: Api, trainee: Api, clock: FakeClock) -> None:
    d = demo()
    d.update(key="fixed-seed-exam", name="Fixed exercise", description="Scripted exercise with a fixed seed.")
    d["randomization"] = {"seed": 77, "allow_seed_override": False}
    assert instructor.post("/scenarios", {"definition": d}).status_code == 201
    a = assign(instructor, trainee, "fixed-seed-exam")
    assert [attempt(trainee, clock, {"assignment_id": a["id"]})["seed"] for _ in range(2)] == [77, 77]


def test_existing_assignments_keep_identical_attempts_after_the_upgrade(engine: Engine) -> None:
    with engine.connect() as c:
        default = c.execute(
            text(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_name = 'assignments' AND column_name = 'vary_seed'"
            )
        ).scalar_one()
    assert default == "false"  # rows that existed before migration 0006 are not changed


def test_the_seed_is_withheld_until_the_session_ends(trainee: Api, clock: FakeClock) -> None:
    """Security finding S-01: with a published definition, the seed reveals every track's class."""
    sid = scenario_id(trainee, "demo-perimeter-basics")
    s = trainee.post("/sessions", {"scenario_id": sid, "selection": {}}).json()
    assert s["seed"] is None
    trainee.post(f"/sessions/{s['id']}/start")
    assert trainee.get(f"/sessions/{s['id']}").json()["seed"] is None
    assert trainee.get(f"/sessions/{s['id']}/feed?since_ms=0").json()["state"]["seed"] is None
    clock.advance(5)
    trainee.post(f"/sessions/{s['id']}/complete")
    assert isinstance(trainee.get(f"/sessions/{s['id']}").json()["seed"], int)
