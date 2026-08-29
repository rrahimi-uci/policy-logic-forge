"""Fail-closed DMN 1.3 and BPMN 2.0 projections for extraction graphs.

The extraction graph is not an executable semantics.  This exporter therefore
emits a reviewable model for every rule, while marking rules that are not
grounded or contain unsupported predicates as ``requiresReview``.  Unsupported
predicates lower to a never-match DMN entry (``false``), rather than silently
inventing behavior.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Mapping, Sequence

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


def _feel(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _predicate_test(predicate: Mapping[str, Any]) -> str | None:
    variable = str(predicate.get("variable") or "").strip()
    operator = str(predicate.get("operator") or "").strip()
    if not variable:
        return None
    value = predicate.get("value")
    if operator in {"==", "="}:
        return _feel(value)
    if operator in {"!=", "<>", "<", "<=", ">", ">="}:
        return f"{operator if operator != '<>' else '!='} {_feel(value)}"
    if operator == "in" and isinstance(value, list):
        return "[" + ", ".join(_feel(item) for item in value) + "]"
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
            expr = ET.SubElement(inp, f"{{{DMN_NS}}}inputExpression", {"typeRef": "boolean" if variables.get(var, {}).get("type") == "boolean" else "string"})
            ET.SubElement(expr, f"{{{DMN_NS}}}text").text = var
        for o in outcomes:
            var = str(o.get("variable"))
            ET.SubElement(table, f"{{{DMN_NS}}}output", {"id": _id(f"output_{rid}_{var}", "output"), "name": var, "typeRef": "string"})
        row = ET.SubElement(table, f"{{{DMN_NS}}}rule", {"id": _id(f"row_{rid}", f"row_{index}")})
        for p in predicates:
            entry = ET.SubElement(row, f"{{{DMN_NS}}}inputEntry")
            ET.SubElement(entry, f"{{{DMN_NS}}}text").text = _predicate_test(p) or "false"
        for o in outcomes:
            entry = ET.SubElement(row, f"{{{DMN_NS}}}outputEntry")
            ET.SubElement(entry, f"{{{DMN_NS}}}text").text = _feel(o.get("value"))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def build_dags_bpmn(graph: Mapping[str, Any], dags: Mapping[str, Any], *, model_name: str = "Policy Logic Forge BPMN") -> bytes:
    """Emit executable business-rule tasks following the dependency-DAG order."""
    rules = {str(r.get("rule_id")): r for r in graph.get("business_rules", []) if isinstance(r, Mapping)}
    root = ET.Element(f"{{{BPMN_NS}}}definitions", {"id": "definitions_compliance_graph", "targetNamespace": CTC_NS})
    for dindex, dag in enumerate(dags.get("dags", []), 1):
        process = ET.SubElement(root, f"{{{BPMN_NS}}}process", {"id": _id(dag.get("dag_id"), f"process_{dindex}"), "name": str(dag.get("dag_id")), "isExecutable": "true"})
        start = ET.SubElement(process, f"{{{BPMN_NS}}}startEvent", {"id": f"start_{dindex}"})
        previous = start
        order = list(dag.get("topological_order") or dag.get("rule_ids", []))
        # A condensed cycle-group is an ordering barrier, not a lost rule.
        # Expand its members deterministically and append any defensive misses.
        for group in dag.get("cycle_groups", []):
            members = [str(item) for item in group.get("rule_ids", [])]
            if any(str(item) == str(group.get("group_id")) for item in order):
                position = next(i for i, item in enumerate(order) if str(item) == str(group.get("group_id")))
                order[position:position + 1] = members
        order.extend(str(rid) for rid in dag.get("rule_ids", []) if str(rid) not in {str(item) for item in order})
        for nindex, rid in enumerate(order, 1):
            rule = rules.get(str(rid), {})
            task = ET.SubElement(process, f"{{{BPMN_NS}}}businessRuleTask", {"id": _id(f"task_{rid}", f"task_{dindex}_{nindex}"), "name": str(rule.get("rule_name") or rid), "implementation": "##DMN"})
            task.set(f"{{{CTC_NS}}}ruleId", str(rid)); task.set(f"{{{CTC_NS}}}decisionRef", _id(f"decision_{rid}", f"decision_{nindex}"))
            task.set(f"{{{CTC_NS}}}requiresReview", str(bool(rule.get("requires_review", True))).lower()); task.set(f"{{{CTC_NS}}}sourceRef", _source_ref(rule))
            ET.SubElement(process, f"{{{BPMN_NS}}}sequenceFlow", {"id": f"flow_{dindex}_{nindex}", "sourceRef": previous.get("id"), "targetRef": task.get("id")})
            previous = task
        end = ET.SubElement(process, f"{{{BPMN_NS}}}endEvent", {"id": f"end_{dindex}"})
        ET.SubElement(process, f"{{{BPMN_NS}}}sequenceFlow", {"id": f"flow_{dindex}_end", "sourceRef": previous.get("id"), "targetRef": end.get("id")})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def validate_executable_models(dmn: bytes, bpmn: bytes, expected_rule_ids: Sequence[str]) -> list[str]:
    """Structural validation shared by CLI and tests; no engine is implied."""
    errors: list[str] = []
    try:
        droot, broot = ET.fromstring(dmn), ET.fromstring(bpmn)
    except ET.ParseError as exc:
        return [f"XML parse error: {exc}"]
    if droot.tag != f"{{{DMN_NS}}}definitions": errors.append("DMN root is not DMN 1.3 definitions")
    if broot.tag != f"{{{BPMN_NS}}}definitions": errors.append("BPMN root is not BPMN 2.0 definitions")
    d_ids = {node.get(f"{{{CTC_NS}}}ruleId") for node in droot.iter(f"{{{DMN_NS}}}decision")}
    b_ids = {node.get(f"{{{CTC_NS}}}ruleId") for node in broot.iter(f"{{{BPMN_NS}}}businessRuleTask")}
    expected = set(map(str, expected_rule_ids))
    if d_ids != expected: errors.append(f"DMN rule coverage mismatch: {len(d_ids)} != {len(expected)}")
    if not expected.issubset(b_ids): errors.append("BPMN does not reference every graph rule")
    for flow in broot.iter(f"{{{BPMN_NS}}}sequenceFlow"):
        if not flow.get("sourceRef") or not flow.get("targetRef"): errors.append("BPMN sequenceFlow has missing endpoint")
    return errors
