"""Semantic change classification for one aligned rule pair.

Implements the closed taxonomy from plan/proposal.md Section 6.3, at the
granularity two already-compiled LExec IR rules make observable: their
``scope``, ``condition``, ``exceptions``, and ``effects``. Comparison
deliberately ignores ``provenance`` (source spans), since compiling the same
unedited rule out of two different document snapshots legitimately produces
different provenance without the rule itself having changed.

This module classifies exactly one rule pair at a time and does not decide
whether that pair should be reported at all -- see ``utils.impact_propagation``
for how a rule's changed/unchanged classification combines with its
downstream reachability and review status into a reported disposition.

Taxonomy coverage is intentionally partial: a single-literal change at one
comparison node is classified precisely (including a best-effort
strengthening/weakening direction for ordered comparisons); anything more
structurally complex is still classified, but only as an honestly-labeled
catch-all (``condition_change_other``, ``multi_field_change``) rather than
guessed at. Rule addition/removal and dependency change are alignment- and
propagation-level concepts respectively and are not produced here.
"""

from __future__ import annotations

from typing import Any, Mapping


_UNCLASSIFIED = object()

# For an ordered comparison, whether *increasing* the right-hand literal
# narrows the set of inputs that satisfy it (1) or widens it (-1). Used to
# report a best-effort strengthening ("narrower, harder to satisfy") /
# weakening ("broader, easier to satisfy") direction; unordered predicates
# (eq/ne/contains) have no direction.
_ORDERED_DIRECTION = {"gt": 1, "ge": 1, "lt": -1, "le": -1}


def _without_provenance(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _without_provenance(item) for key, item in value.items() if key != "provenance"}
    if isinstance(value, list):
        return [_without_provenance(item) for item in value]
    return value


def _single_literal_diff(old: Any, new: Any) -> Any:
    """Return the one differing (op, symbol, old/new literal) leaf, if the
    two formula trees are otherwise structurally identical; ``_UNCLASSIFIED``
    otherwise (including when nothing differs at this node, which the caller
    should not reach for genuinely differing subtrees)."""

    if old == new:
        return _UNCLASSIFIED
    if not isinstance(old, Mapping) or not isinstance(new, Mapping) or old.get("op") != new.get("op"):
        return _UNCLASSIFIED
    op = old["op"]
    if op in {"and", "or"}:
        old_args, new_args = old.get("args") or [], new.get("args") or []
        if len(old_args) != len(new_args):
            return _UNCLASSIFIED
        found: Any = None
        for old_arg, new_arg in zip(old_args, new_args):
            if old_arg == new_arg:
                continue
            if found is not None:
                return _UNCLASSIFIED  # more than one differing branch
            found = _single_literal_diff(old_arg, new_arg)
            if found is _UNCLASSIFIED:
                return _UNCLASSIFIED
        return found if found is not None else _UNCLASSIFIED
    if op in {"eq", "ne", "lt", "le", "gt", "ge", "contains"}:
        if old.get("left") != new.get("left"):
            return _UNCLASSIFIED
        old_right, new_right = old.get("right"), new.get("right")
        if not (
            isinstance(old_right, Mapping) and set(old_right) == {"literal", "type"}
            and isinstance(new_right, Mapping) and set(new_right) == {"literal", "type"}
            and old_right.get("type") == new_right.get("type")
        ):
            return _UNCLASSIFIED
        left = old.get("left")
        symbol = left.get("symbol") if isinstance(left, Mapping) else None
        return {"op": op, "symbol": symbol, "old_literal": old_right.get("literal"), "new_literal": new_right.get("literal")}
    return _UNCLASSIFIED


def _direction(diff: Mapping[str, Any]) -> str | None:
    slope = _ORDERED_DIRECTION.get(diff["op"])
    old_v, new_v = diff["old_literal"], diff["new_literal"]
    if slope is None or not isinstance(old_v, (int, float)) or not isinstance(new_v, (int, float)):
        return None
    if isinstance(old_v, bool) or isinstance(new_v, bool) or new_v == old_v:
        return None
    increased = new_v > old_v
    return "strengthening" if increased == (slope == 1) else "weakening"


def classify_change(old_rule: Mapping[str, Any], new_rule: Mapping[str, Any]) -> dict[str, Any]:
    """Classify one aligned (old, new) IR rule pair.

    Returns ``{"taxonomy": <label>, "detail": <dict|None>}``. ``taxonomy``
    is one of: ``unchanged``, ``threshold_or_constant_change``,
    ``condition_change_other``, ``output_effect_change``, ``scope_change``,
    ``exception_added``, ``exception_removed``, ``exception_change_other``,
    ``multi_field_change``.
    """

    old_c, new_c = _without_provenance(old_rule), _without_provenance(new_rule)
    if old_c == new_c:
        return {"taxonomy": "unchanged", "detail": None}

    changed_fields = {
        field for field in ("scope", "condition", "exceptions", "effects")
        if old_c.get(field) != new_c.get(field)
    }

    if changed_fields == {"condition"}:
        diff = _single_literal_diff(old_c["condition"], new_c["condition"])
        if diff is not _UNCLASSIFIED:
            return {"taxonomy": "threshold_or_constant_change", "detail": {**diff, "direction": _direction(diff)}}
        return {"taxonomy": "condition_change_other", "detail": None}

    if changed_fields == {"effects"}:
        return {"taxonomy": "output_effect_change", "detail": {"old_effects": old_c["effects"], "new_effects": new_c["effects"]}}

    if changed_fields == {"scope"}:
        return {"taxonomy": "scope_change", "detail": {"old_scope": old_c["scope"], "new_scope": new_c["scope"]}}

    if changed_fields == {"exceptions"}:
        old_ids = {exception["id"] for exception in old_c["exceptions"]}
        new_ids = {exception["id"] for exception in new_c["exceptions"]}
        if new_ids - old_ids and not (old_ids - new_ids):
            return {"taxonomy": "exception_added", "detail": {"added": sorted(new_ids - old_ids)}}
        if old_ids - new_ids and not (new_ids - old_ids):
            return {"taxonomy": "exception_removed", "detail": {"removed": sorted(old_ids - new_ids)}}
        return {"taxonomy": "exception_change_other", "detail": None}

    return {"taxonomy": "multi_field_change", "detail": {"changed_fields": sorted(changed_fields)}}
