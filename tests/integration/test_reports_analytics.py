"""AAR data, analytics, reviews and exports: values come from persisted records and respect permissions."""

from __future__ import annotations

import csv
import io
import uuid
from typing import Any

import pytest

from tests.integration.conftest import Api, FakeClock, World, assign

pytestmark = pytest.mark.integration


def run_exercise(
    trainee: Api,
    instructor: Api,
    clock: FakeClock,
    key: str = "demo-perimeter-basics",
    classify: str | None = "small_multirotor",
    **kw: Any,
) -> str:
    a = assign(instructor, trainee, key, **kw)
    sid = trainee.post("/sessions", {"assignment_id": a["id"]}).json()["id"]
    trainee.post(f"/sessions/{sid}/start")
    since = 0
    tracks: set[str] = set()
    for _ in range(12):
        clock.advance(5)
        body = trainee.get(f"/sessions/{sid}/feed?since_ms={since}").json()
        since = body["state"]["sim_time_ms"]
        tracks |= {e["payload"]["track_id"] for e in body["events"] if e["type"] == "track_observation"}
    if classify:
        for t in sorted(tracks):
            trainee.post(
                f"/sessions/{sid}/actions",
                {
                    "client_action_id": str(uuid.uuid4()),
                    "kind": "classify",
                    "track_ids": [t],
                    "classification": classify,
                    "confidence": "low",
                },
            )
    trainee.post(f"/sessions/{sid}/complete")
    return sid


def test_empty_states_do_not_invent_data(instructor: Api, trainee: Api) -> None:
    assert instructor.get("/analytics/progress").json()["points"] == []
    ov = instructor.get("/analytics/overview").json()
    assert ov["sessions_completed"] == 0 and ov["average_overall"] is None
    assert trainee.get("/analytics/progress").json()["points"] == []
    rows = list(csv.reader(io.StringIO(instructor.get("/reports/sessions.csv").text)))
    assert len(rows) == 1  # header only


def test_progress_matches_persisted_results_and_filters(
    instructor: Api, trainee: Api, trainee2: Api, clock: FakeClock
) -> None:
    s1 = run_exercise(trainee, instructor, clock)
    s2 = run_exercise(
        trainee2,
        instructor,
        clock,
        "demo-night-loiter",
        classify="bird_or_clutter",
        difficulty_level=3,
        min_level=2,
        max_level=5,
    )
    pts = instructor.get("/analytics/progress").json()["points"]
    assert {p["session_id"] for p in pts} == {s1, s2}
    for p in pts:
        res = instructor.get(f"/sessions/{p['session_id']}/result").json()
        assert p["overall"] == res["overall"]
        assert p["dimensions"] == {k: v["score"] for k, v in res["dimensions"].items()}
    only = instructor.get(f"/analytics/progress?trainee_id={trainee.user['id']}").json()["points"]  # type: ignore[index]
    assert [p["session_id"] for p in only] == [s1]
    by_scn = instructor.get("/analytics/progress?scenario_key=demo-night-loiter").json()["points"]
    assert [p["session_id"] for p in by_scn] == [s2]
    by_obj = instructor.get("/analytics/progress?objective_id=classify-birds").json()["points"]
    assert [p["session_id"] for p in by_obj] == [s1] and by_obj[0]["objective_status"] in ("met", "not_met")
    future = instructor.get("/analytics/progress?date_from=2030-01-01T00:00:00Z").json()["points"]
    assert future == []
    f = instructor.get("/analytics/filters").json()
    assert {s["key"] for s in f["scenarios"]} == {"demo-perimeter-basics", "demo-night-loiter"}
    assert trainee.get("/analytics/progress").json()["points"][0]["session_id"] == s1


