"""Administrator-managed application settings stored in the database."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from drikr_api.models import AppSetting, User
from drikr_scoring.adaptive import AdaptivePolicy


class RetentionPolicy(BaseModel):
    """Data-retention periods. ``None`` disables that rule. Audit events are never deleted."""

    model_config = ConfigDict(extra="forbid")

    #: Delete raw event logs of completed or aborted sessions this many days after completion.
    #: Scores, digests and AAR summaries are kept.
    session_event_days: int | None = Field(default=None, ge=30, le=3650)
    #: Delete expired or revoked sign-in sessions and MFA challenges after this many days.
    auth_record_days: int = Field(default=30, ge=1, le=365)
    #: Anonymise accounts that have been deactivated for this many days.
    anonymise_deactivated_after_days: int | None = Field(default=None, ge=30, le=3650)


MfaRole = Literal["administrator", "instructor", "trainee"]

DEFAULTS: dict[str, Any] = {
    "adaptive_policy": AdaptivePolicy().model_dump(),
    "self_guided_enabled": True,
    # Administrators must use MFA by default; instructors and trainees are opt-in.
    "mfa_required_roles": ["administrator"],
    "retention_policy": RetentionPolicy().model_dump(),
}


def get_all(db: Session) -> dict[str, Any]:
    out = dict(DEFAULTS)
    for row in db.query(AppSetting).all():
        if row.key in DEFAULTS:
            out[row.key] = row.value
    return out


def adaptive_policy(db: Session) -> AdaptivePolicy:
    return AdaptivePolicy.model_validate(get_all(db)["adaptive_policy"])


def retention_policy(db: Session) -> RetentionPolicy:
    return RetentionPolicy.model_validate(get_all(db)["retention_policy"])


def self_guided_enabled(db: Session) -> bool:
    return bool(get_all(db)["self_guided_enabled"])


def put(db: Session, key: str, value: Any, actor: User) -> None:
    if key not in DEFAULTS:
        raise KeyError(key)
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value, updated_by_id=actor.id))
    else:
        row.value = value
        row.updated_by_id = actor.id
