"""Report exports (CSV and PDF). Every export is audited."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from drikr_api.audit import append_audit
from drikr_api.deps import AppContext, Principal, get_ctx, get_db, require
from drikr_api.errors import ApiError, not_found
from drikr_api.models import InstructorReview, Role, Scenario, ScoreResult, SessionStatus, TrainingSession
from drikr_api.routers.sessions import filtered_sessions
from drikr_api.security.rbac import Permission
from drikr_api.security.tokens import token_digest
from drikr_api.services import report_service

router = APIRouter(prefix="/reports", tags=["reports"])

MAX_CSV_ROWS = 10_000


@router.get("/sessions.csv")
def sessions_csv(
    trainee_id: uuid.UUID | None = None,
    scenario_key: str | None = Query(default=None, max_length=64),
    status: SessionStatus | None = None,
    assignment_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    principal: Principal = Depends(require(Permission.REPORTS_EXPORT)),
    db: Session = Depends(get_db),
) -> Response:
    stmt = filtered_sessions(principal, trainee_id, scenario_key, status, assignment_id, date_from, date_to)
    sessions = db.scalars(stmt.order_by(TrainingSession.created_at).limit(MAX_CSV_ROWS)).all()
    ids = [s.id for s in sessions]
    results = {r.session_id: r for r in db.scalars(select(ScoreResult).where(ScoreResult.session_id.in_(ids))).all()}
    reviews = {
        r.session_id: r for r in db.scalars(select(InstructorReview).where(InstructorReview.session_id.in_(ids))).all()
    }
    body = report_service.sessions_csv([(s, results.get(s.id), reviews.get(s.id)) for s in sessions])
    filters = {
        k: str(v)
        for k, v in {
            "trainee_id": trainee_id,
            "scenario_key": scenario_key,
            "status": status,
            "assignment_id": assignment_id,
            "date_from": date_from,
            "date_to": date_to,
        }.items()
        if v is not None
    }
    append_audit(
        db,
        actor=principal.user,
        action="report.exported",
        details={"format": "csv", "rows": len(sessions), "filters": filters},
        ip_address=principal.ip,
    )
    db.commit()
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="drikr-sessions.csv"', "Cache-Control": "no-store"},
    )


@router.get("/sessions/{session_id}.pdf")
def session_pdf(
    session_id: uuid.UUID,
    principal: Principal = Depends(require(Permission.REPORTS_EXPORT, Permission.REPORTS_EXPORT_OWN)),
    db: Session = Depends(get_db),
) -> Response:
    s = db.get(TrainingSession, session_id)
    if s is None:
        raise not_found("Session")
    trainee = principal.role is Role.TRAINEE
    if trainee and s.trainee_id != principal.user.id:
        raise not_found("Session")
    if s.status is not SessionStatus.COMPLETED:
        raise ApiError(409, "not_completed", "Reports are available for completed sessions")
    r = db.scalar(select(ScoreResult).where(ScoreResult.session_id == s.id))
    rv = db.scalar(select(InstructorReview).where(InstructorReview.session_id == s.id))
    if trainee:
        level = s.assignment.feedback_level.value if s.assignment else "detailed"
        if level != "detailed":
            raise ApiError(403, "detailed_feedback_required", "Detailed reports are not enabled for this exercise")
        if rv is not None and not rv.shared_with_trainee:
            rv = None
    # Private instructor notes are never included in a trainee's copy.
    pdf = report_service.session_pdf(s, r, rv, principal.user.display_name, include_notes=not trainee)
    append_audit(
        db,
        actor=principal.user,
        action="report.exported",
        target_type="session",
        target_id=s.id,
        details={"format": "pdf"},
        ip_address=principal.ip,
    )
    db.commit()
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="drikr-aar-{s.id}.pdf"', "Cache-Control": "no-store"},
    )


STUDY_DIMENSIONS = ("recognition", "timing", "consistency", "uncertainty", "objectives", "procedure")


@router.get("/study.csv")
def study_csv(
    scenario_key: str | None = Query(default=None, max_length=64),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    principal: Principal = Depends(require(Permission.REPORTS_EXPORT)),
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
) -> Response:
    """Pseudonymised dataset for training-effectiveness analysis (one row per scored session).

    Participants appear only as stable codes (keyed HMAC of the account id); names, usernames,
    notes and timestamps finer than a day are excluded.
    """
    stmt = (
        select(TrainingSession, ScoreResult, Scenario)
        .join(ScoreResult, ScoreResult.session_id == TrainingSession.id)
        .join(Scenario, Scenario.id == TrainingSession.scenario_id)
        .where(TrainingSession.status == SessionStatus.COMPLETED, ScoreResult.status == "scored")
        .order_by(TrainingSession.completed_at)
    )
    if scenario_key:
        stmt = stmt.where(Scenario.key == scenario_key)
    if date_from:
        stmt = stmt.where(TrainingSession.completed_at >= date_from)
    if date_to:
        stmt = stmt.where(TrainingSession.completed_at <= date_to)
    secret = ctx.settings.secret_key.get_secret_value()
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(
        [
            "participant",
            "scenario_key",
            "scenario_version",
            "mode",
            "attempt",
            "difficulty_level",
            "seed",
            "completed_date",
            "sim_duration_s",
            "overall",
            "passed",
            *[f"{d}_score" for d in STUDY_DIMENSIONS],
            "objectives_met",
            "objectives_assessable",
            "observable_tracks",
            "classified_tracks",
            "rubric_version",
            "scoring_engine",
        ]
    )
    rows = db.execute(stmt.limit(MAX_CSV_ROWS)).all()
    for s, r, scn in rows:
        res = r.result
        dims = res.get("dimensions", {})
        objectives = res.get("objectives", [])
        w.writerow(
            [
                "P-" + token_digest(secret, f"study|{s.trainee_id}")[:10],
                scn.key,
                scn.version,
                s.mode.value,
                s.attempt_number,
                s.difficulty_level,
                s.seed,
                s.completed_at.date().isoformat() if s.completed_at else "",
                round(s.sim_elapsed_ms / 1000, 1),
                r.overall,
                int(bool(r.passed)),
                *["" if dims.get(d, {}).get("score") is None else dims[d]["score"] for d in STUDY_DIMENSIONS],
                sum(1 for o in objectives if o["status"] == "met"),
                sum(1 for o in objectives if o["status"] != "not_assessable"),
                res.get("counts", {}).get("observable_tracks", ""),
                res.get("counts", {}).get("classified_tracks", ""),
                r.rubric_version,
                r.scoring_engine_version,
            ]
        )
    append_audit(
        db,
        actor=principal.user,
        action="report.exported",
        details={"format": "study_csv", "rows": len(rows)},
        ip_address=principal.ip,
    )
    db.commit()
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="drikr-study-export.csv"', "Cache-Control": "no-store"},
    )
