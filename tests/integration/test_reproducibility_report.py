"""Bulk reproducibility report and measured request performance on System health."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.integration.conftest import Api, FakeClock
from tests.integration.test_reports_analytics import run_exercise

pytestmark = pytest.mark.integration


def test_report_counts_and_flags_a_changed_log(
    engine: Engine, admin: Api, instructor: Api, trainee: Api, clock: FakeClock
) -> None:
    good = run_exercise(trainee, instructor, clock)
    bad = run_exercise(trainee, instructor, clock)
    out = admin.get("/admin/reproducibility?limit=10").json()
    assert out["counts"]["checked"] == 2 and out["counts"]["reproducible"] == 2 and out["failures"] == []
    assert out["counts"]["exact_score_match"] == 2

    with engine.begin() as c:  # privileged edit of one generated event, bypassing triggers
        c.execute(text("SET LOCAL session_replication_role = replica"))
        c.execute(
            text(
                "UPDATE session_events SET payload = jsonb_set(payload, '{quality}', '0.01') "
                "WHERE id = (SELECT id FROM session_events WHERE session_id = :s AND type = 'track_observation' "
                "ORDER BY seq LIMIT 1)"
            ),
            {"s": uuid.UUID(bad)},
        )
    out = admin.get("/admin/reproducibility?limit=10").json()
    assert out["counts"]["not_reproducible"] == 1
    assert out["failures"] == [
        {
            "session_id": bad,
            "completed_at": out["failures"][0]["completed_at"],
            "reason": "stored_log_changed",
            "note": None,
        }
    ]
    assert good not in {f["session_id"] for f in out["failures"]}
    actions = [e["action"] for e in admin.get("/audit?action=reproducibility").json()["items"]]
    assert actions.count("reproducibility.report") == 2
    assert instructor.get("/admin/reproducibility").status_code == 403


def test_system_health_reports_measured_request_times(admin: Api, trainee: Api) -> None:
    for _ in range(3):
        trainee.get("/sessions")
    perf = admin.get("/admin/system").json()["performance"]
    routes = {r["route"]: r for r in perf["routes"]}
    assert routes["GET /sessions"]["requests"] >= 3
    row = routes["GET /sessions"]
    assert 0 < row["p50_ms"] <= row["p95_ms"] <= row["max_ms"]
    assert perf["requests_total"] >= 3 and "Server time only" in perf["note"]
    # Route templates, never concrete ids, so no personal or session data is kept.
    assert all("{" in r["route"] or r["route"].count("/") <= 3 for r in perf["routes"])
