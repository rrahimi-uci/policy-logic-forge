"""Bounded reference evaluator for the declared LExec IR v1 subset.

This evaluator is intentionally small and independent from the lowering
implementation.  It executes only a table whose policy proof is ``proved``;
unknown, refused, or timeout proof records fail closed.  Formula evaluation
uses the IR's Kleene three-valued semantics and returns structured diagnostics
instead of converting missing data into false or a successful output.
"""

from __future__ import annotations

import math
import re
from typing import Any, Mapping, Sequence

from utils.lexec_ir import validate_ir


UNKNOWN = None
_RANGE = re.compile(r"^([\[\(])\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*,\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*([\]\)])$")


def _operand(value: Any, environment: Mapping[str, Any]) -> Any:
    if isinstance(value, Mapping) and set(value) == {"symbol"}:
        return environment.get(value.get("symbol"), UNKNOWN)
    if isinstance(value, Mapping) and set(value) == {"literal", "type"}:
        return value.get("literal")
    return UNKNOWN


def _not(value: bool | None) -> bool | None:
    return UNKNOWN if value is UNKNOWN else not value


def _and(values: Sequence[bool | None]) -> bool | None:
    if any(value is False for value in values):
        return False
    return True if values and all(value is True for value in values) else UNKNOWN


def _or(values: Sequence[bool | None]) -> bool | None:
    if any(value is True for value in values):
        return True
    return False if values and all(value is False for value in values) else UNKNOWN


def _compare(op: str, left: Any, right: Any) -> bool | None:
    if left is UNKNOWN or right is UNKNOWN or left is None or right is None:
        return UNKNOWN
    try:
        if op == "eq":
            return left == right
        if op == "ne":
            return left != right
        if op == "lt":
            return left < right
        if op == "le":
            return left <= right
        if op == "gt":
            return left > right
        if op == "ge":
            return left >= right
        if op == "contains":
            return isinstance(left, str) and isinstance(right, str) and right in left
    except (TypeError, ValueError):
        return UNKNOWN
    return UNKNOWN


def _in_range(value: Any, range_text: Any) -> bool | None:
    if value is UNKNOWN or range_text is UNKNOWN or value is None or range_text is None:
        return UNKNOWN
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isinstance(range_text, str):
        return UNKNOWN
    match = _RANGE.fullmatch(range_text)
    if not match:
        return UNKNOWN
    lower, upper = float(match.group(2)), float(match.group(3))
    if not math.isfinite(lower) or not math.isfinite(upper):
        return UNKNOWN
    return (value >= lower if match.group(1) == "[" else value > lower) and (value <= upper if match.group(4) == "]" else value < upper)


def evaluate_formula(formula: Mapping[str, Any], environment: Mapping[str, Any]) -> bool | None:
    """Evaluate one IR formula as true, false, or unknown."""

    op = formula.get("op")
    if op in {"and", "or"}:
        values = [evaluate_formula(child, environment) for child in formula.get("args", [])]
        return _and(values) if op == "and" else _or(values)
    if op == "not":
        return _not(evaluate_formula(formula.get("arg"), environment))
    if op == "is_null":
        value = _operand(formula.get("arg"), environment)
        return value is None or value is UNKNOWN
    if op == "in_binned_range":
        return _in_range(_operand(formula.get("left"), environment), _operand(formula.get("right"), environment))
    if op in {"eq", "ne", "lt", "le", "gt", "ge", "contains"}:
        return _compare(op, _operand(formula.get("left"), environment), _operand(formula.get("right"), environment))
    return UNKNOWN


def _effect_value(effect: Mapping[str, Any], environment: Mapping[str, Any]) -> Any:
    return _operand(effect.get("value"), environment)


def _scope_available(scope: Mapping[str, Any]) -> tuple[bool, str | None]:
    metadata = scope.get("metadata") if isinstance(scope.get("metadata"), Mapping) else {}
    # The v1 evaluator has no jurisdiction/party/date context.  Refusing here
    # is safer than silently treating a contextual scope as universal.
    contextual = {
        "jurisdictions": metadata.get("jurisdictions") or [],
        "parties": metadata.get("parties") or [],
        "effective_from": metadata.get("effective_from"),
        "effective_to": metadata.get("effective_to"),
        "document_version": metadata.get("document_version"),
    }
    if any(value for value in contextual.values()):
        return False, "scope metadata requires runtime context not provided by the bounded evaluator"
    return True, None


def _evaluate_rule(rule: Mapping[str, Any], inputs: Mapping[str, Any]) -> tuple[str, dict[str, Any], str | None]:
    scope = rule.get("scope") if isinstance(rule.get("scope"), Mapping) else {}
    available, scope_reason = _scope_available(scope)
    if not available:
        return "unknown", {}, scope_reason
    environment = dict(inputs)
    predicate = scope.get("predicate")
    if predicate is not None:
        scope_value = evaluate_formula(predicate, environment)
        if scope_value is False:
            return "no_match", {}, None
        if scope_value is not True:
            return "unknown", {}, "scope predicate is unknown"
    condition = evaluate_formula(rule.get("condition"), environment)
    if condition is False:
        return "no_match", {}, None
    if condition is not True:
        return "unknown", {}, "rule condition is unknown"
    unknown_exception = False
    for exception in rule.get("exceptions", []) or []:
        value = evaluate_formula(exception.get("condition"), environment)
        if value is True:
            return "defeated", {}, None
        if value is UNKNOWN:
            unknown_exception = True
    if unknown_exception:
        return "unknown", {}, "exception condition is unknown"
    outputs: dict[str, Any] = {}
    for effect in rule.get("effects", []) or []:
        value = _effect_value(effect, environment)
        if value is UNKNOWN:
            return "unknown", {}, "effect value is unknown"
        target = str(effect.get("target"))
        if target in outputs and outputs[target] != value:
            return "conflict", {}, f"rule assigns incompatible values to {target!r}"
        outputs[target] = value
        environment[target] = value
    return "matched", outputs, None


