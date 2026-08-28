"""Unit tests for the RegDelta alignment/semantic-diff/propagation/engine
modules, against small synthetic graphs -- not the real mortgage fixture
(see tests/test_mortgage_tier1_fixture.py for that).
"""

from __future__ import annotations

from copy import deepcopy

from utils.impact_propagation import direct_set, potential_set, recompute_set, resolve_statuses
from utils.regdelta_engine import build_changes, diff_graphs, evaluate_rule_for_diff
from utils.rule_alignment import align_by_id
from utils.semantic_diff import classify_change


def _ref(text="An LTV cap of 80 percent applies."):
    return {"chunk_path": "fixture/mortgage.txt", "section_id": "s1", "source_text": text, "start_offset": 0, "end_offset": len(text)}


def _ltv_rule(rule_id="R-1", *, threshold=80, requires_review=False, related_rules=None):
    return {
        "schema_version": "2.0",
        "rule_id": rule_id,
        "rule_type": "constraint",
        "condition_predicates": [{"predicate_id": "p1", "variable": "ltv_ratio_percent", "operator": ">", "value": threshold, "value_type": "number"}],
        "condition_logic": {"predicate_ref": "p1"},
        "outcomes": [{"variable": "pmi_required", "operator": "=", "value": True, "value_type": "boolean"}],
        "variables": [
            {"name": "ltv_ratio_percent", "type": "number", "role": "input"},
            {"name": "pmi_required", "type": "boolean", "role": "output"},
        ],
        "recommended_hit_policy": "UNIQUE",
        "applicability_scope": {},
        "scope_basis": "genuinely_unscoped",
        "exceptions": [],
        "mandatory": True,
        "requires_review": requires_review,
        "related_rules": related_rules or [],
        "source_reference": _ref(),
    }


def _dependent_rule(rule_id="R-2", requires_review=True):
    # Deliberately uses a *different* variable name than R-1's own output
    # ("insurance_required_flag", not "pmi_required") -- this mirrors the
    # real R-120-004/R-120-003 pair, where the two independently-extracted
    # rules never share an IR symbol at all (see utils.regdelta_engine's
    # module docstring and plan/regdelta-product-plan.md Section 6.5).
    return {
        "schema_version": "2.0",
        "rule_id": rule_id,
        "rule_type": "compliance",
        "condition_predicates": [{"predicate_id": "p1", "variable": "insurance_required_flag", "operator": "==", "value": True, "value_type": "boolean"}],
        "condition_logic": {"predicate_ref": "p1"},
        "outcomes": [{"variable": "evidence_required", "operator": "=", "value": True, "value_type": "boolean"}],
        "variables": [
            {"name": "insurance_required_flag", "type": "boolean", "role": "input"},
            {"name": "evidence_required", "type": "boolean", "role": "output"},
        ],
        "recommended_hit_policy": "UNIQUE",
        "applicability_scope": {},
        "scope_basis": "genuinely_unscoped",
        "exceptions": [],
        "mandatory": True,
        "requires_review": requires_review,
        "source_reference": _ref("Evidence of PMI must be retained."),
    }


# --- utils.rule_alignment ----------------------------------------------------

def test_align_by_id_reports_one_to_one_added_and_removed():
    alignments = align_by_id(["a", "b", "c"], ["b", "c", "d"])
    kinds = {a["kind"]: a for a in alignments}
    assert set(kinds) == {"one_to_one", "added", "removed"}
    ones = sorted((a["old_rule_ids"][0] for a in alignments if a["kind"] == "one_to_one"))
    assert ones == ["b", "c"]
    assert [a["new_rule_ids"] for a in alignments if a["kind"] == "added"] == [["d"]]
    assert [a["old_rule_ids"] for a in alignments if a["kind"] == "removed"] == [["a"]]


# --- utils.semantic_diff ------------------------------------------------------

