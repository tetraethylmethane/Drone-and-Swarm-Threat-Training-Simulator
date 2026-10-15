"""Exercise lifecycle: launch, timing model, feed, actions, completion, scoring, recovery and reproducibility."""

from __future__ import annotations

import threading
import uuid
from typing import Any

import pytest
from sqlalchemy import func, select

from drikr_api.models import ScoreResult, SessionEvent
from tests.integration.conftest import Api, FakeClock, World, assign, scenario_id

pytestmark = pytest.mark.integration


def launch(trainee: Api, assignment_id: str, selection: dict[str, Any] | None = None) -> dict[str, Any]:
    r = trainee.post("/sessions", {"assignment_id": assignment_id, "selection": selection or {}})
    assert r.status_code == 201, r.text
    return r.json()


def poll(trainee: Api, sid: str, clock: FakeClock, seconds: float, step: float = 5.0) -> dict[str, dict[str, Any]]:
    """Advance the clock while polling like a real client; return all events seen, keyed by id."""
    seen: dict[str, dict[str, Any]] = {}
    since = 0
    elapsed = 0.0
    while elapsed < seconds:
        clock.advance(step)
        elapsed += step
        r = trainee.get(f"/sessions/{sid}/feed?since_ms={since}")
        assert r.status_code == 200, r.text
        body = r.json()
        for e in body["events"]:
            seen[e["event_id"]] = e
        since = body["state"]["sim_time_ms"]
    return seen


def act(trainee: Api, sid: str, **kw: Any) -> Any:
    body = {"client_action_id": str(uuid.uuid4()), **kw}
    return trainee.post(f"/sessions/{sid}/actions", body)


def test_full_trainee_workflow_scores_and_persists(
    world: World, instructor: Api, trainee: Api, clock: FakeClock
) -> None:
    a = assign(instructor, trainee)
    mine = trainee.get("/assignments").json()["items"]
    assert [x["id"] for x in mine] == [a["id"]]
    assert "briefing" in mine[0] and "entities" not in str(mine[0]["briefing"])

    s = launch(trainee, a["id"])
    sid = s["id"]
    assert s["status"] == "created" and s["difficulty_level"] == 2
    assert s["briefing"]["synthetic_notice"]
    assert trainee.post(f"/sessions/{sid}/start").json()["status"] == "running"

    seen = poll(trainee, sid, clock, 90)
    types = {e["type"] for e in seen.values()}
    assert "track_observation" in types
    assert not types & {"entity_spawned", "entity_state", "track_assigned", "observation_missed"}, "ground truth leaked"
    assert all(e["payload"].get("synthetic") is True for e in seen.values() if e["type"] == "track_observation")

    tracks = sorted({e["payload"]["track_id"] for e in seen.values() if e["type"] == "track_observation"})
    assert tracks
    for tid in tracks:
        r = act(trainee, sid, kind="classify", track_ids=[tid], classification="small_multirotor", confidence="medium")
        assert r.status_code == 200, r.text
        assert (
            act(trainee, sid, kind="respond", track_ids=[tid], response="report_to_exercise_control").status_code == 200
        )

    done = trainee.post(f"/sessions/{sid}/complete").json()
    assert done["status"] == "completed" and done["completion_reason"] == "trainee_submitted"
    assert done["result"]["status"] == "scored"
    assert 0 <= done["result"]["overall"] <= 100

    result = trainee.get(f"/sessions/{sid}/result").json()
    assert result["feedback_level"] == "detailed"
    assert {i["track_id"] for i in result["items"]} >= set(tracks)
    # Values shown match what is persisted.
    with world.app.state.ctx.database.session_factory() as db:
        row = db.scalar(select(ScoreResult).where(ScoreResult.session_id == uuid.UUID(sid)))
        assert row is not None and row.overall == result["overall"] and row.rubric_version == 1

    # Instructor sees the completed attempt.
    prog = instructor.get(f"/assignments/{a['id']}").json()["progress"]
    assert prog["attempts_used"] == 1 and prog["sessions"][0]["overall"] == result["overall"]


