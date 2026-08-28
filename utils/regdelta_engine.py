"""RegDelta differential-execution engine (plan/proposal.md Section 6,
plan/regdelta-product-plan.md Section 6-7 Phases 1-3).

Orchestrates the pieces that exist independently elsewhere -- compilation
(``utils.lexec_ir.lower_graph``), alignment (``utils.rule_alignment``),
semantic classification (``utils.semantic_diff``), and impact propagation
(``utils.impact_propagation``) -- into one ``diff_graphs`` entry point that
takes two v2 rule graphs plus a scenario cohort and produces an impact
report shaped like plan/proposal.md Section 12's contract.

Rule-level scenario evaluation is deliberately NOT ``utils.feel.evaluate_ir``.
That evaluator's contextual-scope block (any populated jurisdiction/party/
effective-date metadata forces ``unknown`` -- a correct, deliberately tested
safety property for "is this rule in force for a real transaction", see
``tests/test_feel.py::test_contextual_scope_and_collect_are_not_silently_executed``)
answers the wrong question for a document-version differential, which asks
"does this rule's own logic differ between two whole, already-selected
document snapshots" -- not whether either snapshot is currently in force.
This module instead evaluates each rule's ``scope.predicate`` (loan/
transaction/occupancy-type gating -- see ``utils.lexec_ir``), ``condition``,
``exceptions``, and ``effects`` directly via the same side-effect-free
``evaluate_formula`` primitive ``utils.feel._evaluate_rule`` is built from.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from utils.feel import UNKNOWN, evaluate_formula
from utils.impact_propagation import direct_set, potential_set, recompute_set, resolve_statuses
from utils.lexec_ir import lower_graph
from utils.rule_alignment import align_by_id, rules_by_id
from utils.semantic_diff import classify_change


SCHEMA_VERSION = "regdelta-impact/1.0"


def _resolve_operand(value: Any, environment: Mapping[str, Any]) -> Any:
    if isinstance(value, Mapping) and set(value) == {"symbol"}:
        return environment.get(value.get("symbol"), UNKNOWN)
    if isinstance(value, Mapping) and set(value) == {"literal", "type"}:
        return value.get("literal")
    return UNKNOWN


def evaluate_rule_for_diff(rule: Mapping[str, Any], inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate one compiled IR rule for document-version comparison.

    Same three-valued (matched/no_match/unknown/defeated) semantics as
    ``utils.feel._evaluate_rule``, except contextual scope metadata
    (jurisdictions/parties/effective dates) is not checked -- see the module
    docstring for why. ``scope.predicate`` (loan/transaction/occupancy type
    gating) *is* checked, exactly like the rule's own ``condition``.
    """

    scope = rule.get("scope") if isinstance(rule.get("scope"), Mapping) else {}
    predicate = scope.get("predicate")
    if predicate is not None:
        scope_value = evaluate_formula(predicate, inputs)
        if scope_value is False:
            return {"status": "no_match", "outputs": {}, "reason": None}
        if scope_value is not True:
            return {"status": "unknown", "outputs": {}, "reason": "scope predicate is unknown"}
    condition = evaluate_formula(rule.get("condition"), inputs)
    if condition is False:
        return {"status": "no_match", "outputs": {}, "reason": None}
    if condition is not True:
        return {"status": "unknown", "outputs": {}, "reason": "rule condition is unknown"}
    environment = dict(inputs)
    unknown_exception = False
    for exception in rule.get("exceptions", []) or []:
        value = evaluate_formula(exception.get("condition"), environment)
        if value is True:
            return {"status": "defeated", "outputs": {}, "reason": None}
        if value is UNKNOWN:
            unknown_exception = True
    if unknown_exception:
        return {"status": "unknown", "outputs": {}, "reason": "exception condition is unknown"}
    outputs: dict[str, Any] = {}
    for effect in rule.get("effects", []) or []:
        value = _resolve_operand(effect.get("value"), environment)
        if value is UNKNOWN:
            return {"status": "unknown", "outputs": {}, "reason": "effect value is unknown"}
        outputs[str(effect.get("target"))] = value
    return {"status": "matched", "outputs": outputs, "reason": None}


def _compile(graph: Mapping[str, Any], *, document_id: str) -> dict[str, Any]:
    return lower_graph(graph, document_id=document_id)


def _refusal_reasons(ir: Mapping[str, Any]) -> dict[str, str]:
    return {str(refusal.get("rule_id")): str(refusal.get("code")) for refusal in ir.get("refusals", []) if refusal.get("rule_id")}


