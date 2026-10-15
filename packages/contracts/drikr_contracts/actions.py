"""Trainee actions submitted during a virtual exercise.

The available training responses are procedural reporting steps inside the
virtual exercise. None of them represent or recommend a real-world engagement.
"""

from __future__ import annotations

import re
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from drikr_contracts._base import StrictModel
from drikr_contracts.enums import ActionKind, Confidence, TrackClassification, TrainingResponse

TRACK_ID_PATTERN = r"^TRK-\d{3}$"


class TraineeAction(StrictModel):
    """A single trainee decision. ``client_action_id`` makes submission idempotent."""

    client_action_id: UUID
    kind: ActionKind
    track_ids: list[str] = Field(min_length=1, max_length=24)
    classification: TrackClassification | None = None
    confidence: Confidence | None = None
    response: TrainingResponse | None = None
    note: str | None = Field(default=None, max_length=280)

    @model_validator(mode="after")
    def _shape(self) -> Self:
        for tid in self.track_ids:
            if not re.match(TRACK_ID_PATTERN, tid):
                raise ValueError(f"invalid track id '{tid}'")
        if len(set(self.track_ids)) != len(self.track_ids):
            raise ValueError("track_ids must be unique")
        if self.kind is ActionKind.CLASSIFY:
            if self.classification is None or self.confidence is None:
                raise ValueError("classify actions require classification and confidence")
            if self.response is not None:
                raise ValueError("classify actions must not include a response")
        else:
            if self.response is None:
                raise ValueError("respond actions require a response")
            if self.classification is not None or self.confidence is not None:
                raise ValueError("respond actions must not include classification or confidence")
        return self
