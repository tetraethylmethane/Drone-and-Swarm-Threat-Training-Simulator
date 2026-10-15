"""Administration: audit log, application settings and system health."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from drikr_api import __version__
from drikr_api.audit import append_audit, verify_chain
from drikr_api.deps import Principal, get_db, require
from drikr_api.errors import ApiError
from drikr_api.models import AuditEvent, RetentionRun, Scenario, SessionEvent, TrainingSession, User
from drikr_api.schemas import RetentionRunBody, SettingsBody
from drikr_api.security.rbac import Permission
from drikr_api.serializers import page
from drikr_api.services import retention_service, settings_service
from drikr_contracts import CONTRACTS_VERSION
from drikr_scoring import SCORING_ENGINE_VERSION
from drikr_simcore import ENGINE_VERSION

router = APIRouter(tags=["admin"])


@router.get("/audit")
def list_audit(
    action: str | None = Query(default=None, max_length=64),
    actor: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: Principal = Depends(require(Permission.AUDIT_READ)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    stmt = select(AuditEvent)
    if action:
        stmt = stmt.where(AuditEvent.action.like(f"{action}%"))
    if actor:
        stmt = stmt.where(AuditEvent.actor_username == actor)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(AuditEvent.id.desc()).limit(limit).offset(offset)).all()
    items = [
        {
            "id": e.id,
            "occurred_at": e.occurred_at.isoformat(),
            "actor_username": e.actor_username,
            "action": e.action,
            "target_type": e.target_type,
            "target_id": e.target_id,
            "details": e.details,
            "ip_address": e.ip_address,
            "hash": e.hash,
            "prev_hash": e.prev_hash,
        }
        for e in rows
    ]
    return page(items, total, limit, offset)


@router.get("/audit/verify")
def verify_audit(
    _: Principal = Depends(require(Permission.AUDIT_READ)), db: Session = Depends(get_db)
) -> dict[str, Any]:
    return verify_chain(db)


@router.get("/admin/settings")
def get_settings(
    _: Principal = Depends(require(Permission.SETTINGS_MANAGE)), db: Session = Depends(get_db)
) -> dict[str, Any]:
    return settings_service.get_all(db)


@router.put("/admin/settings")
def put_settings(
    body: SettingsBody,
    principal: Principal = Depends(require(Permission.SETTINGS_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    before = settings_service.get_all(db)
    after = {
        "adaptive_policy": body.adaptive_policy.model_dump(),
        "self_guided_enabled": body.self_guided_enabled,
        "mfa_required_roles": body.mfa_required_roles,
        "retention_policy": body.retention_policy.model_dump(),
    }
    if "administrator" in body.mfa_required_roles and not principal.user.mfa_enabled:
        raise ApiError(
            409,
            "mfa_enable_first",
            "Enable multi-factor authentication on your own account before requiring it for administrators",
        )
    for k, v in after.items():
        settings_service.put(db, k, v, principal.user)
    append_audit(
        db,
        actor=principal.user,
        action="settings.updated",
        details={"before": before, "after": after},
        ip_address=principal.ip,
    )
    db.commit()
    return settings_service.get_all(db)


@router.get("/admin/retention/preview")
def retention_preview(
    _: Principal = Depends(require(Permission.SETTINGS_MANAGE)), db: Session = Depends(get_db)
) -> dict[str, Any]:
    return retention_service.preview(db)


@router.post("/admin/retention/run")
def retention_run(
    body: RetentionRunBody,
    principal: Principal = Depends(require(Permission.SETTINGS_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    record = retention_service.run(db, principal.user, dry_run=body.dry_run, trigger="admin", ip=principal.ip)
    db.commit()
    return retention_service.run_out(record)


@router.get("/admin/retention/runs")
def retention_runs(
    _: Principal = Depends(require(Permission.SETTINGS_MANAGE)), db: Session = Depends(get_db)
) -> dict[str, Any]:
    rows = db.scalars(select(RetentionRun).order_by(RetentionRun.started_at.desc()).limit(50)).all()
    return {"items": [retention_service.run_out(r) for r in rows]}


@router.get("/admin/system")
def system(_: Principal = Depends(require(Permission.SYSTEM_HEALTH)), db: Session = Depends(get_db)) -> dict[str, Any]:
    t0 = time.perf_counter()
    db.execute(text("SELECT 1"))
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    size = db.execute(text("SELECT pg_database_size(current_database())")).scalar()
    pg_version = db.execute(text("SHOW server_version")).scalar()
    return {
        "versions": {
            "api": __version__,
            "contracts": CONTRACTS_VERSION,
            "simulation_engine": ENGINE_VERSION,
            "scoring_engine": SCORING_ENGINE_VERSION,
            "schema_revision": revision,
            "postgresql": pg_version,
        },
        "database": {"status": "ok", "latency_ms": latency_ms, "size_bytes": size},
        "counts": {
            "users": db.scalar(select(func.count()).select_from(User)) or 0,
            "scenarios": db.scalar(select(func.count()).select_from(Scenario)) or 0,
            "sessions": db.scalar(select(func.count()).select_from(TrainingSession)) or 0,
            "session_events": db.scalar(select(func.count()).select_from(SessionEvent)) or 0,
            "audit_events": db.scalar(select(func.count()).select_from(AuditEvent)) or 0,
        },
        "audit_chain": verify_chain(db),
        "simulation": {
            "engine": "drikr_simcore (deterministic Python logical simulation, server-authoritative)",
            "visual_clients": "Unity 6 Windows client and browser adapter (React Three Fiber), both presentation-only",
        },
        "network": {"external_runtime_dependencies": [], "telemetry": "none"},
    }
