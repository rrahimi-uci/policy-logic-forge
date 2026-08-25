"""Restricted P3-prime representative-cell comparison for known IR tables.

P3-prime is a comparison theorem for two *known* tables whose numeric
thresholds are both contained in an explicit finite set.  It is not a test
generator for an unknown reference artifact and it never replaces exhaustive
enumeration for instrument validation.
"""

from __future__ import annotations

import itertools
import math
import re
from copy import deepcopy
from typing import Any, Mapping, Sequence

from utils.feel import evaluate_ir
from utils.lexec_ir import validate_ir


_RANGE = re.compile(r"^([\[\(])\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*,\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*([\]\)])$")
_NUMERIC = {"int", "real"}
_ALLOWED_OPS = {"and", "or", "not", "eq", "ne", "lt", "le", "gt", "ge", "is_null", "in_binned_range"}


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _symbol_map(ir: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(symbol.get("id")): symbol for symbol in ir.get("symbols", []) if isinstance(symbol, Mapping) and symbol.get("id")}


def _table(ir: Mapping[str, Any], table_id: str | None) -> Mapping[str, Any] | None:
    tables = [table for table in ir.get("tables", []) if isinstance(table, Mapping)]
    if table_id is not None:
        matches = [table for table in tables if table.get("id") == table_id]
    else:
        matches = tables if len(tables) == 1 else []
    return matches[0] if len(matches) == 1 else None


def _formula_symbols(formula: Any) -> set[str]:
    if not isinstance(formula, Mapping):
        return set()
    found: set[str] = set()
    for key in ("left", "right", "arg"):
        operand = formula.get(key)
        if isinstance(operand, Mapping) and set(operand) == {"symbol"}:
            found.add(str(operand["symbol"]))
        elif isinstance(operand, Mapping) and "op" in operand:
            found.update(_formula_symbols(operand))
    for child in formula.get("args", []) if isinstance(formula.get("args"), list) else []:
        found.update(_formula_symbols(child))
    return found


def _numeric_literal(operand: Any) -> float | int | None:
    if not isinstance(operand, Mapping) or set(operand) != {"literal", "type"}:
        return None
    value, literal_type = operand.get("literal"), operand.get("type")
    if literal_type not in _NUMERIC or not _finite_number(value):
        return None
    return value


def _range_bounds(operand: Any) -> tuple[float, float] | None:
    if not isinstance(operand, Mapping) or set(operand) != {"literal", "type"} or operand.get("type") != "string":
        return None
    match = _RANGE.fullmatch(operand.get("literal", ""))
    if not match:
        return None
    lower, upper = float(match.group(2)), float(match.group(3))
    if not math.isfinite(lower) or not math.isfinite(upper) or lower > upper:
        return None
    return lower, upper