def test_timing_model_pause_resume_and_tick_quantisation(trainee: Api, instructor: Api, clock: FakeClock) -> None:
    sid = launch(trainee, assign(instructor, trainee)["id"])["id"]
    trainee.post(f"/sessions/{sid}/start")
    clock.advance(10.05)
    st = trainee.get(f"/sessions/{sid}/feed").json()["state"]
    assert st["sim_time_ms"] == 10_000  # quantised down to the 100 ms tick
    paused = trainee.post(f"/sessions/{sid}/pause").json()
    assert paused["status"] == "paused"
    clock.advance(600)  # paused time does not count
    assert trainee.get(f"/sessions/{sid}").json()["sim_time_ms"] == 10_000
    trainee.post(f"/sessions/{sid}/resume")
    clock.advance(4)
    assert trainee.get(f"/sessions/{sid}/feed").json()["state"]["sim_time_ms"] == 14_000
    # Events visible to the client never come from the future.
    events = trainee.get(f"/sessions/{sid}/feed?since_ms=0").json()["events"]
    assert all(e["available_at_ms"] <= 14_000 for e in events)
    kinds = [e["type"] for e in events if e["type"].startswith("session_")]
    assert kinds == ["session_started", "session_paused", "session_resumed"]


@pytest.mark.parametrize(
    ("op", "status_before"),
    [("pause", "created"), ("resume", "created"), ("complete", "created"), ("start", "running"), ("resume", "running")],
)
def test_invalid_transitions_rejected(
    trainee: Api, instructor: Api, clock: FakeClock, op: str, status_before: str
) -> None:
    sid = launch(trainee, assign(instructor, trainee)["id"])["id"]
    if status_before == "running":
        trainee.post(f"/sessions/{sid}/start")
    r = trainee.post(f"/sessions/{sid}/{op}")
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition"


