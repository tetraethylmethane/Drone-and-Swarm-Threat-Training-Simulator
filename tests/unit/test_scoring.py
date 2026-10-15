"""Scoring engine and adaptive difficulty tests."""

from __future__ import annotations

import copy
import math

import pytest
from pydantic import ValidationError

from drikr_scoring import Rubric, load_default_rubrics, score_session
from drikr_scoring.adaptive import AdaptivePolicy, SessionOutcome, recommend_level
from drikr_scoring.engine import _timing_credit, evaluate_tree
from drikr_simcore.canonical import digest
from drikr_simcore.rng import Rng
from tests.unit.helpers import build_session, idle_policy, perfect_policy, rubric, scenario

# ---------------------------------------------------------------------------
# Rubric validation
# ---------------------------------------------------------------------------


def _rubric_data() -> dict:
    return copy.deepcopy(load_default_rubrics()[0])


def test_default_rubric_valid() -> None:
    r = Rubric.model_validate(_rubric_data())
    assert math.isclose(sum(r.weights.as_dict().values()), 1.0)


@pytest.mark.parametrize(
    ("mutate", "fragment"),
    [
        (lambda d: d["weights"].update(recognition=0.5), "must sum to 1.0"),
        (lambda d: d["timing"].update(target_s=100, max_s=90), "max_s must exceed target_s"),
        (lambda d: d["decision_tree"]["if_true"].update(id="is-clutter"), "node ids must be unique"),
        (lambda d: d["decision_tree"]["if_true"].update(acceptable=["log_as_cleared"]), "both expected and acceptable"),
        (
            lambda d: d["partial_credit"].append(
                {"true_class": "bird_or_clutter", "given": "bird_or_clutter", "credit": 1}
            ),
            "must not redefine",
        ),
        (lambda d: d["decision_tree"]["condition"].update(op="lt", value="x"), "requires a numeric value"),
        (lambda d: d["procedure_rules"].append({"kind": "classify_before_report"}), "may appear once"),
    ],
)
def test_invalid_rubrics_rejected(mutate, fragment: str) -> None:  # type: ignore[no-untyped-def]
    data = _rubric_data()
    mutate(data)
    with pytest.raises(ValidationError, match=fragment):
        Rubric.model_validate(data)


# ---------------------------------------------------------------------------
# Decision tree and timing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("facts", "leaf"),
    [
        ({"true_class": "bird_or_clutter"}, "clutter"),
        ({"true_class": "coordinated_swarm"}, "swarm"),
        ({"true_class": "small_multirotor", "cooperative": True, "beacon_observed": True}, "cooperative-confirmed"),
        ({"true_class": "small_multirotor", "cooperative": True, "beacon_observed": False}, "cooperative-unconfirmed"),
        ({"true_class": "small_multirotor", "cooperative": False, "closest_range_m": 1500}, "noncooperative-near"),
        ({"true_class": "fixed_wing_uas", "cooperative": False, "closest_range_m": 1500.1}, "noncooperative-distant"),
    ],
)
def test_decision_tree_paths(facts: dict, leaf: str) -> None:
    node, path = evaluate_tree(rubric().decision_tree, facts)
    assert node.id == leaf
    assert path[-1] == {"node": leaf, "leaf": True}
    assert all("result" in p for p in path[:-1])


@pytest.mark.parametrize(
    ("delta", "expected"),
    [(0, 1.0), (20, 1.0), (20.0001, 0.99999857), (55, 0.5), (90, 0.0), (500, 0.0)],
)
def test_timing_boundaries(delta: float, expected: float) -> None:
    assert _timing_credit(delta, 20, 90) == pytest.approx(expected, abs=1e-6)


# ---------------------------------------------------------------------------
# End-to-end scoring over generated timelines
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key", ["demo-perimeter-basics", "demo-night-loiter", "demo-swarm-recognition", "demo-degraded-picture"]
)
def test_perfect_trainee_scores_high(key: str) -> None:
    scn = scenario(key)
    events, _, end_ms = build_session(scn, perfect_policy)
    res = score_session(events, scn, rubric(), end_ms)
    assert res["status"] == "scored"
    assert res["dimensions"]["recognition"]["score"] == 100.0
    assert res["errors"]["missed_tracks"] == []
    assert res["errors"]["incorrect_classifications"] == []
    assert res["overall"] >= 90, res["dimensions"]
    assert res["passed"] is True


