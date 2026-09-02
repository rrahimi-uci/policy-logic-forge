"""Tests for utils/rule_gating.py — solver-backed dataflow -> gating promotion.

``dataflow`` says the target reads a symbol the source assigns. ``gating`` is
the stronger claim: the target cannot be evaluated at all unless the source's
outcome holds. The retired ``prerequisite`` label asserted that without ever
testing it; here it is decided by asking whether ``condition(target) ∧ s ≠ v``
has any satisfying assignment.

The property these tests protect above all is that every undecidable case
returns ``None`` rather than a guess, because ``classify_gating`` promotes only
on ``True``.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.rule_dependencies import classify_gating, derive_dataflow  # noqa: E402
from utils.rule_gating import gating_stats, make_entailment_oracle  # noqa: E402


def _rule(rule_id, *, reads=(), writes=(), read_value=True, write_value=True):
    """A rule that lowers cleanly: boolean symbols, plain equality, one effect.

    Every rule carries a rule-local predicate and outcome as well, because the
    lowering contract requires at least one of each -- a rule that only reads or
    only writes is refused before any gating question can be asked of it.
    """
    reads = list(reads) + [f"{rule_id}_applies".lower()]
    writes = list(writes) + [f"{rule_id}_result".lower()]
    predicates = [
        {"predicate_id": f"p{i}", "variable": name, "operator": "==",
         "value": read_value if i <= len(reads) - 1 else True, "value_type": "boolean"}
        for i, name in enumerate(reads, 1)
    ]
    return {
        "rule_id": rule_id,
        "schema_version": "2.0",
        "rule_type": "obligation",
        "condition_predicates": predicates,
        "condition_logic": {"all": [{"predicate_ref": p["predicate_id"]} for p in predicates]},
        "outcomes": [
            {"variable": name, "operator": "=",
             "value": write_value if name != f"{rule_id}_result".lower() else True,
             "value_type": "boolean"}
            for name in writes
        ],
        "variables": (
            [{"name": n, "type": "boolean", "role": "input"} for n in reads]
            + [{"name": n, "type": "boolean", "role": "output"} for n in writes]
        ),
        "recommended_hit_policy": "UNIQUE",
        "mandatory": True,
        "source_reference": {
            "chunk_path": "policy.txt", "section_id": "s1",
            "source_text": f"Rule {rule_id} applies as stated.",
        },
    }


def _graph(*rules):
    return {"business_rules": list(rules)}


def test_target_requiring_the_produced_value_is_gating():
    """A writes x=true; B fires only when x is true, so B is gated on A.

    ``condition(B) ∧ x ≠ true`` is unsatisfiable, which is exactly the
    entailment the old `prerequisite` label claimed without checking.
    """
    graph = _graph(_rule("A", writes=["x"], write_value=True),
                   _rule("B", reads=["x"], read_value=True))
    entails, stats = make_entailment_oracle(graph)
    promoted = classify_gating(derive_dataflow(graph), graph, entails=entails)

    assert [r.kind for r in promoted] == ["gating"]
    assert promoted[0].basis == "solver"
    assert stats["entailed"] == 1 and stats["undecided"] == 0


def test_target_reading_the_opposite_value_is_not_gating():
    """A writes x=true but B fires when x is false: B is not gated on A.

    The dataflow relation is still real -- B reads what A writes -- so it must
    survive as the weaker claim rather than disappearing.
    """
    graph = _graph(_rule("A", writes=["x"], write_value=True),
                   _rule("B", reads=["x"], read_value=False))
    entails, stats = make_entailment_oracle(graph)
    promoted = classify_gating(derive_dataflow(graph), graph, entails=entails)

    assert [r.kind for r in promoted] == ["dataflow"]
    assert stats["not_entailed"] == 1


def test_a_rule_that_does_not_lower_is_undecided_not_assumed():
    """One side unrepresentable means unanswerable, never a promotion."""
    graph = _graph(_rule("A", writes=["x"]), _rule("B", reads=["x"]))
    graph["business_rules"][0]["applicability_scope"] = {"predicate": "unrepresentable"}
    graph["business_rules"][0]["scope_basis"] = "inferred"

    entails, stats = make_entailment_oracle(graph)
    promoted = classify_gating(derive_dataflow(graph), graph, entails=entails)

    assert [r.kind for r in promoted] == ["dataflow"]
    assert stats["undecided"] >= 1
    assert stats["entailed"] == 0


def test_unknown_symbol_is_undecided():
    """Asked about a symbol the source never assigns, the oracle abstains."""
    graph = _graph(_rule("A", writes=["x"]), _rule("B", reads=["x"]))
    entails, stats = make_entailment_oracle(graph)
    source, target = graph["business_rules"]
    assert entails(source, target, "not_a_symbol") is None
    assert stats["undecided"] == 1


def test_oracle_reports_its_own_coverage():
    """A caller must be able to say how much of the graph was actually checked."""
    graph = _graph(_rule("A", writes=["x"]), _rule("B", reads=["x"]))
    _, stats = make_entailment_oracle(graph)
    assert stats["rules_lowered"] == 2 and stats["rules_refused"] == 0
    assert "rules lowered" in gating_stats(stats)


def test_promotion_never_happens_without_the_oracle():
    """The wiring is opt-in: no oracle, no gating, regardless of the graph."""
    graph = _graph(_rule("A", writes=["x"]), _rule("B", reads=["x"]))
    assert [r.kind for r in classify_gating(derive_dataflow(graph), graph)] == ["dataflow"]
