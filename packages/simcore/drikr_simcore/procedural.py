"""Procedural scenario generation.

Builds a complete, valid scenario definition from a seed and a few constraints.
The output is a *draft* for an instructor to review and save; it passes both
validation layers before it is returned.
"""

from __future__ import annotations

from typing import Any

from drikr_simcore.presets import ENVIRONMENT_PRESETS
from drikr_simcore.rng import Rng
from drikr_simcore.validation import validate_definition

MAX_ATTEMPTS = 12


class ProceduralGenerationError(RuntimeError):
    pass


def _rng_range(rng: Rng, lo: float, hi: float, width: float) -> dict[str, float]:
    a = round(rng.uniform(lo, hi - width), 0)
    return {"min": a, "max": round(a + width, 0)}


def generate_scenario_definition(
    seed: int,
    *,
    preset: str | None = None,
    include_swarm: bool | None = None,
    duration_s: int = 300,
    difficulty_level: int = 3,
    rubric_key: str = "standard-assessment",
    rubric_version: int = 1,
) -> dict[str, Any]:
    if preset is not None and preset not in ENVIRONMENT_PRESETS:
        raise ProceduralGenerationError(f"unknown preset '{preset}'")
    last_errors: list[str] = []
    for attempt in range(MAX_ATTEMPTS):
        rng = Rng.stream(seed, "procedural", attempt)
        definition = _draft(rng, seed, preset, include_swarm, duration_s, difficulty_level, rubric_key, rubric_version)
        report = validate_definition(definition)
        if report.valid and report.scenario is not None:
            # Return the canonical form with every default made explicit, so editors and
            # reviewers see exactly what will run.
            return report.scenario.model_dump(mode="json")
        last_errors = [f"{i.path}: {i.message}" for i in report.issues if i.severity == "error"]
    raise ProceduralGenerationError("could not produce a valid scenario: " + "; ".join(last_errors[:3]))


def _draft(
    rng: Rng,
    seed: int,
    preset: str | None,
    include_swarm: bool | None,
    duration_s: int,
    level: int,
    rubric_key: str,
    rubric_version: int,
) -> dict[str, Any]:
    preset_key = preset or rng.choice(sorted(ENVIRONMENT_PRESETS))
    p = ENVIRONMENT_PRESETS[preset_key]
    swarm = rng.chance(0.4) if include_swarm is None else include_swarm
    latest_spawn = max(30.0, duration_s * 0.55)

    sensors: dict[str, dict[str, Any]] = {"radar": {}, "electro_optical": {}, "rf": {}}
    for k, v in p["sensor_overrides"].items():
        sensors[k].update(v)

    groups: list[dict[str, Any]] = [
        {
            "id": "intruder",
            "label": "Non-cooperative multirotor",
            "entity_class": "small_multirotor",
            "behavior": rng.choice(["loiter", "hover", "orbit"]),
            "cooperative": False,
            "count": {"min": 1, "max": 2},
            "spawn_time_s": _rng_range(rng, 0, latest_spawn, 30),
            "speed_mps": {"min": 8, "max": 14},
            "altitude_m": {"min": 40, "max": 120},
            "closest_approach_m": {"min": 300, "max": 900},
            "dwell_s": {"min": 60, "max": 120},
        },
        {
            "id": "survey",
            "label": "Cooperative survey aircraft",
            "entity_class": rng.choice(["fixed_wing_uas", "small_multirotor"]),
            "behavior": "transit",
            "cooperative": True,
            "count": {"min": 1, "max": 1},
            "spawn_time_s": _rng_range(rng, 0, latest_spawn, 20),
            "speed_mps": {"min": 15, "max": 22},
            "altitude_m": {"min": 80, "max": 200},
            "closest_approach_m": {"min": 400, "max": 1500},
        },
        {
            "id": "birds",
            "label": "Bird activity",
            "entity_class": "bird_or_clutter",
            "behavior": "erratic",
            "cooperative": False,
            "count": {"min": 1, "max": 3},
            "spawn_time_s": _rng_range(rng, 0, latest_spawn, 30),
            "speed_mps": {"min": 5, "max": 12},
            "altitude_m": {"min": 15, "max": 80},
            "closest_approach_m": {"min": 300, "max": 1500},
        },
    ]
    objectives: list[dict[str, Any]] = [
        {
            "id": "no-false-clear",
            "description": "Do not log a non-cooperative virtual drone as cleared.",
            "criterion": {"kind": "no_false_clearance"},
        },
        {
            "id": "classify-most",
            "description": "Classify at least 80% of observed tracks.",
            "criterion": {"kind": "classify_all", "min_fraction": 0.8},
        },
    ]
    if swarm:
        groups.append(
            {
                "id": "swarm",
                "label": "Coordinated swarm",
                "entity_class": "coordinated_swarm",
                "behavior": rng.choice(["transit", "orbit"]),
                "cooperative": False,
                "count": {"min": 1, "max": 1},
                "spawn_time_s": _rng_range(rng, 10, latest_spawn, 20),
                "speed_mps": {"min": 10, "max": 16},
                "altitude_m": {"min": 60, "max": 150},
                "closest_approach_m": {"min": 400, "max": 900},
                "dwell_s": {"min": 60, "max": 90},
                "swarm": {
                    "size": {"min": 4, "max": 8},
                    "formation": rng.choice(["cluster", "wedge", "line"]),
                    "spacing_m": 30,
                },
            }
        )
        objectives.append(
            {
                "id": "report-swarm",
                "description": "Report the coordinated swarm to exercise control "
                "within 90 seconds of first observation.",
                "criterion": {
                    "kind": "respond_within",
                    "entity_class": "coordinated_swarm",
                    "response": "report_to_exercise_control",
                    "within_s": 90,
                },
            }
        )

    events: list[dict[str, Any]] = []
    if rng.chance(0.5):
        at = round(rng.uniform(duration_s * 0.3, duration_s * 0.6), 0)
        events = [
            {
                "type": "sensor_degraded",
                "id": "eo-degrade",
                "at_s": at,
                "sensor": "electro_optical",
                "detection_factor": 0.5,
                "noise_factor": 1.5,
            },
            {
                "type": "sensor_restored",
                "id": "eo-restore",
                "at_s": min(duration_s - 10, at + 60),
                "sensor": "electro_optical",
            },
        ]

    return {
        "schema_version": "1.0",
        "key": f"generated-{seed % 1_000_000:06d}",
        "version": 1,
        "name": f"Generated exercise {seed % 1_000_000:06d} ({p['label']})",
        "description": "Procedurally generated training scenario. Review objectives and entities before assigning.",
        "briefing": "Monitor the simulated sensor picture around the protected virtual site. "
        "Classify each track and choose the appropriate training response.",
        "learning_objectives": objectives,
        "environment": p["environment"],
        "sensors": sensors,
        "entities": groups,
        "event_schedule": events,
        "randomization": {"seed": seed % (2**53), "allow_seed_override": True},
        "difficulty": {"level": level, "adaptive_allowed": True, "min_level": 1, "max_level": 5},
        "scoring": {"rubric_key": rubric_key, "rubric_version": rubric_version},
        "time_limits": {"duration_s": duration_s, "allow_pause": True},
        "self_guided": False,
    }
