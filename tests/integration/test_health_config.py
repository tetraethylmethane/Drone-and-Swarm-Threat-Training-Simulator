"""Health checks, configuration validation and database-unavailable handling."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from drikr_api.db import Database
from drikr_api.main import create_app
from tests.integration.conftest import TEST_URL, World, make_settings

pytestmark = pytest.mark.integration


def test_health_and_readiness(world: World) -> None:
    api = world.anon()
    r = api.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    ready = api.get("/health/ready").json()
    assert ready == {"status": "ready", "database": "ok", "schema_revision": "0006"}
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"secret_key": "short"}, "at least 32 characters"),
        ({"secret_key": "change-me"}, "at least 32 characters"),
        ({"database_url": "sqlite:///x.db"}, r"postgresql\+psycopg"),
        ({"environment": "production", "cookie_secure": False}, "cookie_secure must be true"),
        (
            {
                "environment": "production",
                "cookie_secure": True,
                "secret_key": "dev_only-but-long-enough-0123456789abcdef",
            },
            "development credentials",
        ),
        ({"heartbeat_grace_s": 1}, "greater than or equal to 3"),
    ],
)
def test_invalid_configuration_rejected(overrides: dict, fragment: str) -> None:
    with pytest.raises(ValidationError, match=fragment):
        make_settings(**overrides)


def test_database_unavailable_returns_structured_503() -> None:
    bad_url = TEST_URL.rsplit("@", 1)[0] + "@127.0.0.1:1/nowhere"
    app = create_app(make_settings(database_url=bad_url), Database(bad_url, connect_args={"connect_timeout": 1}))
    with TestClient(app) as c:
        r = c.post("/api/v1/auth/login", json={"username": "x", "password": "y"})
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "database_unavailable"
        ready = c.get("/api/v1/health/ready")
        assert ready.status_code == 503


def test_no_interactive_docs_or_cdn_assets(world: World) -> None:
    api = world.anon()
    assert api.client.get("/docs").status_code == 404
    spec = api.get("/openapi.json")
    assert spec.status_code == 200
    assert "cdn" not in spec.text.lower()
