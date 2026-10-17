"""Adaptive difficulty: evidence rules for the retuned policy (docs/research/adaptive-difficulty.md)."""

from __future__ import annotations

import pytest

from drikr_scoring.adaptive import AdaptivePolicy, SessionOutcome, recommend_level


def hist(*pairs: tuple[float, int]) -> list[SessionOutcome]:
    return [
        SessionOutcome(f"s{i}", score, level, f"2026-10-16T10:{i:02d}:00Z") for i, (score, level) in enumerate(pairs)
    ]


SAME = AdaptivePolicy(same_level_only=True)


def test_insufficient_evidence_holds_with_low_confidence() -> None:
    rec = recommend_level(hist((99, 2)), 2, 1, 4, SAME)
    assert rec.change == "hold" and rec.confidence == "low" and "required" in rec.reason


@pytest.mark.parametrize("outlier", [100.0, 0.0])
def test_one_unusual_result_is_not_enough(outlier: float) -> None:
    """A single very good or very poor session among steady ones does not move the level."""
    steady = [(65.0, 2), (66.0, 2)]
    rec = recommend_level(hist(*steady, (outlier, 2)), 2, 1, 4, SAME)
    assert rec.change == "hold", rec.reason


def test_results_at_another_level_do_not_count() -> None:
    # Promoted to 3 after strong sessions at level 2: those level-2 scores must not justify level 4.
    h = hist((95, 2), (96, 2), (97, 2), (92, 3))
    mixed = recommend_level(h, 3, 1, 4, AdaptivePolicy())
    same = recommend_level(h, 3, 1, 4, SAME)
    assert mixed.change == "increase"  # the previous behaviour, kept when the option is off
    assert same.change == "hold" and same.evidence["sessions_considered"] == ["s3"]


def test_sustained_evidence_at_the_current_level_changes_one_step_within_bounds() -> None:
    up = recommend_level(hist((90, 3), (92, 3), (91, 3)), 3, 1, 4, SAME)
    assert (up.change, up.recommended_level) == ("increase", 4)
    capped = recommend_level(hist((90, 4), (92, 4), (91, 4)), 4, 1, 4, SAME)
    assert capped.change == "hold" and "maximum" in capped.reason
    down = recommend_level(hist((30, 2), (35, 2), (28, 2)), 2, 2, 4, SAME)
    assert down.change == "hold" and "minimum" in down.reason
    assert all(r.reason for r in (up, capped, down))


def test_policy_round_trips_and_validates() -> None:
    assert AdaptivePolicy.model_validate(SAME.model_dump()) == SAME
    with pytest.raises(ValueError):
        AdaptivePolicy(demote_mean=90, promote_mean=80)


DEFAULT = AdaptivePolicy()


def test_default_policy_uses_robust_demotion() -> None:
    assert DEFAULT.robust_demotion and not DEFAULT.same_level_only and DEFAULT.demote_max_each == 100


@pytest.mark.parametrize(
    ("scores", "change"),
    [
        ((60.0, 58.0, 0.0), "hold"),  # one failed session among adequate ones
        ((70.0, 0.0), "hold"),  # window not yet full
        ((50.0, 40.0, 70.0), "decrease"),  # two poor sessions out of three
        ((30.0, 35.0, 28.0), "decrease"),
    ],
)
def test_a_decrease_needs_most_of_a_full_window_to_be_poor(scores: tuple[float, ...], change: str) -> None:
    rec = recommend_level(hist(*[(x, 3) for x in scores]), 3, 1, 4, DEFAULT)
    assert rec.change == change, rec.reason
    assert rec.evidence["median"] is not None and rec.reason
