"""Scenario and rubric catalogue: validate, create, version, archive, preview and generate."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from drikr_api import cpu
from drikr_api.audit import append_audit
from drikr_api.deps import Principal, get_db, require
from drikr_api.errors import ApiError, not_found
from drikr_api.models import Role, Rubric, Scenario
from drikr_api.schemas import DefinitionBody, ScenarioGenerateBody, ScenarioValidateBody
from drikr_api.security.rbac import Permission
from drikr_api.serializers import briefing, rubric_out, scenario_out, scenario_summary
from drikr_api.services import catalog_service
from drikr_contracts.scenario import Scenario as ScenarioContract
from drikr_simcore import DIFFICULTY_TABLE, GroundTruthIndex, generate_timeline
from drikr_simcore.presets import ENVIRONMENT_PRESETS
from drikr_simcore.procedural import ProceduralGenerationError, generate_scenario_definition

router = APIRouter(tags=["catalog"])

READ = Depends(require(Permission.SCENARIOS_READ))
WRITE = Depends(require(Permission.SCENARIOS_WRITE))


# --- rubrics -------------------------------------------------------------------


@router.get("/rubrics")
def list_rubrics(
    all_versions: bool = False,
    _: Principal = Depends(require(Permission.RUBRICS_READ)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = list(db.scalars(select(Rubric).order_by(Rubric.key, Rubric.version.desc())).all())
    if not all_versions:
        latest: dict[str, Rubric] = {}
        for r in rows:
            latest.setdefault(r.key, r)
        rows = list(latest.values())
    return {"items": [rubric_out(r) for r in rows]}


@router.get("/rubrics/{rubric_id}")
def get_rubric(
    rubric_id: uuid.UUID,
    _: Principal = Depends(require(Permission.RUBRICS_READ)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    r = db.get(Rubric, rubric_id)
    if r is None:
        raise not_found("Rubric")
    versions = db.scalars(select(Rubric).where(Rubric.key == r.key).order_by(Rubric.version)).all()
    return {
        **rubric_out(r, full=True),
        "versions": [{"id": str(v.id), "version": v.version, "created_at": v.created_at.isoformat()} for v in versions],
    }


@router.post("/rubrics/validate")
def validate_rubric(
    body: DefinitionBody,
    _: Principal = Depends(require(Permission.RUBRICS_WRITE)),
) -> dict[str, Any]:
    model, issues = catalog_service.validate_rubric(body.definition)
    return {"valid": model is not None, "issues": issues}


@router.post("/rubrics", status_code=201)
def create_rubric(
    body: DefinitionBody,
    principal: Principal = Depends(require(Permission.RUBRICS_WRITE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = catalog_service.create_rubric(db, body.definition, principal.user, new_key=True)
    append_audit(
        db,
        actor=principal.user,
        action="rubric.created",
        target_type="rubric",
        target_id=row.id,
        details={"key": row.key, "version": row.version, "digest": row.digest},
        ip_address=principal.ip,
    )
    db.commit()
    return rubric_out(row, full=True)


@router.post("/rubrics/key/{key}/versions", status_code=201)
def create_rubric_version(
    key: str,
    body: DefinitionBody,
    principal: Principal = Depends(require(Permission.RUBRICS_WRITE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if body.definition.get("key") != key:
        raise ApiError(422, "key_mismatch", "Definition key must match the URL key")
    row = catalog_service.create_rubric(db, body.definition, principal.user, new_key=False)
    append_audit(
        db,
        actor=principal.user,
        action="rubric.versioned",
        target_type="rubric",
        target_id=row.id,
        details={"key": row.key, "version": row.version, "digest": row.digest},
        ip_address=principal.ip,
    )
    db.commit()
    return rubric_out(row, full=True)


# --- scenarios -----------------------------------------------------------------


@router.get("/scenarios/presets")
def presets(_: Principal = READ) -> dict[str, Any]:
    return {
        "environment_presets": [{"id": k, **v} for k, v in ENVIRONMENT_PRESETS.items()],
        "difficulty_levels": [m.as_dict() for m in DIFFICULTY_TABLE.values()],
    }


@router.get("/scenarios")
def list_scenarios(
    include_archived: bool = False,
    self_guided: bool | None = None,
    q: str | None = Query(default=None, max_length=64),
    principal: Principal = READ,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    latest = (
        select(Scenario.key, func.max(Scenario.version).label("v"), func.count().label("n"))
        .group_by(Scenario.key)
        .subquery()
    )
    stmt = select(Scenario, latest.c.n).join(latest, (Scenario.key == latest.c.key) & (Scenario.version == latest.c.v))
    if principal.role is Role.TRAINEE:
        # Trainees only browse the self-guided practice library.
        stmt = stmt.where(Scenario.self_guided.is_(True), Scenario.status == "published")
    else:
        if not include_archived:
            stmt = stmt.where(Scenario.status == "published")
        if self_guided is not None:
            stmt = stmt.where(Scenario.self_guided.is_(self_guided))
    if q:
        stmt = stmt.where(func.lower(Scenario.name).like(f"%{q.lower()}%"))
    rows = db.execute(stmt.order_by(Scenario.name)).all()
    if principal.role is Role.TRAINEE:
        return {"items": [{**scenario_summary(s), "briefing": briefing(s.definition)} for s, _ in rows]}
    return {"items": [scenario_summary(s, n) for s, n in rows]}


def _scenario(db: Session, scenario_id: uuid.UUID) -> Scenario:
    s = db.get(Scenario, scenario_id)
    if s is None:
        raise not_found("Scenario")
    return s


@router.get("/scenarios/{scenario_id}")
def get_scenario(
    scenario_id: uuid.UUID,
    principal: Principal = READ,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    s = _scenario(db, scenario_id)
    if principal.role is Role.TRAINEE:
        if not (s.self_guided and s.status == "published"):
            raise not_found("Scenario")
        return {**scenario_summary(s), "briefing": briefing(s.definition)}
    versions = db.scalars(select(Scenario).where(Scenario.key == s.key).order_by(Scenario.version)).all()
    return {
        **scenario_out(s),
        "versions": [
            {"id": str(v.id), "version": v.version, "status": v.status, "created_at": v.created_at.isoformat()}
            for v in versions
        ],
    }


@router.get("/scenarios/{scenario_id}/preview")
def preview(
    scenario_id: uuid.UUID,
    seed: int | None = Query(default=None, ge=0, le=2**53 - 1),
    difficulty_level: int | None = Query(default=None, ge=1, le=5),
    _: Principal = WRITE,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Instructor planning view: expanded entities and timeline statistics (contains ground truth)."""
    s = _scenario(db, scenario_id)
    scn = ScenarioContract.model_validate(s.definition)
    tl = cpu.run(generate_timeline, scn, seed=seed, difficulty_level=difficulty_level)
    idx = GroundTruthIndex(tl.events)
    entities = [
        {
            "entity_id": e.entity_id,
            "group_id": e.group_id,
            "entity_class": e.entity_class,
            "behavior": e.behavior,
            "cooperative": e.cooperative,
            "spawn_s": e.spawn_ms / 1000,
            "exit_s": e.exit_ms / 1000 if e.exit_ms is not None else None,
            "closest_range_m": e.closest_range_m,
            "track_id": idx.track_by_entity.get(e.entity_id),
        }
        for e in idx.entities.values()
    ]
    return {"summary": tl.summary(), "entities": entities}


