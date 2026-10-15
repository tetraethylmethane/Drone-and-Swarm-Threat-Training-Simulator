"""Small, dependency-free statistics used by learning-gain analytics and the validation study.

Deterministic: resampling uses the documented SplitMix64 generator with an explicit seed, so the
same data always yields the same interval.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

from drikr_simcore.rng import Rng


def mean(xs: Sequence[float]) -> float:
    return statistics.fmean(xs)


def sd(xs: Sequence[float]) -> float:
    return statistics.stdev(xs) if len(xs) > 1 else 0.0


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 3:
        raise ValueError("need at least three paired values")
    mx, my = mean(xs), mean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else 0.0


def ranks(xs: Sequence[float]) -> list[float]:
    """Average ranks (ties share the mean rank), 1-based."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    return pearson(ranks(xs), ranks(ys))


def cohen_d(a: Sequence[float], b: Sequence[float]) -> float:
    """Standardised mean difference (b - a) with pooled SD."""
    na, nb = len(a), len(b)
    pooled = math.sqrt(((na - 1) * sd(a) ** 2 + (nb - 1) * sd(b) ** 2) / (na + nb - 2))
    return (mean(b) - mean(a)) / pooled if pooled else 0.0


def cohen_dz(diffs: Sequence[float]) -> float:
    """Paired effect size: mean difference divided by the SD of differences."""
    s = sd(diffs)
    return mean(diffs) / s if s else 0.0


def bootstrap_mean_ci(
    xs: Sequence[float], *, level: float = 0.95, resamples: int = 2000, seed: int = 20261015
) -> tuple[float, float]:
    """Percentile bootstrap confidence interval for the mean."""
    if len(xs) < 2:
        raise ValueError("need at least two values")
    rng = Rng.stream(seed, "bootstrap", len(xs))
    n = len(xs)
    means = sorted(sum(xs[rng.randint(0, n - 1)] for _ in range(n)) / n for _ in range(resamples))
    lo = means[int((1 - level) / 2 * resamples)]
    hi = means[min(resamples - 1, int((1 + level) / 2 * resamples))]
    return lo, hi


def sign_test_p(diffs: Sequence[float]) -> float:
    """Exact two-sided sign test (zero differences dropped). Robust to non-normal score changes."""
    pos = sum(1 for d in diffs if d > 0)
    neg = sum(1 for d in diffs if d < 0)
    n = pos + neg
    if n == 0:
        return 1.0
    k = min(pos, neg)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (1 << n)
    return min(1.0, 2 * tail)


def icc_a1(pairs: Sequence[tuple[float, float]]) -> float:
    """ICC(A,1): two-way, absolute agreement, single measurement (test-retest reliability)."""
    n, k = len(pairs), 2
    grand = mean([v for p in pairs for v in p])
    row_means = [mean(p) for p in pairs]
    col_means = [mean([p[j] for p in pairs]) for j in range(k)]
    ss_rows = k * sum((m - grand) ** 2 for m in row_means)
    ss_cols = n * sum((m - grand) ** 2 for m in col_means)
    ss_total = sum((v - grand) ** 2 for p in pairs for v in p)
    ss_err = ss_total - ss_rows - ss_cols
    msr = ss_rows / (n - 1)
    msc = ss_cols / (k - 1)
    mse = ss_err / ((n - 1) * (k - 1))
    return (msr - mse) / (msr + (k - 1) * mse + k * (msc - mse) / n)
