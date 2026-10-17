"""Sessions list sorted by score on the server (backlog B-07, usability finding U-03).

The list is paginated, so sorting must happen before paging: the first page of "lowest score first"
must hold the lowest score of all sessions, not only of the current page.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration.conftest import Api, FakeClock
from tests.integration.test_reports_analytics import run_exercise

pytestmark = pytest.mark.integration


def _scores(items: list[dict[str, Any]]) -> list[float | None]:
    return [i["result"]["overall"] if i.get("result") else None for i in items]


def test_sorting_by_score_spans_pages_and_puts_unscored_last(
    instructor: Api, trainee: Api, trainee2: Api, clock: FakeClock
) -> None:
    # Different decisions give different scores; one session stays unscored (still running).
    for api, classify in ((trainee, "small_multirotor"), (trainee, "bird_or_clutter"), (trainee2, None)):
        run_exercise(api, instructor, clock, classify=classify)
    running = trainee2.post(
        "/sessions",
        {"scenario_id": trainee2.get("/scenarios").json()["items"][0]["id"], "selection": {}},
    ).json()["id"]
    trainee2.post(f"/sessions/{running}/start")

    everything = _scores(instructor.get("/sessions?limit=200").json()["items"])
    scored = sorted(x for x in everything if x is not None)
    assert len(scored) == 3 and None in everything and len(set(scored)) > 1

    asc = instructor.get("/sessions?sort=score_asc&limit=200").json()["items"]
    assert _scores(asc) == [*scored, None]
    desc = instructor.get("/sessions?sort=score_desc&limit=200").json()["items"]
    assert _scores(desc) == [*reversed(scored), None]
    # One per page: the first page is the lowest score overall, the last page the unscored session.
    assert _scores(instructor.get("/sessions?sort=score_asc&limit=1&offset=0").json()["items"]) == [scored[0]]
    assert instructor.get("/sessions?sort=score_asc&limit=1&offset=3").json()["items"][0]["id"] == running
    # Filters still apply, and the default order is unchanged (newest first).
    mine = instructor.get(f"/sessions?sort=score_asc&trainee_id={trainee.user['id']}").json()["items"]  # type: ignore[index]
    assert {i["trainee"]["id"] for i in mine} == {trainee.user["id"]}  # type: ignore[index]
    newest = instructor.get("/sessions").json()["items"]
    assert [i["created_at"] for i in newest] == sorted((i["created_at"] for i in newest), reverse=True)
    assert instructor.get("/sessions?sort=random").status_code == 422
