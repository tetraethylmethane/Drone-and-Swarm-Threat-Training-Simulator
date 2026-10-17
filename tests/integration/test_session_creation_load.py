"""Session creation under concurrency (load-test defect L-01, docs/testing/load-resilience-report.md).

Under ten concurrent trainees the API exhausted its 20-connection pool: each new session wrote about
3,700 generated events with a parameterised INSERT while holding a connection, and requests that
already had a worker thread then waited 30 s for a connection and failed. The fix writes the timeline
with COPY and sizes the pool to the worker-thread pool. These tests pin the behaviour the fix must
keep (the stored timeline is exactly the generated one) and the conditions it relies on.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import anyio
import anyio.to_thread
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from drikr_api import cpu
from drikr_api.db import Database
from drikr_api.main import create_app
from drikr_contracts.scenario import Scenario as ScenarioContract
from drikr_simcore import generate_timeline, load_demo_scenarios
from tests.integration.conftest import PASSWORD, TEST_URL, Api, World, make_settings, scenario_id

pytestmark = pytest.mark.integration

TRAINEES = 8


def test_stored_timeline_is_exactly_the_generated_one(trainee: Api, engine: Engine) -> None:
    s = trainee.post("/sessions", {"scenario_id": scenario_id(trainee, "demo-perimeter-basics"), "selection": {}})
    assert s.status_code == 201, s.text
    sid = s.json()["id"]
    with engine.connect() as c:
        row = c.execute(
            text(
                "SELECT effective_definition, seed, difficulty_level, generated_event_count"
                " FROM training_sessions WHERE id = :i"
            ),
            {"i": sid},
        ).one()
        stored = c.execute(
            text(
                "SELECT seq, event_id, t_ms, available_at_ms, type, visibility, origin, payload, recorded_at"
                " FROM session_events WHERE session_id = :i ORDER BY seq"
            ),
            {"i": sid},
        ).all()
    expected = generate_timeline(
        ScenarioContract.model_validate(row.effective_definition), seed=row.seed, difficulty_level=row.difficulty_level
    )
    assert len(stored) == row.generated_event_count == len(expected.events) > 3000
    fields = ("seq", "event_id", "t_ms", "available_at_ms", "type", "visibility", "origin", "payload")
    assert [tuple(getattr(r, f) for f in fields) for r in stored] == [
        tuple(e[f] for f in fields) for e in expected.events
    ]
    assert all(r.recorded_at is not None for r in stored)
    # The append-only trigger still guards rows written by COPY.
    with engine.connect() as c, pytest.raises(Exception, match="append-only"):
        c.execute(text("UPDATE session_events SET t_ms = t_ms WHERE session_id = :i"), {"i": sid})


def test_connection_pool_covers_the_worker_threads() -> None:
    database = Database(TEST_URL)
    try:
        pool: Any = database.engine.pool
        capacity = pool.size() + pool._max_overflow

        async def worker_threads() -> float:
            return anyio.to_thread.current_default_thread_limiter().total_tokens

        assert capacity >= anyio.run(worker_threads)
    finally:
        database.dispose()


def test_concurrent_trainees_all_create_and_poll_sessions(world: World, admin: Api, engine: Engine) -> None:
    for i in range(TRAINEES):
        r = admin.post(
            "/users",
            {"username": f"conc{i}", "display_name": f"Conc {i}", "role": "trainee", "password": "Training-Pass-2026!"},
        )
        assert r.status_code == 201, r.text
    with engine.begin() as c:  # skip the first-sign-in password change; it is not under test here
        c.execute(text("UPDATE users SET must_change_password = false WHERE username LIKE 'conc%'"))
    apis = [world.login(f"conc{i}") for i in range(TRAINEES)]
    sc = scenario_id(apis[0], "demo-perimeter-basics")

    def run(api: Api) -> list[int]:
        codes = []
        created = api.post("/sessions", {"scenario_id": sc, "selection": {}})
        codes.append(created.status_code)
        sid = created.json()["id"]
        codes.append(api.post(f"/sessions/{sid}/start").status_code)
        codes += [api.get(f"/sessions/{sid}/feed?since_ms=0").status_code for _ in range(3)]
        codes.append(api.post(f"/sessions/{sid}/complete").status_code)
        return codes

    with ThreadPoolExecutor(TRAINEES) as pool:
        results = list(pool.map(run, apis))
    assert results == [[201, 200, 200, 200, 200, 200]] * TRAINEES


def test_generation_in_a_worker_process_matches_inline() -> None:
    """Moving generation to worker processes (L-02) cannot change a record."""
    scn = ScenarioContract.model_validate(load_demo_scenarios()[0])
    inline = generate_timeline(scn, seed=4242, difficulty_level=3)
    cpu.configure(1)
    try:
        pooled = cpu.run(generate_timeline, scn, seed=4242, difficulty_level=3)
    finally:
        cpu.configure(0)
    assert pooled.digest == inline.digest and pooled.events == inline.events


def test_api_with_worker_processes_stores_the_same_timeline(engine: Engine, seeded: dict[str, Any]) -> None:
    database = Database(TEST_URL)
    try:
        with TestClient(create_app(make_settings(cpu_workers=1, sweeper_interval_s=0), database)) as client:
            api = Api(client)
            r = api.post("/auth/login", {"username": "trainee1", "password": PASSWORD})
            api.csrf = r.json()["csrf_token"]
            s = api.post("/sessions", {"scenario_id": scenario_id(api, "demo-night-loiter"), "selection": {}})
            assert s.status_code == 201, s.text
        with engine.connect() as c:
            row = c.execute(
                text(
                    "SELECT effective_definition, seed, difficulty_level, timeline_digest"
                    " FROM training_sessions WHERE id = :i"
                ),
                {"i": s.json()["id"]},
            ).one()
        expected = generate_timeline(
            ScenarioContract.model_validate(row.effective_definition),
            seed=row.seed,
            difficulty_level=row.difficulty_level,
        )
        assert row.timeline_digest == expected.digest
    finally:
        cpu.configure(0)
        database.dispose()