def test_classify_change_identifies_threshold_change_with_direction():
    from utils.lexec_ir import lower_graph

    old_ir = lower_graph([_ltv_rule(threshold=80)], source_sha256="a" * 64)
    new_ir = lower_graph([_ltv_rule(threshold=78)], source_sha256="b" * 64)
    old_rule, new_rule = old_ir["rules"][0], new_ir["rules"][0]
    result = classify_change(old_rule, new_rule)
    assert result["taxonomy"] == "threshold_or_constant_change"
    assert result["detail"]["op"] == "gt"
    assert result["detail"]["old_literal"] == 80
    assert result["detail"]["new_literal"] == 78
    # gt: a lower threshold admits *more* inputs -- weakening, not strengthening.
    assert result["detail"]["direction"] == "weakening"


def test_classify_change_reports_unchanged_ignoring_provenance():
    from utils.lexec_ir import lower_graph

    old_ir = lower_graph([_ltv_rule()], source_sha256="a" * 64)
    new_ir = lower_graph([_ltv_rule()], source_sha256="b" * 64)  # different document digest, identical rule
    result = classify_change(old_ir["rules"][0], new_ir["rules"][0])
    assert result == {"taxonomy": "unchanged", "detail": None}


def test_classify_change_falls_back_for_multi_field_and_effect_changes():
    from utils.lexec_ir import lower_graph

    old_ir = lower_graph([_ltv_rule()], source_sha256="a" * 64)
    new_rule = deepcopy(_ltv_rule())
    new_rule["outcomes"][0]["value"] = False
    new_ir = lower_graph([new_rule], source_sha256="b" * 64)
    result = classify_change(old_ir["rules"][0], new_ir["rules"][0])
    assert result["taxonomy"] == "output_effect_change"


# --- utils.impact_propagation --------------------------------------------------

def test_direct_potential_recompute_and_status_resolution():
    changes = {
        "R-1": {"taxonomy": "threshold_or_constant_change", "detail": {}},
        "R-2": {"taxonomy": "unchanged", "detail": None},
        "R-3": {"taxonomy": "unchanged", "detail": None},
        # R-5 is requires_review and untouched by any change (no edge reaches
        # it) -- its own comparison is trustworthy precisely because nothing
        # upstream of it changed, so it should read "unchanged", not
        # "unresolved-review".
        "R-5": {"taxonomy": "unchanged", "detail": None},
    }
    edges = [("R-1", "R-2"), ("R-2", "R-3")]
    direct = direct_set(changes)
    assert direct == {"R-1"}
    potential = potential_set(direct, edges)
    assert potential == {"R-1", "R-2", "R-3"}

    review_status = {"R-1": False, "R-2": True, "R-3": False, "R-5": True}
    recompute = recompute_set(potential=potential, direct=direct, review_status=review_status)
    # R-2 is requires_review -- excluded from recompute despite being downstream.
    assert recompute == {"R-3"}

    statuses = resolve_statuses(universe=["R-1", "R-2", "R-3", "R-4", "R-5"], potential=potential, review_status=review_status, changes=changes)
    assert statuses["R-1"]["status"] == "threshold_or_constant_change"
    assert statuses["R-2"]["status"] == "unresolved-review"  # requires_review AND reached by R-1's change
    assert statuses["R-3"]["status"] == "unchanged"
    assert statuses["R-4"]["status"] == "refused-unsupported-construct"  # no entry in `changes` at all
    assert statuses["R-5"]["status"] == "unchanged"  # requires_review but never reached -- own comparison stands


def test_resolve_statuses_refuses_rules_missing_from_changes():
    statuses = resolve_statuses(universe=["R-9"], potential={"R-9"}, review_status={}, changes={})
    assert statuses["R-9"]["status"] == "refused-unsupported-construct"


# --- utils.regdelta_engine -----------------------------------------------------

