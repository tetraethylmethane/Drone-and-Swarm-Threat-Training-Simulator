"""Exercise assignments: instructors assign scenario versions to trainees."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from drikr_api.audit import append_audit
from drikr_api.deps import Principal, get_db, require
from drikr_api.errors import ApiError, conflict, not_found
from drikr_api.models import (
    Assignment,
    DifficultyAdjustment,
    DifficultyMode,
    Role,
    Scenario,
    ScoreResult,
    SessionStatus,
    TrainingSession,
    User,
)
from drikr_api.schemas import AssignmentCreate
from drikr_api.security.rbac import Permission
from drikr_api.serializers import assignment_out, page
from drikr_api.services import adaptive_service
from drikr_contracts.scenario import Scenario as ScenarioContract

router = APIRouter(prefix="/assignments", tags=["assignments"])

ACTIVE = (SessionStatus.CREATED, SessionStatus.RUNNING, SessionStatus.PAUSED)


def progress(db: Session, a: Assignment) -> dict[str, Any]:
    rows = db.execute(
        select(TrainingSession, ScoreResult)
        .outerjoin(ScoreResult, ScoreResult.session_id == TrainingSession.id)
        .where(TrainingSession.assignment_id == a.id)
        .order_by(TrainingSession.created_at)
    ).all()
    sessions = [
        {
            "id": str(s.id),
            "attempt_number": s.attempt_number,
            "status": s.status.value,
            "difficulty_level": s.difficulty_level,
            "overall": r.overall if r else None,
            "passed": r.passed if r else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        }
        for s, r in rows
    ]
    used = sum(1 for s, _ in rows if s.status is not SessionStatus.ABORTED)
    scored = [x["overall"] for x in sessions if x["overall"] is not None]
    active = next((x["id"] for x in sessions if x["status"] in {st.value for st in ACTIVE}), None)
    if a.status != "active":
        state = "cancelled"
    elif active:
        state = "in_progress"
    elif any(x["status"] == "completed" for x in sessions):
        state = "completed" if used >= a.max_attempts or any(x["passed"] for x in sessions) else "attempted"
    else:
        state = "not_started"
    return {
        "state": state,
        "attempts_used": used,
        "attempts_remaining": max(0, a.max_attempts - used),
        "best_overall": max(scored) if scored else None,
        "active_session_id": active,
        "next_difficulty_level": adaptive_service.next_level_for_assignment(db, a),
        "sessions": sessions,
    }


@router.get("")
def list_assignments(
    trainee_id: uuid.UUID | None = None,
    scenario_key: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None, pattern="^(active|cancelled)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require(Permission.ASSIGNMENTS_MANAGE, Permission.ASSIGNMENTS_READ_OWN)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    stmt = select(Assignment).join(Scenario, Scenario.id == Assignment.scenario_id)
    trainee_view = principal.role is Role.TRAINEE
    if trainee_view:
        stmt = stmt.where(Assignment.trainee_id == principal.user.id, Assignment.status == "active")
    else:
        if trainee_id:
            stmt = stmt.where(Assignment.trainee_id == trainee_id)
        if status:
            stmt = stmt.where(Assignment.status == status)
    if scenario_key:
        stmt = stmt.where(Scenario.key == scenario_key)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Assignment.created_at.desc()).limit(limit).offset(offset)).all()
    return page([assignment_out(a, progress(db, a), for_trainee=trainee_view) for a in rows], total, limit, offset)


@router.post("", status_code=201)
def create_assignments(
    body: AssignmentCreate,
    principal: Principal = Depends(require(Permission.ASSIGNMENTS_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    scn = db.get(Scenario, body.scenario_id)
    if scn is None:
        raise not_found("Scenario")
    if scn.status != "published":
        raise conflict("scenario_archived", "Archived scenarios cannot be assigned")
    d = ScenarioContract.model_validate(scn.definition).difficulty
    if body.min_level < d.min_level or body.max_level > d.max_level:
        raise ApiError(
            422,
            "difficulty_out_of_bounds",
            f"Difficulty bounds must lie within the scenario's {d.min_level}..{d.max_level}",
        )
    if body.difficulty_mode.value == "adaptive" and not d.adaptive_allowed:
        raise ApiError(422, "adaptive_not_allowed", "This scenario does not allow adaptive difficulty")
    if (
        body.trainee_options.allow_custom_seed
        and not ScenarioContract.model_validate(scn.definition).randomization.allow_seed_override
    ):
        raise ApiError(422, "seed_override_not_allowed", "This scenario does not allow seed overrides")
    trainees = db.scalars(select(User).where(User.id.in_(body.trainee_ids))).all()
    found = {t.id: t for t in trainees}
    bad = [
        str(t)
        for t in body.trainee_ids
        if t not in found or found[t].role is not Role.TRAINEE or not found[t].is_active
    ]
    if bad:
        raise ApiError(422, "invalid_trainees", "Assignments can only be made to active trainees", {"trainee_ids": bad})

    created = []
    for tid in body.trainee_ids:
        a = Assignment(
            scenario_id=scn.id,
            trainee_id=tid,
            assigned_by_id=principal.user.id,
            title=body.title,
            instructions=body.instructions,
            trainee_options=body.trainee_options.model_dump(mode="json"),
            difficulty_mode=body.difficulty_mode,
            difficulty_level=body.difficulty_level,
            min_level=body.min_level,
            max_level=body.max_level,
            max_attempts=body.max_attempts,
            feedback_level=body.feedback_level,
            due_at=body.due_at,
        )
        db.add(a)
        db.flush()
        append_audit(
            db,
            actor=principal.user,
            action="assignment.created",
            target_type="assignment",
            target_id=a.id,
            details={
                "scenario": f"{scn.key}@{scn.version}",
                "trainee_id": str(tid),
                "difficulty_mode": body.difficulty_mode.value,
            },
            ip_address=principal.ip,
        )
        created.append(a)
    db.commit()
    return {"items": [assignment_out(a, progress(db, a)) for a in created]}


def _load(db: Session, assignment_id: uuid.UUID, principal: Principal) -> Assignment:
    a = db.get(Assignment, assignment_id)
    if a is None or (principal.role is Role.TRAINEE and (a.trainee_id != principal.user.id or a.status != "active")):
        raise not_found("Assignment")
    return a


@router.get("/{assignment_id}")
def get_assignment(
    assignment_id: uuid.UUID,
    principal: Principal = Depends(require(Permission.ASSIGNMENTS_MANAGE, Permission.ASSIGNMENTS_READ_OWN)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    a = _load(db, assignment_id, principal)
    return assignment_out(a, progress(db, a), for_trainee=True)


@router.post("/{assignment_id}/cancel")
def cancel(
    assignment_id: uuid.UUID,
    principal: Principal = Depends(require(Permission.ASSIGNMENTS_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    a = _load(db, assignment_id, principal)
    if a.status != "cancelled":
        a.status = "cancelled"
        append_audit(
            db,
            actor=principal.user,
            action="assignment.cancelled",
            target_type="assignment",
            target_id=a.id,
            ip_address=principal.ip,
        )
        db.commit()
    return assignment_out(a, progress(db, a))


class DifficultyOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: int = Field(ge=1, le=5)
    reason: str = Field(min_length=3, max_length=280)


@router.post("/{assignment_id}/difficulty")
def override_difficulty(
    assignment_id: uuid.UUID,
    body: DifficultyOverride,
    principal: Principal = Depends(require(Permission.ASSIGNMENTS_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Instructor override of an adaptive assignment's next level (one step at a time, within bounds)."""
    a = _load(db, assignment_id, principal)
    if a.difficulty_mode is not DifficultyMode.ADAPTIVE:
        raise conflict("not_adaptive", "Only adaptive assignments have a level to override; edit fixed ones directly")
    current = adaptive_service.next_level_for_assignment(db, a)
    if not a.min_level <= body.level <= a.max_level:
        raise ApiError(
            422, "level_out_of_bounds", f"Choose a level between {a.min_level} and {a.max_level} for this assignment"
        )
    if abs(body.level - current) > 1:
        raise ApiError(422, "one_step_only", f"Change one level at a time (current level {current})")
    change = "increase" if body.level > current else "decrease" if body.level < current else "hold"
    adj = DifficultyAdjustment(
        trainee_id=a.trainee_id,
        assignment_id=a.id,
        scenario_key=a.scenario.key,
        triggered_by_session_id=None,
        from_level=current,
        to_level=body.level,
        change=change,
        confidence="high",
        reason=f"Instructor override by {principal.user.display_name}: {body.reason}",
        evidence={"override": True, "by": principal.user.username, "previous_level": current},
    )
    db.add(adj)
    append_audit(
        db,
        actor=principal.user,
        action="assignment.difficulty_override",
        target_type="assignment",
        target_id=a.id,
        details={"from_level": current, "to_level": body.level, "reason": body.reason},
        ip_address=principal.ip,
    )
    db.commit()
    return {"assignment_id": str(a.id), "from_level": current, "to_level": body.level, "change": change}
