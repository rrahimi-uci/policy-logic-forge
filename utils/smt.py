"""Bounded, dependency-free proof core for LExec IR v1 tables.

This module deliberately does *not* pretend to be a complete SMT solver.  It
enumerates complete finite domains (booleans, enums, and small closed integer
intervals) under the IR's Kleene three-valued semantics.  Unbounded reals,
open intervals, and strings are reported as ``unknown`` unless a satisfying
candidate is found.  A policy is never marked proved from an incomplete
search.  The interface is shaped so a real SMT backend can replace this core
without changing proof-record consumers.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


UNKNOWN = None
MAX_ASSIGNMENTS = 10_000
_RANGE = re.compile(r"^([\[\(])\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*,\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*([\]\)])$")


@dataclass(frozen=True)
class SolveResult:
    """A bounded satisfiability result with explicit incompleteness."""

    status: str  # sat, unsat, unknown, timeout
    witness: dict[str, Any] | None
    explored: int
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "witness": self.witness,
            "explored": self.explored,
            "reason": self.reason,
        }


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _symbols_by_id(symbols: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    if isinstance(symbols, Mapping):
        return {str(key): value for key, value in symbols.items() if isinstance(value, Mapping)}
    return {str(item.get("id")): item for item in symbols if isinstance(item, Mapping) and item.get("id")}


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


def _formula_literals(formula: Any) -> list[Any]:
    if not isinstance(formula, Mapping):
        return []
    values: list[Any] = []
    for key in ("left", "right", "arg"):
        operand = formula.get(key)
        if isinstance(operand, Mapping) and set(operand) == {"literal", "type"}:
            values.append(operand.get("literal"))
        elif isinstance(operand, Mapping) and "op" in operand:
            values.extend(_formula_literals(operand))
    for child in formula.get("args", []) if isinstance(formula.get("args"), list) else []:
        values.extend(_formula_literals(child))
    return values


def _formula_error(formula: Any) -> str | None:
    """Return a deterministic shape error before bounded evaluation."""

    if not isinstance(formula, Mapping):
        return "formula must be an object"
    op = formula.get("op")
    if not isinstance(op, str):
        return f"unsupported formula operator {op!r}"
    if op in {"and", "or"}:
        args = formula.get("args")
        if not isinstance(args, list) or not args:
            return f"{op} requires non-empty args"
        for child in args:
            error = _formula_error(child)
            if error:
                return error
        return None
    if op == "not":
        return _formula_error(formula.get("arg"))
    if op == "is_null":
        operand = formula.get("arg")
        if isinstance(operand, Mapping) and (set(operand) == {"symbol"} or set(operand) == {"literal", "type"}):
            return None
        return "is_null requires an operand"
    if op in {"eq", "ne", "lt", "le", "gt", "ge", "contains", "in_binned_range"}:
        for key in ("left", "right"):
            operand = formula.get(key)
            if not isinstance(operand, Mapping) or set(operand) not in ({"symbol"}, {"literal", "type"}):
                return f"{op} requires valid {key} operand"
        return None
    return f"unsupported formula operator {op!r}"


def _candidate_values(symbol: Mapping[str, Any], literals: Sequence[Any]) -> tuple[list[Any], bool, str | None]:
    theory = symbol.get("theory")
    domain = symbol.get("domain") if isinstance(symbol.get("domain"), Mapping) else {}
    kind = domain.get("kind")
    if theory == "bool" or kind == "boolean":
        return [None, False, True], True, None
    if theory == "enum" or kind == "enum":
        values = domain.get("values")
        if not isinstance(values, list) or not values:
            return [], False, "enum domain has no values"
        return [None, *dict.fromkeys(values)], True, None
    if theory in {"int", "real"} or kind == "interval":
        minimum, maximum = domain.get("minimum"), domain.get("maximum")
        if isinstance(minimum, int) and isinstance(maximum, int) and not isinstance(minimum, bool) and not isinstance(maximum, bool) and 0 <= maximum - minimum <= 16:
            return [None, *range(minimum, maximum + 1)], True, None
        return [], False, "numeric interval is not a small closed integer interval"
    if theory == "string" or kind == "string":
        strings = [value for value in literals if isinstance(value, str)]
        # The domain is infinite; these candidates are useful for finding a
        # witness but cannot establish unsatisfiability.
        return [None, "", "x", *dict.fromkeys(strings)], False, "string domain is open-ended"
    return [], False, f"unsupported theory {theory!r}"


def _kleene_not(value: bool | None) -> bool | None:
    return UNKNOWN if value is UNKNOWN else not value


def _kleene_and(values: Sequence[bool | None]) -> bool | None:
    if any(value is False for value in values):
        return False
    return True if values and all(value is True for value in values) else UNKNOWN


def _kleene_or(values: Sequence[bool | None]) -> bool | None:
    if any(value is True for value in values):
        return True
    return False if values and all(value is False for value in values) else UNKNOWN


def _operand(value: Any, assignment: Mapping[str, Any]) -> Any:
    if isinstance(value, Mapping) and set(value) == {"symbol"}:
        return assignment.get(value.get("symbol"), UNKNOWN)
    if isinstance(value, Mapping) and set(value) == {"literal", "type"}:
        return value.get("literal")
    return UNKNOWN


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


def _range_membership(value: Any, range_text: Any) -> bool | None:
    if value is UNKNOWN or range_text is UNKNOWN or value is None or range_text is None:
        return UNKNOWN
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not isinstance(range_text, str):
        return UNKNOWN
    match = _RANGE.fullmatch(range_text)
    if not match:
        return UNKNOWN
    lower, upper = float(match.group(2)), float(match.group(3))
    if not math.isfinite(lower) or not math.isfinite(upper):
        return UNKNOWN
    lower_ok = value >= lower if match.group(1) == "[" else value > lower
    upper_ok = value <= upper if match.group(4) == "]" else value < upper
    return lower_ok and upper_ok


def evaluate_formula(formula: Mapping[str, Any], assignment: Mapping[str, Any]) -> bool | None:
    """Evaluate an IR formula with Kleene true/false/unknown semantics."""

    if not isinstance(formula, Mapping):
        return UNKNOWN
    op = formula.get("op")
    if op in {"and", "or"}:
        values = [evaluate_formula(child, assignment) for child in formula.get("args", [])]
        return _kleene_and(values) if op == "and" else _kleene_or(values)
    if op == "not":
        return _kleene_not(evaluate_formula(formula.get("arg"), assignment))
    if op == "is_null":
        value = _operand(formula.get("arg"), assignment)
        return value is None or value is UNKNOWN
    if op == "in_binned_range":
        return _range_membership(_operand(formula.get("left"), assignment), _operand(formula.get("right"), assignment))
    if op in {"eq", "ne", "lt", "le", "gt", "ge", "contains"}:
        return _compare(op, _operand(formula.get("left"), assignment), _operand(formula.get("right"), assignment))
    return UNKNOWN


def solve_formula(
    formula: Mapping[str, Any],
    symbols: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    max_assignments: int = MAX_ASSIGNMENTS,
) -> SolveResult:
    """Find a satisfying assignment, or conservatively report unknown."""

    formula_error = _formula_error(formula)
    if formula_error:
        return SolveResult("unknown", None, 0, formula_error)
    symbol_map = _symbols_by_id(symbols)
    referenced = sorted(_formula_symbols(formula))
    missing = [name for name in referenced if name not in symbol_map]
    if missing:
        return SolveResult("unknown", None, 0, f"unknown symbols: {missing}")
    literals = _formula_literals(formula)
    choices: list[list[Any]] = []
    complete = True
    incomplete_reasons: list[str] = []
    for name in referenced:
        values, is_complete, reason = _candidate_values(symbol_map[name], literals)
        if not values:
            return SolveResult("unknown", None, 0, reason)
        choices.append(values)
        complete = complete and is_complete
        if reason:
            incomplete_reasons.append(f"{name}: {reason}")
    total = 1
    for values in choices:
        total *= len(values)
    if total > max_assignments:
        return SolveResult("timeout", None, 0, f"candidate space {total} exceeds max_assignments={max_assignments}")
    explored = 0
    for values in itertools.product(*choices):
        assignment = dict(zip(referenced, values))
        explored += 1
        if evaluate_formula(formula, assignment) is True:
            return SolveResult("sat", assignment, explored)
    if complete:
        return SolveResult("unsat", None, explored)
    return SolveResult("unknown", None, explored, "; ".join(incomplete_reasons))


def _query_record(query_type: str, query: Mapping[str, Any], result: SolveResult) -> dict[str, Any]:
    """Attach stable query metadata to a bounded solver result."""

    record = {
        "query_type": query_type,
        **result.as_dict(),
        "query_sha256": _sha256({"query_type": query_type, "query": query}),
    }
    return record


def query_satisfiable(
    formula: Mapping[str, Any],
    symbols: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    max_assignments: int = MAX_ASSIGNMENTS,
) -> dict[str, Any]:
    """Run the bounded satisfiability query and retain its witness contract."""

    query = {"formula": formula, "symbols": symbols}
    return _query_record("satisfiable", query, solve_formula(formula, symbols, max_assignments=max_assignments))


def query_overlap(
    left_rule: Mapping[str, Any],
    right_rule: Mapping[str, Any],
    symbols: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    max_assignments: int = MAX_ASSIGNMENTS,
) -> dict[str, Any]:
    """Ask whether two rule conditions can be true at the same assignment."""

    left_condition = left_rule.get("condition") if isinstance(left_rule, Mapping) else None
    right_condition = right_rule.get("condition") if isinstance(right_rule, Mapping) else None
    left_id = left_rule.get("id") if isinstance(left_rule, Mapping) else None
    right_id = right_rule.get("id") if isinstance(right_rule, Mapping) else None
    formula = {"op": "and", "args": [left_condition, right_condition]}
    query = {
        "left_rule": {"id": left_id, "condition": left_condition},
        "right_rule": {"id": right_id, "condition": right_condition},
        "symbols": symbols,
    }
    result = solve_formula(formula, symbols, max_assignments=max_assignments)
    record = _query_record("overlap", query, result)
    record.update({
        "rule_ids": [left_id, right_id],
        "overlap": True if result.status == "sat" else False if result.status == "unsat" else None,
    })
    return record


def query_counterexample(
    formula: Mapping[str, Any],
    symbols: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    max_assignments: int = MAX_ASSIGNMENTS,
) -> dict[str, Any]:
    """Search for a satisfying assignment to a violation formula.

    ``status == "sat"`` means that a counterexample was found.  The original
    solver status is intentionally preserved so unknown and timeout can never
    be mistaken for a negative result.
    """

    record = _query_record(
        "counterexample",
        {"formula": formula, "symbols": symbols},
        solve_formula(formula, symbols, max_assignments=max_assignments),
    )
    record["found"] = record["status"] == "sat"
    return record


def query_witness(
    formula: Mapping[str, Any],
    symbols: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    max_assignments: int = MAX_ASSIGNMENTS,
) -> dict[str, Any]:
    """Return a satisfying witness while preserving incomplete outcomes."""

    record = _query_record(
        "witness",
        {"formula": formula, "symbols": symbols},
        solve_formula(formula, symbols, max_assignments=max_assignments),
    )
    record["found"] = record["status"] == "sat"
    return record


def query_coverage(
    rules: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    symbols: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    max_assignments: int = MAX_ASSIGNMENTS,
) -> dict[str, Any]:
    """Check that every bounded assignment satisfies at least one rule.

    This query is deliberately stricter than satisfiability: an assignment
    whose disjunction evaluates to ``unknown`` prevents a proof.  A concrete
    false assignment is a valid coverage-gap counterexample, even when the
    domain is otherwise open-ended.
    """

    rule_list = list(_rule_map(rules).values())
    rule_ids = [str(rule.get("id")) for rule in rule_list]
    conditions = [rule.get("condition") for rule in rule_list if isinstance(rule.get("condition"), Mapping)]
    query = {
        "rules": [{"id": rule.get("id"), "condition": rule.get("condition")} for rule in rule_list],
        "symbols": symbols,
    }
    if rule_list and (len(conditions) != len(rule_list) or any(not isinstance(rule, Mapping) for rule in rule_list)):
        return {
            "query_type": "coverage",
            "status": "unknown",
            "witness": None,
            "explored": 0,
            "reason": "one or more rules has no executable condition",
            "query_sha256": _sha256({"query_type": "coverage", "query": query}),
            "rule_ids": rule_ids,
            "covered": None,
        }
    if not conditions:
        return {
            "query_type": "coverage",
            "status": "counterexample",
            "witness": {},
            "explored": 0,
            "reason": "no executable rule conditions",
            "query_sha256": _sha256({"query_type": "coverage", "query": query}),
            "rule_ids": rule_ids,
            "covered": False,
        }

    formula = {"op": "or", "args": conditions}
    symbol_map = _symbols_by_id(symbols)
    referenced = sorted(_formula_symbols(formula))
    missing = [name for name in referenced if name not in symbol_map]
    if missing:
        result = {
            "query_type": "coverage",
            "status": "unknown",
            "witness": None,
            "explored": 0,
            "reason": f"unknown symbols: {missing}",
            "query_sha256": _sha256({"query_type": "coverage", "query": query}),
            "rule_ids": rule_ids,
            "covered": None,
        }
        return result

    literals = _formula_literals(formula)
    choices: list[list[Any]] = []
    complete = True
    incomplete_reasons: list[str] = []
    for name in referenced:
        values, is_complete, reason = _candidate_values(symbol_map[name], literals)
        if not values:
            return {
                "query_type": "coverage",
                "status": "unknown",
                "witness": None,
                "explored": 0,
                "reason": reason,
                "query_sha256": _sha256({"query_type": "coverage", "query": query}),
                "rule_ids": rule_ids,
                "covered": None,
            }
        choices.append(values)
        complete = complete and is_complete
        if reason:
            incomplete_reasons.append(f"{name}: {reason}")

    total = math.prod(len(values) for values in choices) if choices else 1
    if total > max_assignments:
        return {
            "query_type": "coverage",
            "status": "timeout",
            "witness": None,
            "explored": 0,
            "reason": f"candidate space {total} exceeds max_assignments={max_assignments}",
            "query_sha256": _sha256({"query_type": "coverage", "query": query}),
            "rule_ids": rule_ids,
            "covered": None,
        }

    explored = 0
    unknown_assignment: dict[str, Any] | None = None
    for values in itertools.product(*choices):
        assignment = dict(zip(referenced, values))
        explored += 1
        outcome = evaluate_formula(formula, assignment)
        if outcome is False:
            return {
                "query_type": "coverage",
                "status": "counterexample",
                "witness": assignment,
                "explored": explored,
                "reason": "no rule condition is true for this assignment",
                "query_sha256": _sha256({"query_type": "coverage", "query": query}),
                "rule_ids": rule_ids,
                "covered": False,
            }
        if outcome is UNKNOWN and unknown_assignment is None:
            unknown_assignment = assignment

    if unknown_assignment is not None:
        reason = "; ".join(incomplete_reasons) or "a rule disjunction evaluates to unknown"
        status = "unknown"
        covered = None
        witness = None
    elif complete:
        reason = None
        status = "proved"
        covered = True
        witness = None
    else:
        reason = "; ".join(incomplete_reasons) or "domain is incomplete"
        status = "unknown"
        covered = None
        witness = None
    return {
        "query_type": "coverage",
        "status": status,
        "witness": witness,
        "explored": explored,
        "reason": reason,
        "query_sha256": _sha256({"query_type": "coverage", "query": query}),
        "rule_ids": rule_ids,
        "covered": covered,
    }


def query_conflicts(
    rules: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    symbols: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    max_assignments: int = MAX_ASSIGNMENTS,
) -> dict[str, Any]:
    """Find overlapping rules with different executable outputs."""

    rule_list = list(_rule_map(rules).values())
    rule_ids = [str(rule.get("id")) for rule in rule_list]
    query = {
        "rules": [
            {"id": rule.get("id"), "condition": rule.get("condition"), "effects": rule.get("effects")}
            for rule in rule_list
        ],
        "symbols": symbols,
    }
    if any(
        not isinstance(rule, Mapping)
        or not isinstance(rule.get("condition"), Mapping)
        or not isinstance(rule.get("effects"), list)
        for rule in rule_list
    ):
        return {
            "query_type": "conflicts",
            "status": "unknown",
            "witness": None,
            "explored": 0,
            "reason": "one or more rules is malformed for conflict analysis",
            "query_sha256": _sha256({"query_type": "conflicts", "query": query}),
            "rule_ids": rule_ids,
            "conflict_count": 0,
            "witnesses": [],
        }
    witnesses: list[dict[str, Any]] = []
    unknown_reason: str | None = None
    timeout_reason: str | None = None
    explored = 0
    for left, right in itertools.combinations(rule_list, 2):
        overlap = query_overlap(left, right, symbols, max_assignments=max_assignments)
        explored += int(overlap["explored"])
        if overlap["status"] == "sat":
            assignment = overlap["witness"] or {}
            left_output = _effect_values(left, assignment)
            right_output = _effect_values(right, assignment)
            if left_output is None or right_output is None:
                unknown_reason = "overlap witness has unknown output value"
                continue
            if left_output != right_output:
                witnesses.append({
                    "rule_ids": [left.get("id"), right.get("id")],
                    "assignment": assignment,
                    "left_output": left_output,
                    "right_output": right_output,
                })
                return {
                    "query_type": "conflicts",
                    "status": "conflict",
                    "witness": assignment,
                    "explored": explored,
                    "reason": "overlapping rules produce different outputs",
                    "query_sha256": _sha256({"query_type": "conflicts", "query": query}),
                    "rule_ids": rule_ids,
                    "conflict_count": len(witnesses),
                    "witnesses": witnesses,
                }
        elif overlap["status"] == "timeout":
            timeout_reason = overlap.get("reason") or "overlap query timed out"
        elif overlap["status"] == "unknown":
            unknown_reason = overlap.get("reason") or "overlap query is unknown"

    if timeout_reason:
        status, reason = "timeout", timeout_reason
    elif unknown_reason:
        status, reason = "unknown", unknown_reason
    else:
        status, reason = "proved", None
    return {
        "query_type": "conflicts",
        "status": status,
        "witness": None,
        "explored": explored,
        "reason": reason,
        "query_sha256": _sha256({"query_type": "conflicts", "query": query}),
        "rule_ids": rule_ids,
        "conflict_count": len(witnesses),
        "witnesses": witnesses,
    }


def _rule_map(rules: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    if isinstance(rules, Mapping):
        return {str(key): value for key, value in rules.items() if isinstance(value, Mapping)}
    return {str(rule.get("id")): rule for rule in rules if isinstance(rule, Mapping) and rule.get("id")}


def _effect_values(rule: Mapping[str, Any], assignment: Mapping[str, Any]) -> dict[str, Any] | None:
    result: dict[str, Any] = {}
    for effect in rule.get("effects", []):
        if not isinstance(effect, Mapping) or effect.get("target") is None:
            return None
        value = _operand(effect.get("value"), assignment)
        if value is UNKNOWN:
            return None
        result[str(effect["target"])] = value
    return result


def _proof_base(table: Mapping[str, Any], method: str, query: Any) -> dict[str, Any]:
    return {
        "status": "unknown",
        "method": method,
        "solver": "bounded-enumeration-v1",
        "query_sha256": _sha256(query),
        "witnesses": [],
    }


def prove_table(
    table: Mapping[str, Any],
    rules: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    symbols: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    max_assignments: int = MAX_ASSIGNMENTS,
) -> dict[str, Any]:
    """Produce a conservative proof record for one IR decision table."""

    rule_map = _rule_map(rules)
    rule_ids = [str(rule_id) for rule_id in table.get("rule_ids", [])]
    selected = [rule_map.get(rule_id) for rule_id in rule_ids]
    query = {
        "table_id": table.get("id"),
        "rule_ids": rule_ids,
        "hit_policy": table.get("hit_policy"),
        "rules": [
            {
                "id": rule.get("id"),
                "condition": rule.get("condition"),
                "effects": rule.get("effects"),
            }
            for rule in selected
            if isinstance(rule, Mapping)
        ],
    }
    policy = table.get("hit_policy")
    method = "pairwise_disjointness" if policy == "UNIQUE" else "equal_outputs_on_overlap"
    if policy == "PRIORITY":
        proof = _proof_base(table, "source_precedence", query)
        proof.update({"status": "refused", "witnesses": [{"reason": "priority order is not represented in LExec IR v1"}]})
        return proof
    if policy not in {"UNIQUE", "ANY", "COLLECT"}:
        proof = _proof_base(table, "unproved", query)
        proof.update({"status": "refused", "witnesses": [{"reason": f"unsupported hit policy {policy!r}"}]})
        return proof
    if any(rule is None or not isinstance(rule.get("condition"), Mapping) for rule in selected):
        proof = _proof_base(table, method, query)
        proof.update({"status": "unknown", "witnesses": [{"reason": "table references a missing or malformed rule"}]})
        return proof
    proof = _proof_base(table, method, query)
    unknown_reason: str | None = None
    for left_index, right_index in itertools.combinations(range(len(selected)), 2):
        left, right = selected[left_index], selected[right_index]
        overlap = {"op": "and", "args": [left["condition"], right["condition"]]}
        result = solve_formula(overlap, symbols, max_assignments=max_assignments)
        if result.status == "sat":
            witness = {
                "rule_ids": [rule_ids[left_index], rule_ids[right_index]],
                "assignment": result.witness,
            }
            if policy == "UNIQUE":
                proof.update({"status": "refused", "witnesses": [witness]})
                return proof
            if policy == "ANY":
                left_values = _effect_values(left, result.witness or {})
                right_values = _effect_values(right, result.witness or {})
                if left_values is None or right_values is None:
                    unknown_reason = "overlap witness has unknown output value"
                elif left_values != right_values:
                    proof.update({"status": "refused", "witnesses": [{**witness, "left_output": left_values, "right_output": right_values}]})
                    return proof
            # COLLECT permits overlap by definition; no conflict is claimed.
        elif result.status in {"unknown", "timeout"}:
            unknown_reason = result.reason or result.status
    if policy == "COLLECT":
        proof.update({"status": "unknown", "witnesses": [{"reason": "COLLECT overlap semantics are permitted but not solver-proved in v1"}]})
    elif unknown_reason:
        proof.update({"status": "unknown", "witnesses": [{"reason": unknown_reason}]})
    else:
        proof["status"] = "proved"
    return proof


def annotate_policy_proofs(
    ir: Mapping[str, Any],
    *,
    max_assignments: int = MAX_ASSIGNMENTS,
) -> dict[str, Any]:
    """Return a copy of IR with conservative table proof records attached."""

    result = deepcopy(dict(ir))
    rules = result.get("rules", [])
    symbols = result.get("symbols", [])
    for table in result.get("tables", []):
        table["policy_proof"] = prove_table(table, rules, symbols, max_assignments=max_assignments)
    return result


def prove_tables(ir: Mapping[str, Any], *, max_assignments: int = MAX_ASSIGNMENTS) -> dict[str, Any]:
    """Alias used by callers that treat table proofs as a batch operation."""

    return annotate_policy_proofs(ir, max_assignments=max_assignments)
