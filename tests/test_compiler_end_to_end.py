"""End-to-end compiler and backend regression tests."""

from __future__ import annotations

import json
import sys

from bench.dmn_engine_harness import run_crosscheck
from utils.dmn_emit import emit_dmn, validate_dmn
from utils.feel import evaluate_ir
from utils.lexec_ir import lower_graph, validate_ir
from utils.smt import annotate_policy_proofs


SOURCE_HASH = "c" * 64


def _span(text: str = "The customer is active."):
    return {
        "chunk_path": "fixture/policy.txt",
        "section_id": "policy",
        "source_text": text,
        "start_offset": 0,
        "end_offset": len(text),
    }


def _v2_rule(*, duplicate_outcome: bool = False):
    outcomes = [{"variable": "decision", "operator": "=", "value": "allow", "value_type": "enum"}]
    if duplicate_outcome:
        outcomes.append({"variable": "decision", "operator": "=", "value": "deny", "value_type": "enum"})
    return {
        "schema_version": "2.0",
        "rule_id": "r_active",
        "rule_type": "collection",
        "condition_predicates": [{"predicate_id": "p_active", "variable": "active", "operator": "==", "value": True, "value_type": "boolean"}],
        "condition_logic": {"predicate_ref": "p_active"},
        "outcomes": outcomes,
        "variables": [
            {"name": "active", "type": "boolean", "role": "input"},
            {"name": "decision", "type": "enum", "allowed_values": ["allow", "deny"], "role": "output"},
        ],
        "recommended_hit_policy": "UNIQUE",
        "applicability_scope": {"loan_types": [], "occupancy_types": [], "transaction_types": []},
        "scope_basis": "genuinely_unscoped",
        "responsible_party": None,
        "counterparties": [],
        "exceptions": [],
        "mandatory": True,
        "source_reference": _span(),
        "field_evidence": {"condition_predicates": [_span()], "outcomes": [_span()]},
    }


def _xml_adapter_command():
    code = r"""
import json
import sys
import xml.etree.ElementTree as ET

for line in sys.stdin:
    request = json.loads(line)
    root = ET.fromstring(request["dmn_xml"])
    output_text = root.find(".//{*}outputEntry/{*}text").text
    matched = request["inputs"].get("active") is True
    outputs = {"decision": json.loads(output_text)} if matched else {}
    print(json.dumps({
        "protocol": request["protocol"],
        "case_id": request["case_id"],
        "status": "matched" if matched else "no_match",
        "outputs": outputs,
        "matched_rule_ids": ["r_active"] if matched else [],
        "unknown_rule_ids": [],
    }))
"""
    return [sys.executable, "-c", code]


def test_v2_to_ir_to_proof_to_reference_to_dmn_to_engine_adapter():
    lowered = lower_graph({"business_rules": [_v2_rule()]}, document_id="e2e", source_sha256=SOURCE_HASH)
    assert validate_ir(lowered) == []
    assert lowered["tables"][0]["policy_proof"]["status"] == "unknown"

    proven = annotate_policy_proofs(lowered)
    assert validate_ir(proven) == []
    assert proven["tables"][0]["policy_proof"]["status"] == "proved"

    matched = evaluate_ir(proven, {"active": True}, table_id="table_1")
    no_match = evaluate_ir(proven, {"active": False}, table_id="table_1")
    assert matched["status"] == "matched" and matched["outputs"] == {"decision": "allow"}
    assert no_match["status"] == "no_match"

    dmn = emit_dmn(proven)
    assert validate_dmn(dmn) == []
    report = run_crosscheck(
        proven,
        [
            {"case_id": "active", "table_id": "table_1", "inputs": {"active": True}},
            {"case_id": "inactive", "table_id": "table_1", "inputs": {"active": False}},
        ],
        engine_command=_xml_adapter_command(),
        engine_metadata={
            "engine_id": "xml-fixture-adapter",
            "engine_version": "1.0",
            "source": "https://example.invalid/xml-fixture-adapter",
            "revision": "fixture",
            "license": "MIT",
            "artifact_sha256": "d" * 64,
        },
    )
    assert report["status"] == "completed"
    assert report["claimable"] is True
    assert report["summary"] == {"total": 2, "agree": 2, "disagree": 0}


def test_malformed_nested_ir_is_reported_instead_of_raising():
    ir = lower_graph({"business_rules": [_v2_rule()]}, document_id="malformed", source_sha256=SOURCE_HASH)
    ir["rules"][0]["effects"] = [None]
    ir["rules"][0]["exceptions"] = "not-an-array"
    ir["rules"][0]["provenance"] = 7
    ir["symbols"][0]["provenance"] = 7
    ir["tables"][0]["rule_ids"] = "r_active"

    errors = validate_ir(ir)
    assert any("effects[0]: malformed effect" in error for error in errors)
    assert any("exceptions: exceptions must be an array" in error for error in errors)
    assert any("provenance must be an array" in error for error in errors)
    assert any("rule_ids must be a non-empty array" in error for error in errors)
    assert evaluate_ir(ir, {"active": True}, table_id="table_1")["status"] == "refused"


def test_empty_ir_has_no_implicit_unproved_unique_execution():
    empty = lower_graph([], document_id="empty", source_sha256=SOURCE_HASH)
    assert validate_ir(empty) == []
    result = evaluate_ir(empty, {})
    assert result["status"] == "refused"
    assert result["diagnostics"][0]["code"] == "NO_EXECUTABLE_TABLE"


def test_duplicate_outcomes_are_refused_at_lowering_boundary():
    ir = lower_graph([_v2_rule(duplicate_outcome=True)], source_sha256=SOURCE_HASH)
    assert ir["rules"] == []
    assert ir["refusals"][0]["code"] == "DUPLICATE_OUTCOME_TARGET"
    assert ir["refusals"][0]["requires_review"] is True
