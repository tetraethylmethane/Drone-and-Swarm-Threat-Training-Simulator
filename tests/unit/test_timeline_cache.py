"""Packed timelines and the pre-generation cache (backlog B-17)."""

from __future__ import annotations

from drikr_api.timeline_cache import TimelineCache
from drikr_contracts import Scenario
from drikr_simcore import generate_timeline
from drikr_simcore.packed import PackedTimeline, generate_packed, unpack_events
from tests.unit.helpers import DEMOS


def test_a_packed_timeline_is_exactly_the_generated_one() -> None:
    for key, definition in sorted(DEMOS.items()):
        scn = Scenario.model_validate(definition)
        direct = generate_timeline(scn, seed=11, difficulty_level=3)
        packed = generate_packed(scn.model_dump(mode="json"), 11, 3)
        assert unpack_events(packed) == direct.events, key
        assert (packed.digest, packed.engine_version, packed.event_count) == (
            direct.digest,
            direct.engine_version,
            len(direct.events),
        )
        assert len(packed.blob) < 600_000  # compact enough to keep a class's worth in memory


def _item(n: int) -> PackedTimeline:
    return PackedTimeline(f"d{n}", "e", 1, bytes(100))


def test_the_cache_is_bounded_and_drops_the_least_recently_used() -> None:
    c = TimelineCache(max_bytes=250)
    c.put("a", _item(1))
    c.put("b", _item(2))
    assert c.get("a") is not None  # "a" is now the most recently used
    c.put("c", _item(3))  # over budget: "b" goes
    assert "b" not in c and "a" in c and "c" in c
    assert c.stats()["bytes"] == 200 and c.stats()["entries"] == 2
    assert c.get("missing") is None and c.stats()["misses"] == 1


def test_a_disabled_cache_keeps_nothing() -> None:
    c = TimelineCache(max_bytes=0)
    c.put("a", _item(1))
    assert "a" not in c and c.stats()["entries"] == 0
