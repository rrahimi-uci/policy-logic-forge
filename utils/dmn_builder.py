"""Build a conservative DMN 1.3 decision-table projection from LExec IR."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Mapping, Sequence

from utils.lexec_ir import validate_ir


DMN_NS = "https://www.omg.org/spec/DMN/20191111/MODEL/"
DMN_PREFIX = "https://github.com/rrahimi-uci/compliance-to-code/dmn/"
SUPPORTED_HIT_POLICIES = {"UNIQUE", "ANY", "PRIORITY", "COLLECT"}
SAFE_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


class DmnBuildError(ValueError):
    """A semantic or structural construct is outside the DMN emitter subset."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _tag(name: str) -> str:
    return f"{{{DMN_NS}}}{name}"


def _safe_id(value: Any, fallback: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("_")
    if not candidate or not (candidate[0].isalpha() or candidate[0] == "_"):
        candidate = f"{fallback}_{candidate}" if candidate else fallback
    return candidate


def _type_ref(symbol: Mapping[str, Any]) -> str:
    theory = symbol.get("theory")
    if theory == "bool":
        return "boolean"
    if theory in {"int", "real"}:
        return "number"
    if theory in {"enum", "string"}:
        return "string"
    raise DmnBuildError("UNSUPPORTED_THEORY", f"DMN type mapping is unavailable for {theory!r}.")


def _feel_literal(value: Any, value_type: str | None = None) -> str:
    if value is None or value_type == "null":
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise DmnBuildError("UNSUPPORTED_LITERAL", f"FEEL literal {value!r} is not supported.")


def _operand_symbol(value: Any) -> str | None:
    return str(value["symbol"]) if isinstance(value, Mapping) and set(value) == {"symbol"} else None


def _formula_symbols(formula: Any) -> set[str]:
    if not isinstance(formula, Mapping):
        return set()
    found: set[str] = set()
    for key in ("left", "right", "arg"):
        value = formula.get(key)
        symbol = _operand_symbol(value)
        if symbol:
            found.add(symbol)
        elif isinstance(value, Mapping) and "op" in value:
            found.update(_formula_symbols(value))
    for child in formula.get("args", []) if isinstance(formula.get("args"), list) else []:
        found.update(_formula_symbols(child))
    return found


def _feel_operand(value: Any) -> str:
    symbol = _operand_symbol(value)
    if symbol:
        return symbol
    if isinstance(value, Mapping) and set(value) == {"literal", "type"}:
        return _feel_literal(value.get("literal"), str(value.get("type")))
    raise DmnBuildError("INVALID_OPERAND", "Formula operand is not a symbol or typed literal.")


def formula_to_feel(formula: Mapping[str, Any]) -> str:
    """Render the supported IR formula subset as deterministic FEEL text."""

    op = formula.get("op")
    if op in {"and", "or"}:
        args = formula.get("args")
        if not isinstance(args, list) or not args:
            raise DmnBuildError("INVALID_FORMULA", f"{op} requires non-empty args.")
        joiner = f" {op} "
        return "(" + joiner.join(f"({formula_to_feel(arg)})" for arg in args) + ")"
    if op == "not":
        return f"not({formula_to_feel(formula.get('arg'))})"
    if op == "is_null":
        return f"{_feel_operand(formula.get('arg'))} = null"
    if op == "in_binned_range":
        left = _feel_operand(formula.get("left"))
        right = _feel_operand(formula.get("right"))
        if right.startswith('"') and right.endswith('"'):
            right = right[1:-1]
        return f"{left} in {right}"
    if op in {"eq", "ne", "lt", "le", "gt", "ge"}:
        symbols = _formula_symbols(formula)
        if len(symbols) != 1:
            raise DmnBuildError("UNSUPPORTED_FORMULA", "Comparison must reference exactly one symbol.")
        operator = {"eq": "=", "ne": "!=", "lt": "<", "le": "<=", "gt": ">", "ge": ">="}[op]
        return f"{_feel_operand(formula.get('left'))} {operator} {_feel_operand(formula.get('right'))}"
    if op == "contains":
        return f"contains({_feel_operand(formula.get('left'))}, {_feel_operand(formula.get('right'))})"
    raise DmnBuildError("UNSUPPORTED_FORMULA", f"Formula operator {op!r} is outside the DMN emitter subset.")


def _conjuncts(formula: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if formula.get("op") == "and":
        result: list[Mapping[str, Any]] = []
        for child in formula.get("args", []):
            if not isinstance(child, Mapping):
                raise DmnBuildError("INVALID_FORMULA", "Conjunction child is not an object.")
            result.extend(_conjuncts(child))
        return result
    if formula.get("op") in {"eq", "ne", "lt", "le", "gt", "ge", "contains", "in_binned_range", "is_null"}:
        return [formula]
    raise DmnBuildError("UNSUPPORTED_CONDITION", "DMN input cells support only conjunctions of atomic predicates.")


def _constraint_for_symbol(formula: Mapping[str, Any], symbol_id: str) -> str:
    if symbol_id not in _formula_symbols(formula):
        raise DmnBuildError("SYMBOL_NOT_IN_CONDITION", f"Condition does not reference {symbol_id!r}.")
    op = formula.get("op")
    if op == "is_null":
        return "null"
    if op == "contains":
        return formula_to_feel(formula)
    if op == "in_binned_range":
        return formula_to_feel(formula)
    left_symbol = _operand_symbol(formula.get("left"))
    right_symbol = _operand_symbol(formula.get("right"))
    if left_symbol == symbol_id and right_symbol is None:
        operator = {"eq": "", "ne": "!= ", "lt": "< ", "le": "<= ", "gt": "> ", "ge": ">= "}[op]
        literal = _feel_operand(formula.get("right"))
        return literal if op == "eq" else operator + literal
    if right_symbol == symbol_id and left_symbol is None:
        return formula_to_feel(formula)
    raise DmnBuildError("UNSUPPORTED_CONDITION", "Each DMN input cell must constrain one symbol against a literal.")


def _condition_cells(condition: Mapping[str, Any], input_ids: Sequence[str]) -> dict[str, str]:
    cells: dict[str, str] = {}
    for atom in _conjuncts(condition):
        symbols = _formula_symbols(atom)
        if len(symbols) != 1:
            raise DmnBuildError("UNSUPPORTED_CONDITION", "Each atomic condition must reference one symbol.")
        symbol_id = next(iter(symbols))
        if symbol_id not in input_ids:
            raise DmnBuildError("UNSUPPORTED_CONDITION", f"Condition symbol {symbol_id!r} is not an input symbol.")
        value = _constraint_for_symbol(atom, symbol_id)
        cells[symbol_id] = f"({cells[symbol_id]}) and ({value})" if symbol_id in cells else value
    return cells


def _metadata_is_unscoped(scope: Mapping[str, Any]) -> bool:
    metadata = scope.get("metadata") if isinstance(scope.get("metadata"), Mapping) else {}
    return not any(value for value in metadata.values()) and scope.get("predicate") is None


def _rule_to_xml(rule: Mapping[str, Any], input_ids: Sequence[str], output_ids: Sequence[str], symbols: Mapping[str, Mapping[str, Any]], index: int, table_id: str) -> ET.Element:
    if rule.get("exceptions"):
        raise DmnBuildError("UNSUPPORTED_EXCEPTIONS", f"Rule {rule.get('id')!r} has exceptions not representable in this DMN subset.")
    if not _metadata_is_unscoped(rule.get("scope", {})):
        raise DmnBuildError("UNSUPPORTED_SCOPE", f"Rule {rule.get('id')!r} has contextual scope metadata.")
    cells = _condition_cells(rule["condition"], input_ids)
    effects = {str(effect.get("target")): effect for effect in rule.get("effects", [])}
    if set(effects) != set(output_ids):
        raise DmnBuildError("OUTPUT_MISMATCH", f"Rule {rule.get('id')!r} does not assign every table output exactly once.")
    node = ET.Element(_tag("rule"), {"id": _safe_id(f"rule_{table_id}_{rule.get('id')}_{index}", f"rule_{index}")})
    for symbol_id in input_ids:
        entry = ET.SubElement(node, _tag("inputEntry"))
        ET.SubElement(entry, _tag("text")).text = cells.get(symbol_id, "-")
    for symbol_id in output_ids:
        effect = effects[symbol_id]
        entry = ET.SubElement(node, _tag("outputEntry"))
        ET.SubElement(entry, _tag("text")).text = _feel_operand(effect.get("value"))
    return node


def build_dmn_document(ir: Mapping[str, Any], *, model_name: str = "LExec IR v1 DMN") -> ET.Element:
    """Build a DMN 1.3 XML element for every proven table in *ir*."""

    errors = validate_ir(ir)
    if errors:
        raise DmnBuildError("INVALID_IR", "; ".join(errors))
    symbols = {str(symbol["id"]): symbol for symbol in ir.get("symbols", [])}
    root = ET.Element(_tag("definitions"), {
        "id": "definitions_lexec_ir_v1",
        "name": model_name,
        "namespace": DMN_PREFIX,
        "exporter": "compliance-to-code",
        "exporterVersion": "lexec-ir/1",
    })
    input_symbols = {symbol_id: symbol for symbol_id, symbol in symbols.items() if symbol.get("role") == "input"}
    for symbol_id, symbol in sorted(input_symbols.items()):
        input_data = ET.SubElement(root, _tag("inputData"), {"id": _safe_id(f"input_{symbol_id}", "input"), "name": symbol_id})
        ET.SubElement(input_data, _tag("variable"), {"name": symbol_id, "typeRef": _type_ref(symbol)})
    rule_map = {str(rule["id"]): rule for rule in ir.get("rules", [])}
    for table_index, table in enumerate(ir.get("tables", []), 1):
        proof = table.get("policy_proof", {})
        if proof.get("status") != "proved":
            raise DmnBuildError("UNPROVED_TABLE_POLICY", f"Table {table.get('id')!r} has proof status {proof.get('status')!r}.")
        policy = table.get("hit_policy")
        if policy not in SUPPORTED_HIT_POLICIES:
            raise DmnBuildError("UNSUPPORTED_HIT_POLICY", f"Table {table.get('id')!r} uses {policy!r}.")
        selected = [rule_map.get(str(rule_id)) for rule_id in table.get("rule_ids", [])]
        if any(rule is None for rule in selected):
            raise DmnBuildError("MISSING_RULE", f"Table {table.get('id')!r} references a missing rule.")
        referenced = set()
        for rule in selected:
            referenced.update(_formula_symbols(rule["condition"]))
            if any(symbol_id not in input_symbols for symbol_id in referenced):
                raise DmnBuildError("UNSUPPORTED_DERIVED_INPUT", f"Table {table.get('id')!r} references a non-input symbol.")
        input_ids = sorted(referenced)
        output_ids = list(table.get("output_signature", []))
        if not input_ids or not output_ids:
            raise DmnBuildError("EMPTY_TABLE_SIGNATURE", f"Table {table.get('id')!r} needs inputs and outputs.")
        decision_id = _safe_id(f"decision_{table.get('id')}", f"decision_{table_index}")
        decision = ET.SubElement(root, _tag("decision"), {"id": decision_id, "name": str(table.get("id"))})
        output_type = "string" if len(output_ids) == 1 else "context"
        ET.SubElement(decision, _tag("variable"), {"id": _safe_id(f"variable_{table.get('id')}", f"variable_{table_index}"), "name": str(table.get("id")), "typeRef": output_type})
        for symbol_id in input_ids:
            ET.SubElement(decision, _tag("informationRequirement")).append(
                ET.Element(_tag("requiredInput"), {"href": f"#input_{symbol_id}"})
            )
        table_node = ET.SubElement(decision, _tag("decisionTable"), {"id": _safe_id(f"decisionTable_{table.get('id')}", f"decisionTable_{table_index}"), "hitPolicy": policy})
        for input_index, symbol_id in enumerate(input_ids, 1):
            input_node = ET.SubElement(table_node, _tag("input"), {"id": _safe_id(f"inputClause_{table.get('id')}_{symbol_id}", f"input_{input_index}")})
            expression = ET.SubElement(input_node, _tag("inputExpression"), {"id": _safe_id(f"inputExpression_{table.get('id')}_{symbol_id}", f"expression_{input_index}"), "typeRef": _type_ref(input_symbols[symbol_id])})
            ET.SubElement(expression, _tag("text")).text = symbol_id
        for output_index, symbol_id in enumerate(output_ids, 1):
            if symbol_id not in symbols:
                raise DmnBuildError("UNKNOWN_OUTPUT", f"Table output {symbol_id!r} is not declared.")
            ET.SubElement(table_node, _tag("output"), {"id": _safe_id(f"outputClause_{table.get('id')}_{symbol_id}", f"output_{output_index}"), "name": symbol_id, "typeRef": _type_ref(symbols[symbol_id])})
        for rule_index, rule in enumerate(selected, 1):
            table_node.append(_rule_to_xml(rule, input_ids, output_ids, symbols, rule_index, str(table.get("id"))))
    return root
