"""Solver-backed promotion of a dataflow relation to a gating relation.

``utils/rule_dependencies`` derives that a target rule *reads* a symbol the
source *assigns*.  That is a real dependency, but it is the weaker of the two
claims worth making.  The stronger one -- what the retired ``prerequisite``
label gestured at without ever testing -- is that the target **cannot be
evaluated at all** unless the source's outcome holds.

That is decidable.  If the source assigns ``s = v``, the target is gated on it
exactly when ``condition(target) ∧ s ≠ v`` has no satisfying assignment: there
is no world in which the target fires while the source's outcome is absent.
This module builds that query and hands it to ``utils/smt.py``.

Everything here is best-effort by construction.  Only a rule that lowers to
LExec IR can be asked about, the solver enumerates finite domains and reports
``unknown`` rather than guessing past them, and a rule pair that cannot be
decided returns ``None``.  ``classify_gating`` promotes only on ``True``, so
every undecidable case reports as the weaker ``dataflow`` claim rather than
being talked up into the stronger one.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from utils.lexec_ir import lower_graph
from utils.smt import MAX_ASSIGNMENTS, query_overlap

__all__ = ["make_entailment_oracle", "gating_stats"]


def _negated_outcome(effect: Mapping[str, Any], symbol: str) -> dict[str, Any] | None:
    """``s ≠ v`` for the effect that assigns ``symbol``, or None if unusable."""
    if str(effect.get("target") or "").strip().lower() != symbol:
        return None
    if str(effect.get("kind") or "") != "assignment":
        return None                      # only a plain assignment pins a value
    value = effect.get("value")
    if not isinstance(value, Mapping) or "literal" not in value:
        return None                      # a computed effect pins no single value
    return {"op": "ne", "left": {"symbol": symbol}, "right": dict(value)}


def make_entailment_oracle(
    graph: Mapping[str, Any],
    *,
    max_assignments: int = MAX_ASSIGNMENTS,
    document_id: str = "gating-probe",
) -> tuple[Callable[[Mapping[str, Any], Mapping[str, Any], str], bool | None], dict[str, Any]]:
    """Build an ``entails(source_rule, target_rule, symbol)`` oracle for a graph.

    Returns the oracle and a stats dict describing how much of the graph it can
    actually speak about, so a caller can report coverage rather than implying
    the whole graph was checked.  Lowering happens once here, not per query.
    """
    ir = lower_graph(graph, document_id=document_id)
    lowered = {str(rule.get("id")): rule for rule in ir.get("rules", []) if isinstance(rule, Mapping)}
    symbols = ir.get("symbols", [])
    stats: dict[str, Any] = {
        "rules_lowered": len(lowered),
        "rules_refused": len(ir.get("refusals", [])),
        "queries": 0,
        "entailed": 0,
        "not_entailed": 0,
        "undecided": 0,
    }

    def entails(source_rule: Mapping[str, Any], target_rule: Mapping[str, Any], symbol: str) -> bool | None:
        source_ir = lowered.get(str(source_rule.get("rule_id")))
        target_ir = lowered.get(str(target_rule.get("rule_id")))
        if source_ir is None or target_ir is None:
            stats["undecided"] += 1
            return None                  # one side never lowered: unanswerable

        name = str(symbol or "").strip().lower()
        negations = [
            formula for formula in (
                _negated_outcome(effect, name)
                for effect in source_ir.get("effects", []) or []
                if isinstance(effect, Mapping)
            ) if formula is not None
        ]
        if not negations:
            stats["undecided"] += 1
            return None

        # Several effects may touch the symbol; the target is gated only if it
        # is incompatible with the outcome being absent in every one of them.
        verdicts = []
        for negation in negations:
            stats["queries"] += 1
            result = query_overlap(
                target_ir,
                {"id": f"__not_{name}", "condition": negation},
                symbols,
                max_assignments=max_assignments,
            )
            verdicts.append(result.get("overlap"))

        if any(verdict is None for verdict in verdicts):
            stats["undecided"] += 1
            return None                  # solver could not close the search
        if all(verdict is False for verdict in verdicts):
            stats["entailed"] += 1
            return True                  # unsat everywhere: target requires the outcome
        stats["not_entailed"] += 1
        return False

    return entails, stats


def gating_stats(stats: Mapping[str, Any]) -> str:
    """One line describing what the oracle could and could not decide."""
    return (
        f"{stats.get('entailed', 0)} gating, {stats.get('not_entailed', 0)} plain dataflow, "
        f"{stats.get('undecided', 0)} undecided "
        f"({stats.get('rules_lowered', 0)} rules lowered, {stats.get('rules_refused', 0)} refused)"
    )
