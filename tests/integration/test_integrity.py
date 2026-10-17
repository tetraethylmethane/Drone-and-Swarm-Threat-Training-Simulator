"""Data integrity: reconnection, atomic writes, recovery after an API restart, immutable records."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from drikr_api.db import Database
from drikr_api.main import create_app
from drikr_api.models import SessionEvent
from tests.integration.conftest import TEST_URL, Api, FakeClock, World, assign, make_settings
from tests.integration.test_reports_analytics import run_exercise
from tests.integration.test_session_flow import act, launch, poll

pytestmark = pytest.mark.integration


def _event_count(world: World, sid: str) -> int:
    with world.app.state.ctx.database.session_factory() as db:
        return int(
            db.scalar(select(func.count()).select_from(SessionEvent).where(SessionEvent.session_id == uuid.UUID(sid)))
            or 0
        )


def test_reconnecting_client_rebuilds_the_same_state_from_the_server(
    world: World, instructor: Api, trainee: Api, clock: FakeClock
) -> None:
    sid = launch(trainee, assign(instructor, trainee)["id"])["id"]
    trainee.post(f"/sessions/{sid}/start")
    incremental = poll(trainee, sid, clock, 60)  # what the original client received, 5 s at a time
    # A second client (a reloaded browser tab or a restarted Unity client) asks for everything.
    fresh = world.login("trainee1")
    body = fresh.get(f"/sessions/{sid}/feed?since_ms=0").json()
    rebuilt = {e["event_id"]: e for e in body["events"]}
    assert rebuilt == incremental  # identical events: nothing missing, nothing invented
    now = body["state"]["sim_time_ms"]
    assert all(e["available_at_ms"] <= now for e in rebuilt.values())
    assert all(e["visibility"] != "ground_truth" for e in rebuilt.values())  # ground truth never sent
    # The reconnecting client keeps the authoritative session state; it does not create a new session.
    assert body["state"]["id"] == sid and body["state"]["status"] == "running"


def test_partially_invalid_action_writes_nothing(world: World, instructor: Api, trainee: Api, clock: FakeClock) -> None:
    sid = launch(trainee, assign(instructor, trainee)["id"])["id"]
    trainee.post(f"/sessions/{sid}/start")
    seen = poll(trainee, sid, clock, 40)
    visible = next(e["payload"]["track_id"] for e in seen.values() if e["type"] == "track_observation")
    before = _event_count(world, sid)
    r = act(trainee, sid, kind="classify", track_ids=[visible, "TRK-999"], classification="unknown", confidence="low")
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_tracks"
    assert _event_count(world, sid) == before


def test_failure_midway_through_a_request_rolls_back(
    world: World, instructor: Api, trainee: Api, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A confirmation request stores two events; if the second fails, neither is kept."""
    sid = launch(trainee, assign(instructor, trainee)["id"])["id"]
    trainee.post(f"/sessions/{sid}/start")
    seen = poll(trainee, sid, clock, 40)
    tid = next(e["payload"]["track_id"] for e in seen.values() if e["type"] == "track_observation")
    before = _event_count(world, sid)

    def boom(*_: Any, **__: Any) -> Any:
        raise RuntimeError("simulated failure after the response event was written")

    monkeypatch.setattr("drikr_api.services.session_service.sensor_confirmation_event", boom)
    client = TestClient(world.app, raise_server_exceptions=False, cookies=trainee.client.cookies)
    r = client.post(
        f"/api/v1/sessions/{sid}/actions",
        json={
            "client_action_id": str(uuid.uuid4()),
            "kind": "respond",
            "track_ids": [tid],
            "response": "request_sensor_confirmation",
        },
        headers={"X-CSRF-Token": trainee.csrf or ""},
    )
    assert r.status_code == 500
    assert _event_count(world, sid) == before


def test_session_continues_after_the_api_restarts(
    world: World, instructor: Api, trainee: Api, clock: FakeClock
) -> None:
    sid = launch(trainee, assign(instructor, trainee)["id"])["id"]
    trainee.post(f"/sessions/{sid}/start")
    seen = poll(trainee, sid, clock, 30)
    tid = next(e["payload"]["track_id"] for e in seen.values() if e["type"] == "track_observation")
    assert (
        act(trainee, sid, kind="classify", track_ids=[tid], classification="unknown", confidence="low").status_code
        == 200
    )

    # A brand-new API process: nothing in memory, only the database (and the client's cookie).
    database = Database(TEST_URL)
    try:
        restarted = Api(TestClient(create_app(make_settings(), database), cookies=trainee.client.cookies), trainee.csrf)
        clock.advance(5)
        st = restarted.get(f"/sessions/{sid}/feed?since_ms=0").json()
        assert st["state"]["status"] == "running" and st["state"]["sim_time_ms"] == 35_000
        decisions = [e for e in st["events"] if e["type"] == "classification_submitted"]
        assert [d["payload"]["track_ids"] for d in decisions] == [[tid]]
        assert restarted.post(f"/sessions/{sid}/complete").status_code == 200
        report = instructor.post(f"/sessions/{sid}/verify").json()
        assert report["reproducible"] and report["score_reproduced"]
    finally:
        database.dispose()


def test_no_api_route_can_edit_events_or_results(world: World) -> None:
    """Results and event logs are written once; no route offers to change them."""
    editable = [
        (sorted(r.methods or []), r.path)
        for r in world.app.routes
        if getattr(r, "methods", None) and set(r.methods) & {"PUT", "PATCH", "DELETE"}
    ]
    for _methods, path in editable:
        assert not any(word in path for word in ("/result", "/timeline", "/feed", "/events", "/actions")), path


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("UPDATE session_events SET payload = '{}' WHERE session_id = :s", "session_events are append-only"),
        ("UPDATE score_results SET overall = 100 WHERE session_id = :s", "score_results are immutable"),
        ("DELETE FROM score_results WHERE session_id = :s", "score_results are immutable"),
    ],
)
def test_database_refuses_edits_to_records(
    engine: Engine, instructor: Api, trainee: Api, clock: FakeClock, sql: str, message: str
) -> None:
    sid = run_exercise(trainee, instructor, clock)
    with pytest.raises(DBAPIError, match=message), engine.begin() as c:
        c.execute(text(sql), {"s": uuid.UUID(sid)})
    # Deleting event logs remains possible: the retention policy needs it (scores are kept).
    with engine.begin() as c:
        c.execute(text("SAVEPOINT x"))
        deleted = c.execute(text("DELETE FROM session_events WHERE session_id = :s"), {"s": uuid.UUID(sid)}).rowcount
        c.execute(text("ROLLBACK TO SAVEPOINT x"))
    assert deleted > 0
