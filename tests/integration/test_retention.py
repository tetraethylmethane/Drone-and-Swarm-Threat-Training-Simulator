"""Data retention: policy validation, preview, purge, anonymisation and verification after purge."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text, update

from drikr_api.models import AuthSession, SessionEvent, TrainingSession, User, utcnow
from tests.integration.conftest import PASSWORD, Api, FakeClock, World, assign

pytestmark = pytest.mark.integration


def finished_session(trainee: Api, instructor: Api, clock: FakeClock, note: str = "Private observation") -> str:
    a = assign(instructor, trainee)
    sid = trainee.post("/sessions", {"assignment_id": a["id"]}).json()["id"]
    trainee.post(f"/sessions/{sid}/start")
    tracks: set[str] = set()
    for _ in range(8):
        clock.advance(5)
        tracks |= {
            e["payload"]["track_id"]
            for e in trainee.get(f"/sessions/{sid}/feed").json()["events"]
            if e["type"] == "track_observation"
        }
    tid = sorted(tracks)[0]
    trainee.post(
        f"/sessions/{sid}/actions",
        {
            "client_action_id": str(uuid.uuid4()),
            "kind": "classify",
            "track_ids": [tid],
            "classification": "unknown",
            "confidence": "low",
            "note": note,
        },
    )
    trainee.post(f"/sessions/{sid}/complete")
    return sid


def set_retention(admin: Api, **policy: object) -> object:
    current = admin.get("/admin/settings").json()
    return admin.put("/admin/settings", {**current, "retention_policy": {**current["retention_policy"], **policy}})


def backdate(world: World, sid: str, days: int) -> None:
    with world.app.state.ctx.database.session_factory() as db:
        db.execute(
            update(TrainingSession)
            .where(TrainingSession.id == uuid.UUID(sid))
            .values(completed_at=utcnow() - timedelta(days=days))
        )
        db.commit()


def test_policy_bounds_are_validated(admin: Api) -> None:
    r = set_retention(admin, session_event_days=5)
    assert r.status_code == 422  # minimum 30 days
    assert set_retention(admin, session_event_days=90, anonymise_deactivated_after_days=365).status_code == 200


def test_preview_and_purge_keep_scores(
    world: World, admin: Api, instructor: Api, trainee: Api, clock: FakeClock
) -> None:
    old = finished_session(trainee, instructor, clock)
    recent = finished_session(trainee, instructor, clock)
    backdate(world, old, 200)
    before = instructor.get(f"/sessions/{old}/result").json()
    set_retention(admin, session_event_days=90)

    preview = admin.get("/admin/retention/preview").json()
    assert preview["session_event_logs"]["sessions"] == 1 and preview["session_event_logs"]["events"] > 100
    dry = admin.post("/admin/retention/run", {"dry_run": True}).json()
    assert dry["dry_run"] and dry["summary"]["session_event_logs"]["sessions"] == 1
    with world.app.state.ctx.database.session_factory() as db:
        assert (
            db.scalar(select(func.count()).select_from(SessionEvent).where(SessionEvent.session_id == uuid.UUID(old)))
            > 0
        )

    run = admin.post("/admin/retention/run", {"dry_run": False}).json()
    assert run["summary"]["session_event_logs"]["sessions"] == 1
    with world.app.state.ctx.database.session_factory() as db:
        assert (
            db.scalar(select(func.count()).select_from(SessionEvent).where(SessionEvent.session_id == uuid.UUID(old)))
            == 0
        )
        assert (
            db.scalar(
                select(func.count()).select_from(SessionEvent).where(SessionEvent.session_id == uuid.UUID(recent))
            )
            > 0
        )

    # The score and its explanation survive; the timeline is gone but explained; verify still regenerates.
    assert instructor.get(f"/sessions/{old}/result").json() == before
    tl = instructor.get(f"/sessions/{old}/timeline").json()
    assert tl["total"] == 0 and tl["events_purged_at"]
    v = instructor.post(f"/sessions/{old}/verify").json()
    assert v["timeline_reproduced"] and v["stored_log_intact"] is None and v["reproducible"]
    assert instructor.get(f"/reports/sessions/{old}.pdf").status_code == 200
    # Idempotent: a second run purges nothing more.
    assert (
        admin.post("/admin/retention/run", {"dry_run": False}).json()["summary"]["session_event_logs"]["sessions"] == 0
    )
    runs = admin.get("/admin/retention/runs").json()["items"]
    assert len(runs) == 3
    actions = {e["action"] for e in admin.get("/audit?action=retention").json()["items"]}
    assert actions == {"retention.dry_run", "retention.executed"}


def test_expired_auth_records_are_removed(world: World, admin: Api) -> None:
    world.login("trainee2").post("/auth/logout")
    with world.app.state.ctx.database.session_factory() as db:
        db.execute(
            update(AuthSession)
            .where(AuthSession.revoked_at.is_not(None))
            .values(revoked_at=utcnow() - timedelta(days=60))
        )
        db.commit()
    assert admin.get("/admin/retention/preview").json()["auth_records"]["sessions"] >= 1
    out = admin.post("/admin/retention/run", {"dry_run": False}).json()
    assert out["summary"]["auth_records"]["sessions_deleted"] >= 1
    assert admin.get("/auth/me").status_code == 200  # live sessions untouched


def test_anonymise_deactivated_account(
    world: World, admin: Api, instructor: Api, trainee: Api, clock: FakeClock
) -> None:
    sid = finished_session(trainee, instructor, clock, note="Trainee mentioned their home town")
    instructor.put(
        f"/sessions/{sid}/review",
        {"status": "reviewed", "notes": "Personal remark", "strengths": "Good", "improvements": "More"},
    )
    uid = trainee.user["id"]  # type: ignore[index]
    score = instructor.get(f"/sessions/{sid}/result").json()["overall"]

    r = admin.post(f"/users/{uid}/anonymise", {"confirm_username": "trainee1"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "account_active"
    admin.patch(f"/users/{uid}", {"is_active": False})
    assert admin.post(f"/users/{uid}/anonymise", {"confirm_username": "wrong"}).status_code == 422
    out = admin.post(f"/users/{uid}/anonymise", {"confirm_username": "trainee1"}).json()
    assert out["username"].startswith("deleted-") and out["display_name"] == "Deleted user" and out["anonymised_at"]
    assert out["anonymisation"]["events_deleted"] > 0

    with world.app.state.ctx.database.session_factory() as db:
        dump = db.execute(text("SELECT string_agg(payload::text, ' ') FROM session_events")).scalar() or ""
        assert "home town" not in dump
        assert db.scalar(select(func.count()).select_from(User).where(User.username == "trainee1")) == 0
        rv = db.execute(text("SELECT notes || strengths || improvements FROM instructor_reviews")).scalar()
        assert rv == ""
    # Scores remain as pseudonymous records; the account cannot sign in or be reactivated.
    assert instructor.get(f"/sessions/{sid}/result").json()["overall"] == score
    assert world.anon().post("/auth/login", {"username": "trainee1", "password": PASSWORD}).status_code == 401
    assert admin.patch(f"/users/{uid}", {"is_active": True}).status_code == 409
    audit = admin.get("/audit?action=user.anonymised").json()["items"][0]
    assert audit["details"]["previous_username"] == "trainee1"  # documented: the audit log keeps history


def test_policy_anonymises_after_period(world: World, admin: Api, trainee2: Api) -> None:
    uid = trainee2.user["id"]  # type: ignore[index]
    admin.patch(f"/users/{uid}", {"is_active": False})
    set_retention(admin, anonymise_deactivated_after_days=30)
    assert admin.get("/admin/retention/preview").json()["accounts_to_anonymise"]["count"] == 0
    with world.app.state.ctx.database.session_factory() as db:
        db.execute(update(User).where(User.id == uuid.UUID(uid)).values(deactivated_at=utcnow() - timedelta(days=45)))
        db.commit()
    assert admin.get("/admin/retention/preview").json()["accounts_to_anonymise"]["count"] == 1
    assert admin.post("/admin/retention/run", {"dry_run": False}).json()["summary"]["accounts_anonymised"] == 1


def test_retention_requires_administrator(instructor: Api, trainee: Api) -> None:
    for api in (instructor, trainee):
        assert api.get("/admin/retention/preview").status_code == 403
        assert api.post("/admin/retention/run", {"dry_run": True}).status_code == 403
