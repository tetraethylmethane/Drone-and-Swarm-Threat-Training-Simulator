"""Index over a recorded event log for ground-truth lookups.

Used by the runtime (sensor confirmation requests), the scoring engine and the
after-action review. It only reads recorded events; it never consults live
simulation state, so a session can be replayed from its stored log alone.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EntityRecord:
    entity_id: str
    entity_class: str
    behavior: str
    cooperative: bool
    group_id: str
    swarm_id: str | None
    spawn_ms: int
    exit_ms: int | None = None
    state_times: list[int] = field(default_factory=list)
    states: list[dict[str, Any]] = field(default_factory=list)

    def active_at(self, t_ms: int) -> bool:
        return self.spawn_ms <= t_ms and (self.exit_ms is None or t_ms < self.exit_ms)

    def state_at(self, t_ms: int) -> dict[str, Any] | None:
        i = bisect.bisect_right(self.state_times, t_ms) - 1
        return self.states[i] if i >= 0 else None

    @property
    def closest_range_m(self) -> float | None:
        return min((s["range_m"] for s in self.states), default=None)


@dataclass
class TrackRecord:
    track_id: str
    entity_id: str
    first_observed_ms: int | None = None  # simulation time of first observation
    first_available_ms: int | None = None  # when the trainee could first see it
    observations: list[dict[str, Any]] = field(default_factory=list)

    def visible_observations(self, until_ms: int) -> list[dict[str, Any]]:
        return [o for o in self.observations if o["available_at_ms"] <= until_ms]


class GroundTruthIndex:
    def __init__(self, events: Iterable[Mapping[str, Any]]) -> None:
        self.entities: dict[str, EntityRecord] = {}
        self.tracks: dict[str, TrackRecord] = {}
        self.track_by_entity: dict[str, str] = {}
        for ev in events:
            etype = ev["type"]
            p = ev["payload"]
            if etype == "entity_spawned":
                self.entities[p["entity_id"]] = EntityRecord(
                    entity_id=p["entity_id"],
                    entity_class=p["entity_class"],
                    behavior=p["behavior"],
                    cooperative=p["cooperative"],
                    group_id=p["group_id"],
                    swarm_id=p.get("swarm_id"),
                    spawn_ms=ev["t_ms"],
                )
            elif etype == "entity_state":
                rec = self.entities[p["entity_id"]]
                rec.state_times.append(ev["t_ms"])
                rec.states.append(dict(p))
            elif etype == "entity_exited":
                self.entities[p["entity_id"]].exit_ms = ev["t_ms"]
            elif etype == "track_assigned":
                self.tracks[p["track_id"]] = TrackRecord(track_id=p["track_id"], entity_id=p["entity_id"])
                self.track_by_entity[p["entity_id"]] = p["track_id"]
            elif etype == "track_observation":
                tr = self.tracks[p["track_id"]]
                obs = {"t_ms": ev["t_ms"], "available_at_ms": ev["available_at_ms"], **p}
                tr.observations.append(obs)
                if tr.first_observed_ms is None or ev["t_ms"] < tr.first_observed_ms:
                    tr.first_observed_ms = ev["t_ms"]
                if tr.first_available_ms is None or ev["available_at_ms"] < tr.first_available_ms:
                    tr.first_available_ms = ev["available_at_ms"]

    def entity_for_track(self, track_id: str) -> EntityRecord | None:
        tr = self.tracks.get(track_id)
        return self.entities.get(tr.entity_id) if tr else None

    def observable_tracks(self, until_ms: int) -> list[TrackRecord]:
        """Tracks the trainee could have seen at least once before ``until_ms``."""
        return [
            t for t in self.tracks.values() if t.first_available_ms is not None and t.first_available_ms <= until_ms
        ]
