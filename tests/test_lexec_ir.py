"""Contract tests for the LExec IR v1 boundary."""

from __future__ import annotations

from copy import deepcopy

from utils.lexec_ir import lower_graph, validate_ir


SOURCE_HASH = "a" * 64


def _ref(text="The customer is active and the category is pii."):
    return {
        "chunk_path": "fixture/policy.txt",
        "section_id": "privacy",
        "source_text": text,
        "start_offset": 10,
        "end_offset": 10 + len(text),
    }


def _rule(**overrides):
    rule = {
        "schema_version": "2.0",
        "rule_id": "r_active_pii",
        "rule_type": "collection",
        "condition_predicates": [
            {"predicate_id": "p_active", "variable": "active", "operator": "==", "value": True, "value_type": "boolean"},
            {"predicate_id": "p_category", "variable": "category", "operator": "==", "value": "pii", "value_type": "enum"},
        ],
        "condition_logic": {"all": [{"predicate_ref": "p_active"}, {"predicate_ref": "p_category"}]},
        "outcomes": [{"variable": "decision", "operator": "=", "value": "allow", "value_type": "enum"}],
        "variables": [
            {"name": "active", "type": "boolean", "role": "input"},
            {"name": "category", "type": "enum", "allowed_values": ["pii", "anonymous"], "role": "input"},
            {"name": "decision", "type": "enum", "allowed_values": ["allow", "deny"], "role": "output"},
        ],
        "recommended_hit_policy": "UNIQUE",
        "applicability_scope": {"loan_types": [], "occupancy_types": [], "transaction_types": []},
        "scope_basis": "genuinely_unscoped",
        "responsible_party": "FIRST_PARTY",
        "counterparties": [],
        "exceptions": [],
        "mandatory": True,
        "source_reference": _ref(),
        "field_evidence": {"condition_predicates": [_ref()], "outcomes": [_ref()], "exceptions": [_ref()]},
    }
    rule.update(overrides)
    return rule


def test_lower_graph_emits_complete_ir_with_provenance_and_table():
    ir = lower_graph({"business_rules": [_rule()]}, document_id="fixture", source_sha256=SOURCE_HASH)

    assert validate_ir(ir) == []
    assert len(ir["rules"]) == 1
    assert ir["refusals"] == []
    assert {symbol["id"] for symbol in ir["symbols"]} == {"active", "category", "decision"}
    assert ir["rules"][0]["condition"] == {
        "op": "and",
        "args": [
            {"op": "eq", "left": {"symbol": "active"}, "right": {"literal": True, "type": "bool"}},
            {"op": "eq", "left": {"symbol": "category"}, "right": {"literal": "pii", "type": "enum"}},
        ],
    }
    assert ir["rules"][0]["effects"][0]["modality"] == "obligation"
    assert ir["tables"][0]["policy_proof"]["status"] == "unknown"
    assert ir["tables"][0]["policy_proof"]["method"] == "unproved"
    assert ir["rules"][0]["provenance"][0]["source_sha256"] == SOURCE_HASH
    assert ir["ignored_fields"] == []


def test_string_contains_and_null_are_explicitly_represented():
    rule = _rule(
        rule_id="r_string",
        condition_predicates=[
            {"predicate_id": "p_contains", "variable": "note", "operator": "contains", "value": "urgent", "value_type": "string"},
        ],
        condition_logic={"predicate_ref": "p_contains"},
        variables=[
            {"name": "note", "type": "string", "free_text": True, "role": "input"},
            {"name": "decision", "type": "enum", "allowed_values": ["allow"], "role": "output"},
        ],
        outcomes=[{"variable": "decision", "operator": "=", "value": "allow", "value_type": "enum"}],
    )
    ir = lower_graph([rule], source_sha256=SOURCE_HASH)
    assert validate_ir(ir) == []
    assert ir["rules"][0]["condition"]["op"] == "contains"
    assert ir["symbols"][1]["domain"] == {"kind": "string", "predicates": ["contains"]} or ir["symbols"][0]["domain"] == {"kind": "string", "predicates": ["contains"]}


def test_unsupported_type_is_refused_without_partial_rule():
    rule = _rule(
        rule_id="r_date",
        variables=[
            {"name": "active", "type": "date", "role": "input"},
            {"name": "decision", "type": "enum", "allowed_values": ["allow"], "role": "output"},
        ],
        condition_predicates=[{"predicate_id": "p", "variable": "active", "operator": "==", "value": "2026-01-01", "value_type": "date"}],
        condition_logic={"predicate_ref": "p"},
        outcomes=[{"variable": "decision", "operator": "=", "value": "allow", "value_type": "enum"}],
    )
    ir = lower_graph([rule], source_sha256=SOURCE_HASH)
    assert ir["rules"] == []
    assert len(ir["refusals"]) == 1
    assert ir["refusals"][0]["code"] == "UNSUPPORTED_VARIABLE_TYPE"
    assert ir["refusals"][0]["requires_review"] is True
    assert validate_ir(ir) == []


def test_non_executable_annotations_are_accounted_for_not_dropped():
    rule = _rule(description="annotation", confidence_score=42, test_vectors=[])
    ir = lower_graph([rule], source_sha256=SOURCE_HASH)
    assert ir["rules"]
    assert {entry["field"] for entry in ir["ignored_fields"]} == {"description", "confidence_score", "test_vectors"}
    assert {entry["reason"] for entry in ir["ignored_fields"]} == {"NON_EXECUTABLE_METADATA", "AUDIT_STATUS_NOT_EXECUTABLE"}
    assert validate_ir(ir) == []


def test_invalid_ir_cross_reference_is_detected():
    ir = lower_graph([_rule()], source_sha256=SOURCE_HASH)
    broken = deepcopy(ir)
    broken["rules"][0]["condition"]["args"][0]["left"]["symbol"] = "missing"
    errors = validate_ir(broken)
    assert any("unknown symbol 'missing'" in error for error in errors)


def test_unknown_input_field_is_refused_instead_of_silently_lost():
    rule = _rule(future_semantics={"new": "meaning"})
    ir = lower_graph([rule], source_sha256=SOURCE_HASH)
    assert ir["rules"] == []
    assert ir["refusals"][0]["code"] == "UNCLASSIFIED_FIELD"
    assert ir["ignored_fields"] == []