def _formula_info(formula: Any, symbols: Mapping[str, Mapping[str, Any]]) -> tuple[set[str], dict[str, set[float | int]], str | None]:
    """Validate the restricted interval language and collect thresholds."""

    if not isinstance(formula, Mapping) or formula.get("op") not in _ALLOWED_OPS:
        return set(), {}, f"unsupported formula operator {formula.get('op') if isinstance(formula, Mapping) else None!r}"
    op = formula["op"]
    if op in {"and", "or"}:
        args = formula.get("args")
        if not isinstance(args, list) or not args:
            return set(), {}, f"{op} requires non-empty args"
        names: set[str] = set()
        thresholds: dict[str, set[float | int]] = {}
        for child in args:
            child_names, child_thresholds, error = _formula_info(child, symbols)
            if error:
                return set(), {}, error
            names.update(child_names)
            for name, values in child_thresholds.items():
                thresholds.setdefault(name, set()).update(values)
        return names, thresholds, None
    if op == "not":
        return _formula_info(formula.get("arg"), symbols)
    if op == "is_null":
        operand = formula.get("arg")
        if not (isinstance(operand, Mapping) and set(operand) == {"symbol"}):
            return set(), {}, "is_null requires a symbol operand"
        name = str(operand.get("symbol"))
        if name not in symbols:
            return set(), {}, f"unknown symbol {name!r}"
        return {name}, {}, None

    left, right = formula.get("left"), formula.get("right")
    operands = (left, right)
    for operand in operands:
        if not isinstance(operand, Mapping) or set(operand) not in ({"symbol"}, {"literal", "type"}):
            return set(), {}, f"{op} requires symbol/literal operands"
        if set(operand) == {"literal", "type"} and operand.get("type") not in {"bool", "int", "real", "enum", "string", "null"}:
            return set(), {}, f"unsupported literal type {operand.get('type')!r}"
    names = _formula_symbols(formula)
    if any(name not in symbols for name in names):
        missing = sorted(name for name in names if name not in symbols)
        return set(), {}, f"unknown symbols: {missing}"
    if op == "in_binned_range":
        left_name = str(left.get("symbol")) if isinstance(left, Mapping) and set(left) == {"symbol"} else None
        bounds = _range_bounds(right)
        if left_name is None or symbols[left_name].get("theory") not in _NUMERIC or bounds is None:
            return set(), {}, "in_binned_range requires a numeric symbol and valid string range"
        return names, {left_name: set(bounds)}, None

    left_type = symbols.get(str(left.get("symbol")), {}).get("theory") if isinstance(left, Mapping) and set(left) == {"symbol"} else left.get("type")
    right_type = symbols.get(str(right.get("symbol")), {}).get("theory") if isinstance(right, Mapping) and set(right) == {"symbol"} else right.get("type")
    if op in {"lt", "le", "gt", "ge"} and (left_type not in _NUMERIC or right_type not in _NUMERIC):
        return set(), {}, f"{op} requires numeric operands"
    if op in {"eq", "ne"} and (left_type == "string" or right_type == "string"):
        return set(), {}, "string equality is outside the interval comparison class"
    if op in {"eq", "ne"} and left_type != right_type and not (left_type in _NUMERIC and right_type in _NUMERIC):
        return set(), {}, f"{op} compares incompatible theories {left_type!r} and {right_type!r}"
    if op in {"eq", "ne", "lt", "le", "gt", "ge"}:
        numeric_side = None
        if isinstance(left, Mapping) and set(left) == {"symbol"} and symbols[str(left["symbol"])].get("theory") in _NUMERIC:
            numeric_side = (str(left["symbol"]), right)
        elif isinstance(right, Mapping) and set(right) == {"symbol"} and symbols[str(right["symbol"])].get("theory") in _NUMERIC:
            numeric_side = (str(right["symbol"]), left)
        if numeric_side:
            value = _numeric_literal(numeric_side[1])
            if value is None:
                return set(), {}, "numeric predicates require a numeric literal threshold"
            return names, {numeric_side[0]: {value}}, None
    return names, {}, None


def _merge_thresholds(formulas: Sequence[Any], symbols: Mapping[str, Mapping[str, Any]]) -> tuple[set[str], dict[str, set[float | int]], str | None]:
    names: set[str] = set()
    thresholds: dict[str, set[float | int]] = {}
    for formula in formulas:
        formula_names, formula_thresholds, error = _formula_info(formula, symbols)
        if error:
            return set(), {}, error
        names.update(formula_names)
        for name, values in formula_thresholds.items():
            thresholds.setdefault(name, set()).update(values)
    return names, thresholds, None


def _selected_rule_parts(table: Mapping[str, Any], rules: Mapping[Any, Mapping[str, Any]]) -> tuple[list[Any], set[str]]:
    """Collect every executable predicate and symbol-valued effect."""

    formulas: list[Any] = []
    effect_symbols: set[str] = set()
    for rule_id in table.get("rule_ids", []):
        rule = rules.get(rule_id, {})
        formulas.append(rule.get("condition"))
        scope = rule.get("scope", {}) if isinstance(rule, Mapping) else {}
        if isinstance(scope, Mapping) and scope.get("predicate") is not None:
            formulas.append(scope.get("predicate"))
        for exception in rule.get("exceptions", []) if isinstance(rule, Mapping) else []:
            if isinstance(exception, Mapping):
                formulas.append(exception.get("condition"))
        for effect in rule.get("effects", []) if isinstance(rule, Mapping) else []:
            value = effect.get("value") if isinstance(effect, Mapping) else None
            if isinstance(value, Mapping) and set(value) == {"symbol"}:
                effect_symbols.add(str(value.get("symbol")))
    return formulas, effect_symbols


def _within_domain(value: float | int, symbol: Mapping[str, Any]) -> bool:
    domain = symbol.get("domain", {})
    minimum, maximum = domain.get("minimum"), domain.get("maximum")
    if minimum is not None and (value < minimum or value == minimum and not domain.get("minimum_inclusive", True)):
        return False
    if maximum is not None and (value > maximum or value == maximum and not domain.get("maximum_inclusive", True)):
        return False
    return True


