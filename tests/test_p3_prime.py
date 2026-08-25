"""Tests for the restricted, known-table P3-prime comparator."""

from __future__ import annotations

from copy import deepcopy

from utils.p3_prime import compare_ir_tables


def _span():
    return [{"chunk_path": "fixture.txt", "section_id": "s1", "start_offset": 0, "end_offset": 1, "source_sha256": "a" * 64}]


def _symbol(name, theory, domain, role="input"):
    return {"id": name, "theory": theory, "role": role, "domain": domain, "unit": None, "derived_expression": None, "provenance": _span()}


def _rule(rule_id, condition, value):
    return {
        "id": rule_id,
        "scope": {"predicate": None, "metadata": {}},
        "condition": condition,
        "exceptions": [],
        "effects": [{"kind": "assignment", "modality": "none", "target": "decision", "value": {"literal": value, "type": "enum"}, "provenance": _span()}],
        "provenance": _span(),
    }


def _ir(rules, symbols, *, policy="UNIQUE"):
    return {
        "schema_version": "lexec-ir/1.0",
        "document_unit": {"document_id": "fixture", "source_sha256": "a" * 64, "source_paths": ["fixture.txt"], "corpus_id": None, "split": None},
        "semantics": {"null_model": "kleene_three_valued", "unknown_at_table_boundary": "refuse", "exception_reading": "defeater_or"},
        "symbols": symbols,
        "rules": rules,
        "tables": [{"id": "t1", "rule_ids": [rule["id"] for rule in rules], "output_signature": ["decision"], "hit_policy": policy, "policy_proof": {"status": "proved", "method": "pairwise_disjointness", "solver": "fixture", "query_sha256": "b" * 64, "witnesses": []}}],
        "refusals": [],
        "ignored_fields": [],
    }


def _real_symbols(*, minimum=0, maximum=10, minimum_inclusive=True, maximum_inclusive=True):
    return [
        _symbol("amount", "real", {"kind": "interval", "minimum": minimum, "maximum": maximum, "minimum_inclusive": minimum_inclusive, "maximum_inclusive": maximum_inclusive}),
        _symbol("decision", "enum", {"kind": "enum", "values": ["allow", "deny"]}, role="output"),
    ]


def _comparison(op, value):
    return {"op": op, "left": {"symbol": "amount"}, "right": {"literal": value, "type": "real"}}


def test_equal_known_interval_tables_compare_on_representative_cells():
    condition = {"op": "and", "args": [_comparison("ge", 0), _comparison("lt", 10)]}
    left = _ir([_rule("r1", condition, "allow")], _real_symbols())
    right = deepcopy(left)

    result = compare_ir_tables(left, right, thresholds={"amount": [0, 10]})

    assert result["status"] == "equivalent"
    assert result["checked_cases"] == result["case_count"]
    assert result["case_count"] >= 5


def test_exact_ties_distinguish_open_and_closed_thresholds():
    left = _ir([_rule("r1", _comparison("ge", 0), "allow")], _real_symbols(minimum=-1, maximum=1))
    right = _ir([_rule("r1", _comparison("gt", 0), "allow")], _real_symbols(minimum=-1, maximum=1))

    result = compare_ir_tables(left, right, thresholds={"amount": [0]})

    assert result["status"] == "different"
    assert any(difference["inputs"]["amount"] == 0.0 for difference in result["differences"])


def test_multiple_dimensions_are_compared_as_a_cartesian_cell_suite():
    symbols = _real_symbols(maximum=10) + [_symbol("score", "real", {"kind": "interval", "minimum": 0, "maximum": 20})]
    condition = {"op": "and", "args": [_comparison("ge", 0), {"op": "lt", "left": {"symbol": "score"}, "right": {"literal": 5, "type": "real"}}]}
    left = _ir([_rule("r1", condition, "allow")], symbols)
    right = deepcopy(left)

    result = compare_ir_tables(left, right, thresholds={"amount": [0], "score": [5]})

    assert result["status"] == "equivalent"
    assert result["case_count"] > 1


