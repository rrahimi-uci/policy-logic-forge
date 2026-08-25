"""DMN 1.3 serialization and structural validation for the LExec emitter."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Mapping

from utils.dmn_builder import DMN_NS, DmnBuildError, build_dmn_document


def emit_dmn(ir: Mapping[str, Any]) -> bytes:
    """Serialize a proven LExec IR document to validated DMN 1.3 XML."""

    root = build_dmn_document(ir)
    document = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    errors = validate_dmn(document)
    if errors:
        raise DmnBuildError("INVALID_DMN", "; ".join(errors))
    return document


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(parent: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(parent) if _local(child.tag) == name]


def validate_dmn(document: bytes | str | ET.Element) -> list[str]:
    """Return deterministic structural errors for emitted DMN XML.

    This is intentionally a shape/policy validator, not an XSD or DMN engine;
    semantic equivalence remains BE-4's responsibility.
    """

    try:
        root = document if isinstance(document, ET.Element) else ET.fromstring(document)
    except (ET.ParseError, TypeError) as exc:
        return [f"XML parse error: {exc}"]
    errors: list[str] = []
    if _local(root.tag) != "definitions" or not root.tag.startswith("{" + DMN_NS + "}"):
        errors.append("root must be DMN 1.3 definitions")
        return errors
    decisions = _children(root, "decision")
    if not decisions:
        errors.append("definitions must contain at least one decision")
    seen_rule_ids: set[str] = set()
    for decision_index, decision in enumerate(decisions):
        tables = _children(decision, "decisionTable")
        if len(tables) != 1:
            errors.append(f"decision[{decision_index}] must contain exactly one decisionTable")
            continue
        table = tables[0]
        if table.get("hitPolicy") not in {"UNIQUE", "ANY", "PRIORITY", "COLLECT"}:
            errors.append(f"decision[{decision_index}] has invalid hitPolicy")
        inputs = _children(table, "input")
        outputs = _children(table, "output")
        if not inputs or not outputs:
            errors.append(f"decision[{decision_index}] table needs inputs and outputs")
        for input_index, input_node in enumerate(inputs):
            expressions = _children(input_node, "inputExpression")
            if len(expressions) != 1:
                errors.append(f"decision[{decision_index}] input[{input_index}] needs one inputExpression")
            elif len(_children(expressions[0], "text")) != 1 or not (_children(expressions[0], "text")[0].text or "").strip():
                errors.append(f"decision[{decision_index}] input[{input_index}] has an empty inputExpression")
        for rule_index, rule in enumerate(_children(table, "rule")):
            rule_id = rule.get("id")
            if not rule_id or rule_id in seen_rule_ids:
                errors.append(f"decision[{decision_index}] rule[{rule_index}] has a duplicate/missing id")
            seen_rule_ids.add(rule_id or "")
            if len(_children(rule, "inputEntry")) != len(inputs):
                errors.append(f"decision[{decision_index}] rule[{rule_index}] inputEntry count mismatch")
            if len(_children(rule, "outputEntry")) != len(outputs):
                errors.append(f"decision[{decision_index}] rule[{rule_index}] outputEntry count mismatch")
            for entry in [*_children(rule, "inputEntry"), *_children(rule, "outputEntry")]:
                texts = _children(entry, "text")
                if len(texts) != 1 or not (texts[0].text or "").strip():
                    errors.append(f"decision[{decision_index}] rule[{rule_index}] has an empty entry")
    return errors
