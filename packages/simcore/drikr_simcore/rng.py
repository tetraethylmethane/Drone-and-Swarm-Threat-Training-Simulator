"""Deterministic pseudo-random number generation.

The algorithm is fixed and documented so that a future Unity (C#) client or any
other implementation can reproduce the same stream:

* Stream seeds are derived with SHA-256 over ``"<seed>|<label>|<label>..."`` and
  the first 8 bytes taken as a big-endian unsigned 64-bit integer.
* Values are produced by SplitMix64 (Steele, Lea & Flood, 2014).
* ``uniform()`` uses the top 53 bits: ``(x >> 11) * 2**-53``.
* ``gauss()`` uses the Box-Muller transform without caching the second value.

Independent named streams (per entity, per sensor) mean that adding a new
entity group does not perturb the random draws of existing ones.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")

_MASK64 = (1 << 64) - 1


def derive_seed(seed: int, *labels: object) -> int:
    material = "|".join([str(int(seed)), *(str(label) for label in labels)]).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


class Rng:
    __slots__ = ("_state",)

    def __init__(self, seed: int) -> None:
        self._state = seed & _MASK64

    @classmethod
    def stream(cls, seed: int, *labels: object) -> Rng:
        return cls(derive_seed(seed, *labels))

    def next_u64(self) -> int:
        self._state = (self._state + 0x9E3779B97F4A7C15) & _MASK64
        z = self._state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
        return z ^ (z >> 31)

    def uniform(self, low: float = 0.0, high: float = 1.0) -> float:
        u = (self.next_u64() >> 11) * (1.0 / (1 << 53))
        return low + (high - low) * u

    def randint(self, low: int, high: int) -> int:
        """Inclusive integer in [low, high]."""
        if high < low:
            raise ValueError("high must be >= low")
        span = high - low + 1
        return low + int(self.uniform() * span) if span > 1 else low

    def chance(self, probability: float) -> bool:
        return self.uniform() < probability

    def gauss(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        u1 = self.uniform()
        u2 = self.uniform()
        u1 = max(u1, 1e-12)
        return mu + sigma * math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)

    def choice(self, items: Sequence[T]) -> T:
        if not items:
            raise ValueError("cannot choose from an empty sequence")
        return items[self.randint(0, len(items) - 1)]

    def shuffled(self, items: Sequence[T]) -> list[T]:
        out = list(items)
        for i in range(len(out) - 1, 0, -1):
            j = self.randint(0, i)
            out[i], out[j] = out[j], out[i]
        return out
