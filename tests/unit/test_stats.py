"""Statistics helpers against known values."""

from __future__ import annotations

import pytest

from drikr_scoring import stats


def test_correlations() -> None:
    xs = [1, 2, 3, 4, 5]
    assert stats.pearson(xs, [2, 4, 6, 8, 10]) == pytest.approx(1.0)
    assert stats.pearson(xs, [5, 4, 3, 2, 1]) == pytest.approx(-1.0)
    assert stats.spearman(xs, [1, 4, 9, 16, 25]) == pytest.approx(1.0)  # monotonic, non-linear
    assert stats.ranks([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]


def test_effect_sizes() -> None:
    assert stats.cohen_dz([1, 2, 3, 4, 5]) == pytest.approx(3 / 1.5811388, rel=1e-6)
    assert stats.cohen_d([1, 2, 3], [3, 4, 5]) == pytest.approx(2.0)


def test_sign_test_exact() -> None:
    # 8 positive of 8: two-sided p = 2 * (1/256)
    assert stats.sign_test_p([1] * 8) == pytest.approx(2 / 256)
    assert stats.sign_test_p([1, -1, 0]) == pytest.approx(1.0)
    assert stats.sign_test_p([]) == 1.0


def test_bootstrap_is_deterministic_and_covers_mean() -> None:
    xs = [3.0, 5.0, 7.0, 9.0, 11.0, 4.0, 6.0]
    a = stats.bootstrap_mean_ci(xs)
    assert a == stats.bootstrap_mean_ci(xs)
    assert a[0] < stats.mean(xs) < a[1]


def test_icc_perfect_and_noisy() -> None:
    assert stats.icc_a1([(1, 1), (2, 2), (3, 3), (4, 4)]) == pytest.approx(1.0)
    assert stats.icc_a1([(1, 4), (4, 1), (2, 3), (3, 2)]) < 0
