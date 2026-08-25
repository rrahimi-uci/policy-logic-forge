"""Tests for the bounded, fail-closed IR-3 proof core."""

from __future__ import annotations

from utils.smt import annotate_policy_proofs, evaluate_formula, prove_table, solve_formula


def _bool_symbol(name="x"):
    return {"id": name, "theory": "bool", "role": "input", "domain": {"kind": "boolean"}}


def _rule(rule_id, condition, value):
    return {
        "id": rule_id,
        "condition": condition,
        "effects": [{"target": "decision", "value": {"literal": value, "type": "enum"}}],
    }


def test_kleene_logic_preserves_unknown_and_short_circuit_values():
    assert evaluate_formula({"op": "and", "args": [{"op": "eq", "left": {"symbol": "x"}, "right": {"literal": True, "type": "bool"}}, {"op": "eq", "left": {"symbol": "y"}, "right": {"literal": True, "type": "bool"}}]}, {"x": False, "y": None}) is False
    assert evaluate_formula({"op": "or", "args": [{"op": "eq", "left": {"symbol": "x"}, "right": {"literal": True, "type": "bool"}}, {"op": "eq", "left": {"symbol": "y"}, "right": {"literal": True, "type": "bool"}}]}, {"x": False, "y": None}) is None
    assert evaluate_formula({"op": "not", "arg": {"op": "eq", "left": {"symbol": "x"}, "right": {"literal": True, "type": "bool"}}}, {"x": None}) is None


def test_finite_solver_proves_sat_and_unsat_with_witnesses():
    symbols = [_bool_symbol()]
    sat = solve_formula({"op": "eq", "left": {"symbol": "x"}, "right": {"literal": True, "type": "bool"}}, symbols)
    unsat = solve_formula({"op": "and", "args": [
        {"op": "eq", "left": {"symbol": "x"}, "right": {"literal": True, "type": "bool"}},
        {"op": "eq", "left": {"symbol": "x"}, "right": {"literal": False, "type": "bool"}},
    ]}, symbols)
    assert sat.status == "sat" and sat.witness == {"x": True}
    assert unsat.status == "unsat" and unsat.witness is None


def test_open_string_domain_can_find_a_witness_but_cannot_prove_unsat():
    symbols = [{"id": "note", "theory": "string", "role": "input", "domain": {"kind": "string", "predicates": ["contains"]}}]
    sat = solve_formula({"op": "contains", "left": {"symbol": "note"}, "right": {"literal": "urgent", "type": "string"}}, symbols)
    unsat = solve_formula({"op": "and", "args": [
        {"op": "contains", "left": {"symbol": "note"}, "right": {"literal": "urgent", "type": "string"}},
        {"op": "not", "arg": {"op": "contains", "left": {"symbol": "note"}, "right": {"literal": "urgent", "type": "string"}}},
    ]}, symbols)
    assert sat.status == "sat"
    assert unsat.status == "unknown"


def test_unique_table_overlap_is_refused_with_counterexample():
    symbols = [_bool_symbol()]
    rules = [
        _rule("r_true", {"op": "eq", "left": {"symbol": "x"}, "right": {"literal": True, "type": "bool"}}, "allow"),
        _rule("r_any", {"op": "eq", "left": {"symbol": "x"}, "right": {"literal": True, "type": "bool"}}, "deny"),
    ]
    proof = prove_table({"id": "t1", "rule_ids": ["r_true", "r_any"], "hit_policy": "UNIQUE"}, rules, symbols)
    assert proof["status"] == "refused"
    assert proof["method"] == "pairwise_disjointness"
    assert proof["witnesses"][0]["assignment"] == {"x": True}


