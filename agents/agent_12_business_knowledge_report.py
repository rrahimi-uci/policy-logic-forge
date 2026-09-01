#!/usr/bin/env python3
"""Generate a self-contained, human-reviewable business knowledge report.

Agent 12 is deliberately presentation-only.  It consumes the validated graph
and the model artifacts produced by Agent 11; it never invents rules, concepts,
or process semantics.  Every rendered item carries a stable link to an embedded
source chunk (or an explicit unresolved marker when no source pointer exists).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.config import get_config
from utils.kg_readiness import dependency_edges, source_document_index
from utils.semantic_artifacts import build_sbvr_profile


REPORT_DIR_NAME = "agent_12-business-knowledge-report"
REPORT_FILE_NAME = "business_knowledge_report.html"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _slug(value: Any, prefix: str = "item") -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "")).strip("-")
    return (text or prefix)[:160]


def _humanize(name: str) -> str:
    """``loan_eligible_for_sale`` -> ``Loan eligible for sale``, for display labels."""
    text = re.sub(r"[_\-]+", " ", str(name or "")).strip()
    return (text[:1].upper() + text[1:]) if text else ""


def _json_for_script(value: Any) -> str:
    """Serialize data safely for an application/json script element."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def _references(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _ref_key(ref: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(ref.get("chunk_path") or ref.get("document") or "").strip(),
        str(ref.get("section_id") or ref.get("section") or "").strip(),
        str(ref.get("start_offset") or ref.get("start") or "").strip(),
        str(ref.get("end_offset") or ref.get("end") or "").strip(),
    )


