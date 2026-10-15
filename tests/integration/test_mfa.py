"""Multi-factor authentication: enrolment, two-step sign-in, replay and recovery, policy, resets."""

from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select, text

from drikr_api.cli import main as cli_main
from drikr_api.models import User
from drikr_api.security import totp
from tests.integration.conftest import PASSWORD, TEST_URL, Api, World

pytestmark = pytest.mark.integration


class TotpClock:
    def __init__(self) -> None:
        self.t = 1_800_000_000.0

    def code(self, secret: str) -> str:
        return totp.code_at(secret, self.t)

    def next_step(self) -> None:
        self.t += 30


@pytest.fixture
def tclock(monkeypatch: pytest.MonkeyPatch) -> TotpClock:
    c = TotpClock()
    monkeypatch.setattr(totp, "time", SimpleNamespace(time=lambda: c.t))
    return c


def enrol(api: Api, clock: TotpClock) -> tuple[str, list[str]]:
    setup = api.post("/auth/mfa/setup", {"current_password": PASSWORD})
    assert setup.status_code == 200, setup.text
    body = setup.json()
    assert base64.b64decode(body["qr_svg_base64"]).startswith(b"<svg")
    secret = body["secret"]
    r = api.post("/auth/mfa/enable", {"code": clock.code(secret)})
    assert r.status_code == 200, r.text
    return secret, r.json()["recovery_codes"]


def start_login(world: World, username: str, mode: str = "cookie") -> tuple[Api, dict[str, Any]]:
    api = world.anon()
    r = api.post("/auth/login", {"username": username, "password": PASSWORD, "mode": mode})
    assert r.status_code == 200, r.text
    return api, r.json()


def finish(api: Api, token: str, code: str) -> Any:
    r = api.post("/auth/mfa/verify", {"mfa_token": token, "code": code})
    if r.status_code == 200 and "csrf_token" in r.json():
        api.csrf = r.json()["csrf_token"]
    return r


def set_policy(admin: Api, roles: list[str]) -> Any:
    current = admin.get("/admin/settings").json()
    return admin.put("/admin/settings", {**current, "mfa_required_roles": roles})


def test_enrol_and_two_step_sign_in(world: World, instructor: Api, tclock: TotpClock) -> None:
    secret, codes = enrol(instructor, tclock)
    assert len(codes) == 10 and len(set(codes)) == 10
    status = instructor.get("/auth/mfa").json()
    assert status["enabled"] and status["recovery_codes_remaining"] == 10

    api, step1 = start_login(world, "instructor")
    assert step1["mfa_required"] is True and "user" not in step1 and "csrf_token" not in step1
    assert api.get("/auth/me").status_code == 401  # no session after the password step
    tclock.next_step()
    r = finish(api, step1["mfa_token"], tclock.code(secret))
    assert r.status_code == 200 and r.json()["user"]["mfa_enabled"] is True
    assert api.get("/scenarios").status_code == 200
    # Challenge tokens are single-use.
    assert finish(world.anon(), step1["mfa_token"], tclock.code(secret)).status_code == 401


def test_bearer_mode_for_adapters(world: World, trainee: Api, tclock: TotpClock) -> None:
    secret, _ = enrol(trainee, tclock)
    api, step1 = start_login(world, "trainee1", mode="token")
    tclock.next_step()
    r = api.post("/auth/mfa/verify", {"mfa_token": step1["mfa_token"], "code": tclock.code(secret)})
    token = r.json()["access_token"]
    assert api.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_replay_wrong_codes_and_lockout(world: World, instructor: Api, tclock: TotpClock) -> None:
    secret, _ = enrol(instructor, tclock)
    used = tclock.code(secret)  # consumed by enrolment
    api, step1 = start_login(world, "instructor")
    r = finish(api, step1["mfa_token"], used)
    assert r.status_code == 401 and r.json()["error"]["code"] == "mfa_code_invalid"  # replay
    for _ in range(4):
        finish(api, step1["mfa_token"], "000000")
    # Five failures lock the account (threshold 5) and exhaust the challenge.
    tclock.next_step()
    assert finish(api, step1["mfa_token"], tclock.code(secret)).status_code == 401
    r = world.anon().post("/auth/login", {"username": "instructor", "password": PASSWORD})
    assert r.status_code == 401  # locked
    with world.app.state.ctx.database.session_factory() as db:
        actions = db.execute(text("SELECT action FROM audit_events WHERE action LIKE 'auth.%'")).scalars().all()
    assert "auth.mfa_failed" in actions and "auth.account_locked" in actions


