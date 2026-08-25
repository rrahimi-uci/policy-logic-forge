"""Edge-case contracts for the scoped compiler/backend coverage gate.

These tests deliberately exercise refusal and unknown paths as well as happy
paths.  The compiler is fail-closed, so those branches are part of its public
contract rather than implementation-only bookkeeping.
"""

from __future__ import annotations

from copy import deepcopy
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from bench import dmn_engine_harness as harness
from tests.test_dmn_builder import _ir as builder_ir
from tests.test_feel import _active, _ir as feel_ir, _span
from tests.test_lexec_ir import _rule as source_rule
from utils import dmn_builder as builder
from utils import lexec_ir
from utils import smt
from utils.dmn_builder import DmnBuildError
from utils.dmn_emit import validate_dmn
from utils.feel import evaluate_formula, evaluate_ir


def _literal(value, value_type="bool"):
    return {"literal": value, "type": value_type}


def _symbol(name="x", theory="bool", domain=None):
    return {
        "id": name,
        "theory": theory,
        "role": "input",
        "domain": domain or {"kind": "boolean"},
    }


def _eq(name="x", value=True, value_type="bool"):
    return {"op": "eq", "left": {"symbol": name}, "right": _literal(value, value_type)}


def test_feel_formula_operators_ranges_and_malformed_values():
    env = {"x": 2, "text": "urgent notice", "none": None}
    assert evaluate_formula(None, env) is None
    assert evaluate_formula({"op": "and", "args": []}, env) is None
    assert evaluate_formula({"op": "or", "args": []}, env) is None
    assert evaluate_formula({"op": "and", "args": [_eq("x", 2, "int"), _eq("x", 3, "int")]}, env) is False
    assert evaluate_formula({"op": "or", "args": [_eq("x", 2, "int"), _eq("x", 3, "int")]}, env) is True
    assert evaluate_formula({"op": "not", "arg": _eq("x", 3, "int")}, env) is True
    assert evaluate_formula({"op": "is_null", "arg": {"symbol": "none"}}, env) is True
    assert evaluate_formula({"op": "is_null", "arg": {"symbol": "missing"}}, env) is True
    assert evaluate_formula({"op": "contains", "left": {"symbol": "text"}, "right": _literal("gent", "string")}, env) is True
    for op, expected in (("ne", True), ("lt", True), ("le", True), ("gt", False), ("ge", False)):
        assert evaluate_formula({"op": op, "left": {"symbol": "x"}, "right": _literal(3, "int")}, env) is expected
    assert evaluate_formula({"op": "in_binned_range", "left": {"symbol": "x"}, "right": _literal("[2, 3)", "string")}, env) is True
    assert evaluate_formula({"op": "in_binned_range", "left": {"symbol": "x"}, "right": _literal("(2, 3)", "string")}, env) is False
    assert evaluate_formula({"op": "in_binned_range", "left": {"symbol": "x"}, "right": _literal("bad", "string")}, env) is None
    assert evaluate_formula({"op": "in_binned_range", "left": {"symbol": "x"}, "right": _literal("[nan, 3]", "string")}, env) is None
    assert evaluate_formula({"op": "eq", "left": {"symbol": "x"}, "right": _literal("x", "string")}, env) is False
    assert evaluate_formula({"op": "unsupported", "arg": _literal(True)}, env) is None


