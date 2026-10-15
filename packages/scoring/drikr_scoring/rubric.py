"""Versioned scoring rubric schema.

A rubric is immutable once saved: changing weights or rules creates a new
version, and each score result records the exact rubric key, version and digest
it was produced with. Historical scores therefore never change silently.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from drikr_contracts.enums import EntityClass, TrackClassification, TrainingResponse

RUBRIC_SCHEMA_VERSION = "1.0"

DIMENSIONS = ("recognition", "timing", "consistency", "uncertainty", "objectives", "procedure")

FactName = Literal[
    "true_class",
    "cooperative",
    "behavior",
    "closest_range_m",
    "beacon_observed",
    "swarm_member",
]
Operator = Literal["eq", "ne", "in", "not_in", "lt", "lte", "gt", "gte"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DimensionWeights(_Strict):
    recognition: float = Field(ge=0, le=1)
    timing: float = Field(ge=0, le=1)
    consistency: float = Field(ge=0, le=1)
    uncertainty: float = Field(ge=0, le=1)
    objectives: float = Field(ge=0, le=1)
    procedure: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _sum(self) -> Self:
        total = sum(getattr(self, d) for d in DIMENSIONS)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"dimension weights must sum to 1.0 (got {total:.4f})")
        if self.recognition <= 0:
            raise ValueError("recognition weight must be positive")
        return self

    def as_dict(self) -> dict[str, float]:
        return {d: getattr(self, d) for d in DIMENSIONS}


class TimingRule(_Strict):
    """Full credit at or below ``target_s``; zero credit at or beyond ``max_s``; linear in between."""

    target_s: float = Field(gt=0, le=600)
    max_s: float = Field(gt=0, le=1800)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.max_s <= self.target_s:
            raise ValueError("max_s must exceed target_s")
        return self


class PartialCredit(_Strict):
    true_class: EntityClass
    given: TrackClassification
    credit: float = Field(ge=0, le=1)


class UncertaintyRule(_Strict):
    """Applies to tracks classified while classification evidence quality was below the threshold."""

    evidence_threshold: float = Field(ge=0, le=1, default=0.5)
    credit_low_confidence: float = Field(ge=0, le=1, default=1.0)
    credit_medium_confidence: float = Field(ge=0, le=1, default=0.6)
    credit_high_confidence_correct: float = Field(ge=0, le=1, default=0.3)
    credit_high_confidence_wrong: float = Field(ge=0, le=1, default=0.0)
    credit_confirmation_requested: float = Field(ge=0, le=1, default=1.0)


class Condition(_Strict):
    fact: FactName
    op: Operator
    value: Any

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if self.op in ("in", "not_in") and not isinstance(self.value, list):
            raise ValueError(f"operator '{self.op}' requires a list value")
        if self.op in ("lt", "lte", "gt", "gte") and not isinstance(self.value, int | float):
            raise ValueError(f"operator '{self.op}' requires a numeric value")
        return self


class DecisionLeaf(_Strict):
    kind: Literal["leaf"] = "leaf"
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")
    expected: list[TrainingResponse] = Field(min_length=1)
    acceptable: list[TrainingResponse] = Field(default_factory=list)
    rationale: str = Field(min_length=5, max_length=300)

    @model_validator(mode="after")
    def _disjoint(self) -> Self:
        if set(self.expected) & set(self.acceptable):
            raise ValueError(f"leaf '{self.id}': a response cannot be both expected and acceptable")
        return self


class DecisionBranch(_Strict):
    kind: Literal["branch"] = "branch"
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")
    condition: Condition
    if_true: DecisionNode
    if_false: DecisionNode


DecisionNode = Annotated[DecisionBranch | DecisionLeaf, Field(discriminator="kind")]
DecisionBranch.model_rebuild()


class ConfirmBeforeClearRule(_Strict):
    kind: Literal["confirm_before_clear"] = "confirm_before_clear"
    description: str = "Request sensor confirmation before clearing a track with weak classification evidence."
    evidence_threshold: float = Field(ge=0, le=1, default=0.5)


class MinObservationsBeforeClearRule(_Strict):
    kind: Literal["min_observations_before_clear"] = "min_observations_before_clear"
    description: str = "Wait for enough observations before clearing a track."
    min_observations: int = Field(ge=1, le=100, default=5)


class ClassifyBeforeReportRule(_Strict):
    kind: Literal["classify_before_report"] = "classify_before_report"
    description: str = "Classify a track before reporting or clearing it."


ProcedureRule = Annotated[
    ConfirmBeforeClearRule | MinObservationsBeforeClearRule | ClassifyBeforeReportRule,
    Field(discriminator="kind"),
]


class Rubric(_Strict):
    schema_version: Literal["1.0"] = "1.0"
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    version: int = Field(ge=1, default=1)
    name: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=5, max_length=2000)
    pass_mark: float = Field(ge=0, le=100, default=70)
    weights: DimensionWeights
    timing: TimingRule
    timing_overrides: dict[EntityClass, TimingRule] = Field(default_factory=dict)
    partial_credit: list[PartialCredit] = Field(default_factory=list)
    uncertainty: UncertaintyRule = Field(default_factory=UncertaintyRule)
    decision_tree: DecisionNode
    procedure_rules: list[ProcedureRule] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids: list[str] = []

        def walk(n: DecisionBranch | DecisionLeaf) -> None:
            ids.append(n.id)
            if isinstance(n, DecisionBranch):
                walk(n.if_true)
                walk(n.if_false)

        walk(self.decision_tree)
        if len(ids) != len(set(ids)):
            raise ValueError("decision tree node ids must be unique")
        pairs = [(p.true_class, p.given) for p in self.partial_credit]
        if len(pairs) != len(set(pairs)):
            raise ValueError("partial_credit entries must be unique per (true_class, given)")
        for p in self.partial_credit:
            if p.given.value == p.true_class.value:
                raise ValueError("partial_credit must not redefine a correct classification")
        kinds = [r.kind for r in self.procedure_rules]
        if len(kinds) != len(set(kinds)):
            raise ValueError("each procedure rule kind may appear once")
        return self

    def timing_for(self, entity_class: str) -> TimingRule:
        try:
            return self.timing_overrides.get(EntityClass(entity_class), self.timing)
        except ValueError:
            return self.timing
