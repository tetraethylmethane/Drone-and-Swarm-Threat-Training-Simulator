"""Training analytics computed from persisted records only (no synthetic or sample data)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from drikr_api.deps import Principal, get_db, require
from drikr_api.models import (
    Assignment,
    DifficultyAdjustment,
    InstructorReview,
    ReviewStatus,
    Role,
    Scenario,
    ScoreResult,
    SessionStatus,
    TrainingSession,
    User,
)
from drikr_api.security.rbac import Permission
from drikr_scoring import stats

router = APIRouter(prefix="/analytics", tags=["analytics"])

ANY_READ = Depends(require(Permission.ANALYTICS_READ_ALL, Permission.ANALYTICS_READ_OWN))


def _scope_trainee(principal: Principal, trainee_id: uuid.UUID | None) -> uuid.UUID | None:
    if principal.can(Permission.ANALYTICS_READ_ALL):
        return trainee_id
    return principal.user.id


@router.get("/progress")
def progress(
    trainee_id: uuid.UUID | None = None,
    scenario_key: str | None = Query(default=None, max_length=64),
    objective_id: str | None = Query(default=None, max_length=40),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    principal: Principal = ANY_READ,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """One point per completed, scored session, oldest first."""
    tid = _scope_trainee(principal, trainee_id)
    stmt = (
        select(TrainingSession, ScoreResult, Scenario, User)
        .join(ScoreResult, ScoreResult.session_id == TrainingSession.id)
        .join(Scenario, Scenario.id == TrainingSession.scenario_id)
        .join(User, User.id == TrainingSession.trainee_id)
        .where(TrainingSession.status == SessionStatus.COMPLETED, ScoreResult.status == "scored")
    )
    if tid:
        stmt = stmt.where(TrainingSession.trainee_id == tid)
    if scenario_key:
        stmt = stmt.where(Scenario.key == scenario_key)
    if date_from:
        stmt = stmt.where(TrainingSession.completed_at >= date_from)
    if date_to:
        stmt = stmt.where(TrainingSession.completed_at <= date_to)
    rows = db.execute(stmt.order_by(TrainingSession.completed_at).limit(limit)).all()
    points = []
    for s, r, scn, u in rows:
        objectives = {o["id"]: o["status"] for o in r.result.get("objectives", [])}
        if objective_id and objective_id not in objectives:
            continue
        points.append(
            {
                "session_id": str(s.id),
                "trainee": {"id": str(u.id), "display_name": u.display_name},
                "scenario_key": scn.key,
                "scenario_version": scn.version,
                "scenario_name": scn.name,
                "mode": s.mode.value,
                "difficulty_level": s.difficulty_level,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "overall": r.overall,
                "passed": r.passed,
                "rubric_version": r.rubric_version,
                "dimensions": {k: v.get("score") for k, v in r.result.get("dimensions", {}).items()},
                "objective_status": objectives.get(objective_id) if objective_id else None,
            }
        )
    return {
        "points": points,
        "units": {
            "overall": "percent (0-100)",
            "dimensions": "percent (0-100); null = not applicable",
            "difficulty_level": "1-5",
        },
    }


@router.get("/filters")
def filters(principal: Principal = ANY_READ, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Values available for analytics filters, derived from recorded sessions."""
    tid = _scope_trainee(principal, None)
    stmt = (
        select(Scenario.key, Scenario.name, Scenario.definition)
        .join(TrainingSession, TrainingSession.scenario_id == Scenario.id)
        .where(TrainingSession.status == SessionStatus.COMPLETED)
    )
    if tid:
        stmt = stmt.where(TrainingSession.trainee_id == tid)
    scenarios: dict[str, str] = {}
    objectives: dict[str, str] = {}
    for key, name, definition in db.execute(stmt.distinct()).all():
        scenarios[key] = name
        for o in definition["learning_objectives"]:
            objectives.setdefault(o["id"], o["description"])
    trainees: list[dict[str, str]] = []
    if principal.can(Permission.ANALYTICS_READ_ALL):
        trainees = [
            {"id": str(u.id), "display_name": u.display_name}
            for u in db.scalars(select(User).where(User.role == Role.TRAINEE).order_by(User.display_name)).all()
        ]
    return {
        "scenarios": [{"key": k, "name": v} for k, v in sorted(scenarios.items())],
        "objectives": [{"id": k, "description": v} for k, v in sorted(objectives.items())],
        "trainees": trainees,
    }


