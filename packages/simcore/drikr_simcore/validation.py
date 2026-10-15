"""Two-layer scenario validation.

1. Structural and cross-field validation (Pydantic contract).
2. Generation checks: the scenario is expanded with its seed and difficulty and
   the resulting timeline is checked for training usability.

Invalid scenarios are rejected before any session can execute them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from pydantic import ValidationError

from drikr_contracts.scenario import ClassifyCorrectlyCriterion, RespondWithinCriterion, Scenario
from drikr_simcore.generator import generate_timeline
from drikr_simcore.ground_truth import GroundTruthIndex

MAX_EVENTS = 120_000
LATE_TRACK_MARGIN_MS = 30_000


@dataclass
class ValidationIssue:
    path: str
    code: str
    message: str
    severity: Literal["error", "warning"] = "error"


@dataclass
class ValidationReport:
    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    scenario: Scenario | None = None
    preview: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "issues": [asdict(i) for i in self.issues],
            "preview": self.preview,
        }


def _loc(loc: tuple[int | str, ...]) -> str:
    return ".".join(str(p) for p in loc) or "$"


def validate_definition(
    data: Any,
    *,
    seed: int | None = None,
    difficulty_level: int | None = None,
    run_generation: bool = True,
) -> ValidationReport:
    try:
        scn = Scenario.model_validate(data)
    except ValidationError as exc:
        issues = [ValidationIssue(path=_loc(err["loc"]), code=err["type"], message=err["msg"]) for err in exc.errors()]
        return ValidationReport(valid=False, issues=issues)

    report = ValidationReport(valid=True, scenario=scn)
    if not run_generation:
        return report
    report.issues.extend(generation_checks(scn, seed=seed, difficulty_level=difficulty_level, report=report))
    report.valid = not any(i.severity == "error" for i in report.issues)
    return report


def generation_checks(
    scn: Scenario,
    *,
    seed: int | None = None,
    difficulty_level: int | None = None,
    report: ValidationReport | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    timeline = generate_timeline(scn, seed=seed, difficulty_level=difficulty_level)
    duration = timeline.duration_ms
    if report is not None:
        report.preview = timeline.summary()

    if len(timeline.events) > MAX_EVENTS:
        issues.append(
            ValidationIssue("$", "too_many_events", f"timeline has {len(timeline.events)} events (max {MAX_EVENTS})")
        )

    index = GroundTruthIndex(timeline.events)
    observable = index.observable_tracks(duration)
    if not observable:
        issues.append(
            ValidationIssue("entities", "no_observable_tracks", "no virtual entity is observed by any simulated sensor")
        )
        return issues

    observable_classes = {index.entities[t.entity_id].entity_class for t in observable}
    for i, obj in enumerate(scn.learning_objectives):
        crit = obj.criterion
        if (
            isinstance(crit, ClassifyCorrectlyCriterion | RespondWithinCriterion)
            and crit.entity_class.value not in observable_classes
        ):
            issues.append(
                ValidationIssue(
                    f"learning_objectives.{i}.criterion.entity_class",
                    "objective_unobservable",
                    f"objective '{obj.id}' needs an observable '{crit.entity_class.value}' track, "
                    "but none is observed with this seed and difficulty",
                )
            )

    late = [t.track_id for t in observable if (t.first_available_ms or 0) > duration - LATE_TRACK_MARGIN_MS]
    if late:
        issues.append(
            ValidationIssue(
                "time_limits.duration_s",
                "late_tracks",
                f"{len(late)} track(s) first become visible in the final 30 s: {', '.join(late[:5])}",
                severity="warning",
            )
        )
    return issues
