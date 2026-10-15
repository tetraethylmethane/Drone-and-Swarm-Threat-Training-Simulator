"""Liveness and readiness probes (unauthenticated, no sensitive detail)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from drikr_api import __version__
from drikr_api.deps import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "version": __version__}


@router.get("/health/ready", response_model=None)
def ready(db: Session = Depends(get_db)) -> dict[str, Any] | JSONResponse:
    try:
        db.execute(text("SELECT 1"))
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "unreachable"})
    if revision is None:
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "not_migrated"})
    return {"status": "ready", "database": "ok", "schema_revision": revision}
