"""Difficulty levels and the modifiers they apply to an authored scenario.

Level 3 runs the scenario exactly as authored. Lower levels make simulated
sensors more reliable; higher levels add noise, latency, missed detections and
radar clutter tracks. The table is versioned with the engine.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DifficultyModifiers:
    level: int
    detection_mult: float
    noise_mult: float
    latency_add_s: float
    extra_clutter_per_min: float
    eo_accuracy_mult: float
    description: str

    def as_dict(self) -> dict[str, float | int | str]:
        return asdict(self)


DIFFICULTY_TABLE: dict[int, DifficultyModifiers] = {
    1: DifficultyModifiers(1, 1.15, 0.6, 0.0, 0.0, 1.15, "Foundation: reliable sensors, low noise"),
    2: DifficultyModifiers(2, 1.07, 0.8, 0.0, 0.0, 1.07, "Developing: slightly improved sensor quality"),
    3: DifficultyModifiers(3, 1.00, 1.0, 0.0, 0.0, 1.00, "Standard: scenario as authored"),
    4: DifficultyModifiers(4, 0.90, 1.3, 0.5, 0.5, 0.90, "Advanced: more noise, delay and clutter"),
    5: DifficultyModifiers(5, 0.80, 1.6, 1.0, 1.0, 0.80, "Expert: degraded sensors and heavy clutter"),
}


def modifiers_for(level: int) -> DifficultyModifiers:
    if level not in DIFFICULTY_TABLE:
        raise ValueError(f"difficulty level must be 1..5, got {level}")
    return DIFFICULTY_TABLE[level]
