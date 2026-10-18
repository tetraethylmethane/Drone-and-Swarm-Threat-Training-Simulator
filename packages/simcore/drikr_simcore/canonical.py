"""Canonical JSON serialisation and digests used for reproducibility evidence."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _without_negative_zero(value: Any) -> Any:
    """-0.0 becomes 0.0. Rounding can produce -0.0 (for example a coordinate of -0.04 m), but
    PostgreSQL JSONB stores it as 0.0, so a digest that kept the sign would not match the stored
    log (defect D-03). The two are numerically equal; only the sign of zero is ignored."""
    if isinstance(value, float):
        return 0.0 if value == 0.0 else value
    if isinstance(value, dict):
        return {k: _without_negative_zero(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_without_negative_zero(v) for v in value]
    return value


def digest(value: Any) -> str:
    """SHA-256 of the canonical JSON, with -0.0 treated as 0.0. Audit hashing uses
    ``canonical_json`` directly and is unchanged."""
    return hashlib.sha256(canonical_json(_without_negative_zero(value)).encode("utf-8")).hexdigest()