def test_feel_evaluator_scope_effect_and_policy_boundaries():
    scoped_predicate = feel_ir(_active())
    scoped_predicate["rules"][0]["scope"]["predicate"] = {"op": "eq", "left": {"symbol": "active"}, "right": _literal(False)}
    assert evaluate_ir(scoped_predicate, {"active": True}, table_id="t1")["status"] == "no_match"
    scoped_predicate["rules"][0]["scope"]["predicate"] = _active()
    assert evaluate_ir(scoped_predicate, {}, table_id="t1")["status"] == "unknown"
    assert evaluate_ir(feel_ir(_active()), [], table_id="t1")["diagnostics"][0]["code"] == "INVALID_INPUTS"

    no_table = feel_ir(_active())
    no_table["tables"] = []
    assert evaluate_ir(no_table, {})["diagnostics"][0]["code"] == "NO_EXECUTABLE_TABLE"
    multi = feel_ir(_active())
    multi["tables"].append(deepcopy(multi["tables"][0]) | {"id": "t2"})
    assert evaluate_ir(multi, {"active": True})["diagnostics"][0]["code"] == "TABLE_SELECTION_REQUIRED"
    assert evaluate_ir(multi, {"active": True}, table_id="missing")["diagnostics"][0]["code"] == "UNKNOWN_TABLE"

    unknown_effect = feel_ir(_active(), effects=[{"kind": "assignment", "modality": "obligation", "target": "decision", "value": {"symbol": "other"}, "provenance": _span()}])
    unknown_effect["symbols"].insert(1, {"id": "other", "theory": "bool", "role": "input", "domain": {"kind": "boolean"}, "unit": None, "derived_expression": None, "provenance": _span()})
    assert evaluate_ir(unknown_effect, {"active": True}, table_id="t1")["status"] == "unknown"
    conflict_effect = feel_ir(_active(), effects=[
        {"target": "decision", "value": _literal("allow", "enum")},
        {"target": "decision", "value": _literal("deny", "enum")},
    ])
    # This synthetic object is intentionally invalid at the IR boundary; use
    # the rule helper directly to exercise the evaluator's conflict branch.
    conflict_effect["rules"][0]["effects"][1]["provenance"] = _span()
    assert evaluate_ir(conflict_effect, {"active": True}, table_id="t1")["status"] == "refused"

    defeated = feel_ir(_active(), exceptions=[{"condition": _active()}])
    assert evaluate_ir(defeated, {"active": True}, table_id="t1")["diagnostics"][0]["code"] == "DEFEATED_RULE"
    any_ir = feel_ir(_active(), policy="ANY")
    any_ir["tables"][0]["rule_ids"] = ["r1", "r2"]
    any_ir["rules"].append(deepcopy(any_ir["rules"][0]) | {"id": "r2", "effects": [{"target": "decision", "value": _literal("deny", "enum")}]})
    # Duplicate rule ids in one table are refused by validation; this remains
    # a direct policy-shape test for the ANY output merge.
    any_ir["rules"][1]["provenance"] = _span()
    assert evaluate_ir(any_ir, {"active": True}, table_id="t1")["status"] == "refused"


def test_lexec_private_helpers_cover_source_hash_provenance_and_literals():
    assert lexec_ir._safe_identifier("123 bad") == "symbol_123_bad"
    assert lexec_ir._iter_rules([]) == []
    assert lexec_ir._iter_rules({"rules": [{"id": "r"}, None]}) == [{"id": "r"}]
    with pytest.raises(TypeError):
        lexec_ir._iter_rules(3)
    digest = "a" * 64
    assert lexec_ir._source_hash({"source_sha256": digest}, None) == digest
    with pytest.raises(ValueError):
        lexec_ir._source_hash({}, "not-a-hash")
    assert len(lexec_ir._source_hash({"source_reference": {"source_text": "hello"}}, None)) == 64
    with pytest.raises(lexec_ir.LoweringRefusal):
        lexec_ir._span({"source_text": ""}, digest)
    with pytest.raises(lexec_ir.LoweringRefusal):
        lexec_ir._span({"source_text": "x", "start_offset": -1, "end_offset": 1}, digest)
    assert lexec_ir._provenance({}, digest)[0]["chunk_path"] == "<synthetic-input>"
    assert lexec_ir._provenance({"source_reference": {"source_text": "x", "start_offset": -1, "end_offset": 1}}, digest)[0]["chunk_path"] == "<missing-source>"
    with pytest.raises(lexec_ir.LoweringRefusal):
        lexec_ir._literal("x", "date")
    with pytest.raises(lexec_ir.LoweringRefusal):
        lexec_ir._literal(1, "bool")
    with pytest.raises(lexec_ir.LoweringRefusal):
        lexec_ir._literal(1.5, "int")
    with pytest.raises(lexec_ir.LoweringRefusal):
        lexec_ir._literal(1, "enum")
    assert lexec_ir._theory({"type": "number"}) == "real"
    with pytest.raises(lexec_ir.LoweringRefusal):
        lexec_ir._theory({"type": "date"})


