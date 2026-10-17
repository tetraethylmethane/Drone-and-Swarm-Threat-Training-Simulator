"""Every API route is authenticated unless explicitly listed, and new routes keep role boundaries.

Walks the application's dependency graph instead of a hand-written list, so a newly added route
without authentication fails this test.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import Api, FakeClock, World
from tests.integration.test_reports_analytics import run_exercise

pytestmark = pytest.mark.integration

#: Routes that must be reachable without a session.
PUBLIC = {
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/health/ready"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/mfa/verify"),
    ("POST", "/api/v1/auth/logout"),
}


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000000", path)


def test_every_non_public_operation_rejects_anonymous_calls(world: World) -> None:
    """Calls every operation in the OpenAPI schema without a session: all must answer 401."""
    schema = world.app.openapi()
    operations = [(m.upper(), path) for path, ops in schema["paths"].items() for m in ops]
    assert len(operations) > 60  # sanity: the schema lists the API
    anon = TestClient(world.app)
    wrong = []
    for method, path in operations:
        if (method, path) in PUBLIC:
            continue
        r = anon.request(method, _concrete(path), json={} if method in ("POST", "PUT", "PATCH") else None)
        if r.status_code != 401:
            wrong.append((method, path, r.status_code))
    assert wrong == []


def test_public_routes_reveal_nothing_without_a_session(world: World) -> None:
    anon = world.anon()
    assert anon.get("/auth/me").status_code == 401
    for path in ("/users", "/sessions", "/audit", "/admin/system", "/analytics/units", "/reports/study.csv"):
        assert anon.get(path).status_code == 401, path


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("PUT", "/admin/settings", {}),
        ("POST", "/admin/retention/run", {"dry_run": True}),
        ("GET", "/admin/reproducibility", None),
        ("GET", "/audit", None),
        ("POST", "/users", {}),
        ("PATCH", "/users/00000000-0000-0000-0000-000000000000", {"unit": "x"}),
    ],
)
def test_instructors_cannot_change_administrator_configuration(
    instructor: Api, method: str, path: str, body: dict[str, Any] | None
) -> None:
    r = {"GET": instructor.get, "PUT": instructor.put, "POST": instructor.post, "PATCH": instructor.patch}[method](
        path, *([] if body is None else [body])
    )
    assert r.status_code == 403, (path, r.status_code, r.text)


def test_trainees_cannot_reach_other_trainees_records(
    instructor: Api, trainee: Api, trainee2: Api, clock: FakeClock
) -> None:
    other = run_exercise(trainee2, instructor, clock)
    mine = run_exercise(trainee, instructor, clock)
    for path in (
        f"/sessions/{other}",
        f"/sessions/{other}/result",
        f"/sessions/{other}/timeline",
        f"/reports/sessions/{other}.pdf",
        f"/analytics/compare?a={mine}&b={other}",
    ):
        assert trainee.get(path).status_code == 404, path  # existence is not revealed
    assert trainee.post(f"/sessions/{other}/verify").status_code == 403
    progress = trainee.get(f"/analytics/progress?trainee_id={trainee2.user['id']}").json()  # type: ignore[index]
    assert {p["trainee"]["id"] for p in progress["points"]} == {trainee.user["id"]}  # type: ignore[index]
    assert trainee.get("/reports/sessions.csv").status_code == 403
    assert trainee.get("/reports/study.csv").status_code == 403
