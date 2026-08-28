"""Downstream impact propagation over a dependency DAG (Section 6.5).

``Direct(D,L)`` is the set of rules whose old/new comparison is not
``unchanged`` (including added/removed rules, and rules refused by the
compiler on one side but not the other). ``Potential(D,L)`` is the
executable downstream closure of ``Direct`` over the dependency DAG's edges
(``source_rule_id -> target_rule_id``): every rule reachable by following
edges forward from a directly-changed rule. Full replay is the correctness
oracle; an incremental ``Recompute`` set may only claim savings when its
observable outputs exactly match full replay.

Status resolution combines ``Potential`` membership with the pipeline's own
``requires_review`` flag. This repository's dependency DAG links rules by
narrative/semantic judgment, not by a shared IR symbol between one rule's
outcome and the next rule's precondition (a concrete, real example is
documented in plan/regdelta-product-plan.md Section 6.5), so a rule whose
own text has not been confirmed executable-ready can never be conservatively
resolved to changed/unchanged just because its own comparison happens to
show no difference -- it is reported as ``unresolved-review`` whenever it
appears in ``Potential``, regardless of its own comparison result.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping


def direct_set(changes: Mapping[str, Mapping[str, Any]]) -> set[str]:
    """Rule IDs whose own old/new comparison is not ``unchanged``.

    ``changes`` must already cover every rule ID under consideration (added,
    removed, one-to-one, and refused-to-compile alike) with a
    ``{"taxonomy": ..., "detail": ...}`` record per rule ID -- see
    ``utils.semantic_diff.classify_change`` for one-to-one pairs.
    """

    return {rule_id for rule_id, change in changes.items() if change.get("taxonomy") != "unchanged"}


def potential_set(direct: Iterable[str], edges: Iterable[tuple[str, str]]) -> set[str]:
    """The downstream closure of ``direct`` over DAG edges (source -> target)."""

    adjacency: dict[str, set[str]] = defaultdict(set)
    for source, target in edges:
        adjacency[source].add(target)
    potential = set(direct)
    frontier = list(potential)
    while frontier:
        current = frontier.pop()
        for downstream in adjacency.get(current, ()):
            if downstream not in potential:
                potential.add(downstream)
                frontier.append(downstream)
    return potential


def recompute_set(*, potential: Iterable[str], direct: Iterable[str], review_status: Mapping[str, bool]) -> set[str]:
    """Potential-but-not-direct rules that are candidates for re-execution.

    A rule is only a Recompute candidate if it is not itself
    ``requires_review``: a review-required rule is reported as
    ``unresolved-review`` instead of being (silently) recomputed with
    unwarranted confidence -- see the module docstring.
    """

    direct_set_ = set(direct)
    return {rule_id for rule_id in set(potential) - direct_set_ if not review_status.get(rule_id)}


def resolve_statuses(
    *,
    universe: Iterable[str],
    potential: Iterable[str],
    review_status: Mapping[str, bool],
    changes: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Resolve one reported status per rule ID in ``universe``.

    - No entry in ``changes`` at all (compiled on neither side):
      ``refused-unsupported-construct``.
    - ``requires_review`` *and* reached by an actual change (in
      ``potential``): ``unresolved-review``, overriding whatever the rule's
      own comparison says. This is deliberately narrower than "any
      review-required rule": an untouched review-required rule that is not
      downstream of anything that changed is not being asked to trust a
      newly-propagated fact, so its own (unedited, therefore ``unchanged``)
      comparison stands.
    - Otherwise: the rule's own comparison taxonomy from ``changes``
      (a ``changed``-family label, or ``unchanged``).
    """

    potential_set_ = set(potential)
    statuses: dict[str, dict[str, Any]] = {}
    for rule_id in universe:
        change = changes.get(rule_id)
        if change is None:
            statuses[rule_id] = {"status": "refused-unsupported-construct", "detail": "not compiled on either side"}
            continue
        if review_status.get(rule_id) and rule_id in potential_set_:
            statuses[rule_id] = {"status": "unresolved-review", "detail": None}
            continue
        statuses[rule_id] = {"status": change["taxonomy"], "detail": change.get("detail")}
    return statuses
