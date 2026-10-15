"""Rules-based adaptive difficulty.

The policy looks at a trainee's most recent completed, scored sessions for the
same scenario and recommends whether to raise, lower or hold difficulty. Every
recommendation, including "hold", carries a human-readable reason and the
evidence it used, so that no adaptive change happens without a recorded reason.

No machine-learning model is involved. See docs/architecture/scoring-model.md.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AdaptivePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window: int = Field(ge=1, le=10, default=3)
    min_sessions: int = Field(ge=1, le=10, default=2)
    promote_mean: float = Field(ge=0, le=100, default=85.0)
    promote_min_each: float = Field(ge=0, le=100, default=75.0)
    demote_mean: float = Field(ge=0, le=100, default=55.0)
    high_confidence_max_stdev: float = Field(ge=0, le=100, default=10.0)

    @model_validator(mode="after")
    def _order(self) -> AdaptivePolicy:
        if self.min_sessions > self.window:
            raise ValueError("min_sessions cannot exceed window")
        if self.demote_mean >= self.promote_mean:
            raise ValueError("demote_mean must be below promote_mean")
        return self


@dataclass(frozen=True)
class SessionOutcome:
    session_id: str
    overall: float
    difficulty_level: int
    completed_at: str


@dataclass
class Recommendation:
    current_level: int
    recommended_level: int
    change: Literal["increase", "decrease", "hold"]
    confidence: Literal["low", "medium", "high"]
    reason: str
    evidence: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def recommend_level(
    history: list[SessionOutcome],
    current_level: int,
    min_level: int,
    max_level: int,
    policy: AdaptivePolicy | None = None,
) -> Recommendation:
    """``history`` must be ordered oldest to newest and contain only scored sessions."""
    policy = policy or AdaptivePolicy()
    if not (1 <= min_level <= max_level <= 5):
        raise ValueError("invalid difficulty bounds")
    current = max(min_level, min(max_level, current_level))
    recent = history[-policy.window :]
    scores = [h.overall for h in recent]
    evidence: dict[str, object] = {
        "window": policy.window,
        "sessions_considered": [h.session_id for h in recent],
        "scores": scores,
        "bounds": [min_level, max_level],
        "policy": policy.model_dump(),
    }

    if current != current_level:
        evidence["clamped_from"] = current_level

    if len(recent) < policy.min_sessions:
        return Recommendation(
            current,
            current,
            "hold",
            "low",
            f"Holding at level {current}: {len(recent)} scored session(s) available, "
            f"{policy.min_sessions} required before adjusting.",
            evidence,
        )

    mean = statistics.fmean(scores)
    stdev = statistics.pstdev(scores) if len(scores) > 1 else 0.0
    evidence.update(mean=round(mean, 2), stdev=round(stdev, 2))
    confidence: Literal["low", "medium", "high"]
    if len(recent) >= policy.window and stdev <= policy.high_confidence_max_stdev:
        confidence = "high"
    elif len(recent) >= policy.window or stdev <= policy.high_confidence_max_stdev:
        confidence = "medium"
    else:
        confidence = "low"

    if mean >= policy.promote_mean and min(scores) >= policy.promote_min_each:
        if current >= max_level:
            return Recommendation(
                current,
                current,
                "hold",
                confidence,
                f"Holding at level {current}: performance supports an increase (mean {mean:.1f}) "
                f"but the instructor maximum is level {max_level}.",
                evidence,
            )
        if confidence == "low":
            return Recommendation(
                current,
                current,
                "hold",
                confidence,
                f"Holding at level {current}: mean {mean:.1f} meets the promotion threshold but results vary "
                f"too much (stdev {stdev:.1f}) to be confident.",
                evidence,
            )
        return Recommendation(
            current,
            current + 1,
            "increase",
            confidence,
            f"Increasing to level {current + 1}: mean {mean:.1f} >= {policy.promote_mean:g} and every recent "
            f"score >= {policy.promote_min_each:g}.",
            evidence,
        )
    if mean < policy.demote_mean:
        if current <= min_level:
            return Recommendation(
                current,
                current,
                "hold",
                confidence,
                f"Holding at level {current}: mean {mean:.1f} is below {policy.demote_mean:g} "
                f"but the instructor minimum is level {min_level}.",
                evidence,
            )
        return Recommendation(
            current,
            current - 1,
            "decrease",
            confidence,
            f"Decreasing to level {current - 1}: mean {mean:.1f} < {policy.demote_mean:g}.",
            evidence,
        )
    return Recommendation(
        current,
        current,
        "hold",
        confidence,
        f"Holding at level {current}: mean {mean:.1f} is between {policy.demote_mean:g} and {policy.promote_mean:g}"
        + (f" or a recent score fell below {policy.promote_min_each:g}." if mean >= policy.promote_mean else "."),
        evidence,
    )