def test_actions_rejected_when_not_running_or_track_unknown(trainee: Api, instructor: Api, clock: FakeClock) -> None:
    sid = launch(trainee, assign(instructor, trainee)["id"])["id"]
    r = act(trainee, sid, kind="respond", track_ids=["TRK-001"], response="continue_monitoring")
    assert r.status_code == 409 and r.json()["error"]["code"] == "session_not_running"
    trainee.post(f"/sessions/{sid}/start")
    clock.advance(1)
    trainee.get(f"/sessions/{sid}/feed")
    r = act(trainee, sid, kind="respond", track_ids=["TRK-999"], response="continue_monitoring")
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_tracks"
    bad = trainee.post(
        f"/sessions/{sid}/actions",
        {
            "client_action_id": str(uuid.uuid4()),
            "kind": "respond",
            "track_ids": ["TRK-001"],
            "response": "engage_target",
        },
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "validation_error"


def test_duplicate_actions_and_completion_are_idempotent(
    world: World, trainee: Api, instructor: Api, clock: FakeClock
) -> None:
    sid = launch(trainee, assign(instructor, trainee)["id"])["id"]
    trainee.post(f"/sessions/{sid}/start")
    seen = poll(trainee, sid, clock, 60)
    tid = next(e["payload"]["track_id"] for e in seen.values() if e["type"] == "track_observation")
    body = {
        "client_action_id": str(uuid.uuid4()),
        "kind": "classify",
        "track_ids": [tid],
        "classification": "unknown",
        "confidence": "low",
    }
    first = trainee.post(f"/sessions/{sid}/actions", body).json()
    clock.advance(3)
    retry = trainee.post(f"/sessions/{sid}/actions", body).json()
    assert retry["duplicate"] is True and retry["event"]["event_id"] == first["event"]["event_id"]

    # Concurrent retries of the same action produce exactly one event.
    body2 = {**body, "client_action_id": str(uuid.uuid4())}
    codes: list[int] = []
    threads = [
        threading.Thread(target=lambda: codes.append(trainee.post(f"/sessions/{sid}/actions", body2).status_code))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert set(codes) <= {200, 409}

    c1 = trainee.post(f"/sessions/{sid}/complete").json()
    c2 = trainee.post(f"/sessions/{sid}/complete").json()
    assert c1["result"] == c2["result"]
    with world.app.state.ctx.database.session_factory() as db:
        assert (
            db.scalar(select(func.count()).select_from(ScoreResult).where(ScoreResult.session_id == uuid.UUID(sid)))
            == 1
        )
        n = db.scalar(
            select(func.count())
            .select_from(SessionEvent)
            .where(
                SessionEvent.session_id == uuid.UUID(sid),
                SessionEvent.client_action_id == uuid.UUID(body2["client_action_id"]),
            )
        )
        assert n == 1


def test_connection_loss_pauses_and_recovers(trainee: Api, instructor: Api, clock: FakeClock) -> None:
    sid = launch(trainee, assign(instructor, trainee)["id"])["id"]
    trainee.post(f"/sessions/{sid}/start")
    poll(trainee, sid, clock, 20)  # heartbeats every 5 s up to 20 s
    clock.advance(300)  # client disappears far longer than the 15 s grace
    st = trainee.get(f"/sessions/{sid}/feed").json()["state"]
    assert st["status"] == "paused" and st["pause_reason"] == "connection_lost"
    assert st["sim_time_ms"] == 35_000  # stopped at last heartbeat + grace
    assert trainee.post(f"/sessions/{sid}/resume").json()["status"] == "running"
    clock.advance(5)
    assert trainee.get(f"/sessions/{sid}/feed").json()["state"]["sim_time_ms"] == 40_000


def test_time_limit_completes_and_scores_via_sweeper(
    world: World, trainee: Api, instructor: Api, clock: FakeClock
) -> None:
    from drikr_api.services import session_service

    sid = launch(trainee, assign(instructor, trainee)["id"])["id"]
    trainee.post(f"/sessions/{sid}/start")
    for _ in range(25):  # 250 s of polling; demo duration is 240 s
        clock.advance(10)
        trainee.get(f"/sessions/{sid}/feed")
    st = trainee.get(f"/sessions/{sid}").json()
    assert st["status"] == "completed" and st["completion_reason"] == "time_limit"
    assert st["sim_time_ms"] == st["duration_ms"]

    # A second, abandoned session is finalised by the background sweeper.
    a2 = assign(instructor, trainee, "demo-night-loiter", difficulty_level=3, min_level=2, max_level=5)
    sid2 = launch(trainee, a2["id"])["id"]
    trainee.post(f"/sessions/{sid2}/start")
    clock.advance(400)
    with world.app.state.ctx.database.session_factory() as db:
        assert session_service.sweep(db, 15, now=clock.now) == 1
    st2 = trainee.get(f"/sessions/{sid2}").json()
    assert st2["status"] == "paused" and st2["pause_reason"] == "connection_lost"


def test_sensor_confirmation_arrives_after_delay(trainee: Api, instructor: Api, clock: FakeClock) -> None:
    sid = launch(trainee, assign(instructor, trainee)["id"])["id"]
    trainee.post(f"/sessions/{sid}/start")
    seen = poll(trainee, sid, clock, 40)
    tid = next(e["payload"]["track_id"] for e in seen.values() if e["type"] == "track_observation")
    r = act(trainee, sid, kind="respond", track_ids=[tid], response="request_sensor_confirmation").json()
    conf = r["confirmations"][0]
    assert conf["type"] == "sensor_confirmation" and conf["t_ms"] == r["event"]["t_ms"] + 4000
    now_ms = r["state"]["sim_time_ms"]
    early = trainee.get(f"/sessions/{sid}/feed?since_ms={now_ms}").json()["events"]
    assert conf["event_id"] not in {e["event_id"] for e in early}
    clock.advance(5)
    later = trainee.get(f"/sessions/{sid}/feed?since_ms={now_ms}").json()["events"]
    assert conf["event_id"] in {e["event_id"] for e in later}


def test_trainee_selection_permissions(trainee: Api, instructor: Api, clock: FakeClock) -> None:
    a = assign(
        instructor, trainee, trainee_options={"time_of_day": ["night"], "weather": [], "allow_custom_seed": True}
    )
    r = trainee.post("/sessions", {"assignment_id": a["id"], "selection": {"weather": "fog"}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "selection_not_permitted"
    s = launch(trainee, a["id"], {"time_of_day": "night", "seed": 4242})
    assert s["seed"] == 4242 and s["briefing"]["environment"]["time_of_day"] == "night"
    # Only one active attempt at a time.
    r = trainee.post("/sessions", {"assignment_id": a["id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "session_in_progress"


def test_attempt_limit(trainee: Api, instructor: Api, clock: FakeClock) -> None:
    a = assign(instructor, trainee, max_attempts=1)
    sid = launch(trainee, a["id"])["id"]
    trainee.post(f"/sessions/{sid}/start")
    clock.advance(5)
    trainee.post(f"/sessions/{sid}/complete")
    r = trainee.post("/sessions", {"assignment_id": a["id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "attempts_exhausted"


def test_reproducibility_verification(trainee: Api, instructor: Api, clock: FakeClock) -> None:
    a = assign(instructor, trainee)
    sid = launch(trainee, a["id"])["id"]
    trainee.post(f"/sessions/{sid}/start")
    seen = poll(trainee, sid, clock, 30)
    for tid in sorted({e["payload"]["track_id"] for e in seen.values() if e["type"] == "track_observation"}):
        act(trainee, sid, kind="classify", track_ids=[tid], classification="bird_or_clutter", confidence="low")
    trainee.post(f"/sessions/{sid}/complete")
    report = instructor.post(f"/sessions/{sid}/verify").json()
    assert (
        report["timeline_reproduced"]
        and report["stored_log_intact"]
        and report["score_reproduced"]
        and report["reproducible"]
    )
    # Same scenario version, configuration and seed reproduce the same logical timeline in a new session.
    a2 = assign(instructor, trainee)
    s2 = launch(trainee, a2["id"])
    first = instructor.get(f"/sessions/{sid}").json()
    assert s2["timeline_digest"] == first["timeline_digest"] and s2["config_digest"] == first["config_digest"]


def test_self_guided_practice(trainee: Api, instructor: Api, clock: FakeClock) -> None:
    lib = trainee.get("/scenarios").json()["items"]
    assert lib and all(s["self_guided"] for s in lib)
    assert "definition" not in lib[0]
    swarm_id = scenario_id(instructor, "demo-swarm-recognition")  # not self-guided
    assert trainee.post("/sessions", {"scenario_id": swarm_id}).status_code == 403
    s = trainee.post("/sessions", {"scenario_id": lib[0]["id"], "selection": {"weather": "rain"}}).json()
    assert s["mode"] == "self_guided"
    trainee.post(f"/sessions/{s['id']}/start")
    clock.advance(10)
    trainee.post(f"/sessions/{s['id']}/complete")
    assert trainee.get(f"/sessions/{s['id']}/result").json()["status"] in ("scored", "insufficient_data")


def test_adaptive_difficulty_records_reasons(world: World, trainee: Api, instructor: Api, clock: FakeClock) -> None:
    a = assign(
        instructor, trainee, difficulty_mode="adaptive", difficulty_level=3, min_level=2, max_level=4, max_attempts=5
    )
    levels = []
    for _ in range(3):
        sid = launch(trainee, a["id"])["id"]
        levels.append(trainee.get(f"/sessions/{sid}").json()["difficulty_level"])
        trainee.post(f"/sessions/{sid}/start")
        clock.advance(30)
        trainee.get(f"/sessions/{sid}/feed")
        trainee.post(f"/sessions/{sid}/complete")  # idle trainee: low scores
    hist = instructor.get(f"/analytics/difficulty?trainee_id={trainee.user['id']}").json()["items"]  # type: ignore[index]
    assert len(hist) == 3 and all(h["reason"] for h in hist)
    assert hist[-1]["change"] == "hold" and "required before adjusting" in hist[-1]["reason"]  # first session
    assert levels[0] == 3
    assert min(levels) >= 2  # never below the instructor minimum
    assert levels[2] == 2  # demoted after two low scores
    assert hist[0]["to_level"] == 2  # most recent: held at the minimum bound
    assert "instructor minimum" in hist[0]["reason"]


def test_feed_and_actions_restricted_to_owner(trainee: Api, trainee2: Api, instructor: Api, clock: FakeClock) -> None:
    sid = launch(trainee, assign(instructor, trainee)["id"])["id"]
    trainee.post(f"/sessions/{sid}/start")
    for call in (
        lambda: trainee2.get(f"/sessions/{sid}"),
        lambda: trainee2.get(f"/sessions/{sid}/feed"),
        lambda: trainee2.post(f"/sessions/{sid}/pause"),
        lambda: act(trainee2, sid, kind="respond", track_ids=["TRK-001"], response="continue_monitoring"),
    ):
        assert call().status_code == 404
    assert instructor.get(f"/sessions/{sid}/feed").status_code == 403  # instructors observe via AAR, not the live feed
    assert (
        instructor.post(f"/sessions/{sid}/abort", {"reason": "Exercise cancelled by instructor"}).json()["status"]
        == "aborted"
    )
    assert trainee.post(f"/sessions/{sid}/resume").status_code == 409
