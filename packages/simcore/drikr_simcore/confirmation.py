"""Simulated sensor-confirmation requests.

When a trainee chooses ``request_sensor_confirmation`` the virtual exercise
returns an improved (but still uncertain) synthetic classification hint after a
fixed delay. The outcome is deterministic: it depends only on the session seed,
the track, the request tick and the recorded ground truth.
"""

from __future__ import annotations

import math
from typing import Any
from uuid import UUID

from drikr_contracts.enums import TrackClassification
from drikr_contracts.events import EventOrigin, EventType, EventVisibility
from drikr_contracts.scenario import Scenario
from drikr_simcore.difficulty import modifiers_for
from drikr_simcore.generator import effective_eo_accuracy, effective_eo_range, wrong_label
from drikr_simcore.ground_truth import GroundTruthIndex
from drikr_simcore.rng import Rng

CONFIRMATION_DELAY_MS = 4000


def sensor_confirmation_event(
    scn: Scenario,
    seed: int,
    difficulty_level: int,
    index: GroundTruthIndex,
    track_id: str,
    t_ms: int,
    action_id: UUID,
) -> dict[str, Any]:
    """Build an unsequenced ``sensor_confirmation`` event for a request made at ``t_ms``."""
    rng = Rng.stream(seed, "confirmation", track_id, t_ms)
    entity = index.entity_for_track(track_id)
    result_ms = t_ms + CONFIRMATION_DELAY_MS
    payload: dict[str, Any] = {
        "track_id": track_id,
        "synthetic": True,
        "requested_by_action": str(action_id),
        "outcome": "no_contact",
        "class_hint": None,
        "quality": 0.0,
    }
    if entity is not None and entity.active_at(t_ms):
        mods = modifiers_for(difficulty_level)
        acc = min(0.95, effective_eo_accuracy(scn, mods) + 0.2) if scn.sensors.electro_optical.enabled else 0.6
        state = entity.state_at(t_ms)
        if state is not None:
            reach = max(1500.0, effective_eo_range(scn, scn.environment.visibility_km) * 1.5)
            if math.hypot(state["x_m"], state["y_m"]) > reach:
                acc *= 0.7
        true_label = TrackClassification(entity.entity_class)
        hint = true_label if rng.chance(acc) else wrong_label(true_label, rng)
        payload.update({"outcome": "hint_available", "class_hint": hint.value, "quality": round(acc, 2)})
    return {
        "t_ms": result_ms,
        "available_at_ms": result_ms,
        "type": EventType.SENSOR_CONFIRMATION.value,
        "visibility": EventVisibility.TRAINEE.value,
        "origin": EventOrigin.SYSTEM.value,
        "payload": payload,
    }
