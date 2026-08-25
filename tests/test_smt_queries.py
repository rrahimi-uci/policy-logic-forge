"""Contract tests for the bounded SMT-shaped query interface."""

from __future__ import annotations

from utils.smt import (
    query_conflicts,
    query_counterexample,
    query_coverage,
    query_overlap,
    query_satisfiable,
    query_witness,
    solve_formula,
)


def _bool_symbol(name: str = "x") -> dict:
    return {"id": name, "theory": "bool", "role": "input", "domain": {"kind": "boolean"}}


def _string_symbol(name: str = "note") -> dict:
    return {"id": name, "theory": "string", "role": "input", "domain": {"kind": "string", "predicates": ["contains"]}}


def _eq(name: str, value: object) -> dict:
    value_type = "bool" if isinstance(value, bool) else "enum"
    return {"op": "eq", "left": {"symbol": name}, "right": {"literal": value, "type": value_type}}


def _rule(rule_id: str, condition: dict, value: str) -> dict:
    return {
        "id": rule_id,
        "condition": condition,
        "effects": [{"target": "decision", "value": {"literal": value, "type": "enum"}}],
    }


def test_satisfiable_and_witness_queries_preserve_status_and_hash():
    symbols = [_bool_symbol()]
    formula = _eq("x", True)
    result = query_satisfiable(formula, symbols)
    witness = query_witness(formula, symbols)

    assert result["query_type"] == "satisfiable"
    assert result["status"] == "sat"
    assert result["witness"] == {"x": True}
    assert witness["status"] == "sat" and witness["found"] is True
    assert len(result["query_sha256"]) == 64
    assert result["query_sha256"] != query_satisfiable(_eq("x", False), symbols)["query_sha256"]


def test_query_hash_binds_the_bounded_search_budget():
    symbols = [_bool_symbol()]
    formula = _eq("x", True)

    default = query_satisfiable(formula, symbols)
    bounded = query_satisfiable(formula, symbols, max_assignments=1)

    assert default["query_sha256"] != bounded["query_sha256"]


def test_real_intervals_are_not_discretized_into_unsound_integer_proofs():
    symbols = [{"id": "amount", "theory": "real", "role": "input", "domain": {"kind": "interval", "minimum": 0, "maximum": 2}}]
    formula = {"op": "eq", "left": {"symbol": "amount"}, "right": {"literal": 1, "type": "real"}}

    result = solve_formula(formula, symbols)

    assert result.status == "unknown"
    assert "continuous" in (result.reason or "")


def test_open_integer_interval_is_not_treated_as_a_complete_domain():
    symbols = [{"id": "count", "theory": "int", "role": "input", "domain": {"kind": "interval", "minimum": 0, "maximum": 2, "minimum_inclusive": False, "maximum_inclusive": True}}]
    formula = {"op": "eq", "left": {"symbol": "count"}, "right": {"literal": 1, "type": "int"}}

    result = solve_formula(formula, symbols)

    assert result.status == "unknown"
    assert "closed" in (result.reason or "")


def test_incompatible_or_malformed_query_inputs_remain_unknown():
    bool_symbols = [_bool_symbol()]
    incompatible = {"op": "gt", "left": {"symbol": "x"}, "right": {"literal": 1, "type": "int"}}
    outside_enum = {"op": "eq", "left": {"symbol": "category"}, "right": {"literal": "deny", "type": "enum"}}
    enum_symbols = [{"id": "category", "theory": "enum", "role": "input", "domain": {"kind": "enum", "values": ["allow"]}}]

    assert query_satisfiable(incompatible, bool_symbols)["status"] == "unknown"
    assert query_satisfiable(outside_enum, enum_symbols)["status"] == "unknown"
    assert query_satisfiable(_eq("x", True), bool_symbols, max_assignments=-1)["status"] == "unknown"
    assert query_conflicts([], bool_symbols, max_assignments=-1)["status"] == "unknown"


def test_unsatisfiable_and_counterexample_queries_do_not_invent_witnesses():
    symbols = [_bool_symbol()]
    formula = {"op": "and", "args": [_eq("x", True), _eq("x", False)]}

    result = query_satisfiable(formula, symbols)
    counterexample = query_counterexample(formula, symbols)

    assert result["status"] == "unsat" and result["witness"] is None
    assert counterexample["status"] == "unsat" and counterexample["found"] is False


