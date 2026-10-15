"""Versioned scenario and rubric catalogue.

Definitions are immutable once stored. Saving changes always creates a new
version row; sessions reference the exact version (and an effective copy of the
definition) they were run with, so history never changes silently.
"""

from __future__ import annotations

import copy
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from drikr_api.errors import ApiError, conflict
from drikr_api.models import Rubric, Scenario, User
from drikr_contracts.scenario import Scenario as ScenarioContract
from drikr_scoring import Rubric as RubricContract
from drikr_simcore import validate_definition
from drikr_simcore.canonical import digest


def _issues_from_pydantic(exc: ValidationError) -> list[dict[str, Any]]:
    return [
        {"path": ".".join(str(p) for p in e["loc"]) or "$", "code": e["type"], "message": e["msg"], "severity": "error"}
        for e in exc.errors()
    ]


# --- rubrics -------------------------------------------------------------------


def validate_rubric(definition: dict[str, Any]) -> tuple[RubricContract | None, list[dict[str, Any]]]:
    try:
        return RubricContract.model_validate(definition), []
    except ValidationError as exc:
        return None, _issues_from_pydantic(exc)


def latest_rubric_version(db: Session, key: str) -> int:
    return db.scalar(select(func.max(Rubric.version)).where(Rubric.key == key)) or 0


def create_rubric(
    db: Session, definition: dict[str, Any], actor: User | None, *, new_key: bool, is_demo: bool = False
) -> Rubric:
    data = copy.deepcopy(definition)
    key = data.get("key")
    if not isinstance(key, str):
        raise ApiError(
            422,
            "rubric_invalid",
            "Rubric definition is invalid",
            [{"path": "key", "message": "key is required", "code": "missing", "severity": "error"}],
        )
    current = latest_rubric_version(db, key)
    if new_key and current:
        raise conflict("key_exists", f"Rubric key '{key}' already exists; save a new version instead")
    if not new_key and not current:
        raise ApiError(404, "not_found", f"Rubric key '{key}' not found")
    data["version"] = current + 1
    model, issues = validate_rubric(data)
    if model is None:
        raise ApiError(422, "rubric_invalid", "Rubric definition is invalid", issues)
    canonical = model.model_dump(mode="json")
    row = Rubric(
        key=model.key,
        version=model.version,
        name=model.name,
        definition=canonical,
        digest=digest(canonical),
        is_demo=is_demo,
        created_by_id=actor.id if actor else None,
    )
    db.add(row)
    db.flush()
    return row


def get_rubric_by_ref(db: Session, key: str, version: int) -> Rubric | None:
    return db.scalar(select(Rubric).where(Rubric.key == key, Rubric.version == version))


# --- scenarios -----------------------------------------------------------------


def latest_scenario_version(db: Session, key: str) -> int:
    return db.scalar(select(func.max(Scenario.version)).where(Scenario.key == key)) or 0


def validate_scenario(
    db: Session, definition: dict[str, Any], *, seed: int | None = None, difficulty_level: int | None = None
) -> dict[str, Any]:
    report = validate_definition(definition, seed=seed, difficulty_level=difficulty_level)
    out = report.as_dict()
    if report.scenario is not None:
        ref = report.scenario.scoring
        if get_rubric_by_ref(db, ref.rubric_key, ref.rubric_version) is None:
            out["issues"].append(
                {
                    "path": "scoring",
                    "code": "rubric_not_found",
                    "message": f"Rubric '{ref.rubric_key}' version {ref.rubric_version} does not exist",
                    "severity": "error",
                }
            )
            out["valid"] = False
    return out


def create_scenario(
    db: Session, definition: dict[str, Any], actor: User | None, *, new_key: bool, is_demo: bool = False
) -> Scenario:
    data = copy.deepcopy(definition)
    key = data.get("key")
    if not isinstance(key, str):
        raise ApiError(
            422,
            "scenario_invalid",
            "Scenario definition is invalid",
            [{"path": "key", "message": "key is required", "code": "missing", "severity": "error"}],
        )
    current = latest_scenario_version(db, key)
    if new_key and current:
        raise conflict("key_exists", f"Scenario key '{key}' already exists; save a new version instead")
    if not new_key and not current:
        raise ApiError(404, "not_found", f"Scenario key '{key}' not found")
    data["version"] = current + 1
    report = validate_scenario(db, data)
    if not report["valid"]:
        raise ApiError(422, "scenario_invalid", "Scenario failed validation", report["issues"])
    model = ScenarioContract.model_validate(data)
    canonical = model.model_dump(mode="json")
    rubric = get_rubric_by_ref(db, model.scoring.rubric_key, model.scoring.rubric_version)
    assert rubric is not None
    row = Scenario(
        key=model.key,
        version=model.version,
        name=model.name,
        definition=canonical,
        digest=digest(canonical),
        status="published",
        is_demo=is_demo,
        self_guided=model.self_guided,
        rubric_id=rubric.id,
        created_by_id=actor.id if actor else None,
    )
    db.add(row)
    db.flush()
    return row
