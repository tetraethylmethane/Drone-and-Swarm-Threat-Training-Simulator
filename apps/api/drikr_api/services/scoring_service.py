"""Scoring orchestration and reproducibility verification."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from drikr_api.models import ScoreResult, SessionEvent, TrainingSession
from drikr_contracts.scenario import Scenario as ScenarioContract
from drikr_scoring import SCORING_ENGINE_VERSION, score_session
from drikr_scoring import Rubric as RubricContract
from drikr_simcore import generate_timeline
from drikr_simcore.canonical import digest


def _events(db: Session, s: TrainingSession) -> list[dict[str, Any]]:
    rows = db.scalars(select(SessionEvent).where(SessionEvent.session_id == s.id).order_by(SessionEvent.seq)).all()
    return [r.as_event() for r in rows]


def compute(db: Session, s: TrainingSession, end_ms: int) -> dict[str, Any]:
    scenario = ScenarioContract.model_validate(s.effective_definition)
    rubric = RubricContract.model_validate(s.rubric.definition)
    return score_session(_events(db, s), scenario, rubric, end_ms)


def score_and_store(db: Session, s: TrainingSession, end_ms: int) -> ScoreResult:
    existing = db.scalar(select(ScoreResult).where(ScoreResult.session_id == s.id))
    if existing is not None:
        return existing
    result = compute(db, s, end_ms)
    row = ScoreResult(
        session_id=s.id,
        rubric_id=s.rubric_id,
        rubric_version=s.rubric.version,
        scoring_engine_version=result["scoring_engine_version"],
        input_digest=result["input_digest"],
        result_digest=digest(result),
        status=result["status"],
        overall=result["overall"],
        passed=result["passed"],
        result=result,
    )
    db.add(row)
    db.flush()
    return row


def verify(db: Session, s: TrainingSession) -> dict[str, Any]:
    """Re-derive the timeline and the score from stored inputs and compare digests."""
    scenario = ScenarioContract.model_validate(s.effective_definition)
    regenerated = generate_timeline(scenario, seed=s.seed, difficulty_level=s.difficulty_level)
    stored = _events(db, s)
    stored_generated = [e for e in stored if e["seq"] < s.generated_event_count]
    report: dict[str, Any] = {
        "session_id": str(s.id),
        "engine_version_recorded": s.engine_version,
        "engine_version_current": regenerated.engine_version,
        "timeline_digest_recorded": s.timeline_digest,
        "timeline_digest_regenerated": regenerated.digest,
        "timeline_reproduced": regenerated.digest == s.timeline_digest,
        "stored_log_digest": digest(stored_generated),
        "stored_log_intact": digest(stored_generated) == s.timeline_digest,
        "score_checked": False,
        "events_purged_at": s.events_purged_at.isoformat() if s.events_purged_at else None,
    }
    if s.events_purged_at is not None:
        # The raw log was removed under the retention policy: the timeline can still be regenerated
        # from the stored configuration and seed, but the stored log can no longer be re-scored.
        report.update(
            stored_log_digest=None,
            stored_log_intact=None,
            score_note=(
                "The event log was deleted under the data-retention policy; the stored score is retained unchanged."
            ),
            reproducible=report["timeline_reproduced"],
        )
        return report
    result = db.scalar(select(ScoreResult).where(ScoreResult.session_id == s.id))
    if result is not None:
        report["scoring_engine_version_recorded"] = result.scoring_engine_version
        report["scoring_engine_version_current"] = SCORING_ENGINE_VERSION
        recomputed = score_session(
            stored, scenario, RubricContract.model_validate(s.rubric.definition), int(result.result["end_ms"])
        )
        report.update(
            score_checked=True,
            score_digest_recorded=result.result_digest,
            score_digest_recomputed=digest(recomputed),
            score_reproduced=digest(recomputed) == result.result_digest,
            input_digest_matches=recomputed["input_digest"] == result.input_digest,
        )
    if report.get("score_checked") and result is not None and result.scoring_engine_version != SCORING_ENGINE_VERSION:
        # A different engine version is expected to produce different output; the stored
        # result remains authoritative for that session and is never rewritten.
        report["score_note"] = (
            f"Scored with {result.scoring_engine_version}; the running engine is {SCORING_ENGINE_VERSION}. "
            "The stored result is retained unchanged."
        )
    report["reproducible"] = bool(
        report["timeline_reproduced"]
        and report["stored_log_intact"]
        and (not report["score_checked"] or report.get("score_reproduced"))
    )
    return report