def _numeric_samples(symbol: Mapping[str, Any], thresholds: Sequence[float | int]) -> list[Any]:
    theory = symbol.get("theory")
    domain = symbol.get("domain", {})
    values: set[Any] = {None}
    minimum, maximum = domain.get("minimum"), domain.get("maximum")
    if theory == "int":
        boundaries = sorted({int(value) for value in (*thresholds, minimum, maximum) if isinstance(value, int) and not isinstance(value, bool)})
        for boundary in boundaries:
            for candidate in (boundary - 1, boundary, boundary + 1):
                if _within_domain(candidate, symbol):
                    values.add(candidate)
        for left, right in zip(boundaries, boundaries[1:]):
            candidate = (left + right) // 2
            if left < candidate < right and _within_domain(candidate, symbol):
                values.add(candidate)
        if not boundaries:
            values.update((-1, 0, 1))
        elif minimum is None:
            values.add(boundaries[0] - 1)
        elif maximum is None:
            values.add(boundaries[-1] + 1)
    else:
        finite_thresholds = sorted({float(value) for value in thresholds if _finite_number(value)})
        boundaries = sorted({value for value in (*finite_thresholds, minimum, maximum) if _finite_number(value)})
        for boundary in boundaries:
            if _within_domain(boundary, symbol):
                values.add(boundary)
            for direction in (-math.inf, math.inf):
                candidate = math.nextafter(float(boundary), direction)
                if _within_domain(candidate, symbol):
                    values.add(candidate)
        for left, right in zip(boundaries, boundaries[1:]):
            candidate = (left + right) / 2.0
            if left < candidate < right and _within_domain(candidate, symbol):
                values.add(candidate)
        if not boundaries:
            values.update((-1.0, 0.0, 1.0))
        else:
            if minimum is None:
                values.add(math.nextafter(boundaries[0], -math.inf))
            if maximum is None:
                values.add(math.nextafter(boundaries[-1], math.inf))
    return sorted(values, key=lambda value: (value is not None, value is not None and value))


def _domain_samples(symbol: Mapping[str, Any], thresholds: Sequence[float | int]) -> list[Any]:
    theory = symbol.get("theory")
    if theory in _NUMERIC:
        return _numeric_samples(symbol, thresholds)
    if theory == "bool":
        return [None, False, True]
    if theory == "enum":
        return [None, *dict.fromkeys(symbol.get("domain", {}).get("values", []))]
    return [None]


def _signature(result: Mapping[str, Any]) -> dict[str, Any]:
    return {"status": result.get("status"), "outputs": result.get("outputs", {})}


def _preflight(ir: Mapping[str, Any], table_id: str | None) -> tuple[Mapping[str, Any] | None, dict[str, Mapping[str, Any]], str | None]:
    if not isinstance(ir, Mapping):
        return None, {}, "IR must be an object"
    errors = validate_ir(ir)
    if errors:
        return None, {}, f"invalid IR: {errors[0]}"
    table = _table(ir, table_id)
    if table is None:
        return None, {}, "exactly one table must be selected"
    if table.get("hit_policy") not in {"UNIQUE", "ANY"}:
        return None, {}, f"hit policy {table.get('hit_policy')!r} is outside the comparator subset"
    if (table.get("policy_proof") or {}).get("status") != "proved":
        return None, {}, "table policy proof must be proved before comparison"
    rules = {rule.get("id"): rule for rule in ir.get("rules", []) if isinstance(rule, Mapping)}
    for rule_id in table.get("rule_ids", []):
        rule = rules.get(rule_id)
        scope = rule.get("scope", {}) if isinstance(rule, Mapping) else {}
        metadata = scope.get("metadata", {}) if isinstance(scope, Mapping) else {}
        if isinstance(metadata, Mapping) and any(value not in (None, [], "") for value in metadata.values()):
            return None, {}, "contextual scope metadata is outside the comparator subset"
    return table, _symbol_map(ir), None


