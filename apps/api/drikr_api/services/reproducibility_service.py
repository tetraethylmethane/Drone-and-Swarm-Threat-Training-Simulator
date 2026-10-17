"""Reproducibility report: verify recent completed sessions in bulk.

Each session is checked with the same procedure as the per-session `verify` endpoint
(regenerate the timeline from the stored configuration and seed, check the stored event log,
re-score). The report counts outcomes and lists every session that did not reproduce, with the
reason, so an administrator can follow it up.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from drikr_api.models import ScoreResult, SessionStatus, TrainingSession
from drikr_api.services import scoring_service


def _reason(r: dict[str, Any]) -> str:
    if r.get("events_purged_at") and not r.get("purge_recorded"):
        return "purge_unrecorded"
    if not r["timeline_reproduced"]:
        return "timeline_differs"
    if r.get("stored_log_intact") is False:
        return "stored_log_changed"
    if r.get("score_checked") and not r.get("score_reproduced") and not r.get("assessment_values_match"):
        return "score_differs"
    return "other"


def report(db: Session, limit: int = 100) -> dict[str, Any]:
    started = time.perf_counter()
    sessions = db.scalars(
        select(TrainingSession)
        .join(ScoreResult, ScoreResult.session_id == TrainingSession.id)
        .where(TrainingSession.status == SessionStatus.COMPLETED)
        .order_by(TrainingSession.completed_at.desc())
        .limit(limit)
    ).all()
    counts = {
        "checked": 0,
        "reproducible": 0,
        "not_reproducible": 0,
        "exact_score_match": 0,
        "same_assessment_older_engine": 0,
        "event_log_purged": 0,
    }
    engines: dict[str, int] = {}
    failures: list[dict[str, Any]] = []
    for s in sessions:
        r = scoring_service.verify(db, s)
        counts["checked"] += 1
        engines[r.get("scoring_engine_version_recorded") or "unknown"] = (
            engines.get(r.get("scoring_engine_version_recorded") or "unknown", 0) + 1
        )
        if r.get("events_purged_at"):
            counts["event_log_purged"] += 1
        if r.get("score_reproduced"):
            counts["exact_score_match"] += 1
        elif r.get("assessment_values_match"):
            counts["same_assessment_older_engine"] += 1
        if r["reproducible"]:
            counts["reproducible"] += 1
        else:
            counts["not_reproducible"] += 1
            failures.append(
                {
                    "session_id": str(s.id),
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                    "reason": _reason(r),
                    "note": r.get("score_note"),
                }
            )
    return {
        "limit": limit,
        "counts": counts,
        "scoring_engine_versions": engines,
        "failures": failures,
        "duration_s": round(time.perf_counter() - started, 2),
        "method": "Each session: regenerate the timeline from its stored scenario version, seed and difficulty; "
        "compare with the stored log; re-score the stored log. Results from an older scoring engine count as "
        "reproducible when re-scoring gives the same scores, outcomes and error counts.",
    }
