"""Instructor override of adaptive difficulty: bounded, one step, explained, audited, instructor-only."""

from __future__ import annotations

import pytest

from tests.integration.conftest import Api, FakeClock, assign
from tests.integration.test_reports_analytics import run_exercise

pytestmark = pytest.mark.integration


def test_instructor_override_is_bounded_explained_and_used(
    admin: Api, instructor: Api, trainee: Api, clock: FakeClock
) -> None:
    a = assign(
        instructor, trainee, difficulty_mode="adaptive", difficulty_level=2, min_level=1, max_level=3, max_attempts=5
    )
    aid = a["id"]
    assert instructor.post(f"/assignments/{aid}/difficulty", {"level": 4, "reason": "too easy"}).status_code == 422
    r = instructor.post(f"/assignments/{aid}/difficulty", {"level": 3, "reason": "Ready for a harder picture"})
    assert r.status_code == 200 and r.json() == {
        "assignment_id": aid,
        "from_level": 2,
        "to_level": 3,
        "change": "increase",
    }
    assert (
        instructor.post(f"/assignments/{aid}/difficulty", {"level": 1, "reason": "x" * 3}).json()["error"]["code"]
        == "one_step_only"
    )
    # The next session runs at the overridden level, and the change is explained in the history.
    s = trainee.post("/sessions", {"assignment_id": aid}).json()
    assert s["difficulty_level"] == 3
    adjustments = instructor.get(f"/analytics/difficulty?trainee_id={trainee.user['id']}").json()["items"]  # type: ignore[index]
    assert any(x["reason"].startswith("Instructor override by") for x in adjustments)
    assert any(
        e["action"] == "assignment.difficulty_override" for e in admin.get("/audit?action=assignment").json()["items"]
    )
    # Trainees cannot override, and fixed assignments have nothing to override.
    assert trainee.post(f"/assignments/{aid}/difficulty", {"level": 2, "reason": "please"}).status_code == 403
    fixed = assign(instructor, trainee, max_attempts=2)
    assert instructor.post(f"/assignments/{fixed['id']}/difficulty", {"level": 3, "reason": "n/a"}).status_code == 409


def test_automatic_adjustments_still_follow_completed_sessions(instructor: Api, trainee: Api, clock: FakeClock) -> None:
    sid = run_exercise(trainee, instructor, clock, difficulty_mode="adaptive", min_level=1, max_level=4, max_attempts=3)
    items = instructor.get(f"/analytics/difficulty?trainee_id={trainee.user['id']}").json()["items"]  # type: ignore[index]
    assert items and items[0]["reason"] and sid
