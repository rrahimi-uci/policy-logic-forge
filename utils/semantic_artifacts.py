"""SBVR-aligned vocabulary and CMMN review artifacts.

These are deliberately scoped profiles, not claims of full OMG interchange
conformance. They preserve concept typing and review lifecycle semantics that
DMN/BPMN cannot represent without overloading those notations.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Mapping


CMMN_NS = "http://www.omg.org/spec/CMMN/20151109/MODEL"
CTC_NS = "https://github.com/rrahimi-uci/policy-logic-forge/executable/1"
ET.register_namespace("cmmn", CMMN_NS)
ET.register_namespace("ctc", CTC_NS)

CONCEPT_KINDS = {"actor_role", "business_object", "evidence_object", "event", "decision_variable", "process"}


def _id(value: Any, prefix: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("_")
    if not text or not (text[0].isalpha() or text[0] == "_"):
        text = f"{prefix}_{text}" if text else prefix
    return text


def build_sbvr_profile(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Build a provenance-preserving, SBVR-aligned semantic vocabulary."""

    concepts = []
    unresolved = []
    entity_types = graph.get("entity_types")
    for name, definition in sorted(entity_types.items() if isinstance(entity_types, Mapping) else []):
        body = definition if isinstance(definition, Mapping) else {}
        kind = str(body.get("concept_kind", "unresolved"))
        item = {
            "concept_id": str(name),
            "preferred_term": str(name).replace("_", " ").title(),
            "definition": str(body.get("definition", "")),
            "concept_kind": kind,
            "source_evidence": body.get("source_evidence", []),
        }
        concepts.append(item)
        if kind not in CONCEPT_KINDS:
            unresolved.append(str(name))
    facts = []
    relationships = graph.get("relationships")
    for name, definition in sorted(relationships.items() if isinstance(relationships, Mapping) else []):
        body = definition if isinstance(definition, Mapping) else {}
        grounding = body.get("grounding") if isinstance(body.get("grounding"), Mapping) else {}
        facts.append({
            "fact_type_id": str(name),
            "subject_concept": body.get("source_entity"),
            "verb_term": str(name).replace("_", " ").casefold(),
            "object_concept": body.get("target_entity"),
            "grounding_status": grounding.get("status", "unverified"),
            "source_evidence": body.get("source_evidence", []),
        })
    return {
        "profile_type": "sbvr_aligned_semantic_vocabulary",
        "conformance": "pipeline_profile_not_full_sbvr_exchange",
        "concept_kinds": sorted(CONCEPT_KINDS),
        "concepts": concepts,
        "fact_types": facts,
        "unresolved_concept_ids": unresolved,
    }


def build_review_cmmn(graph: Mapping[str, Any]) -> bytes:
    """Emit one CMMN case for each non-machine review route."""

    root = ET.Element(f"{{{CMMN_NS}}}definitions", {
        "id": "definitions_policy_review", "targetNamespace": CTC_NS,
        "exporter": "policy-logic-forge", "exporterVersion": "review-routing/1",
    })
    for index, rule in enumerate(graph.get("business_rules", []), 1):
        if not isinstance(rule, Mapping):
            continue
        route = rule.get("review_route") if isinstance(rule.get("review_route"), Mapping) else {}
        if route.get("route") not in {"case_management", "human_review"}:
            continue
        rid = str(rule.get("rule_id") or f"rule_{index}")
        case = ET.SubElement(root, f"{{{CMMN_NS}}}case", {
            "id": _id(f"case_{rid}", f"case_{index}"), "name": str(rule.get("rule_name") or rid),
        })
        case.set(f"{{{CTC_NS}}}ruleId", rid)
        case.set(f"{{{CTC_NS}}}reviewRoute", str(route.get("route")))
        plan = ET.SubElement(case, f"{{{CMMN_NS}}}casePlanModel", {
            "id": _id(f"plan_{rid}", f"plan_{index}"), "name": "Resolve policy evidence findings",
        })
        task_id = _id(f"review_task_{rid}", f"review_task_{index}")
        ET.SubElement(plan, f"{{{CMMN_NS}}}humanTask", {"id": task_id, "name": "Review grounded findings"})
        ET.SubElement(plan, f"{{{CMMN_NS}}}planItem", {
            "id": _id(f"review_item_{rid}", f"review_item_{index}"), "definitionRef": task_id,
        })
        milestone_id = _id(f"resolved_{rid}", f"resolved_{index}")
        ET.SubElement(plan, f"{{{CMMN_NS}}}milestone", {"id": milestone_id, "name": "Review resolved"})
        ET.SubElement(plan, f"{{{CMMN_NS}}}planItem", {
            "id": _id(f"resolved_item_{rid}", f"resolved_item_{index}"), "definitionRef": milestone_id,
        })
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def validate_review_cmmn(document: bytes, expected_rule_ids: set[str]) -> list[str]:
    """Validate parseability and exact routed-rule coverage."""

    try:
        root = ET.fromstring(document)
    except ET.ParseError as exc:
        return [f"CMMN XML parse error: {exc}"]
    errors = []
    if root.tag != f"{{{CMMN_NS}}}definitions":
        errors.append("CMMN root is not CMMN 1.1 definitions")
    actual = {node.get(f"{{{CTC_NS}}}ruleId") for node in root.iter(f"{{{CMMN_NS}}}case")}
    if actual != set(map(str, expected_rule_ids)):
        errors.append(f"CMMN review coverage mismatch: {len(actual)} != {len(expected_rule_ids)}")
    return errors