def test_idle_trainee_gets_no_free_points() -> None:
    scn = scenario()
    events, _, end_ms = build_session(scn, idle_policy)
    res = score_session(events, scn, rubric(), end_ms)
    dims = res["dimensions"]
    assert dims["recognition"]["score"] == 0.0
    assert dims["consistency"]["score"] == 0.0
    assert dims["timing"]["applicable"] is False
    assert dims["uncertainty"]["applicable"] is False
    assert dims["procedure"]["applicable"] is False
    assert res["passed"] is False
    # Only "no false clearance" can be met by doing nothing; it must not lift the score above a low bound.
    assert res["overall"] < 25
    assert len(res["errors"]["missed_tracks"]) == res["counts"]["observable_tracks"]


def test_scoring_is_deterministic() -> None:
    scn = scenario("demo-swarm-recognition")
    events, _, end_ms = build_session(scn, perfect_policy)
    a = score_session(events, scn, rubric(), end_ms)
    b = score_session(list(reversed(events)), scn, rubric(), end_ms)  # input order must not matter
    assert digest(a) == digest(b)


def test_explanations_match_computed_scores() -> None:
    scn = scenario("demo-degraded-picture")

    def mixed(tid: str, info: dict) -> list[dict]:
        n = int(tid[-3:])
        ent = info["entity"]
        if n % 3 == 0:
            return []
        cls = ent.entity_class if n % 2 else "unknown"
        return [
            {"delay_s": n * 3, "kind": "classify", "classification": cls, "confidence": "high"},
            {
                "delay_s": n * 3 + 1,
                "kind": "respond",
                "response": "log_as_cleared" if n % 2 else "report_to_exercise_control",
            },
        ]

    events, _, end_ms = build_session(scn, mixed)
    res = score_session(events, scn, rubric(), end_ms)
    eff_total = 0.0
    overall = 0.0
    for d in res["dimensions"].values():
        if not d["applicable"]:
            assert d["score"] is None and d["contribution"] == 0.0
            continue
        mean = 100 * sum(i["credit"] for i in d["items"]) / len(d["items"])
        assert d["score"] == pytest.approx(round(mean, 1))
        eff_total += d["effective_weight"]
        overall += d["contribution"]
    assert eff_total == pytest.approx(1.0, abs=1e-3)
    assert res["overall"] == pytest.approx(overall, abs=0.1)
    assert res["errors"]["procedure_violations"], "clearing on weak evidence without confirmation must be flagged"


def test_weight_change_changes_score_and_records_version() -> None:
    scn = scenario()
    events, _, end_ms = build_session(
        scn, lambda t, i: [{"delay_s": 1, "kind": "classify", "classification": i["entity"].entity_class}]
    )
    v1 = rubric()
    data = _rubric_data()
    data["version"] = 2
    data["weights"] = {
        "recognition": 0.9,
        "timing": 0.02,
        "consistency": 0.02,
        "uncertainty": 0.02,
        "objectives": 0.02,
        "procedure": 0.02,
    }
    v2 = Rubric.model_validate(data)
    r1 = score_session(events, scn, v1, end_ms)
    r2 = score_session(events, scn, v2, end_ms)
    assert r1["rubric"]["version"] == 1 and r2["rubric"]["version"] == 2
    assert r1["rubric"]["digest"] != r2["rubric"]["digest"]
    assert r1["overall"] != r2["overall"]
    assert r1["input_digest"] == r2["input_digest"]


def test_insufficient_data_when_nothing_observable() -> None:
    scn = scenario()
    events, _, _ = build_session(scn, idle_policy)
    res = score_session(events, scn, rubric(), end_ms=0)
    assert res["status"] == "insufficient_data"
    assert res["overall"] is None and res["passed"] is None


def test_overconfidence_on_weak_evidence_flagged() -> None:
    scn = scenario("demo-degraded-picture")

    def guess(tid: str, info: dict) -> list[dict]:
        wrong = "coordinated_swarm" if info["entity"].entity_class != "coordinated_swarm" else "bird_or_clutter"
        return [{"delay_s": 0, "kind": "classify", "classification": wrong, "confidence": "high"}]

    events, _, end_ms = build_session(scn, guess)
    res = score_session(events, scn, rubric(), end_ms)
    assert res["dimensions"]["uncertainty"]["applicable"] is True
    assert res["dimensions"]["uncertainty"]["score"] == 0.0
    assert res["errors"]["overconfident"]


