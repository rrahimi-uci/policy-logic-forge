"""Old/new rule-version alignment (RegDelta, plan/proposal.md Section 6.4).

The full alignment contract is staged: exact benchmark ID or citation, then
source-section-plus-output-signature, then normalized predicate/effect
structure, then constrained semantic similarity, then explicit review. Only
the first stage -- exact rule ID -- is implemented here. It is sufficient
for Tier 1 (plan/regdelta-product-plan.md Section 6.4): a hand-edited fork
of one real graph keeps every rule ID unchanged, so alignment is exact by
construction. The later stages are required once independently-extracted
"old" and "new" runs are aligned (Tier 2 and beyond) and are explicitly not
implemented yet -- embedding similarity alone must never silently establish
identity, so an unresolved rule ID pair must never be guessed at here.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


ALIGNMENT_KINDS = {"one_to_one", "added", "removed"}


def align_by_id(old_rule_ids: Sequence[str], new_rule_ids: Sequence[str]) -> list[dict[str, Any]]:
    """Align two rule-ID sets by exact identity.

    Returns one alignment record per rule ID present on either side, sorted
    for determinism. A rule ID present on both sides is ``one_to_one``; a
    rule ID present only on the new side is ``added``; only on the old side
    is ``removed``. This function does not inspect rule content at all --
    see ``utils.semantic_diff`` for classifying what changed within a
    ``one_to_one`` pair.
    """

    old_ids = set(old_rule_ids)
    new_ids = set(new_rule_ids)
    alignments: list[dict[str, Any]] = []
    for rule_id in sorted(old_ids & new_ids):
        alignments.append({"kind": "one_to_one", "old_rule_ids": [rule_id], "new_rule_ids": [rule_id], "method": "exact_id"})
    for rule_id in sorted(new_ids - old_ids):
        alignments.append({"kind": "added", "old_rule_ids": [], "new_rule_ids": [rule_id], "method": "exact_id"})
    for rule_id in sorted(old_ids - new_ids):
        alignments.append({"kind": "removed", "old_rule_ids": [rule_id], "new_rule_ids": [], "method": "exact_id"})
    return alignments


def rules_by_id(ir: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Index one compiled IR document's ``rules`` array by rule id."""

    return {rule["id"]: rule for rule in ir.get("rules", []) if isinstance(rule, Mapping) and rule.get("id")}