def _source_anchor(ref: Mapping[str, Any]) -> str:
    payload = "|".join(_ref_key(ref))
    return "source-" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _rule_references(rule: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Collect direct, field, and grounding references without duplicates."""
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add(value: Any, field: str = "source") -> None:
        for raw in _references(value):
            ref = dict(raw)
            ref["evidence_field"] = field
            key = _ref_key(ref)
            # A quote/source_text makes two otherwise-identical field records
            # useful only once in the report; retain the first field label.
            if key in seen:
                continue
            seen.add(key)
            refs.append(ref)

    add(rule.get("source_reference"))
    field_evidence = _mapping(rule.get("field_evidence"))
    for field, values in field_evidence.items():
        add(values, str(field))
    grounding = _mapping(rule.get("grounding"))
    add(grounding.get("evidence") or grounding.get("source_evidence"), "grounding")
    return refs


def _source_text(ref: Mapping[str, Any], chunks: Mapping[tuple[str, str], Mapping[str, Any]]) -> str:
    supplied = ref.get("source_text") or ref.get("quote") or ref.get("text")
    if supplied:
        return str(supplied)
    path = str(ref.get("chunk_path") or ref.get("document") or "")
    section = str(ref.get("section_id") or ref.get("section") or "")
    chunk = chunks.get((path, section)) or chunks.get((path, ""))
    return str(chunk.get("text", "")) if isinstance(chunk, Mapping) else ""


def _all_rule_refs(graph: Mapping[str, Any]) -> Iterable[tuple[str, Mapping[str, Any]]]:
    for rule in _list(graph.get("business_rules")):
        if not isinstance(rule, Mapping):
            continue
        rid = str(rule.get("rule_id") or "")
        if rid:
            yield rid, rule


def _concepts(graph: Mapping[str, Any], profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the governed SBVR vocabulary, excluding rule-local symbols.

    Decision variables are executable rule symbols, not automatically business
    concepts.  Treating each predicate name as an SBVR concept inflated real
    reports by thousands of mostly single-use propositions and attached a
    rule's citation as if it were a concept definition.
    """
    concepts: dict[str, dict[str, Any]] = {}

    def add(cid: Any, term: Any = None, definition: Any = "", kind: str = "unresolved", refs: Any = None) -> None:
        key = str(cid or "").strip()
        if not key:
            return
        item = concepts.setdefault(key, {
            "concept_id": key,
            "preferred_term": str(term or key).replace("_", " ").title(),
            "definition": str(definition or ""),
            "concept_kind": kind,
            "source_evidence": list(refs) if isinstance(refs, list) else [],
        })
        if not item.get("definition") and definition:
            item["definition"] = str(definition)
        if item.get("concept_kind") == "unresolved" and kind != "unresolved":
            item["concept_kind"] = kind
        existing = {_ref_key(ref) for ref in _references(item.get("source_evidence"))}
        for ref in _references(refs):
            if _ref_key(ref) not in existing:
                item["source_evidence"].append(dict(ref))
                existing.add(_ref_key(ref))

    for item in _list(profile.get("concepts")):
        if isinstance(item, Mapping):
            add(item.get("concept_id"), item.get("preferred_term"), item.get("definition"), str(item.get("concept_kind", "unresolved")), item.get("source_evidence"))
    for fact in _list(profile.get("fact_types")):
        if not isinstance(fact, Mapping):
            continue
        fact_refs = fact.get("source_evidence")
        add(fact.get("subject_concept"), kind="business_object", refs=fact_refs)
        add(fact.get("object_concept"), kind="business_object", refs=fact_refs)

    return [concepts[key] for key in sorted(concepts, key=str.casefold)]


def _decision_variables(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build a separate registry of executable symbols and their rule usage."""
    registry: dict[str, dict[str, Any]] = {}
    for rule_id, rule in _all_rule_refs(graph):
        declarations = [item for item in _list(rule.get("variables")) if isinstance(item, Mapping)]
        declared_names = {str(item.get("name")) for item in declarations if item.get("name")}
        declarations.extend(
            {"name": item.get("variable"), "role": "output", "type": item.get("value_type", "unknown")}
            for item in _list(rule.get("outcomes"))
            if isinstance(item, Mapping) and item.get("variable") and str(item.get("variable")) not in declared_names
        )
        for variable in declarations:
            name = str(variable.get("name") or "").strip()
            if not name:
                continue
            entry = registry.setdefault(name, {
                "variable_id": name,
                "types": set(),
                "roles": set(),
                "rule_ids": set(),
            })
            if variable.get("type"):
                entry["types"].add(str(variable.get("type")))
            if variable.get("role"):
                entry["roles"].add(str(variable.get("role")))
            entry["rule_ids"].add(rule_id)
    return [
        {
            "variable_id": name,
            "types": sorted(entry["types"], key=str.casefold),
            "roles": sorted(entry["roles"], key=str.casefold),
            "rule_ids": sorted(entry["rule_ids"], key=str.casefold),
            "scope": "reusable" if len(entry["rule_ids"]) > 1 else "rule_local",
        }
        for name, entry in sorted(registry.items(), key=lambda item: item[0].casefold())
    ]


def _category(rule: Mapping[str, Any]) -> tuple[str, str]:
    category = rule.get("business_category") or rule.get("category") or rule.get("rule_type") or "Uncategorized"
    subcategory = rule.get("business_subcategory") or rule.get("subcategory") or rule.get("rule_domain") or rule.get("rule_type") or "General"
    return str(category), str(subcategory)


def _rule_statement(rule: Mapping[str, Any]) -> str:
    for key in ("rule_statement", "natural_language", "description", "rule_name"):
        value = rule.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    conditions = "; ".join(str(p.get("variable")) + " " + str(p.get("operator")) + " " + str(p.get("value")) for p in _list(rule.get("condition_predicates")) if isinstance(p, Mapping))
    outcomes = "; ".join(str(o.get("variable")) + " = " + str(o.get("value")) for o in _list(rule.get("outcomes")) if isinstance(o, Mapping))
    return "When " + (conditions or "the rule applies") + ", then " + (outcomes or "the policy outcome is evaluated") + "."


def _confidence(rule: Mapping[str, Any]) -> float | None:
    # The extraction contract calls this field ``confidence_score``.  The
    # shorter aliases are retained for older graph snapshots, but omitting the
    # canonical field made every real report render a misleading "—" score.
    for key in ("confidence", "extraction_confidence", "grounding_confidence", "confidence_score"):
        value = rule.get(key)
        try:
            if value is not None:
                number = float(value)
                return number * 100 if 0 <= number <= 1 else number
        except (TypeError, ValueError):
            continue
    return None


def _confidence_source(rule: Mapping[str, Any]) -> str:
    source = str(rule.get("confidence_source") or "").strip()
    if source:
        return source
    if isinstance(rule.get("confidence_breakdown"), Mapping):
        return "derived_from_breakdown"
    if "confidence_score" in rule:
        return "unattributed_score"
    for key in ("confidence", "extraction_confidence", "grounding_confidence"):
        if key in rule:
            return key
    return "not_reported"


def _confidence_source_label(source: str) -> str:
    return {
        "default_config": "default configured",
        "derived_from_breakdown": "derived from breakdown",
        "model_reported": "model reported",
        "unattributed_score": "score origin not recorded",
        "not_scored": "not independently scored",
        "not_reported": "not reported",
    }.get(source, source.replace("_", " "))


def _logic_value(value: Any) -> str:
    """Render a typed value without losing its formal shape."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _predicate_expression(predicate: Mapping[str, Any]) -> str:
    return " ".join(
        str(predicate.get(key) or "?")
        for key in ("variable", "operator")
    ) + " " + _logic_value(predicate.get("value"))


def _condition_expression(predicates: Sequence[Mapping[str, Any]], logic: Any) -> str:
    """Turn condition_logic references into a compact, readable expression."""
    by_id = {
        str(predicate.get("predicate_id") or index): _predicate_expression(predicate)
        for index, predicate in enumerate(predicates)
    }

    def render(node: Any) -> str:
        if isinstance(node, Mapping):
            if "all" in node and isinstance(node["all"], list):
                return "( " + " AND ".join(render(item) for item in node["all"]) + " )"
            if "any" in node and isinstance(node["any"], list):
                return "( " + " OR ".join(render(item) for item in node["any"]) + " )"
            if "not" in node:
                return "NOT " + render(node["not"])
            if "predicate_ref" in node:
                reference = str(node["predicate_ref"])
                return by_id.get(reference, f"[{reference}]")
            return _logic_value(node)
        if isinstance(node, list):
            return "( " + " AND ".join(render(item) for item in node) + " )"
        return str(node)

    if logic is not None:
        return render(logic)
    if predicates:
        return " AND ".join(_predicate_expression(predicate) for predicate in predicates)
    return "No structured conditions reported"


def _logic_field_rows(items: Sequence[Any], kind: str) -> str:
    rows: list[str] = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, Mapping):
            rows.append(f'<div class="logic-row"><span class="logic-index">{index}</span><code>{_safe(_logic_value(item))}</code></div>')
            continue
        prefix = str(item.get("predicate_id") or item.get("variable") or f"{kind}_{index}")
        expression = _predicate_expression(item)
        value_type = item.get("value_type") or item.get("type")
        type_html = f'<span class="logic-type">{_safe(value_type)}</span>' if value_type else ""
        rows.append(f'<div class="logic-row"><span class="logic-index">{_safe(prefix)}</span><code>{_safe(expression)}</code>{type_html}</div>')
    return "".join(rows) or '<div class="empty">None declared</div>'


def _outcome_kind(value: Any, value_type: str) -> str:
    """Classify an outcome's value for badge styling: bool/number/list/text."""
    if isinstance(value, bool) or str(value_type or "").casefold() == "boolean":
        return "true" if (value is True or str(value).casefold() == "true") else "false"
    if isinstance(value, (int, float)) or str(value_type or "").casefold() == "number":
        return "number"
    if isinstance(value, list):
        return "list"
    return "text"


def _outcome_badge_html(value: Any, value_type: str) -> str:
    """A single outcome value, styled by kind: TRUE/FALSE pill, number chip, or
    text/enum chip -- a list explodes into its own set of small chips instead
    of one dense JSON string."""
    kind = _outcome_kind(value, value_type)
    if kind == "list":
        chips = "".join(f'<span class="outcome-value-item">{_safe(_logic_value(v))}</span>' for v in value) or '<span class="outcome-value-item">empty</span>'
        return f'<span class="outcome-badge type-list">{chips}</span>'
    if kind in ("true", "false"):
        return f'<span class="outcome-badge type-{kind}">{"TRUE" if kind == "true" else "FALSE"}</span>'
    label = _logic_value(value)
    return f'<span class="outcome-badge type-{kind}" title="{_safe(label)}">{_safe(label)}</span>'


def _outcome_cards_html(outcomes: Sequence[Any]) -> str:
    """Render each outcome as its own labeled card instead of a flat code
    row, so a rule that sets several variables reads as a scannable result
    panel rather than a repeated 'name = name value' line per entry."""
    cards: list[str] = []
    for index, item in enumerate(outcomes, 1):
        if not isinstance(item, Mapping):
            cards.append(f'<div class="outcome-card"><span class="outcome-name">Result {index}</span>{_outcome_badge_html(item, "")}</div>')
            continue
        name = str(item.get("variable") or f"outcome_{index}")
        cards.append(
            f'<div class="outcome-card"><span class="outcome-name">{_safe(_humanize(name))}'
            f'<code class="outcome-var">{_safe(name)}</code></span>'
            f'{_outcome_badge_html(item.get("value"), item.get("value_type") or item.get("type"))}</div>'
        )
    return "".join(cards) or '<div class="empty">None declared</div>'


def _outcome_chip_html(item: Mapping[str, Any]) -> str:
    """One outcome as an inline chip for the compact IF/THEN banner -- each
    result wraps on its own instead of joining into one long AND-chained
    sentence that becomes unreadable once a rule sets more than two or three
    variables."""
    name = str(item.get("variable") or "?")
    value = item.get("value")
    kind = _outcome_kind(value, item.get("value_type") or item.get("type"))
    value_class = f" ov-{kind}" if kind in ("true", "false") else ""
    return (
        f'<span class="outcome-chip{value_class}"><span class="ov-name">{_safe(name)}</span>'
        f'<span class="ov-eq">=</span><span class="ov-val">{_safe(_logic_value(value))}</span></span>'
    )


def _formal_logic_html(rule: Mapping[str, Any]) -> str:
    predicates = [item for item in _list(rule.get("condition_predicates")) if isinstance(item, Mapping)]
    outcomes = _list(rule.get("outcomes"))
    outcome_mappings = [item for item in outcomes if isinstance(item, Mapping)]
    exceptions = _list(rule.get("exceptions"))
    variables = [item for item in _list(rule.get("variables")) if isinstance(item, Mapping)]
    inputs = [item for item in variables if str(item.get("role") or "").casefold() == "input"]
    outputs = [item for item in variables if str(item.get("role") or "").casefold() == "output"]
    expression = _condition_expression(predicates, rule.get("condition_logic"))
    then_html = "".join(_outcome_chip_html(item) for item in outcome_mappings) or '<span class="outcome-chip">evaluate outcome</span>'
    return f'''<div class="formal-logic"><div class="logic-expression"><div class="logic-if"><span class="logic-keyword">IF</span> {_safe(expression)}</div><div class="logic-then-row"><span class="logic-keyword">THEN</span><div class="logic-then">{then_html}</div></div></div><div class="logic-grid"><div><h4>Conditions</h4><div class="logic-list">{_logic_field_rows(predicates, "condition")}</div></div><div><h4>Outcomes</h4><div class="outcome-grid">{_outcome_cards_html(outcome_mappings)}</div></div><div><h4>Exceptions</h4><div class="logic-list">{_logic_field_rows(exceptions, "exception")}</div></div><div><h4>Variables</h4><div class="logic-list"><div class="logic-row"><span class="logic-index">IN</span><code>{_safe(", ".join(str(item.get("name")) for item in inputs) or "none")}</code></div><div class="logic-row"><span class="logic-index">OUT</span><code>{_safe(", ".join(str(item.get("name")) for item in outputs) or "none")}</code></div></div></div></div><details class="logic-raw"><summary>Raw structured contract</summary><pre>{_safe(json.dumps({"conditions": rule.get("condition_predicates", []), "condition_logic": rule.get("condition_logic"), "outcomes": rule.get("outcomes", []), "exceptions": rule.get("exceptions", []), "dependencies": rule.get("dependencies", []), "related_entities": rule.get("related_entities", [])}, indent=2, ensure_ascii=False))}</pre></details></div>'''


def _grounding_summary(rule: Mapping[str, Any], grounding_status: str) -> str:
    grounding = _mapping(rule.get("grounding"))
    counts = _mapping(grounding.get("counts"))
    supported = counts.get("supported", 0)
    claim_count = grounding.get("claim_count")
    if claim_count is None and counts:
        claim_count = sum(value for value in counts.values() if isinstance(value, (int, float)))
    parts = [f'{supported}/{claim_count} claims supported'] if claim_count is not None else []
    if counts.get("contradicted"):
        parts.append(f'{counts["contradicted"]} contradiction' + ("s" if counts["contradicted"] != 1 else ""))
    if counts.get("insufficient_evidence"):
        parts.append(f'{counts["insufficient_evidence"]} evidence gap' + ("s" if counts["insufficient_evidence"] != 1 else ""))
    if grounding.get("invalid_evidence_records"):
        parts.append(f'{grounding["invalid_evidence_records"]} invalid citation' + ("s" if grounding["invalid_evidence_records"] != 1 else ""))
    if grounding_status == "certified":
        return parts[0] if parts else "All evaluated claims supported"
    return " · ".join(parts) or "Certification incomplete"


def _review_reasons(rule: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    readiness = _mapping(rule.get("readiness"))
    for section in _list(readiness.get("failed_sections")) + _list(readiness.get("pending_sections")):
        reasons.append(f"Readiness section {section} is unresolved")
    for issue in _list(readiness.get("failed_requirements")):
        if isinstance(issue, Mapping):
            reasons.append(str(issue.get("message") or issue.get("reason") or issue.get("requirement") or "Unresolved requirement"))
        elif issue:
            reasons.append(str(issue))
    for key in ("contract_issues", "grounding_issues", "review_reasons", "issues"):
        value = rule.get(key)
        if isinstance(value, list):
            for issue in value:
                if isinstance(issue, Mapping):
                    reasons.append(str(issue.get("message") or issue.get("reason") or issue.get("requirement") or "Unresolved issue"))
                elif issue:
                    reasons.append(str(issue))
    route = _mapping(rule.get("review_route"))
    reasons.extend(str(item) for item in _list(route.get("reasons")) if item)
    return list(dict.fromkeys(reasons))


#: No explicit severity/priority field exists anywhere in the data contract
#: (confirmed: the graph carries review_route + grounding status, not a
#: standalone severity). Derived here from those two signals so Human Review
#: can be triaged without a reviewer having to read every reason list first.
#: case_management and a contradicted grounding verdict outrank a plain
#: human_review route -- both represent a positively wrong or stuck state,
#: not an open judgment call.
_SEVERITY_META: dict[str, tuple[str, str]] = {
    "critical": ("🟥", "Critical"),
    "high": ("🟧", "High"),
    "medium": ("🟨", "Medium"),
    "low": ("🟩", "Low"),
}
_SEVERITY_ORDER = ("critical", "high", "medium", "low")


def _review_severity(rule: Mapping[str, Any]) -> str:
    if not rule.get("requires_review"):
        return "none"
    route = str(_mapping(rule.get("review_route")).get("route") or "unclassified")
    grounding_status = str(_mapping(rule.get("grounding")).get("status") or "")
    if route == "case_management" or grounding_status == "contradicted":
        return "critical"
    if route in ("human_review", "unclassified"):
        return "high"
    if route == "machine_repair":
        return "medium"
    return "low"


def _severity_badge_html(severity: str) -> str:
    icon, label = _SEVERITY_META.get(severity, ("⬜", "None"))
    return f'<span class="severity-badge severity-{_safe(severity)}"><span aria-hidden="true">{icon}</span>{_safe(label)}</span>'


#: Grounded in utils/semantic_routing.py::classify_review_route -- the actual
#: decision logic behind each route -- plus agent_12's own "unclassified"
#: fallback for a review-flagged rule whose graph predates route
#: classification. Icon + one-line description turn the raw enum value into
#: something a reviewer can act on without reading source code.
_ROUTE_META: dict[str, tuple[str, str, str]] = {
    "none": ("✅", "No review needed", "No open findings — this rule is not on any review or repair queue."),
    "human_review": ("🧑‍⚖️", "Human review", "A person must confirm this: evidence conflict, ambiguity, or a policy-owner judgment call was detected."),
    "machine_repair": ("🛠️", "Machine repair", "A deterministic structural issue (contract, execution, naming, or test vectors) — repairable without human judgment."),
    "case_management": ("🗂️", "Case management", "Needs handling as a case, such as an evidence gap — doesn't require a policy-owner judgment call."),
    "unclassified": ("❔", "Unclassified", "Flagged for review, but no route classification was recorded for this rule."),
}


def _review_route_meta(route: str) -> tuple[str, str, str]:
    return _ROUTE_META.get(route, ("❔", _humanize(route) or "Unclassified", "This route is not part of the known classification set."))


def _route_badge_html(route: str) -> str:
    """A compact icon + label pill for dense contexts (the Review Queue table)."""
    icon, label, _description = _review_route_meta(route)
    route_class = _safe(route.casefold().replace(" ", "_"))
    return (
        f'<span class="status status-{route_class} route-badge">'
        f'<span class="route-icon" aria-hidden="true">{icon}</span>{_safe(route.replace("_", " "))}</span>'
        f'<div class="muted route-badge-label">{_safe(label)}</div>'
    )


def _route_card_html(route: str, *, has_hold: bool, reason_items: Sequence[str]) -> str:
    """The fuller review-route presentation for the Rule Explorer's own column:
    an icon-led route badge, a plain-language description of what the route
    actually means, whether it carries a quality hold, and the specific
    reasons in a styled (not bare-<ul>) callout instead of a plain list."""
    icon, label, description = _review_route_meta(route)
    route_class = _safe(route.casefold().replace(" ", "_"))
    reasons_html = "".join(f'<li>{_safe(item)}</li>' for item in reason_items) or "<li>No review reason recorded.</li>"
    hold_class = "route-hold-yes" if has_hold else "route-hold-no"
    hold_text = "Quality hold" if has_hold else "No quality hold"
    return (
        f'<div class="route-card route-{route_class}">'
        f'<div class="route-head"><span class="route-icon" aria-hidden="true">{icon}</span>'
        f'<div><span class="status status-{route_class}">{_safe(route.replace("_", " "))}</span>'
        f'<div class="route-title">{_safe(label)}</div></div></div>'
        f'<p class="route-desc">{_safe(description)}</p>'
        f'<span class="route-hold {hold_class}">{hold_text}</span>'
        f'<details class="route-reasons"><summary>Why ({len(reason_items)})</summary><ul class="reason-list">{reasons_html}</ul></details>'
        f'</div>'
    )


def _source_chunks(organized_dir: Path | None) -> tuple[dict[tuple[str, str], Mapping[str, Any]], list[Mapping[str, Any]]]:
    if organized_dir is None or not organized_dir.exists():
        return {}, []
    try:
        index = source_document_index(str(organized_dir))
    except (OSError, ValueError):
        return {}, []
    chunks = [dict(chunk) for chunk in _list(index.get("chunks")) if isinstance(chunk, Mapping)]
    lookup: dict[tuple[str, str], Mapping[str, Any]] = {}
    for chunk in chunks:
        lookup[(str(chunk.get("chunk_path", "")), str(chunk.get("section_id", "")))] = chunk
        lookup.setdefault((str(chunk.get("chunk_path", "")), ""), chunk)
    return lookup, chunks


def _model_info(models_dir: Path) -> dict[str, Any]:
    info: dict[str, Any] = {}
    for filename, kind in (("compliance_decisions.dmn", "DMN"), ("compliance_workflows.bpmn", "BPMN"), ("compliance_reviews.cmmn", "CMMN")):
        path = models_dir / filename
        record: dict[str, Any] = {"kind": kind, "file": filename, "exists": path.exists(), "rule_ids": [], "element_count": 0}
        if path.exists():
            try:
                root = ET.fromstring(path.read_bytes())
                record["element_count"] = sum(1 for _ in root.iter())
                for element in root.iter():
                    for key, value in element.attrib.items():
                        if key.endswith("}ruleId") and value:
                            record["rule_ids"].append(str(value))
                record["rule_ids"] = sorted(set(record["rule_ids"]))
            except (OSError, ET.ParseError):
                record["parse_error"] = True
        info[kind] = record
    return info


# ---------------------------------------------------------------------------
# BPMN/DMN/CMMN structural parsing -- reads the actual XML shape emitted by
# utils/executable_models.py::build_graph_dmn/build_dags_bpmn and
# utils/semantic_artifacts.py::build_review_cmmn, so the "beautiful" diagrams
# below are real projections of the generated model, never invented layout.
# Tag matching is namespace-agnostic (local-name only, matching the existing
# `key.endswith("}ruleId")` style above) so it tolerates the exact xmlns
# string differing across generator versions/fixtures.
# ---------------------------------------------------------------------------

def _local_tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _children_by_tag(element: ET.Element, tag: str) -> list[ET.Element]:
    return [child for child in element if _local_tag(child) == tag]


def _first_child_by_tag(element: ET.Element, tag: str) -> ET.Element | None:
    found = _children_by_tag(element, tag)
    return found[0] if found else None


def _ctc_attr(element: ET.Element, name: str) -> str:
    """Read a ctc:-namespaced audit attribute regardless of its exact xmlns string."""
    for key, value in element.attrib.items():
        if key == name or key.endswith("}" + name):
            return value
    return ""


def _text_of(element: ET.Element | None) -> str:
    return (element.text or "").strip() if element is not None else ""


def _parse_xml_root(path: Path) -> ET.Element | None:
    try:
        return ET.fromstring(path.read_bytes())
    except (OSError, ET.ParseError):
        return None


def _parse_dmn_decisions(path: Path) -> list[dict[str, Any]]:
    """One entry per <decision>: its decisionTable's input/output columns
    (name + type) and the single generated rule row's FEEL expressions, in
    column order -- everything needed to render a real decision table."""
    root = _parse_xml_root(path) if path.exists() else None
    if root is None:
        return []
    decisions = []
    for decision in _children_by_tag(root, "decision"):
        table = _first_child_by_tag(decision, "decisionTable")
        inputs: list[dict[str, str]] = []
        outputs: list[dict[str, str]] = []
        input_entries: list[str] = []
        output_entries: list[str] = []
        if table is not None:
            for inp in _children_by_tag(table, "input"):
                expr = _first_child_by_tag(inp, "inputExpression")
                inputs.append({
                    "name": _text_of(_first_child_by_tag(expr, "text")) if expr is not None else "",
                    "type": (expr.get("typeRef") if expr is not None else "") or "string",
                })
            for out in _children_by_tag(table, "output"):
                outputs.append({"name": out.get("name") or "", "type": out.get("typeRef") or "string"})
            rule_row = _first_child_by_tag(table, "rule")
            if rule_row is not None:
                input_entries = [_text_of(_first_child_by_tag(entry, "text")) for entry in _children_by_tag(rule_row, "inputEntry")]
                output_entries = [_text_of(_first_child_by_tag(entry, "text")) for entry in _children_by_tag(rule_row, "outputEntry")]
        decisions.append({
            "rule_id": _ctc_attr(decision, "ruleId") or decision.get("id") or "",
            "name": decision.get("name") or "",
            "hit_policy": table.get("hitPolicy") if table is not None else "",
            "requires_review": _ctc_attr(decision, "requiresReview"),
            "grounding_status": _ctc_attr(decision, "groundingStatus"),
            "source_ref": _ctc_attr(decision, "sourceRef"),
            "inputs": inputs, "outputs": outputs,
            "input_entries": input_entries, "output_entries": output_entries,
        })
    return decisions


# XML tag -> internal node kind, for icon/shape lookup in _bpmn_flow_html.
_BPMN_TASK_KIND = {
    "businessRuleTask": "business_rule_task", "userTask": "user_task", "serviceTask": "service_task",
    "sendTask": "send_task", "receiveTask": "receive_task",
}


def _parse_bpmn_processes(path: Path) -> list[dict[str, Any]]:
    """One entry per <process>: its nodes (start event, ordered tasks, end
    event) in document order. sequenceFlow elements are intentionally not
    resolved into a graph -- the generator always emits a strict linear
    chain in document order (see build_dags_bpmn's `previous` chaining), so
    document order already *is* the process order, with no invented layout."""
    root = _parse_xml_root(path) if path.exists() else None
    if root is None:
        return []
    processes = []
    for process in _children_by_tag(root, "process"):
        nodes: list[dict[str, Any]] = []
        for child in process:
            tag = _local_tag(child)
            if tag == "startEvent":
                nodes.append({"kind": "start", "name": child.get("name") or "Start"})
            elif tag == "endEvent":
                nodes.append({"kind": "end", "name": child.get("name") or "End"})
            elif tag in _BPMN_TASK_KIND:
                nodes.append({
                    "kind": _BPMN_TASK_KIND[tag],
                    "name": child.get("name") or tag,
                    "decision_ref": _ctc_attr(child, "decisionRef") or None,
                })
        processes.append({
            "rule_id": _ctc_attr(process, "ruleId") or process.get("id") or "",
            "name": process.get("name") or "",
            "trigger_event": _ctc_attr(process, "triggerEvent"),
            "actor_role": _ctc_attr(process, "actorRole"),
            "source_ref": _ctc_attr(process, "sourceRef"),
            "nodes": nodes,
        })
    return processes


def _parse_cmmn_cases(path: Path) -> list[dict[str, Any]]:
    """One entry per <case>: its casePlanModel's plan items (humanTask,
    milestone). planItem elements only reference these by id and add no
    displayable information. Deliberately not drawn as a sequence: CMMN
    case items are not ordered (see ARCHITECTURE.md's note that the real
    generator emits no sentry/entryCriterion gating)."""
    root = _parse_xml_root(path) if path.exists() else None
    if root is None:
        return []
    cases = []
    for case in _children_by_tag(root, "case"):
        plan = _first_child_by_tag(case, "casePlanModel")
        items: list[dict[str, str]] = []
        if plan is not None:
            for child in plan:
                tag = _local_tag(child)
                if tag == "humanTask":
                    items.append({"kind": "human_task", "name": child.get("name") or "Human task"})
                elif tag == "milestone":
                    items.append({"kind": "milestone", "name": child.get("name") or "Milestone"})
        cases.append({
            "rule_id": _ctc_attr(case, "ruleId") or case.get("id") or "",
            "name": case.get("name") or "",
            "review_route": _ctc_attr(case, "reviewRoute"),
            "plan_name": plan.get("name") if plan is not None else "",
            "items": items,
        })
    return cases


def _dmn_table_html(decision: Mapping[str, Any]) -> str:
    """A real DMN decision table: input columns, output columns (visually
    distinguished), and the one generated rule row's FEEL expressions."""
    inputs = list(decision.get("inputs") or [])
    outputs = list(decision.get("outputs") or [])
    if not inputs and not outputs:
        return '<div class="model-diagram-empty">No decision table structure was generated for this rule.</div>'
    input_entries = list(decision.get("input_entries") or [])
    output_entries = list(decision.get("output_entries") or [])
    header = "".join(f'<th class="dmn-col-input">{_safe(item.get("name") or "?")}<span class="dmn-col-type">{_safe(item.get("type") or "")}</span></th>' for item in inputs)
    header += "".join(f'<th class="dmn-col-output">{_safe(item.get("name") or "?")}<span class="dmn-col-type">{_safe(item.get("type") or "")}</span></th>' for item in outputs)
    cells = "".join(f'<td class="dmn-col-input"><code>{_safe(value)}</code></td>' for value in input_entries)
    cells += "".join(f'<td class="dmn-col-output"><code>{_safe(value)}</code></td>' for value in output_entries)
    return (
        '<div class="dmn-table-wrap">'
        f'<div class="dmn-table-meta"><span class="status status-dmn">{_safe(decision.get("hit_policy") or "UNIQUE")}</span><span class="muted">hit policy</span></div>'
        f'<div class="table-wrap"><table class="dmn-table"><thead><tr>{header}</tr></thead><tbody><tr>{cells}</tr></tbody></table></div>'
        "</div>"
    )


_BPMN_ICONS = {
    "start": "▶", "end": "■", "business_rule_task": "📐", "user_task": "🧑",
    "service_task": "⚙️", "send_task": "📤", "receive_task": "📥",
}


def _bpmn_flow_html(process: Mapping[str, Any]) -> str:
    """A left-to-right BPMN flow: shaped nodes connected by arrows, in the
    generator's own document order (see _parse_bpmn_processes)."""
    nodes = list(process.get("nodes") or [])
    if not nodes:
        return '<div class="model-diagram-empty">No ordered workflow steps were generated for this rule.</div>'
    parts = []
    for index, node in enumerate(nodes):
        kind = str(node.get("kind") or "")
        icon = _BPMN_ICONS.get(kind, "▪")
        shape = "bpmn-node-event" if kind in ("start", "end") else "bpmn-node-task"
        sub = '<span class="bpmn-node-sub">DMN-backed</span>' if node.get("decision_ref") else ""
        # Node and its outgoing arrow share one flex item so a wide flow
        # wraps between steps, never orphaning an arrow from its node.
        arrow = '<div class="bpmn-arrow" aria-hidden="true">→</div>' if index < len(nodes) - 1 else ""
        parts.append(
            f'<div class="bpmn-step"><div class="bpmn-node {shape}"><span class="bpmn-node-icon" aria-hidden="true">{icon}</span>'
            f'<span class="bpmn-node-label">{_safe(node.get("name") or kind.replace("_", " ").title())}</span>{sub}</div>{arrow}</div>'
        )
    return f'<div class="bpmn-flow">{"".join(parts)}</div>'


_CMMN_ICONS = {"human_task": "🧑‍💼", "milestone": "🏁"}


def _cmmn_plan_html(case: Mapping[str, Any]) -> str:
    """The case plan's items as unordered cards -- CMMN case items carry no
    forced sequence, so no arrows are drawn between them (see the docstring
    on _parse_cmmn_cases)."""
    items = list(case.get("items") or [])
    if not items:
        return '<div class="model-diagram-empty">No case plan items were generated for this rule.</div>'
    cards = "".join(
        f'<div class="cmmn-item cmmn-{_safe(item.get("kind") or "item")}">'
        f'<span class="cmmn-item-icon" aria-hidden="true">{_CMMN_ICONS.get(item.get("kind"), "▪")}</span>'
        f'<div><div class="cmmn-item-kind">{_safe(str(item.get("kind") or "").replace("_", " ").title())}</div>'
        f'<div class="cmmn-item-name">{_safe(item.get("name") or "")}</div></div></div>'
        for item in items
    )
    return f'<div class="cmmn-plan">{cards}</div>'


def _dependency_graph_layout(edges: Sequence[Mapping[str, Any]], rule_ids: Sequence[str] = ()) -> dict[str, Any]:
    """Build a deterministic directed, shortest-distance dependency layout.

    ``source_rule_id`` remains the tail and ``target_rule_id`` remains the
    arrow head exactly as emitted by the dependency contract.  Degree layers
    are shortest directed distances from zero-indegree roots.  A cyclic or
    otherwise rootless component gets a deterministic degree-0 anchor so that
    every node remains visible without inventing a direction.
    """
    nodes = {str(rule_id).strip() for rule_id in rule_ids if str(rule_id).strip()}
    clean_edges: list[dict[str, str]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    outgoing: dict[str, set[str]] = defaultdict(set)
    indegree: Counter[str] = Counter()
    connected: set[str] = set()
    for raw_edge in edges:
        if not isinstance(raw_edge, Mapping):
            continue
        source = str(raw_edge.get("source_rule_id") or "").strip()
        target = str(raw_edge.get("target_rule_id") or "").strip()
        if not source or not target:
            continue
        dependency_type = str(raw_edge.get("dependency_type") or "unknown").strip() or "unknown"
        key = (source, target, dependency_type)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        nodes.update((source, target))
        connected.update((source, target))
        outgoing[source].add(target)
        indegree[target] += 1
        clean_edges.append({"source_rule_id": source, "target_rule_id": target, "dependency_type": dependency_type})

    roots = sorted(node for node in nodes if indegree[node] == 0)
    degrees: dict[str, int] = {}
    queue: list[str] = []

    def assign_component(anchor: str) -> None:
        if anchor in degrees:
            return
        degrees[anchor] = 0
        queue.append(anchor)
        cursor = len(queue) - 1
        while cursor < len(queue):
            source = queue[cursor]
            cursor += 1
            for target in sorted(outgoing.get(source, ())):
                candidate = degrees[source] + 1
                if target not in degrees or candidate < degrees[target]:
                    degrees[target] = candidate
                    queue.append(target)

    for root in roots:
        assign_component(root)
    fallback_roots: list[str] = []
    for node in sorted(nodes):
        if node not in degrees:
            fallback_roots.append(node)
            assign_component(node)

    layers: dict[int, list[str]] = defaultdict(list)
    for node, degree in degrees.items():
        layers[degree].append(node)
    ordered_layers = {degree: sorted(values) for degree, values in sorted(layers.items())}
    return {
        "nodes": sorted(nodes),
        "edges": sorted(clean_edges, key=lambda edge: (edge["source_rule_id"], edge["target_rule_id"], edge["dependency_type"])),
        "degrees": degrees,
        "layers": ordered_layers,
        "roots": roots,
        "fallback_roots": fallback_roots,
        "isolated_nodes": sorted(nodes - connected),
    }


_DEGREE_BUCKET_ORDER = ("0", "1–2", "3–5", "6–10", "11+")


def _rule_connectivity(edges: Sequence[Mapping[str, Any]], rule_ids: Sequence[str]) -> dict[str, Any]:
    """True graph-theoretic in+out degree per rule -- distinct from the BFS
    'degree lane' (shortest distance from a zero-indegree root) that
    ``_dependency_graph_layout`` computes for visual layout. That's a depth,
    not a connectivity count; the two are easy to conflate but answer
    different questions ("how central is this rule" vs. "how deep in the
    chain is it"), so this is a separate, dedicated pass over the same edges."""
    degree: Counter[str] = Counter()
    for edge in edges:
        if not isinstance(edge, Mapping):
            continue
        source = str(edge.get("source_rule_id") or "").strip()
        target = str(edge.get("target_rule_id") or "").strip()
        if source:
            degree[source] += 1
        if target:
            degree[target] += 1
    all_ids = sorted({str(rid).strip() for rid in rule_ids if str(rid).strip()})
    buckets: Counter[str] = Counter()
    for rid in all_ids:
        d = degree.get(rid, 0)
        bucket = "0" if d == 0 else "1–2" if d <= 2 else "3–5" if d <= 5 else "6–10" if d <= 10 else "11+"
        buckets[bucket] += 1
    most_connected = sorted(((rid, count) for rid, count in degree.items()), key=lambda item: (-item[1], item[0]))[:10]
    isolated = [rid for rid in all_ids if degree.get(rid, 0) == 0]
    return {
        "degree_buckets": {bucket: buckets.get(bucket, 0) for bucket in _DEGREE_BUCKET_ORDER},
        "most_connected": most_connected,
        "isolated_rule_ids": isolated,
    }


def _dependency_graph_svg(layout: Mapping[str, Any]) -> str:
    """Render a self-contained directed SVG with degree lanes and arrowheads."""
    layers = {int(degree): list(nodes) for degree, nodes in _mapping(layout.get("layers")).items()}
    nodes = [str(node) for node in layout.get("nodes", [])]
    edges = [edge for edge in layout.get("edges", []) if isinstance(edge, Mapping)]
    degrees = {str(node): int(degree) for node, degree in _mapping(layout.get("degrees")).items()}
    if not nodes:
        return '<div class="dependency-graph-empty">No dependency nodes were reported.</div>'

    node_width, node_height = 188, 48
    layer_gap, row_gap = 176, 18
    left, top, bottom = 34, 48, 34
    max_rows = max((len(values) for values in layers.values()), default=1)
    layer_count = max(layers, default=0) + 1
    width = max(520, left * 2 + layer_count * node_width + max(0, layer_count - 1) * layer_gap)
    height = max(180, top + 36 + max_rows * node_height + max(0, max_rows - 1) * row_gap + bottom)
    positions: dict[str, tuple[int, int]] = {}
    for degree, layer_nodes in layers.items():
        x = left + degree * (node_width + layer_gap)
        for row, node in enumerate(layer_nodes):
            positions[str(node)] = (x, top + 36 + row * (node_height + row_gap))

    body = [
        f'<svg class="dependency-graph-svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Directed dependency graph layered by degree">',
        '<defs><marker id="dependency-arrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L10,5 L0,10 z" fill="#4251bd"/></marker></defs>',
    ]
    for degree, layer_nodes in layers.items():
        x = left + degree * (node_width + layer_gap)
        lane_height = height - top - bottom
        body.append(f'<rect class="dependency-lane" x="{x - 16}" y="20" width="{node_width + 32}" height="{lane_height}" rx="14"/>')
        body.append(f'<text class="dependency-layer-label" x="{x + node_width / 2:.1f}" y="40" text-anchor="middle">degree {degree} · {len(layer_nodes)} nodes</text>')

    for edge in edges:
        source = str(edge.get("source_rule_id") or "")
        target = str(edge.get("target_rule_id") or "")
        if source not in positions or target not in positions:
            continue
        sx, sy = positions[source]
        tx, ty = positions[target]
        if source == target:
            start_x, start_y = sx + node_width, sy + node_height / 2
            end_x, end_y = sx + node_width, sy + node_height / 2
            path = f'M {start_x} {start_y:.1f} C {start_x + 76} {sy - 16}, {end_x + 76} {sy + node_height + 16}, {end_x} {end_y:.1f}'
        elif degrees.get(target, 0) >= degrees.get(source, 0):
            start_x, start_y = sx + node_width, sy + node_height / 2
            end_x, end_y = tx, ty + node_height / 2
            bend = max(48, (end_x - start_x) * 0.35)
            path = f'M {start_x} {start_y:.1f} C {start_x + bend:.1f} {start_y:.1f}, {end_x - bend:.1f} {end_y:.1f}, {end_x} {end_y:.1f}'
        else:
            start_x, start_y = sx, sy + node_height / 2
            end_x, end_y = tx + node_width, ty + node_height / 2
            bend = max(48, (start_x - end_x) * 0.35)
            path = f'M {start_x} {start_y:.1f} C {start_x - bend:.1f} {start_y:.1f}, {end_x + bend:.1f} {end_y:.1f}, {end_x} {end_y:.1f}'
        edge_label = f'{source} → {target} · {edge.get("dependency_type", "unknown")}'
        body.append(f'<path class="dependency-edge" d="{path}" marker-end="url(#dependency-arrow)" data-source="{_safe(source)}" data-target="{_safe(target)}"><title>{_safe(edge_label)}</title></path>')

    for node in nodes:
        x, y = positions[node]
        degree = degrees.get(node, 0)
        is_root = node in set(layout.get("roots", ())) or node in set(layout.get("fallback_roots", ()))
        fill = "#e9f7f3" if is_root else "#eef1ff"
        stroke = "#27c2a5" if is_root else "#7c83fd"
        label = node if len(node) <= 28 else node[:25] + "…"
        body.append(f'<g class="dependency-node" data-node-id="{_safe(node)}" data-degree="{degree}"><title>{_safe(node)} · degree {degree}</title><rect x="{x}" y="{y}" width="{node_width}" height="{node_height}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/><text class="dependency-node-id" x="{x + 12}" y="{y + 21}">{_safe(label)}</text><text class="dependency-node-degree" x="{x + 12}" y="{y + 37}">degree {degree}{" · root" if is_root else ""}</text></g>')
    body.append('</svg>')
    return "".join(body)


def _metric_card(label: str, value: Any, detail: str = "") -> str:
    return f'<div class="metric-card"><div class="metric-value">{_safe(value)}</div><div class="metric-label">{_safe(label)}</div><div class="metric-detail">{_safe(detail)}</div></div>'


def _percent(part: int | float, total: int | float) -> float:
    return round(float(part) / max(1.0, float(total)) * 100, 1)


def _progress_bar(label: str, value: int | float, total: int | float, color: str = "#27c2a5") -> str:
    percentage = min(100.0, max(0.0, _percent(value, total)))
    return (
        f'<div class="insight-bar-row"><div class="insight-bar-label"><span>{_safe(label)}</span>'
        f'<strong>{_safe(value)}</strong></div><div class="insight-bar-track"><span style="width:{percentage:.1f}%;background:{_safe(color)}"></span></div>'
        f'<div class="muted">{percentage:.1f}% of vocabulary</div></div>'
    )


def _bar_chart_svg(data: Sequence[tuple[str, int]], *, width: int = 560, bar_height: int = 24, gap: int = 10, color: str = "#7c83fd", max_bars: int = 14) -> str:
    """A hand-rolled horizontal bar chart -- kept as server-rendered SVG,
    matching the existing dependency-graph technique, rather than vendoring a
    JS charting library: the report's hard contract is zero external network
    calls, and a vendored library's minified source would meaningfully add
    to a file that's already several megabytes on a real run."""
    items = [(str(label), int(value)) for label, value in data][:max_bars]
    if not items:
        return '<div class="chart-empty">No data available.</div>'
    max_value = max(value for _, value in items) or 1
    label_width = 168
    plot_width = max(120, width - label_width - 56)
    height = len(items) * (bar_height + gap) + gap
    rows = []
    for index, (label, value) in enumerate(items):
        y = gap + index * (bar_height + gap)
        bar_w = max(2.0, plot_width * value / max_value)
        display = label if len(label) <= 24 else label[:21] + "…"
        rows.append(
            f'<text class="chart-label" x="{label_width - 10}" y="{y + bar_height / 2 + 4:.1f}" text-anchor="end">{_safe(display)}</text>'
            f'<rect class="chart-bar" x="{label_width}" y="{y}" width="{bar_w:.1f}" height="{bar_height}" rx="5" fill="{_safe(color)}"><title>{_safe(label)}: {value}</title></rect>'
            f'<text class="chart-value" x="{label_width + bar_w + 8:.1f}" y="{y + bar_height / 2 + 4:.1f}">{value}</text>'
        )
    return f'<svg class="chart-svg bar-chart" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Bar chart">{"".join(rows)}</svg>'


_DONUT_COLORS = ("#27c2a5", "#7c83fd", "#f3a94b", "#d85d69", "#5a8dee", "#8f6be8", "#a9b3c3")


def _donut_chart_svg(data: Sequence[tuple[str, int]], *, size: int = 176, stroke: int = 24) -> str:
    """A hand-rolled donut chart with an accompanying legend -- same
    no-external-library rationale as ``_bar_chart_svg``."""
    items = [(str(label), int(value)) for label, value in data if value]
    total = sum(value for _, value in items)
    if not items or not total:
        return '<div class="chart-empty">No data available.</div>'
    center = size / 2
    radius = center - stroke / 2
    circumference = 2 * 3.14159265358979 * radius
    segments, legend = [], []
    offset = 0.0
    for index, (label, value) in enumerate(items):
        color = _DONUT_COLORS[index % len(_DONUT_COLORS)]
        fraction = value / total
        dash = fraction * circumference
        segments.append(
            f'<circle class="chart-donut-seg" cx="{center}" cy="{center}" r="{radius:.1f}" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-dasharray="{dash:.2f} {max(0.0, circumference - dash):.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 {center} {center})"><title>{_safe(label)}: {value} ({fraction * 100:.1f}%)</title></circle>'
        )
        legend.append(f'<li><span class="chart-legend-dot" style="background:{color}"></span>{_safe(label.replace("_", " "))} <strong>{value}</strong><span class="muted">({fraction * 100:.1f}%)</span></li>')
        offset += dash
    svg = (
        f'<svg class="chart-svg donut-chart" width="{size}" height="{size}" viewBox="0 0 {size} {size}" role="img" aria-label="Donut chart">'
        f'{"".join(segments)}<text class="chart-donut-total" x="{center}" y="{center - 3}" text-anchor="middle">{total}</text>'
        f'<text class="chart-donut-caption" x="{center}" y="{center + 15}" text-anchor="middle">total</text></svg>'
    )
    return f'<div class="donut-wrap">{svg}<ul class="chart-legend">{"".join(legend)}</ul></div>'


def _validate_report_html(document: str, rule_ids: Sequence[str], source_anchors: Sequence[str]) -> None:
    """Validate the non-network, single-document report contract."""
    required = (
        '<!doctype html>', 'id="report-data"',
        'data-tab="overview"', 'data-tab="vocabulary"', 'data-tab="rules"', 'data-tab="dependencies"', 'data-tab="review"', 'data-tab="sources"',
        'id="concept-search"', 'id="concept-grid"', 'id="fact-types"',
        'dependency-graph-shell', 'dependency-graph-scroll', 'id="dep-side-panel"',
        'model-badges', 'severity-badge', 'trace-path',
    )
    missing = [marker for marker in required if marker not in document]
    if missing:
        raise ValueError("business report missing required sections: " + ", ".join(missing))
    if re.search(r"<(?:script|link)[^>]+(?:src|href)=['\"](?:https?:|//)", document, flags=re.IGNORECASE):
        raise ValueError("business report contains an external asset reference")
    for rule_id in rule_ids:
        if f'id="rule-{_safe(_slug(rule_id))}"' not in document:
            raise ValueError(f"business report missing rule anchor: {rule_id}")
    for anchor in source_anchors:
        if f'id="{_safe(anchor)}"' not in document:
            raise ValueError(f"business report missing source anchor: {anchor}")


def _source_block(anchor: str, ref: Mapping[str, Any], text: str) -> str:
    path = ref.get("chunk_path") or ref.get("document") or "Unresolved source"
    section = ref.get("section_id") or ref.get("section") or ""
    label = f"{path}{('#' + str(section)) if section else ''}"
    return f'<article class="source-card" id="{_safe(anchor)}"><h4>{_safe(label)}</h4><div class="source-meta">{_safe(ref.get("evidence_field", "source"))} · offsets { _safe(ref.get("start_offset", "?")) }–{ _safe(ref.get("end_offset", "?")) }</div><pre>{_safe(text or "No source text was available for this pointer.")}</pre></article>'


def _model_badges_html(rid: str, model_rule_ids: Mapping[str, set[str]]) -> str:
    """Which of DMN/BPMN/CMMN exist for this rule -- always visible (not just
    linked) so a reviewer can tell at a glance what's available without
    expanding the row. Greyed badges make an absence as legible as a presence."""
    badges = []
    for kind in ("DMN", "BPMN", "CMMN"):
        has = rid in model_rule_ids.get(kind, ())
        state = "yes" if has else "no"
        title = f"{kind} " + ("generated for this rule" if has else "not generated for this rule")
        badges.append(f'<span class="model-badge model-badge-{state}" title="{_safe(title)}">{kind}</span>')
    return f'<div class="model-badges">{"".join(badges)}</div>'


def _rule_model_diagrams_html(rid: str, model_lookup: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> str:
    """Render this rule's own DMN decision table / BPMN flow / CMMN plan
    inline, reusing the existing per-kind diagram renderers -- the projection
    itself is unchanged, only where it's shown moves (into the rule row that
    already links out to it, instead of a separate Models tab nothing else
    points into). Rendered inside a closed-by-default <details>, so it only
    costs bytes, not paint time, for rows a reviewer never opens."""
    renderers = {"DMN": _dmn_table_html, "BPMN": _bpmn_flow_html, "CMMN": _cmmn_plan_html}
    blocks = []
    for kind, renderer in renderers.items():
        item = model_lookup.get(kind, {}).get(rid)
        if item is None:
            continue
        blocks.append(f'<div class="rule-model-block"><div class="rule-model-kind">{_safe(kind)}</div>{renderer(item)}</div>')
    if not blocks:
        return '<div class="model-diagram-empty">No executable model (DMN/BPMN/CMMN) was generated for this rule.</div>'
    return f'<div class="rule-model-diagrams">{"".join(blocks)}</div>'


def _traceability_html(
    rule: Mapping[str, Any],
    rid: str,
    source_anchors: Sequence[str],
    model_rule_ids: Mapping[str, set[str]],
) -> str:
    """Source document -> passage -> this rule -> related entities ->
    dependencies -> executable model, as one explicit breadcrumb, built
    entirely from data already loaded for other tabs (source references,
    related_entities, dependency edges, model membership) -- no new fields,
    just a single first-class path through fields that were previously only
    reachable by switching tabs."""
    refs = _rule_references(rule)
    if refs and source_anchors:
        ref, anchor = refs[0], source_anchors[0]
        path = ref.get("chunk_path") or ref.get("document") or "Unresolved source"
        section = ref.get("section_id") or ref.get("section") or ""
        excerpt = str(ref.get("source_text") or ref.get("quote") or "")[:220].strip()
        excerpt_html = f'<span class="trace-node-excerpt">“{_safe(excerpt)}{"…" if len(str(ref.get("source_text") or ref.get("quote") or "")) > 220 else ""}”</span>' if excerpt else ""
        more = f'<span class="muted trace-more">+{len(source_anchors) - 1} more source pointer(s)</span>' if len(source_anchors) > 1 else ""
        source_step = (
            f'<a class="trace-node trace-source" href="#{_safe(anchor)}">'
            f'<span class="trace-node-kind">Source document</span>'
            f'<span class="trace-node-label">{_safe(path)}{("#" + _safe(str(section))) if section else ""}</span>'
            f'{excerpt_html}</a>{more}'
        )
    else:
        source_step = '<span class="trace-node trace-empty">No source pointer</span>'

    entity_names = list(dict.fromkeys(str(value) for value in _list(rule.get("related_entities")) if value))
    entities_html = "".join(f'<span class="trace-chip">{_safe(name)}</span>' for name in entity_names[:12]) or '<span class="trace-chip trace-chip-empty">None recorded</span>'
    if len(entity_names) > 12:
        entities_html += f'<span class="muted trace-more">+{len(entity_names) - 12} more</span>'

    dep_ids = list(dict.fromkeys(
        str(dep.get("depends_on_rule") or dep.get("target_rule_id") or "")
        for dep in _list(rule.get("dependencies")) if isinstance(dep, Mapping)
    ))
    dep_ids = [d for d in dep_ids if d]
    deps_html = "".join(f'<a class="trace-chip trace-chip-link" href="#rule-{_safe(_slug(d))}">{_safe(d)}</a>' for d in dep_ids[:12]) or '<span class="trace-chip trace-chip-empty">No dependencies</span>'
    if len(dep_ids) > 12:
        deps_html += f'<span class="muted trace-more">+{len(dep_ids) - 12} more</span>'

    model_kinds = [kind for kind in ("DMN", "BPMN", "CMMN") if rid in model_rule_ids.get(kind, ())]
    model_html = "".join(f'<span class="trace-chip trace-chip-model">{kind}</span>' for kind in model_kinds) or '<span class="trace-chip trace-chip-empty">No executable model</span>'

    steps = [
        source_step,
        f'<span class="trace-node"><span class="trace-node-kind">This rule</span><span class="trace-node-label">{_safe(rid)}</span></span>',
        f'<span class="trace-node"><span class="trace-node-kind">Related entities</span><span class="trace-chip-row">{entities_html}</span></span>',
        f'<span class="trace-node"><span class="trace-node-kind">Dependencies</span><span class="trace-chip-row">{deps_html}</span></span>',
        f'<span class="trace-node"><span class="trace-node-kind">Executable model</span><span class="trace-chip-row">{model_html}</span></span>',
    ]
    arrow = '<span class="trace-arrow" aria-hidden="true">→</span>'
    trace_steps = arrow.join(f'<div class="trace-step">{step}</div>' for step in steps)
    return f'<div class="trace-path">{trace_steps}</div>'


def _rule_row(
    rule: Mapping[str, Any],
    source_anchors: Sequence[str],
    model_rule_ids: Mapping[str, set[str]] = {},
    model_item_lookup: Mapping[str, Mapping[str, Mapping[str, Any]]] = {},
) -> str:
    rid = str(rule.get("rule_id") or "unidentified")
    category, subcategory = _category(rule)
    review = bool(rule.get("requires_review", False))
    review_route = str(_mapping(rule.get("review_route")).get("route") or ("unclassified" if review else "none"))
    grounding = _mapping(rule.get("grounding"))
    grounding_status = str(grounding.get("status") or rule.get("extraction_status") or "unknown")
    status = "review_required" if review else ("verified" if grounding_status == "certified" else grounding_status)
    status_label = "Quality hold" if review else ("Verified" if status == "verified" else status.replace("_", " ").title())
    grounding_label = "Grounding certified" if grounding_status == "certified" else ("Grounding not certified" if grounding_status == "failed" else f"Grounding {grounding_status}")
    confidence = _confidence(rule)
    confidence_text = f"{confidence:.1f}%" if confidence is not None else "—"
    confidence_source = _confidence_source(rule)
    reason_items = _review_reasons(rule)
    refs = " ".join(f'<a class="evidence-link" href="#{_safe(anchor)}">Evidence {index + 1}</a>' for index, anchor in enumerate(source_anchors)) or '<span class="muted">Unresolved source</span>'
    grounding_detail = _grounding_summary(rule, grounding_status)
    has_dmn = "true" if rid in model_rule_ids.get("DMN", ()) else "false"
    has_bpmn = "true" if rid in model_rule_ids.get("BPMN", ()) else "false"
    has_cmmn = "true" if rid in model_rule_ids.get("CMMN", ()) else "false"
    details_body = (
        _traceability_html(rule, rid, source_anchors, model_rule_ids)
        + _formal_logic_html(rule)
        + _rule_model_diagrams_html(rid, model_item_lookup)
    )
    return f'''<tr id="rule-{_safe(_slug(rid))}" class="rule-row" data-category="{_safe(category)}" data-status="{_safe(status)}" data-route="{_safe(review_route)}" data-review="{str(review).lower()}" data-has-dmn="{has_dmn}" data-has-bpmn="{has_bpmn}" data-has-cmmn="{has_cmmn}" data-search="{_safe((rid + ' ' + str(rule.get('rule_name', '')) + ' ' + _rule_statement(rule) + ' ' + category + ' ' + subcategory).casefold())}">
      <td><a href="#rule-{_safe(_slug(rid))}">{_safe(rid)}</a><div class="muted">{_safe(rule.get('rule_name') or 'Untitled rule')}</div>{_model_badges_html(rid, model_rule_ids)}</td>
      <td>{_safe(category)}<div class="muted">{_safe(subcategory)}</div></td>
      <td>{_safe(_rule_statement(rule))}</td>
      <td><details class="logic-details"><summary><span class="logic-summary">IF / THEN</span><span class="muted">contract, traceability & models</span></summary>{details_body}</details></td>
      <td><div class="status-stack"><span class="status status-{_safe(status.casefold().replace(' ', '_'))}">{_safe(status_label)}</span><span class="status status-grounding-{_safe(grounding_status.casefold().replace(' ', '_'))}" title="Underlying claim-level grounding verdict">{_safe(grounding_label)}</span></div><div class="confidence-score"><strong>{confidence_text}</strong><span class="muted">{_safe(_confidence_source_label(confidence_source))}</span></div><div class="muted">{_safe(grounding_detail)}</div></td>
      <td>{_route_card_html(review_route, has_hold=review, reason_items=reason_items)}</td>
      <td>{refs}</td>
    </tr>'''


def generate(
    graph_file: Path,
    dags_file: Path | None,
    models_dir: Path | None,
    output_dir: Path,
    organized_dir: Path | None = None,
) -> dict[str, Any]:
    """Generate the report and return its machine-readable manifest."""
    graph = json.loads(graph_file.read_text(encoding="utf-8"))
    if not isinstance(graph, Mapping):
        raise ValueError("optimized graph must be a JSON object")
    dags: Mapping[str, Any] = {}
    if dags_file and dags_file.exists():
        loaded = json.loads(dags_file.read_text(encoding="utf-8"))
        dags = loaded if isinstance(loaded, Mapping) else {}
    models_dir = models_dir or graph_file.parent
    profile_path = models_dir / "semantic_vocabulary_profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else build_sbvr_profile(graph)
    concepts = _concepts(graph, profile)
    rules = [dict(rule) for rule in _list(graph.get("business_rules")) if isinstance(rule, Mapping)]
    decision_variables = _decision_variables(graph)
    chunks, chunk_list = _source_chunks(organized_dir)
    source_blocks: dict[str, str] = {}
    rule_sources: dict[str, list[str]] = {}
    for rule in rules:
        rid = str(rule.get("rule_id") or "unidentified")
        anchors: list[str] = []
        for ref in _rule_references(rule):
            anchor = _source_anchor(ref)
            anchors.append(anchor)
            if anchor not in source_blocks:
                source_blocks[anchor] = _source_block(anchor, ref, _source_text(ref, chunks))
        rule_sources[rid] = anchors

    concept_refs: dict[str, list[str]] = defaultdict(list)
    for concept in concepts:
        for ref in _references(concept.get("source_evidence")):
            anchor = _source_anchor(ref)
            if anchor not in source_blocks:
                source_blocks[anchor] = _source_block(anchor, ref, _source_text(ref, chunks))
            concept_refs[str(concept.get("concept_id"))].append(anchor)

    fact_types = [fact for fact in _list(profile.get("fact_types")) if isinstance(fact, Mapping)]
    fact_refs: dict[str, list[str]] = defaultdict(list)
    for fact in fact_types:
        fact_id = str(fact.get("fact_type_id") or "")
        for ref in _references(fact.get("source_evidence")):
            anchor = _source_anchor(ref)
            if anchor not in source_blocks:
                source_blocks[anchor] = _source_block(anchor, ref, _source_text(ref, chunks))
            if fact_id:
                fact_refs[fact_id].append(anchor)

    model_info = _model_info(models_dir)
    model_rule_ids = {kind: set(record["rule_ids"]) for kind, record in model_info.items()}
    # Parsed once, up front: these feed both the per-rule inline diagrams
    # (Rule Explorer, §2 of the redesign) and the model-type distribution
    # chart (Overview) -- the removed Models tab used to parse them a second
    # time, purely for its own now-deleted section.
    model_parsers = {"DMN": _parse_dmn_decisions, "BPMN": _parse_bpmn_processes, "CMMN": _parse_cmmn_cases}
    model_items_by_kind = {
        kind: (parser(models_dir / model_info[kind]["file"]) if model_info[kind]["exists"] else [])
        for kind, parser in model_parsers.items()
    }
    model_item_lookup = {
        kind: {str(item.get("rule_id")): item for item in items if item.get("rule_id")}
        for kind, items in model_items_by_kind.items()
    }
    edges = dependency_edges(graph)
    rule_ids_all = [str(rule.get("rule_id") or "") for rule in rules]
    dependency_layout = _dependency_graph_layout(edges, rule_ids_all)
    connectivity = _rule_connectivity(edges, rule_ids_all)
    max_dependency_depth = max(dependency_layout["layers"], default=0)
    cyclic_component_count = len(dependency_layout.get("fallback_roots", []))
    rule_adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in dependency_layout["edges"]:
        source, target = edge["source_rule_id"], edge["target_rule_id"]
        if source == target:
            continue
        rule_adjacency[source].add(target)
        rule_adjacency[target].add(source)
    categories = Counter(_category(rule)[0] for rule in rules)
    review_count = sum(bool(rule.get("requires_review")) for rule in rules)
    human_review_count = sum(bool(_mapping(rule.get("review_route")).get("human_review_required")) for rule in rules)
    route_counts = Counter(str(_mapping(rule.get("review_route")).get("route") or ("unclassified" if rule.get("requires_review") else "none")) for rule in rules)
    nonhuman_quality_hold_count = sum(
        bool(rule.get("requires_review"))
        and not bool(_mapping(rule.get("review_route")).get("human_review_required"))
        for rule in rules
    )
    source_pointer_count = sum(bool(_rule_references(rule)) for rule in rules)
    grounded_count = sum(str(_mapping(rule.get("grounding")).get("status")) == "certified" for rule in rules)
    confidence_values = [value for rule in rules if (value := _confidence(rule)) is not None]
    confidence_buckets = Counter("90–100%" if value >= 90 else "75–89%" if value >= 75 else "50–74%" if value >= 50 else "0–49%" for value in confidence_values)
    confidence_sources = Counter(_confidence_source(rule) for rule in rules)
    grounding_status_counts = Counter(str(_mapping(rule.get("grounding")).get("status") or "not_reported") for rule in rules)
    grounding_dimension_metrics: dict[str, dict[str, Any]] = {}
    for dimension in ("core_rule", "enrichment", "contract"):
        statuses = Counter(
            str(_mapping(_mapping(_mapping(rule.get("grounding")).get("dimensions")).get(dimension)).get("status") or "not_reported")
            for rule in rules
        )
        grounding_dimension_metrics[dimension] = {
            "status_counts": dict(sorted(statuses.items())),
            "certified_count": statuses.get("certified", 0),
            "failed_count": statuses.get("failed", 0),
            "hold_rate": _percent(statuses.get("failed", 0), len(rules)),
        }
    relationship_statuses = Counter(
        str(_mapping(rule.get("grounding")).get("relationship_status") or "not_reported")
        for rule in rules
    )
    grounding_dimension_metrics["relationship"] = {
        "status_counts": dict(sorted(relationship_statuses.items())),
        "certified_count": relationship_statuses.get("supported", 0),
        "failed_count": relationship_statuses.get("failed", 0),
        "hold_rate": _percent(relationship_statuses.get("failed", 0), len(rules)),
    }
    grounding_claim_counts: Counter[str] = Counter()
    for rule in rules:
        grounding_claim_counts.update({
            str(key): int(value)
            for key, value in _mapping(_mapping(rule.get("grounding")).get("counts")).items()
            if isinstance(value, (int, float))
        })
    grounding_claim_total = sum(grounding_claim_counts.values())
    quarantined_claim_count = sum(
        len(_list(rule.get("quarantined_claims"))) for rule in rules
    )
    rules_with_quarantined_claims = sum(
        bool(_list(rule.get("quarantined_claims"))) for rule in rules
    )
    unresolved = sum(1 for rule in rules if _review_reasons(rule))
    source_documents = {str(ref.get("chunk_path") or ref.get("document") or "").split("/")[0] for rule in rules for ref in _rule_references(rule) if ref.get("chunk_path") or ref.get("document")}
    concept_supported = len(concepts)
    concept_ids = {str(concept.get("concept_id")) for concept in concepts}
    concept_kind_counts = Counter(str(concept.get("concept_kind") or "unresolved") for concept in concepts)
    concept_rule_usage: Counter[str] = Counter()
    for rule in rules:
        referenced = set(str(value) for value in _list(rule.get("related_entities")) if value)
        referenced.update(
            str(value) for value in (
                rule.get("source_entity"),
                rule.get("responsible_party"),
                rule.get("entity_or_relationship"),
            ) if value
        )
        for concept_id in referenced.intersection(concept_ids):
            concept_rule_usage[concept_id] += 1
    concept_fact_usage: Counter[str] = Counter()
    fact_status_counts = Counter(str(fact.get("grounding_status") or "unverified") for fact in fact_types)
    for fact in fact_types:
        for field in ("subject_concept", "object_concept"):
            concept_id = str(fact.get(field) or "")
            if concept_id in concept_ids:
                concept_fact_usage[concept_id] += 1
    concept_evidence_count = sum(bool(_references(concept.get("source_evidence"))) for concept in concepts)
    vocabulary_coverage = _percent(concept_evidence_count, concept_supported)
    concept_orphan_count = sum(
        not concept_rule_usage.get(str(concept.get("concept_id")))
        and not concept_fact_usage.get(str(concept.get("concept_id")))
        for concept in concepts
    )
    fact_grounded_count = sum(
        str(fact.get("grounding_status") or "").casefold() in {"supported", "certified"}
        for fact in fact_types
    )
    top_concepts = sorted(
        (
            {
                "concept_id": str(concept.get("concept_id")),
                "preferred_term": str(concept.get("preferred_term") or concept.get("concept_id")),
                "rule_links": concept_rule_usage.get(str(concept.get("concept_id")), 0),
                "fact_links": concept_fact_usage.get(str(concept.get("concept_id")), 0),
            }
            for concept in concepts
        ),
        key=lambda item: (-item["rule_links"], -item["fact_links"], item["preferred_term"].casefold()),
    )[:8]
    report_data = {
        "title": "Policy Logic Forge · Business Knowledge Report",
        "rule_count": len(rules), "concept_count": concept_supported,
        "review_required_count": review_count, "review_required_rate": round(review_count / max(1, len(rules)) * 100, 2),
        "human_review_count": human_review_count, "human_review_rate": round(human_review_count / max(1, len(rules)) * 100, 2),
        "quality_hold_count": review_count, "quality_hold_rate": round(review_count / max(1, len(rules)) * 100, 2),
        "nonhuman_quality_hold_count": nonhuman_quality_hold_count,
        "quarantined_claim_count": quarantined_claim_count,
        "rules_with_quarantined_claims": rules_with_quarantined_claims,
        "review_route_counts": dict(sorted(route_counts.items())),
        "source_pointer_count": source_pointer_count,
        "source_pointer_coverage_rate": round(source_pointer_count / max(1, len(rules)) * 100, 2),
        "grounded_rule_count": grounded_count, "grounding_coverage_rate": round(grounded_count / max(1, len(rules)) * 100, 2),
        "source_document_count": len(source_documents), "source_chunk_count": len(chunk_list),
        "concept_coverage_rate": vocabulary_coverage, "concept_coverage_scope": "concepts with concept-specific source evidence",
        "concept_review_count": sum(str(concept.get("concept_kind")) == "unresolved" for concept in concepts),
        "concept_kind_counts": dict(sorted(concept_kind_counts.items())),
        "concepts_with_evidence": concept_evidence_count,
        "concept_evidence_coverage_rate": _percent(concept_evidence_count, concept_supported),
        "concept_orphan_count": concept_orphan_count,
        "fact_type_count": len(fact_types),
        "fact_type_grounded_count": fact_grounded_count,
        "fact_type_grounding_rate": _percent(fact_grounded_count, len(fact_types)),
        "fact_type_status_counts": dict(sorted(fact_status_counts.items())),
        "decision_variable_count": len(decision_variables),
        "rule_local_decision_variable_count": sum(item["scope"] == "rule_local" for item in decision_variables),
        "reusable_decision_variable_count": sum(item["scope"] == "reusable" for item in decision_variables),
        "top_concepts": top_concepts,
        "unresolved_item_count": unresolved,
        "confidence_distribution": dict(sorted(confidence_buckets.items())), "confidence_source_counts": dict(sorted(confidence_sources.items())), "categories": dict(categories),
        "grounding_status_counts": dict(sorted(grounding_status_counts.items())),
        "grounding_dimensions": grounding_dimension_metrics,
        "grounding_claim_counts": dict(sorted(grounding_claim_counts.items())),
        "grounding_claim_support_rate": _percent(grounding_claim_counts.get("supported", 0), grounding_claim_total),
        "model_info": model_info, "edge_count": len(edges), "source_graph": str(graph_file),
        "model_type_counts": {kind: len(model_info[kind]["rule_ids"]) for kind in ("DMN", "BPMN", "CMMN")},
        "degree_buckets": connectivity["degree_buckets"],
        "most_connected_rules": connectivity["most_connected"],
        "isolated_rule_ids": connectivity["isolated_rule_ids"],
        "isolated_rule_count": len(connectivity["isolated_rule_ids"]),
        "max_dependency_depth": max_dependency_depth,
        "cyclic_component_count": cyclic_component_count,
        # Embedded once for the Dependencies tab's client-side interactivity
        # (click-to-highlight, side panel) -- the graph's own <g>/<path>
        # elements already carry data-node-id/data-source/data-target, so the
        # JS only needs this to build an adjacency map and render panel text
        # without any additional server-rendered markup per node.
        "dependency_edges": dependency_layout["edges"],
        "rule_summary": {
            rid: {
                "slug": _slug(rid),
                "name": str(rule.get("rule_name") or ""),
                "category": _category(rule)[0],
                "status": ("Quality hold" if rule.get("requires_review") else ("Verified" if str(_mapping(rule.get("grounding")).get("status")) == "certified" else str(_mapping(rule.get("grounding")).get("status") or "unknown").replace("_", " ").title())),
                "confidence": _confidence(rule),
                "route": str(_mapping(rule.get("review_route")).get("route") or ("unclassified" if rule.get("requires_review") else "none")),
                "severity": _review_severity(rule),
                "degree": len(rule_adjacency.get(rid, ())),
            }
            for rule in rules
            for rid in (str(rule.get("rule_id") or "unidentified"),)
        },
    }

    concept_rows = []
    for concept in concepts:
        cid = str(concept.get("concept_id"))
        kind = str(concept.get("concept_kind") or "unresolved")
        evidence_anchors = list(dict.fromkeys(concept_refs.get(cid, [])))
        refs = " ".join(f'<a class="evidence-link" href="#{_safe(anchor)}">Evidence {index + 1}</a>' for index, anchor in enumerate(evidence_anchors)) or '<span class="muted">Unresolved source</span>'
        fact_links = [
            str(fact.get("fact_type_id")) for fact in fact_types
            if str(fact.get("subject_concept") or "") == cid or str(fact.get("object_concept") or "") == cid
        ]
        relation_links = " ".join(f'<a class="evidence-link" href="#fact-{_safe(_slug(fact_id))}">{_safe(fact_id)}</a>' for fact_id in fact_links) or '<span class="muted">No fact types</span>'
        rule_links = concept_rule_usage.get(cid, 0)
        fact_link_count = concept_fact_usage.get(cid, 0)
        concept_status = "review_required" if kind == "unresolved" else "presented"
        concept_rows.append(
            f'''<article class="concept-card" id="concept-{_safe(_slug(cid))}" data-kind="{_safe(kind)}" data-evidence="{'grounded' if evidence_anchors else 'unresolved'}" data-search="{_safe((cid + ' ' + str(concept.get('preferred_term') or '') + ' ' + str(concept.get('definition') or '') + ' ' + kind).casefold())}">
              <div class="concept-card-head"><div><div class="concept-term">{_safe(concept.get("preferred_term"))}</div><div class="muted">{_safe(cid)}</div></div><span class="status status-{_safe(concept_status)}">{_safe(kind.replace('_', ' '))}</span></div>
              <p>{_safe(concept.get("definition") or "Definition not provided by the source graph.")}</p>
              <div class="concept-meta"><span><strong>{rule_links}</strong> rule links</span><span><strong>{fact_link_count}</strong> fact endpoints</span><span><strong>{len(evidence_anchors)}</strong> evidence links</span></div>
              <details><summary>Inspect concept relationships</summary><div class="concept-detail"><div><strong>Fact types</strong><div>{relation_links}</div></div><div><strong>Source evidence</strong><div>{refs}</div></div></div></details>
            </article>'''
        )
    decision_variable_rows = []
    for variable in decision_variables:
        linked_rules = " ".join(
            f'<a class="evidence-link" href="#rule-{_safe(_slug(rule_id))}">{_safe(rule_id)}</a>'
            for rule_id in variable["rule_ids"][:12]
        )
        if len(variable["rule_ids"]) > 12:
            linked_rules += f' <span class="muted">+{len(variable["rule_ids"]) - 12} more</span>'
        decision_variable_rows.append(
            f'<tr><td><code>{_safe(variable["variable_id"])}</code></td>'
            f'<td>{_safe(", ".join(variable["types"]) or "unknown")}</td>'
            f'<td>{_safe(", ".join(variable["roles"]) or "unknown")}</td>'
            f'<td><span class="status status-{_safe(variable["scope"])}">{_safe(variable["scope"].replace("_", " "))}</span></td>'
            f'<td>{linked_rules or "No linked rules"}</td></tr>'
        )
    concept_rows.append(
        f'''<article class="panel decision-variable-registry" style="grid-column:1/-1">
          <div class="eyebrow">Executable symbol registry</div>
          <h3>Decision variables are not SBVR concepts</h3>
          <p class="muted">These symbols implement predicates and outcomes. Reusable symbols may later be mapped to governed concepts, but rule-local propositions do not inflate vocabulary coverage.</p>
          <div class="insight-grid"><div class="insight-card"><h3>Total symbols</h3><div class="metric-value">{len(decision_variables)}</div></div><div class="insight-card"><h3>Rule-local</h3><div class="metric-value">{report_data["rule_local_decision_variable_count"]}</div></div><div class="insight-card"><h3>Reusable</h3><div class="metric-value">{report_data["reusable_decision_variable_count"]}</div></div></div>
          <details><summary>Explore decision-variable registry</summary><div class="table-wrap" style="margin-top:12px"><table><thead><tr><th>Variable</th><th>Types</th><th>Roles</th><th>Scope</th><th>Rules</th></tr></thead><tbody>{''.join(decision_variable_rows) or '<tr><td colspan="5">No decision variables were reported.</td></tr>'}</tbody></table></div></details>
        </article>'''
    )
    fact_rows = []
    for fact in fact_types:
        fact_id = str(fact.get("fact_type_id") or "unidentified")
        subject = str(fact.get("subject_concept") or "")
        object_concept = str(fact.get("object_concept") or "")
        fact_status = str(fact.get("grounding_status") or "unverified")
        fact_source_refs = list(dict.fromkeys(fact_refs.get(fact_id, [])))
        fact_evidence = " ".join(f'<a class="evidence-link" href="#{_safe(anchor)}">Evidence</a>' for anchor in fact_source_refs) or '<span class="muted">No source evidence</span>'
        subject_html = f'<a href="#concept-{_safe(_slug(subject))}">{_safe(subject)}</a>' if subject in concept_ids else _safe(subject)
        object_html = f'<a href="#concept-{_safe(_slug(object_concept))}">{_safe(object_concept)}</a>' if object_concept in concept_ids else _safe(object_concept)
        fact_rows.append(
            f'<tr id="fact-{_safe(_slug(fact_id))}"><td><strong>{_safe(fact_id)}</strong><div class="muted">{_safe(fact.get("verb_term"))}</div></td><td>{subject_html}</td><td>{_safe(fact.get("verb_term"))}</td><td>{object_html}</td><td><span class="status status-{_safe(fact_status.casefold().replace(" ", "_"))}">{_safe(fact_status)}</span><div>{fact_evidence}</div></td></tr>'
        )
    rule_rows = [_rule_row(rule, rule_sources.get(str(rule.get("rule_id") or "unidentified"), []), model_rule_ids, model_item_lookup) for rule in rules]

    # Unified, severity-triaged Human Review dashboard -- replaces the old
    # split human-review-queue / quality-holds-outside-queue tables (§5 of
    # the redesign). Route + confidence stay visible for context; severity
    # is the new primary sort/filter signal since neither of those alone
    # told a reviewer what to look at first.
    review_rows: list[str] = []
    for rule in rules:
        if not rule.get("requires_review"):
            continue
        rid = str(rule.get("rule_id") or "unidentified")
        review_route = str(_mapping(rule.get("review_route")).get("route") or "unclassified")
        severity = _review_severity(rule)
        reasons = _review_reasons(rule) or ["Review flag set without a detailed reason."]
        reason_html = "".join(f"<li>{_safe(reason)}</li>" for reason in reasons)
        evidence_html = " ".join(
            f'<a class="evidence-link" href="#{_safe(anchor)}">Evidence</a>'
            for anchor in rule_sources.get(rid, [])
        ) or "Unresolved source"
        confidence = _confidence(rule)
        related = sorted(rule_adjacency.get(rid, ()))
        related_html = "".join(f'<a class="trace-chip trace-chip-link" href="#rule-{_safe(_slug(r))}">{_safe(r)}</a>' for r in related[:8]) or '<span class="trace-chip trace-chip-empty">None</span>'
        if len(related) > 8:
            related_html += f'<span class="muted trace-more">+{len(related) - 8} more</span>'
        human_required = bool(_mapping(rule.get("review_route")).get("human_review_required"))
        review_rows.append(
            f'<tr class="review-row" data-severity="{_safe(severity)}" data-route="{_safe(review_route)}" data-human="{str(human_required).lower()}" '
            f'data-search="{_safe((rid + " " + str(rule.get("rule_name", ""))).casefold())}">'
            f'<td>{_severity_badge_html(severity)}</td>'
            f'<td><a href="#rule-{_safe(_slug(rid))}">{_safe(rid)}</a><div class="muted">{_safe(rule.get("rule_name") or "Untitled rule")}</div></td>'
            f'<td>{_route_badge_html(review_route)}</td>'
            f'<td><ul class="reason-list">{reason_html}</ul></td>'
            f'<td>{_safe(f"{confidence:.1f}%" if confidence is not None else "—")}</td>'
            f'<td>{evidence_html}</td>'
            f'<td><div class="trace-chip-row">{related_html}</div></td></tr>'
        )
    # Overview / Rule Analytics chart data (§4 of the redesign) -- rendered
    # as SVG bar/donut charts below, replacing the old plain KPI tables.
    category_chart = _bar_chart_svg(sorted(categories.items(), key=lambda item: (-item[1], item[0].casefold())), color="#7c83fd")
    confidence_chart = _bar_chart_svg(sorted(confidence_buckets.items()), color="#27c2a5")
    confidence_source_summary = " · ".join(f'{_confidence_source_label(source)}: {count}' for source, count in sorted(confidence_sources.items())) or "Not reported"
    route_donut = _donut_chart_svg([(route.replace("_", " ").title(), count) for route, count in sorted(route_counts.items(), key=lambda item: -item[1])])
    model_type_chart = _bar_chart_svg([(kind, len(model_info[kind]["rule_ids"])) for kind in ("DMN", "BPMN", "CMMN")], color="#5a8dee")
    degree_chart = _bar_chart_svg(list(connectivity["degree_buckets"].items()), color="#f3a94b")
    most_connected_html = "".join(
        f'<li><a href="#rule-{_safe(_slug(rid))}">{_safe(rid)}</a><span class="muted">{count} connection{"s" if count != 1 else ""}</span></li>'
        for rid, count in connectivity["most_connected"]
    ) or '<li class="muted">No dependency edges were reported.</li>'
    isolated_ids = connectivity["isolated_rule_ids"]
    isolated_chips = "".join(f'<a class="trace-chip trace-chip-link" href="#rule-{_safe(_slug(rid))}">{_safe(rid)}</a>' for rid in isolated_ids[:60]) or '<span class="trace-chip trace-chip-empty">None -- every rule has at least one dependency edge.</span>'
    if len(isolated_ids) > 60:
        isolated_chips += f'<span class="muted trace-more">+{len(isolated_ids) - 60} more</span>'
    edge_rows = "".join(f'<tr><td>{_safe(edge.get("source_rule_id"))}</td><td>{_safe(edge.get("target_rule_id"))}</td><td>{_safe(edge.get("dependency_type", "unknown"))}</td></tr>' for edge in edges[:500]) or '<tr><td colspan="3">No dependency edges were reported.</td></tr>'
    dependency_layers = dependency_layout["layers"]
    dependency_layer_chips = "".join(
        f'<span class="graph-layer-chip"><strong>degree {degree}</strong> · {len(layer_nodes)} nodes</span>'
        for degree, layer_nodes in dependency_layers.items()
    ) or '<span class="muted">No degree layers were reported.</span>'
    dependency_graph = _dependency_graph_svg(dependency_layout)
    dependency_graph_note = (
        "Layers show shortest directed distance from zero-indegree roots. "
        "Cyclic or rootless components use a deterministic degree-0 anchor; "
        "arrows always follow source_rule_id → target_rule_id."
    )
    route_options = "".join(f'<option value="{_safe(route)}">{_safe(route.replace("_", " "))}</option>' for route in sorted(route_counts, key=str.casefold))
    kind_colors = {"actor_role": "#27c2a5", "business_object": "#7c83fd", "decision_variable": "#f3a94b", "evidence_object": "#5a8dee", "event": "#d85d69", "process": "#8f6be8", "unresolved": "#a9b3c3"}
    kind_bars = "".join(_progress_bar(kind.replace("_", " "), count, concept_supported, kind_colors.get(kind, "#7c83fd")) for kind, count in sorted(concept_kind_counts.items(), key=lambda item: (-item[1], item[0])))
    top_concept_rows = "".join(
        f'<li><a href="#concept-{_safe(_slug(item["concept_id"]))}">{_safe(item["preferred_term"])}</a><span class="muted">{item["rule_links"]} rule links · {item["fact_links"]} fact endpoints</span></li>'
        for item in top_concepts if item["rule_links"] or item["fact_links"]
    ) or '<li class="muted">No connected concepts were reported.</li>'
    fact_status_rows = "".join(f'<tr><td>{_safe(status)}</td><td>{count}</td><td>{_percent(count, len(fact_types)):.1f}%</td></tr>' for status, count in sorted(fact_status_counts.items(), key=lambda item: (-item[1], item[0]))) or '<tr><td>Not reported</td><td>0</td><td>0.0%</td></tr>'

    report_html = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Business Knowledge Report</title>
<style>
:root{{--ink:#17253d;--muted:#6f7d91;--line:#e4eaf2;--paper:#fff;--wash:#f5f8fc;--teal:#27c2a5;--violet:#7c83fd;--amber:#f3a94b;--red:#d85d69;--shadow:0 18px 50px rgba(23,37,61,.08)}}*{{box-sizing:border-box}}body{{margin:0;color:var(--ink);background:var(--wash);font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}}a{{color:#4251bd;text-decoration:none}}a:hover{{text-decoration:underline}}button,input,select{{font:inherit}}.shell{{max-width:1560px;margin:auto;padding:26px}}header.hero{{background:linear-gradient(125deg,#17253d,#2b4169 55%,#5165ce);border-radius:24px;color:#fff;padding:34px;box-shadow:var(--shadow);position:relative;overflow:hidden}}header.hero:after{{content:"";position:absolute;width:320px;height:320px;border-radius:50%;right:-90px;top:-130px;background:rgba(39,194,165,.22)}}.eyebrow{{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--teal);font-weight:800}}.hero h1{{font-size:clamp(28px,4vw,48px);line-height:1.05;max-width:800px;margin:10px 0}}.hero p{{max-width:800px;color:#dce7f7;font-size:16px}}.metric-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:18px 0 26px}}.metric-card,.panel,.model-card{{background:var(--paper);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow)}}.metric-card{{padding:18px}}.metric-value{{font-size:27px;font-weight:800}}.metric-label{{font-weight:750;margin-top:2px}}.metric-detail,.muted{{color:var(--muted);font-size:12px}}nav.tabs{{display:flex;gap:8px;flex-wrap:wrap;margin:20px 0}}nav.tabs button{{border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:999px;padding:10px 16px;cursor:pointer;font-weight:700}}nav.tabs button.active{{background:var(--ink);color:#fff;border-color:var(--ink)}}section.tab{{display:none}}section.tab.active{{display:block}}.panel{{padding:22px;margin:14px 0}}.panel h2,.panel h3{{margin-top:0}}.grid-2{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:11px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);background:#f8fafd;position:sticky;top:0;z-index:1}}tr:hover td{{background:#fbfcff}}.table-wrap{{overflow:auto;max-height:720px;border:1px solid var(--line);border-radius:12px}}.toolbar{{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}}.toolbar input,.toolbar select{{border:1px solid var(--line);border-radius:9px;padding:9px 11px;background:#fff;min-width:190px}}.status{{display:inline-block;border-radius:999px;padding:3px 8px;font-size:11px;font-weight:800;background:#e9f7f3;color:#087760}}.status-review_required,.status-unresolved{{background:#fff1df;color:#92570a}}.status-fail,.status-contradicted{{background:#ffe8eb;color:#9d2937}}details summary{{cursor:pointer;color:#4251bd;font-weight:650}}pre{{white-space:pre-wrap;word-break:break-word;background:#f7f9fc;border-radius:9px;padding:12px;font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;max-height:360px;overflow:auto}}.evidence-link{{display:inline-block;margin:2px 4px 2px 0;padding:2px 7px;border-radius:99px;background:#eef1ff;font-size:11px}}.model-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:14px}}.model-card{{padding:18px}}.model-svg{{width:100%;height:auto;background:#fbfcff;border-radius:12px;margin-top:10px}}.svg-title{{font-size:16px;font-weight:800;fill:var(--ink)}}.svg-label{{font-size:11px;fill:var(--ink)}}.svg-empty{{font-size:12px;fill:var(--muted)}}.source-card{{border:1px solid var(--line);background:#fff;border-radius:12px;padding:16px;margin:10px 0;scroll-margin-top:20px}}.source-card h4{{margin:0 0 4px;font-size:14px;word-break:break-all}}.source-meta{{color:var(--muted);font-size:11px;margin-bottom:8px}}.callout{{border-left:4px solid var(--teal);padding:12px 16px;background:#effaf7;border-radius:8px}}.empty{{padding:30px;text-align:center;color:var(--muted)}}footer{{padding:28px 0;color:var(--muted);font-size:12px}}@media(max-width:700px){{.shell{{padding:12px}}header.hero{{padding:24px 20px}}th,td{{min-width:130px}}}}
 .insight-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:16px 0}}.insight-card{{background:linear-gradient(145deg,#f7fbff,#fff);border:1px solid var(--line);border-radius:14px;padding:16px}}.insight-card .metric-value{{font-size:24px}}.insight-card h3{{font-size:13px;margin:0 0 4px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}}.insight-bar-row{{margin:12px 0}}.insight-bar-label{{display:flex;justify-content:space-between;gap:12px;text-transform:capitalize}}.insight-bar-track{{height:8px;background:#edf1f7;border-radius:99px;overflow:hidden;margin:6px 0 3px}}.insight-bar-track span{{display:block;height:100%;border-radius:99px}}.insight-list{{margin:0;padding:0;list-style:none}}.insight-list li{{display:flex;justify-content:space-between;gap:12px;padding:9px 0;border-bottom:1px solid var(--line)}}.insight-list li:last-child{{border-bottom:0}}.concept-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:14px;margin-top:16px}}.concept-card{{background:#fff;border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 10px 28px rgba(23,37,61,.05);scroll-margin-top:20px}}.concept-card:hover{{border-color:#b9c4ff;box-shadow:0 14px 34px rgba(66,81,189,.12)}}.concept-card-head{{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}}.concept-term{{font-size:18px;font-weight:800;line-height:1.2}}.concept-card p{{color:#4e5e73;min-height:42px}}.concept-meta{{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0;color:var(--muted);font-size:12px}}.concept-meta span{{padding:5px 8px;background:#f5f7fb;border-radius:999px}}.concept-detail{{display:grid;gap:12px;padding-top:10px}}.concept-detail strong{{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}}.vocabulary-toolbar{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:14px 0}}.vocabulary-toolbar input,.vocabulary-toolbar select{{border:1px solid var(--line);border-radius:9px;padding:9px 11px;background:#fff;min-width:190px}}.vocabulary-toolbar output{{color:var(--muted);font-size:12px}}.fact-table{{margin-top:18px}}.status-case_management{{background:#eef1ff;color:#4251bd}}.status-human_review{{background:#ffe8eb;color:#9d2937}}.status-machine_repair{{background:#e9f7f3;color:#087760}}.status-presented{{background:#e9f7f3;color:#087760}}.status-unverified{{background:#fff1df;color:#92570a}}.status-grounding-failed{{background:#ffe8eb;color:#9d2937}}.status-grounding-certified{{background:#e9f7f3;color:#087760}}.status-grounding-unknown{{background:#f0f2f6;color:#5d6b7e}}.status-stack{{display:flex;flex-wrap:wrap;gap:5px}}.confidence-score{{display:flex;align-items:baseline;gap:6px;margin-top:7px}}.logic-details{{min-width:250px}}.logic-details summary{{display:flex;align-items:center;justify-content:space-between;gap:8px}}.logic-summary{{font-weight:800;color:#4251bd}}.formal-logic{{padding:14px 0 4px}}.logic-expression{{padding:12px 14px;background:#17253d;color:#eef4ff;border-radius:10px;font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;overflow:auto}}.logic-keyword{{color:#7de4ce;font-weight:900;margin:0 4px}}.logic-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-top:14px}}.logic-grid h4{{margin:0 0 7px;font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}}.logic-list{{border:1px solid var(--line);border-radius:10px;overflow:hidden}}.logic-row{{display:flex;align-items:flex-start;gap:8px;padding:8px 10px;border-bottom:1px solid var(--line);background:#fff}}.logic-row:last-child{{border-bottom:0}}.logic-index{{flex:0 0 auto;color:#4251bd;font:700 11px ui-monospace,SFMono-Regular,Menlo,monospace}}.logic-row code{{font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}}.logic-type{{margin-left:auto;flex:0 0 auto;color:var(--muted);font-size:11px}}.logic-raw{{margin-top:12px}}.logic-raw pre{{max-height:260px}}.logic-if{{margin-bottom:10px}}.logic-then-row{{display:flex;align-items:flex-start;gap:8px;flex-wrap:wrap}}.logic-then{{display:flex;flex-wrap:wrap;gap:6px;flex:1}}.outcome-chip{{display:inline-flex;align-items:center;gap:5px;padding:4px 9px;border-radius:7px;background:rgba(124,131,253,.22);font:12px/1.3 ui-monospace,SFMono-Regular,Menlo,monospace}}.outcome-chip .ov-name{{color:#b9c4ff}}.outcome-chip .ov-eq{{color:#7de4ce;font-weight:900}}.outcome-chip .ov-val{{color:#eef4ff;font-weight:700}}.outcome-chip.ov-true{{background:rgba(39,194,165,.26)}}.outcome-chip.ov-true .ov-val{{color:#7de4ce}}.outcome-chip.ov-false{{background:rgba(111,125,145,.24)}}.outcome-chip.ov-false .ov-val{{color:#c3cbdb}}.outcome-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px;border:1px solid var(--line);border-radius:10px;padding:10px;background:#fbfcff}}.outcome-card{{display:flex;flex-direction:column;gap:6px;padding:9px 11px;border-radius:9px;background:#fff;border:1px solid var(--line)}}.outcome-name{{font-size:11.5px;font-weight:700;color:var(--ink);word-break:break-word;display:flex;flex-direction:column;gap:2px}}.outcome-var{{font:11px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--muted);font-weight:400;word-break:break-all}}.outcome-badge{{align-self:flex-start;display:inline-flex;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:800;max-width:100%;overflow-wrap:anywhere}}.outcome-badge.type-true{{background:#e9f7f3;color:#087760}}.outcome-badge.type-false{{background:#f0f2f6;color:#5d6b7e}}.outcome-badge.type-number{{background:#eef1ff;color:#4251bd}}.outcome-badge.type-text{{background:#fff1df;color:#92570a}}.outcome-badge.type-list{{background:transparent;padding:0;display:flex;flex-wrap:wrap;gap:4px}}.outcome-value-item{{background:#f5f7fb;border:1px solid var(--line);border-radius:999px;padding:3px 9px;font-size:11px;font-weight:700;color:var(--ink)}}.status-unclassified{{background:#f0f2f6;color:#5d6b7e}}.route-card{{border:1px solid var(--line);border-left:4px solid #c7ceda;border-radius:10px;padding:12px 14px;background:#fff;display:flex;flex-direction:column;gap:8px;min-width:230px}}.route-head{{display:flex;align-items:flex-start;gap:10px}}.route-icon{{font-size:18px;line-height:1;flex:0 0 auto}}.route-title{{font-weight:800;font-size:13px;margin-top:3px}}.route-desc{{margin:0;color:var(--muted);font-size:12px;line-height:1.45}}.route-hold{{align-self:flex-start;display:inline-flex;padding:3px 9px;border-radius:999px;font-size:11px;font-weight:800}}.route-hold-yes{{background:#fff1df;color:#92570a}}.route-hold-no{{background:#e9f7f3;color:#087760}}.route-reasons{{margin-top:2px}}.route-reasons summary{{font-size:12px}}.route-badge{{display:inline-flex;align-items:center;gap:5px}}.route-badge-label{{margin-top:3px}}.reason-list{{margin:6px 0 0;padding-left:18px;color:#4e5e73;font-size:12.5px;line-height:1.6}}.route-human_review{{border-left-color:#d85d69}}.route-case_management{{border-left-color:#7c83fd}}.route-machine_repair{{border-left-color:#27c2a5}}.route-none{{border-left-color:#27c2a5}}.route-unclassified{{border-left-color:#9aa5b8}}.model-diagram-empty{{padding:22px;text-align:center;color:var(--muted);border:1px dashed var(--line);border-radius:10px;margin-top:12px}}.status-dmn{{background:#eef1ff;color:#4251bd}}.dmn-table-wrap{{margin-top:2px}}.dmn-table-meta{{display:flex;align-items:center;gap:8px;margin-bottom:8px}}.dmn-table{{min-width:100%}}.dmn-table th,.dmn-table td{{border:1px solid var(--line)}}.dmn-table thead th.dmn-col-input{{background:#f4f7ff;color:#4251bd}}.dmn-table thead th.dmn-col-output{{background:#effaf7;color:#087760;border-left:3px solid var(--teal)}}.dmn-col-type{{display:block;font-weight:400;text-transform:none;letter-spacing:0;color:var(--muted);font-size:10px}}.dmn-table td.dmn-col-output{{border-left:3px solid var(--teal);background:#fbfffd}}.dmn-table td code{{font:12px ui-monospace,SFMono-Regular,Menlo,monospace}}.bpmn-flow{{display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-top:4px;padding:16px;background:#fbfcff;border:1px solid var(--line);border-radius:12px}}.bpmn-step{{display:flex;align-items:center;gap:6px}}.bpmn-node{{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;min-width:120px;min-height:64px;padding:8px 12px;text-align:center;font-size:12px;font-weight:700}}.bpmn-node-event{{border-radius:999px;background:#eef1ff;border:2px solid #7c83fd;color:#4251bd}}.bpmn-node-task{{border-radius:12px;background:#fff;border:1.5px solid var(--line);box-shadow:0 6px 16px rgba(23,37,61,.06)}}.bpmn-node-icon{{font-size:18px}}.bpmn-node-sub{{font-size:10px;font-weight:700;color:var(--teal);text-transform:uppercase;letter-spacing:.04em}}.bpmn-arrow{{color:#7c83fd;font-size:20px;font-weight:900}}.cmmn-plan{{display:flex;flex-wrap:wrap;gap:10px;margin-top:4px}}.cmmn-item{{display:flex;align-items:center;gap:10px;padding:12px 14px;border-radius:12px;background:#fff;border:1px solid var(--line);min-width:220px;box-shadow:0 6px 16px rgba(23,37,61,.05)}}.cmmn-item-icon{{font-size:20px}}.cmmn-item-kind{{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}}.cmmn-item-name{{font-weight:700}}.cmmn-human_task{{border-left:4px solid var(--violet)}}.cmmn-milestone{{border-left:4px solid var(--amber)}}@keyframes navHighlight{{0%{{box-shadow:0 0 0 3px rgba(66,81,189,.55)}}100%{{box-shadow:0 0 0 3px rgba(66,81,189,0)}}}}.nav-highlight{{animation:navHighlight 1.6s ease-out;border-radius:10px}}.dependency-graph-shell{{border:1px solid var(--line);border-radius:14px;background:#fbfcff;padding:16px;margin:16px 0}}.dependency-graph-toolbar{{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}}.dependency-graph-toolbar h3{{margin:0}}.dependency-graph-stats{{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}}.graph-layer-chip{{display:inline-flex;align-items:center;gap:4px;border-radius:999px;padding:6px 10px;background:#eef1ff;color:#4251bd;font-size:12px}}.dependency-graph-layout{{display:flex;gap:14px;align-items:flex-start}}.dependency-graph-scroll{{flex:1;min-width:0;overflow:auto;border:1px solid var(--line);border-radius:12px;background:#fff;max-height:760px}}.dependency-graph-svg{{display:block;max-width:none;background:#fff;cursor:grab}}.dependency-graph-svg.grabbing{{cursor:grabbing}}.dependency-lane{{fill:#f7f9fc;stroke:#e4eaf2}}.dependency-layer-label{{fill:#6f7d91;font:700 12px Inter,ui-sans-serif,system-ui,sans-serif}}.dependency-edge{{fill:none;stroke:#7c83fd;stroke-width:1.6;opacity:.62;vector-effect:non-scaling-stroke;transition:opacity .15s,stroke-width .15s}}.dependency-edge:hover,.dependency-edge.active{{stroke:#4251bd;stroke-width:2.8;opacity:1}}.dependency-edge.dimmed{{opacity:.12}}.dependency-node{{cursor:pointer;transition:opacity .15s}}.dependency-node rect{{transition:stroke-width .15s,filter .15s}}.dependency-node.selected rect{{stroke-width:3;filter:drop-shadow(0 0 6px rgba(66,81,189,.45))}}.dependency-node.neighbor rect{{stroke-width:2.4}}.dependency-node.dimmed{{opacity:.22}}.dependency-node-id{{fill:#17253d;font:700 12px ui-monospace,SFMono-Regular,Menlo,monospace}}.dependency-node-degree{{fill:#6f7d91;font:11px Inter,ui-sans-serif,system-ui,sans-serif}}.dependency-graph-empty{{padding:32px;text-align:center;color:var(--muted);border:1px dashed var(--line);border-radius:10px}}.dependency-graph-note{{margin:12px 0 0;color:var(--muted);font-size:12px}}.dep-side-panel{{flex:0 0 260px;border:1px solid var(--line);border-radius:12px;background:#fff;padding:14px;max-height:760px;overflow:auto}}.dep-panel-head{{display:flex;align-items:center;justify-content:space-between;gap:8px;font:700 13px ui-monospace,SFMono-Regular,Menlo,monospace}}.dep-panel-close{{border:0;background:none;font-size:18px;line-height:1;cursor:pointer;color:var(--muted)}}.dep-panel-meta{{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0;font-size:11px}}.dep-panel-meta span{{padding:3px 8px;border-radius:999px;background:#f5f7fb;color:var(--muted)}}.dep-panel-list{{list-style:none;margin:6px 0 0;padding:0}}.dep-panel-list li{{display:flex;justify-content:space-between;gap:8px;padding:6px 0;border-bottom:1px solid var(--line);font-size:12.5px}}.dep-panel-list li:last-child{{border-bottom:0}}.dep-panel-head+*{{margin-top:2px}}
.model-badges{{margin-top:6px;display:flex;gap:4px}}.model-badge{{font-size:10px;font-weight:800;letter-spacing:.03em;padding:2px 7px;border-radius:6px}}.model-badge-yes{{background:#eef7f3;color:#087760}}.model-badge-no{{background:#f0f2f6;color:#a9b3c3}}
.rule-model-diagrams{{margin-top:14px;display:grid;gap:12px}}.rule-model-block{{border:1px solid var(--line);border-radius:10px;padding:12px;background:#fbfcff}}.rule-model-kind{{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:6px}}
.trace-path{{display:flex;flex-wrap:wrap;align-items:stretch;gap:0;margin-bottom:16px;padding:14px;background:#f7f9fc;border:1px solid var(--line);border-radius:12px}}.trace-step{{display:flex;align-items:center}}.trace-arrow{{display:flex;align-items:center;padding:0 8px;color:#9aa5b8;font-weight:900;font-size:15px}}.trace-node{{display:flex;flex-direction:column;gap:4px;min-width:120px;max-width:230px}}a.trace-node{{color:inherit}}a.trace-node:hover{{text-decoration:none}}a.trace-node .trace-node-label{{text-decoration:underline}}.trace-node-kind{{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}}.trace-node-label{{font-weight:700;font-size:12.5px;word-break:break-word}}.trace-node-excerpt{{font-size:11px;color:var(--muted);font-style:italic;line-height:1.4}}.trace-node.trace-empty{{color:var(--muted);font-style:italic;justify-content:center}}.trace-chip-row{{display:flex;flex-wrap:wrap;gap:4px;margin-top:2px}}.trace-chip{{display:inline-flex;padding:3px 8px;border-radius:999px;background:#eef1ff;color:#4251bd;font-size:11px;font-weight:700}}.trace-chip-link{{background:#eef1ff}}.trace-chip-model{{background:#eef7f3;color:#087760}}.trace-chip-empty{{background:#f0f2f6;color:#a9b3c3;font-weight:400}}.trace-more{{align-self:center;font-size:11px}}
.chart-empty{{padding:26px;text-align:center;color:var(--muted);border:1px dashed var(--line);border-radius:10px}}.chart-svg{{max-width:100%}}.bar-chart{{width:100%;height:auto}}.chart-label{{font:11px Inter,ui-sans-serif,system-ui,sans-serif;fill:var(--ink)}}.chart-value{{font:700 11px Inter,ui-sans-serif,system-ui,sans-serif;fill:var(--muted)}}.chart-bar{{transition:opacity .15s}}.chart-bar:hover{{opacity:.8}}.donut-wrap{{display:flex;align-items:center;gap:18px;flex-wrap:wrap}}.chart-donut-seg{{transition:opacity .15s}}.chart-donut-seg:hover{{opacity:.8}}.chart-donut-total{{font:800 22px Inter,ui-sans-serif,system-ui,sans-serif;fill:var(--ink)}}.chart-donut-caption{{font:11px Inter,ui-sans-serif,system-ui,sans-serif;fill:var(--muted)}}.chart-legend{{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px}}.chart-legend li{{display:flex;align-items:center;gap:8px;font-size:12.5px}}.chart-legend-dot{{width:10px;height:10px;border-radius:3px;display:inline-block;flex:0 0 auto}}
.severity-badge{{display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border-radius:999px;font-size:11px;font-weight:800}}.severity-critical{{background:#ffe8eb;color:#9d2937}}.severity-high{{background:#fff1df;color:#92570a}}.severity-medium{{background:#fff8e1;color:#8a6d1c}}.severity-low{{background:#eef1ff;color:#4251bd}}
 </style></head><body><div class="shell">
<header class="hero"><div class="eyebrow">Agent 12 · presentation and knowledge exploration</div><h1>Business knowledge, ready to review.</h1><p>A self-contained, source-traceable view of the extracted domain. Navigate from SBVR concepts to rules, decisions, workflows, review findings, and the exact evidence that supports each result.</p><div class="muted" style="color:#cbd9ee">Generated from {_safe(graph_file.name)} · no external assets or network calls required</div></header>
<div class="metric-grid">{_metric_card('Business rules', len(rules), 'All extracted rules shown')}{_metric_card('SBVR concepts', concept_supported, f'{vocabulary_coverage:.1f}% with concept-specific evidence')}{_metric_card('Decision variables', len(decision_variables), 'Executable symbols kept outside SBVR')}{_metric_card('Human-review queue', f'{human_review_count} ({report_data["human_review_rate"]:.1f}%)', 'Explicit human judgment required')}{_metric_card('Quality holds', f'{review_count} ({report_data["quality_hold_rate"]:.1f}%)', 'Strict whole-rule execution holds')}{_metric_card('Quarantined claims', quarantined_claim_count, f'Ontology-invalid enrichment removed from {rules_with_quarantined_claims} rules')}{_metric_card('Core-rule holds', f'{grounding_dimension_metrics["core_rule"]["failed_count"]} ({grounding_dimension_metrics["core_rule"]["hold_rate"]:.1f}%)', 'Description, conditions, or outcomes')}{_metric_card('Enrichment holds', f'{grounding_dimension_metrics["enrichment"]["failed_count"]} ({grounding_dimension_metrics["enrichment"]["hold_rate"]:.1f}%)', 'Party, scope, or exception evidence')}{_metric_card('Contract holds', f'{grounding_dimension_metrics["contract"]["failed_count"]} ({grounding_dimension_metrics["contract"]["hold_rate"]:.1f}%)', 'Derived structural projections')}{_metric_card('Relationship holds', f'{grounding_dimension_metrics["relationship"]["failed_count"]} ({grounding_dimension_metrics["relationship"]["hold_rate"]:.1f}%)', 'Graph relationship grounding')}{_metric_card('Grounding certified', f'{grounded_count} ({report_data["grounding_coverage_rate"]:.1f}%)', 'Independent whole-rule certification')}{_metric_card('Source pointers', f'{source_pointer_count} ({report_data["source_pointer_coverage_rate"]:.1f}%)', 'Pointer presence, not grounding certification')}{_metric_card('Grounding claims', f'{grounding_claim_counts.get("supported", 0)} ({report_data["grounding_claim_support_rate"]:.1f}%)', 'Claim-level support; holds may be partial')}{_metric_card('Source documents', len(source_documents), 'Documents referenced by rule evidence')}{_metric_card('Dependencies', len(edges), 'DAG edges available')}</div>
<nav class="tabs" aria-label="Report sections"><button class="active" data-tab="overview">Overview</button><button data-tab="vocabulary">SBVR vocabulary</button><button data-tab="rules">Rule explorer</button><button data-tab="dependencies">Relationships</button><button data-tab="review">Review queue</button><button data-tab="sources">Source traceability</button></nav>
<section id="overview" class="tab active"><div class="grid-2"><div class="panel"><div class="eyebrow">Executive summary</div><h2>What this domain contains</h2><p>The report presents <strong>{len(rules)}</strong> rules across <strong>{len(categories)}</strong> categories, <strong>{concept_supported}</strong> governed SBVR concepts, and <strong>{len(decision_variables)}</strong> separately managed decision variables.</p><div class="callout">Concept evidence, rule source pointers, and independent grounding certification are reported as distinct signals. A pointer is never presented as proof of entailment.</div></div><div class="panel"><div class="eyebrow">Coverage and quality</div><h2>At a glance</h2><table><tr><td>Concept evidence coverage</td><td><strong>{vocabulary_coverage:.1f}%</strong></td></tr><tr><td>Rule source-pointer coverage</td><td><strong>{report_data["source_pointer_coverage_rate"]:.1f}%</strong></td></tr><tr><td>Rules grounding-certified</td><td><strong>{report_data["grounding_coverage_rate"]:.1f}%</strong> ({grounded_count} rules)</td></tr><tr><td>Grounding claims supported</td><td><strong>{grounding_claim_counts.get("supported", 0)}/{grounding_claim_total}</strong> ({report_data["grounding_claim_support_rate"]:.1f}%)</td></tr><tr><td>Human-review queue</td><td><strong>{report_data["human_review_rate"]:.1f}%</strong> ({human_review_count} rules)</td></tr><tr><td>Quality holds</td><td><strong>{report_data["quality_hold_rate"]:.1f}%</strong> ({review_count} rules)</td></tr></table></div></div>
<div class="grid-2"><div class="panel"><h3>Rule categories</h3><p class="muted">How the extracted rules are distributed across business categories.</p>{category_chart}</div><div class="panel"><h3>Confidence distribution</h3><p class="muted">Confidence provenance: {_safe(confidence_source_summary)}</p>{confidence_chart}</div></div>
<div class="grid-2"><div class="panel"><h3>Review route distribution</h3><p class="muted">Where each rule that needs attention is routed -- human judgment, deterministic repair, or case management.</p>{route_donut}</div><div class="panel"><h3>Executable model coverage</h3><p class="muted">How many rules have a generated DMN decision, BPMN process, or CMMN case.</p>{model_type_chart}</div></div>
<div class="grid-2"><div class="panel"><h3>Dependency degree distribution</h3><p class="muted">Total in+out dependency edges per rule -- a rule with more edges is more structurally central to the domain.</p>{degree_chart}</div><div class="panel"><h3>Most connected rules</h3><p class="muted">The rules with the most direct dependency edges -- start here to understand the domain's structural core.</p><ol class="insight-list">{most_connected_html}</ol></div></div>
<div class="grid-2"><div class="panel"><h3>Isolated rules ({len(isolated_ids)})</h3><p class="muted">Rules with no dependency edges at all -- self-contained, or possibly missing an expected relationship.</p><details><summary>View isolated rules</summary><div class="trace-chip-row" style="margin-top:8px">{isolated_chips}</div></details></div><div class="panel"><h3>Dependency depth & complexity</h3><p class="muted">Shortest-path depth from root rules, and how many rules sit in a cyclic or rootless component.</p><div class="insight-grid"><div class="insight-card"><h3>Max depth</h3><div class="metric-value">{max_dependency_depth}</div></div><div class="insight-card"><h3>Cyclic/rootless anchors</h3><div class="metric-value">{cyclic_component_count}</div></div><div class="insight-card"><h3>Dependency edges</h3><div class="metric-value">{len(edges)}</div></div></div></div></div>
</section>
<section id="vocabulary" class="tab"><div class="panel"><div class="eyebrow">SBVR-aligned business vocabulary</div><h2>Vocabulary workbench</h2><p>Explore the domain lexicon as typed concepts and fact types. The view is grounded in the input graph: definitions, usage counts, relationships, and evidence links are shown only when the upstream artifacts provide them.</p><div class="insight-grid"><div class="insight-card"><h3>Supported concepts</h3><div class="metric-value">{concept_supported}</div><div class="muted">{report_data["concept_coverage_rate"]:.1f}% graph-supported coverage</div></div><div class="insight-card"><h3>Evidence coverage</h3><div class="metric-value">{report_data["concept_evidence_coverage_rate"]:.1f}%</div><div class="muted">{concept_evidence_count} concepts have source evidence</div></div><div class="insight-card"><h3>Fact types</h3><div class="metric-value">{len(fact_types)}</div><div class="muted">{fact_grounded_count} grounded · {report_data["fact_type_grounding_rate"]:.1f}%</div></div><div class="insight-card"><h3>Unresolved / orphaned</h3><div class="metric-value">{report_data["concept_review_count"]} / {concept_orphan_count}</div><div class="muted">Unresolved kinds / no rule or fact links</div></div></div><div class="grid-2"><div class="panel"><h3>Concept type mix</h3><p class="muted">How the vocabulary is distributed across SBVR-aligned concept kinds.</p>{kind_bars}</div><div class="panel"><h3>Most connected concepts</h3><p class="muted">Concepts with the strongest links into rules and fact types.</p><ul class="insight-list">{top_concept_rows}</ul></div></div><div class="panel"><div class="eyebrow">Concept explorer</div><h3>Find a term, definition, or concept kind</h3><div class="vocabulary-toolbar"><input id="concept-search" type="search" placeholder="Search concepts and definitions…"><select id="concept-kind"><option value="">All kinds</option>{''.join(f'<option value="{_safe(kind)}">{_safe(kind.replace("_", " "))}</option>' for kind in sorted(concept_kind_counts, key=str.casefold))}</select><select id="concept-evidence"><option value="">All evidence states</option><option value="grounded">With source evidence</option><option value="unresolved">Evidence unresolved</option></select><output id="concept-count" for="concept-search"></output></div><div id="concept-grid" class="concept-grid">{''.join(concept_rows) or '<div class="empty">No concepts were reported.</div>'}</div></div><div id="fact-types" class="panel fact-table"><div class="eyebrow">SBVR fact types</div><h3>Relationships and grounding status</h3><p class="muted">Each endpoint links back to its concept card; evidence links land on the embedded source block.</p><div class="grid-2"><div class="table-wrap"><table><thead><tr><th>Grounding status</th><th>Fact types</th><th>Share</th></tr></thead><tbody>{fact_status_rows}</tbody></table></div><div class="callout"><strong>{len(fact_types)}</strong> fact types connect <strong>{len(concept_ids)}</strong> concepts. A fact type is a vocabulary relationship, not a workflow sequence.</div></div><div class="table-wrap" style="margin-top:14px"><table><thead><tr><th>Fact type</th><th>Subject</th><th>Verb</th><th>Object</th><th>Grounding and evidence</th></tr></thead><tbody>{''.join(fact_rows) or '<tr><td colspan="5">No fact types were reported.</td></tr>'}</tbody></table></div></div></div></section>
<section id="rules" class="tab"><div class="panel"><div class="eyebrow">Structured rule explorer</div><h2>Business rules</h2><p class="muted">Readiness, grounding, and confidence are separate signals. A quality hold means the rule is fail-closed for execution; it does not mean every extracted statement is wrong. Expand <strong>IF / THEN</strong> to inspect the typed contract, traceability path, and any generated DMN/BPMN/CMMN model.</p><div class="toolbar"><input id="rule-search" type="search" placeholder="Search ID, title, statement, category…"><select id="rule-category"><option value="">All categories</option>{''.join(f'<option>{_safe(category)}</option>' for category in sorted(categories, key=str.casefold))}</select><select id="rule-status"><option value="">All statuses</option><option value="review_required">Quality hold</option><option value="verified">Verified</option><option value="unresolved">Unresolved</option></select><select id="rule-route"><option value="">All routes</option>{route_options}</select><label class="muted" style="padding:9px 0"><input id="review-only" type="checkbox"> quality holds only</label><label class="muted" style="padding:9px 0"><input id="filter-has-dmn" type="checkbox"> has DMN</label><label class="muted" style="padding:9px 0"><input id="filter-has-bpmn" type="checkbox"> has BPMN</label><label class="muted" style="padding:9px 0"><input id="filter-has-cmmn" type="checkbox"> has CMMN</label><span id="rule-count" class="muted" style="padding:9px 0"></span></div><div class="table-wrap"><table id="rules-table"><thead><tr><th>Rule</th><th>Category</th><th>Natural-language statement</th><th>Contract, traceability & models</th><th>Readiness, grounding and confidence</th><th>Review route</th><th>Source evidence</th></tr></thead><tbody>{''.join(rule_rows) or '<tr><td colspan="7">No rules were reported.</td></tr>'}</tbody></table></div></div></section>
<section id="dependencies" class="tab"><div class="panel"><div class="eyebrow">Relationship and dependency view</div><h2>Directed rule relationship graph</h2><p>These are the dependency edges emitted by the knowledge-graph optimizer and DAG generator. They are not treated as BPMN sequence flows. The graph preserves the emitted direction and groups nodes into degree layers for readable traversal. <strong>Click a rule</strong> to highlight it and its direct connections; everything else dims. Scroll to zoom, drag to pan.</p><div class="dependency-graph-shell"><div class="dependency-graph-toolbar"><h3>Dependency topology</h3><span class="muted">{len(dependency_layout["nodes"])} nodes · {len(dependency_layout["edges"])} unique directed edges · {len(dependency_layers)} degree layers</span></div><div class="dependency-graph-stats">{dependency_layer_chips}<span class="graph-layer-chip"><strong>isolated</strong> · {len(dependency_layout["isolated_nodes"])} nodes</span></div><div class="dependency-graph-layout"><div class="dependency-graph-scroll">{dependency_graph}</div><aside id="dep-side-panel" class="dep-side-panel" hidden></aside></div><p class="dependency-graph-note">{_safe(dependency_graph_note)} Hover an edge for its dependency type and full source → target direction.</p></div><div class="table-wrap"><table><thead><tr><th>Source rule</th><th>Target rule</th><th>Type</th></tr></thead><tbody>{edge_rows}</tbody></table></div></div></section>
<section id="review" class="tab"><div class="panel"><div class="eyebrow">Review management</div><h2>Human review, triaged by severity</h2><p>Every rule with an open review flag, in one dashboard. <strong>Severity</strong> is derived from review route and grounding status (a case-management route or a contradicted grounding verdict is <em>Critical</em>; a plain human-review route is <em>High</em>; machine-repair is <em>Medium</em>; everything else is <em>Low</em>) -- it is not a separately extracted field, so treat it as a triage aid, not ground truth.</p><div class="grid-2"><div class="callout"><strong>{human_review_count}</strong> rules are in the human-review queue (<strong>{report_data["human_review_rate"]:.1f}%</strong>).</div><div class="callout"><strong>{review_count}</strong> rules have quality holds (<strong>{report_data["quality_hold_rate"]:.1f}%</strong>); <strong>{nonhuman_quality_hold_count}</strong> are outside the human queue.</div></div><div class="toolbar"><input id="review-search" type="search" placeholder="Search rule ID or name…"><select id="review-severity"><option value="">All severities</option><option value="critical">Critical</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select><select id="review-route"><option value="">All routes</option>{route_options}</select><label class="muted" style="padding:9px 0"><input id="review-human-only" type="checkbox"> human-review only</label><span id="review-count" class="muted" style="padding:9px 0"></span></div><div class="table-wrap"><table id="review-table"><thead><tr><th>Severity</th><th>Rule</th><th>Route</th><th>Why flagged</th><th>Confidence</th><th>Evidence</th><th>Related rules</th></tr></thead><tbody>{''.join(review_rows) or '<tr><td colspan="7">No rules currently require review.</td></tr>'}</tbody></table></div></div></section>
<section id="sources" class="tab"><div class="panel"><div class="eyebrow">Source traceability</div><h2>Embedded source chunks</h2><p>These source blocks are embedded in this HTML file. Links from concepts, rules, and review items land on the exact referenced chunk/section without requiring filesystem access.</p>{''.join(source_blocks.values()) or '<div class="empty">No source references were present in the graph.</div>'}</div></section>
<footer>Policy Logic Forge Agent 12 · presentation-only artifact · source graph SHA-256: {_safe(hashlib.sha256(graph_file.read_bytes()).hexdigest())}</footer></div>
<script type="application/json" id="report-data">{_json_for_script(report_data)}</script><script>
const tabs=[...document.querySelectorAll('[data-tab]')], sections=[...document.querySelectorAll('section.tab')];
function activateTab(tabId){{tabs.forEach(item=>item.classList.toggle('active',item.dataset.tab===tabId));sections.forEach(section=>section.classList.toggle('active',section.id===tabId));}}
tabs.forEach(button=>button.addEventListener('click',()=>{{activateTab(button.dataset.tab);history.replaceState(null,'','#'+button.dataset.tab);}}));
const rows=[...document.querySelectorAll('#rules-table tbody .rule-row')], search=document.getElementById('rule-search'), category=document.getElementById('rule-category'), status=document.getElementById('rule-status'), route=document.getElementById('rule-route'), review=document.getElementById('review-only'), hasDmn=document.getElementById('filter-has-dmn'), hasBpmn=document.getElementById('filter-has-bpmn'), hasCmmn=document.getElementById('filter-has-cmmn'), count=document.getElementById('rule-count');
function applyFilters(){{const query=(search.value||'').toLowerCase(), cat=category.value, state=status.value, selectedRoute=route.value, only=review.checked;let visible=0;rows.forEach(row=>{{const matches=(!query||row.dataset.search.includes(query))&&(!cat||row.dataset.category===cat)&&(!state||row.dataset.status===state)&&(!selectedRoute||row.dataset.route===selectedRoute)&&(!only||row.dataset.review==='true')&&(!hasDmn.checked||row.dataset.hasDmn==='true')&&(!hasBpmn.checked||row.dataset.hasBpmn==='true')&&(!hasCmmn.checked||row.dataset.hasCmmn==='true');row.hidden=!matches;if(matches)visible++;}});count.textContent=visible+' of '+rows.length+' rules shown';}}
[search,category,status,route,review,hasDmn,hasBpmn,hasCmmn].forEach(control=>control&&control.addEventListener('input',applyFilters));applyFilters();
const conceptCards=[...document.querySelectorAll('#concept-grid .concept-card')], conceptSearch=document.getElementById('concept-search'), conceptKind=document.getElementById('concept-kind'), conceptEvidence=document.getElementById('concept-evidence'), conceptCount=document.getElementById('concept-count');
function applyConceptFilters(){{const query=(conceptSearch.value||'').toLowerCase(), kind=conceptKind.value, evidence=conceptEvidence.value;let visible=0;conceptCards.forEach(card=>{{const matches=(!query||card.dataset.search.includes(query))&&(!kind||card.dataset.kind===kind)&&(!evidence||card.dataset.evidence===evidence);card.hidden=!matches;if(matches)visible++;}});conceptCount.textContent=visible+' of '+conceptCards.length+' concepts shown';}}
[conceptSearch,conceptKind,conceptEvidence].forEach(control=>control&&control.addEventListener('input',applyConceptFilters));applyConceptFilters();
const reviewRows=[...document.querySelectorAll('#review-table tbody .review-row')], reviewSearch=document.getElementById('review-search'), reviewSeverity=document.getElementById('review-severity'), reviewRoute=document.getElementById('review-route'), reviewHumanOnly=document.getElementById('review-human-only'), reviewCount=document.getElementById('review-count');
function applyReviewFilters(){{if(!reviewRows.length)return;const query=(reviewSearch.value||'').toLowerCase(), sev=reviewSeverity.value, selectedRoute=reviewRoute.value, humanOnly=reviewHumanOnly.checked;let visible=0;reviewRows.forEach(row=>{{const matches=(!query||row.dataset.search.includes(query))&&(!sev||row.dataset.severity===sev)&&(!selectedRoute||row.dataset.route===selectedRoute)&&(!humanOnly||row.dataset.human==='true');row.hidden=!matches;if(matches)visible++;}});reviewCount.textContent=visible+' of '+reviewRows.length+' review items shown';}}
[reviewSearch,reviewSeverity,reviewRoute,reviewHumanOnly].forEach(control=>control&&control.addEventListener('input',applyReviewFilters));applyReviewFilters();
function revealTarget(id){{const el=document.getElementById(id);if(!el)return false;const tabSection=el.closest('section.tab');if(tabSection)activateTab(tabSection.id);let node=el.parentElement;while(node){{if(node.tagName==='DETAILS'&&!node.open)node.open=true;node=node.parentElement;}}el.scrollIntoView({{behavior:'smooth',block:'start'}});el.classList.add('nav-highlight');setTimeout(()=>el.classList.remove('nav-highlight'),1600);return true;}}
document.addEventListener('click',event=>{{const anchor=event.target.closest('a[href^="#"]');if(!anchor)return;const id=anchor.getAttribute('href').slice(1);if(!id||!document.getElementById(id))return;event.preventDefault();revealTarget(id);history.replaceState(null,'','#'+id);}});
if(location.hash)revealTarget(location.hash.slice(1));
(function(){{
  const reportData=JSON.parse(document.getElementById('report-data').textContent);
  const edges=reportData.dependency_edges||[], ruleSummary=reportData.rule_summary||{{}};
  const adjacency={{}};
  edges.forEach(e=>{{const s=e.source_rule_id,t=e.target_rule_id;(adjacency[s]=adjacency[s]||new Set()).add(t);(adjacency[t]=adjacency[t]||new Set()).add(s);}});
  const panel=document.getElementById('dep-side-panel');
  function clearDepSelection(){{document.querySelectorAll('.dependency-node,.dependency-edge').forEach(el=>el.classList.remove('selected','neighbor','dimmed','active'));if(panel)panel.hidden=true;}}
  function renderDepPanel(id,neighbors){{if(!panel)return;const info=ruleSummary[id]||{{}};const items=[...neighbors].sort().map(n=>{{const ninfo=ruleSummary[n]||{{}};return '<li><a href="#" data-dep-jump="'+n+'">'+n+'</a><span class="muted">'+(ninfo.category||'')+'</span></li>';}}).join('')||'<li class="muted">No direct connections</li>';const conf=(info.confidence!=null)?info.confidence.toFixed(1)+'%':'—';panel.innerHTML='<div class="dep-panel-head"><strong>'+id+'</strong><button type="button" class="dep-panel-close" aria-label="Close">×</button></div><div class="muted">'+(info.name||'')+'</div><div class="dep-panel-meta"><span>'+(info.category||'Uncategorized')+'</span><span>'+(info.status||'')+'</span><span>'+conf+'</span></div><a class="evidence-link" href="#rule-'+(info.slug||id)+'">Open rule →</a><h4>Direct connections ('+neighbors.size+')</h4><ul class="dep-panel-list">'+items+'</ul>';panel.hidden=false;panel.querySelectorAll('[data-dep-jump]').forEach(a=>a.addEventListener('click',e=>{{e.preventDefault();selectDepNode(a.dataset.depJump);}}));const closeBtn=panel.querySelector('.dep-panel-close');if(closeBtn)closeBtn.addEventListener('click',clearDepSelection);}}
  function selectDepNode(id){{const neighbors=adjacency[id]||new Set();document.querySelectorAll('.dependency-node').forEach(node=>{{const nid=node.dataset.nodeId;node.classList.toggle('selected',nid===id);node.classList.toggle('neighbor',neighbors.has(nid));node.classList.toggle('dimmed',nid!==id&&!neighbors.has(nid));}});document.querySelectorAll('.dependency-edge').forEach(edge=>{{const active=edge.dataset.source===id||edge.dataset.target===id;edge.classList.toggle('active',active);edge.classList.toggle('dimmed',!active);}});renderDepPanel(id,neighbors);}}
  document.querySelectorAll('.dependency-node').forEach(node=>node.addEventListener('click',event=>{{event.stopPropagation();selectDepNode(node.dataset.nodeId);}}));
  const svg=document.querySelector('.dependency-graph-svg');
  if(svg){{
    let dragMoved=false;
    svg.addEventListener('click',event=>{{if(!dragMoved&&!event.target.closest('.dependency-node'))clearDepSelection();}});
    const vb=svg.viewBox.baseVal;let vx=vb.x,vy=vb.y,vw=vb.width,vh=vb.height;const baseW=vw,baseH=vh,minScale=0.3,maxScale=4;
    function apply(){{svg.setAttribute('viewBox',vx+' '+vy+' '+vw+' '+vh);}}
    svg.addEventListener('wheel',event=>{{event.preventDefault();const factor=event.deltaY>0?1.1:0.9;const newW=Math.min(baseW/minScale,Math.max(baseW/maxScale,vw*factor));const newH=newW*(baseH/baseW);const rect=svg.getBoundingClientRect();const mx=vx+(event.clientX-rect.left)/rect.width*vw;const my=vy+(event.clientY-rect.top)/rect.height*vh;vx=mx-(mx-vx)*(newW/vw);vy=my-(my-vy)*(newH/vh);vw=newW;vh=newH;apply();}},{{passive:false}});
    let dragging=false,lastX=0,lastY=0;
    svg.addEventListener('mousedown',event=>{{dragging=true;dragMoved=false;lastX=event.clientX;lastY=event.clientY;svg.classList.add('grabbing');}});
    window.addEventListener('mousemove',event=>{{if(!dragging)return;if(Math.abs(event.clientX-lastX)+Math.abs(event.clientY-lastY)>3)dragMoved=true;const rect=svg.getBoundingClientRect();vx-=(event.clientX-lastX)/rect.width*vw;vy-=(event.clientY-lastY)/rect.height*vh;lastX=event.clientX;lastY=event.clientY;apply();}});
    window.addEventListener('mouseup',()=>{{dragging=false;svg.classList.remove('grabbing');}});
  }}
}})();
</script></body></html>'''
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / REPORT_FILE_NAME
    _validate_report_html(report_html, [str(rule.get("rule_id") or "unidentified") for rule in rules], list(source_blocks))
    output_path.write_text(report_html, encoding="utf-8")
    manifest = {**report_data, "report_file": str(output_path), "report_size_bytes": output_path.stat().st_size, "validation": "pass"}
    (output_dir / "business_knowledge_report_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path)
    parser.add_argument("--dags", type=Path)
    parser.add_argument("--models-dir", type=Path)
    parser.add_argument("--organized-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--batch-name", help="Read the configured pipeline-output/<batch-name> bundle")
    parser.add_argument("--domain", help="Set KG_DOMAIN before resolving configured paths")
    args = parser.parse_args(argv)
    if args.batch_name:
        os.environ["KG_BATCH_NAME"] = args.batch_name
    if args.domain:
        os.environ["KG_DOMAIN"] = args.domain
    config = get_config()
    graph = args.graph or (config.get_optimized_dir() / "optimized_compliance_knowledge_graph.json")
    dags = args.dags or (config.get_dag_dir() / "dependency_dags.json")
    models = args.models_dir or config.get_executable_models_dir()
    organized = args.organized_dir or config.get_organized_dir()
    configured_output = getattr(config, "get_business_report_dir", None)
    output = args.output_dir or (configured_output() if configured_output else config.get_pipeline_base_path() / REPORT_DIR_NAME)
    missing = [str(path) for path in (graph,) if not path.exists()]
    if missing:
        print("ERROR: required upstream artifact(s) missing: " + ", ".join(missing), flush=True)
        return 2
    try:
        report = generate(graph, dags if dags.exists() else None, models, output, organized)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: business knowledge report generation failed: {exc}", flush=True)
        return 2
    print(f"Generated self-contained business knowledge report for {report['rule_count']} rules and {report['concept_count']} concepts: {output / REPORT_FILE_NAME}", flush=True)
    print(f"Human-review queue: {report['human_review_count']} ({report['human_review_rate']}%); quality holds: {report['quality_hold_count']} ({report['quality_hold_rate']}%); grounding-certified: {report['grounding_coverage_rate']}%; source-pointer coverage: {report['source_pointer_coverage_rate']}%", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
