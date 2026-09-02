"""Domain-neutral applicability-scope helpers.

The rule contract represents scope as a mapping from a domain-defined dimension
name to a list of admitted values.  The pipeline must never assume that every
domain uses mortgage dimensions such as ``loan_types``.  These helpers keep the
shape invariant universal while leaving the vocabulary to the active domain.
"""
from __future__ import annotations

from typing import Any, Mapping


def normalized_scope(scope: Any) -> dict[str, list[Any]]:
    """Return a clean dimension mapping, or an empty mapping for malformed data."""
    if not isinstance(scope, Mapping):
        return {}
    return {
        str(key).strip(): list(values)
        for key, values in scope.items()
        if str(key).strip() and isinstance(values, list)
    }


def scope_shape_issues(scope: Any) -> list[str]:
    """Describe violations of the domain-neutral ``dimension -> list`` shape."""
    if not isinstance(scope, Mapping):
        return ["scope must be an object whose values are lists"]
    issues: list[str] = []
    for key, values in scope.items():
        name = str(key).strip()
        if not name:
            issues.append("scope contains an empty dimension name")
        if not isinstance(values, list):
            issues.append(f"scope dimension {name or '<empty>'} must be list-valued")
    return issues


def populated_scope(scope: Any) -> dict[str, list[Any]]:
    """Return only dimensions carrying at least one non-empty value."""
    return {
        key: [value for value in values if value not in (None, "")]
        for key, values in normalized_scope(scope).items()
        if any(value not in (None, "") for value in values)
    }


def scopes_may_overlap(left: Any, right: Any) -> bool:
    """Fail closed only when a shared populated dimension is provably disjoint.

    Missing dimensions mean "not constrained here", not an empty universe.  A
    pair is therefore rejected only when both rules constrain the same dimension
    and the normalized value sets do not intersect.
    """
    left_dims, right_dims = populated_scope(left), populated_scope(right)
    for dimension in set(left_dims) & set(right_dims):
        left_values = {str(value).strip().casefold() for value in left_dims[dimension]}
        right_values = {str(value).strip().casefold() for value in right_dims[dimension]}
        if left_values.isdisjoint(right_values):
            return False
    return True


def newly_populated_dimension_count(before: Any, after: Any) -> int:
    """Count dimensions that changed from empty/absent to populated."""
    old, new = populated_scope(before), populated_scope(after)
    return sum(bool(values) and not old.get(key) for key, values in new.items())
