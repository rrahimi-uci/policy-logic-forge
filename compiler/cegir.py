"""Counterexample-guided, source-preserving repair primitives."""

from __future__ import annotations

import copy
import hashlib
from typing import Any, Callable, Mapping, Sequence


class CEGIRError(ValueError):
    """Raised when a repair would lose provenance or violate an ablation gate."""


def _digest(value: Any) -> str:
    import json
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def apply_repair(ir: Mapping[str, Any], edit: Mapping[str, Any]) -> dict[str, Any]:
    """Apply one explicit replacement while preserving source provenance."""
    if not isinstance(ir, Mapping) or not isinstance(edit, Mapping):
        raise CEGIRError("ir and edit must be objects")
    rule_id, field = edit.get("rule_id"), edit.get("field")
    if not isinstance(rule_id, str) or not isinstance(field, str):
        raise CEGIRError("edit requires rule_id and field")
    result = copy.deepcopy(dict(ir))
    rules = result.get("rules", [])
    rule = next((item for item in rules if isinstance(item, Mapping) and item.get("id") == rule_id), None)
    if rule is None:
        raise CEGIRError(f"unknown rule: {rule_id}")
    if field not in {"condition", "effects", "exceptions", "scope"}:
        raise CEGIRError(f"field is not repairable: {field}")
    if not isinstance(rule.get("provenance"), list) or not rule["provenance"]:
        raise CEGIRError("repair target has no source provenance")
    rule[field] = copy.deepcopy(edit.get("value"))
    result.setdefault("repair_log", []).append({"edit_id": edit.get("edit_id", _digest(edit)[:16]),
                                                 "rule_id": rule_id, "field": field,
                                                 "source_preserved": True})
    return result


def evaluate_repair(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    regression_check: Callable[[Mapping[str, Any]], bool],
    counterexample_check: Callable[[Mapping[str, Any]], bool],
    objective: Callable[[Mapping[str, Any]], float],
) -> dict[str, Any]:
    """Accept a repair only when all frozen guards pass and objective improves."""
    baseline_score, candidate_score = objective(baseline), objective(candidate)
    guards = {
        "source_preservation": all(bool(rule.get("provenance")) for rule in candidate.get("rules", []) if isinstance(rule, Mapping)),
        "regression": bool(regression_check(candidate)),
        "counterexamples": bool(counterexample_check(candidate)),
        "objective_improved": candidate_score > baseline_score,
    }
    accepted = all(guards.values())
    return {"schema_version": "cegir/1.0", "accepted": accepted, "guards": guards,
            "baseline_objective": baseline_score, "candidate_objective": candidate_score,
            "claimable": accepted, "reason": None if accepted else "one or more repair guards failed"}


def ablation_matrix(
    baseline: Mapping[str, Any], candidate: Mapping[str, Any], *,
    evaluate: Callable[[Mapping[str, Any]], Mapping[str, Any]],
) -> dict[str, Any]:
    """Run required deletion/no-op/oracle-withheld/source-preservation controls."""
    deletion = {"rules": []}
    noop = copy.deepcopy(dict(baseline))
    oracle_withheld = copy.deepcopy(dict(candidate))
    oracle_withheld["oracle"] = None
    source_stripped = copy.deepcopy(dict(candidate))
    for rule in source_stripped.get("rules", []):
        if isinstance(rule, dict):
            rule.pop("provenance", None)
    cases = {"baseline": baseline, "candidate": candidate, "deletion": deletion,
             "no_op": noop, "oracle_withheld": oracle_withheld, "source_stripped": source_stripped}
    results = {name: dict(evaluate(value)) for name, value in cases.items()}
    return {"schema_version": "cegir-ablation/1.0", "cases": results,
            "source_preservation_required": True,
            "claimable": bool(results.get("candidate", {}).get("accepted")) and not bool(results.get("source_stripped", {}).get("accepted"))}