def test_recovery_codes_single_use(world: World, trainee: Api, tclock: TotpClock) -> None:
    _, codes = enrol(trainee, tclock)
    api, step1 = start_login(world, "trainee1")
    assert finish(api, step1["mfa_token"], codes[0].lower()).status_code == 200
    assert api.get("/auth/mfa").json()["recovery_codes_remaining"] == 9
    api2, step2 = start_login(world, "trainee1")
    assert finish(api2, step2["mfa_token"], codes[0]).status_code == 401


def test_secret_is_encrypted_at_rest(world: World, trainee: Api, tclock: TotpClock) -> None:
    secret, codes = enrol(trainee, tclock)
    with world.app.state.ctx.database.session_factory() as db:
        u = db.scalar(select(User).where(User.username == "trainee1"))
        assert u is not None and u.mfa_secret_enc and secret not in u.mfa_secret_enc
        stored = db.execute(text("SELECT string_agg(code_digest, ' ') FROM mfa_recovery_codes")).scalar() or ""
        assert all(c.replace("-", "") not in stored for c in codes)


def test_policy_requires_enrolment(world: World, admin: Api, instructor: Api, tclock: TotpClock) -> None:
    # An administrator cannot require MFA for administrators before enabling it personally.
    r = set_policy(admin, ["administrator", "instructor"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "mfa_enable_first"
    enrol(admin, tclock)
    assert set_policy(admin, ["administrator", "instructor"]).status_code == 200

    blocked = instructor.get("/scenarios")
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "mfa_enrollment_required"
    me = instructor.get("/auth/me").json()
    assert me["mfa_enrollment_required"] is True
    enrol(instructor, tclock)
    assert instructor.get("/scenarios").status_code == 200
    # Required roles cannot switch MFA off.
    tclock.next_step()
    r = instructor.post("/auth/mfa/disable", {"current_password": PASSWORD, "code": "123456"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "mfa_required_by_policy"


def test_disable_when_optional(world: World, trainee: Api, tclock: TotpClock) -> None:
    secret, _ = enrol(trainee, tclock)
    tclock.next_step()
    assert trainee.post("/auth/mfa/disable", {"current_password": PASSWORD, "code": "000000"}).status_code == 400
    r = trainee.post("/auth/mfa/disable", {"current_password": PASSWORD, "code": tclock.code(secret)})
    assert r.status_code == 200 and trainee.get("/auth/mfa").json()["enabled"] is False
    r = world.anon().post("/auth/login", {"username": "trainee1", "password": PASSWORD})
    assert r.json()["mfa_required"] is False


def test_admin_and_cli_reset(
    world: World, admin: Api, trainee: Api, tclock: TotpClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    enrol(trainee, tclock)
    uid = trainee.user["id"]  # type: ignore[index]
    r = admin.post(f"/users/{uid}/reset-mfa")
    assert r.status_code == 200 and r.json()["mfa_enabled"] is False
    assert trainee.get("/auth/me").status_code == 401  # sessions revoked
    assert (
        world.anon().post("/auth/login", {"username": "trainee1", "password": PASSWORD}).json()["mfa_required"] is False
    )

    inst = world.login("instructor")
    enrol(inst, tclock)
    monkeypatch.setenv("DRIKR_ENVIRONMENT", "test")
    monkeypatch.setenv("DRIKR_DATABASE_URL", TEST_URL)
    monkeypatch.setenv("DRIKR_SECRET_KEY", "test-secret-key-that-is-long-enough-0123456789")
    from drikr_api.config import get_settings

    get_settings.cache_clear()
    cli_main(["reset-mfa", "--username", "instructor"])
    get_settings.cache_clear()
    with world.app.state.ctx.database.session_factory() as db:
        u = db.scalar(select(User).where(User.username == "instructor"))
        assert u is not None and not u.mfa_enabled
        assert db.execute(text("SELECT count(*) FROM audit_events WHERE action = 'cli.mfa_reset'")).scalar() == 1
