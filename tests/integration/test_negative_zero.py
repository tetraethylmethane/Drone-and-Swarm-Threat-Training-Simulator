"""Regression for D-03: a timeline containing -0.0 must verify after the database round trip."""

from __future__ import annotations

import math
from typing import Any

import pytest

from drikr_contracts import Scenario
from drikr_simcore import generate_timeline
from tests.integration.conftest import Api, FakeClock, assign
from tests.unit.helpers import demo

pytestmark = pytest.mark.integration

SEED_WITH_NEGATIVE_ZERO = 4293632572495760  # entity_state x_m = -0.0 in Perimeter basics v2, level 2


def _has_negative_zero(obj: Any) -> bool:
    if isinstance(obj, float):
        return obj == 0.0 and math.copysign(1.0, obj) < 0
    if isinstance(obj, dict):
        return any(_has_negative_zero(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_negative_zero(v) for v in obj)
    return False


def test_a_session_whose_timeline_contains_negative_zero_verifies(
    instructor: Api, trainee: Api, clock: FakeClock
) -> None:
    tl = generate_timeline(Scenario.model_validate(demo()), seed=SEED_WITH_NEGATIVE_ZERO, difficulty_level=2)
    assert any(_has_negative_zero(e["payload"]) for e in tl.events)  # the case under test
    a = assign(instructor, trainee, trainee_options={"allow_custom_seed": True}, difficulty_level=2)
    sid = trainee.post("/sessions", {"assignment_id": a["id"], "selection": {"seed": SEED_WITH_NEGATIVE_ZERO}}).json()[
        "id"
    ]
    trainee.post(f"/sessions/{sid}/start")
    clock.advance(5)
    trainee.post(f"/sessions/{sid}/complete")
    report = instructor.post(f"/sessions/{sid}/verify").json()
    assert report["stored_log_intact"] and report["timeline_reproduced"] and report["reproducible"]
