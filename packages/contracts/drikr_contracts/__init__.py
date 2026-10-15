"""Shared, versioned contracts for the Drikr Systems training simulator.

These models are the single source of truth for scenario definitions, simulation
events and trainee actions. JSON Schema files exported from them live in
``packages/contracts/schemas`` and are consumed by the web client and by any
future Unity adapter.

All data described by these contracts is synthetic training data.
"""

from drikr_contracts.actions import TraineeAction
from drikr_contracts.enums import (
    ActionKind,
    Behavior,
    Confidence,
    EntityClass,
    Formation,
    SensorKind,
    Terrain,
    TimeOfDay,
    TrackClassification,
    TrainingResponse,
    Weather,
)
from drikr_contracts.events import EventOrigin, EventType, EventVisibility, SimEvent
from drikr_contracts.scenario import (
    SCENARIO_SCHEMA_VERSION,
    Scenario,
    TraineeOptions,
    TraineeSelection,
)

CONTRACTS_VERSION = "1.0.0"

__all__ = [
    "CONTRACTS_VERSION",
    "SCENARIO_SCHEMA_VERSION",
    "ActionKind",
    "Behavior",
    "Confidence",
    "EntityClass",
    "EventOrigin",
    "EventType",
    "EventVisibility",
    "Formation",
    "Scenario",
    "SensorKind",
    "SimEvent",
    "Terrain",
    "TimeOfDay",
    "TrackClassification",
    "TraineeAction",
    "TraineeOptions",
    "TraineeSelection",
    "TrainingResponse",
    "Weather",
]