def test_csv_export_respects_filters_and_neutralises_formulas(
    world: World, admin: Api, instructor: Api, trainee: Api, trainee2: Api, clock: FakeClock
) -> None:
    uid = trainee.user["id"]  # type: ignore[index]
    admin.patch(f"/users/{uid}", {"display_name": '=HYPERLINK("x")'})
    s1 = run_exercise(trainee, instructor, clock)
    run_exercise(trainee2, instructor, clock)
    rows = list(csv.DictReader(io.StringIO(instructor.get(f"/reports/sessions.csv?trainee_id={uid}").text)))
    assert [r["session_id"] for r in rows] == [s1]
    assert rows[0]["trainee_name"].startswith("'=")
    res = instructor.get(f"/sessions/{s1}/result").json()
    assert float(rows[0]["overall"]) == res["overall"]
    assert rows[0]["rubric_version"] == "1"
    all_rows = list(csv.DictReader(io.StringIO(instructor.get("/reports/sessions.csv").text)))
    assert len(all_rows) == 2
    assert trainee.get("/reports/sessions.csv").status_code == 403


def test_pdf_export_and_permissions(instructor: Api, trainee: Api, trainee2: Api, clock: FakeClock) -> None:
    sid = run_exercise(trainee, instructor, clock)
    r = instructor.get(f"/reports/sessions/{sid}.pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and r.headers["content-type"] == "application/pdf"
    assert trainee.get(f"/reports/sessions/{sid}.pdf").status_code == 200
    assert trainee2.get(f"/reports/sessions/{sid}.pdf").status_code == 404
    summary_sid = run_exercise(trainee, instructor, clock, feedback_level="summary")
    assert trainee.get(f"/reports/sessions/{summary_sid}.pdf").status_code == 403


def test_review_workflow_and_sharing(instructor: Api, trainee: Api, clock: FakeClock) -> None:
    sid = run_exercise(trainee, instructor, clock)
    assert trainee.get(f"/sessions/{sid}/review").json() is None
    body = {
        "status": "reviewed",
        "notes": "Private note",
        "strengths": "Fast classification",
        "improvements": "Report earlier",
        "focus_objectives": ["no-false-clear"],
        "shared_with_trainee": False,
    }
    assert instructor.put(f"/sessions/{sid}/review", body).status_code == 200
    assert trainee.get(f"/sessions/{sid}/review").json() is None
    body["shared_with_trainee"] = True
    instructor.put(f"/sessions/{sid}/review", body)
    shared = trainee.get(f"/sessions/{sid}/review").json()
    assert shared["strengths"] == "Fast classification" and "notes" not in shared
    bad = instructor.put(f"/sessions/{sid}/review", {**body, "focus_objectives": ["made-up"]})
    assert bad.status_code == 422
    assert instructor.get("/sessions?needs_review=false").json()["total"] == 1
    assert instructor.get("/sessions?needs_review=true").json()["total"] == 0


def test_timeline_pagination_and_categories(instructor: Api, trainee: Api, clock: FakeClock) -> None:
    sid = run_exercise(
        trainee, instructor, clock, "demo-swarm-recognition", difficulty_level=3, min_level=2, max_level=5
    )
    page1 = instructor.get(f"/sessions/{sid}/timeline?limit=100&offset=0").json()
    page2 = instructor.get(f"/sessions/{sid}/timeline?limit=100&offset=100").json()
    assert page1["total"] > 1000 and len(page1["items"]) == 100
    assert {e["event_id"] for e in page1["items"]}.isdisjoint({e["event_id"] for e in page2["items"]})
    times = [e["t_ms"] for e in page1["items"] + page2["items"]]
    assert times == sorted(times)
    dec = instructor.get(f"/sessions/{sid}/timeline?category=decisions").json()["items"]
    assert dec and all(
        e["type"] in ("classification_submitted", "response_submitted", "sensor_confirmation") for e in dec
    )
    gt = instructor.get(f"/sessions/{sid}/timeline?category=ground_truth&limit=50").json()["items"]
    assert all(e["visibility"] == "ground_truth" for e in gt)
    one = instructor.get(f"/sessions/{sid}/timeline?track_id=TRK-001").json()["items"]
    assert one and all(e["payload"].get("track_id") == "TRK-001" for e in one)
