"""Pre-generated first attempts (backlog B-17): created with the assignment, used at the start,
identical to generating at the start, and never used where the inputs differ."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from drikr_api import timeline_cache
from drikr_api.models import TrainingSession
from drikr_contracts import Scenario
from drikr_simcore import generate_timeline
from tests.integration.conftest import Api, World, assign

pytestmark = pytest.mark.integration


@pytest.fixture
def cache() -> Any:
    timeline_cache.configure(64)
    yield
    timeline_cache.configure(64)


def _count_generation(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    calls: list[object] = []
    real = timeline_cache.cpu.run

    def counting(fn: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(fn)
        return real(fn, *args, **kwargs)

    monkeypatch.setattr(timeline_cache.cpu, "run", counting)
    return calls


def test_a_class_starts_from_pregenerated_timelines(
    cache: None, world: World, instructor: Api, trainee: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = assign(instructor, trainee)
    timeline_cache.wait_idle()
    assert timeline_cache.stats()["entries"] == 1

    calls = _count_generation(monkeypatch)
    s = trainee.post("/sessions", {"assignment_id": a["id"]}).json()
    assert calls == []  # the start did no generation
    assert timeline_cache.stats()["hits"] == 1

    # Identical to generating now, and verifiable like any session.
    with world.app.state.ctx.database.session_factory() as db:
        row = db.get(TrainingSession, uuid.UUID(s["id"]))
        assert row is not None
        fresh = generate_timeline(
            Scenario.model_validate(row.effective_definition), seed=row.seed, difficulty_level=row.difficulty_level
        )
        assert row.timeline_digest == fresh.digest
    trainee.post(f"/sessions/{s['id']}/start")
    trainee.post(f"/sessions/{s['id']}/complete")
    assert instructor.post(f"/sessions/{s['id']}/verify").json()["reproducible"]


def test_later_attempts_and_the_adaptive_adversary_are_generated_at_the_start(
    cache: None, instructor: Api, trainee: Api, trainee2: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = assign(instructor, trainee, max_attempts=3)
    adv = assign(instructor, trainee2, adaptive_adversary=True)
    timeline_cache.wait_idle()
    assert timeline_cache.stats()["entries"] == 1  # nothing for the adversary assignment

    calls = _count_generation(monkeypatch)
    first = trainee.post("/sessions", {"assignment_id": a["id"]}).json()["id"]
    trainee.post(f"/sessions/{first}/start")
    trainee.post(f"/sessions/{first}/complete")
    trainee.post("/sessions", {"assignment_id": a["id"]})  # attempt 2: other seed, generated now
    trainee2.post("/sessions", {"assignment_id": adv["id"]})  # plan depends on history: generated now
    assert len(calls) == 2


def test_pregeneration_can_be_turned_off(world: World, instructor: Api, trainee: Api) -> None:
    timeline_cache.configure(0)
    try:
        assign(instructor, trainee)
        timeline_cache.wait_idle()
        assert timeline_cache.stats()["entries"] == 0
    finally:
        timeline_cache.configure(64)
