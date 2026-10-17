"""Raw event logs can be deleted only by a recorded purge (security finding F-09, migration 0005).

Before 0005 the API's database role could delete a session's events and set `events_purged_at`, and
verification then reported a routine purge. Each attempt below runs as the least-privilege role.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import DBAPIError

from drikr_api import db_roles
from tests.integration.conftest import TEST_URL, Api, FakeClock, World
from tests.integration.test_retention import backdate, finished_session, set_retention

pytestmark = pytest.mark.integration

ROLE = "drikr_app_purge_test"
ROLE_PASSWORD = "app-role-purge-test-password-0123456789"  # test database only


@pytest.fixture
def app_engine(engine: Engine) -> Iterator[Engine]:
    with engine.begin() as conn:
        db_roles.provision(conn, ROLE, ROLE_PASSWORD)
    url = make_url(TEST_URL).set(username=ROLE, password=ROLE_PASSWORD).render_as_string(hide_password=False)
    eng = create_engine(url)
    yield eng
    eng.dispose()


def _events(engine: Engine, sid: str) -> int:
    with engine.connect() as c:
        return int(
            c.execute(text("SELECT count(*) FROM session_events WHERE session_id = :s"), {"s": sid}).scalar_one()
        )


def _fake_run(c: object, days: int | None = 30) -> str:
    """A retention-run row as a compromised API could insert it (the role may insert runs)."""
    run_id = str(uuid.uuid4())
    c.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO retention_runs (id, trigger, dry_run, policy, summary, started_at) "
            "VALUES (:id, 'cli', false, CAST(:p AS jsonb), '{}', now())"
        ),
        {"id": run_id, "p": json.dumps({"session_event_days": days})},
    )
    return run_id


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("DELETE FROM session_events WHERE session_id = :s", "permission denied"),
        ("UPDATE training_sessions SET events_purged_at = now() WHERE id = :s", "no recorded purge"),
        (
            "INSERT INTO event_log_purges (session_id, reason, purged_at, events_deleted) "
            "VALUES (:s, 'anonymisation', now(), 0)",
            "permission denied",
        ),
    ],
)
def test_app_role_cannot_delete_or_mark_logs_purged(
    world: World,
    app_engine: Engine,
    engine: Engine,
    trainee: Api,
    instructor: Api,
    clock: FakeClock,
    sql: str,
    message: str,
) -> None:
    sid = finished_session(trainee, instructor, clock)
    before = _events(engine, sid)
    with pytest.raises(DBAPIError, match=message), app_engine.begin() as c:
        c.execute(text(sql), {"s": sid})
    assert _events(engine, sid) == before > 0
    assert instructor.post(f"/sessions/{sid}/verify").json()["reproducible"]


def test_purge_function_refuses_recent_sessions_and_unusable_runs(
    world: World, app_engine: Engine, engine: Engine, trainee: Api, instructor: Api, clock: FakeClock
) -> None:
    sid = finished_session(trainee, instructor, clock)  # completed now: younger than any allowed cutoff
    with app_engine.begin() as c:
        run_id = _fake_run(c, days=30)
        row = c.execute(
            text("SELECT sessions_purged, events_deleted FROM drikr_purge_session_events(:r, ARRAY[CAST(:s AS uuid)])"),
            {"r": run_id, "s": sid},
        ).one()
    assert tuple(row) == (0, 0)  # skipped, not deleted
    assert _events(engine, sid) > 0
    for days in (5, None):  # below the policy minimum, or purging disabled
        with app_engine.begin() as c:
            run_id = _fake_run(c, days=days)
        with pytest.raises(DBAPIError, match="minimum 30 days"), app_engine.begin() as c:
            c.execute(
                text("SELECT * FROM drikr_purge_session_events(:r, ARRAY[CAST(:s AS uuid)])"), {"r": run_id, "s": sid}
            )
    with pytest.raises(DBAPIError, match="not an in-progress, non-dry run"), app_engine.begin() as c:
        c.execute(
            text("SELECT * FROM drikr_purge_session_events(:r, ARRAY[CAST(:s AS uuid)])"),
            {"r": str(uuid.uuid4()), "s": sid},
        )
    # The anonymisation path needs a deactivated account.
    with pytest.raises(DBAPIError, match="not a deactivated account"), app_engine.begin() as c:
        c.execute(text("SELECT * FROM drikr_purge_user_event_logs(:u)"), {"u": trainee.user["id"]})  # type: ignore[index]
    assert _events(engine, sid) > 0


def test_legitimate_purges_are_recorded_and_verified(
    world: World, admin: Api, instructor: Api, trainee: Api, clock: FakeClock, engine: Engine
) -> None:
    old = finished_session(trainee, instructor, clock)
    backdate(world, old, 200)
    set_retention(admin, session_event_days=90)
    assert (
        admin.post("/admin/retention/run", {"dry_run": False}).json()["summary"]["session_event_logs"]["sessions"] == 1
    )
    v = instructor.post(f"/sessions/{old}/verify").json()
    assert v["reproducible"] and v["purge_recorded"] and v["purge"]["reason"] == "retention"
    with engine.connect() as c:
        rec = c.execute(
            text("SELECT reason, events_deleted FROM event_log_purges WHERE session_id = :s"), {"s": old}
        ).one()
    assert rec.reason == "retention" and rec.events_deleted > 100
    # The record is append-only for every role, including the owner.
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as c:
        c.execute(text("DELETE FROM event_log_purges WHERE session_id = :s"), {"s": old})
    report = admin.get("/admin/reproducibility?limit=50").json()
    assert report["counts"]["event_log_purged"] == 1 and report["counts"]["not_reproducible"] == 0


def test_unrecorded_or_inconsistent_purges_are_flagged(
    world: World, admin: Api, instructor: Api, trainee: Api, clock: FakeClock, engine: Engine
) -> None:
    sid = finished_session(trainee, instructor, clock)
    # A record claiming anonymisation for an account that was never anonymised (written here with
    # owner rights, which the API role does not have), followed by the flag it permits.
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO event_log_purges (session_id, reason, purged_at, events_deleted) "
                "VALUES (:s, 'anonymisation', now(), 0)"
            ),
            {"s": sid},
        )
        c.execute(text("UPDATE training_sessions SET events_purged_at = now() WHERE id = :s"), {"s": sid})
    v = instructor.post(f"/sessions/{sid}/verify").json()
    assert v["events_purged_at"] and not v["purge_recorded"] and not v["reproducible"]
    report = admin.get("/admin/reproducibility?limit=50").json()
    assert [f["reason"] for f in report["failures"]] == ["purge_unrecorded"]
    # Once set, the flag cannot be changed again.
    with pytest.raises(DBAPIError, match="cannot be changed once set"), engine.begin() as c:
        c.execute(text("UPDATE training_sessions SET events_purged_at = NULL WHERE id = :s"), {"s": sid})
