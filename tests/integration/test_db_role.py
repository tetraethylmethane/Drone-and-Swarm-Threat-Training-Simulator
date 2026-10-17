"""Least-privilege database role (security finding F-01).

The API connects as a role that can read and write rows but cannot rewrite history: no updates to
the audit log, scores or event logs, no trigger bypass, no schema changes. The full training workflow
must still work through the API when it runs as that role.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import DBAPIError

from drikr_api import db_roles
from drikr_api.db import Database
from drikr_api.main import create_app
from tests.integration.conftest import PASSWORD, TEST_URL, Api, FakeClock, World, make_settings
from tests.integration.test_reports_analytics import run_exercise

pytestmark = pytest.mark.integration

ROLE = "drikr_app_test"
ROLE_PASSWORD = "app-role-test-password-0123456789"  # test database only


@pytest.fixture
def app_url(engine: Engine) -> str:
    with engine.begin() as conn:
        db_roles.provision(conn, ROLE, ROLE_PASSWORD)
    return make_url(TEST_URL).set(username=ROLE, password=ROLE_PASSWORD).render_as_string(hide_password=False)


@pytest.fixture
def app_engine(app_url: str) -> Iterator[Engine]:
    eng = create_engine(app_url)
    yield eng
    eng.dispose()


def test_url_parsing_decides_whether_a_separate_role_is_used() -> None:
    owner = "postgresql+psycopg://drikr:ownerpw@db:5432/drikr"
    assert db_roles.app_role_from_urls(owner, owner) is None
    assert db_roles.app_role_from_urls("postgresql+psycopg://drikr_app:pw@db:5432/drikr", owner) == ("drikr_app", "pw")
    with pytest.raises(ValueError):
        db_roles.app_role_from_urls("postgresql+psycopg://Robert';--:pw@db/drikr", owner)


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE audit_events SET action = 'x'",
        "DELETE FROM audit_events",
        "UPDATE score_results SET overall = 100",
        "DELETE FROM score_results",
        "UPDATE session_events SET payload = '{}'",
        "TRUNCATE session_events",
        "SET session_replication_role = replica",
        "ALTER TABLE score_results DISABLE TRIGGER ALL",
        "DROP TRIGGER audit_events_append_only ON audit_events",
        "CREATE TABLE intruder (id int)",
        "UPDATE alembic_version SET version_num = '0000'",
    ],
)
def test_app_role_cannot_rewrite_history_or_the_schema(app_engine: Engine, sql: str) -> None:
    with pytest.raises(DBAPIError, match=r"permission denied|must be owner|must be superuser"), app_engine.begin() as c:
        c.execute(text(sql))


def test_app_role_attributes(app_engine: Engine) -> None:
    with app_engine.connect() as c:
        info = db_roles.describe_current_role(c)
    assert info == {"name": ROLE, "superuser": False, "owns_tables": False, "least_privilege": True}


def test_full_workflow_runs_as_the_app_role(world: World, app_url: str, engine: Engine, clock: FakeClock) -> None:
    database = Database(app_url)
    app = create_app(make_settings(database_url=app_url), database)
    clients: list[TestClient] = []

    def login(username: str) -> Api:
        c = TestClient(app)
        clients.append(c)
        api = Api(c)
        r = api.post("/auth/login", {"username": username, "password": PASSWORD})
        assert r.status_code == 200, r.text
        api.csrf, api.user = r.json()["csrf_token"], r.json()["user"]
        return api

    try:
        instructor, trainee, admin = login("instructor"), login("trainee1"), login("admin")
        sid = run_exercise(trainee, instructor, clock)  # assign, run, decide, complete, score
        assert instructor.get(f"/sessions/{sid}/result").json()["status"] == "scored"
        assert instructor.post(f"/sessions/{sid}/verify").json()["reproducible"]
        assert (
            instructor.put(
                f"/sessions/{sid}/review", {"status": "reviewed", "notes": "n", "strengths": "s", "improvements": "i"}
            ).status_code
            == 200
        )
        assert instructor.get(f"/reports/sessions/{sid}.pdf").status_code == 200
        assert admin.get("/audit/verify").json()["valid"] is True
        health = admin.get("/admin/system").json()["database"]["role"]
        assert health["least_privilege"] is True and health["name"] == ROLE
        # Retention deletes old event logs (allowed) and keeps the score (immutable).
        with engine.begin() as c:
            c.execute(
                text("UPDATE training_sessions SET completed_at = now() - interval '400 days' WHERE id = :s"),
                {"s": uuid.UUID(sid)},
            )
        current = admin.get("/admin/settings").json()
        admin.put(
            "/admin/settings",
            {**current, "retention_policy": {**current["retention_policy"], "session_event_days": 90}},
        )
        run = admin.post("/admin/retention/run", {"dry_run": False}).json()
        assert run["summary"]["session_event_logs"]["sessions"] >= 1
        assert instructor.get(f"/sessions/{sid}/result").json()["status"] == "scored"
        # Anonymising a user updates their account, reviews and sessions: all permitted.
        uid = trainee.user["id"]  # type: ignore[index]
        admin.patch(f"/users/{uid}", {"is_active": False})
        assert admin.post(f"/users/{uid}/anonymise", {"confirm_username": "trainee1"}).status_code == 200
    finally:
        for c in clients:
            c.close()
        database.dispose()
