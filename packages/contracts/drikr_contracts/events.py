"""Simulation event log contract.

Every session owns an append-only, ordered event log. Generated events (the
deterministic timeline) are written when the session is created; lifecycle and
trainee events are appended as the exercise runs.

Timing rules (see docs/architecture/architecture-decisions.md, ADR-002):

* ``t_ms`` is simulation time in milliseconds, quantised to the 100 ms tick.
* ``available_at_ms`` is when the event becomes visible to the trainee
  (``t_ms`` plus simulated sensor latency). It is never earlier than ``t_ms``.
* Ground-truth events are never delivered to the trainee during an exercise.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from drikr_contracts._base import StrictModel
from drikr_contracts.enums import (
    Behavior,
    Confidence,
    EntityClass,
    SensorKind,
    TrackClassification,
    TrainingResponse,
)

TICK_MS = 100


class EventVisibility(StrEnum):
    TRAINEE = "trainee"
    GROUND_TRUTH = "ground_truth"
    SYSTEM = "system"


class EventOrigin(StrEnum):
    GENERATED = "generated"
    TRAINEE = "trainee"
    SYSTEM = "system"


class EventType(StrEnum):
    # Ground truth: hidden from trainees during the exercise.
    ENTITY_SPAWNED = "entity_spawned"
    ENTITY_STATE = "entity_state"
    ENTITY_EXITED = "entity_exited"
    TRACK_ASSIGNED = "track_assigned"
    OBSERVATION_MISSED = "observation_missed"
    # Trainee-visible synthetic observations and exercise information.
    TRACK_OBSERVATION = "track_observation"
    TRACK_LOST = "track_lost"
    SENSOR_STATUS = "sensor_status"
    ENVIRONMENT_UPDATE = "environment_update"
    EXERCISE_MESSAGE = "exercise_message"
    SENSOR_CONFIRMATION = "sensor_confirmation"
    # Session lifecycle.
    SESSION_STARTED = "session_started"
    SESSION_PAUSED = "session_paused"
    SESSION_RESUMED = "session_resumed"
    SESSION_COMPLETED = "session_completed"
    # Trainee decisions.
    CLASSIFICATION_SUBMITTED = "classification_submitted"
    RESPONSE_SUBMITTED = "response_submitted"


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------


class EntitySpawnedPayload(StrictModel):
    entity_id: str
    group_id: str
    entity_class: EntityClass
    behavior: Behavior
    cooperative: bool
    swarm_id: str | None = None
    signature: float


class EntityStatePayload(StrictModel):
    entity_id: str
    x_m: float
    y_m: float
    alt_m: float
    speed_mps: float
    heading_deg: float
    range_m: float


class EntityExitedPayload(StrictModel):
    entity_id: str
    reason: Literal["left_area", "faded"]


class TrackAssignedPayload(StrictModel):
    track_id: str
    entity_id: str


class ObservationMissedPayload(StrictModel):
    entity_id: str
    sensor: SensorKind
    reason: Literal["out_of_range", "not_detected"]


class TrackObservationPayload(StrictModel):
    track_id: str
    sensor: SensorKind
    synthetic: Literal[True] = True
    quality: float = Field(ge=0.0, le=1.0)
    x_m: float | None = None
    y_m: float | None = None
    alt_m: float | None = None
    speed_mps: float | None = None
    bearing_deg: float | None = None
    class_hint: TrackClassification | None = None
    beacon: bool | None = None


class TrackLostPayload(StrictModel):
    track_id: str


class SensorStatusPayload(StrictModel):
    sensor: SensorKind
    status: Literal["nominal", "degraded"]
    detection_factor: float
    noise_factor: float
    extra_delay_s: float


class EnvironmentUpdatePayload(StrictModel):
    visibility_km: float


class ExerciseMessagePayload(StrictModel):
    message: str


class SensorConfirmationPayload(StrictModel):
    track_id: str
    synthetic: Literal[True] = True
    outcome: Literal["hint_available", "no_contact"]
    class_hint: TrackClassification | None = None
    quality: float = Field(ge=0.0, le=1.0)
    requested_by_action: UUID


class LifecyclePayload(StrictModel):
    reason: str | None = None


class ClassificationSubmittedPayload(StrictModel):
    client_action_id: UUID
    track_ids: list[str]
    classification: TrackClassification
    confidence: Confidence
    note: str | None = None


class ResponseSubmittedPayload(StrictModel):
    client_action_id: UUID
    track_ids: list[str]
    response: TrainingResponse
    note: str | None = None


PAYLOAD_MODELS: dict[EventType, type[BaseModel]] = {
    EventType.ENTITY_SPAWNED: EntitySpawnedPayload,
    EventType.ENTITY_STATE: EntityStatePayload,
    EventType.ENTITY_EXITED: EntityExitedPayload,
    EventType.TRACK_ASSIGNED: TrackAssignedPayload,
    EventType.OBSERVATION_MISSED: ObservationMissedPayload,
    EventType.TRACK_OBSERVATION: TrackObservationPayload,
    EventType.TRACK_LOST: TrackLostPayload,
    EventType.SENSOR_STATUS: SensorStatusPayload,
    EventType.ENVIRONMENT_UPDATE: EnvironmentUpdatePayload,
    EventType.EXERCISE_MESSAGE: ExerciseMessagePayload,
    EventType.SENSOR_CONFIRMATION: SensorConfirmationPayload,
    EventType.SESSION_STARTED: LifecyclePayload,
    EventType.SESSION_PAUSED: LifecyclePayload,
    EventType.SESSION_RESUMED: LifecyclePayload,
    EventType.SESSION_COMPLETED: LifecyclePayload,
    EventType.CLASSIFICATION_SUBMITTED: ClassificationSubmittedPayload,
    EventType.RESPONSE_SUBMITTED: ResponseSubmittedPayload,
}

GROUND_TRUTH_TYPES = frozenset(
    {
        EventType.ENTITY_SPAWNED,
        EventType.ENTITY_STATE,
        EventType.ENTITY_EXITED,
        EventType.TRACK_ASSIGNED,
        EventType.OBSERVATION_MISSED,
    }
)


class SimEvent(StrictModel):
    event_id: str = Field(pattern=r"^[GST]-\d{6}$")
    seq: int = Field(ge=0)
    t_ms: int = Field(ge=0)
    available_at_ms: int = Field(ge=0)
    type: EventType
    visibility: EventVisibility
    origin: EventOrigin
    payload: dict[str, Any]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.t_ms % TICK_MS != 0 or self.available_at_ms % TICK_MS != 0:
            raise ValueError("event times must be quantised to the 100 ms simulation tick")
        if self.available_at_ms < self.t_ms:
            raise ValueError("available_at_ms must not precede t_ms")
        if (self.type in GROUND_TRUTH_TYPES) != (self.visibility is EventVisibility.GROUND_TRUTH):
            raise ValueError("ground-truth event types must carry ground_truth visibility and vice versa")
        PAYLOAD_MODELS[self.type].model_validate(self.payload)
        return self
