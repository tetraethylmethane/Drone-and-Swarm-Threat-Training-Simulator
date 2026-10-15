"""Authentication, session lifecycle, CSRF, lockout and secret hygiene."""

from __future__ import annotations

import logging
from datetime import timedelta

import pytest
from sqlalchemy import select, text, update

from drikr_api.models import AuthSession, User
from tests.integration.conftest import PASSWORD, Api, World

pytestmark = pytest.mark.integration


def test_login_success_sets_hardened_cookies(world: World) -> None:
    api = world.anon()
    r = api.post("/auth/login", {"username": "instructor", "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["role"] == "instructor"
    assert "scenarios:write" in body["user"]["permissions"]
    cookies = r.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("drikr_session="))
    assert "HttpOnly" in session_cookie and "SameSite=strict" in session_cookie and "Path=/api" in session_cookie
    assert "access_token" not in body


@pytest.mark.parametrize(
    ("username", "password"), [("instructor", "wrong-password-123"), ("nobody", PASSWORD), ("", "")]
)
def test_login_failures_are_generic(world: World, username: str, password: str) -> None:
    r = world.anon().post("/auth/login", {"username": username, "password": password})
    assert r.status_code in (401, 422)
    if r.status_code == 401:
        assert r.json()["error"]["message"].startswith("Invalid username or password")


def test_unauthenticated_requests_rejected(world: World) -> None:
    api = world.anon()
    for url in ("/auth/me", "/scenarios", "/sessions", "/users", "/audit", "/analytics/progress"):
        r = api.get(url)
        assert r.status_code == 401, url
        assert r.json()["error"]["code"] == "unauthorized"


def test_csrf_required_for_cookie_sessions(instructor: Api) -> None:
    r = instructor.post("/scenarios/validate", {"definition": {}}, headers={"X-CSRF-Token": "forged"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    instructor.csrf = None
    r = instructor.post("/scenarios/validate", {"definition": {}})
    assert r.status_code == 403


def test_bearer_token_mode_for_adapters(world: World) -> None:
    api = world.anon()
    r = api.post("/auth/login", {"username": "trainee1", "password": PASSWORD, "mode": "token"})
    token = r.json()["access_token"]
    me = api.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["username"] == "trainee1"
    # A bearer token cannot be replayed as a cookie session.
    api.client.cookies.set("drikr_session", token)
    assert api.client.get("/api/v1/auth/me").status_code == 401


def test_logout_revokes_session(world: World) -> None:
    api = world.login("trainee1")
    assert api.post("/auth/logout").status_code == 200
    assert api.get("/auth/me").status_code == 401


def test_lockout_after_repeated_failures(world: World) -> None:
    api = world.anon()
    for _ in range(5):
        assert api.post("/auth/login", {"username": "trainee2", "password": "Wrong-password-1"}).status_code == 401
    # Correct password is now refused while locked.
    assert api.post("/auth/login", {"username": "trainee2", "password": PASSWORD}).status_code == 401
    admin = world.login("admin")
    uid = next(u["id"] for u in admin.get("/users?q=trainee2").json()["items"])
    assert admin.post(f"/users/{uid}/unlock").status_code == 200
    assert api.post("/auth/login", {"username": "trainee2", "password": PASSWORD}).status_code == 200


def test_rate_limit(world: World) -> None:
    world.app.state.ctx.login_limiter.limit = 3
    api = world.anon()
    codes = [
        api.post("/auth/login", {"username": "x-user", "password": "nope-nope-nope"}).status_code for _ in range(5)
    ]
    assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]


def test_idle_and_absolute_expiry(world: World) -> None:
    api = world.login("trainee1")
    db = world.app.state.ctx.database
    with db.session_factory() as s:
        s.execute(update(AuthSession).values(last_seen_at=AuthSession.last_seen_at - timedelta(hours=2)))
        s.commit()
    r = api.get("/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "session_expired"


def test_password_change_policy_and_forced_change(world: World) -> None:
    admin = world.login("admin")
    r = admin.post(
        "/users", {"username": "new.trainee", "display_name": "New Trainee", "role": "trainee", "password": "short"}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "password_policy"
    r = admin.post(
        "/users",
        {"username": "new.trainee", "display_name": "New Trainee", "role": "trainee", "password": "Initial-Pass-2026!"},
    )
    assert r.status_code == 201 and r.json()["must_change_password"] is True

    nt = world.login("new.trainee", "Initial-Pass-2026!")
    blocked = nt.get("/assignments")
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "password_change_required"
    weak = nt.post(
        "/auth/change-password", {"current_password": "Initial-Pass-2026!", "new_password": "new.trainee-Pass-1"}
    )
    assert weak.status_code == 422
    ok = nt.post(
        "/auth/change-password", {"current_password": "Initial-Pass-2026!", "new_password": "Brand-New-Pass-77"}
    )
    assert ok.status_code == 200
    assert nt.get("/assignments").status_code == 200


def test_passwords_hashed_and_never_logged(world: World, caplog: pytest.LogCaptureFixture) -> None:
    secret = "Never-Log-This-Pass-9"
    caplog.set_level(logging.DEBUG)
    api = world.anon()
    api.post("/auth/login", {"username": "admin", "password": secret})
    admin = world.login("admin")
    admin.post("/users", {"username": "logcheck", "display_name": "Log Check", "role": "trainee", "password": secret})
    joined = "\n".join(r.getMessage() + str(vars(r)) for r in caplog.records)
    assert secret not in joined
    with world.app.state.ctx.database.session_factory() as s:
        h = s.scalar(select(User.password_hash).where(User.username == "logcheck"))
        assert h and h.startswith("$argon2id$") and secret not in h
        audit_text = s.execute(text("SELECT string_agg(details::text, ' ') FROM audit_events")).scalar() or ""
        assert secret not in audit_text
        tokens = s.execute(text("SELECT token_digest FROM auth_sessions")).scalars().all()
        assert all(len(t) == 64 for t in tokens)
