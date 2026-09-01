"""Conservative compilation of extracted arithmetic into DMN FEEL.

The extractor frequently emits a source-backed calculation as ``formula`` or
``expression`` even when it is already a simple arithmetic expression over
declared rule variables.  Treating that text as a string is wrong, while
forcing every calculation into review wastes a deterministic capability.

This module accepts only a deliberately small, auditable subset: numeric
constants, declared numeric variables, arithmetic operators, and the standard
FEEL functions min/max/sum/abs/ceiling/floor.  Natural-language
operator aliases are normalized only when every referenced phrase resolves to
an existing variable. Anything else returns ``None`` and remains fail-closed.
"""

from __future__ import annotations

import ast
import math
import re
from typing import Any, Iterable, Mapping


_FUNCTIONS = {
    "abs": "abs",
    "ceil": "ceiling",
    "ceiling": "ceiling",
    "floor": "floor",
    "max": "max",
    "min": "min",
    "sum": "sum",
}
_BIN_OPS = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.Mod: "%",
    ast.Pow: "**",
}
def _label(name: str) -> str:
    return re.sub(r"_+", " ", name).strip()


def _replace_declared_phrases(text: str, variable_names: Iterable[str]) -> str:
    result = text
    for name in sorted({str(item) for item in variable_names if str(item)}, key=len, reverse=True):
        labels = {name, _label(name)}
        for label in sorted(labels, key=len, reverse=True):
            result = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(label)}(?![A-Za-z0-9_])", name, result, flags=re.IGNORECASE)
    return result


def _normalize_text(expression: str, variable_names: Iterable[str], unit: str | None) -> str:
    text = " ".join(expression.strip().split())
    text = _replace_declared_phrases(text, variable_names)
    text = re.sub(r"\bthe\s+lesser\s+of\s+([A-Za-z_][A-Za-z0-9_]*)\s+and\s+([A-Za-z_][A-Za-z0-9_]*)\b", r"min(\1, \2)", text, flags=re.IGNORECASE)
    text = re.sub(r"\blesser\s*\(", "min(", text, flags=re.IGNORECASE)
    for phrase, symbol in (
        (r"\bmultiplied\s+by\b", "*"),
        (r"\bdivided\s+by\b", "/"),
        (r"\bminus\b", "-"),
        (r"\bplus\b", "+"),
    ):
        text = re.sub(phrase, symbol, text, flags=re.IGNORECASE)
    if unit:
        # DMN carries units on the variable declaration, not inside numeric
        # literals. Strip a matching unit only when it immediately follows a
        # number; unrelated words remain and make parsing fail closed.
        text = re.sub(rf"(?<=\d)\s+{re.escape(unit)}\b", "", text, flags=re.IGNORECASE)
    return text


def _emit(node: ast.AST, allowed_names: set[str]) -> str:
    if isinstance(node, ast.Expression):
        return _emit(node.body, allowed_names)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return repr(node.value)
    if isinstance(node, ast.Name) and node.id in allowed_names:
        return node.id
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return ("+" if isinstance(node.op, ast.UAdd) else "-") + _emit(node.operand, allowed_names)
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return f"({_emit(node.left, allowed_names)} {_BIN_OPS[type(node.op)]} {_emit(node.right, allowed_names)})"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS and not node.keywords:
        if not node.args:
            raise ValueError("computed functions require at least one argument")
        if node.func.id in {"abs", "ceil", "ceiling", "floor"} and len(node.args) != 1:
            raise ValueError(f"{node.func.id} requires exactly one argument")
        return f"{_FUNCTIONS[node.func.id]}(" + ", ".join(_emit(arg, allowed_names) for arg in node.args) + ")"
    raise ValueError(f"unsupported computed-expression node: {type(node).__name__}")


def compile_feel_expression(
    expression: Any,
    variables: Iterable[Mapping[str, Any]],
    *,
    output_variable: str,
) -> str | None:
    """Return canonical FEEL or ``None`` when safe lowering is unavailable."""

    if not isinstance(expression, str) or not expression.strip():
        return None
    definitions = {
        str(item.get("name", "")).strip(): item
        for item in variables
        if isinstance(item, Mapping) and str(item.get("name", "")).strip()
    }
    target = definitions.get(str(output_variable).strip())
    if not isinstance(target, Mapping) or target.get("type") != "number":
        return None
    numeric_names = {
        name for name, definition in definitions.items()
        if definition.get("type") == "number" and definition.get("role") in {"input", "derived"}
    }
    normalized = _normalize_text(expression, numeric_names, str(target.get("unit") or "") or None)
    try:
        tree = ast.parse(normalized, mode="eval")
        rendered = _emit(tree, numeric_names)
    except (SyntaxError, TypeError, ValueError):
        return None
    referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id not in _FUNCTIONS}
    if not referenced or not referenced <= numeric_names:
        # A computed expression with no declared input is usually a disguised
        # literal or unparsed prose; keep it review-gated.
        return None
    return rendered


def evaluate_feel_expression(expression: Any, inputs: Mapping[str, Any]) -> int | float | None:
    """Evaluate only the numeric FEEL subset accepted by the compiler.

    This is intentionally not a general FEEL runtime. It is used to construct
    deterministic test vectors after an expression has already passed
    :func:`compile_feel_expression`. Unknown identifiers, booleans,
    non-finite results, and unsupported nodes fail closed.
    """

    if not isinstance(expression, str) or not expression.strip():
        return None

    def evaluate(node: ast.AST) -> int | float:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.Name):
            value = inputs.get(node.id)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return value
            raise ValueError("expression input is not numeric")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
            left, right = evaluate(node.left), evaluate(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Mod):
                return left % right
            return left**right
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            values = [evaluate(argument) for argument in node.args]
            if not values:
                raise ValueError("computed functions require arguments")
            if node.func.id == "min":
                return min(values)
            if node.func.id == "max":
                return max(values)
            if node.func.id == "sum":
                return sum(values)
            if node.func.id == "abs" and len(values) == 1:
                return abs(values[0])
            if node.func.id == "ceiling" and len(values) == 1:
                return math.ceil(values[0])
            if node.func.id == "floor" and len(values) == 1:
                return math.floor(values[0])
            raise ValueError("unsupported computed function")
        raise ValueError("unsupported computed-expression node")

    try:
        tree = ast.parse(expression, mode="eval")
        result = evaluate(tree)
    except (ArithmeticError, SyntaxError, TypeError, ValueError):
        return None
    if isinstance(result, float) and not math.isfinite(result):
        return None
    return result
