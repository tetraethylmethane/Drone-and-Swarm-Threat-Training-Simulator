"""Unit (team) membership and unit-level reporting."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from tests.integration.conftest import Api, FakeClock
from tests.integration.test_reports_analytics import run_exercise

pytestmark = pytest.mark.integration


def test_unit_summary_and_filters(admin: Api, instructor: Api, trainee: Api, trainee2: Api, clock: FakeClock) -> None:
    t1, t2 = trainee.user["id"], trainee2.user["id"]  # type: ignore[index]
    r = admin.patch(f"/users/{t1}", {"unit": "  Alpha   Section "})
    assert r.status_code == 200 and r.json()["unit"] == "Alpha Section"  # whitespace normalised
    admin.patch(f"/users/{t2}", {"unit": "Bravo"})
    s1 = run_exercise(trainee, instructor, clock)
    run_exercise(trainee2, instructor, clock, classify=None)

    out = instructor.get("/analytics/units").json()["units"]
    by = {u["unit"]: u for u in out}
    assert by["Alpha Section"]["trainees"] == 1 and by["Alpha Section"]["sessions"] == 1
    assert by["Bravo"]["sessions"] == 1
    alpha_score = instructor.get(f"/sessions/{s1}/result").json()["overall"]
    assert by["Alpha Section"]["mean_overall"] == pytest.approx(round(alpha_score, 1))

    pts = instructor.get("/analytics/progress?unit=Bravo").json()["points"]
    assert pts and {p["trainee"]["id"] for p in pts} == {t2}
    assert "Alpha Section" in instructor.get("/analytics/filters").json()["units"]

    # Clearing, auditing and permissions.
    assert admin.patch(f"/users/{t2}", {"unit": ""}).json()["unit"] is None
    assert admin.patch(f"/users/{t1}", {"display_name": "Renamed"}).json()["unit"] == "Alpha Section"  # omitted = kept
    audit = admin.get("/audit?action=user.updated").json()["items"]
    assert any("unit" in e["details"] for e in audit)
    assert trainee.get("/analytics/units").status_code == 403


def test_database_rejects_blank_unit(engine: Engine, trainee: Api) -> None:
    with pytest.raises(IntegrityError), engine.begin() as c:
        c.execute(text("UPDATE users SET unit = '   ' WHERE username = 'trainee1'"))
