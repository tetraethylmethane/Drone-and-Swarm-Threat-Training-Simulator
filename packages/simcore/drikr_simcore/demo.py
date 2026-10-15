"""Access to the bundled demonstration scenarios (clearly marked as demo content)."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any


def load_demo_scenarios() -> list[dict[str, Any]]:
    folder = resources.files("drikr_simcore") / "demo_scenarios"
    out = []
    for entry in sorted(folder.iterdir(), key=lambda p: p.name):
        if entry.name.endswith(".json"):
            out.append(json.loads(entry.read_text(encoding="utf-8")))
    return out
