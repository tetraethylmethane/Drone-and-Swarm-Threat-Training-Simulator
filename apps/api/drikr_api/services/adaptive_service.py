"""Persistence and application of rules-based adaptive difficulty.

After every scored session in an adaptive context the policy is evaluated and
its recommendation (including "hold") is stored with its reason and evidence in
``difficulty_adjustments``. The next attempt uses the latest recorded level.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from drikr_api.models import (
    Assignment,
    DifficultyAdjustment,
    DifficultyMode,
    Scenario,
    ScoreResult,
    SessionMode,
    SessionStatus,
    TrainingSession,
    User,
)
from drikr_api.services import settings_service
from drikr_contracts.scenario import Scenario as ScenarioContract
from drikr_scoring.adaptive import SessionOutcome, recommend_level


def _latest_adjustment(db: Session, *conds: object) -> DifficultyAdjustment | None:
    return db.scalar(
        select(DifficultyAdjustment).where(*conds).order_by(DifficultyAdjustment.created_at.desc()).limit(1)  # type: ignore[arg-type]
    )


def next_level_for_assignment(db: Session, a: Assignment) -> int:
    if a.difficulty_mode is DifficultyMode.FIXED:
        return a.difficulty_level
    adj = _latest_adjustment(db, DifficultyAdjustment.assignment_id == a.id)
    level = adj.to_level if adj else a.difficulty_level
    return max(a.min_level, min(a.max_level, level))


def _scenario_bounds(row: Scenario) -> tuple[int, int, int, bool]:
    d = ScenarioContract.model_validate(row.definition).difficulty
    return d.level, d.min_level, d.max_level, d.adaptive_allowed


def next_level_self_guided(db: Session, trainee: User, row: Scenario) -> int:
    base, lo, hi, adaptive = _scenario_bounds(row)
    if not adaptive:
        return base
    adj = _latest_adjustment(
        db,
        DifficultyAdjustment.trainee_id == trainee.id,
        DifficultyAdjustment.assignment_id.is_(None),
        DifficultyAdjustment.scenario_key == row.key,
    )
    level = adj.to_level if adj else base
    return max(lo, min(hi, level))


def _history(db: Session, s: TrainingSession) -> list[SessionOutcome]:
    q = (
        select(TrainingSession, ScoreResult)
        .join(ScoreResult, ScoreResult.session_id == TrainingSession.id)
        .where(
            TrainingSession.trainee_id == s.trainee_id,
            TrainingSession.status == SessionStatus.COMPLETED,
            ScoreResult.status == "scored",
        )
        .order_by(TrainingSession.completed_at)
    )
    if s.assignment_id is not None:
        q = q.where(TrainingSession.assignment_id == s.assignment_id)
    else:
        q = q.join(Scenario, Scenario.id == TrainingSession.scenario_id).where(
            TrainingSession.mode == SessionMode.SELF_GUIDED, Scenario.key == s.scenario.key
        )
    return [
        SessionOutcome(
            str(ts.id),
            float(r.overall or 0.0),
            ts.difficulty_level,
            ts.completed_at.isoformat() if ts.completed_at else "",
        )
        for ts, r in db.execute(q).all()
    ]


def record_after_session(db: Session, s: TrainingSession) -> DifficultyAdjustment | None:
    a = s.assignment
    if a is not None:
        if a.difficulty_mode is not DifficultyMode.ADAPTIVE:
            return None
        lo, hi = a.min_level, a.max_level
    else:
        _, lo, hi, adaptive = _scenario_bounds(s.scenario)
        if not adaptive:
            return None
    rec = recommend_level(_history(db, s), s.difficulty_level, lo, hi, settings_service.adaptive_policy(db))
    adj = DifficultyAdjustment(
        trainee_id=s.trainee_id,
        assignment_id=s.assignment_id,
        scenario_key=s.scenario.key,
        triggered_by_session_id=s.id,
        from_level=rec.current_level,
        to_level=rec.recommended_level,
        change=rec.change,
        confidence=rec.confidence,
        reason=rec.reason,
        evidence=rec.evidence,
    )
    db.add(adj)
    db.flush()
    return adj