def test_lexec_predicate_logic_domains_and_scope_refusals():
    variables = {
        "active": {"name": "active", "type": "boolean"},
        "note": {"name": "note", "type": "string", "free_text": True},
        "amount": {"name": "amount", "type": "number", "allowed_range": [0, 10]},
    }
    for value_type, value in (("boolean", True), ("number", 1), ("string", "x")):
        assert lexec_ir._operand(value, value_type, variables)["type"] in {"bool", "real", "string"}
    with pytest.raises(lexec_ir.LoweringRefusal):
        lexec_ir._operand("missing", "variable_reference", variables)
    with pytest.raises(lexec_ir.LoweringRefusal):
        lexec_ir._operand(True, "date", variables)
    predicate = {"variable": "active", "operator": "is_null", "value_type": "boolean"}
    assert lexec_ir._formula_for_predicate(predicate, variables)["op"] == "is_null"
    assert lexec_ir._formula_for_predicate({"variable": "note", "operator": "contains", "value": "x", "value_type": "string"}, variables)["op"] == "contains"
    assert lexec_ir._formula_for_predicate({"variable": "note", "operator": "in", "value": ["x", "y"], "value_type": "string"}, variables)["op"] == "or"
    assert lexec_ir._formula_for_predicate({"variable": "amount", "operator": "in", "value": "[0, 1]", "value_type": "range"}, variables)["op"] == "in_binned_range"
    with pytest.raises(lexec_ir.LoweringRefusal):
        lexec_ir._formula_for_predicate({"variable": "note", "operator": "in", "value": [], "value_type": "string"}, variables)
    with pytest.raises(lexec_ir.LoweringRefusal):
        lexec_ir._formula_for_predicate({"variable": "active", "operator": "???", "value": True, "value_type": "boolean"}, variables)
    predicates = {"p": {"variable": "active", "operator": "==", "value": True, "value_type": "boolean"}}
    assert lexec_ir._logic("AND", predicates, variables)["op"] == "and"
    assert lexec_ir._logic("OR", predicates, variables)["op"] == "or"
    with pytest.raises(lexec_ir.LoweringRefusal):
        lexec_ir._logic({"predicate_ref": "missing"}, predicates, variables)
    with pytest.raises(lexec_ir.LoweringRefusal):
        lexec_ir._logic({"all": []}, predicates, variables)
    assert lexec_ir._domain(variables["note"], "string", [predicates["p"]])["kind"] == "string"
    with pytest.raises(lexec_ir.LoweringRefusal):
        lexec_ir._domain({"name": "note", "type": "string"}, "string", [])
    with pytest.raises(lexec_ir.LoweringRefusal):
        lexec_ir._domain(variables["note"], "string", [{"variable": "note", "operator": ">"}])
    assert lexec_ir._modality({"rule_type": "prohibition"}) == "prohibition"
    assert lexec_ir._modality({"rule_type": "definition"}) == "definition"
    assert lexec_ir._modality({"mandatory": False}) == "permission"
    assert lexec_ir._modality({}) == "none"
    with pytest.raises(lexec_ir.LoweringRefusal):
        lexec_ir._scope({"applicability_scope": "bad"})
    with pytest.raises(lexec_ir.LoweringRefusal):
        lexec_ir._scope({"applicability_scope": {"loan_types": ["home"]}})
    with pytest.raises(lexec_ir.LoweringRefusal):
        lexec_ir._scope({"applicability_scope": {"jurisdiction": [1]}})
    with pytest.raises(lexec_ir.LoweringRefusal):
        lexec_ir._scope({"scope_basis": "unknown"})