def build_changes(old_ir: Mapping[str, Any], new_ir: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Align two compiled IR documents by rule ID and classify each pair.

    Returns ``(alignments, changes)``. ``changes`` covers every rule ID
    compiled on at least one side: ``added``/``removed`` for rules compiled
    on only one side, and ``utils.semantic_diff.classify_change``'s result
    for rules compiled on both.
    """

    old_rules, new_rules = rules_by_id(old_ir), rules_by_id(new_ir)
    alignments = align_by_id(list(old_rules), list(new_rules))
    changes: dict[str, dict[str, Any]] = {}
    for alignment in alignments:
        if alignment["kind"] == "added":
            changes[alignment["new_rule_ids"][0]] = {"taxonomy": "added", "detail": None}
        elif alignment["kind"] == "removed":
            changes[alignment["old_rule_ids"][0]] = {"taxonomy": "removed", "detail": None}
        else:
            rule_id = alignment["old_rule_ids"][0]
            changes[rule_id] = classify_change(old_rules[rule_id], new_rules[rule_id])
    return alignments, changes


def diff_graphs(
    old_graph: Mapping[str, Any],
    new_graph: Mapping[str, Any],
    *,
    universe_rule_ids: Sequence[str],
    dag_edges: Sequence[tuple[str, str]],
    review_status: Mapping[str, bool],
    scenarios: Sequence[Mapping[str, Any]] = (),
    pair_id: str = "unnamed-pair",
) -> dict[str, Any]:
    """Compile, align, classify, propagate, and replay one old/new pair.

    ``universe_rule_ids`` is the full set of rule IDs this run is
    responsible for reporting a status on (every one gets an entry in
    ``downstream_impacts``, even if it never compiled on either side).
    ``review_status`` maps rule ID -> ``requires_review`` (from the source
    v2 graph; the compiled IR does not retain this value -- see
    ``utils.lexec_ir.IGNORED_FIELD_REASONS``).
    """

    old_ir = _compile(old_graph, document_id=f"{pair_id}-old")
    new_ir = _compile(new_graph, document_id=f"{pair_id}-new")
    alignments, changes = build_changes(old_ir, new_ir)

    direct = direct_set(changes)
    potential = potential_set(direct, dag_edges)
    recompute = recompute_set(potential=potential, direct=direct, review_status=review_status)
    statuses = resolve_statuses(universe=universe_rule_ids, potential=potential, review_status=review_status, changes=changes)

    old_rules, new_rules = rules_by_id(old_ir), rules_by_id(new_ir)
    old_refusals, new_refusals = _refusal_reasons(old_ir), _refusal_reasons(new_ir)
    affected_cases: list[dict[str, Any]] = []
    witnesses: list[dict[str, Any]] = []
    for scenario in scenarios:
        case_id = scenario.get("case_id")
        inputs = scenario.get("inputs", {})
        targets = scenario.get("targets") or sorted(set(old_rules) | set(new_rules))
        case_record: dict[str, Any] = {"case_id": case_id, "rule_results": {}}
        for rule_id in targets:
            old_rule, new_rule = old_rules.get(rule_id), new_rules.get(rule_id)
            if old_rule is None or new_rule is None:
                continue
            old_result = evaluate_rule_for_diff(old_rule, inputs)
            new_result = evaluate_rule_for_diff(new_rule, inputs)
            differs = old_result != new_result
            case_record["rule_results"][rule_id] = {"old": old_result, "new": new_result, "differs": differs}
            if differs:
                witnesses.append({"case_id": case_id, "rule_id": rule_id, "old_result": old_result, "new_result": new_result})
        affected_cases.append(case_record)

    refusals = [
        {"rule_id": rule_id, "old_code": old_refusals.get(rule_id), "new_code": new_refusals.get(rule_id)}
        for rule_id in universe_rule_ids
        if statuses.get(rule_id, {}).get("status") == "refused-unsupported-construct"
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "pair_id": pair_id,
        "rule_alignments": alignments,
        "semantic_changes": [{"rule_id": rule_id, **change} for rule_id, change in sorted(changes.items())],
        "affected_cases": affected_cases,
        "witnesses": witnesses,
        "downstream_impacts": {
            "direct": sorted(direct),
            "potential": sorted(potential),
            "recompute": sorted(recompute),
            "statuses": {rule_id: statuses[rule_id] for rule_id in universe_rule_ids},
        },
        "refusals": refusals,
        "provenance": {
            "old_document_id": old_ir["document_unit"]["document_id"],
            "new_document_id": new_ir["document_unit"]["document_id"],
            "old_source_sha256": old_ir["document_unit"]["source_sha256"],
            "new_source_sha256": new_ir["document_unit"]["source_sha256"],
        },
        "metrics": {
            "universe_size": len(universe_rule_ids),
            "compiled_old": len(old_ir.get("rules", [])),
            "compiled_new": len(new_ir.get("rules", [])),
            "direct_count": len(direct),
            "potential_count": len(potential),
            "recompute_count": len(recompute),
            "unresolved_review_count": sum(1 for status in statuses.values() if status["status"] == "unresolved-review"),
            "refused_count": len(refusals),
        },
    }
