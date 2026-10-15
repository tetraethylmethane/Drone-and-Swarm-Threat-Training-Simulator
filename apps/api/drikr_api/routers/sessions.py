"""Training sessions: lifecycle, live feed, trainee actions, results, AAR timeline and verification.

This router is also the documented simulation adapter protocol (docs/architecture/api-contracts.md):
any visual client (the bundled browser adapter, or a future Unity client) drives an exercise
through ``start/pause/resume/complete``, polls ``feed`` and submits ``actions``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from drikr_api.audit import append_audit
from drikr_api.deps import AppContext, Principal, get_ctx, get_db, require
from drikr_api.errors import ApiError, forbidden, not_found
from drikr_api.models import (
    Assignment,
    FeedbackLevel,
    InstructorReview,
    ReviewStatus,
    Role,
    Scenario,
    ScoreResult,
    SessionEvent,
    SessionStatus,
    TrainingSession,
    utcnow,
)
from drikr_api.schemas import AbortBody, SessionCreate
from drikr_api.security.rbac import Permission
from drikr_api.serializers import briefing, feedback_level_for, page, result_for_viewer, session_out
from drikr_api.services import scoring_service, session_service, settings_service
from drikr_contracts.actions import TraineeAction
from drikr_contracts.events import GROUND_TRUTH_TYPES, EventType

router = APIRouter(prefix="/sessions", tags=["sessions"])

PARTICIPATE = Depends(require(Permission.SESSIONS_PARTICIPATE))
READ = Depends(require(Permission.SESSIONS_READ_ALL, Permission.SESSIONS_READ_OWN))

TIMELINE_CATEGORIES: dict[str, set[str] | None] = {
    "all": None,
    "decisions": {
        EventType.CLASSIFICATION_SUBMITTED.value,
        EventType.RESPONSE_SUBMITTED.value,
        EventType.SENSOR_CONFIRMATION.value,
    },
    "exercise": {
        EventType.SENSOR_STATUS.value,
        EventType.ENVIRONMENT_UPDATE.value,
        EventType.EXERCISE_MESSAGE.value,
        EventType.TRACK_LOST.value,
        EventType.SESSION_STARTED.value,
        EventType.SESSION_PAUSED.value,
        EventType.SESSION_RESUMED.value,
        EventType.SESSION_COMPLETED.value,
    },
    "observations": {EventType.TRACK_OBSERVATION.value},
    "ground_truth": {t.value for t in GROUND_TRUTH_TYPES},
}


def _grace(ctx: AppContext) -> int:
    return ctx.settings.heartbeat_grace_s


def _state(s: TrainingSession, ctx: AppContext, now: datetime | None = None) -> dict[str, Any]:
    return session_out(s, session_service.now_sim_ms(s, now or utcnow(), _grace(ctx)))


def _readable(db: Session, session_id: uuid.UUID, principal: Principal) -> TrainingSession:
    s = db.get(TrainingSession, session_id)
    if s is None:
        raise not_found("Session")
    if principal.can(Permission.SESSIONS_READ_ALL):
        return s
    if s.trainee_id != principal.user.id:
        raise not_found("Session")  # do not reveal other trainees' sessions
    return s


def _owned_locked(db: Session, session_id: uuid.UUID, principal: Principal) -> TrainingSession:
    s = session_service.lock_session(db, session_id)
    if s.trainee_id != principal.user.id:
        raise not_found("Session")
    return s


# --- creation and listing ------------------------------------------------------


@router.post("", status_code=201)
def create(
    body: SessionCreate,
    principal: Principal = PARTICIPATE,
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    assignment = None
    scenario_row = None
    if body.assignment_id:
        assignment = db.scalar(select(Assignment).where(Assignment.id == body.assignment_id).with_for_update())
        if assignment is None:
            raise not_found("Assignment")
    else:
        scenario_row = db.get(Scenario, body.scenario_id)
    s = session_service.create_session(
        db,
        principal.user,
        assignment=assignment,
        scenario_row=scenario_row,
        selection=body.selection,
        self_guided_enabled=settings_service.self_guided_enabled(db),
    )
    db.commit()
    db.refresh(s)
    return {**_state(s, ctx), "briefing": briefing(s.effective_definition)}


@router.get("")
def list_sessions(
    trainee_id: uuid.UUID | None = None,
    scenario_key: str | None = Query(default=None, max_length=64),
    status: SessionStatus | None = None,
    assignment_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    needs_review: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = READ,
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    stmt = filtered_sessions(
        principal, trainee_id, scenario_key, status, assignment_id, date_from, date_to, needs_review
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(TrainingSession.created_at.desc()).limit(limit).offset(offset)).all()
    now = utcnow()
    return page([_state(s, ctx, now) for s in rows], total, limit, offset)


def filtered_sessions(
    principal: Principal,
    trainee_id: uuid.UUID | None,
    scenario_key: str | None,
    status: SessionStatus | None,
    assignment_id: uuid.UUID | None,
    date_from: datetime | None,
    date_to: datetime | None,
    needs_review: bool | None = None,
) -> Any:
    stmt = select(TrainingSession).join(Scenario, Scenario.id == TrainingSession.scenario_id)
    if not principal.can(Permission.SESSIONS_READ_ALL):
        stmt = stmt.where(TrainingSession.trainee_id == principal.user.id)
    elif trainee_id:
        stmt = stmt.where(TrainingSession.trainee_id == trainee_id)
    if scenario_key:
        stmt = stmt.where(Scenario.key == scenario_key)
    if status:
        stmt = stmt.where(TrainingSession.status == status)
    if assignment_id:
        stmt = stmt.where(TrainingSession.assignment_id == assignment_id)
    if date_from:
        stmt = stmt.where(TrainingSession.created_at >= date_from)
    if date_to:
        stmt = stmt.where(TrainingSession.created_at <= date_to)
    if needs_review is not None:
        reviewed = select(InstructorReview.session_id).where(InstructorReview.status == ReviewStatus.REVIEWED)
        stmt = stmt.where(TrainingSession.status == SessionStatus.COMPLETED)
        stmt = stmt.where(TrainingSession.id.not_in(reviewed) if needs_review else TrainingSession.id.in_(reviewed))
    return stmt


@router.get("/{session_id}")
def get_session(
    session_id: uuid.UUID,
    principal: Principal = READ,
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    s = _readable(db, session_id, principal)
    return {**_state(s, ctx), "briefing": briefing(s.effective_definition)}


# --- lifecycle -----------------------------------------------------------------


def _transition(db: Session, ctx: AppContext, principal: Principal, session_id: uuid.UUID, op: str) -> dict[str, Any]:
    now = utcnow()
    s = _owned_locked(db, session_id, principal)
    grace = _grace(ctx)
    if op != "start":
        session_service.refresh(db, s, now, grace, heartbeat=False)
    if op == "start":
        session_service.start(db, s, now)
    elif op == "pause":
        if s.status is SessionStatus.PAUSED and s.pause_reason == "connection_lost":
            pass  # already paused by the server; treat as success
        else:
            session_service.pause(db, s, now, grace)
    elif op == "resume":
        session_service.resume(db, s, now)
    elif op == "complete":
        session_service.complete(db, s, now, grace, "trainee_submitted")
    db.commit()
    db.refresh(s)
    return _state(s, ctx, now)


@router.post("/{session_id}/start")
def start(
    session_id: uuid.UUID,
    principal: Principal = PARTICIPATE,
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    return _transition(db, ctx, principal, session_id, "start")


@router.post("/{session_id}/pause")
def pause(
    session_id: uuid.UUID,
    principal: Principal = PARTICIPATE,
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    return _transition(db, ctx, principal, session_id, "pause")


@router.post("/{session_id}/resume")
def resume(
    session_id: uuid.UUID,
    principal: Principal = PARTICIPATE,
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    return _transition(db, ctx, principal, session_id, "resume")


@router.post("/{session_id}/complete")
def complete(
    session_id: uuid.UUID,
    principal: Principal = PARTICIPATE,
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    return _transition(db, ctx, principal, session_id, "complete")


@router.post("/{session_id}/abort")
def abort(
    session_id: uuid.UUID,
    body: AbortBody,
    principal: Principal = Depends(require(Permission.SESSIONS_ABORT)),
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    now = utcnow()
    s = session_service.lock_session(db, session_id)
    session_service.abort(db, s, now, _grace(ctx), body.reason)
    append_audit(
        db,
        actor=principal.user,
        action="session.aborted",
        target_type="session",
        target_id=s.id,
        details={"reason": body.reason},
        ip_address=principal.ip,
    )
    db.commit()
    db.refresh(s)
    return _state(s, ctx, now)


# --- live exercise ------------------------------------------------------------


@router.get("/{session_id}/feed")
def feed(
    session_id: uuid.UUID,
    since_ms: int = Query(default=0, ge=0),
    principal: Principal = PARTICIPATE,
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """Poll for trainee-visible events. Also acts as the heartbeat for the exercise clock."""
    now = utcnow()
    s = _owned_locked(db, session_id, principal)
    session_service.refresh(db, s, now, _grace(ctx), heartbeat=True)
    db.commit()
    db.refresh(s)
    t = session_service.now_sim_ms(s, now, _grace(ctx))
    events = session_service.feed(db, s, since_ms, t)
    return {"state": session_out(s, t), "events": events}


@router.post("/{session_id}/actions")
def submit_action(
    session_id: uuid.UUID,
    action: TraineeAction,
    principal: Principal = PARTICIPATE,
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    if not ctx.action_limiter.allow(f"session:{session_id}"):
        raise ApiError(429, "rate_limited", "Too many actions submitted; slow down")
    now = utcnow()
    s = _owned_locked(db, session_id, principal)
    try:
        event, duplicate, confirmations = session_service.submit_action(db, s, action, now, _grace(ctx))
    except ApiError:
        db.commit()  # persist any time-based transition applied before rejecting
        raise
    db.commit()
    db.refresh(s)
    return {"event": event, "duplicate": duplicate, "confirmations": confirmations, "state": _state(s, ctx, now)}


# --- results and AAR -----------------------------------------------------------


def _trainee_view(principal: Principal) -> bool:
    return principal.role is Role.TRAINEE


@router.get("/{session_id}/result")
def result(
    session_id: uuid.UUID,
    principal: Principal = READ,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    s = _readable(db, session_id, principal)
    r = db.scalar(select(ScoreResult).where(ScoreResult.session_id == s.id))
    if r is None:
        raise ApiError(404, "result_not_available", "This session has not been scored yet")
    return result_for_viewer(r, trainee_view=_trainee_view(principal), level=feedback_level_for(s))


@router.get("/{session_id}/timeline")
def timeline(
    session_id: uuid.UUID,
    category: str = Query(default="all", pattern="^(all|decisions|exercise|observations|ground_truth)$"),
    track_id: str | None = Query(default=None, pattern=r"^TRK-\d{3}$"),
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    principal: Principal = READ,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    s = _readable(db, session_id, principal)
    if _trainee_view(principal) and s.status not in (SessionStatus.COMPLETED, SessionStatus.ABORTED):
        raise forbidden("The event timeline is available after the exercise is completed")
    include_gt = not _trainee_view(principal) or feedback_level_for(s) is FeedbackLevel.DETAILED
    stmt = select(SessionEvent).where(SessionEvent.session_id == s.id)
    types = TIMELINE_CATEGORIES[category]
    if types is not None:
        stmt = stmt.where(SessionEvent.type.in_(sorted(types)))
    if not include_gt:
        if category == "ground_truth":
            raise forbidden("Ground-truth events are not available at this feedback level")
        stmt = stmt.where(SessionEvent.visibility != "ground_truth")
    if track_id:
        stmt = stmt.where(SessionEvent.payload["track_id"].astext == track_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(SessionEvent.t_ms, SessionEvent.seq).limit(limit).offset(offset)).all()
    out = page([r.as_event() for r in rows], total, limit, offset)
    out["events_purged_at"] = s.events_purged_at.isoformat() if s.events_purged_at else None
    return out


@router.post("/{session_id}/verify")
def verify(
    session_id: uuid.UUID,
    principal: Principal = Depends(require(Permission.SESSIONS_VERIFY)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    s = _readable(db, session_id, principal)
    report = scoring_service.verify(db, s)
    append_audit(
        db,
        actor=principal.user,
        action="session.verified",
        target_type="session",
        target_id=s.id,
        details={"reproducible": report["reproducible"]},
        ip_address=principal.ip,
    )
    db.commit()
    return report
