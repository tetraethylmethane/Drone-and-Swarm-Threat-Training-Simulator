"""Data retention and anonymisation.

What is removed, and what is kept (see docs/security/data-retention.md):

* **Session event logs** of completed or aborted sessions older than the policy period are deleted.
  The score result (including all explanations), configuration, seed and digests are kept, so the
  timeline can still be regenerated and the stored score remains attributable to its inputs; the
  stored log itself can no longer be re-scored.
* **Expired or revoked sign-in sessions** and MFA challenges older than the policy period.
* **Anonymisation** of a deactivated account replaces its identifying fields, removes its
  credentials, MFA data and sign-in sessions, deletes the event logs of its sessions (which may
  contain free-text notes) and clears free text in instructor reviews of those sessions. Scores
  remain as pseudonymous training records.
* **Audit events are never deleted or altered** (append-only, tamper-evident). They retain the
  username recorded at the time of each event; this is a documented exception for security logging.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from drikr_api.audit import append_audit
from drikr_api.errors import ApiError, conflict
from drikr_api.models import (
    AuthSession,
    InstructorReview,
    MfaChallenge,
    RetentionRun,
    Role,
    SessionEvent,
    SessionStatus,
    TrainingSession,
    User,
    utcnow,
)
from drikr_api.security.passwords import hash_password
from drikr_api.services import mfa_service, settings_service
from drikr_api.services.settings_service import RetentionPolicy

FINISHED = (SessionStatus.COMPLETED, SessionStatus.ABORTED)


def _event_cutoff(policy: RetentionPolicy, now: datetime) -> datetime | None:
    return now - timedelta(days=policy.session_event_days) if policy.session_event_days else None


def _sessions_due(db: Session, cutoff: datetime) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(TrainingSession.id).where(
                TrainingSession.status.in_(FINISHED),
                TrainingSession.completed_at < cutoff,
                TrainingSession.events_purged_at.is_(None),
            )
        ).all()
    )


def _auth_filter(cutoff: datetime) -> Any:
    return or_(AuthSession.expires_at < cutoff, AuthSession.revoked_at < cutoff)


def _users_due(db: Session, policy: RetentionPolicy, now: datetime) -> list[User]:
    if not policy.anonymise_deactivated_after_days:
        return []
    cutoff = now - timedelta(days=policy.anonymise_deactivated_after_days)
    return list(
        db.scalars(
            select(User).where(
                User.is_active.is_(False),
                User.anonymised_at.is_(None),
                User.deactivated_at.is_not(None),
                User.deactivated_at < cutoff,
            )
        ).all()
    )


def preview(db: Session, policy: RetentionPolicy | None = None, now: datetime | None = None) -> dict[str, Any]:
    policy = policy or settings_service.retention_policy(db)
    now = now or utcnow()
    out: dict[str, Any] = {"policy": policy.model_dump(), "evaluated_at": now.isoformat()}
    cutoff = _event_cutoff(policy, now)
    if cutoff:
        ids = _sessions_due(db, cutoff)
        events = (
            db.scalar(select(func.count()).select_from(SessionEvent).where(SessionEvent.session_id.in_(ids)))
            if ids
            else 0
        )
        out["session_event_logs"] = {"sessions": len(ids), "events": events or 0, "older_than": cutoff.isoformat()}
    else:
        out["session_event_logs"] = {"sessions": 0, "events": 0, "older_than": None, "disabled": True}
    auth_cutoff = now - timedelta(days=policy.auth_record_days)
    out["auth_records"] = {
        "sessions": db.scalar(select(func.count()).select_from(AuthSession).where(_auth_filter(auth_cutoff))) or 0,
        "mfa_challenges": db.scalar(
            select(func.count()).select_from(MfaChallenge).where(MfaChallenge.expires_at < auth_cutoff)
        )
        or 0,
        "older_than": auth_cutoff.isoformat(),
    }
    users = _users_due(db, policy, now)
    out["accounts_to_anonymise"] = {"count": len(users), "disabled": policy.anonymise_deactivated_after_days is None}
    return out


def _purge_events(db: Session, session_ids: list[uuid.UUID], now: datetime) -> int:
    if not session_ids:
        return 0
    deleted = db.execute(delete(SessionEvent).where(SessionEvent.session_id.in_(session_ids))).rowcount or 0
    db.execute(update(TrainingSession).where(TrainingSession.id.in_(session_ids)).values(events_purged_at=now))
    return int(deleted)


def anonymise_user(
    db: Session, user: User, actor: User | None, ip: str | None = None, now: datetime | None = None
) -> dict[str, Any]:
    now = now or utcnow()
    if user.anonymised_at is not None:
        raise conflict("already_anonymised", "This account has already been anonymised")
    if user.is_active:
        raise conflict("account_active", "Deactivate the account before anonymising it")
    if actor is not None and user.id == actor.id:
        raise conflict("self_anonymise", "You cannot anonymise your own account")
    if user.role is Role.ADMINISTRATOR:
        others = (
            db.scalar(
                select(func.count()).where(
                    User.role == Role.ADMINISTRATOR, User.is_active.is_(True), User.id != user.id
                )
            )
            or 0
        )
        if others == 0:
            raise conflict("last_admin", "At least one active administrator must remain")
    original = user.username
    session_ids = list(db.scalars(select(TrainingSession.id).where(TrainingSession.trainee_id == user.id)).all())
    finished = list(
        db.scalars(
            select(TrainingSession.id).where(
                TrainingSession.trainee_id == user.id, TrainingSession.status.in_(FINISHED)
            )
        ).all()
    )
    if len(finished) != len(session_ids):
        raise conflict("sessions_in_progress", "The account has unfinished exercise sessions; abort them first")
    events = _purge_events(db, finished, now)
    if session_ids:
        db.execute(
            update(InstructorReview)
            .where(InstructorReview.session_id.in_(session_ids))
            .values(notes="", strengths="", improvements="")
        )
    mfa_service.clear(db, user)
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    pseudonym = f"deleted-{uuid.uuid4().hex[:10]}"
    user.username = pseudonym
    user.display_name = "Deleted user"
    user.password_hash = hash_password(secrets.token_urlsafe(32))
    user.must_change_password = True
    user.failed_login_count = 0
    user.locked_until = None
    user.anonymised_at = now
    db.flush()
    summary = {"pseudonym": pseudonym, "sessions_retained": len(session_ids), "events_deleted": events}
    append_audit(
        db,
        actor=actor,
        action="user.anonymised",
        target_type="user",
        target_id=user.id,
        details={"previous_username": original, **summary},
        ip_address=ip,
    )
    return summary


def run(db: Session, actor: User | None, *, dry_run: bool, trigger: str, ip: str | None = None) -> RetentionRun:
    policy = settings_service.retention_policy(db)
    now = utcnow()
    record = RetentionRun(
        actor_id=actor.id if actor else None,
        trigger=trigger,
        dry_run=dry_run,
        policy=policy.model_dump(),
        summary={},
        started_at=now,
    )
    db.add(record)
    if dry_run:
        record.summary = preview(db, policy, now)
    else:
        summary: dict[str, Any] = {}
        cutoff = _event_cutoff(policy, now)
        ids = _sessions_due(db, cutoff) if cutoff else []
        summary["session_event_logs"] = {"sessions": len(ids), "events_deleted": _purge_events(db, ids, now)}
        auth_cutoff = now - timedelta(days=policy.auth_record_days)
        summary["auth_records"] = {
            "sessions_deleted": db.execute(delete(AuthSession).where(_auth_filter(auth_cutoff))).rowcount or 0,
            "mfa_challenges_deleted": db.execute(
                delete(MfaChallenge).where(MfaChallenge.expires_at < auth_cutoff)
            ).rowcount
            or 0,
        }
        anonymised = []
        for u in _users_due(db, policy, now):
            try:
                anonymised.append(anonymise_user(db, u, actor, ip, now)["pseudonym"])
            except ApiError as exc:  # e.g. unfinished sessions: skip and report
                summary.setdefault("skipped_accounts", []).append({"user_id": str(u.id), "reason": exc.code})
        summary["accounts_anonymised"] = len(anonymised)
        record.summary = summary
    record.finished_at = utcnow()
    db.flush()
    append_audit(
        db,
        actor=actor,
        action="retention.dry_run" if dry_run else "retention.executed",
        target_type="retention_run",
        target_id=record.id,
        details={"trigger": trigger, "summary": record.summary},
        ip_address=ip,
    )
    return record


def run_out(r: RetentionRun) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "trigger": r.trigger,
        "dry_run": r.dry_run,
        "policy": r.policy,
        "summary": r.summary,
        "started_at": r.started_at.isoformat(),
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
    }
