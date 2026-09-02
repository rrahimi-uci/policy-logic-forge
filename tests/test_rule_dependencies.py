"""Tests for utils/rule_dependencies.py — typed, deterministic rule relations.

The model under test replaces one in which an LLM proposed edges carrying an
unenforced ``dependency_type`` label, screened by a single structural check
that was correct for only one of the six labels it validated. These tests pin
the three properties that model lacked: exhaustive derivation, a distinct
acceptance condition per kind, and re-validation after the graph is rewritten.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.rule_dependencies import (  # noqa: E402
    Relation,
    classify_gating,
    derive_associations,
    derive_conflicts,
    derive_dataflow,
    derive_relations,
    refusal_for_declared_kind,
    relation_holds,
    revalidate,
    rule_reads,
    rule_writes,
)


def _rule(rule_id, *, reads=(), writes=(), passages=(), outcomes=None, variables=None):
    """A minimal v2-shaped rule. Roles mirror what the contract validator enforces."""
    declared = [{"name": name, "type": "boolean", "role": "input"} for name in reads]
    declared += [{"name": name, "type": "boolean", "role": "output"} for name in writes]
    return {
        "rule_id": rule_id,
        "condition_predicates": [
            {"predicate_id": f"p{i}", "variable": name, "operator": "==", "value": True}
            for i, name in enumerate(reads, 1)
        ],
        "outcomes": outcomes if outcomes is not None else [
            {"variable": name, "operator": "=", "value": True} for name in writes
        ],
        "variables": variables if variables is not None else declared,
        "source_reference": [
            {"chunk_path": path, "section_id": section} for path, section in passages
        ],
    }


# ---------------------------------------------------------------------------
# symbol extraction
# ---------------------------------------------------------------------------

def test_writes_and_reads_are_normalised_consistently():
    rule = _rule("R1", reads=["  Loan_Type "], writes=["ELIGIBLE"])
    assert rule_reads(rule) == {"loan_type"}
    assert rule_writes(rule) == {"eligible"}


def test_feel_expression_operands_count_as_reads():
    """A rule computing ``a / b`` consumes a and b.

    The previous structural check scanned only condition predicates, so an edge
    feeding a computed outcome was invisible to it.
    """
    rule = _rule(
        "R1", reads=["threshold"], writes=[],
        outcomes=[{
            "variable": "ratio", "operator": "=",
            "value": "non_residential_area / total_area", "value_type": "feel_expression",
        }],
        variables=[
            {"name": "threshold", "type": "number", "role": "input"},
            {"name": "non_residential_area", "type": "number", "role": "input"},
            {"name": "total_area", "type": "number", "role": "input"},
            {"name": "ratio", "type": "number", "role": "output"},
        ],
    )
    assert {"non_residential_area", "total_area"} <= rule_reads(rule)


def test_variable_reference_right_hand_side_counts_as_a_read():
    rule = _rule("R1", reads=[], writes=["ok"])
    rule["condition_predicates"] = [{
        "predicate_id": "p1", "variable": "amount", "operator": ">=",
        "value": "threshold_amount", "value_type": "variable_reference",
    }]
    rule["variables"] = [
        {"name": "amount", "type": "number", "role": "input"},
        {"name": "threshold_amount", "type": "number", "role": "input"},
        {"name": "ok", "type": "boolean", "role": "output"},
    ]
    assert {"amount", "threshold_amount"} <= rule_reads(rule)


# ---------------------------------------------------------------------------
# dataflow
# ---------------------------------------------------------------------------

def test_dataflow_is_exhaustive_over_all_pairs():
    """Every writer/reader pair is found, not a sampled subset.

    This is the property the previous LLM-proposal model could not offer: it
    examined roughly 4% of rule pairs on a real run.
    """
    rules = [_rule("A", writes=["x"])] + [_rule(f"R{i}", reads=["x"]) for i in range(25)]
    edges = derive_dataflow(rules)
    assert len(edges) == 25
    assert {e.target_rule_id for e in edges} == {f"R{i}" for i in range(25)}
    assert all(e.kind == "dataflow" and e.directed for e in edges)


def test_dataflow_records_the_symbols_that_justify_it():
    rules = [_rule("A", writes=["x", "y"]), _rule("B", reads=["x", "y", "z"])]
    edge, = derive_dataflow(rules)
    assert edge.symbols == ("x", "y")
    assert "x" in edge.rationale and edge.basis == "deterministic"


def test_dataflow_excludes_self_loops():
    rules = [_rule("A", reads=["x"], writes=["x"])]
    assert derive_dataflow(rules) == []


def test_dataflow_is_deterministic_and_order_independent():
    rules = [_rule("A", writes=["x"]), _rule("B", reads=["x"]), _rule("C", reads=["x"])]
    assert derive_dataflow(rules) == derive_dataflow(list(reversed(rules)))


# ---------------------------------------------------------------------------
# conflict / association
# ---------------------------------------------------------------------------

def test_conflict_pairs_rules_assigning_the_same_symbol_undirected():
    rules = [_rule("A", writes=["decision"]), _rule("B", writes=["decision"])]
    rel, = derive_conflicts(rules)
    assert rel.kind == "conflict" and rel.directed is False
    assert rel.symbols == ("decision",)


def test_association_links_rules_sharing_an_unproduced_input():
    """Shared input is co-sensitivity, not dependency -- and it is symmetric."""
    rules = [_rule("A", reads=["transaction_type"]), _rule("B", reads=["transaction_type"])]
    rel, = derive_associations(rules, shared_passage=False)
    assert rel.kind == "association" and rel.directed is False
    assert rel.symbols == ("input:transaction_type",)
    assert "not dependency" in rel.rationale


def test_a_produced_symbol_is_dataflow_not_association():
    """If some rule produces the symbol, the link is a real dependency."""
    rules = [_rule("P", writes=["x"]), _rule("A", reads=["x"]), _rule("B", reads=["x"])]
    associations = derive_associations(rules, shared_passage=False)
    assert not any("input:x" in rel.symbols for rel in associations)


def test_association_links_rules_from_the_same_passage():
    rules = [
        _rule("A", passages=[("guide/b2.txt", "s1")]),
        _rule("B", passages=[("guide/b2.txt", "s1")]),
        _rule("C", passages=[("guide/b9.txt", "s4")]),
    ]
    rels = derive_associations(rules, shared_input=False)
    assert len(rels) == 1
    assert {rels[0].source_rule_id, rels[0].target_rule_id} == {"A", "B"}


def test_oversized_passage_groups_are_skipped_as_catch_alls():
    """A pointer cited by hundreds of rules is a document, not a passage.

    Associating every member with every other would produce a blob rather than
    a reviewable cluster, so the group is dropped rather than exploded.
    """
    rules = [_rule(f"R{i}", passages=[("whole_doc.txt", "")]) for i in range(30)]
    assert derive_associations(rules, shared_input=False, max_passage_fanout=10) == []


# ---------------------------------------------------------------------------
# gating
# ---------------------------------------------------------------------------

def test_gating_requires_an_oracle_and_defaults_to_the_weaker_claim():
    """Without an entailment check nothing is promoted -- fail-closed.

    The old ``prerequisite`` label made this stronger claim with no test behind
    it; here an unchecked relation stays ``dataflow``.
    """
    rules = [_rule("A", writes=["x"]), _rule("B", reads=["x"])]
    assert [r.kind for r in classify_gating(derive_dataflow(rules), rules)] == ["dataflow"]


def test_gating_promotes_only_on_a_true_verdict():
    rules = [_rule("A", writes=["x"]), _rule("B", reads=["x"])]
    flows = derive_dataflow(rules)
    assert [r.kind for r in classify_gating(flows, rules, entails=lambda s, t, sym: True)] == ["gating"]
    assert [r.kind for r in classify_gating(flows, rules, entails=lambda s, t, sym: False)] == ["dataflow"]
    # undecided (rules did not compile, solver timed out) must not promote
    assert [r.kind for r in classify_gating(flows, rules, entails=lambda s, t, sym: None)] == ["dataflow"]


def test_an_oracle_failure_never_loses_the_relation():
    rules = [_rule("A", writes=["x"]), _rule("B", reads=["x"])]

    def boom(source, target, symbol):
        raise RuntimeError("solver unavailable")

    kept = classify_gating(derive_dataflow(rules), rules, entails=boom)
    assert [r.kind for r in kept] == ["dataflow"]


# ---------------------------------------------------------------------------
# re-validation — the stale-attestation defect
# ---------------------------------------------------------------------------

def test_relation_stops_holding_when_the_symbol_is_renamed():
    """The real defect this guards against.

    A relation derived while the source assigned ``transaction_type`` must stop
    holding once a later stage renames that output -- which is exactly what
    remediation does when it rewrites an output into a list-typed
    ``allowed_*_values`` form.
    """
    before = [_rule("A", writes=["transaction_type"]), _rule("B", reads=["transaction_type"])]
    relation, = derive_dataflow(before)
    assert relation_holds(relation, before)

    after = [_rule("A", writes=["allowed_transaction_type_values"]), _rule("B", reads=["transaction_type"])]
    assert not relation_holds(relation, after)

    held, dropped = revalidate([relation], after)
    assert held == [] and dropped == [relation]


def test_relation_stops_holding_when_a_rule_disappears():
    rules = [_rule("A", writes=["x"]), _rule("B", reads=["x"])]
    relation, = derive_dataflow(rules)
    assert not relation_holds(relation, [_rule("B", reads=["x"])])


def test_each_kind_is_revalidated_by_its_own_condition():
    """A conflict must not be re-checked as though it were dataflow.

    One shared check standing in for every kind is the flaw in the previous
    model; these two relations hold under different conditions on the same
    graph.
    """
    rules = [_rule("A", writes=["decision"]), _rule("B", writes=["decision"], reads=["x"])]
    conflict, = derive_conflicts(rules)
    assert relation_holds(conflict, rules)

    # the same pair as a *dataflow* claim does not hold: B reads x, not decision
    bogus = Relation("A", "B", "dataflow", ("decision",), True, "deterministic", "")
    assert not relation_holds(bogus, rules)


def test_association_revalidates_on_passage_as_well_as_input():
    rules = [
        _rule("A", reads=["shared"], passages=[("d.txt", "s1")]),
        _rule("B", reads=["shared"], passages=[("d.txt", "s1")]),
    ]
    for rel in derive_associations(rules):
        assert relation_holds(rel, rules)


# ---------------------------------------------------------------------------
# refusals
# ---------------------------------------------------------------------------

def test_undecidable_legacy_kinds_are_refused_with_a_reason():
    """Kinds the contract cannot express are refused, not relabelled.

    Same posture utils/lexec_ir.py takes toward constructs it cannot lower.
    """
    for kind, code in (
        ("sequential", "NO_TEMPORAL_SEMANTICS"),
        ("override", "NO_PRECEDENCE"),
        ("complementary", "NOT_A_DEPENDENCY"),
        ("validation", "NO_ACCEPTANCE_CONDITION"),
        ("contradictory", "BELONGS_TO_CONFLICT"),
    ):
        refusal = refusal_for_declared_kind(kind)
        assert refusal is not None and refusal.code == code
        assert refusal.detail and not refusal.detail.endswith(".")


def test_decidable_kinds_are_not_refused():
    assert refusal_for_declared_kind("conditional") is None
    assert refusal_for_declared_kind("prerequisite") is None


# ---------------------------------------------------------------------------
# top level
# ---------------------------------------------------------------------------

def test_derive_relations_keeps_the_kinds_separate():
    """Associations and conflicts must never land in the dependency list.

    Both are symmetric; folding either into a directed graph would invent an
    ordering the evidence does not support.
    """
    graph = {"business_rules": [
        _rule("A", writes=["x"], passages=[("d.txt", "s1")]),
        _rule("B", reads=["x", "ext"], passages=[("d.txt", "s1")]),
        _rule("C", reads=["ext"]),
        _rule("D", writes=["x"]),
    ]}
    result = derive_relations(graph, declared_kinds=["sequential", "override", "sequential"])

    assert all(r.kind in ("dataflow", "gating") and r.directed for r in result.dependencies)
    assert all(r.kind == "conflict" and not r.directed for r in result.conflicts)
    assert all(r.kind == "association" and not r.directed for r in result.associations)

    assert ("A", "D") in {(r.source_rule_id, r.target_rule_id) for r in result.conflicts}
    assert {r.kind for r in result.refusals} == {"sequential", "override"}  # deduplicated

    payload = result.as_dict()
    assert payload["counts"]["dependencies"] == len(result.dependencies)


def test_empty_graph_produces_nothing_rather_than_failing():
    result = derive_relations({"business_rules": []})
    assert result.as_dict()["counts"] == {
        "dependencies": 0, "conflicts": 0, "associations": 0, "refusals": 0,
    }
