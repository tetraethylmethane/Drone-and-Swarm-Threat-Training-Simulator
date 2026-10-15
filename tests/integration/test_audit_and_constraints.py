"""Tamper-evident audit chain, append-only enforcement and database integrity constraints."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError

from tests.integration.conftest import Api, World, assign

pytestmark = pytest.mark.integration

USER_INSERT = (
    "INSERT INTO users (id, username, display_name, role, password_hash, is_active, must_change_password, "
    "failed_login_count, password_changed_at, created_at, updated_at) "
)


def test_privileged_actions_are_audited(world: World, admin: Api, instructor: Api, trainee: Api) -> None:
    admin.post(
        "/users",
        {"username": "audited", "display_name": "Audited User", "role": "trainee", "password": "Audit-Pass-2026!"},
    )
    a = assign(instructor, trainee)
    sid = trainee.post("/sessions", {"assignment_id": a["id"]}).json()["id"]
    instructor.post(f"/sessions/{sid}/abort", {"reason": "audit test"})
    instructor.get("/reports/sessions.csv")
    actions = {e["action"] for e in admin.get("/audit?limit=500").json()["items"]}
    assert {
        "user.created",
        "assignment.created",
        "session.aborted",
        "report.exported",
        "auth.login_succeeded",
    } <= actions
    v = admin.get("/audit/verify").json()
    assert v["valid"] is True and v["checked"] >= 5


def test_audit_table_is_append_only(engine: Engine, admin: Api) -> None:
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as c:
        c.execute(text("UPDATE audit_events SET action = 'tampered'"))
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as c:
        c.execute(text("DELETE FROM audit_events"))


def test_tampering_is_detected(engine: Engine, admin: Api, instructor: Api) -> None:
    instructor.post("/scenarios/generate", {"seed": 3})
    admin.post(
        "/users", {"username": "tamper.x", "display_name": "Tamper", "role": "trainee", "password": "Tamper-Pass-2026!"}
    )
    with engine.begin() as c:
        target = c.execute(text("SELECT id FROM audit_events ORDER BY id LIMIT 1 OFFSET 1")).scalar()
        # Simulate a privileged attacker who bypasses the trigger.
        c.execute(text("SET LOCAL session_replication_role = replica"))
        c.execute(text("UPDATE audit_events SET details = '{\"forged\": true}' WHERE id = :i"), {"i": target})
    v = admin.get("/audit/verify").json()
    assert v["valid"] is False and v["first_invalid_id"] == target


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO rubrics (id, key, version, name, definition, digest, is_demo, created_at) "
        "SELECT gen_random_uuid(), key, version, name, definition, digest, false, now() FROM rubrics LIMIT 1",
        USER_INSERT
        + "VALUES (gen_random_uuid(), 'Bad Name!', 'x', 'trainee', 'h', true, false, 0, now(), now(), now())",
        USER_INSERT
        + "VALUES (gen_random_uuid(), 'okname', 'x', 'superuser', 'h', true, false, 0, now(), now(), now())",
    ],
    ids=["duplicate-version", "bad-username", "unknown-role"],
)
def test_database_rejects_invalid_records(engine: Engine, world: World, sql: str) -> None:
    with pytest.raises((IntegrityError, DBAPIError)), engine.begin() as c:
        c.execute(text(sql))


def test_event_and_score_constraints(engine: Engine, world: World, instructor: Api, trainee: Api) -> None:
    a = assign(instructor, trainee)
    sid = trainee.post("/sessions", {"assignment_id": a["id"]}).json()["id"]
    bad_events = [
        ("G-000000", 0, 150, 150),  # duplicate seq / event id
        ("S-999998", 999998, 150, 150),  # not tick-quantised
        ("S-999999", 999999, 500, 400),  # available before t
    ]
    for event_id, seq, t, avail in bad_events:
        with pytest.raises(IntegrityError), engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO session_events (session_id, seq, event_id, t_ms, available_at_ms, type, visibility, "
                    "origin, payload, recorded_at) "
                    "VALUES (:s, :q, :e, :t, :a, 'exercise_message', 'trainee', 'system', '{}', now())"
                ),
                {"s": uuid.UUID(sid), "q": seq, "e": event_id, "t": t, "a": avail},
            )
    with pytest.raises(IntegrityError), engine.begin() as c:
        c.execute(text("UPDATE assignments SET difficulty_level = 5, max_level = 4"))
    with pytest.raises(IntegrityError), engine.begin() as c:
        c.execute(text("UPDATE training_sessions SET status = 'running', running_since = NULL"))