def test_unique_disjoint_table_is_proved_and_annotation_is_non_mutating():
    symbols = [_bool_symbol()]
    rules = [
        _rule("r_true", {"op": "eq", "left": {"symbol": "x"}, "right": {"literal": True, "type": "bool"}}, "allow"),
        _rule("r_false", {"op": "eq", "left": {"symbol": "x"}, "right": {"literal": False, "type": "bool"}}, "deny"),
    ]
    ir = {"rules": rules, "symbols": symbols, "tables": [{"id": "t1", "rule_ids": ["r_true", "r_false"], "hit_policy": "UNIQUE", "policy_proof": {"status": "unknown"}}]}
    annotated = annotate_policy_proofs(ir)
    assert annotated["tables"][0]["policy_proof"]["status"] == "proved"
    assert len(annotated["tables"][0]["policy_proof"]["query_sha256"]) == 64
    assert ir["tables"][0]["policy_proof"]["status"] == "unknown"


def test_policy_proof_hash_binds_symbols_and_search_budget():
    symbols = [_bool_symbol()]
    rules = [
        _rule("r_true", {"op": "eq", "left": {"symbol": "x"}, "right": {"literal": True, "type": "bool"}}, "allow"),
        _rule("r_any", {"op": "eq", "left": {"symbol": "x"}, "right": {"literal": True, "type": "bool"}}, "deny"),
    ]
    table = {"id": "t1", "rule_ids": ["r_true", "r_any"], "hit_policy": "UNIQUE"}

    proof = prove_table(table, rules, symbols)
    bounded = prove_table(table, rules, symbols, max_assignments=1)
    altered_symbols = [{**symbols[0], "unit": "flag"}]
    altered = prove_table(table, rules, altered_symbols)

    assert proof["query_sha256"] != bounded["query_sha256"]
    assert proof["query_sha256"] != altered["query_sha256"]


def test_unknown_and_priority_never_pass():
    symbols = [{"id": "n", "theory": "real", "role": "input", "domain": {"kind": "interval", "minimum": None, "maximum": None}}]
    rule = _rule("r", {"op": "gt", "left": {"symbol": "n"}, "right": {"literal": 0, "type": "real"}}, "allow")
    unknown = prove_table({"id": "t", "rule_ids": ["r", "r"], "hit_policy": "UNIQUE"}, [rule], symbols)
    priority = prove_table({"id": "tp", "rule_ids": ["r"], "hit_policy": "PRIORITY"}, [rule], symbols)
    assert unknown["status"] == "unknown"
    assert priority["status"] == "refused"


def test_unique_proof_does_not_discretize_a_continuous_real_interval():
    symbols = [{"id": "amount", "theory": "real", "role": "input", "domain": {"kind": "interval", "minimum": 0, "maximum": 2}}]
    condition = {"op": "gt", "left": {"symbol": "amount"}, "right": {"literal": 0, "type": "real"}}
    rules = [_rule("r1", condition, "allow"), _rule("r2", condition, "allow")]

    proof = prove_table({"id": "t", "rule_ids": ["r1", "r2"], "hit_policy": "UNIQUE"}, rules, symbols)

    assert proof["status"] == "unknown"
    assert "continuous" in proof["witnesses"][0]["reason"]


def test_policy_proof_rejects_an_invalid_resource_bound():
    symbols = [_bool_symbol()]
    rule = _rule("r", {"op": "eq", "left": {"symbol": "x"}, "right": {"literal": True, "type": "bool"}}, "allow")

    proof = prove_table({"id": "t", "rule_ids": ["r"], "hit_policy": "UNIQUE"}, [rule], symbols, max_assignments=-1)

    assert proof["status"] == "unknown"
    assert "non-negative integer" in proof["witnesses"][0]["reason"]


def test_collect_is_explicitly_unproved_even_when_overlap_is_allowed():
    symbols = [_bool_symbol()]
    rule = _rule("r", {"op": "eq", "left": {"symbol": "x"}, "right": {"literal": True, "type": "bool"}}, "allow")
    proof = prove_table({"id": "tc", "rule_ids": ["r", "r"], "hit_policy": "COLLECT"}, [rule], symbols)
    assert proof["status"] == "unknown"
    assert proof["method"] == "equal_outputs_on_overlap"
