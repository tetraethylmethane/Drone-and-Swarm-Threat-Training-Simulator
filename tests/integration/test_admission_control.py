"""Admission control (backlog B-01): above the configured number of active exercises, new or resumed
exercises are refused quickly instead of slowing every trainee down (load-resilience-report.md)."""

from __future__ import annotations

import contextlib
import threading
import time
from typing import Any

import pytest

from drikr_api import timeline_cache
from drikr_api.services import session_service
from tests.integration.conftest import Api, FakeClock, World, make_settings, scenario_id

pytestmark = pytest.mark.integration


@pytest.fixture
def capped(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(world.app.state.ctx, "settings", make_settings(max_active_sessions=1))


def practice(api: Api) -> Any:
    return api.post("/sessions", {"scenario_id": scenario_id(api, "demo-perimeter-basics"), "selection": {}})


def test_the_next_trainee_is_refused_until_a_place_is_free(
    capped: None, admin: Api, trainee: Api, trainee2: Api, clock: FakeClock
) -> None:
    first = practice(trainee)
    assert first.status_code == 201  # a created session holds a place before it starts
    refused = practice(trainee2)
    assert refused.status_code == 503 and refused.headers["Retry-After"] == "30"
    assert refused.json()["error"]["code"] == "capacity_reached"
    assert "maximum of 1 exercises" in refused.json()["error"]["message"]
    assert trainee2.get("/sessions").json()["items"] == []  # nothing was stored for the refused trainee
    sid = first.json()["id"]
    trainee.post(f"/sessions/{sid}/start")
    clock.advance(5)
    assert trainee.post(f"/sessions/{sid}/complete").status_code == 200
    assert practice(trainee2).status_code == 201  # the place is free again
    capacity = admin.get("/admin/system").json()["capacity"]
    assert (capacity["active_sessions"], capacity["max_active_sessions"]) == (1, 1)


def test_resuming_counts_against_the_limit(capped: None, trainee: Api, trainee2: Api, clock: FakeClock) -> None:
    a = practice(trainee).json()["id"]
    trainee.post(f"/sessions/{a}/start")
    assert trainee.post(f"/sessions/{a}/pause").status_code == 200  # paused sessions hold no place
    b = practice(trainee2)
    assert b.status_code == 201
    trainee2.post(f"/sessions/{b.json()['id']}/start")
    r = trainee.post(f"/sessions/{a}/resume")
    assert r.status_code == 503 and r.json()["error"]["code"] == "capacity_reached"
    assert trainee.get(f"/sessions/{a}").json()["status"] == "paused"  # unchanged; resumable later


def _simultaneous_creations(apis: list[Api], sid: str) -> list[int]:
    codes: list[int] = []
    barrier = threading.Barrier(len(apis))

    def go(api: Api) -> None:
        barrier.wait()
        codes.append(api.post("/sessions", {"scenario_id": sid, "selection": {}}).status_code)

    threads = [threading.Thread(target=go, args=(a,)) for a in apis]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return sorted(codes)


def test_concurrent_requests_cannot_both_take_the_last_place(
    capped: None, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Widen the race window: pause after counting, as a slow commit would. Without the advisory lock
    # both requests count only themselves and both are admitted; with it, the second waits and is refused.
    count = session_service.active_session_count

    def slow_count(db: Any) -> int:
        n = count(db)
        time.sleep(0.5)
        return n

    monkeypatch.setattr(session_service, "active_session_count", slow_count)
    # Bypass the in-process slot, as requests in separate API processes would: this tests the
    # database lock, which is the guarantee across processes.
    monkeypatch.setattr(session_service, "creation_slot", lambda db, limit: contextlib.nullcontext())
    for _ in range(3):
        apis = [world.login("trainee1"), world.login("trainee2")]
        assert _simultaneous_creations(apis, scenario_id(apis[0], "demo-perimeter-basics")) == [201, 503]
        for api in apis:  # free the place for the next round
            for s in api.get("/sessions").json()["items"]:
                if s["status"] in ("created", "running", "paused"):
                    api.post(f"/sessions/{s['id']}/start")
                    api.post(f"/sessions/{s['id']}/complete")


def test_a_refused_request_does_no_generation_work(
    capped: None, trainee: Api, trainee2: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression (load report 5.8): refusals used to generate and store a whole timeline before
    # being rolled back, which slowed the admitted trainees the limit is meant to protect.
    assert practice(trainee).status_code == 201
    calls: list[object] = []
    real = timeline_cache.cpu.run

    def counting(fn: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(fn)
        return real(fn, *args, **kwargs)

    monkeypatch.setattr(timeline_cache.cpu, "run", counting)
    for _ in range(3):
        assert practice(trainee2).status_code == 503
    assert calls == []


def test_a_simultaneous_burst_generates_only_what_can_be_admitted(
    capped: None, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression (load report 5.8, run 2): at a synchronised start every request saw zero committed
    # sessions, so all of them generated a timeline and the surplus was refused only afterwards.
    # Creations in progress now hold a place, so the surplus is refused before any work.
    generated: list[object] = []
    real = timeline_cache.cpu.run

    def slow_generation(fn: Any, *args: Any, **kwargs: Any) -> Any:
        generated.append(fn)
        time.sleep(0.5)  # a realistic generation time keeps the creations overlapping
        return real(fn, *args, **kwargs)

    monkeypatch.setattr(timeline_cache.cpu, "run", slow_generation)
    apis = [world.login("trainee1"), world.login("trainee2")]
    assert _simultaneous_creations(apis, scenario_id(apis[0], "demo-perimeter-basics")) == [201, 503]
    assert len(generated) == 1


def test_no_limit_by_default(world: World, trainee: Api, trainee2: Api) -> None:
    assert world.app.state.ctx.settings.max_active_sessions == 0
    assert practice(trainee).status_code == 201 and practice(trainee2).status_code == 201