def _result(status: str, table_id: str | None, *, matched: Sequence[str] = (), unknown: Sequence[str] = (), outputs: Mapping[str, Any] | None = None, diagnostics: Sequence[Mapping[str, Any] | str] = ()) -> dict[str, Any]:
    return {
        "status": status,
        "table_id": table_id,
        "matched_rule_ids": list(matched),
        "unknown_rule_ids": list(unknown),
        "outputs": dict(outputs or {}),
        "diagnostics": list(diagnostics),
    }


def evaluate_ir(ir: Mapping[str, Any], inputs: Mapping[str, Any], *, table_id: str | None = None) -> dict[str, Any]:
    """Evaluate one LExec IR document with fail-closed table semantics."""

    errors = validate_ir(ir)
    if errors:
        return _result("refused", table_id, diagnostics=[{"code": "INVALID_IR", "detail": error} for error in errors])
    if not isinstance(inputs, Mapping):
        return _result("refused", table_id, diagnostics=[{"code": "INVALID_INPUTS", "detail": "inputs must be an object"}])

    tables = list(ir.get("tables", []))
    if table_id is not None:
        tables = [table for table in tables if table.get("id") == table_id]
        if not tables:
            return _result("refused", table_id, diagnostics=[{"code": "UNKNOWN_TABLE", "detail": f"No table {table_id!r}"}])
    elif len(tables) > 1:
        return _result("refused", None, diagnostics=[{"code": "TABLE_SELECTION_REQUIRED", "detail": "Multiple tables require an explicit table_id"}])

    rules = {rule.get("id"): rule for rule in ir.get("rules", [])}
    if tables:
        table = tables[0]
        proof = table.get("policy_proof") if isinstance(table.get("policy_proof"), Mapping) else {}
        if proof.get("status") != "proved":
            return _result("refused", table.get("id"), diagnostics=[{"code": "UNPROVED_TABLE_POLICY", "detail": f"Table policy status is {proof.get('status')!r}"}])
        rule_ids = list(table.get("rule_ids", []))
        policy = table.get("hit_policy")
    else:
        table = None
        rule_ids = list(rules)
        policy = "UNIQUE"

    evaluated: list[tuple[str, str, dict[str, Any], str | None]] = []
    for rule_id in rule_ids:
        rule = rules.get(rule_id)
        if rule is None:
            return _result("refused", table.get("id") if table else table_id, diagnostics=[{"code": "MISSING_RULE", "detail": f"Table references {rule_id!r}"}])
        evaluated.append((rule_id, *_evaluate_rule(rule, inputs)))

    matched = [(rule_id, outputs) for rule_id, status, outputs, _ in evaluated if status == "matched"]
    unknown = [rule_id for rule_id, status, _, _ in evaluated if status == "unknown"]
    defeated = [rule_id for rule_id, status, _, _ in evaluated if status == "defeated"]
    conflicts = [(rule_id, reason) for rule_id, status, _, reason in evaluated if status == "conflict"]
    diagnostics: list[dict[str, Any]] = []
    diagnostics.extend({"code": "UNKNOWN_RULE", "rule_id": rule_id, "detail": next(reason for rid, status, _, reason in evaluated if rid == rule_id and status == "unknown")} for rule_id in unknown)
    diagnostics.extend({"code": "DEFEATED_RULE", "rule_id": rule_id} for rule_id in defeated)
    diagnostics.extend({"code": "RULE_CONFLICT", "rule_id": rule_id, "detail": reason} for rule_id, reason in conflicts)
    if conflicts:
        return _result("refused", table.get("id") if table else table_id, unknown=unknown, diagnostics=diagnostics)
    if policy == "UNIQUE":
        if len(matched) > 1:
            return _result("refused", table.get("id") if table else table_id, matched=[rule_id for rule_id, _ in matched], unknown=unknown, diagnostics=[{"code": "UNIQUE_OVERLAP", "detail": "More than one rule matched"}, *diagnostics])
        if unknown:
            return _result("unknown", table.get("id") if table else table_id, matched=[rule_id for rule_id, _ in matched], unknown=unknown, outputs=matched[0][1] if matched else {}, diagnostics=diagnostics)
        return _result("matched" if matched else "no_match", table.get("id") if table else table_id, matched=[rule_id for rule_id, _ in matched], outputs=matched[0][1] if matched else {}, diagnostics=diagnostics)
    if policy == "ANY":
        if unknown:
            return _result("unknown", table.get("id") if table else table_id, matched=[rule_id for rule_id, _ in matched], unknown=unknown, diagnostics=diagnostics)
        outputs: dict[str, Any] = {}
        for _, rule_outputs in matched:
            for key, value in rule_outputs.items():
                if key in outputs and outputs[key] != value:
                    return _result("refused", table.get("id") if table else table_id, matched=[rule_id for rule_id, _ in matched], diagnostics=[{"code": "ANY_OUTPUT_CONFLICT", "detail": f"Conflicting output {key!r}"}])
                outputs[key] = value
        return _result("matched" if matched else "no_match", table.get("id") if table else table_id, matched=[rule_id for rule_id, _ in matched], outputs=outputs, diagnostics=diagnostics)
    if policy == "COLLECT":
        return _result("refused", table.get("id") if table else table_id, diagnostics=[{"code": "COLLECT_NOT_IMPLEMENTED", "detail": "Collect output semantics are not frozen in the bounded evaluator"}])
    return _result("refused", table.get("id") if table else table_id, diagnostics=[{"code": "UNSUPPORTED_HIT_POLICY", "detail": repr(policy)}])