def test_evaluate_rule_for_diff_matches_no_match_and_unknown():
    from utils.lexec_ir import lower_graph

    ir = lower_graph([_ltv_rule(threshold=80)], source_sha256="a" * 64)
    rule = ir["rules"][0]
    assert evaluate_rule_for_diff(rule, {"ltv_ratio_percent": 90})["status"] == "matched"
    assert evaluate_rule_for_diff(rule, {"ltv_ratio_percent": 90})["outputs"] == {"pmi_required": True}
    assert evaluate_rule_for_diff(rule, {"ltv_ratio_percent": 50})["status"] == "no_match"
    assert evaluate_rule_for_diff(rule, {})["status"] == "unknown"


def test_build_changes_covers_added_removed_and_one_to_one():
    from utils.lexec_ir import lower_graph

    old_ir = lower_graph([_ltv_rule("R-1"), _ltv_rule("R-2")], source_sha256="a" * 64)
    new_ir = lower_graph([_ltv_rule("R-1", threshold=78), _ltv_rule("R-3")], source_sha256="b" * 64)
    alignments, changes = build_changes(old_ir, new_ir)
    assert {a["kind"] for a in alignments} == {"one_to_one", "added", "removed"}
    assert changes["R-1"]["taxonomy"] == "threshold_or_constant_change"
    assert changes["R-2"] == {"taxonomy": "removed", "detail": None}
    assert changes["R-3"] == {"taxonomy": "added", "detail": None}


def test_diff_graphs_end_to_end_reproduces_the_r120004_r120003_shape():
    """A stand-in for the real R-120-004 -> R-120-003 cluster: an edited,
    non-review rule with a review-required downstream dependent that shares
    no IR symbol with it (see plan/regdelta-product-plan.md Section 6.5)."""

    old_graph = {"business_rules": [_ltv_rule("R-1", threshold=80, requires_review=False), _dependent_rule("R-2", requires_review=True)]}
    new_graph = {"business_rules": [_ltv_rule("R-1", threshold=78, requires_review=False), _dependent_rule("R-2", requires_review=True)]}
    universe = ["R-1", "R-2"]
    dag_edges = [("R-1", "R-2")]
    review_status = {"R-1": False, "R-2": True}
    scenarios = [
        {"case_id": "boundary_79", "inputs": {"ltv_ratio_percent": 79, "insurance_required_flag": True}, "targets": ["R-1", "R-2"]},
        {"case_id": "clearly_over_90", "inputs": {"ltv_ratio_percent": 90, "insurance_required_flag": True}, "targets": ["R-1", "R-2"]},
    ]

    report = diff_graphs(
        old_graph, new_graph,
        universe_rule_ids=universe, dag_edges=dag_edges, review_status=review_status,
        scenarios=scenarios, pair_id="test-r120004",
    )

    assert report["schema_version"] == "regdelta-impact/1.0"
    assert report["downstream_impacts"]["direct"] == ["R-1"]
    assert report["downstream_impacts"]["potential"] == ["R-1", "R-2"]
    assert report["downstream_impacts"]["recompute"] == []  # R-2 is requires_review, never recomputed
    assert report["downstream_impacts"]["statuses"]["R-1"]["status"] == "threshold_or_constant_change"
    assert report["downstream_impacts"]["statuses"]["R-2"]["status"] == "unresolved-review"

    boundary = next(case for case in report["affected_cases"] if case["case_id"] == "boundary_79")
    assert boundary["rule_results"]["R-1"]["differs"] is True
    assert boundary["rule_results"]["R-1"]["old"]["status"] == "no_match"  # 79 is not > 80
    assert boundary["rule_results"]["R-1"]["new"]["status"] == "matched"  # 79 is > 78
    over_90 = next(case for case in report["affected_cases"] if case["case_id"] == "clearly_over_90")
    assert over_90["rule_results"]["R-1"]["differs"] is False  # matched on both sides regardless of the edit

    witness_rule_ids = {w["rule_id"] for w in report["witnesses"]}
    assert witness_rule_ids == {"R-1"}
    assert report["metrics"]["unresolved_review_count"] == 1
    assert report["metrics"]["refused_count"] == 0