@router.post("/scenarios/validate")
def validate_scenario(
    body: ScenarioValidateBody,
    _: Principal = WRITE,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return catalog_service.validate_scenario(
        db, body.definition, seed=body.seed, difficulty_level=body.difficulty_level
    )


@router.post("/scenarios/generate")
def generate(
    body: ScenarioGenerateBody,
    _: Principal = WRITE,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rubric = (
        db.get(Rubric, body.rubric_id)
        if body.rubric_id
        else db.scalar(select(Rubric).order_by(Rubric.created_at).limit(1))
    )
    if rubric is None:
        raise ApiError(422, "rubric_required", "Create a rubric before generating scenarios")
    try:
        definition = generate_scenario_definition(
            body.seed,
            preset=body.preset,
            include_swarm=body.include_swarm,
            duration_s=body.duration_s,
            difficulty_level=body.difficulty_level,
            rubric_key=rubric.key,
            rubric_version=rubric.version,
        )
    except ProceduralGenerationError as exc:
        raise ApiError(422, "generation_failed", str(exc)) from exc
    return {"definition": definition, "saved": False}


@router.post("/scenarios", status_code=201)
def create_scenario(
    body: DefinitionBody,
    principal: Principal = WRITE,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = catalog_service.create_scenario(db, body.definition, principal.user, new_key=True)
    append_audit(
        db,
        actor=principal.user,
        action="scenario.created",
        target_type="scenario",
        target_id=row.id,
        details={"key": row.key, "version": row.version, "digest": row.digest},
        ip_address=principal.ip,
    )
    db.commit()
    return scenario_out(row)


@router.post("/scenarios/key/{key}/versions", status_code=201)
def create_scenario_version(
    key: str,
    body: DefinitionBody,
    principal: Principal = WRITE,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if body.definition.get("key") != key:
        raise ApiError(422, "key_mismatch", "Definition key must match the URL key")
    row = catalog_service.create_scenario(db, body.definition, principal.user, new_key=False)
    append_audit(
        db,
        actor=principal.user,
        action="scenario.versioned",
        target_type="scenario",
        target_id=row.id,
        details={"key": row.key, "version": row.version, "digest": row.digest},
        ip_address=principal.ip,
    )
    db.commit()
    return scenario_out(row)


@router.post("/scenarios/{scenario_id}/archive")
def archive(
    scenario_id: uuid.UUID,
    principal: Principal = WRITE,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    s = _scenario(db, scenario_id)
    if s.status != "archived":
        s.status = "archived"
        append_audit(
            db,
            actor=principal.user,
            action="scenario.archived",
            target_type="scenario",
            target_id=s.id,
            details={"key": s.key, "version": s.version},
            ip_address=principal.ip,
        )
        db.commit()
    return scenario_summary(s)


@router.post("/scenarios/{scenario_id}/restore")
def restore(
    scenario_id: uuid.UUID,
    principal: Principal = WRITE,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    s = _scenario(db, scenario_id)
    if s.status != "published":
        s.status = "published"
        append_audit(
            db,
            actor=principal.user,
            action="scenario.restored",
            target_type="scenario",
            target_id=s.id,
            details={"key": s.key, "version": s.version},
            ip_address=principal.ip,
        )
        db.commit()
    return scenario_summary(s)
