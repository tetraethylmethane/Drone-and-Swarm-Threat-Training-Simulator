"""Export JSON Schema files for consumers outside Python (web client, Unity adapter).

Run: ``python -m drikr_contracts.export_schemas [output_dir]``
A test (tests/unit/test_contracts.py) fails if the committed files are stale.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel

from drikr_contracts.actions import TraineeAction
from drikr_contracts.events import SimEvent
from drikr_contracts.scenario import Scenario, TraineeOptions, TraineeSelection

SCHEMAS: dict[str, type[BaseModel]] = {
    "scenario.schema.json": Scenario,
    "sim-event.schema.json": SimEvent,
    "trainee-action.schema.json": TraineeAction,
    "trainee-options.schema.json": TraineeOptions,
    "trainee-selection.schema.json": TraineeSelection,
}


def render() -> dict[str, str]:
    return {
        name: json.dumps(model.model_json_schema(mode="validation"), indent=2, sort_keys=True) + "\n"
        for name, model in SCHEMAS.items()
    }


def main(out_dir: str | None = None) -> None:
    target = Path(out_dir) if out_dir else Path(__file__).resolve().parent.parent / "schemas"
    target.mkdir(parents=True, exist_ok=True)
    for name, text in render().items():
        (target / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {target / name}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
