"""DMN 1.3 builder tests for the bounded LExec subset."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from utils.dmn_builder import DMN_NS, DmnBuildError, build_dmn_document, formula_to_feel


def _span():
    return [{"chunk_path": "fixture.txt", "section_id": "s1", "start_offset": 0, "end_offset": 1, "source_sha256": "a" * 64}]


def _ir(*, proof_status="proved", policy="UNIQUE", condition=None, exceptions=None, metadata=None):
    condition = condition or {"op": "eq", "left": {"symbol": "active"}, "right": {"literal": True, "type": "bool"}}
    rule = {
        "id": "r1",
        "scope": {"predicate": None, "metadata": metadata or {}},
        "condition": condition,
        "exceptions": exceptions or [],
        "effects": [{"kind": "assignment", "modality": "obligation", "target": "decision", "value": {"literal": "allow", "type": "enum"}, "provenance": _span()}],
        "provenance": _span(),
    }
    return {
        "schema_version": "lexec-ir/1.0",
        "document_unit": {"document_id": "fixture", "source_sha256": "a" * 64, "source_paths": ["fixture.txt"], "corpus_id": None, "split": None},
        "semantics": {"null_model": "kleene_three_valued", "unknown_at_table_boundary": "refuse", "exception_reading": "defeater_or"},
        "symbols": [
            {"id": "active", "theory": "bool", "role": "input", "domain": {"kind": "boolean"}, "unit": None, "derived_expression": None, "provenance": _span()},
            {"id": "decision", "theory": "enum", "role": "output", "domain": {"kind": "enum", "values": ["allow", "deny"]}, "unit": None, "derived_expression": None, "provenance": _span()},
        ],
        "rules": [rule],
        "tables": [{"id": "t1", "rule_ids": ["r1"], "output_signature": ["decision"], "hit_policy": policy, "policy_proof": {"status": proof_status, "method": "pairwise_disjointness", "solver": "fixture", "query_sha256": "b" * 64, "witnesses": []}}],
        "refusals": [],
        "ignored_fields": [],
    }


def test_builder_emits_namespaced_table_with_inputs_outputs_and_rule():
    root = build_dmn_document(_ir())
    assert root.tag == f"{{{DMN_NS}}}definitions"
    decision = next(child for child in root if child.tag.endswith("decision"))
    table = next(child for child in decision if child.tag.endswith("decisionTable"))
    assert table.attrib["hitPolicy"] == "UNIQUE"
    assert len([child for child in decision if child.tag.endswith("informationRequirement")]) == 1
    assert len([child for child in table if child.tag.endswith("input")]) == 1
    assert len([child for child in table if child.tag.endswith("output")]) == 1
    rule = next(child for child in table if child.tag.endswith("rule"))
    assert next(child for child in rule if child.tag.endswith("inputEntry")).find(f"{{{DMN_NS}}}text").text == "true"
    assert next(child for child in rule if child.tag.endswith("outputEntry")).find(f"{{{DMN_NS}}}text").text == '"allow"'


def test_formula_to_feel_covers_supported_atomic_and_boolean_forms():
    assert formula_to_feel({"op": "eq", "left": {"symbol": "x"}, "right": {"literal": True, "type": "bool"}}) == "x = true"
    assert formula_to_feel({"op": "contains", "left": {"symbol": "note"}, "right": {"literal": "urgent", "type": "string"}}) == 'contains(note, "urgent")'
    assert formula_to_feel({"op": "and", "args": [{"op": "eq", "left": {"symbol": "x"}, "right": {"literal": True, "type": "bool"}}, {"op": "eq", "left": {"symbol": "y"}, "right": {"literal": False, "type": "bool"}}]}) == "((x = true) and (y = false))"


def test_unproved_tables_fail_closed():
    with pytest.raises(DmnBuildError, match="proof status"):
        build_dmn_document(_ir(proof_status="unknown"))


def test_exceptions_scope_and_nonconjunctive_conditions_are_refused():
    exception = {"id": "e1", "condition": {"op": "eq", "left": {"symbol": "active"}, "right": {"literal": False, "type": "bool"}}, "provenance": _span()}
    with pytest.raises(DmnBuildError, match="exceptions"):
        build_dmn_document(_ir(exceptions=[exception]))
    with pytest.raises(DmnBuildError, match="contextual scope"):
        build_dmn_document(_ir(metadata={"jurisdictions": ["US"]}))
    with pytest.raises(DmnBuildError, match="conjunctions"):
        build_dmn_document(_ir(condition={"op": "or", "args": [{"op": "eq", "left": {"symbol": "active"}, "right": {"literal": True, "type": "bool"}}, {"op": "eq", "left": {"symbol": "active"}, "right": {"literal": False, "type": "bool"}}]}))
