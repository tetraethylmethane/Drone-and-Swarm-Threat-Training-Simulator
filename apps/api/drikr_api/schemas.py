"""Request schemas: the validated trust boundary for every API call.

Unknown fields are rejected. Response bodies are produced by ``serializers``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from drikr_api.models import DifficultyMode, FeedbackLevel, ReviewStatus, Role
from drikr_api.services.settings_service import MfaRole, RetentionPolicy
from drikr_contracts.scenario import TraineeOptions, TraineeSelection
from drikr_scoring.adaptive import AdaptivePolicy

USERNAME_PATTERN = r"^[a-z0-9][a-z0-9._-]{2,63}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --- auth ----------------------------------------------------------------------


class LoginRequest(Strict):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    mode: Literal["cookie", "token"] = "cookie"


class ChangePasswordRequest(Strict):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


# --- users ---------------------------------------------------------------------


class UserCreate(Strict):
    username: str = Field(pattern=USERNAME_PATTERN)
    display_name: str = Field(min_length=2, max_length=120)
    role: Role
    password: str = Field(min_length=1, max_length=256)
    unit: str | None = Field(default=None, max_length=80)

    @field_validator("unit")
    @classmethod
    def _unit(cls, v: str | None) -> str | None:
        return clean_unit(v)


class UserUpdate(Strict):
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    role: Role | None = None
    is_active: bool | None = None
    #: Send "" or null to clear; omit to leave unchanged.
    unit: str | None = Field(default=None, max_length=80)

    @field_validator("unit")
    @classmethod
    def _unit(cls, v: str | None) -> str | None:
        return clean_unit(v)


def clean_unit(v: str | None) -> str | None:
    """Units are free text; surrounding spaces are removed and an empty value means none."""
    if v is None:
        return None
    v = " ".join(v.split())
    return v or None


class PasswordReset(Strict):
    new_password: str = Field(min_length=1, max_length=256)


# --- scenarios and rubrics -------------------------------------------------------


class DefinitionBody(Strict):
    definition: dict[str, Any]


class ScenarioValidateBody(Strict):
    definition: dict[str, Any]
    seed: int | None = Field(default=None, ge=0, le=2**53 - 1)
    difficulty_level: int | None = Field(default=None, ge=1, le=5)


class ScenarioGenerateBody(Strict):
    seed: int = Field(ge=0, le=2**53 - 1)
    preset: str | None = Field(default=None, max_length=64)
    include_swarm: bool | None = None
    duration_s: int = Field(default=300, ge=120, le=1800)
    difficulty_level: int = Field(default=3, ge=1, le=5)
    rubric_id: uuid.UUID | None = None


# --- assignments ---------------------------------------------------------------


class AssignmentCreate(Strict):
    scenario_id: uuid.UUID
    trainee_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    title: str = Field(min_length=3, max_length=160)
    instructions: str = Field(default="", max_length=4000)
    trainee_options: TraineeOptions = Field(default_factory=TraineeOptions)
    difficulty_mode: DifficultyMode = DifficultyMode.FIXED
    difficulty_level: int = Field(ge=1, le=5)
    min_level: int = Field(ge=1, le=5, default=1)
    max_level: int = Field(ge=1, le=5, default=5)
    max_attempts: int = Field(ge=1, le=50, default=3)
    feedback_level: FeedbackLevel = FeedbackLevel.DETAILED
    due_at: datetime | None = None

    @model_validator(mode="after")
    def _levels(self) -> Self:
        if not (self.min_level <= self.difficulty_level <= self.max_level):
            raise ValueError("difficulty_level must lie within min_level..max_level")
        if len(set(self.trainee_ids)) != len(self.trainee_ids):
            raise ValueError("trainee_ids must be unique")
        return self


# --- sessions ------------------------------------------------------------------


class SessionCreate(Strict):
    assignment_id: uuid.UUID | None = None
    scenario_id: uuid.UUID | None = None
    selection: TraineeSelection = Field(default_factory=TraineeSelection)

    @model_validator(mode="after")
    def _one_source(self) -> Self:
        if (self.assignment_id is None) == (self.scenario_id is None):
            raise ValueError("provide exactly one of assignment_id (assigned) or scenario_id (self-guided)")
        return self


class AbortBody(Strict):
    reason: str = Field(min_length=3, max_length=280)


class ReviewBody(Strict):
    status: ReviewStatus
    notes: str = Field(default="", max_length=8000)
    strengths: str = Field(default="", max_length=4000)
    improvements: str = Field(default="", max_length=4000)
    focus_objectives: list[str] = Field(default_factory=list, max_length=20)
    shared_with_trainee: bool = False


# --- admin ---------------------------------------------------------------------


class SettingsBody(Strict):
    adaptive_policy: AdaptivePolicy
    self_guided_enabled: bool = True
    mfa_required_roles: list[MfaRole] = ["administrator"]  # pydantic copies mutable defaults
    retention_policy: RetentionPolicy = Field(default_factory=RetentionPolicy)

    @model_validator(mode="after")
    def _unique_roles(self) -> Self:
        self.mfa_required_roles = sorted(set(self.mfa_required_roles))
        return self


class MfaCode(Strict):
    code: str = Field(min_length=6, max_length=16)


class MfaVerify(Strict):
    mfa_token: str = Field(min_length=10, max_length=128)
    code: str = Field(min_length=6, max_length=16)


class MfaSetup(Strict):
    current_password: str = Field(min_length=1, max_length=256)


class MfaDisable(Strict):
    current_password: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=6, max_length=16)


class AnonymiseBody(Strict):
    confirm_username: str = Field(min_length=3, max_length=64)


class RetentionRunBody(Strict):
    dry_run: bool = True
