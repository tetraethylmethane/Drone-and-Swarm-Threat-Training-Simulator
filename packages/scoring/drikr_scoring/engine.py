"""Transparent, deterministic scoring engine.

Input: the recorded event log of a session (generated timeline, lifecycle and
trainee events), the scenario definition, the rubric version and the simulation
time at which the session ended. Output: a fully explained result.

The engine reads only the recorded events. It never consults live simulation
state, so any stored session can be re-scored to verify reproducibility.

Scoring is defined in docs/architecture/scoring-model.md. In summary:

* Scoring items are the tracks the trainee could observe before the session ended.
* Each dimension is the mean credit (0..1) over its applicable items, x100.
* Dimensions with no applicable items are reported as not applicable and their
  weight is redistributed proportionally; they never award free points.
* Overall = sum(weight * score) / sum(weight) over applicable dimensions.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from drikr_contracts.enums import Confidence, EntityClass, TrainingResponse
from drikr_contracts.scenario import (
    ClassifyAllCriterion,
    ClassifyCorrectlyCriterion,
    NoFalseClearanceCriterion,
    RespondWithinCriterion,
    Scenario,
)
from drikr_scoring.rubric import (
    DIMENSIONS,
    ClassifyBeforeReportRule,
    Condition,
    ConfirmBeforeClearRule,
    DecisionBranch,
    DecisionLeaf,
    MinObservationsBeforeClearRule,
    Rubric,
)
from drikr_simcore.canonical import digest
from drikr_simcore.ground_truth import GroundTruthIndex, TrackRecord

SCORING_ENGINE_VERSION = "scoring-1.1.0"

DIMENSION_LABELS = {
    "recognition": "Recognition accuracy",
    "timing": "Decision timing",
    "consistency": "Rubric consistency",
    "uncertainty": "Handling of uncertainty",
    "objectives": "Objective completion",
    "procedure": "Procedural compliance",
}


@dataclass(frozen=True)
class Decision:
    seq: int
    t_ms: int
    kind: str  # "classify" | "respond"
    classification: str | None
    confidence: str | None
    response: str | None
    action_id: str


def _h(value: str | None) -> str:
    """Human-readable form of a contract enum value for explanations."""
    return (value or "none").replace("_", " ")


def _s(ms: int | None) -> float | None:
    return None if ms is None else round(ms / 1000.0, 1)


def extract_decisions(events: Iterable[Mapping[str, Any]]) -> dict[str, list[Decision]]:
    out: dict[str, list[Decision]] = {}
    for ev in sorted(events, key=lambda e: e["seq"]):
        p = ev["payload"]
        if ev["type"] == "classification_submitted":
            for tid in p["track_ids"]:
                out.setdefault(tid, []).append(
                    Decision(
                        ev["seq"],
                        ev["t_ms"],
                        "classify",
                        p["classification"],
                        p["confidence"],
                        None,
                        str(p["client_action_id"]),
                    )
                )
        elif ev["type"] == "response_submitted":
            for tid in p["track_ids"]:
                out.setdefault(tid, []).append(
                    Decision(ev["seq"], ev["t_ms"], "respond", None, None, p["response"], str(p["client_action_id"]))
                )
    return out


def evaluate_condition(cond: Condition, facts: Mapping[str, Any]) -> bool:
    actual = facts.get(cond.fact)
    v = cond.value
    match cond.op:
        case "eq":
            return bool(actual == v)
        case "ne":
            return bool(actual != v)
        case "in":
            return actual in v
        case "not_in":
            return actual not in v
        case "lt":
            return actual is not None and actual < v
        case "lte":
            return actual is not None and actual <= v
        case "gt":
            return actual is not None and actual > v
        case "gte":
            return actual is not None and actual >= v
    raise ValueError(f"unsupported operator {cond.op}")


def evaluate_tree(
    node: DecisionBranch | DecisionLeaf, facts: Mapping[str, Any]
) -> tuple[DecisionLeaf, list[dict[str, Any]]]:
    path: list[dict[str, Any]] = []
    while isinstance(node, DecisionBranch):
        result = evaluate_condition(node.condition, facts)
        path.append(
            {
                "node": node.id,
                "fact": node.condition.fact,
                "op": node.condition.op,
                "value": node.condition.value,
                "actual": facts.get(node.condition.fact),
                "result": result,
            }
        )
        node = node.if_true if result else node.if_false
    path.append({"node": node.id, "leaf": True})
    return node, path


def _timing_credit(delta_s: float, target: float, max_s: float) -> float:
    if delta_s <= target:
        return 1.0
    if delta_s >= max_s:
        return 0.0
    return 1.0 - (delta_s - target) / (max_s - target)


class _Item:
    def __init__(self, track: TrackRecord, index: GroundTruthIndex, events_by_track: dict[str, list[dict[str, Any]]]):
        ent = index.entities[track.entity_id]
        self.track = track
        self.track_id = track.track_id
        self.entity = ent
        self.true_class = ent.entity_class
        self.first_available_ms = track.first_available_ms or 0
        self.confirmations = events_by_track.get(track.track_id, [])

    def evidence_at(self, t_ms: int) -> float:
        """Best classification evidence quality visible to the trainee at ``t_ms``."""
        best = 0.0
        for o in self.track.observations:
            if o["available_at_ms"] <= t_ms and o.get("class_hint") is not None:
                best = max(best, float(o["quality"]))
        for c in self.confirmations:
            if c["available_at_ms"] <= t_ms and c["payload"]["outcome"] == "hint_available":
                best = max(best, float(c["payload"]["quality"]))
        return round(best, 2)

    def visible_obs_count(self, t_ms: int) -> int:
        return sum(1 for o in self.track.observations if o["available_at_ms"] <= t_ms)


def score_session(
    events: Sequence[Mapping[str, Any]],
    scenario: Scenario,
    rubric: Rubric,
    end_ms: int,
) -> dict[str, Any]:
    ordered = sorted(events, key=lambda e: e["seq"])
    input_digest = digest([dict(e) for e in ordered])
    index = GroundTruthIndex(ordered)
    decisions = extract_decisions(ordered)

    confirmations: dict[str, list[dict[str, Any]]] = {}
    for ev in ordered:
        if ev["type"] == "sensor_confirmation":
            confirmations.setdefault(ev["payload"]["track_id"], []).append(dict(ev))

    observable = sorted(index.observable_tracks(end_ms), key=lambda t: t.track_id)
    items = [_Item(t, index, confirmations) for t in observable]
    observable_ids = {i.track_id for i in items}
    ignored = sorted(tid for tid in decisions if tid not in observable_ids)

    base: dict[str, Any] = {
        "scoring_engine_version": SCORING_ENGINE_VERSION,
        "rubric": {"key": rubric.key, "version": rubric.version, "digest": digest(rubric.model_dump(mode="json"))},
        "scenario": {"key": scenario.key, "version": scenario.version},
        "input_digest": input_digest,
        "end_ms": end_ms,
        "pass_mark": rubric.pass_mark,
        "weights": rubric.weights.as_dict(),
    }
    if not items:
        return {
            **base,
            "status": "insufficient_data",
            "overall": None,
            "passed": None,
            "explanation": "No track was observable before the session ended, so no performance can be assessed.",
            "dimensions": {},
            "items": [],
            "objectives": [],
            "procedure": [],
            "errors": _empty_errors(),
            "feedback": {"strengths": [], "improvements": []},
            "counts": {"observable_tracks": 0, "classified_tracks": 0, "ignored_decisions": len(ignored)},
        }

    dim_items: dict[str, list[dict[str, Any]]] = {d: [] for d in DIMENSIONS}
    item_rows: list[dict[str, Any]] = []
    errors = _empty_errors()
    partial = {(p.true_class.value, p.given.value): p.credit for p in rubric.partial_credit}
    unc = rubric.uncertainty

    for it in items:
        decs = decisions.get(it.track_id, [])
        classes = [d for d in decs if d.kind == "classify"]
        responses = [d for d in decs if d.kind == "respond"]
        first_cls = classes[0] if classes else None
        final_cls = classes[-1] if classes else None
        final_resp = responses[-1] if responses else None

        beacon = any(o.get("beacon") is True and o["available_at_ms"] <= end_ms for o in it.track.observations)
        facts = {
            "true_class": it.true_class,
            "cooperative": it.entity.cooperative,
            "behavior": it.entity.behavior,
            "closest_range_m": it.entity.closest_range_m,
            "beacon_observed": beacon,
            "swarm_member": it.entity.swarm_id is not None,
        }

        # --- recognition ---------------------------------------------------
        if final_cls is None:
            rec_credit, rec_reason = 0.0, "Observed but never classified (missed track)."
            errors["missed_tracks"].append(
                {"track_id": it.track_id, "true_class": it.true_class, "first_available_s": _s(it.first_available_ms)}
            )
        elif final_cls.classification == it.true_class:
            rec_credit, rec_reason = 1.0, f"Correctly classified as {_h(it.true_class)}."
        else:
            rec_credit = partial.get((it.true_class, final_cls.classification or ""), 0.0)
            rec_reason = f"Classified as {_h(final_cls.classification)}; ground truth was {_h(it.true_class)}" + (
                f" (partial credit {rec_credit:.2f})." if rec_credit else "."
            )
            errors["incorrect_classifications"].append(
                {
                    "track_id": it.track_id,
                    "true_class": it.true_class,
                    "given": final_cls.classification,
                    "confidence": final_cls.confidence,
                    "t_s": _s(final_cls.t_ms),
                }
            )
        dim_items["recognition"].append({"track_id": it.track_id, "credit": rec_credit, "reason": rec_reason})

        # --- timing --------------------------------------------------------
        if first_cls is not None:
            rule = rubric.timing_for(it.true_class)
            delta = max(0.0, (first_cls.t_ms - it.first_available_ms) / 1000.0)
            credit = _timing_credit(delta, rule.target_s, rule.max_s)
            dim_items["timing"].append(
                {
                    "track_id": it.track_id,
                    "credit": credit,
                    "reason": f"First classification {delta:.1f} s after first observation "
                    f"(full credit within {rule.target_s:g} s, none after {rule.max_s:g} s).",
                }
            )

        # --- consistency (decision tree) ----------------------------------
        leaf, path = evaluate_tree(rubric.decision_tree, facts)
        expected = [r.value for r in leaf.expected]
        acceptable = [r.value for r in leaf.acceptable]
        if final_resp is None:
            con_credit, con_reason = (
                0.0,
                f"No training response recorded. Expected: {' or '.join(_h(e) for e in expected)}.",
            )
        elif final_resp.response in expected:
            con_credit, con_reason = 1.0, f"Response '{_h(final_resp.response)}' matches the rubric. {leaf.rationale}"
        elif final_resp.response in acceptable:
            con_credit, con_reason = (
                0.5,
                f"Response '{_h(final_resp.response)}' is acceptable but not preferred. {leaf.rationale}",
            )
        else:
            con_credit, con_reason = (
                0.0,
                f"Response '{_h(final_resp.response)}' is inconsistent with the rubric. {leaf.rationale}",
            )
        if con_credit < 1.0:
            errors["inconsistent_decisions"].append(
                {
                    "track_id": it.track_id,
                    "response": final_resp.response if final_resp else None,
                    "expected": expected,
                    "acceptable": acceptable,
                    "rationale": leaf.rationale,
                }
            )
        dim_items["consistency"].append({"track_id": it.track_id, "credit": con_credit, "reason": con_reason})

        # --- uncertainty --------------------------------------------------
        evidence_at_decision = None
        if first_cls is not None:
            evidence_at_decision = it.evidence_at(first_cls.t_ms)
            if evidence_at_decision < unc.evidence_threshold:
                confirmed_first = any(
                    r.response == TrainingResponse.REQUEST_SENSOR_CONFIRMATION.value and r.t_ms <= first_cls.t_ms
                    for r in responses
                )
                correct = first_cls.classification == it.true_class
                if confirmed_first:
                    u_credit, u_reason = (
                        unc.credit_confirmation_requested,
                        "Requested sensor confirmation before classifying weak evidence.",
                    )
                elif first_cls.confidence == Confidence.LOW.value:
                    u_credit, u_reason = unc.credit_low_confidence, "Marked low confidence on weak evidence."
                elif first_cls.confidence == Confidence.MEDIUM.value:
                    u_credit, u_reason = unc.credit_medium_confidence, "Medium confidence on weak evidence."
                elif correct:
                    u_credit, u_reason = (
                        unc.credit_high_confidence_correct,
                        "High confidence on weak evidence (correct, but unsupported).",
                    )
                else:
                    u_credit, u_reason = (
                        unc.credit_high_confidence_wrong,
                        "High confidence on weak evidence and incorrect.",
                    )
                    errors["overconfident"].append(
                        {
                            "track_id": it.track_id,
                            "evidence": evidence_at_decision,
                            "given": first_cls.classification,
                            "true_class": it.true_class,
                        }
                    )
                dim_items["uncertainty"].append(
                    {
                        "track_id": it.track_id,
                        "credit": u_credit,
                        "reason": f"{u_reason} Evidence quality {evidence_at_decision:.2f} "
                        f"< threshold {unc.evidence_threshold:.2f}.",
                    }
                )

        item_rows.append(
            {
                "track_id": it.track_id,
                "entity_id": it.entity.entity_id,
                "true_class": it.true_class,
                "cooperative": it.entity.cooperative,
                "behavior": it.entity.behavior,
                "swarm_member": it.entity.swarm_id is not None,
                "closest_range_m": it.entity.closest_range_m,
                "beacon_observed": beacon,
                "first_available_s": _s(it.first_available_ms),
                "first_classification_s": _s(first_cls.t_ms) if first_cls else None,
                "final_classification": final_cls.classification if final_cls else None,
                "final_confidence": final_cls.confidence if final_cls else None,
                "final_response": final_resp.response if final_resp else None,
                "expected_responses": expected,
                "acceptable_responses": acceptable,
                "decision_leaf": leaf.id,
                "decision_path": path,
                "evidence_at_decision": evidence_at_decision,
                "decisions": len(decs),
            }
        )

    # --- procedure ---------------------------------------------------------
    procedure_rows: list[dict[str, Any]] = []
    for prule in rubric.procedure_rules:
        opportunities = 0
        violations: list[dict[str, Any]] = []
        for it in items:
            decs = decisions.get(it.track_id, [])
            responses = [d for d in decs if d.kind == "respond"]
            if isinstance(prule, ConfirmBeforeClearRule):
                for r in responses:
                    if r.response != TrainingResponse.LOG_AS_CLEARED.value:
                        continue
                    evidence = it.evidence_at(r.t_ms)
                    if evidence >= prule.evidence_threshold:
                        continue
                    opportunities += 1
                    confirmed = any(
                        x.response == TrainingResponse.REQUEST_SENSOR_CONFIRMATION.value and x.t_ms < r.t_ms
                        for x in responses
                    )
                    if not confirmed:
                        violations.append(
                            {
                                "track_id": it.track_id,
                                "t_s": _s(r.t_ms),
                                "detail": f"Cleared with evidence {evidence:.2f} without requesting confirmation.",
                            }
                        )
            elif isinstance(prule, MinObservationsBeforeClearRule):
                for r in responses:
                    if r.response != TrainingResponse.LOG_AS_CLEARED.value:
                        continue
                    opportunities += 1
                    n = it.visible_obs_count(r.t_ms)
                    if n < prule.min_observations:
                        violations.append(
                            {
                                "track_id": it.track_id,
                                "t_s": _s(r.t_ms),
                                "detail": f"Cleared after {n} observation(s); minimum is {prule.min_observations}.",
                            }
                        )
            elif isinstance(prule, ClassifyBeforeReportRule):
                for r in responses:
                    if r.response not in (
                        TrainingResponse.REPORT_TO_EXERCISE_CONTROL.value,
                        TrainingResponse.LOG_AS_CLEARED.value,
                    ):
                        continue
                    opportunities += 1
                    if not any(d.kind == "classify" and d.t_ms <= r.t_ms for d in decs):
                        violations.append(
                            {
                                "track_id": it.track_id,
                                "t_s": _s(r.t_ms),
                                "detail": f"'{r.response}' submitted before any classification.",
                            }
                        )
        procedure_rows.append(
            {
                "rule": prule.kind,
                "description": prule.description,
                "opportunities": opportunities,
                "violations": violations,
            }
        )
        for v in violations:
            errors["procedure_violations"].append({"rule": prule.kind, **v})
        if opportunities:
            dim_items["procedure"].append(
                {
                    "track_id": None,
                    "rule": prule.kind,
                    "credit": 1.0 - len(violations) / opportunities,
                    "reason": f"{prule.description} "
                    f"{opportunities - len(violations)} of {opportunities} opportunities compliant.",
                }
            )

    # --- objectives --------------------------------------------------------
    objective_rows = _evaluate_objectives(scenario, items, decisions)
    for row in objective_rows:
        if row["status"] != "not_assessable":
            dim_items["objectives"].append(
                {
                    "objective_id": row["id"],
                    "track_id": None,
                    "credit": 1.0 if row["status"] == "met" else 0.0,
                    "reason": row["detail"],
                }
            )

    # --- aggregate ---------------------------------------------------------
    weights = rubric.weights.as_dict()
    dimensions: dict[str, Any] = {}
    applicable_weight = sum(weights[d] for d in DIMENSIONS if dim_items[d])
    overall_raw = 0.0
    for d in DIMENSIONS:
        rows = dim_items[d]
        if not rows:
            dimensions[d] = {
                "label": DIMENSION_LABELS[d],
                "applicable": False,
                "score": None,
                "weight": weights[d],
                "effective_weight": 0.0,
                "contribution": 0.0,
                "summary": _na_reason(d),
                "items": [],
            }
            continue
        score = 100.0 * sum(r["credit"] for r in rows) / len(rows)
        eff = weights[d] / applicable_weight if applicable_weight else 0.0
        overall_raw += score * eff
        dimensions[d] = {
            "label": DIMENSION_LABELS[d],
            "applicable": True,
            "score": round(score, 1),
            "weight": weights[d],
            "effective_weight": round(eff, 4),
            "contribution": round(score * eff, 2),
            "summary": f"{DIMENSION_LABELS[d]}: mean credit {score:.1f}% over {len(rows)} item(s).",
            "items": [{**r, "credit": round(r["credit"], 4)} for r in rows],
        }

    overall = round(overall_raw, 1)
    classified = sum(1 for r in item_rows if r["final_classification"] is not None)
    result = {
        **base,
        "status": "scored",
        "overall": overall,
        "passed": overall >= rubric.pass_mark,
        "explanation": "Overall score is the weighted mean of applicable dimensions. "
        "Weights of non-applicable dimensions are redistributed proportionally.",
        "dimensions": dimensions,
        "items": item_rows,
        "objectives": objective_rows,
        "procedure": procedure_rows,
        "errors": errors,
        "feedback": _feedback(dimensions, objective_rows, errors),
        "counts": {
            "observable_tracks": len(items),
            "classified_tracks": classified,
            "ignored_decisions": len(ignored),
        },
    }
    return result


def _empty_errors() -> dict[str, list[dict[str, Any]]]:
    return {
        "incorrect_classifications": [],
        "missed_tracks": [],
        "inconsistent_decisions": [],
        "procedure_violations": [],
        "overconfident": [],
    }


def _na_reason(dim: str) -> str:
    return {
        "recognition": "No observable tracks.",
        "timing": "No classifications were submitted, so decision timing cannot be assessed.",
        "consistency": "No observable tracks.",
        "uncertainty": "No classification was made on weak evidence, so uncertainty handling was not tested.",
        "objectives": "No objective could be assessed with the tracks observed in this session.",
        "procedure": "No action created an opportunity to apply the procedural rules.",
    }[dim]


def _evaluate_objectives(
    scenario: Scenario, items: list[_Item], decisions: dict[str, list[Decision]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for obj in scenario.learning_objectives:
        c = obj.criterion
        row: dict[str, Any] = {"id": obj.id, "description": obj.description, "kind": c.kind}
        if isinstance(c, ClassifyCorrectlyCriterion):
            pool = [i for i in items if i.true_class == c.entity_class.value]
            if not pool:
                row.update(status="not_assessable", detail=f"No {_h(c.entity_class.value)} track was observable.")
            else:
                ok = 0
                for i in pool:
                    cls = [d for d in decisions.get(i.track_id, []) if d.kind == "classify"]
                    if cls and cls[-1].classification == i.true_class:
                        ok += 1
                frac = ok / len(pool)
                row.update(
                    status="met" if frac >= c.min_fraction else "not_met",
                    detail=f"{ok} of {len(pool)} {_h(c.entity_class.value)} track(s) correct "
                    f"({frac:.0%}; required {c.min_fraction:.0%}).",
                )
        elif isinstance(c, RespondWithinCriterion):
            pool = [i for i in items if i.true_class == c.entity_class.value]
            if not pool:
                row.update(status="not_assessable", detail=f"No {_h(c.entity_class.value)} track was observable.")
            else:
                ok = 0
                for i in pool:
                    hit = [
                        d
                        for d in decisions.get(i.track_id, [])
                        if d.kind == "respond"
                        and d.response == c.response.value
                        and (d.t_ms - i.first_available_ms) / 1000.0 <= c.within_s
                    ]
                    ok += 1 if hit else 0
                row.update(
                    status="met" if ok == len(pool) else "not_met",
                    detail=f"{ok} of {len(pool)} {_h(c.entity_class.value)} track(s) received '{_h(c.response.value)}' "
                    f"within {c.within_s:g} s of first observation.",
                )
        elif isinstance(c, NoFalseClearanceCriterion):
            bad = [
                i.track_id
                for i in items
                if i.true_class != EntityClass.BIRD_OR_CLUTTER.value
                and not i.entity.cooperative
                and any(d.response == TrainingResponse.LOG_AS_CLEARED.value for d in decisions.get(i.track_id, []))
            ]
            row.update(
                status="not_met" if bad else "met",
                detail=("Non-cooperative drone track(s) logged as cleared: " + ", ".join(bad))
                if bad
                else "No non-cooperative drone track was logged as cleared.",
            )
        elif isinstance(c, ClassifyAllCriterion):
            n = sum(1 for i in items if any(d.kind == "classify" for d in decisions.get(i.track_id, [])))
            frac = n / len(items)
            row.update(
                status="met" if frac >= c.min_fraction else "not_met",
                detail=f"{n} of {len(items)} observable track(s) classified "
                f"({frac:.0%}; required {c.min_fraction:.0%}).",
            )
        rows.append(row)
    return rows


def _feedback(
    dimensions: dict[str, Any], objectives: list[dict[str, Any]], errors: dict[str, list[dict[str, Any]]]
) -> dict[str, list[str]]:
    strengths: list[str] = []
    improvements: list[str] = []
    scored = {d: v for d, v in dimensions.items() if v["applicable"]}
    for _d, v in sorted(scored.items(), key=lambda kv: -kv[1]["score"]):
        if v["score"] >= 85:
            strengths.append(f"{v['label']} was strong ({v['score']:.1f}%).")
        elif v["score"] < 60:
            improvements.append(f"{v['label']} needs further practice ({v['score']:.1f}%).")
    if errors["missed_tracks"]:
        improvements.append(f"{len(errors['missed_tracks'])} observed track(s) were never classified.")
    if errors["overconfident"]:
        improvements.append(
            f"{len(errors['overconfident'])} high-confidence classification(s) on weak evidence were incorrect; "
            "use low confidence or request sensor confirmation."
        )
    if errors["procedure_violations"]:
        improvements.append(f"{len(errors['procedure_violations'])} procedural rule violation(s) recorded.")
    for o in objectives:
        if o["status"] == "met":
            strengths.append(f"Objective met: {o['description']}")
        elif o["status"] == "not_met":
            improvements.append(f"Objective not met: {o['description']}")
    return {"strengths": strengths, "improvements": improvements}