def compare_ir_tables(
    left_ir: Mapping[str, Any],
    right_ir: Mapping[str, Any],
    *,
    thresholds: Mapping[str, Sequence[float | int]],
    left_table_id: str | None = None,
    right_table_id: str | None = None,
    max_cases: int = 10_000,
) -> dict[str, Any]:
    """Compare two known IR tables on P3-prime representative cells.

    ``thresholds`` is a caller-supplied finite set known to contain every
    numeric threshold in both tables.  The result is ``equivalent`` only for
    the generated representative assignments; it is not an unknown-reference
    certificate and is not exhaustive instrument validation.
    """

    if isinstance(max_cases, bool) or not isinstance(max_cases, int) or max_cases < 1:
        return {"status": "refused", "method": "p3-prime-representative-cells-v1", "reason": "max_cases must be a positive integer", "differences": []}
    left_table, left_symbols, error = _preflight(left_ir, left_table_id)
    if error:
        return {"status": "refused", "method": "p3-prime-representative-cells-v1", "reason": f"left table: {error}", "differences": []}
    right_table, right_symbols, error = _preflight(right_ir, right_table_id)
    if error:
        return {"status": "refused", "method": "p3-prime-representative-cells-v1", "reason": f"right table: {error}", "differences": []}
    if not isinstance(thresholds, Mapping):
        return {"status": "refused", "method": "p3-prime-representative-cells-v1", "reason": "thresholds must be a mapping", "differences": []}

    combined_symbols: dict[str, Mapping[str, Any]] = {}
    for name in sorted(set(left_symbols) | set(right_symbols)):
        left_symbol, right_symbol = left_symbols.get(name), right_symbols.get(name)
        if left_symbol is None or right_symbol is None:
            return {"status": "refused", "method": "p3-prime-representative-cells-v1", "reason": f"symbol {name!r} is not declared by both tables", "differences": []}
        if {key: left_symbol.get(key) for key in ("theory", "role", "domain")} != {key: right_symbol.get(key) for key in ("theory", "role", "domain")}:
            return {"status": "refused", "method": "p3-prime-representative-cells-v1", "reason": f"symbol {name!r} declarations differ", "differences": []}
        combined_symbols[name] = left_symbol

    left_rules = {rule.get("id"): rule for rule in left_ir.get("rules", [])}
    right_rules = {rule.get("id"): rule for rule in right_ir.get("rules", [])}
    left_formulas, left_effect_symbols = _selected_rule_parts(left_table, left_rules)
    right_formulas, right_effect_symbols = _selected_rule_parts(right_table, right_rules)
    referenced, used_thresholds, error = _merge_thresholds(left_formulas + right_formulas, combined_symbols)
    if error:
        return {"status": "refused", "method": "p3-prime-representative-cells-v1", "reason": error, "differences": []}
    referenced.update(left_effect_symbols | right_effect_symbols)
    for name in sorted(referenced):
        if name not in combined_symbols:
            return {"status": "refused", "method": "p3-prime-representative-cells-v1", "reason": f"unknown symbol {name!r}", "differences": []}
        if combined_symbols[name].get("theory") == "string":
            return {"status": "refused", "method": "p3-prime-representative-cells-v1", "reason": "string symbols are outside the interval comparison class", "differences": []}
    for name in referenced:
        declared = thresholds[name] if name in thresholds else []
        if not isinstance(declared, Sequence) or isinstance(declared, (str, bytes)):
            return {"status": "refused", "method": "p3-prime-representative-cells-v1", "reason": f"thresholds[{name!r}] must be a finite sequence", "differences": []}
        if any(not _finite_number(value) for value in declared):
            return {"status": "refused", "method": "p3-prime-representative-cells-v1", "reason": f"thresholds[{name!r}] contains a non-finite/non-numeric value", "differences": []}
        if combined_symbols[name].get("theory") == "int" and any(not isinstance(value, int) or isinstance(value, bool) for value in declared):
            return {"status": "refused", "method": "p3-prime-representative-cells-v1", "reason": f"thresholds[{name!r}] must be integral for an int symbol", "differences": []}
        if not used_thresholds.get(name, set()).issubset(set(declared)):
            missing = sorted(used_thresholds.get(name, set()) - set(declared))
            return {"status": "refused", "method": "p3-prime-representative-cells-v1", "reason": f"threshold set for {name!r} does not cover {missing}", "differences": []}

    dimensions = sorted(referenced)
    choices = [_domain_samples(combined_symbols[name], thresholds.get(name, [])) for name in dimensions]
    case_count = math.prod(len(values) for values in choices) if choices else 1
    if case_count > max_cases:
        return {"status": "timeout", "method": "p3-prime-representative-cells-v1", "case_count": case_count, "checked_cases": 0, "reason": f"representative case count {case_count} exceeds max_cases={max_cases}", "differences": []}

    left_eval = deepcopy(dict(left_ir))
    right_eval = deepcopy(dict(right_ir))
    differences: list[dict[str, Any]] = []
    checked = 0
    for values in itertools.product(*choices) if choices else [()]:
        assignment = dict(zip(dimensions, values))
        left_result = evaluate_ir(left_eval, assignment, table_id=left_table.get("id"))
        right_result = evaluate_ir(right_eval, assignment, table_id=right_table.get("id"))
        checked += 1
        left_signature, right_signature = _signature(left_result), _signature(right_result)
        if left_signature != right_signature:
            differences.append({"inputs": assignment, "left": left_signature, "right": right_signature})

    return {
        "status": "different" if differences else "equivalent",
        "method": "p3-prime-representative-cells-v1",
        "thresholds": {name: list(thresholds.get(name, [])) for name in dimensions},
        "case_count": case_count,
        "checked_cases": checked,
        "differences": differences,
    }


__all__ = ["compare_ir_tables"]