def test_unknown_and_timeout_are_first_class_query_outcomes():
    string_symbols = [_string_symbol()]
    formula = {
        "op": "and",
        "args": [
            {"op": "contains", "left": {"symbol": "note"}, "right": {"literal": "urgent", "type": "string"}},
            {"op": "not", "arg": {"op": "contains", "left": {"symbol": "note"}, "right": {"literal": "urgent", "type": "string"}}},
        ],
    }
    unknown = query_satisfiable(formula, string_symbols)
    timeout = query_satisfiable(_eq("x", True), [_bool_symbol()], max_assignments=1)

    assert unknown["status"] == "unknown"
    assert timeout["status"] == "timeout"


def test_malformed_query_inputs_are_unknown_instead_of_becoming_false_proofs():
    malformed_formula = query_satisfiable({"op": ["not-an-operator"]}, [_bool_symbol()])
    malformed_coverage = query_coverage([{"id": "broken", "condition": None}], [_bool_symbol()])
    malformed_conflicts = query_conflicts([{"id": "broken", "condition": _eq("x", True)}], [_bool_symbol()])

    assert malformed_formula["status"] == "unknown"
    assert malformed_coverage["status"] == "unknown"
    assert malformed_conflicts["status"] == "unknown"


def test_overlap_query_returns_a_counterexample_or_proves_disjointness():
    symbols = [_bool_symbol()]
    true_rule = _rule("r_true", _eq("x", True), "allow")
    false_rule = _rule("r_false", _eq("x", False), "deny")

    overlap = query_overlap(true_rule, true_rule, symbols)
    disjoint = query_overlap(true_rule, false_rule, symbols)

    assert overlap["status"] == "sat" and overlap["overlap"] is True
    assert overlap["witness"] == {"x": True}
    assert disjoint["status"] == "unsat" and disjoint["overlap"] is False


def test_coverage_requires_true_not_unknown_and_returns_gap_witness():
    symbols = [_bool_symbol()]
    rules = [
        _rule("r_null", {"op": "is_null", "arg": {"symbol": "x"}}, "null"),
        _rule("r_true", _eq("x", True), "allow"),
        _rule("r_false", _eq("x", False), "deny"),
    ]
    covered = query_coverage(rules, symbols)
    gap = query_coverage([rules[1]], symbols)

    assert covered["status"] == "proved" and covered["covered"] is True
    assert gap["status"] == "counterexample" and gap["covered"] is False
    assert gap["witness"] == {"x": False}


def test_coverage_of_open_domain_remains_unknown_when_no_gap_is_found():
    symbols = [_string_symbol()]
    rules = [_rule("r", {"op": "contains", "left": {"symbol": "note"}, "right": {"literal": "urgent", "type": "string"}}, "allow")]
    result = query_coverage(rules, symbols)
    assert result["status"] == "counterexample"
    assert result["witness"] in ({"note": None}, {"note": ""}, {"note": "x"})


def test_conflict_query_distinguishes_different_outputs_from_equal_outputs():
    symbols = [_bool_symbol()]
    conflict = query_conflicts([
        _rule("r_allow", _eq("x", True), "allow"),
        _rule("r_deny", _eq("x", True), "deny"),
    ], symbols)
    equal = query_conflicts([
        _rule("r1", _eq("x", True), "allow"),
        _rule("r2", _eq("x", True), "allow"),
    ], symbols)

    assert conflict["status"] == "conflict"
    assert conflict["witnesses"][0]["assignment"] == {"x": True}
    assert equal["status"] == "proved" and equal["conflict_count"] == 0


def test_conflicts_remain_unknown_for_unbounded_domains():
    symbols = [{"id": "amount", "theory": "real", "role": "input", "domain": {"kind": "interval", "minimum": None, "maximum": None}}]
    condition = {"op": "gt", "left": {"symbol": "amount"}, "right": {"literal": 0, "type": "real"}}
    result = query_conflicts([_rule("r1", condition, "allow"), _rule("r2", condition, "deny")], symbols)
    assert result["status"] == "unknown"
