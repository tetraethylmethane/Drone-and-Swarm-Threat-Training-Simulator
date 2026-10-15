"""Shared helpers for unit tests: build session event logs with scripted trainee behaviour."""

from __future__ import annotations

import copy
import uuid
from collections.abc import Callable
from typing import Any

from drikr_contracts import Scenario
from drikr_scoring import Rubric, load_default_rubrics
from drikr_simcore import GroundTruthIndex, generate_timeline, load_demo_scenarios
from drikr_simcore.generator import Timeline

DEMOS = {d["key"]: d for d in load_demo_scenarios()}


def demo(key: str = "demo-perimeter-basics") -> dict[str, Any]:
    return copy.deepcopy(DEMOS[key])


def scenario(key: str = "demo-perimeter-basics") -> Scenario:
    return Scenario.model_validate(demo(key))


def rubric(**overrides: Any) -> Rubric:
    data = copy.deepcopy(load_default_rubrics()[0])
    data.update(overrides)
    return Rubric.model_validate(data)


def _action_id(*parts: object) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "|".join(str(p) for p in parts)))


Policy = Callable[[str, dict[str, Any]], list[dict[str, Any]]]


def build_session(
    scn: Scenario,
    policy: Policy,
    *,
    seed: int | None = None,
    level: int | None = None,
) -> tuple[list[dict[str, Any]], Timeline, int]:
    """Return (events, timeline, end_ms) where trainee events come from ``policy``.

    ``policy(track_id, info)`` returns a list of decision dicts with keys
    ``delay_s`` (after first availability), ``kind`` and the action fields.
    """
    tl = generate_timeline(scn, seed=seed, difficulty_level=level)
    idx = GroundTruthIndex(tl.events)
    events = [dict(e) for e in tl.events]
    seq = len(events)
    end_ms = tl.duration_ms
    trainee: list[tuple[int, dict[str, Any]]] = []
    for tid, tr in sorted(idx.tracks.items()):
        if tr.first_available_ms is None:
            continue
        ent = idx.entities[tr.entity_id]
        info = {"entity": ent, "track": tr, "first_available_ms": tr.first_available_ms}
        for n, d in enumerate(policy(tid, info)):
            t_ms = tr.first_available_ms + int(d["delay_s"] * 1000)
            t_ms = (t_ms // 100) * 100
            if t_ms > end_ms:
                continue
            aid = _action_id(tid, n)
            if d["kind"] == "classify":
                payload = {
                    "client_action_id": aid,
                    "track_ids": [tid],
                    "classification": d["classification"],
                    "confidence": d.get("confidence", "high"),
                    "note": None,
                }
                etype = "classification_submitted"
            else:
                payload = {"client_action_id": aid, "track_ids": [tid], "response": d["response"], "note": None}
                etype = "response_submitted"
            trainee.append((t_ms, {"type": etype, "payload": payload}))
    for t_ms, ev in sorted(trainee, key=lambda x: (x[0], x[1]["payload"]["client_action_id"])):
        events.append(
            {
                "event_id": f"T-{seq:06d}",
                "seq": seq,
                "t_ms": t_ms,
                "available_at_ms": t_ms,
                "visibility": "trainee",
                "origin": "trainee",
                **ev,
            }
        )
        seq += 1
    return events, tl, end_ms


def expected_response(ent: Any) -> str:
    if ent.entity_class == "bird_or_clutter":
        return "log_as_cleared"
    if ent.entity_class == "coordinated_swarm":
        return "report_to_exercise_control"
    if ent.cooperative:
        return "continue_monitoring"
    return "report_to_exercise_control"


def perfect_policy(tid: str, info: dict[str, Any]) -> list[dict[str, Any]]:
    """Ground-truth oracle: classifies correctly at low confidence and responds per rubric.

    Low confidence keeps the uncertainty dimension at full credit; clearing waits
    for confirmation and enough observations to satisfy procedure rules.
    """
    ent = info["entity"]
    resp = expected_response(ent)
    decisions: list[dict[str, Any]] = [
        {"delay_s": 2, "kind": "respond", "response": "request_sensor_confirmation"},
        {"delay_s": 5, "kind": "classify", "classification": ent.entity_class, "confidence": "low"},
    ]
    if resp == "log_as_cleared":
        decisions.append({"delay_s": 15, "kind": "respond", "response": resp})
    else:
        decisions.append({"delay_s": 8, "kind": "respond", "response": resp})
    return decisions


def idle_policy(tid: str, info: dict[str, Any]) -> list[dict[str, Any]]:
    return []
