"""Longitudinal competency summaries and attempt comparison, from persisted results only.

Rules are deliberately simple and stated in the response (`method`), so an instructor can see
exactly why a competency is called improving or an error recurring. Nothing here estimates
real-world readiness; it describes scores already stored.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from drikr_scoring import DIMENSIONS

#: Sessions averaged at each end of the history when describing change.
WINDOW = 3
#: Change in percentage points needed to call a dimension improving or declining.
TREND_THRESHOLD = 5.0
#: An error type recurs when it appears in at least this many of the last WINDOW sessions.
RECUR_MIN = 2

ERROR_LABELS = {
    "incorrect_classifications": "Incorrect classifications",
    "missed_tracks": "Tracks never classified",
    "inconsistent_decisions": "Responses not matching the rubric",
    "procedure_violations": "Procedural rule violations",
    "overconfident": "High confidence on weak evidence",
}


@dataclass(frozen=True)
class Attempt:
    session_id: str
    completed_at: datetime | None
    scenario_key: str
    scenario_version: int
    difficulty_level: int
    seed: int
    timeline_digest: str
    rubric_version: str
    scoring_engine_version: str
    overall: float | None
    result: dict[str, Any]

    def meta(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "scenario_key": self.scenario_key,
            "scenario_version": self.scenario_version,
            "difficulty_level": self.difficulty_level,
            "seed": self.seed,
            "overall": self.overall,
            "rubric_version": self.rubric_version,
            "scoring_engine_version": self.scoring_engine_version,
        }


def _mean(xs: Sequence[float]) -> float | None:
    return round(sum(xs) / len(xs), 1) if xs else None


def _error_count(result: dict[str, Any], key: str) -> int:
    """Errors of one type; summary-level views carry only counts (no per-track detail)."""
    errors = result.get("errors")
    if errors is not None:
        return len(errors.get(key) or [])
    return int((result.get("error_counts") or {}).get(key, 0))


def _dim_score(result: dict[str, Any], dim: str) -> float | None:
    value = ((result.get("dimensions") or {}).get(dim) or {}).get("score")
    return None if value is None else float(value)


def dimension_trends(attempts: Sequence[Attempt]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for dim in DIMENSIONS:
        points = [
            {"session_id": a.session_id, "completed_at": a.meta()["completed_at"], "score": _dim_score(a.result, dim)}
            for a in attempts
        ]
        scored = [float(p["score"]) for p in points if p["score"] is not None]
        early = _mean(scored[:WINDOW])
        recent = _mean(scored[-WINDOW:])
        change = round(recent - early, 1) if len(scored) >= 2 and early is not None and recent is not None else None
        if change is None:
            trend = "insufficient_data"
        elif change >= TREND_THRESHOLD:
            trend = "improving"
        elif change <= -TREND_THRESHOLD:
            trend = "declining"
        else:
            trend = "steady"
        out[dim] = {
            "points": points,
            "assessed_sessions": len(scored),
            "early_mean": early,
            "recent_mean": recent,
            "change": change,
            "trend": trend,
        }
    return out


def recurring_errors(attempts: Sequence[Attempt]) -> list[dict[str, Any]]:
    recent = list(attempts)[-WINDOW:]
    rows = []
    for key, label in ERROR_LABELS.items():
        per_session = [{"session_id": a.session_id, "count": _error_count(a.result, key)} for a in attempts]
        in_recent = sum(1 for a in recent if _error_count(a.result, key))
        latest = next((a for a in reversed(attempts) if _error_count(a.result, key)), None)
        rows.append(
            {
                "type": key,
                "label": label,
                "sessions_with_error": sum(1 for p in per_session if p["count"]),
                "sessions_considered": len(per_session),
                "in_recent_sessions": in_recent,
                "recent_window": len(recent),
                "recurring": len(recent) >= RECUR_MIN and in_recent >= RECUR_MIN,
                "per_session": per_session,
                # Evidence: the latest occurrence, with its first entries as recorded by the scoring engine.
                "latest": None
                if latest is None
                else {
                    "session_id": latest.session_id,
                    "examples": ((latest.result.get("errors") or {}).get(key) or [])[:3],
                },
            }
        )
    return sorted(rows, key=lambda r: (not r["recurring"], -r["sessions_with_error"]))


def equivalent_groups(attempts: Sequence[Attempt]) -> list[dict[str, Any]]:
    """Attempts of the identical exercise: same scenario version, seed and difficulty (same timeline)."""
    groups: dict[str, list[Attempt]] = {}
    for a in attempts:
        groups.setdefault(a.timeline_digest, []).append(a)
    return [
        {
            "timeline_digest": digest,
            "scenario_key": items[0].scenario_key,
            "scenario_version": items[0].scenario_version,
            "seed": items[0].seed,
            "difficulty_level": items[0].difficulty_level,
            "attempts": [i.meta() for i in items],
        }
        for digest, items in groups.items()
        if len(items) >= 2
    ]


def competency(attempts: Sequence[Attempt]) -> dict[str, Any]:
    return {
        "sessions": [a.meta() for a in attempts],
        "dimensions": dimension_trends(attempts),
        "recurring_errors": recurring_errors(attempts),
        "equivalent_attempts": equivalent_groups(attempts),
        "method": {
            "window": WINDOW,
            "trend_threshold_points": TREND_THRESHOLD,
            "recurring_min_in_window": RECUR_MIN,
            "description": (
                f"Change compares the mean of the first {WINDOW} and the last {WINDOW} assessed sessions; "
                f"a change of {TREND_THRESHOLD:g} points or more is called improving or declining. An error type "
                f"recurs when it appears in at least {RECUR_MIN} of the last {WINDOW} sessions. Sessions of "
                "different scenarios or difficulty levels are included unless filtered, so changes can reflect "
                "the exercise as well as the trainee."
            ),
        },
    }


def compare(a: Attempt, b: Attempt, *, include_tracks: bool) -> dict[str, Any]:
    same = {
        "scenario_version": (a.scenario_key, a.scenario_version) == (b.scenario_key, b.scenario_version),
        "seed": a.seed == b.seed,
        "difficulty_level": a.difficulty_level == b.difficulty_level,
        "timeline": a.timeline_digest == b.timeline_digest,
        "rubric_version": a.rubric_version == b.rubric_version,
        "scoring_engine": a.scoring_engine_version == b.scoring_engine_version,
    }
    if same["timeline"] and same["rubric_version"]:
        comparability = "identical"
        note = "Same exercise (identical timeline) scored with the same rubric: differences come from the decisions."
    elif same["scenario_version"]:
        comparability = "same_scenario"
        note = (
            "Same scenario version but a different seed or difficulty: the tracks differ, so compare dimension "
            "scores rather than individual tracks."
        )
    else:
        comparability = "different_scenarios"
        note = "Different scenarios: compare with caution; differences can reflect the exercises themselves."
    dims = {}
    for d in DIMENSIONS:
        sa, sb = _dim_score(a.result, d), _dim_score(b.result, d)
        dims[d] = {"a": sa, "b": sb, "delta": None if sa is None or sb is None else round(sb - sa, 1)}
    objectives_a = {o["id"]: o for o in a.result.get("objectives") or []}
    objectives_b = {o["id"]: o for o in b.result.get("objectives") or []}
    objectives = [
        {
            "id": oid,
            "description": (objectives_a.get(oid) or objectives_b.get(oid) or {}).get("description"),
            "a": (objectives_a.get(oid) or {}).get("status"),
            "b": (objectives_b.get(oid) or {}).get("status"),
        }
        for oid in sorted(set(objectives_a) | set(objectives_b))
    ]
    errors = {
        key: {
            "label": label,
            "a": _error_count(a.result, key),
            "b": _error_count(b.result, key),
        }
        for key, label in ERROR_LABELS.items()
    }
    tracks: list[dict[str, Any]] = []
    if include_tracks and comparability == "identical":
        items_a = {i["track_id"]: i for i in a.result.get("items") or []}
        items_b = {i["track_id"]: i for i in b.result.get("items") or []}
        for tid in sorted(set(items_a) | set(items_b)):
            ia, ib = items_a.get(tid) or {}, items_b.get(tid) or {}
            tracks.append(
                {
                    "track_id": tid,
                    "true_class": ia.get("true_class") or ib.get("true_class"),
                    "a": {k: ia.get(k) for k in ("final_classification", "final_confidence", "final_response")},
                    "b": {k: ib.get(k) for k in ("final_classification", "final_confidence", "final_response")},
                }
            )
    return {
        "a": a.meta(),
        "b": b.meta(),
        "same": same,
        "comparability": comparability,
        "note": note,
        "overall": {
            "a": a.overall,
            "b": b.overall,
            "delta": None if a.overall is None or b.overall is None else round(b.overall - a.overall, 1),
        },
        "dimensions": dims,
        "objectives": objectives,
        "errors": errors,
        "tracks": tracks,
    }