def test_lexec_lowering_refusal_matrix_and_conflicting_symbols():
    base = source_rule()
    digest = "a" * 64
    refusals = [
        ({"rule_id": "r", "source_reference": base["source_reference"]}, "MISSING_VARIABLES"),
        ({**base, "rule_id": "", "id": ""}, "MISSING_RULE_ID"),
        ({**base, "source_reference": None}, "MISSING_PROVENANCE"),
        ({**base, "schema_version": "1.0"}, "UNSUPPORTED_SOURCE_SCHEMA"),
        ({**base, "superseded_by": "r2"}, "UNREPRESENTABLE_VERSIONING"),
        ({**base, "recommended_hit_policy": "FIRST"}, "UNSUPPORTED_HIT_POLICY"),
        ({**base, "variables": []}, "MISSING_VARIABLES"),
        ({**base, "condition_predicates": []}, "MISSING_PREDICATES"),
        ({**base, "outcomes": []}, "MISSING_OUTCOMES"),
        ({**base, "outcomes": [None]}, "INVALID_OUTCOME"),
        ({**base, "outcomes": [{"variable": "active", "operator": "=", "value": True, "value_type": "boolean"}]}, "INVALID_OUTCOME_TARGET"),
        ({**base, "outcomes": [{"variable": "decision", "operator": ":=", "value": "allow", "value_type": "enum"}]}, "UNSUPPORTED_OUTCOME_OPERATOR"),
        ({**base, "outcomes": [{"variable": "decision", "operator": "=", "value": "other", "value_type": "enum"}]}, "ENUM_VALUE_OUT_OF_DOMAIN"),
        ({**base, "exceptions": [None]}, "INVALID_EXCEPTION"),
    ]
    for rule, code in refusals:
        lowered = lexec_ir.lower_graph([rule], source_sha256=digest)
        assert lowered["refusals"][0]["code"] == code
    conflict = source_rule()
    conflict["variables"] = [
        {"name": "active", "type": "string", "free_text": True, "role": "input"},
        {"name": "category", "type": "enum", "allowed_values": ["pii"], "role": "input"},
        {"name": "decision", "type": "enum", "allowed_values": ["allow", "deny"], "role": "output"},
    ]
    conflict["condition_predicates"] = [{"predicate_id": "p_active", "variable": "active", "operator": "==", "value": "yes", "value_type": "string"}]
    conflict["condition_logic"] = {"predicate_ref": "p_active"}
    result = lexec_ir.lower_graph([source_rule(), conflict], source_sha256=digest)
    assert any(item["code"] == "SYMBOL_CONFLICT" for item in result["refusals"])


def test_lexec_validate_ir_rejects_each_malformed_collection():
    valid = lexec_ir.lower_graph([source_rule()], source_sha256="a" * 64)
    assert lexec_ir.validate_ir(None) == ["IR must be an object"]
    broken = deepcopy(valid)
    broken["symbols"].append(deepcopy(broken["symbols"][0]))
    broken["symbols"][0]["provenance"] = []
    broken["symbols"][1]["id"] = "bad-id"
    broken["rules"].append(deepcopy(broken["rules"][0]))
    broken["rules"][1]["effects"] = []
    broken["rules"][1]["exceptions"] = "bad"
    broken["tables"][0]["rule_ids"] = []
    broken["refusals"] = [{"code": "bad", "requires_review": False}]
    broken["ignored_fields"] = [{"field": 1, "reason": "bad"}]
    errors = lexec_ir.validate_ir(broken)
    assert any("duplicate symbol id" in error for error in errors)
    assert any("effects are required" in error for error in errors)
    assert any("exceptions must be an array" in error for error in errors)
    assert any("rule_ids must be a non-empty array" in error for error in errors)
    assert any("malformed refusal" in error for error in errors)
    assert any("malformed ignored-field" in error for error in errors)
    assert lexec_ir._validate_span(None, "span")
    assert lexec_ir._validate_span({"chunk_path": "x", "section_id": "s", "start_offset": 1, "end_offset": 1, "source_sha256": "bad"}, "span")
    with pytest.raises(ValueError):
        lexec_ir.assert_valid_ir(broken)


