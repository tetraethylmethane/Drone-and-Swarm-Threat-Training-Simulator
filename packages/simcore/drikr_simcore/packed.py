"""Timelines in a compact, transferable form (backlog B-17).

A generated timeline is about 3,900 event dictionaries. Sending it between processes, or keeping
it for later, as Python objects is costly in time and memory. ``generate_packed`` returns it as
compressed JSON instead (about 0.3 MB), with the digest, engine version and event count, and
``unpack_events`` restores the exact event list. Generation itself is unchanged.
"""

from __future__ import annotations

import json
import zlib
from typing import Any, NamedTuple

from drikr_contracts import Scenario
from drikr_simcore.generator import generate_timeline


class PackedTimeline(NamedTuple):
    digest: str
    engine_version: str
    event_count: int
    blob: bytes


def generate_packed(definition: dict[str, Any], seed: int, difficulty_level: int) -> PackedTimeline:
    """Generate the timeline for a scenario definition (as stored JSON) and pack it."""
    tl = generate_timeline(Scenario.model_validate(definition), seed=seed, difficulty_level=difficulty_level)
    blob = zlib.compress(json.dumps(tl.events, separators=(",", ":")).encode("utf-8"), 6)
    return PackedTimeline(tl.digest, tl.engine_version, len(tl.events), blob)


def unpack_events(packed: PackedTimeline) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = json.loads(zlib.decompress(packed.blob))
    return events