@router.get("/overview")
def overview(
    _: Principal = Depends(require(Permission.ANALYTICS_READ_ALL)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    completed = db.scalar(select(func.count()).where(TrainingSession.status == SessionStatus.COMPLETED)) or 0
    in_progress = (
        db.scalar(
            select(func.count()).where(
                TrainingSession.status.in_([SessionStatus.CREATED, SessionStatus.RUNNING, SessionStatus.PAUSED])
            )
        )
        or 0
    )
    avg = db.scalar(select(func.avg(ScoreResult.overall)).where(ScoreResult.status == "scored"))
    reviewed = select(InstructorReview.session_id).where(InstructorReview.status == ReviewStatus.REVIEWED)
    awaiting = (
        db.scalar(
            select(func.count()).where(
                TrainingSession.status == SessionStatus.COMPLETED, TrainingSession.id.not_in(reviewed)
            )
        )
        or 0
    )
    return {
        "trainees": db.scalar(select(func.count()).where(User.role == Role.TRAINEE, User.is_active.is_(True))) or 0,
        "active_assignments": db.scalar(select(func.count()).where(Assignment.status == "active")) or 0,
        "sessions_completed": completed,
        "sessions_in_progress": in_progress,
        "sessions_awaiting_review": awaiting,
        "average_overall": round(float(avg), 1) if avg is not None else None,
    }


@router.get("/difficulty")
def difficulty_history(
    trainee_id: uuid.UUID | None = None,
    principal: Principal = ANY_READ,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    tid = _scope_trainee(principal, trainee_id)
    stmt = select(DifficultyAdjustment).order_by(DifficultyAdjustment.created_at.desc()).limit(200)
    if tid:
        stmt = stmt.where(DifficultyAdjustment.trainee_id == tid)
    return {
        "items": [
            {
                "id": str(a.id),
                "trainee_id": str(a.trainee_id),
                "assignment_id": str(a.assignment_id) if a.assignment_id else None,
                "scenario_key": a.scenario_key,
                "session_id": str(a.triggered_by_session_id) if a.triggered_by_session_id else None,
                "from_level": a.from_level,
                "to_level": a.to_level,
                "change": a.change,
                "confidence": a.confidence,
                "reason": a.reason,
                "created_at": a.created_at.isoformat(),
            }
            for a in db.scalars(stmt).all()
        ]
    }


@router.get("/learning-gains")
def learning_gains(
    trainee_id: uuid.UUID | None = None,
    scenario_key: str | None = Query(default=None, max_length=64),
    same_difficulty_only: bool = False,
    principal: Principal = ANY_READ,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """First versus latest scored attempt per trainee and scenario, with cohort statistics.

    Observational only: gains can reflect practice with the same scenario, changed difficulty or
    selection effects. It is not evidence of training effectiveness on its own
    (docs/research/training-effectiveness-study-protocol.md describes a controlled design).
    """
    tid = _scope_trainee(principal, trainee_id)
    stmt = (
        select(TrainingSession, ScoreResult, Scenario, User)
        .join(ScoreResult, ScoreResult.session_id == TrainingSession.id)
        .join(Scenario, Scenario.id == TrainingSession.scenario_id)
        .join(User, User.id == TrainingSession.trainee_id)
        .where(TrainingSession.status == SessionStatus.COMPLETED, ScoreResult.status == "scored")
        .order_by(TrainingSession.completed_at)
    )
    if tid:
        stmt = stmt.where(TrainingSession.trainee_id == tid)
    if scenario_key:
        stmt = stmt.where(Scenario.key == scenario_key)
    groups: dict[tuple[uuid.UUID, str], list[tuple[TrainingSession, ScoreResult, User]]] = {}
    for s, r, scn, u in db.execute(stmt).all():
        groups.setdefault((u.id, scn.key), []).append((s, r, u))
    pairs: list[dict[str, Any]] = []
    for (_, key), rows in sorted(groups.items(), key=lambda kv: (kv[1][0][2].display_name, kv[0][1])):
        if len(rows) < 2:
            continue
        (s0, r0, u), (s1, r1, _) = rows[0], rows[-1]
        if same_difficulty_only and s0.difficulty_level != s1.difficulty_level:
            continue
        pairs.append(
            {
                "trainee": {"id": str(u.id), "display_name": u.display_name},
                "scenario_key": key,
                "sessions": len(rows),
                "first": {
                    "session_id": str(s0.id),
                    "overall": r0.overall,
                    "difficulty_level": s0.difficulty_level,
                    "completed_at": s0.completed_at.isoformat() if s0.completed_at else None,
                },
                "latest": {
                    "session_id": str(s1.id),
                    "overall": r1.overall,
                    "difficulty_level": s1.difficulty_level,
                    "completed_at": s1.completed_at.isoformat() if s1.completed_at else None,
                },
                "gain": round(float(r1.overall or 0) - float(r0.overall or 0), 1),
                "difficulty_changed": s0.difficulty_level != s1.difficulty_level,
            }
        )
    gains = [float(p["gain"]) for p in pairs]
    summary: dict[str, Any] = {"pairs": len(pairs)}
    if len(gains) >= 2:
        lo, hi = stats.bootstrap_mean_ci(gains)
        summary.update(
            mean_gain=round(stats.mean(gains), 2),
            sd_gain=round(stats.sd(gains), 2),
            ci95=[round(lo, 2), round(hi, 2)],
            effect_size_dz=round(stats.cohen_dz(gains), 3),
            improved=sum(1 for g in gains if g > 0),
            declined=sum(1 for g in gains if g < 0),
            sign_test_p=round(stats.sign_test_p(gains), 4),
            difficulty_changed=sum(1 for p in pairs if p["difficulty_changed"]),
        )
    return {
        "pairs": pairs,
        "summary": summary,
        "interpretation": "Observational within-trainee comparison of first and latest attempts. Not a controlled "
        "study: practice effects, scenario familiarity and difficulty changes are not separated from learning.",
    }