def test_dmn_builder_formula_and_error_contracts():
    assert builder._safe_id(" 123 / bad ", "fallback").startswith("fallback_")
    assert builder._safe_id(None, "fallback") == "fallback"
    assert builder._type_ref({"theory": "bool"}) == "boolean"
    assert builder._type_ref({"theory": "int"}) == "number"
    assert builder._type_ref({"theory": "enum"}) == "string"
    with pytest.raises(DmnBuildError):
        builder._type_ref({"theory": "date"})
    assert builder._feel_literal(None) == "null"
    assert builder._feel_literal(True) == "true"
    assert builder._feel_literal(1.5) == "1.5"
    assert builder._feel_literal("a") == '"a"'
    with pytest.raises(DmnBuildError):
        builder._feel_literal(object())
    assert builder.formula_to_feel({"op": "not", "arg": _eq()}) == "not(x = true)"
    assert builder.formula_to_feel({"op": "is_null", "arg": {"symbol": "x"}}) == "x = null"
    assert builder.formula_to_feel({"op": "in_binned_range", "left": {"symbol": "x"}, "right": _literal("[0, 1]", "string")}) == "x in [0, 1]"
    for operator in ("!=", "<", "<=", ">", ">="):
        assert operator in builder.formula_to_feel({"op": {"!=": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge"}[operator], "left": {"symbol": "x"}, "right": _literal(1, "int")})
    with pytest.raises(DmnBuildError):
        builder.formula_to_feel({"op": "and", "args": []})
    with pytest.raises(DmnBuildError):
        builder.formula_to_feel({"op": "eq", "left": {"symbol": "x"}, "right": {"symbol": "y"}})
    with pytest.raises(DmnBuildError):
        builder.formula_to_feel({"op": "nope"})
    with pytest.raises(DmnBuildError):
        builder._feel_operand({"bad": True})
    with pytest.raises(DmnBuildError):
        builder._conjuncts({"op": "or", "args": []})
    with pytest.raises(DmnBuildError):
        builder._conjuncts({"op": "and", "args": [None]})
    with pytest.raises(DmnBuildError):
        builder._condition_cells(_eq("x"), ["y"])
    with pytest.raises(DmnBuildError):
        builder._constraint_for_symbol(_eq("x"), "y")

    ir = builder_ir()
    symbols = {symbol["id"]: symbol for symbol in ir["symbols"]}
    rule = ir["rules"][0]
    with pytest.raises(DmnBuildError, match="OUTPUT_MISMATCH"):
        builder._rule_to_xml({**rule, "effects": []}, ["active"], ["decision"], symbols, 1, "t1")
    with pytest.raises(DmnBuildError, match="UNSUPPORTED_SCOPE"):
        builder._rule_to_xml({**rule, "scope": {"metadata": {"jurisdictions": ["US"]}}}, ["active"], ["decision"], symbols, 1, "t1")
    derived = deepcopy(ir)
    derived["symbols"][0]["role"] = "derived"
    with pytest.raises(DmnBuildError, match="UNSUPPORTED_DERIVED_INPUT"):
        builder.build_dmn_document(derived)
    empty = deepcopy(ir)
    empty["rules"][0]["condition"] = {"op": "eq", "left": _literal(True), "right": _literal(True)}
    with pytest.raises(DmnBuildError, match="EMPTY_TABLE_SIGNATURE"):
        builder.build_dmn_document(empty)
    unknown_output = deepcopy(ir)
    unknown_output["tables"][0]["output_signature"] = ["missing"]
    with pytest.raises(DmnBuildError, match="UNKNOWN_OUTPUT"):
        builder.build_dmn_document(unknown_output)


def test_dmn_validator_covers_structural_failures():
    assert validate_dmn(b"not xml")[0].startswith("XML parse error")
    assert validate_dmn(ET.Element("definitions")) == ["root must be DMN 1.3 definitions"]
    root = ET.Element(builder._tag("definitions"))
    assert validate_dmn(root) == ["definitions must contain at least one decision"]
    decision = ET.SubElement(root, builder._tag("decision"))
    assert any("exactly one decisionTable" in item for item in validate_dmn(root))
    table = ET.SubElement(decision, builder._tag("decisionTable"), {"hitPolicy": "BAD"})
    inp = ET.SubElement(table, builder._tag("input"))
    ET.SubElement(inp, builder._tag("inputExpression"))
    ET.SubElement(table, builder._tag("output"))
    rule = ET.SubElement(table, builder._tag("rule"))
    ET.SubElement(rule, builder._tag("inputEntry"))
    ET.SubElement(rule, builder._tag("outputEntry"))
    errors = validate_dmn(root)
    assert any("invalid hitPolicy" in item for item in errors)
    assert any("empty inputExpression" in item for item in errors)
    assert any("duplicate/missing id" in item for item in errors)
    assert any("empty entry" in item for item in errors)
    duplicate = ET.SubElement(table, builder._tag("rule"), {"id": "r"})
    ET.SubElement(duplicate, builder._tag("inputEntry"))
    ET.SubElement(duplicate, builder._tag("outputEntry"))
    duplicate_errors = validate_dmn(root)
    assert any("duplicate/missing id" in item for item in duplicate_errors)


def test_smt_domain_solver_and_formula_edges():
    assert smt._symbols_by_id({"x": _symbol()})["x"]["id"] == "x"
    assert smt._symbols_by_id([_symbol(), None]) == {"x": _symbol()}
    nested = {"op": "and", "args": [_eq(), {"op": "not", "arg": _eq("y", False)}]}
    assert smt._formula_symbols(nested) == {"x", "y"}
    assert len(smt._formula_literals(nested)) == 2
    for malformed in (None, {"op": "and", "args": []}, {"op": "not"}, {"op": "eq", "left": {"bad": 1}, "right": _literal(True)}):
        assert smt._formula_error(malformed)
    assert smt._candidate_values(_symbol(), [True])[0] == [None, False, True]
    assert smt._candidate_values({"theory": "enum", "domain": {"kind": "enum", "values": ["a"]}}, [])[0] == [None, "a"]
    assert smt._candidate_values({"theory": "int", "domain": {"kind": "interval", "minimum": 0, "maximum": 2}}, [])[0] == [None, 0, 1, 2]
    assert smt._candidate_values({"theory": "real", "domain": {"kind": "interval", "minimum": None, "maximum": None}}, [0])[2]
    assert smt._candidate_values({"theory": "string", "domain": {"kind": "string"}}, ["urgent"])[0]
    assert smt._candidate_values({"theory": "date", "domain": {}}, [])[2]
    assert smt._kleene_not(None) is None
    assert smt._kleene_and([False, None]) is False
    assert smt._kleene_or([True, None]) is True
    assert smt._compare("eq", None, True) is None
    assert smt._compare("ne", 1, 2) is True
    assert smt._compare("contains", "abc", "b") is True
    assert smt._compare("bad", 1, 2) is None
    assert smt._range_membership(1, "[0, 2]") is True
    assert smt._range_membership(1, "(1, 2)") is False
    assert smt._range_membership(1, "[nan, 2]") is None
    assert smt.evaluate_formula({"op": "is_null", "arg": {"symbol": "missing"}}, {}) is True
    assert smt.evaluate_formula({"op": "unsupported"}, {}) is None
    assert smt.solve_formula(_eq("x"), [],).status == "unknown"
    assert smt.solve_formula(_eq("x"), [_symbol()], max_assignments=0).status == "timeout"


def test_smt_query_and_proof_edge_outcomes():
    bool_symbols = [_symbol()]
    rules = [{"id": "r", "condition": _eq(), "effects": [{"target": "decision", "value": _literal("allow", "enum")}]}]
    assert smt.query_coverage([], bool_symbols)["covered"] is False
    assert smt.query_coverage([{"id": "r", "condition": _eq("missing")}], bool_symbols)["status"] == "unknown"
    assert smt.query_coverage(rules, bool_symbols, max_assignments=0)["status"] == "timeout"
    assert smt.query_conflicts({"r": rules[0]}, bool_symbols)["status"] == "proved"
    unknown_effect = {"id": "r2", "condition": _eq(), "effects": [{"target": "decision", "value": {"symbol": "missing"}}]}
    assert smt.query_conflicts([rules[0], unknown_effect], bool_symbols)["status"] == "unknown"
    assert smt.query_overlap({}, {}, bool_symbols)["status"] == "unknown"
    assert smt._effect_values({"effects": [{"target": None, "value": _literal(True)}]}, {}) is None
    assert smt._effect_values({"effects": [{"target": "x", "value": {"symbol": "missing"}}]}, {}) is None
    assert smt.prove_table({"id": "t", "rule_ids": ["missing"], "hit_policy": "UNIQUE"}, rules, bool_symbols)["status"] == "unknown"
    assert smt.prove_table({"id": "t", "rule_ids": ["r"], "hit_policy": "BOGUS"}, rules, bool_symbols)["status"] == "refused"
    any_proof = smt.prove_table({"id": "t", "rule_ids": ["r", "r"], "hit_policy": "ANY"}, rules, bool_symbols)
    assert any_proof["status"] == "proved"
    assert smt.prove_tables({"rules": rules, "symbols": bool_symbols, "tables": [{"id": "t", "rule_ids": ["r"], "hit_policy": "UNIQUE"}]})["tables"][0]["policy_proof"]["status"] == "proved"


def test_engine_harness_validation_and_process_failures():
    assert harness._validate_cases([{"case_id": "x", "inputs": {}}])[0]["case_id"] == "x"
    for bad in ("x", [], [{"case_id": "", "inputs": {}}], [{"case_id": "x", "inputs": {}}, {"case_id": "x", "inputs": {}}], [{"case_id": "x", "inputs": []}], [{"case_id": "x", "inputs": {}, "table_id": ""}]):
        with pytest.raises(harness.CrosscheckProtocolError):
            harness._validate_cases(bad)
    assert harness._validate_engine_command(None) is None
    with pytest.raises(harness.CrosscheckProtocolError):
        harness._validate_engine_command([])
    with pytest.raises(harness.CrosscheckProtocolError):
        harness._validate_engine_command([""])
    with pytest.raises(harness.CrosscheckProtocolError):
        harness._validate_engine_metadata(None)
    with pytest.raises(harness.CrosscheckProtocolError):
        harness._validate_engine_metadata({"engine_id": "x"})
    metadata = {key: "x" for key in harness.REQUIRED_ENGINE_METADATA} | {"container_digest": "sha256:fixture"}
    assert harness._validate_engine_metadata(metadata)["engine_id"] == "x"
    with pytest.raises(harness.CrosscheckProtocolError):
        harness._project_result({"status": "bad"})
    with pytest.raises(harness.CrosscheckProtocolError):
        harness._project_result({"status": "matched", "outputs": [], "matched_rule_ids": [], "unknown_rule_ids": []})
    with pytest.raises(harness.CrosscheckProtocolError):
        harness._parse_engine_output("not-json", [{"case_id": "x"}])
    with pytest.raises(harness.CrosscheckProtocolError):
        harness._parse_engine_output("{}\n", [{"case_id": "x"}])
    assert harness.compare_results({"status": "matched", "outputs": {}, "matched_rule_ids": [], "unknown_rule_ids": [], "diagnostics": ["r"]}, {"status": "no_match", "outputs": {}, "matched_rule_ids": [], "unknown_rule_ids": []})["agree"] is False
    ir = feel_ir(_active())
    cases = [{"case_id": "x", "inputs": {"active": True}, "table_id": "t1"}]
    metadata = {key: "x" for key in harness.REQUIRED_ENGINE_METADATA} | {"container_digest": "sha256:fixture"}
    missing = harness.run_crosscheck(ir, cases, engine_command=["definitely-not-installed"], engine_metadata=metadata)
    assert missing["status"] == "unrun"
    timeout = harness.run_crosscheck(ir, cases, engine_command=[sys.executable, "-c", "import time; time.sleep(1)"], engine_metadata=metadata, timeout_seconds=0.01)
    assert timeout["status"] == "timeout"
    nonzero = harness.run_crosscheck(ir, cases, engine_command=[sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(2)"], engine_metadata=metadata)
    assert nonzero["status"] == "invalid"
    with pytest.raises(harness.CrosscheckProtocolError):
        harness.render_backend_report({"status": "bad"})
    assert "Status" in harness.render_backend_report({"status": "unrun", "claimable": False, "summary": {}})
