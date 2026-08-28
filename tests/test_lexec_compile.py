"""Tests for utils.lexec_compile: compile_and_prove/build_compilation_report/
build_proof_records -- the non-DMN half of Phase 1's live-pipeline wiring
(see agents/agent_11_executable_model_generator.py's _lower_and_prove)."""

from __future__ import annotations

from utils.lexec_compile import build_compilation_report, build_proof_records, compile_and_prove


def _ref(text="An LTV cap of 80 percent applies."):
    return {"chunk_path": "fixture/mortgage.txt", "section_id": "s1", "source_text": text, "start_offset": 0, "end_offset": len(text)}


def _rule(rule_id="R-1"):
    return {
        "schema_version": "2.0",
        "rule_id": rule_id,
        "rule_type": "constraint",
        "condition_predicates": [{"predicate_id": "p1", "variable": "ltv_ratio_percent", "operator": ">", "value": 80, "value_type": "number"}],
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
        "source_reference": _ref(),
    }


def _broken_rule(rule_id="R-broken"):
    # Has typed variables but no condition_predicates -> MISSING_PREDICATES,
    # not the earlier MISSING_VARIABLES refusal.
    return {
        "schema_version": "2.0", "rule_id": rule_id, "rule_type": "constraint",
        "variables": [{"name": "x", "type": "boolean", "role": "input"}],
        "source_reference": _ref(),
    }


def test_compile_and_prove_attaches_a_real_proof_not_the_default_unknown():
    ir = compile_and_prove({"business_rules": [_rule()]}, document_id="test-doc")
    assert len(ir["rules"]) == 1
    assert len(ir["tables"]) == 1
    assert ir["tables"][0]["policy_proof"]["status"] == "proved"  # a single-rule UNIQUE table is trivially provable


def test_build_compilation_report_summarizes_compiled_and_refused():
    ir = compile_and_prove({"business_rules": [_rule("R-1"), _broken_rule("R-2")]}, document_id="test-doc")
    report = build_compilation_report(ir)
    assert report["document_id"] == "test-doc"
    assert report["rules_compiled"] == 1
    assert report["rules_refused"] == 1
    assert report["refusal_codes"] == {"MISSING_PREDICATES": 1}
    assert report["tables"] == 1
    assert report["table_proof_statuses"] == {"proved": 1}


def test_build_proof_records_exports_one_record_per_table():
    ir = compile_and_prove({"business_rules": [_rule()]}, document_id="test-doc")
    records = build_proof_records(ir)
    assert records["document_id"] == "test-doc"
    assert len(records["proofs"]) == 1
    assert records["proofs"][0]["policy_proof"]["status"] == "proved"
    assert records["proofs"][0]["rule_ids"] == ["R-1"]
