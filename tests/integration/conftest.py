"""Integration fixtures: a migrated PostgreSQL test database, an app instance and role-specific clients.

Requires TEST_DATABASE_URL (defaults to the local development cluster created by
scripts/local-postgres.ps1). Tests are skipped if the database is unreachable.
The test database is reset at the start of the run and truncated between tests.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from drikr_api.cli import migrate, seed_demo
from drikr_api.config import Settings
from drikr_api.db import Database
from drikr_api.main import create_app

TEST_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://drikr:drikr_dev_only@127.0.0.1:55432/drikr_test")
PASSWORD = "Training-Pass-2026!"
TABLES = [
    "retention_runs",
    "mfa_challenges",
    "mfa_recovery_codes",
    "difficulty_adjustments",
    "instructor_reviews",
    "score_results",
    "session_events",
    "training_sessions",
    "assignments",
    "scenarios",
    "rubrics",
    "auth_sessions",
    "app_settings",
    "audit_events",
    "users",
]

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    eng = create_engine(TEST_URL, future=True)
    try:
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL not reachable at TEST_DATABASE_URL: {exc}")
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        for t in ("user_role", "difficulty_mode", "feedback_level", "session_mode", "session_status", "review_status"):
            c.execute(text(f"DROP TYPE IF EXISTS {t} CASCADE"))
    migrate(TEST_URL)
    yield eng
    eng.dispose()


MUTABLE_TABLES = [
    "retention_runs",
    "mfa_challenges",
    "mfa_recovery_codes",
    "difficulty_adjustments",
    "instructor_reviews",
    "score_results",
    "session_events",
    "training_sessions",
    "assignments",
    "auth_sessions",
    "app_settings",
    "audit_events",
]
USER_COLUMNS = (
    "password_hash",
    "display_name",
    "role",
    "is_active",
    "must_change_password",
    "failed_login_count",
    "locked_until",
    "mfa_secret_enc",
    "mfa_pending_secret_enc",
    "mfa_enabled_at",
    "mfa_last_step",
    "deactivated_at",
    "anonymised_at",
)


def truncate_all(eng: Engine) -> None:
    with eng.begin() as c:
        # The audit table is append-only via trigger; tests bypass it deliberately.
        c.execute(text("SET LOCAL session_replication_role = replica"))
        c.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def seeded(engine: Engine) -> dict[str, dict[str, Any]]:
    """Seed demo rubric, scenarios and users once; return a snapshot of the demo users."""
    truncate_all(engine)
    os.environ["DRIKR_DEMO_PASSWORD"] = PASSWORD
    seed_demo(TEST_URL, with_users=True)
    with engine.connect() as c:
        rows = c.execute(text(f"SELECT id, username, {', '.join(USER_COLUMNS)} FROM users")).mappings().all()
    return {r["username"]: dict(r) for r in rows}


def reset_to_seed(eng: Engine, users: dict[str, dict[str, Any]]) -> None:
    """Restore the seeded baseline: drop everything tests created and reset demo users."""
    with eng.begin() as c:
        c.execute(text("SET LOCAL session_replication_role = replica"))
        c.execute(text(f"TRUNCATE {', '.join(MUTABLE_TABLES)} RESTART IDENTITY CASCADE"))
        c.execute(text("DELETE FROM scenarios WHERE NOT is_demo"))
        c.execute(text("DELETE FROM rubrics WHERE NOT is_demo"))
        c.execute(text("UPDATE scenarios SET status = 'published'"))
        ids = [row["id"] for row in users.values()]
        c.execute(text("DELETE FROM users WHERE NOT (id = ANY(:ids))"), {"ids": ids})
        for row in users.values():
            sets = ", ".join(f"{col} = :{col}" for col in ("username", *USER_COLUMNS))
            c.execute(text(f"UPDATE users SET {sets} WHERE id = :id"), row)
        # Baseline: no role requires MFA, so general tests can sign in with a password only.
        # tests/integration/test_mfa.py exercises the shipped default (administrators required).
        c.execute(text("INSERT INTO app_settings (key, value, updated_at) VALUES ('mfa_required_roles', '[]', now())"))


def make_settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "environment": "test",
        "database_url": TEST_URL,
        "secret_key": "test-secret-key-that-is-long-enough-0123456789",
        "cookie_secure": False,
        "sweeper_interval_s": 0,
        "login_rate_limit_per_minute": 1000,
        "lockout_threshold": 5,
        "heartbeat_grace_s": 15,
        "log_level": "WARNING",
    }
    base.update(overrides)
    return Settings(**base)


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 14, 9, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    """Controls the exercise clock (session lifecycle, feed and actions)."""
    fc = FakeClock()
    monkeypatch.setattr("drikr_api.routers.sessions.utcnow", fc)
    monkeypatch.setattr("drikr_api.services.session_service.utcnow", fc)
    return fc


@dataclass
class Api:
    """A TestClient bound to one signed-in user, adding the CSRF header automatically."""

    client: TestClient
    csrf: str | None = None
    user: dict[str, Any] | None = None

    def _h(self, headers: dict[str, str] | None) -> dict[str, str]:
        h = dict(headers or {})
        if self.csrf:
            h.setdefault("X-CSRF-Token", self.csrf)
        return h

    def get(self, url: str, **kw: Any) -> Any:
        return self.client.get("/api/v1" + url, **kw)

    def post(self, url: str, json: Any = None, **kw: Any) -> Any:
        return self.client.post("/api/v1" + url, json=json, headers=self._h(kw.pop("headers", None)), **kw)

    def put(self, url: str, json: Any = None, **kw: Any) -> Any:
        return self.client.put("/api/v1" + url, json=json, headers=self._h(kw.pop("headers", None)), **kw)

    def patch(self, url: str, json: Any = None, **kw: Any) -> Any:
        return self.client.patch("/api/v1" + url, json=json, headers=self._h(kw.pop("headers", None)), **kw)


class World:
    def __init__(self, app: Any) -> None:
        self.app = app
        self._clients: list[TestClient] = []

    def anon(self) -> Api:
        c = TestClient(self.app)
        self._clients.append(c)
        return Api(c)

    def login(self, username: str, password: str = PASSWORD) -> Api:
        api = self.anon()
        r = api.post("/auth/login", {"username": username, "password": password})
        assert r.status_code == 200, r.text
        api.csrf = r.json()["csrf_token"]
        api.user = r.json()["user"]
        return api

    def close(self) -> None:
        for c in self._clients:
            c.close()


@pytest.fixture
def app(engine: Engine, seeded: dict[str, dict[str, Any]]) -> Iterator[Any]:
    reset_to_seed(engine, seeded)
    database = Database(TEST_URL)
    application = create_app(make_settings(), database)
    yield application
    database.dispose()


@pytest.fixture
def world(app: Any) -> Iterator[World]:
    w = World(app)
    yield w
    w.close()


@pytest.fixture
def admin(world: World) -> Api:
    return world.login("admin")


@pytest.fixture
def instructor(world: World) -> Api:
    return world.login("instructor")


@pytest.fixture
def trainee(world: World) -> Api:
    return world.login("trainee1")


@pytest.fixture
def trainee2(world: World) -> Api:
    return world.login("trainee2")


def scenario_id(api: Api, key: str) -> str:
    items = api.get("/scenarios").json()["items"]
    return next(s["id"] for s in items if s["key"] == key)


def assign(instructor: Api, trainee: Api, key: str = "demo-perimeter-basics", **overrides: Any) -> dict[str, Any]:
    body = {
        "scenario_id": scenario_id(instructor, key),
        "trainee_ids": [trainee.user["id"]],  # type: ignore[index]
        "title": f"Exercise {key}",
        "instructions": "Complete the exercise.",
        "difficulty_level": 2,
        "min_level": 1,
        "max_level": 4,
        "max_attempts": 3,
    }
    body.update(overrides)
    r = instructor.post("/assignments", body)
    assert r.status_code == 201, r.text
    return r.json()["items"][0]
