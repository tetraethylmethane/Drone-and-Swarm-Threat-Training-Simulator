"""Assessment traceability and verification across scoring-engine versions."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from drikr_scoring import SCORING_ENGINE_VERSION
from tests.integration.conftest import Api, FakeClock
from tests.integration.test_reports_analytics import run_exercise

pytestmark = pytest.mark.integration


def test_every_item_points_to_recorded_events(instructor: Api, trainee: Api, clock: FakeClock) -> None:
    sid = run_exercise(trainee, instructor, clock)
    result = instructor.get(f"/sessions/{sid}/result").json()
    assert result["scoring_engine_version"] == SCORING_ENGINE_VERSION
    timeline = instructor.get(f"/sessions/{sid}/timeline?category=all&limit=2000").json()["items"]
    by_seq = {e["seq"]: e for e in timeline}
    classified = [i for i in result["items"] if i["final_classification"]]
    assert classified, "the exercise should have classified at least one track"
    for item in result["items"]:
        for ev in item["evidence_events"]:
            recorded = by_seq[ev["seq"]]  # every reference resolves to a stored event
            assert recorded["event_id"] == ev["event_id"]
            assert item["track_id"] in (recorded["payload"].get("track_ids") or [recorded["payload"].get("track_id")])
            expected_type = {
                "classification": "classification_submitted",
                "response": "response_submitted",
                "sensor_confirmation": "sensor_confirmation",
            }[ev["kind"]]
            assert recorded["type"] == expected_type
        decisions = [e for e in item["evidence_events"] if e["kind"] != "sensor_confirmation"]
        assert len(decisions) == item["decisions"]
        if item["final_classification"]:
            assert decisions[-1]["value"] == item["final_classification"] or any(
                e["value"] == item["final_classification"] for e in decisions
            )


def _rewrite_stored_result(engine: Engine, sid: str, *, version: str, mutate: object) -> None:
    """Simulate a result stored by an earlier engine (privileged edit bypassing triggers)."""
    with engine.begin() as c:
        row = c.execute(text("SELECT result FROM score_results WHERE session_id = :s"), {"s": uuid.UUID(sid)}).one()
        result = dict(row.result)
        result["scoring_engine_version"] = version
        for item in result["items"]:
            item.pop("evidence_events", None)  # field added in scoring-1.2.0
        if callable(mutate):
            mutate(result)
        c.execute(text("SET LOCAL session_replication_role = replica"))
        c.execute(
            text(
                "UPDATE score_results SET result = CAST(:r AS jsonb), scoring_engine_version = :v, "
                "result_digest = :d, overall = :o WHERE session_id = :s"
            ),
            {"r": json.dumps(result), "v": version, "d": "0" * 64, "o": result["overall"], "s": uuid.UUID(sid)},
        )


def test_older_engine_result_still_verifies_when_scores_agree(
    engine: Engine, instructor: Api, trainee: Api, clock: FakeClock
) -> None:
    sid = run_exercise(trainee, instructor, clock)
    _rewrite_stored_result(engine, sid, version="scoring-1.1.0", mutate=None)
    report = instructor.post(f"/sessions/{sid}/verify").json()
    assert report["scoring_engine_version_recorded"] == "scoring-1.1.0"
    assert report["score_reproduced"] is False  # byte-for-byte output differs (new fields)
    assert report["assessment_values_match"] is True
    assert report["reproducible"] is True
    assert "same scores" in report["score_note"]
    # The stored result is shown as stored, never rewritten by the newer engine.
    stored = instructor.get(f"/sessions/{sid}/result").json()
    assert stored["scoring_engine_version"] == "scoring-1.1.0"
    assert all("evidence_events" not in i for i in stored["items"])


def test_older_engine_result_with_a_different_score_is_flagged(
    engine: Engine, instructor: Api, trainee: Api, clock: FakeClock
) -> None:
    sid = run_exercise(trainee, instructor, clock)

    def change_score(result: dict) -> None:  # type: ignore[type-arg]
        result["overall"] = round((result["overall"] or 0) + 7.5, 1)

    _rewrite_stored_result(engine, sid, version="scoring-1.1.0", mutate=change_score)
    report = instructor.post(f"/sessions/{sid}/verify").json()
    assert report["assessment_values_match"] is False
    assert report["reproducible"] is False
    assert "different assessment" in report["score_note"]
