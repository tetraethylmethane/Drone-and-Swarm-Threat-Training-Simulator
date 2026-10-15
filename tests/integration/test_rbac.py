"""Backend-enforced role isolation: every protected endpoint is checked for every role."""

from __future__ import annotations

import pytest

from tests.integration.conftest import Api, World, assign

pytestmark = pytest.mark.integration

# (method, path, body) -> roles allowed. Paths with {sid}/{aid}/{uid} are filled per test.
MATRIX = [
    ("GET", "/users", None, {"admin", "instructor"}),
    (
        "POST",
        "/users",
        {"username": "zz-user", "display_name": "Zz", "role": "trainee", "password": "Valid-Pass-2026!"},
        {"admin"},
    ),
    ("PATCH", "/users/{uid}", {"display_name": "Renamed"}, {"admin"}),
    ("GET", "/audit", None, {"admin"}),
    ("GET", "/audit/verify", None, {"admin"}),
    ("GET", "/admin/system", None, {"admin"}),
    ("GET", "/admin/settings", None, {"admin"}),
    ("POST", "/scenarios/validate", {"definition": {}}, {"instructor"}),
    ("POST", "/scenarios/generate", {"seed": 1}, {"instructor"}),
    ("GET", "/scenarios", None, {"admin", "instructor", "trainee"}),
    ("POST", "/rubrics/validate", {"definition": {}}, {"instructor"}),
    ("GET", "/rubrics", None, {"admin", "instructor"}),
    (
        "POST",
        "/assignments",
        {
            "scenario_id": "00000000-0000-0000-0000-000000000000",
            "trainee_ids": ["00000000-0000-0000-0000-000000000000"],
            "title": "x title",
            "difficulty_level": 2,
        },
        {"instructor"},
    ),
    ("GET", "/assignments", None, {"instructor", "trainee"}),
    ("POST", "/assignments/{aid}/cancel", None, {"instructor"}),
    ("POST", "/sessions", {"assignment_id": "{aid}"}, {"trainee"}),
    ("GET", "/sessions/{sid}/feed", None, {"trainee"}),
    ("POST", "/sessions/{sid}/abort", {"reason": "rbac check"}, {"admin", "instructor"}),
    ("POST", "/sessions/{sid}/verify", None, {"admin", "instructor"}),
    ("PUT", "/sessions/{sid}/review", {"status": "reviewed"}, {"instructor"}),
    ("GET", "/analytics/overview", None, {"admin", "instructor"}),
    ("GET", "/reports/sessions.csv", None, {"admin", "instructor"}),
]


@pytest.fixture
def ids(world: World, instructor: Api, trainee: Api) -> dict[str, str]:
    a = assign(instructor, trainee)
    sid = trainee.post("/sessions", {"assignment_id": a["id"]}).json()["id"]
    a2 = assign(instructor, trainee)  # unused assignment for the create-session row
    return {"aid": a2["id"], "sid": sid, "uid": trainee.user["id"]}  # type: ignore[index]


def _fill(v: object, ids: dict[str, str]) -> object:
    if isinstance(v, str):
        for k, val in ids.items():
            v = v.replace("{" + k + "}", val)
        return v
    if isinstance(v, dict):
        return {k: _fill(x, ids) for k, x in v.items()}
    return v


@pytest.mark.parametrize(("method", "path", "body", "allowed"), MATRIX, ids=[f"{m} {p}" for m, p, _, _ in MATRIX])
def test_role_matrix(
    world: World, ids: dict[str, str], method: str, path: str, body: object, allowed: set[str]
) -> None:
    url = str(_fill(path, ids))
    payload = _fill(body, ids)
    for role, username in (("admin", "admin"), ("instructor", "instructor"), ("trainee", "trainee2")):
        api = world.login(username)
        r = getattr(api, method.lower())(url, payload) if method != "GET" else api.get(url)
        if role in allowed:
            assert r.status_code not in (
                401,
                403,
            ), f"{role} should be allowed: {method} {url} -> {r.status_code} {r.text}"
        else:
            # trainee2 does not own the session: object-level checks may return 404 instead of 403.
            assert r.status_code in (403, 404), f"{role} must be denied: {method} {url} -> {r.status_code}"


def test_trainee_cannot_see_other_trainees_data(world: World, instructor: Api, trainee: Api, trainee2: Api) -> None:
    a = assign(instructor, trainee)
    sid = trainee.post("/sessions", {"assignment_id": a["id"]}).json()["id"]
    assert trainee2.get(f"/assignments/{a['id']}").status_code == 404
    assert trainee2.get(f"/sessions/{sid}").status_code == 404
    assert trainee2.get(f"/sessions/{sid}/result").status_code == 404
    assert trainee2.get(f"/sessions/{sid}/review").status_code == 404
    assert trainee2.get(f"/reports/sessions/{sid}.pdf").status_code == 404
    assert trainee2.get("/sessions").json()["total"] == 0
    other = trainee2.get(f"/analytics/progress?trainee_id={trainee.user['id']}").json()  # type: ignore[index]
    assert other["points"] == []  # scoped to the caller regardless of the filter


def test_trainee_cannot_read_ground_truth_during_exercise(world: World, instructor: Api, trainee: Api) -> None:
    a = assign(instructor, trainee, feedback_level="summary")
    sid = trainee.post("/sessions", {"assignment_id": a["id"]}).json()["id"]
    trainee.post(f"/sessions/{sid}/start")
    assert trainee.get(f"/sessions/{sid}/timeline").status_code == 403
    sc = trainee.get("/scenarios").json()["items"][0]["id"]
    assert trainee.get(f"/scenarios/{sc}/preview").status_code == 403
    assert "definition" not in trainee.get(f"/scenarios/{sc}").json()
    trainee.post(f"/sessions/{sid}/complete")
    assert trainee.get(f"/sessions/{sid}/timeline?category=ground_truth").status_code == 403
    tl = trainee.get(f"/sessions/{sid}/timeline").json()["items"]
    assert all(e["visibility"] != "ground_truth" for e in tl)
    res = trainee.get(f"/sessions/{sid}/result").json()
    assert res["feedback_level"] == "summary" and "items" not in res


def test_admin_cannot_remove_last_admin_or_self(world: World, admin: Api) -> None:
    me = admin.user["id"]  # type: ignore[index]
    r = admin.patch(f"/users/{me}", {"role": "trainee"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "self_lockout"


def test_deactivated_user_is_signed_out(world: World, admin: Api) -> None:
    t = world.login("trainee2")
    uid = t.user["id"]  # type: ignore[index]
    assert admin.patch(f"/users/{uid}", {"is_active": False}).status_code == 200
    assert t.get("/auth/me").status_code == 401
    assert (
        world.anon().post("/auth/login", {"username": "trainee2", "password": "Training-Pass-2026!"}).status_code == 401
    )
