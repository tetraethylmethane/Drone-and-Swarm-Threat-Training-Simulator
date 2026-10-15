"""Environment presets offered in the scenario editor.

Each preset sets environment conditions and suggests simulated sensor-quality
adjustments. All values are synthetic training parameters, not measured data.
"""

from __future__ import annotations

from typing import Any

ENVIRONMENT_PRESETS: dict[str, dict[str, Any]] = {
    "rural-day-clear": {
        "label": "Rural, daytime, clear",
        "environment": {
            "terrain": "rural",
            "time_of_day": "day",
            "weather": "clear",
            "visibility_km": 15,
            "wind_mps": 3,
        },
        "sensor_overrides": {},
    },
    "urban-day-haze": {
        "label": "Urban, daytime, haze",
        "environment": {"terrain": "urban", "time_of_day": "day", "weather": "haze", "visibility_km": 6, "wind_mps": 4},
        "sensor_overrides": {"radar": {"position_noise_m": 35, "clutter_tracks_per_min": 0.5}},
    },
    "urban-night-clear": {
        "label": "Urban, night, clear",
        "environment": {
            "terrain": "urban",
            "time_of_day": "night",
            "weather": "clear",
            "visibility_km": 10,
            "wind_mps": 2,
        },
        "sensor_overrides": {"electro_optical": {"classification_accuracy": 0.7}},
    },
    "coastal-dusk-clear": {
        "label": "Coastal, dusk, clear",
        "environment": {
            "terrain": "coastal",
            "time_of_day": "dusk",
            "weather": "clear",
            "visibility_km": 12,
            "wind_mps": 7,
        },
        "sensor_overrides": {"radar": {"clutter_tracks_per_min": 1.0}},
    },
    "industrial-day-rain": {
        "label": "Industrial, daytime, rain",
        "environment": {
            "terrain": "industrial",
            "time_of_day": "day",
            "weather": "rain",
            "visibility_km": 5,
            "wind_mps": 6,
        },
        "sensor_overrides": {"radar": {"position_noise_m": 45}, "electro_optical": {"detection_probability": 0.65}},
    },
    "rural-night-fog": {
        "label": "Rural, night, fog",
        "environment": {
            "terrain": "rural",
            "time_of_day": "night",
            "weather": "fog",
            "visibility_km": 1.2,
            "wind_mps": 1,
        },
        "sensor_overrides": {"electro_optical": {"detection_probability": 0.55}},
    },
}
