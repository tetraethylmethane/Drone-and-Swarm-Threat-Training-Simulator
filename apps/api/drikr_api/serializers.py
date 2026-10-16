"""Response serialisation. Controls exactly which fields each role may see."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from drikr_api.models import (
    Assignment,
    FeedbackLevel,
    InstructorReview,
    Rubric,
    Scenario,
    ScoreResult,
    SessionMode,
    TrainingSession,
    User,
    utcnow,
)


def _dt(v: datetime | None) -> str | None:
    return v.isoformat() if v else None


def user_out(u: User) -> dict[str, Any]:
    return {
        "id": str(u.id),
        "username": u.username,
        "display_name": u.display_name,
        "role": u.role.value,
        "is_active": u.is_active,
        "must_change_password": u.must_change_password,
        "locked": bool(u.locked_until and u.locked_until > utcnow()),
        "mfa_enabled": u.mfa_enabled,
        "deactivated_at": _dt(u.deactivated_at),
        "anonymised_at": _dt(u.anonymised_at),
        "unit": u.unit,
        "created_at": _dt(u.created_at),
    }


def user_ref(u: User) -> dict[str, Any]:
    return {"id": str(u.id), "username": u.username, "display_name": u.display_name}


def rubric_out(r: Rubric, *, full: bool = False) -> dict[str, Any]:
    d = r.definition
    out: dict[str, Any] = {
        "id": str(r.id),
        "key": r.key,
        "version": r.version,
        "name": r.name,
        "description": d.get("description"),
        "weights": d.get("weights"),
        "pass_mark": d.get("pass_mark"),
        "digest": r.digest,
        "is_demo": r.is_demo,
        "created_at": _dt(r.created_at),
    }
    if full:
        out["definition"] = d
    return out


def scenario_summary(s: Scenario, version_count: int | None = None) -> dict[str, Any]:
    d = s.definition
    out = {
        "id": str(s.id),
        "key": s.key,
        "version": s.version,
        "name": s.name,
        "description": d["description"],
        "status": s.status,
        "is_demo": s.is_demo,
        "self_guided": s.self_guided,
        "environment": d["environment"],
        "duration_s": d["time_limits"]["duration_s"],
        "difficulty": d["difficulty"],
        "objective_count": len(d["learning_objectives"]),
        "entity_group_count": len(d["entities"]),
        "rubric": {
            "id": str(s.rubric_id),
            "key": d["scoring"]["rubric_key"],
            "version": d["scoring"]["rubric_version"],
        },
        "digest": s.digest,
        "created_at": _dt(s.created_at),
    }
    if version_count is not None:
        out["version_count"] = version_count
    return out


def scenario_out(s: Scenario) -> dict[str, Any]:
    return {**scenario_summary(s), "definition": s.definition}


def briefing(definition: dict[str, Any]) -> dict[str, Any]:
    """Trainee-safe view of a scenario: no entity groups or other ground truth."""
    sensors = definition["sensors"]
    return {
        "name": definition["name"],
        "description": definition["description"],
        "briefing": definition["briefing"],
        "learning_objectives": [
            {"id": o["id"], "description": o["description"]} for o in definition["learning_objectives"]
        ],
        "environment": definition["environment"],
        "sensors": {
            k: {"enabled": v["enabled"], "range_m": v["range_m"], "update_interval_s": v["update_interval_s"]}
            for k, v in sensors.items()
        },
        "duration_s": definition["time_limits"]["duration_s"],
        "allow_pause": definition["time_limits"]["allow_pause"],
        "synthetic_notice": "All tracks, sensor readings and events in this exercise are synthetic training data.",
    }


def assignment_out(
    a: Assignment, progress: dict[str, Any] | None = None, *, for_trainee: bool = False
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": str(a.id),
        "title": a.title,
        "instructions": a.instructions,
        "status": a.status,
        "scenario": {
            "id": str(a.scenario_id),
            "key": a.scenario.key,
            "version": a.scenario.version,
            "name": a.scenario.name,
        },
        "trainee": user_ref(a.trainee),
        "assigned_by": user_ref(a.assigned_by),
        "trainee_options": a.trainee_options,
        "difficulty_mode": a.difficulty_mode.value,
        "difficulty_level": a.difficulty_level,
        "min_level": a.min_level,
        "max_level": a.max_level,
        "max_attempts": a.max_attempts,
        "feedback_level": a.feedback_level.value,
        "due_at": _dt(a.due_at),
        "created_at": _dt(a.created_at),
    }
    if progress is not None:
        out["progress"] = progress
    if for_trainee:
        out["briefing"] = briefing(a.scenario.definition)
    return out


def result_summary(r: ScoreResult | None) -> dict[str, Any] | None:
    if r is None:
        return None
    return {
        "status": r.status,
        "overall": r.overall,
        "passed": r.passed,
        "rubric_version": r.rubric_version,
        "scoring_engine_version": r.scoring_engine_version,
    }


def session_out(s: TrainingSession, sim_time_ms: int) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "status": s.status.value,
        "mode": s.mode.value,
        "attempt_number": s.attempt_number,
        "trainee": user_ref(s.trainee),
        "scenario": {
            "id": str(s.scenario_id),
            "key": s.scenario.key,
            "version": s.scenario.version,
            "name": s.scenario.name,
        },
        "rubric": {"id": str(s.rubric_id), "key": s.rubric.key, "version": s.rubric.version},
        "assignment_id": str(s.assignment_id) if s.assignment_id else None,
        "seed": s.seed,
        "difficulty_level": s.difficulty_level,
        "selection": s.selection,
        "sim_time_ms": sim_time_ms,
        "duration_ms": s.duration_ms,
        "remaining_ms": max(0, s.duration_ms - sim_time_ms),
        "allow_pause": s.allow_pause,
        "pause_reason": s.pause_reason,
        "pause_count": s.pause_count,
        "completion_reason": s.completion_reason,
        "engine_version": s.engine_version,
        "timeline_digest": s.timeline_digest,
        "config_digest": s.config_digest,
        "created_at": _dt(s.created_at),
        "started_at": _dt(s.started_at),
        "completed_at": _dt(s.completed_at),
        "events_purged_at": _dt(s.events_purged_at),
        "result": result_summary(s.result),
    }


def feedback_level_for(s: TrainingSession) -> FeedbackLevel:
    if s.mode is SessionMode.SELF_GUIDED or s.assignment is None:
        return FeedbackLevel.DETAILED
    return s.assignment.feedback_level


def result_for_viewer(r: ScoreResult, *, trainee_view: bool, level: FeedbackLevel) -> dict[str, Any]:
    res = r.result
    if not trainee_view or level is FeedbackLevel.DETAILED:
        return {**res, "feedback_level": FeedbackLevel.DETAILED.value}
    dims = {k: {kk: vv for kk, vv in v.items() if kk != "items"} for k, v in res.get("dimensions", {}).items()}
    return {
        "status": res["status"],
        "overall": res["overall"],
        "passed": res["passed"],
        "pass_mark": res["pass_mark"],
        "scoring_engine_version": res["scoring_engine_version"],
        "rubric": res["rubric"],
        "explanation": res["explanation"],
        "dimensions": dims,
        "objectives": res["objectives"],
        "feedback": res["feedback"],
        "counts": res["counts"],
        "error_counts": {k: len(v) for k, v in res.get("errors", {}).items()},
        "feedback_level": FeedbackLevel.SUMMARY.value,
    }


def review_out(rv: InstructorReview) -> dict[str, Any]:
    return {
        "session_id": str(rv.session_id),
        "reviewer": user_ref(rv.reviewer),
        "status": rv.status.value,
        "notes": rv.notes,
        "strengths": rv.strengths,
        "improvements": rv.improvements,
        "focus_objectives": rv.focus_objectives,
        "shared_with_trainee": rv.shared_with_trainee,
        "updated_at": _dt(rv.updated_at),
    }


def page(items: list[Any], total: int, limit: int, offset: int) -> dict[str, Any]:
    return {"items": items, "total": total, "limit": limit, "offset": offset}
