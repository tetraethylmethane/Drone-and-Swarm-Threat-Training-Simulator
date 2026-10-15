"""Learning-gain analytics and the pseudonymised study export."""

from __future__ import annotations

import csv
import io

import pytest

from tests.integration.conftest import Api, FakeClock
from tests.integration.test_reports_analytics import run_exercise

pytestmark = pytest.mark.integration


def test_learning_gains_from_persisted_attempts(instructor: Api, trainee: Api, trainee2: Api, clock: FakeClock) -> None:
    assert instructor.get("/analytics/learning-gains").json()["summary"] == {"pairs": 0}
    # trainee1: first attempt idle, second attempt classifies everything -> positive gain
    run_exercise(trainee, instructor, clock, classify=None, max_attempts=5)
    run_exercise(trainee, instructor, clock, classify="small_multirotor", max_attempts=5)
    run_exercise(trainee2, instructor, clock, classify=None)
    run_exercise(trainee2, instructor, clock, classify="bird_or_clutter")
    out = instructor.get("/analytics/learning-gains").json()
    pairs = out["pairs"]
    assert {p["trainee"]["display_name"] for p in pairs} == {"Demo Trainee One", "Demo Trainee Two"}
    for p in pairs:
        first = instructor.get(f"/sessions/{p['first']['session_id']}/result").json()["overall"]
        latest = instructor.get(f"/sessions/{p['latest']['session_id']}/result").json()["overall"]
        assert p["gain"] == pytest.approx(round(latest - first, 1))
    s = out["summary"]
    assert s["pairs"] == 2 and s["ci95"][0] <= s["mean_gain"] <= s["ci95"][1]
    assert 0 <= s["sign_test_p"] <= 1 and "Not a controlled study" in out["interpretation"]
    # Trainees only see their own pair.
    mine = trainee.get("/analytics/learning-gains").json()["pairs"]
    assert [p["trainee"]["display_name"] for p in mine] == ["Demo Trainee One"]


def test_study_export_is_pseudonymised(instructor: Api, trainee: Api, clock: FakeClock) -> None:
    run_exercise(trainee, instructor, clock)
    run_exercise(trainee, instructor, clock)
    r = instructor.get("/reports/study.csv")
    assert r.status_code == 200
    text = r.text
    for identifying in ("trainee1", "Demo Trainee", trainee.user["id"]):  # type: ignore[index]
        assert identifying not in text
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == 2 and rows[0]["participant"] == rows[1]["participant"]
    assert rows[0]["participant"].startswith("P-") and len(rows[0]["completed_date"]) == 10
    assert trainee.get("/reports/study.csv").status_code == 403
