"""Competency tracking, recurring errors and attempt comparison from persisted results."""

from __future__ import annotations

import pytest

from tests.integration.conftest import Api, FakeClock
from tests.integration.test_reports_analytics import run_exercise

pytestmark = pytest.mark.integration


def test_competency_trends_recurring_errors_and_identical_attempts(
    instructor: Api, trainee: Api, trainee2: Api, clock: FakeClock
) -> None:
    tid = trainee.user["id"]  # type: ignore[index]
    empty = instructor.get(f"/analytics/competency?trainee_id={tid}").json()
    assert empty["sessions"] == [] and empty["equivalent_attempts"] == []
    assert all(d["trend"] == "insufficient_data" for d in empty["dimensions"].values())

    # Three attempts at the same assigned exercise (same scenario version, seed and difficulty):
    # never classifying, then classifying everything.
    s1 = run_exercise(trainee, instructor, clock, classify=None, max_attempts=5)
    s2 = run_exercise(trainee, instructor, clock, classify=None, max_attempts=5)
    s3 = run_exercise(trainee, instructor, clock, classify="small_multirotor", max_attempts=5)
    run_exercise(trainee2, instructor, clock)  # another trainee's data must not leak in

    out = instructor.get(f"/analytics/competency?trainee_id={tid}").json()
    assert [s["session_id"] for s in out["sessions"]] == [s1, s2, s3]
    for sid in (s1, s2, s3):  # every number is backed by a persisted result
        assert instructor.get(f"/sessions/{sid}/result").status_code == 200

    timing = out["dimensions"]["timing"]
    assert timing["assessed_sessions"] == 1 and timing["trend"] == "insufficient_data"
    recog = out["dimensions"]["recognition"]
    assert len(recog["points"]) == 3

    missed = next(e for e in out["recurring_errors"] if e["type"] == "missed_tracks")
    assert missed["sessions_with_error"] >= 2 and missed["recurring"] is True
    assert missed["latest"]["session_id"] in (s1, s2)
    assert out["recurring_errors"][0]["recurring"] is True  # recurring types listed first

    groups = out["equivalent_attempts"]
    assert len(groups) == 1 and {a["session_id"] for a in groups[0]["attempts"]} == {s1, s2, s3}
    assert "window" in out["method"] and out["method"]["trend_threshold_points"] == 5.0


def test_compare_identical_attempts_shows_tracks(instructor: Api, trainee: Api, clock: FakeClock) -> None:
    first = run_exercise(trainee, instructor, clock, classify=None, max_attempts=5)
    second = run_exercise(trainee, instructor, clock, classify="small_multirotor", max_attempts=5)
    cmp = instructor.get(f"/analytics/compare?a={first}&b={second}").json()
    assert cmp["comparability"] == "identical" and cmp["same"]["timeline"] is True
    a = instructor.get(f"/sessions/{first}/result").json()
    b = instructor.get(f"/sessions/{second}/result").json()
    assert cmp["overall"]["delta"] == pytest.approx(round(b["overall"] - a["overall"], 1))
    assert cmp["tracks"] and all(t["a"]["final_classification"] is None for t in cmp["tracks"])
    assert all(t["b"]["final_classification"] == "small_multirotor" for t in cmp["tracks"])
    assert cmp["errors"]["missed_tracks"]["a"] > cmp["errors"]["missed_tracks"]["b"]


def test_compare_different_scenarios_and_access(instructor: Api, trainee: Api, trainee2: Api, clock: FakeClock) -> None:
    mine = run_exercise(trainee, instructor, clock)
    other_scenario = run_exercise(trainee, instructor, clock, key="demo-degraded-picture")
    cmp = trainee.get(f"/analytics/compare?a={mine}&b={other_scenario}").json()
    assert cmp["comparability"] == "different_scenarios" and cmp["tracks"] == []
    # Trainees can compare only their own sessions, and see only their own competency.
    theirs = run_exercise(trainee2, instructor, clock)
    assert trainee.get(f"/analytics/compare?a={mine}&b={theirs}").status_code == 404
    own = trainee.get(f"/analytics/competency?trainee_id={trainee2.user['id']}").json()  # type: ignore[index]
    assert own["trainee"]["id"] == trainee.user["id"]  # type: ignore[index]
    assert instructor.get("/analytics/competency").status_code == 422
