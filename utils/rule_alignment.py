"""Old/new rule-version alignment (RegDelta, plan/proposal.md Section 6.4).

The full alignment contract is staged: exact benchmark ID, then unique source
citation, then source-section-plus-output-signature, normalized
predicate/effect structure, constrained semantic similarity, and explicit
review. The first two stages are implemented here. A citation is accepted
only when it identifies one unmatched rule on each side; embedding similarity
never silently establishes identity.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Mapping, Sequence


ALIGNMENT_KINDS = {"one_to_one", "added", "removed"}

_CITATION = re.compile(r"\b([A-Z][0-9]+(?:-[0-9]+)+(?:\.[0-9]+)*)\b")


def citation_code(value: Any) -> str | None:
    """Return a normalized regulatory section code, if the source records one."""
    match = _CITATION.search(str(value or "").upper())
    return match.group(1) if match else None


def _citations(rule: Mapping[str, Any]) -> set[str]:
    references = rule.get("source_reference")
    records = references if isinstance(references, list) else [references]
    codes: set[str] = set()
    for reference in records:
        if isinstance(reference, Mapping):
            code = citation_code(reference.get("section_id") or reference.get("section"))
            if code:
                codes.add(code)
    return codes


def align_rules(
    old_rules: Sequence[Mapping[str, Any]], new_rules: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Align independently extracted versions by ID, then unique citation.

    A source-citation alignment proves document correspondence only; semantic
    equality remains the responsibility of the differential classifier. A
    citation with multiple candidate rules on either side is left unmatched.
    """
    old_by_id = {str(rule.get("rule_id")): rule for rule in old_rules if rule.get("rule_id")}
    new_by_id = {str(rule.get("rule_id")): rule for rule in new_rules if rule.get("rule_id")}
    shared_ids = set(old_by_id) & set(new_by_id)
    alignments = [
        {"kind": "one_to_one", "old_rule_ids": [rule_id], "new_rule_ids": [rule_id], "method": "exact_id"}
        for rule_id in sorted(shared_ids)
    ]
    old_by_citation: dict[str, list[str]] = defaultdict(list)
    new_by_citation: dict[str, list[str]] = defaultdict(list)
    for rule_id, rule in old_by_id.items():
        for code in _citations(rule) if rule_id not in shared_ids else ():
            old_by_citation[code].append(rule_id)
    for rule_id, rule in new_by_id.items():
        for code in _citations(rule) if rule_id not in shared_ids else ():
            new_by_citation[code].append(rule_id)

    aligned_old, aligned_new = set(shared_ids), set(shared_ids)
    for code in sorted(set(old_by_citation) & set(new_by_citation)):
        old_ids, new_ids = sorted(old_by_citation[code]), sorted(new_by_citation[code])
        if len(old_ids) == len(new_ids) == 1 and old_ids[0] not in aligned_old and new_ids[0] not in aligned_new:
            old_id, new_id = old_ids[0], new_ids[0]
            alignments.append({
                "kind": "one_to_one", "old_rule_ids": [old_id], "new_rule_ids": [new_id],
                "method": "source_citation", "evidence": {"citation_code": code},
            })
            aligned_old.add(old_id)
            aligned_new.add(new_id)
    for rule_id in sorted(new_by_id.keys() - aligned_new):
        alignments.append({"kind": "added", "old_rule_ids": [], "new_rule_ids": [rule_id], "method": "unmatched"})
    for rule_id in sorted(old_by_id.keys() - aligned_old):
        alignments.append({"kind": "removed", "old_rule_ids": [rule_id], "new_rule_ids": [], "method": "unmatched"})
    return alignments


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