def test_false_clearance_objective_and_classify_before_report() -> None:
    scn = scenario()
    events, _, end_ms = build_session(
        scn, lambda t, i: [{"delay_s": 1, "kind": "respond", "response": "log_as_cleared"}]
    )
    res = score_session(events, scn, rubric(), end_ms)
    obj = {o["id"]: o for o in res["objectives"]}
    assert obj["no-false-clear"]["status"] == "not_met"
    rules = {p["rule"]: p for p in res["procedure"]}
    assert rules["classify_before_report"]["violations"]
    assert rules["min_observations_before_clear"]["violations"]


def test_partial_credit_applied() -> None:
    scn = scenario("demo-swarm-recognition")
    events, _, end_ms = build_session(
        scn,
        lambda t, i: [
            {
                "delay_s": 1,
                "kind": "classify",
                "classification": "small_multirotor"
                if i["entity"].entity_class == "coordinated_swarm"
                else i["entity"].entity_class,
            }
        ],
    )
    res = score_session(events, scn, rubric(), end_ms)
    swarm_items = [i for i in res["dimensions"]["recognition"]["items"] if "coordinated swarm" in i["reason"]]
    assert swarm_items and all(i["credit"] == 0.25 for i in swarm_items)


def test_decisions_on_unobservable_tracks_ignored() -> None:
    scn = scenario()
    events, _, end_ms = build_session(scn, idle_policy)
    events.append(
        {
            "event_id": "T-999999",
            "seq": 999999,
            "t_ms": 1000,
            "available_at_ms": 1000,
            "type": "classification_submitted",
            "visibility": "trainee",
            "origin": "trainee",
            "payload": {
                "client_action_id": "00000000-0000-0000-0000-000000000001",
                "track_ids": ["TRK-999"],
                "classification": "unknown",
                "confidence": "low",
                "note": None,
            },
        }
    )
    res = score_session(events, scn, rubric(), end_ms)
    assert res["counts"]["ignored_decisions"] == 1


# ---------------------------------------------------------------------------
# Adaptive difficulty
# ---------------------------------------------------------------------------


def _hist(*scores: float, level: int = 3) -> list[SessionOutcome]:
    return [SessionOutcome(f"s{i}", s, level, f"2026-01-0{i + 1}") for i, s in enumerate(scores)]


def test_adaptive_holds_without_evidence() -> None:
    rec = recommend_level(_hist(99), 3, 1, 5)
    assert rec.change == "hold" and rec.confidence == "low"
    assert "required before adjusting" in rec.reason


def test_adaptive_increase_decrease_and_hold() -> None:
    assert recommend_level(_hist(90, 92, 88), 3, 1, 5).recommended_level == 4
    assert recommend_level(_hist(40, 50, 45), 3, 1, 5).recommended_level == 2
    held = recommend_level(_hist(90, 70, 95), 3, 1, 5)
    assert held.change == "hold" and "fell below" in held.reason


def test_adaptive_respects_instructor_bounds() -> None:
    top = recommend_level(_hist(95, 96, 97), 4, 1, 4)
    assert top.recommended_level == 4 and "instructor maximum" in top.reason
    bottom = recommend_level(_hist(10, 20, 15), 2, 2, 5)
    assert bottom.recommended_level == 2 and "instructor minimum" in bottom.reason
    clamped = recommend_level(_hist(60, 60), 5, 1, 3)
    assert clamped.current_level == 3 and clamped.evidence["clamped_from"] == 5


def test_adaptive_never_leaves_bounds_and_always_explains() -> None:
    rng = Rng.stream(11, "adaptive-property")
    for _ in range(500):
        lo = rng.randint(1, 5)
        hi = rng.randint(lo, 5)
        cur = rng.randint(1, 5)
        hist = _hist(*[round(rng.uniform(0, 100), 1) for _ in range(rng.randint(0, 6))])
        rec = recommend_level(hist, cur, lo, hi)
        assert lo <= rec.recommended_level <= hi
        assert abs(rec.recommended_level - rec.current_level) <= 1
        assert rec.reason
        assert (rec.change == "hold") == (rec.recommended_level == rec.current_level)


def test_adaptive_policy_validation() -> None:
    with pytest.raises(ValidationError):
        AdaptivePolicy(window=2, min_sessions=3)
    with pytest.raises(ValidationError):
        AdaptivePolicy(demote_mean=90, promote_mean=80)
