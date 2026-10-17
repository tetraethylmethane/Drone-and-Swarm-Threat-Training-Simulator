"""Perimeter basics through the real API: repeated runs, interruption, persistence and seeding upgrade."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select

from drikr_api.cli import seed_demo
from drikr_api.models import Scenario
from drikr_api.services import catalog_service
from tests.integration.conftest import TEST_URL, Api, FakeClock, World, assign
from tests.integration.test_session_flow import act, launch, poll

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
REPEATS = 8


def full_timeline(api: Api, sid: str) -> list[dict]:  # type: ignore[type-arg]
    """All stored events, paging as a client must (at most 2000 per page)."""
    items: list[dict] = []  # type: ignore[type-arg]
    while True:
        page = api.get(f"/sessions/{sid}/timeline?category=all&limit=2000&offset={len(items)}").json()
        items += page["items"]
        if len(items) >= page["total"]:
            return items


def test_repeated_runs_with_interruption_persist_and_reproduce(instructor: Api, trainee: Api, clock: FakeClock) -> None:
    a = assign(instructor, trainee, max_attempts=REPEATS)
    digests, overalls = set(), []
    for run in range(REPEATS):
        s = launch(trainee, a["id"])
        sid = s["id"]
        # Version 2 content (versions are numbered per installation, so check content, not the number).
        assert s["duration_ms"] == 300_000 and s["status"] == "created"
        trainee.post(f"/sessions/{sid}/start")
        seen = poll(trainee, sid, clock, 60)
        if run % 2:  # every other run: the client disappears, the server pauses, the trainee resumes
            clock.advance(120)
            st = trainee.get(f"/sessions/{sid}/feed").json()["state"]
            assert st["status"] == "paused" and st["pause_reason"] == "connection_lost"
            trainee.post(f"/sessions/{sid}/resume")
            seen |= poll(trainee, sid, clock, 30)
        tracks = sorted({e["payload"]["track_id"] for e in seen.values() if e["type"] == "track_observation"})
        assert len(tracks) >= 4  # several tracks visible within the first 90 s of exercise time
        for tid in tracks:
            assert (
                act(
                    trainee, sid, kind="classify", track_ids=[tid], classification="unknown", confidence="low"
                ).status_code
                == 200
            )
        assert trainee.post(f"/sessions/{sid}/complete").status_code == 200

        session = instructor.get(f"/sessions/{sid}").json()
        assert session["status"] == "completed"
        timeline = full_timeline(instructor, sid)
        keys = [(e["t_ms"], e["seq"]) for e in timeline]
        assert keys == sorted(keys)  # chronological (simulation time), ties broken by sequence
        assert sorted(e["seq"] for e in timeline) == list(range(len(timeline)))  # unique, contiguous
        assert len({e["event_id"] for e in timeline}) == len(timeline)
        result = instructor.get(f"/sessions/{sid}/result").json()
        assert result["status"] == "scored" and result["scenario"]["version"] == session["scenario"]["version"]
        report = instructor.post(f"/sessions/{sid}/verify").json()
        assert report["reproducible"] and report["score_reproduced"], report
        digests.add(session["timeline_digest"])
        overalls.append(result["overall"])
    # Same assignment, same seed and difficulty: one timeline across every run.
    assert len(digests) == 1
    assert all(0 <= o <= 100 for o in overalls)


def test_seeding_publishes_a_changed_demo_as_a_new_version(world: World) -> None:
    v1 = json.loads((ROOT / "tests/fixtures/scenarios/demo-perimeter-basics-v1.json").read_text(encoding="utf-8"))
    factory = world.app.state.ctx.database.session_factory
    with factory() as db:
        before = db.scalar(select(func.max(Scenario.version)).where(Scenario.key == v1["key"]))
        # An installation whose latest demo version is the old content.
        catalog_service.create_scenario(db, v1, None, new_key=False, is_demo=True)
        db.commit()
    try:
        created = seed_demo(TEST_URL, with_users=False)
        assert created["scenarios"] == 1
        with factory() as db:
            versions = db.scalars(select(Scenario).where(Scenario.key == v1["key"]).order_by(Scenario.version)).all()
            assert [s.version for s in versions] == [before, before + 1, before + 2]
            assert versions[-1].definition["entities"] != versions[-2].definition["entities"]
        assert seed_demo(TEST_URL, with_users=False)["scenarios"] == 0  # idempotent
    finally:
        with factory() as db:
            db.execute(delete(Scenario).where(Scenario.key == v1["key"], Scenario.version > before))
            db.commit()
