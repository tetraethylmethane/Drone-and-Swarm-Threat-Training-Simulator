"""Persistent data model. See docs/architecture/data-model.md for the full description.

Integrity rules enforced in the database (not only in application code):

* Scenario and rubric versions are unique per key and immutable once written.
* Session events are unique per (session, seq) and (session, event_id); trainee
  actions are unique per (session, client_action_id) for idempotent retries.
* Each session has at most one authoritative score result.
* Audit events are append-only (trigger installed by migration 0001).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from drikr_api.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def _enum(cls: type[StrEnum], name: str) -> SAEnum:
    return SAEnum(cls, name=name, values_callable=lambda e: [m.value for m in e], native_enum=True)


class Role(StrEnum):
    ADMINISTRATOR = "administrator"
    INSTRUCTOR = "instructor"
    TRAINEE = "trainee"


class SessionStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"


class SessionMode(StrEnum):
    ASSIGNED = "assigned"
    SELF_GUIDED = "self_guided"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    REVIEWED = "reviewed"
    FOLLOW_UP = "follow_up"


class FeedbackLevel(StrEnum):
    SUMMARY = "summary"
    DETAILED = "detailed"


class DifficultyMode(StrEnum):
    FIXED = "fixed"
    ADAPTIVE = "adaptive"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[Role] = mapped_column(_enum(Role, "user_role"), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    # Multi-factor authentication (TOTP). Seeds are AES-GCM sealed (security/secretbox.py).
    mfa_secret_enc: Mapped[str | None] = mapped_column(String(255))
    mfa_pending_secret_enc: Mapped[str | None] = mapped_column(String(255))
    mfa_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_last_step: Mapped[int | None] = mapped_column(BigInteger)
    # Data retention
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anonymised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Optional organisational unit (team, squad, course) for unit-level reporting.
    unit: Mapped[str | None] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        CheckConstraint("username ~ '^[a-z0-9][a-z0-9._-]{2,63}$'", name="username_format"),
        CheckConstraint("(mfa_secret_enc IS NULL) = (mfa_enabled_at IS NULL)", name="mfa_consistent"),
        CheckConstraint("unit IS NULL OR length(btrim(unit)) BETWEEN 1 AND 80", name="unit_not_blank"),
    )

    @property
    def mfa_enabled(self) -> bool:
        return self.mfa_enabled_at is not None


class MfaRecoveryCode(Base):
    __tablename__ = "mfa_recovery_codes"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    code_digest: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class MfaChallenge(Base):
    """Second sign-in step after a correct password; short-lived and single-use."""

    __tablename__ = "mfa_challenges"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    user: Mapped[User] = relationship()

    __table_args__ = (CheckConstraint("mode IN ('cookie', 'token')", name="mode_valid"),)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_digest: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="cookie")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))

    user: Mapped[User] = relationship()

    __table_args__ = (CheckConstraint("kind IN ('cookie', 'bearer')", name="kind_valid"),)


class Rubric(Base):
    __tablename__ = "rubrics"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_rubrics_key_version"),
        CheckConstraint("version >= 1", name="version_positive"),
    )


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="published")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    self_guided: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rubric_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubrics.id", ondelete="RESTRICT"), nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    rubric: Mapped[Rubric] = relationship()

    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_scenarios_key_version"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("status IN ('published', 'archived')", name="status_valid"),
    )


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scenarios.id", ondelete="RESTRICT"), nullable=False)
    trainee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assigned_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    trainee_options: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    difficulty_mode: Mapped[DifficultyMode] = mapped_column(_enum(DifficultyMode, "difficulty_mode"), nullable=False)
    difficulty_level: Mapped[int] = mapped_column(Integer, nullable=False)
    min_level: Mapped[int] = mapped_column(Integer, nullable=False)
    max_level: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    feedback_level: Mapped[FeedbackLevel] = mapped_column(_enum(FeedbackLevel, "feedback_level"), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    scenario: Mapped[Scenario] = relationship()
    trainee: Mapped[User] = relationship(foreign_keys=[trainee_id])
    assigned_by: Mapped[User] = relationship(foreign_keys=[assigned_by_id])

    __table_args__ = (
        CheckConstraint(
            "min_level BETWEEN 1 AND 5 AND max_level BETWEEN 1 AND 5 AND min_level <= max_level", name="level_bounds"
        ),
        CheckConstraint("difficulty_level BETWEEN min_level AND max_level", name="level_within_bounds"),
        CheckConstraint("max_attempts BETWEEN 1 AND 50", name="attempts_range"),
        CheckConstraint("status IN ('active', 'cancelled')", name="status_valid"),
    )


class TrainingSession(Base):
    __tablename__ = "training_sessions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trainee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assignments.id", ondelete="RESTRICT"), index=True
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scenarios.id", ondelete="RESTRICT"), nullable=False)
    rubric_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubrics.id", ondelete="RESTRICT"), nullable=False)
    mode: Mapped[SessionMode] = mapped_column(_enum(SessionMode, "session_mode"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    difficulty_level: Mapped[int] = mapped_column(Integer, nullable=False)
    selection: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    effective_definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    config_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    timeline_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    generated_event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    next_seq: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[SessionStatus] = mapped_column(_enum(SessionStatus, "session_status"), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    allow_pause: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sim_elapsed_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    running_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pause_reason: Mapped[str | None] = mapped_column(String(32))
    pause_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_reason: Mapped[str | None] = mapped_column(String(32))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Set when the raw event log was deleted under the retention policy (score and digests are kept).
    events_purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    trainee: Mapped[User] = relationship()
    assignment: Mapped[Assignment | None] = relationship()
    scenario: Mapped[Scenario] = relationship()
    rubric: Mapped[Rubric] = relationship()
    result: Mapped[ScoreResult | None] = relationship(back_populates="session", uselist=False)

    __table_args__ = (
        CheckConstraint("difficulty_level BETWEEN 1 AND 5", name="level_range"),
        CheckConstraint("sim_elapsed_ms >= 0 AND sim_elapsed_ms <= duration_ms", name="elapsed_range"),
        CheckConstraint("(mode = 'assigned') = (assignment_id IS NOT NULL)", name="mode_matches_assignment"),
        CheckConstraint("(status = 'running') = (running_since IS NOT NULL)", name="running_clock"),
        Index("ix_training_sessions_status", "status"),
    )


class SessionEvent(Base):
    __tablename__ = "session_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_id: Mapped[str] = mapped_column(String(16), nullable=False)
    t_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    available_at_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    client_action_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_session_events_seq"),
        UniqueConstraint("session_id", "event_id", name="uq_session_events_event_id"),
        UniqueConstraint("session_id", "client_action_id", name="uq_session_events_client_action"),
        CheckConstraint("t_ms >= 0 AND available_at_ms >= t_ms", name="times_valid"),
        CheckConstraint("mod(t_ms, 100) = 0 AND mod(available_at_ms, 100) = 0", name="tick_quantised"),
        CheckConstraint("visibility IN ('trainee', 'ground_truth', 'system')", name="visibility_valid"),
        CheckConstraint("origin IN ('generated', 'trainee', 'system')", name="origin_valid"),
        Index("ix_session_events_feed", "session_id", "available_at_ms"),
        Index("ix_session_events_type", "session_id", "type"),
    )

    def as_event(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "seq": self.seq,
            "t_ms": self.t_ms,
            "available_at_ms": self.available_at_ms,
            "type": self.type,
            "visibility": self.visibility,
            "origin": self.origin,
            "payload": self.payload,
        }


class ScoreResult(Base):
    __tablename__ = "score_results"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    rubric_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubrics.id", ondelete="RESTRICT"), nullable=False)
    rubric_version: Mapped[int] = mapped_column(Integer, nullable=False)
    scoring_engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    result_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    overall: Mapped[float | None] = mapped_column(Float)
    passed: Mapped[bool | None] = mapped_column(Boolean)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    session: Mapped[TrainingSession] = relationship(back_populates="result")

    __table_args__ = (
        CheckConstraint("status IN ('scored', 'insufficient_data')", name="status_valid"),
        CheckConstraint("overall IS NULL OR (overall >= 0 AND overall <= 100)", name="overall_range"),
    )


class DifficultyAdjustment(Base):
    __tablename__ = "difficulty_adjustments"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trainee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assignments.id", ondelete="SET NULL"))
    scenario_key: Mapped[str] = mapped_column(String(64), nullable=False)
    triggered_by_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="SET NULL")
    )
    from_level: Mapped[int] = mapped_column(Integer, nullable=False)
    to_level: Mapped[int] = mapped_column(Integer, nullable=False)
    change: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        CheckConstraint("change IN ('increase', 'decrease', 'hold')", name="change_valid"),
        CheckConstraint("length(reason) > 0", name="reason_required"),
        CheckConstraint("abs(to_level - from_level) <= 1", name="single_step"),
    )


class InstructorReview(Base):
    __tablename__ = "instructor_reviews"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(_enum(ReviewStatus, "review_status"), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    strengths: Mapped[str] = mapped_column(Text, nullable=False, default="")
    improvements: Mapped[str] = mapped_column(Text, nullable=False, default="")
    focus_objectives: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    shared_with_trainee: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    reviewer: Mapped[User] = relationship()


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    actor_username: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    __table_args__ = (Index("ix_audit_events_action", "action"),)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class RetentionRun(Base):
    """Record of every data-retention execution (dry runs included)."""

    __tablename__ = "retention_runs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False)
    policy: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("trigger IN ('admin', 'cli')", name="trigger_valid"),)
