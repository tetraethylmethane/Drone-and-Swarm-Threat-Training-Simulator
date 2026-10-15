"""Independent, deterministic scoring engine for the Drikr Systems training simulator.

Pure Python: consumes recorded events and a versioned rubric and produces an
explained result. No database, network or model dependency.
"""

import json
from importlib import resources
from typing import Any

from drikr_scoring.adaptive import AdaptivePolicy, Recommendation, SessionOutcome, recommend_level
from drikr_scoring.engine import SCORING_ENGINE_VERSION, evaluate_tree, score_session
from drikr_scoring.rubric import DIMENSIONS, Rubric


def load_default_rubrics() -> list[dict[str, Any]]:
    folder = resources.files("drikr_scoring") / "default_rubrics"
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(folder.iterdir(), key=lambda p: p.name)
        if p.name.endswith(".json")
    ]


__all__ = [
    "DIMENSIONS",
    "SCORING_ENGINE_VERSION",
    "AdaptivePolicy",
    "Recommendation",
    "Rubric",
    "SessionOutcome",
    "evaluate_tree",
    "load_default_rubrics",
    "recommend_level",
    "score_session",
]
