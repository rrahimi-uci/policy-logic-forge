"""Fail-closed DMN 1.3 and BPMN 2.0 projections for extraction graphs.

The extraction graph is not an executable semantics.  This exporter therefore
emits a reviewable DMN model for every rule. BPMN is narrower: it is emitted
only for source-explicit ordered workflow semantics, never inferred from graph
dependency order. Unsupported predicates lower to a never-match DMN entry
(``false``), rather than silently inventing behavior.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Mapping, Sequence

from utils.semantic_routing import bpmn_eligibility

DMN_NS = "https://www.omg.org/spec/DMN/20191111/MODEL/"
BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
CTC_NS = "https://github.com/rrahimi-uci/policy-logic-forge/executable/1"
ET.register_namespace("dmn", DMN_NS)
ET.register_namespace("bpmn", BPMN_NS)
ET.register_namespace("ctc", CTC_NS)


def _id(value: Any, prefix: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("_")
    if not text or not (text[0].isalpha() or text[0] == "_"):
        text = f"{prefix}_{text}" if text else prefix
    return text


def _feel(value: Any, value_type: Any = None) -> str:
    if value_type == "feel_expression" and isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        constructor = {
            "date": "date",
            "date_time": "date and time",
            "time": "time",
            "duration": "duration",
        }.get(str(value_type or ""))
        if constructor:
            return f"{constructor}({json.dumps(value, ensure_ascii=False)})"
    return json.dumps(str(value), ensure_ascii=False)


def _dmn_type_ref(variable_type: Any) -> str:
    return {
        "boolean": "boolean",
        "number": "number",
        "date": "date",
        "date_time": "date and time",
        "time": "time",
        "duration": "days and time duration",
    }.get(str(variable_type or ""), "string")


def _predicate_test(predicate: Mapping[str, Any]) -> str | None:
    variable = str(predicate.get("variable") or "").strip()
    operator = str(predicate.get("operator") or "").strip()
    if not variable:
        return None
    value = predicate.get("value")
    value_type = predicate.get("value_type")
    if operator in {"==", "="}:
        return _feel(value, value_type)
    if operator in {"!=", "<>", "<", "<=", ">", ">="}:
        return f"{operator if operator != '<>' else '!='} {_feel(value, value_type)}"
    if operator == "in" and isinstance(value, list):
        return "[" + ", ".join(_feel(item, value_type) for item in value) + "]"
    if operator == "not_in" and isinstance(value, list):
        return "not(" + ", ".join(_feel(item, value_type) for item in value) + ")"
    if operator == "contains":
        return f'contains(?, {_feel(value)})'
    return None


def _source_ref(rule: Mapping[str, Any]) -> str:
    ref = rule.get("source_reference")
    if isinstance(ref, list):
        ref = ref[0] if ref else {}
    if not isinstance(ref, Mapping):
        return "unresolved"
    return f"{ref.get('chunk_path', 'unresolved')}#{ref.get('section_id', 'unresolved')}"


def build_graph_dmn(graph: Mapping[str, Any], *, model_name: str = "Policy Logic Forge DMN") -> bytes:
    """Emit one DMN decision table per graph rule, preserving audit metadata."""
    rules = [r for r in graph.get("business_rules", []) if isinstance(r, Mapping)]
    root = ET.Element(f"{{{DMN_NS}}}definitions", {
        "id": "definitions_compliance_graph", "name": model_name,
        "namespace": CTC_NS, "exporter": "policy-logic-forge",
        "exporterVersion": "graph-projection/1",
    })
    for index, rule in enumerate(rules, 1):
        rid = str(rule.get("rule_id") or f"rule_{index}")
        decision_id = _id(f"decision_{rid}", f"decision_{index}")
        decision = ET.SubElement(root, f"{{{DMN_NS}}}decision", {
            "id": decision_id, "name": str(rule.get("rule_name") or rid),
        })
        decision.set(f"{{{CTC_NS}}}ruleId", rid)
        decision.set(f"{{{CTC_NS}}}requiresReview", str(bool(rule.get("requires_review", True))).lower())
        decision.set(f"{{{CTC_NS}}}groundingStatus", str((rule.get("grounding") or {}).get("status", "unknown")))
        decision.set(f"{{{CTC_NS}}}sourceRef", _source_ref(rule))
        table = ET.SubElement(decision, f"{{{DMN_NS}}}decisionTable", {
            "id": _id(f"table_{rid}", f"table_{index}"),
            "hitPolicy": str((rule.get("execution") or {}).get("dmn", {}).get("hit_policy") or "UNIQUE"),
        })
        predicates = [p for p in rule.get("condition_predicates", []) if isinstance(p, Mapping)]
        outcomes = [o for o in rule.get("outcomes", []) if isinstance(o, Mapping)]
        variables = {str(v.get("name")): v for v in rule.get("variables", []) if isinstance(v, Mapping) and v.get("name")}
        for p in predicates:
            var = str(p.get("variable"))
            inp = ET.SubElement(table, f"{{{DMN_NS}}}input", {"id": _id(f"input_{rid}_{var}", "input")})
            expr = ET.SubElement(inp, f"{{{DMN_NS}}}inputExpression", {"typeRef": _dmn_type_ref(variables.get(var, {}).get("type"))})
            ET.SubElement(expr, f"{{{DMN_NS}}}text").text = var
        for o in outcomes:
            var = str(o.get("variable"))
            ET.SubElement(table, f"{{{DMN_NS}}}output", {"id": _id(f"output_{rid}_{var}", "output"), "name": var, "typeRef": _dmn_type_ref(variables.get(var, {}).get("type"))})
        row = ET.SubElement(table, f"{{{DMN_NS}}}rule", {"id": _id(f"row_{rid}", f"row_{index}")})
        for p in predicates:
            entry = ET.SubElement(row, f"{{{DMN_NS}}}inputEntry")
            ET.SubElement(entry, f"{{{DMN_NS}}}text").text = _predicate_test(p) or "false"
        for o in outcomes:
            entry = ET.SubElement(row, f"{{{DMN_NS}}}outputEntry")
            ET.SubElement(entry, f"{{{DMN_NS}}}text").text = _feel(o.get("value"), o.get("value_type"))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def build_dags_bpmn(graph: Mapping[str, Any], dags: Mapping[str, Any], *, model_name: str = "Policy Logic Forge BPMN") -> bytes:
    """Emit only source-explicit workflows; dependency DAGs are not processes.

    ``dags`` remains in the signature because it is a required upstream audit
    artifact and older callers provide it. Its graph order is intentionally
    not lowered to sequence flows: a dependency is not evidence that one
    human or service task follows another in the policy's process.
    """
    del dags
    rules = [r for r in graph.get("business_rules", []) if isinstance(r, Mapping)]
    root = ET.Element(f"{{{BPMN_NS}}}definitions", {
        "id": "definitions_compliance_graph", "name": model_name, "targetNamespace": CTC_NS,
        "exporter": "policy-logic-forge", "exporterVersion": "explicit-workflow/2",
    })
    tag_by_kind = {
        "business_rule_task": "businessRuleTask",
        "user_task": "userTask",
        "service_task": "serviceTask",
        "send_task": "sendTask",
        "receive_task": "receiveTask",
    }
    for dindex, rule in enumerate(rules, 1):
        eligible, _ = bpmn_eligibility(rule)
        if not eligible:
            continue
        rid = str(rule.get("rule_id"))
        workflow = rule["workflow_semantics"]
        process = ET.SubElement(root, f"{{{BPMN_NS}}}process", {
            "id": _id(f"process_{rid}", f"process_{dindex}"),
            "name": str(rule.get("rule_name") or rid), "isExecutable": "true",
        })
        process.set(f"{{{CTC_NS}}}ruleId", rid)
        process.set(f"{{{CTC_NS}}}sourceRef", _source_ref(rule))
        process.set(f"{{{CTC_NS}}}triggerEvent", str(workflow.get("trigger_event")))
        process.set(f"{{{CTC_NS}}}actorRole", str(workflow.get("actor_role")))
        start = ET.SubElement(process, f"{{{BPMN_NS}}}startEvent", {"id": f"start_{dindex}", "name": str(workflow.get("trigger_event"))})
        previous = start
        for nindex, step in enumerate(workflow.get("ordered_steps", []), 1):
            kind = str(step.get("kind"))
            attributes = {"id": _id(f"step_{rid}_{step.get('step_id')}", f"task_{dindex}_{nindex}"), "name": str(step.get("name"))}
            if kind == "business_rule_task":
                attributes["implementation"] = "##DMN"
            task = ET.SubElement(process, f"{{{BPMN_NS}}}{tag_by_kind[kind]}", attributes)
            task.set(f"{{{CTC_NS}}}ruleId", rid)
            if kind == "business_rule_task":
                task.set(f"{{{CTC_NS}}}decisionRef", _id(f"decision_{rid}", f"decision_{nindex}"))
            ET.SubElement(process, f"{{{BPMN_NS}}}sequenceFlow", {"id": f"flow_{dindex}_{nindex}", "sourceRef": previous.get("id"), "targetRef": task.get("id")})
            previous = task
        end = ET.SubElement(process, f"{{{BPMN_NS}}}endEvent", {"id": f"end_{dindex}"})
        ET.SubElement(process, f"{{{BPMN_NS}}}sequenceFlow", {"id": f"flow_{dindex}_end", "sourceRef": previous.get("id"), "targetRef": end.get("id")})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def validate_executable_models(
    dmn: bytes,
    bpmn: bytes,
    expected_rule_ids: Sequence[str],
    expected_bpmn_rule_ids: Sequence[str] = (),
) -> list[str]:
    """Structural validation shared by CLI and tests; no engine is implied."""
    errors: list[str] = []
    try:
        droot, broot = ET.fromstring(dmn), ET.fromstring(bpmn)
    except ET.ParseError as exc:
        return [f"XML parse error: {exc}"]
    if droot.tag != f"{{{DMN_NS}}}definitions": errors.append("DMN root is not DMN 1.3 definitions")
    if broot.tag != f"{{{BPMN_NS}}}definitions": errors.append("BPMN root is not BPMN 2.0 definitions")
    d_ids = {node.get(f"{{{CTC_NS}}}ruleId") for node in droot.iter(f"{{{DMN_NS}}}decision")}
    b_ids = {node.get(f"{{{CTC_NS}}}ruleId") for node in broot.iter(f"{{{BPMN_NS}}}process")}
    expected = set(map(str, expected_rule_ids))
    expected_bpmn = set(map(str, expected_bpmn_rule_ids))
    if d_ids != expected: errors.append(f"DMN rule coverage mismatch: {len(d_ids)} != {len(expected)}")
    if b_ids != expected_bpmn: errors.append(f"BPMN eligibility coverage mismatch: {len(b_ids)} != {len(expected_bpmn)}")
    for flow in broot.iter(f"{{{BPMN_NS}}}sequenceFlow"):
        if not flow.get("sourceRef") or not flow.get("targetRef"): errors.append("BPMN sequenceFlow has missing endpoint")
    return errors
