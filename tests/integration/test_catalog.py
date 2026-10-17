"""Scenario and rubric catalogue: validation, immutable versioning and procedural generation."""

from __future__ import annotations

import copy

import pytest

from tests.integration.conftest import Api, World, assign, scenario_id
from tests.unit.helpers import demo

pytestmark = pytest.mark.integration


def _new_definition(key: str = "inst-custom") -> dict:
    d = demo()
    d["key"] = key
    d["name"] = "Instructor custom exercise"
    d["description"] = "Custom training exercise created in an integration test."
    return d


def test_validate_reports_structured_issues(instructor: Api) -> None:
    d = _new_definition()
    d["entities"][0]["speed_mps"] = {"min": 30, "max": 10}
    r = instructor.post("/scenarios/validate", {"definition": d}).json()
    assert r["valid"] is False
    assert r["issues"][0]["path"].startswith("entities.0.speed_mps")
    ok = instructor.post(
        "/scenarios/validate", {"definition": _new_definition(), "seed": 9, "difficulty_level": 4}
    ).json()
    assert ok["valid"] is True and ok["preview"]["seed"] == 9 and ok["preview"]["difficulty_level"] == 4


def test_missing_rubric_reference_rejected(instructor: Api) -> None:
    d = _new_definition()
    d["scoring"] = {"rubric_key": "does-not-exist", "rubric_version": 1}
    r = instructor.post("/scenarios/validate", {"definition": d}).json()
    assert not r["valid"] and any(i["code"] == "rubric_not_found" for i in r["issues"])
    assert instructor.post("/scenarios", {"definition": d}).status_code == 422


def test_versioning_never_overwrites_history(world: World, instructor: Api, trainee: Api) -> None:
    created = instructor.post("/scenarios", {"definition": _new_definition()})
    assert created.status_code == 201
    v1 = created.json()
    assert v1["version"] == 1
    assert instructor.post("/scenarios", {"definition": _new_definition()}).json()["error"]["code"] == "key_exists"

    a = assign(instructor, trainee, "inst-custom")
    sid = trainee.post("/sessions", {"assignment_id": a["id"]}).json()["id"]

    original_s = v1["definition"]["time_limits"]["duration_s"]
    d2 = _new_definition()
    d2["time_limits"]["duration_s"] = original_s + 60  # a real change, whatever the demo duration is
    v2 = instructor.post("/scenarios/key/inst-custom/versions", {"definition": d2}).json()
    assert v2["version"] == 2 and v2["id"] != v1["id"]
    again = instructor.get(f"/scenarios/{v1['id']}").json()
    assert again["definition"]["time_limits"]["duration_s"] == original_s and again["digest"] == v1["digest"]
    assert [v["version"] for v in again["versions"]] == [1, 2]
    # Existing session still references version 1.
    s = trainee.get(f"/sessions/{sid}").json()
    assert s["scenario"]["version"] == 1 and s["duration_ms"] == original_s * 1000
    # Listing shows only the latest version.
    listed = [x for x in instructor.get("/scenarios").json()["items"] if x["key"] == "inst-custom"]
    assert len(listed) == 1 and listed[0]["version"] == 2 and listed[0]["version_count"] == 2

    mismatch = instructor.post("/scenarios/key/other-key/versions", {"definition": d2})
    assert mismatch.status_code == 422


def test_archived_scenarios_cannot_be_assigned(instructor: Api, trainee: Api) -> None:
    sid = scenario_id(instructor, "demo-night-loiter")
    assert instructor.post(f"/scenarios/{sid}/archive").json()["status"] == "archived"
    r = instructor.post(
        "/assignments",
        {
            "scenario_id": sid,
            "trainee_ids": [trainee.user["id"]],
            "title": "Archived",
            "difficulty_level": 3,
            "min_level": 2,
            "max_level": 5,
        },
    )  # type: ignore[index]
    assert r.status_code == 409 and r.json()["error"]["code"] == "scenario_archived"
    assert instructor.post(f"/scenarios/{sid}/restore").json()["status"] == "published"


def test_assignment_bounds_follow_scenario(instructor: Api, trainee: Api) -> None:
    sid = scenario_id(instructor, "demo-perimeter-basics")  # scenario bounds 1..4
    body = {
        "scenario_id": sid,
        "trainee_ids": [trainee.user["id"]],
        "title": "Too hard",
        "difficulty_level": 5,
        "min_level": 1,
        "max_level": 5,
    }  # type: ignore[index]
    r = instructor.post("/assignments", body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "difficulty_out_of_bounds"
    body.update(difficulty_level=2, max_level=4, trainee_ids=[instructor.user["id"]])  # type: ignore[index]
    r = instructor.post("/assignments", body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_trainees"


def test_procedural_generation_returns_valid_unsaved_draft(instructor: Api) -> None:
    r = instructor.post(
        "/scenarios/generate", {"seed": 31337, "preset": "urban-night-clear", "include_swarm": True}
    ).json()
    d = r["definition"]
    assert r["saved"] is False and d["environment"]["time_of_day"] == "night"
    assert any(g["entity_class"] == "coordinated_swarm" for g in d["entities"])
    assert instructor.post("/scenarios/validate", {"definition": d}).json()["valid"] is True
    again = instructor.post(
        "/scenarios/generate", {"seed": 31337, "preset": "urban-night-clear", "include_swarm": True}
    ).json()
    assert again["definition"] == d
    assert instructor.post("/scenarios/generate", {"seed": 1, "preset": "moon-base"}).status_code == 422


def test_preview_shows_ground_truth_to_instructors(instructor: Api) -> None:
    sid = scenario_id(instructor, "demo-swarm-recognition")
    p = instructor.get(f"/scenarios/{sid}/preview?seed=5&difficulty_level=4").json()
    assert p["summary"]["seed"] == 5 and p["summary"]["difficulty_level"] == 4
    assert any(e["entity_class"] == "coordinated_swarm" for e in p["entities"])


def test_rubric_versioning_and_validation(instructor: Api) -> None:
    rub = instructor.get("/rubrics").json()["items"][0]
    full = instructor.get(f"/rubrics/{rub['id']}").json()["definition"]
    bad = copy.deepcopy(full)
    bad["weights"]["recognition"] = 0.9
    v = instructor.post("/rubrics/validate", {"definition": bad}).json()
    assert not v["valid"] and "sum to 1.0" in v["issues"][0]["message"]
    good = copy.deepcopy(full)
    good["weights"] = {
        "recognition": 0.4,
        "timing": 0.1,
        "consistency": 0.2,
        "uncertainty": 0.1,
        "objectives": 0.1,
        "procedure": 0.1,
    }
    r2 = instructor.post(f"/rubrics/key/{full['key']}/versions", {"definition": good}).json()
    assert r2["version"] == 2 and r2["weights"]["recognition"] == 0.4
    original = instructor.get(f"/rubrics/{rub['id']}").json()
    assert original["weights"]["recognition"] == 0.3 and len(original["versions"]) == 2
