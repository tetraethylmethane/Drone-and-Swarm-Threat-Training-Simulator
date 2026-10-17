"""Regression tests for the "Perimeter basics" reliability defect (see docs/testing/perimeter-basics-report.md).

Defect: version 1 produced about 4.4 assessable tracks per session, so one session was not a
reliable individual measure (retest ICC 0.72 to 0.79 across five synthetic samples; 0.62 in an
earlier single sample). Version 2 adds assessable tracks while staying an introductory exercise.
These tests reproduce the defect on the archived version 1 and check the fix on version 2.
"""

from __future__ import annotations

import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from drikr_contracts import Scenario
from drikr_scoring import stats
from drikr_simcore import GroundTruthIndex, generate_timeline, load_demo_scenarios
from drikr_simcore.rng import Rng
from drikr_simcore.validation import generation_checks, validate_definition

pytestmark = pytest.mark.reproducibility

ROOT = Path(__file__).resolve().parents[2]
V1 = json.loads((ROOT / "tests/fixtures/scenarios/demo-perimeter-basics-v1.json").read_text(encoding="utf-8"))
V2 = next(d for d in load_demo_scenarios() if d["key"] == "demo-perimeter-basics")
V1_GOLDEN = "66f645ecced4e437f60aac111aa33293ae119d1d71c03eed51d809e5410a3ec0"
MIN_TRACKS = 7
RELIABILITY = 0.80


def _tracks(definition: dict[str, Any], seed: int, level: int) -> int:
    tl = generate_timeline(Scenario.model_validate(definition), seed=seed, difficulty_level=level)
    return len(GroundTruthIndex(tl.events).observable_tracks(tl.duration_ms))


def test_version_2_is_valid_and_versioned() -> None:
    assert V2["version"] == 2 and V1["version"] == 1
    report = validate_definition(V2)
    assert report.valid, report.issues
    assert generation_checks(Scenario.model_validate(V2)) == []


def test_archived_version_1_still_reproduces_its_golden_digest() -> None:
    """Sessions recorded on version 1 stay verifiable after the fix."""
    assert generate_timeline(Scenario.model_validate(V1)).digest == V1_GOLDEN


def test_version_2_gives_enough_assessable_tracks_for_every_seed_and_level() -> None:
    lo, hi = V2["difficulty"]["min_level"], V2["difficulty"]["max_level"]
    counts = [_tracks(V2, seed, level) for seed in range(0, 200, 5) for level in range(lo, hi + 1)]
    assert min(counts) >= MIN_TRACKS, f"fewest tracks {min(counts)}"
    # The defect, reproduced on version 1: never more than 5 tracks.
    assert max(_tracks(V1, seed, 2) for seed in range(0, 200, 5)) <= 5


def _play(args: tuple[dict[str, Any], int, int, float, int]) -> tuple[int, int, float | None]:
    sys.path.insert(0, str(ROOT / "research/assessment_validation"))
    import run_validation as v  # synthetic agent model; documented in docs/research/assessment-validation.md

    definition, sample, agent, skill, rep = args
    job = v.Job(
        definition["key"],
        40_000 + sample * 1000 + agent * 10 + rep,
        definition["difficulty"]["level"],
        skill,
        7_000_000 + sample * 100_000 + agent * 10 + rep,
    )
    return agent, rep, v.play(job, definition)["overall"]


def _retest_icc(definition: dict[str, Any], sample: int, agents: int = 60) -> tuple[float, float]:
    rng = Rng.stream(20261016 + sample, "agents")
    skills = [round(rng.uniform(0, 1), 3) for _ in range(agents)]
    jobs = [(definition, sample, a, s, rep) for a, s in enumerate(skills) for rep in (0, 1)]
    with ProcessPoolExecutor(max_workers=max(1, min(8, (os.cpu_count() or 2) - 1))) as ex:
        rows = list(ex.map(_play, jobs, chunksize=6))
    by: dict[int, dict[int, float | None]] = {}
    for agent, rep, overall in rows:
        by.setdefault(agent, {})[rep] = overall
    pairs = [(x[0], x[1]) for x in by.values() if x[0] is not None and x[1] is not None]
    sem = stats.sd([b - a for a, b in pairs]) / math.sqrt(2)
    return stats.icc_a1(pairs), sem


@pytest.mark.slow
@pytest.mark.parametrize("sample", [0, 1])
def test_one_session_is_a_reliable_measure_in_version_2_but_not_version_1(sample: int) -> None:
    icc_v2, sem_v2 = _retest_icc(V2, sample)
    icc_v1, sem_v1 = _retest_icc(V1, sample)
    assert icc_v2 >= RELIABILITY, f"version 2 retest ICC {icc_v2:.3f}"
    assert icc_v1 < RELIABILITY, f"version 1 retest ICC {icc_v1:.3f} (the defect should reproduce)"
    assert sem_v2 < sem_v1
