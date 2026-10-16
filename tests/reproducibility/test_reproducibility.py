"""Reproducibility suite: same configuration and seed give the same events and the same scores.

Run alone with:  pytest tests/reproducibility
The digests below were confirmed identical on Windows/CPython 3.12.4 and Linux/CPython 3.12.14
(Docker image) on 2026-10-16. If an intentional engine change alters them, bump ENGINE_VERSION
(simcore) or SCORING_ENGINE_VERSION and update the values in the same commit.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from typing import Any

import pytest

from drikr_contracts import Scenario
from drikr_scoring import Rubric, load_default_rubrics, score_session
from drikr_simcore import ENGINE_VERSION, GroundTruthIndex, generate_timeline, load_demo_scenarios
from drikr_simcore.canonical import digest

pytestmark = pytest.mark.reproducibility

DEMOS = {d["key"]: d for d in load_demo_scenarios()}
RUBRIC = Rubric.model_validate(load_default_rubrics()[0])

GOLDEN = {
    "demo-degraded-picture": "435b48025d27b480eb824f83b08e89a5b8cc752ffa504af4467d512ac6daad33",
    "demo-night-loiter": "7cd9c8a503ac54d98512e7d11170dd4555c2ac078dbfd6383629c7e5c9a260f3",
    "demo-perimeter-basics": "66f645ecced4e437f60aac111aa33293ae119d1d71c03eed51d809e5410a3ec0",
    "demo-swarm-recognition": "9a54292ce3ccb508629b79badcc55253b0d23e8570d0ecad07f0ddb22b463082",
}

CASES = [
    (key, level, seed)
    for key, d in sorted(DEMOS.items())
    for level in range(d["difficulty"]["min_level"], d["difficulty"]["max_level"] + 1)
    for seed in (d["randomization"]["seed"], 7_777)
]


def scenario(key: str) -> Scenario:
    return Scenario.model_validate(DEMOS[key])


def test_engine_version_matches_golden_digests() -> None:
    assert ENGINE_VERSION == "simcore-1.0.0"
    for key, expected in GOLDEN.items():
        assert generate_timeline(scenario(key)).digest == expected, key


@pytest.mark.parametrize(("key", "level", "seed"), CASES)
def test_same_configuration_and_seed_give_identical_events(key: str, level: int, seed: int) -> None:
    a = generate_timeline(scenario(key), seed=seed, difficulty_level=level)
    b = generate_timeline(scenario(key), seed=seed, difficulty_level=level)
    assert a.digest == b.digest
    assert [(e["seq"], e["event_id"], e["type"], e["t_ms"]) for e in a.events] == [
        (e["seq"], e["event_id"], e["type"], e["t_ms"]) for e in b.events
    ]
    assert digest(a.events) == a.digest


def test_fresh_interpreters_with_different_hash_seeds_agree() -> None:
    """Guards against dict/set ordering or hash randomisation leaking into the output."""
    code = (
        "import json; from drikr_contracts import Scenario; "
        "from drikr_simcore import generate_timeline, load_demo_scenarios; "
        "print(json.dumps({d['key']: generate_timeline(Scenario.model_validate(d), difficulty_level=d['difficulty']"
        "['max_level']).digest for d in load_demo_scenarios()}))"
    )
    outputs = []
    for hash_seed in ("0", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed}
        # Fixed code string and the current interpreter: no untrusted input.
        out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)  # noqa: S603
        outputs.append(json.loads(out.stdout))
    assert outputs[0] == outputs[1]


def _scripted_decisions(events: list[dict[str, Any]], end: int) -> list[dict[str, Any]]:
    """A fixed decision pattern: classify each track 10 s after it appears, then report it."""
    idx = GroundTruthIndex(events)
    out: list[dict[str, Any]] = []
    seq = max(e["seq"] for e in events) + 1
    for n, tr in enumerate(sorted(idx.observable_tracks(end), key=lambda t: t.track_id)):
        t = min(((tr.first_available_ms or 0) + 10_000) // 100 * 100, end)
        for kind, body in (
            ("classification_submitted", {"classification": "small_multirotor", "confidence": "medium"}),
            ("response_submitted", {"response": "report_to_exercise_control"}),
        ):
            out.append(
                {
                    "event_id": f"T-{seq:06d}",
                    "seq": seq,
                    "t_ms": t,
                    "available_at_ms": t,
                    "type": kind,
                    "visibility": "trainee",
                    "origin": "trainee",
                    "payload": {
                        "client_action_id": f"00000000-0000-0000-0000-{n * 2 + len(out) % 2:012d}",
                        "track_ids": [tr.track_id],
                        **body,
                        "note": None,
                    },
                }
            )
            seq += 1
    return out


@pytest.mark.parametrize("key", sorted(DEMOS))
def test_scoring_is_deterministic_and_order_independent(key: str) -> None:
    scn = scenario(key)
    tl = generate_timeline(scn)
    events = tl.events + _scripted_decisions(tl.events, tl.duration_ms)
    first = score_session(events, scn, RUBRIC, tl.duration_ms)
    again = score_session(events, scn, RUBRIC, tl.duration_ms)
    shuffled = list(events)
    random.Random(4).shuffle(shuffled)  # storage order must not matter: events carry their sequence
    third = score_session(shuffled, scn, RUBRIC, tl.duration_ms)
    assert digest(first) == digest(again) == digest(third)
    assert first["status"] == "scored"
    # Every assessed item references recorded events.
    seqs = {e["seq"] for e in events}
    assert all(ev["seq"] in seqs for item in first["items"] for ev in item["evidence_events"])
