"""AAR evidence links open the timeline page that holds the event (backlog B-06, usability U-02)."""

from __future__ import annotations

import pytest

from tests.integration.conftest import Api, FakeClock
from tests.integration.test_reports_analytics import run_exercise

pytestmark = pytest.mark.integration


def test_around_seq_returns_the_page_holding_each_evidence_event(
    instructor: Api, trainee: Api, clock: FakeClock
) -> None:
    sid = run_exercise(trainee, instructor, clock)
    items = instructor.get(f"/sessions/{sid}/result").json()["items"]
    evidence = [ev for it in items for ev in it.get("evidence_events", [])]
    assert len(evidence) >= 3
    decisions = instructor.get(f"/sessions/{sid}/timeline?category=decisions&limit=2000").json()["items"]
    order = [e["seq"] for e in decisions]
    for ev in evidence:
        page = instructor.get(f"/sessions/{sid}/timeline?category=decisions&limit=2&around_seq={ev['seq']}").json()
        assert ev["seq"] in [e["seq"] for e in page["items"]]
        assert page["offset"] == (order.index(ev["seq"]) // 2) * 2


def test_around_seq_cannot_locate_hidden_or_unknown_events(instructor: Api, trainee: Api, clock: FakeClock) -> None:
    sid = run_exercise(trainee, instructor, clock, feedback_level="summary")
    ground_truth = instructor.get(f"/sessions/{sid}/timeline?category=ground_truth&limit=1").json()["items"][0]
    # Outside the requested category, or unknown: the requested offset applies unchanged.
    for seq in (ground_truth["seq"], 999_999):
        page = trainee.get(f"/sessions/{sid}/timeline?limit=5&offset=0&around_seq={seq}").json()
        assert page["offset"] == 0
        assert all(e["visibility"] != "ground_truth" for e in page["items"])
    assert trainee.get(f"/sessions/{sid}/timeline?around_seq=-1").status_code == 422
