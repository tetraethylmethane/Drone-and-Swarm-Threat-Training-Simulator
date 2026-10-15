"""Instructor review of completed sessions (notes, status and structured feedback)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from drikr_api.audit import append_audit
from drikr_api.deps import Principal, get_db, require
from drikr_api.errors import ApiError, not_found
from drikr_api.models import InstructorReview, Role, SessionStatus, TrainingSession
from drikr_api.schemas import ReviewBody
from drikr_api.security.rbac import Permission
from drikr_api.serializers import review_out

router = APIRouter(prefix="/sessions", tags=["reviews"])


@router.get("/{session_id}/review")
def get_review(
    session_id: uuid.UUID,
    principal: Principal = Depends(require(Permission.SESSIONS_READ_ALL, Permission.SESSIONS_READ_OWN)),
    db: Session = Depends(get_db),
) -> dict[str, Any] | None:
    s = db.get(TrainingSession, session_id)
    if s is None or (principal.role is Role.TRAINEE and s.trainee_id != principal.user.id):
        raise not_found("Session")
    rv = db.scalar(select(InstructorReview).where(InstructorReview.session_id == s.id))
    if rv is None or (principal.role is Role.TRAINEE and not rv.shared_with_trainee):
        return None
    out = review_out(rv)
    if principal.role is Role.TRAINEE:
        out.pop("notes")  # private instructor notes are never shared
    return out


@router.put("/{session_id}/review")
def put_review(
    session_id: uuid.UUID,
    body: ReviewBody,
    principal: Principal = Depends(require(Permission.REVIEWS_WRITE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    s = db.get(TrainingSession, session_id)
    if s is None:
        raise not_found("Session")
    if s.status is not SessionStatus.COMPLETED:
        raise ApiError(409, "not_completed", "Only completed sessions can be reviewed")
    objective_ids = {o["id"] for o in s.effective_definition["learning_objectives"]}
    unknown = [o for o in body.focus_objectives if o not in objective_ids]
    if unknown:
        raise ApiError(
            422, "unknown_objectives", "Focus objectives must belong to the scenario", {"objective_ids": unknown}
        )
    rv = db.scalar(select(InstructorReview).where(InstructorReview.session_id == s.id).with_for_update())
    if rv is None:
        rv = InstructorReview(session_id=s.id, reviewer_id=principal.user.id, status=body.status)
        db.add(rv)
    rv.reviewer_id = principal.user.id
    rv.status = body.status
    rv.notes = body.notes
    rv.strengths = body.strengths
    rv.improvements = body.improvements
    rv.focus_objectives = body.focus_objectives
    rv.shared_with_trainee = body.shared_with_trainee
    db.flush()
    append_audit(
        db,
        actor=principal.user,
        action="review.saved",
        target_type="session",
        target_id=s.id,
        details={"status": body.status.value, "shared_with_trainee": body.shared_with_trainee},
        ip_address=principal.ip,
    )
    db.commit()
    db.refresh(rv)
    return review_out(rv)
