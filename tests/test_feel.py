"""Reference evaluator tests for the declared LExec IR subset."""

from __future__ import annotations

from utils.feel import evaluate_formula, evaluate_ir


def _span():
    return [{"chunk_path": "fixture.txt", "section_id": "s1", "start_offset": 0, "end_offset": 1, "source_sha256": "a" * 64}]


def _ir(condition, *, proof_status="proved", policy="UNIQUE", exceptions=None, metadata=None, effects=None):
    symbols = [
        {"id": "active", "theory": "bool", "role": "input", "domain": {"kind": "boolean"}, "unit": None, "derived_expression": None, "provenance": _span()},
        {"id": "decision", "theory": "enum", "role": "output", "domain": {"kind": "enum", "values": ["allow", "deny"]}, "unit": None, "derived_expression": None, "provenance": _span()},
    ]
    rule = {"id": "r1", "scope": {"predicate": None, "metadata": metadata or {}}, "condition": condition, "exceptions": exceptions or [], "effects": effects or [{"kind": "assignment", "modality": "obligation", "target": "decision", "value": {"literal": "allow", "type": "enum"}, "provenance": _span()}], "provenance": _span()}
    return {
        "schema_version": "lexec-ir/1.0",
        "document_unit": {"document_id": "fixture", "source_sha256": "a" * 64, "source_paths": ["fixture.txt"], "corpus_id": None, "split": None},
        "semantics": {"null_model": "kleene_three_valued", "unknown_at_table_boundary": "refuse", "exception_reading": "defeater_or"},
        "symbols": symbols,
        "rules": [rule],
        "tables": [{"id": "t1", "rule_ids": ["r1"], "output_signature": ["decision"], "hit_policy": policy, "policy_proof": {"status": proof_status, "method": "pairwise_disjointness", "solver": "fixture", "query_sha256": "b" * 64, "witnesses": []}}],
        "refusals": [],
        "ignored_fields": [],
    }


def _active(value=True):
    return {"op": "eq", "left": {"symbol": "active"}, "right": {"literal": value, "type": "bool"}}


def test_formula_evaluation_uses_kleene_unknown():
    assert evaluate_formula(_active(), {"active": True}) is True
    assert evaluate_formula(_active(), {"active": False}) is False
    assert evaluate_formula(_active(), {}) is None


def test_proved_unique_table_matches_and_returns_assignment():
    result = evaluate_ir(_ir(_active()), {"active": True}, table_id="t1")
    assert result["status"] == "matched"
    assert result["matched_rule_ids"] == ["r1"]
    assert result["outputs"] == {"decision": "allow"}


def test_false_condition_is_no_match_and_unknown_input_is_not_false():
    ir = _ir(_active())
    assert evaluate_ir(ir, {"active": False}, table_id="t1")["status"] == "no_match"
    unknown = evaluate_ir(ir, {}, table_id="t1")
    assert unknown["status"] == "unknown"
    assert unknown["unknown_rule_ids"] == ["r1"]


def test_unproved_policy_fails_closed_before_evaluation():
    result = evaluate_ir(_ir(_active(), proof_status="unknown"), {"active": True}, table_id="t1")
    assert result["status"] == "refused"
    assert result["diagnostics"][0]["code"] == "UNPROVED_TABLE_POLICY"


def test_exception_defeats_match_and_unknown_exception_propagates():
    exception = {"id": "e1", "condition": {"op": "eq", "left": {"symbol": "active"}, "right": {"literal": True, "type": "bool"}}, "provenance": _span()}
    ir = _ir(_active(), exceptions=[exception])
    defeated = evaluate_ir(ir, {"active": True}, table_id="t1")
    assert defeated["status"] == "no_match"
    assert defeated["matched_rule_ids"] == []
    unknown = evaluate_ir(ir, {}, table_id="t1")
    assert unknown["status"] == "unknown"


def test_contextual_scope_and_collect_are_not_silently_executed():
    scoped = evaluate_ir(_ir(_active(), metadata={"jurisdictions": ["US"]}), {"active": True}, table_id="t1")
    assert scoped["status"] == "unknown"
    collect = evaluate_ir(_ir(_active(), policy="COLLECT"), {"active": True}, table_id="t1")
    assert collect["status"] == "refused"
    assert collect["diagnostics"][0]["code"] == "COLLECT_NOT_IMPLEMENTED"


def test_invalid_ir_and_missing_table_are_refused():
    invalid = evaluate_ir({"rules": []}, {}, table_id="t1")
    assert invalid["status"] == "refused"
    assert invalid["diagnostics"][0]["code"] == "INVALID_IR"
    missing = evaluate_ir(_ir(_active()), {"active": True}, table_id="missing")
    assert missing["status"] == "refused"
    assert missing["diagnostics"][0]["code"] == "UNKNOWN_TABLE"
