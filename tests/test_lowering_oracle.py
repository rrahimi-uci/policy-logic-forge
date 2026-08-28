"""Independent expected-value tests for lowering.

These assertions intentionally construct the expected IR fragments directly;
they do not call the lowerer's private helpers to derive the expected answer.
Mutation of an operator, modality, or refusal must fail this suite.
"""

from __future__ import annotations

import json
from pathlib import Path

from utils.lowering_oracle import load_fixture, run_oracle
from utils.lexec_ir import lower_graph


ROOT = Path(__file__).resolve().parents[1]


def _source():
    return {
        "chunk_path": "oracle/source.txt",
        "section_id": "s1",
        "source_text": "The account is active.",
        "start_offset": 0,
        "end_offset": 23,
    }


def test_oracle_for_boolean_assignment():
    rule = {
        "rule_id": "oracle_allow",
        "rule_type": "access_rights",
        "condition_predicates": [{"predicate_id": "p1", "variable": "active", "operator": "==", "value": True, "value_type": "boolean"}],
        "condition_logic": {"predicate_ref": "p1"},
        "outcomes": [{"variable": "access", "operator": "=", "value": "allow", "value_type": "enum"}],
        "variables": [
            {"name": "active", "type": "boolean", "role": "input"},
            {"name": "access", "type": "enum", "allowed_values": ["allow", "deny"], "role": "output"},
        ],
        "recommended_hit_policy": "UNIQUE",
        "applicability_scope": {},
        "scope_basis": "genuinely_unscoped",
        "exceptions": [],
        "mandatory": False,
        "source_reference": _source(),
    }
    ir = lower_graph([rule], source_sha256="b" * 64)
    assert len(ir["rules"]) == 1
    lowered = ir["rules"][0]
    assert lowered["id"] == "oracle_allow"
    assert lowered["condition"] == {"op": "eq", "left": {"symbol": "active"}, "right": {"literal": True, "type": "bool"}}
    assert lowered["effects"] == [{
        "kind": "assignment",
        "modality": "permission",
        "target": "access",
        "value": {"literal": "allow", "type": "enum"},
        "provenance": [{
            "chunk_path": "oracle/source.txt",
            "section_id": "s1",
            "start_offset": 0,
            "end_offset": 23,
            "source_sha256": "b" * 64,
        }],
    }]
def test_oracle_refuses_unrepresentable_scope_instead_of_dropping_it():
    rule = {
        "rule_id": "oracle_scope",
        "condition_predicates": [{"predicate_id": "p", "variable": "x", "operator": "==", "value": True, "value_type": "boolean"}],
        "condition_logic": {"predicate_ref": "p"},
        "outcomes": [{"variable": "y", "operator": "=", "value": True, "value_type": "boolean"}],
        "variables": [{"name": "x", "type": "boolean", "role": "input"}, {"name": "y", "type": "boolean", "role": "output"}],
        "applicability_scope": {"user_categories": ["commercial"]},
        "scope_basis": "explicit_in_source",
        "exceptions": [],
        "source_reference": _source(),
    }
    ir = lower_graph([rule], source_sha256="c" * 64)
    assert ir["rules"] == []
    assert ir["refusals"] == [{
        "rule_id": "oracle_scope",
        "code": "UNREPRESENTABLE_SCOPE",
        "construct": "applicability_scope",
        "detail": "Scope fields cannot be represented: ['user_categories'].",
        "requires_review": True,
        "provenance": [{
            "chunk_path": "oracle/source.txt",
            "section_id": "s1",
            "start_offset": 0,
            "end_offset": 23,
            "source_sha256": "c" * 64,
        }],
    }]


def test_oracle_represents_categorical_scope_dimensions_as_a_predicate():
    rule = {
        "rule_id": "oracle_scope_dimension",
        "condition_predicates": [{"predicate_id": "p", "variable": "x", "operator": "==", "value": True, "value_type": "boolean"}],
        "condition_logic": {"predicate_ref": "p"},
        "outcomes": [{"variable": "y", "operator": "=", "value": True, "value_type": "boolean"}],
        "variables": [{"name": "x", "type": "boolean", "role": "input"}, {"name": "y", "type": "boolean", "role": "output"}],
        "applicability_scope": {"loan_types": ["conventional"], "transaction_types": ["purchase"]},
        "scope_basis": "explicit_in_source",
        "exceptions": [],
        "source_reference": _source(),
    }
    ir = lower_graph([rule], source_sha256="c" * 64)
    assert ir["refusals"] == []
    assert len(ir["rules"]) == 1
    assert ir["rules"][0]["scope"]["predicate"] == {
        "op": "and",
        "args": [
            {"op": "eq", "left": {"symbol": "loan_type"}, "right": {"literal": "conventional", "type": "string"}},
            {"op": "eq", "left": {"symbol": "transaction_type"}, "right": {"literal": "purchase", "type": "string"}},
        ],
    }
    symbol_ids = {symbol["id"] for symbol in ir["symbols"]}
    assert {"loan_type", "transaction_type"} <= symbol_ids


def test_frozen_fixture_cases_and_mutations_all_pass():
    report = run_oracle(load_fixture(ROOT / "tests/fixtures/lowering_oracle"))
    assert report["cases_passed"] == report["case_count"] == 6
    assert report["mutations_killed"] == report["mutation_count"] == 6
    assert report["mutation_score"] == 1.0
    assert report["failed_cases"] == []
    assert report["survived_mutations"] == []


def test_checked_mutation_artifact_matches_recomputed_fixture():
    fixture = load_fixture(ROOT / "tests/fixtures/lowering_oracle")
    artifact = json.loads((ROOT / "results/aggregates/lowering_mutation_score.json").read_text(encoding="utf-8"))
    assert artifact == run_oracle(fixture)