def test_missing_inputs_and_default_no_match_are_observable_outcomes():
    symbols = [_symbol("active", "bool", {"kind": "boolean"}), _symbol("decision", "enum", {"kind": "enum", "values": ["allow"]}, role="output")]
    condition = {"op": "eq", "left": {"symbol": "active"}, "right": {"literal": True, "type": "bool"}}
    left = _ir([_rule("r1", condition, "allow")], symbols)
    right = deepcopy(left)

    result = compare_ir_tables(left, right, thresholds={})

    assert result["status"] == "equivalent"
    assert result["case_count"] == 3  # missing, false/no-match, and true/match


def test_open_domain_endpoint_is_not_sampled_as_an_in_domain_value():
    symbols = _real_symbols(minimum=0, maximum=1, minimum_inclusive=False)
    condition = _comparison("eq", 0)
    left = _ir([_rule("r1", condition, "allow")], symbols)
    right = _ir([_rule("r1", condition, "deny")], symbols)

    result = compare_ir_tables(left, right, thresholds={"amount": [0]})

    assert result["status"] == "equivalent"


def test_non_interval_predicates_are_refused_not_sampled():
    symbols = [_symbol("note", "string", {"kind": "string", "predicates": ["contains"]}), _symbol("decision", "enum", {"kind": "enum", "values": ["allow"]}, role="output")]
    condition = {"op": "contains", "left": {"symbol": "note"}, "right": {"literal": "urgent", "type": "string"}}
    left = _ir([_rule("r1", condition, "allow")], symbols)

    result = compare_ir_tables(left, deepcopy(left), thresholds={})

    assert result["status"] == "refused"
    assert "unsupported formula operator" in result["reason"]


def test_contextual_scope_is_refused_instead_of_treated_as_universal():
    condition = _comparison("ge", 0)
    left = _ir([_rule("r1", condition, "allow")], _real_symbols())
    left["rules"][0]["scope"]["metadata"] = {"jurisdictions": ["US"]}

    result = compare_ir_tables(left, deepcopy(left), thresholds={"amount": [0]})

    assert result["status"] == "refused"
    assert "contextual scope" in result["reason"]


def test_binned_range_bounds_are_included_in_the_threshold_precondition():
    condition = {"op": "in_binned_range", "left": {"symbol": "amount"}, "right": {"literal": "[2, 5)", "type": "string"}}
    left = _ir([_rule("r1", condition, "allow")], _real_symbols())
    right = deepcopy(left)

    result = compare_ir_tables(left, right, thresholds={"amount": [2, 5]})

    assert result["status"] == "equivalent"
    assert result["case_count"] >= 5


def test_threshold_precondition_and_case_resource_bound_are_explicit():
    left = _ir([_rule("r1", _comparison("gt", 10), "allow")], _real_symbols(maximum=20))
    right = deepcopy(left)

    missing = compare_ir_tables(left, right, thresholds={"amount": [0]})
    timeout = compare_ir_tables(left, right, thresholds={"amount": [10]}, max_cases=1)

    assert missing["status"] == "refused"
    assert "does not cover" in missing["reason"]
    assert timeout["status"] == "timeout"
    assert timeout["checked_cases"] == 0


def test_output_changes_are_reported_even_when_conditions_match():
    condition = _comparison("ge", 0)
    left = _ir([_rule("r1", condition, "allow")], _real_symbols())
    right = _ir([_rule("r1", condition, "deny")], _real_symbols())

    result = compare_ir_tables(left, right, thresholds={"amount": [0]})

    assert result["status"] == "different"
    assert result["differences"][0]["left"]["outputs"] == {"decision": "allow"}
    assert result["differences"][0]["right"]["outputs"] == {"decision": "deny"}
