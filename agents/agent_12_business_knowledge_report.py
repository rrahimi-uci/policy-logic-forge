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
    """Return every graph-supported concept, including rule variables.

    The existing SBVR profile contains entity concepts and fact types.  Rules
    also introduce decision variables and named related entities, so those are
    promoted into the report vocabulary rather than silently omitted.
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

    for _rid, rule in _all_rule_refs(graph):
        refs = _rule_references(rule)
        for entity in _list(rule.get("related_entities")) + [rule.get("source_entity"), rule.get("responsible_party"), rule.get("entity_type")]:
            if entity:
                add(entity, kind="actor_role" if entity == rule.get("responsible_party") else "business_object", refs=refs)
        for variable in _list(rule.get("variables")):
            if isinstance(variable, Mapping) and variable.get("name"):
                add(variable.get("name"), kind="decision_variable", definition=f"{variable.get('role', 'policy')} variable of type {variable.get('type', 'unknown')}", refs=refs)
        for outcome in _list(rule.get("outcomes")):
            if isinstance(outcome, Mapping) and outcome.get("variable"):
                add(outcome.get("variable"), kind="decision_variable", refs=refs)
    return [concepts[key] for key in sorted(concepts, key=str.casefold)]


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
    for key in ("confidence", "extraction_confidence", "grounding_confidence"):
        value = rule.get(key)
        try:
            if value is not None:
                number = float(value)
                return number * 100 if 0 <= number <= 1 else number
        except (TypeError, ValueError):
            continue
    return None


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


def _svg(title: str, labels: Sequence[str], color: str) -> str:
    width = 760
    row_height = 34
    height = max(110, 62 + row_height * min(len(labels), 20))
    rows = labels[:20]
    body = [f'<svg class="model-svg" viewBox="0 0 {width} {height}" role="img" aria-label="{_safe(title)}">', f'<text x="24" y="30" class="svg-title">{_safe(title)}</text>']
    if not rows:
        body.append('<text x="24" y="70" class="svg-empty">No applicable elements were generated.</text>')
    for index, label in enumerate(rows):
        y = 48 + index * row_height
        body.append(f'<rect x="24" y="{y}" width="700" height="24" rx="8" fill="{color}" opacity=".16" stroke="{color}"/>')
        body.append(f'<text x="38" y="{y + 16}" class="svg-label">{_safe(label)}</text>')
    if len(labels) > len(rows):
        body.append(f'<text x="24" y="{height - 12}" class="svg-empty">Showing first {len(rows)} of {len(labels)}; full coverage is available in the explorer.</text>')
    body.append("</svg>")
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


def _validate_report_html(document: str, rule_ids: Sequence[str], source_anchors: Sequence[str]) -> None:
    """Validate the non-network, single-document report contract."""
    required = ('<!doctype html>', 'id="report-data"', 'data-tab="vocabulary"', 'data-tab="rules"', 'data-tab="models"', 'data-tab="review"', 'data-tab="sources"', 'id="concept-search"', 'id="concept-grid"', 'id="fact-types"')
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


def _rule_row(rule: Mapping[str, Any], source_anchors: Sequence[str]) -> str:
    rid = str(rule.get("rule_id") or "unidentified")
    category, subcategory = _category(rule)
    review = bool(rule.get("requires_review", False))
    review_route = str(_mapping(rule.get("review_route")).get("route") or ("unclassified" if review else "none"))
    grounding = _mapping(rule.get("grounding"))
    grounding_status = str(grounding.get("status") or rule.get("extraction_status") or "unknown")
    status = "review_required" if review else ("verified" if grounding_status == "certified" else grounding_status)
    confidence = _confidence(rule)
    confidence_text = f"{confidence:.1f}%" if confidence is not None else "—"
    reason_items = _review_reasons(rule)
    reasons = "".join(f"<li>{_safe(item)}</li>" for item in reason_items) or "<li>No review reason recorded.</li>"
    refs = " ".join(f'<a class="evidence-link" href="#{_safe(anchor)}">Evidence {index + 1}</a>' for index, anchor in enumerate(source_anchors)) or '<span class="muted">Unresolved source</span>'
    formal = {"conditions": rule.get("condition_predicates", []), "outcomes": rule.get("outcomes", []), "exceptions": rule.get("exceptions", []), "dependencies": rule.get("dependencies", []), "related_entities": rule.get("related_entities", [])}
    return f'''<tr id="rule-{_safe(_slug(rid))}" class="rule-row" data-category="{_safe(category)}" data-status="{_safe(status)}" data-route="{_safe(review_route)}" data-review="{str(review).lower()}" data-search="{_safe((rid + ' ' + str(rule.get('rule_name', '')) + ' ' + _rule_statement(rule) + ' ' + category + ' ' + subcategory).casefold())}">
      <td><a href="#rule-{_safe(_slug(rid))}">{_safe(rid)}</a><div class="muted">{_safe(rule.get('rule_name') or 'Untitled rule')}</div></td>
      <td>{_safe(category)}<div class="muted">{_safe(subcategory)}</div></td>
      <td>{_safe(_rule_statement(rule))}</td>
      <td><details><summary>Inspect</summary><pre>{_safe(json.dumps(formal, indent=2, ensure_ascii=False))}</pre></details></td>
      <td><span class="status status-{_safe(status.casefold().replace(' ', '_'))}">{_safe(status)}</span><div class="muted">grounding: {_safe(grounding_status)}</div><div>{confidence_text}</div></td>
      <td><span class="status status-{_safe(review_route.casefold().replace(' ', '_'))}">{_safe(review_route.replace('_', ' '))}</span><div>{'Quality hold' if review else 'No quality hold'}</div><details><summary>Why</summary><ul>{reasons}</ul></details></td>
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
    chunks, chunk_list = _source_chunks(organized_dir)
    rules = [dict(rule) for rule in _list(graph.get("business_rules")) if isinstance(rule, Mapping)]
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
    edges = dependency_edges(graph)
    categories = Counter(_category(rule)[0] for rule in rules)
    review_count = sum(bool(rule.get("requires_review")) for rule in rules)
    human_review_count = sum(bool(_mapping(rule.get("review_route")).get("human_review_required")) for rule in rules)
    route_counts = Counter(str(_mapping(rule.get("review_route")).get("route") or ("unclassified" if rule.get("requires_review") else "none")) for rule in rules)
    nonhuman_quality_hold_count = sum(
        bool(rule.get("requires_review"))
        and not bool(_mapping(rule.get("review_route")).get("human_review_required"))
        for rule in rules
    )
    grounded_count = sum(bool(_rule_references(rule)) for rule in rules)
    confidence_values = [value for rule in rules if (value := _confidence(rule)) is not None]
    confidence_buckets = Counter("90–100%" if value >= 90 else "75–89%" if value >= 75 else "50–74%" if value >= 50 else "0–49%" for value in confidence_values)
    unresolved = sum(1 for rule in rules if _review_reasons(rule))
    source_documents = {str(ref.get("chunk_path") or ref.get("document") or "").split("/")[0] for rule in rules for ref in _rule_references(rule) if ref.get("chunk_path") or ref.get("document")}
    concept_supported = len(concepts)
    vocabulary_coverage = 100.0 if concept_supported == len(concepts) else 0.0
    concept_ids = {str(concept.get("concept_id")) for concept in concepts}
    concept_kind_counts = Counter(str(concept.get("concept_kind") or "unresolved") for concept in concepts)
    concept_rule_usage: Counter[str] = Counter()
    for rule in rules:
        referenced = set(str(value) for value in _list(rule.get("related_entities")) if value)
        referenced.update(str(value) for value in (rule.get("source_entity"), rule.get("responsible_party"), rule.get("entity_type")) if value)
        referenced.update(
            str(item.get("name")) for item in _list(rule.get("variables"))
            if isinstance(item, Mapping) and item.get("name")
        )
        referenced.update(
            str(item.get("variable")) for item in _list(rule.get("outcomes"))
            if isinstance(item, Mapping) and item.get("variable")
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
        "review_route_counts": dict(sorted(route_counts.items())),
        "grounded_rule_count": grounded_count, "grounding_coverage_rate": round(grounded_count / max(1, len(rules)) * 100, 2),
        "source_document_count": len(source_documents), "source_chunk_count": len(chunk_list),
        "concept_coverage_rate": vocabulary_coverage, "concept_coverage_scope": "all concepts represented in the input graph",
        "concept_review_count": sum(str(concept.get("concept_kind")) == "unresolved" for concept in concepts),
        "concept_kind_counts": dict(sorted(concept_kind_counts.items())),
        "concepts_with_evidence": concept_evidence_count,
        "concept_evidence_coverage_rate": _percent(concept_evidence_count, concept_supported),
        "concept_orphan_count": concept_orphan_count,
        "fact_type_count": len(fact_types),
        "fact_type_grounded_count": fact_grounded_count,
        "fact_type_grounding_rate": _percent(fact_grounded_count, len(fact_types)),
        "fact_type_status_counts": dict(sorted(fact_status_counts.items())),
        "top_concepts": top_concepts,
        "unresolved_item_count": unresolved,
        "confidence_distribution": dict(sorted(confidence_buckets.items())), "categories": dict(categories),
        "model_info": model_info, "edge_count": len(edges), "source_graph": str(graph_file),
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
    rule_rows = [_rule_row(rule, rule_sources.get(str(rule.get("rule_id") or "unidentified"), [])) for rule in rules]
    human_review_rows: list[str] = []
    quality_hold_rows: list[str] = []
    for rule in rules:
        if not rule.get("requires_review"):
            continue
        rid = str(rule.get("rule_id") or "unidentified")
        review_route = str(_mapping(rule.get("review_route")).get("route") or "unclassified")
        reasons = _review_reasons(rule) or ["Review flag set without a detailed reason."]
        reason_html = "".join(f"<li>{_safe(reason)}</li>" for reason in reasons)
        evidence_html = " ".join(
            f'<a class="evidence-link" href="#{_safe(anchor)}">Evidence</a>'
            for anchor in rule_sources.get(rid, [])
        ) or "Unresolved source"
        confidence = _confidence(rule)
        row = (
            f'<tr><td><a href="#rule-{_safe(_slug(rid))}">{_safe(rid)}</a></td>'
            f'<td><span class="status status-{_safe(review_route.casefold().replace(" ", "_"))}">{_safe(review_route.replace("_", " "))}</span></td>'
            f'<td><ul>{reason_html}</ul></td>'
            f'<td>{_safe(f"{confidence:.1f}%" if confidence is not None else "—")}</td>'
            f'<td>{evidence_html}</td></tr>'
        )
        if bool(_mapping(rule.get("review_route")).get("human_review_required")):
            human_review_rows.append(row)
        else:
            quality_hold_rows.append(row)
    category_rows = "".join(f'<tr><td>{_safe(category)}</td><td>{count}</td><td>{round(count / max(1, len(rules)) * 100, 1)}%</td></tr>' for category, count in sorted(categories.items(), key=lambda item: (-item[1], item[0].casefold())))
    confidence_rows = "".join(f'<tr><td>{_safe(bucket)}</td><td>{count}</td></tr>' for bucket, count in sorted(confidence_buckets.items())) or '<tr><td>Not reported</td><td>0</td></tr>'
    edge_rows = "".join(f'<tr><td>{_safe(edge.get("source_rule_id"))}</td><td>{_safe(edge.get("target_rule_id"))}</td><td>{_safe(edge.get("dependency_type", "unknown"))}</td></tr>' for edge in edges[:500]) or '<tr><td colspan="3">No dependency edges were reported.</td></tr>'
    route_options = "".join(f'<option value="{_safe(route)}">{_safe(route.replace("_", " "))}</option>' for route in sorted(route_counts, key=str.casefold))
    kind_colors = {"actor_role": "#27c2a5", "business_object": "#7c83fd", "decision_variable": "#f3a94b", "evidence_object": "#5a8dee", "event": "#d85d69", "process": "#8f6be8", "unresolved": "#a9b3c3"}
    kind_bars = "".join(_progress_bar(kind.replace("_", " "), count, concept_supported, kind_colors.get(kind, "#7c83fd")) for kind, count in sorted(concept_kind_counts.items(), key=lambda item: (-item[1], item[0])))
    top_concept_rows = "".join(
        f'<li><a href="#concept-{_safe(_slug(item["concept_id"]))}">{_safe(item["preferred_term"])}</a><span class="muted">{item["rule_links"]} rule links · {item["fact_links"]} fact endpoints</span></li>'
        for item in top_concepts if item["rule_links"] or item["fact_links"]
    ) or '<li class="muted">No connected concepts were reported.</li>'
    fact_status_rows = "".join(f'<tr><td>{_safe(status)}</td><td>{count}</td><td>{_percent(count, len(fact_types)):.1f}%</td></tr>' for status, count in sorted(fact_status_counts.items(), key=lambda item: (-item[1], item[0]))) or '<tr><td>Not reported</td><td>0</td><td>0.0%</td></tr>'
    model_cards = []
    colors = {"DMN": "#27c2a5", "BPMN": "#7c83fd", "CMMN": "#f3a94b"}
    for kind in ("DMN", "BPMN", "CMMN"):
        info = model_info[kind]
        labels = [f"{rid} · linked rule" for rid in info["rule_ids"]]
        note = "Generated" if info["exists"] and not info.get("parse_error") else "Not generated or unavailable"
        linked_rules = " ".join(f'<a class="evidence-link" href="#rule-{_safe(_slug(rid))}">{_safe(rid)}</a>' for rid in info["rule_ids"]) or '<span class="muted">No linked rule IDs</span>'
        model_cards.append(f'<article class="model-card"><div class="eyebrow">{kind}</div><h3>{_safe(note)}</h3><p>{len(info["rule_ids"])} linked rules · {info["element_count"]} XML elements</p><div>{linked_rules}</div>{_svg(kind + " coverage", labels, colors[kind])}<details><summary>Artifact</summary><pre>{_safe(info["file"])}</pre></details></article>')

    report_html = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Business Knowledge Report</title>
<style>
:root{{--ink:#17253d;--muted:#6f7d91;--line:#e4eaf2;--paper:#fff;--wash:#f5f8fc;--teal:#27c2a5;--violet:#7c83fd;--amber:#f3a94b;--red:#d85d69;--shadow:0 18px 50px rgba(23,37,61,.08)}}*{{box-sizing:border-box}}body{{margin:0;color:var(--ink);background:var(--wash);font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}}a{{color:#4251bd;text-decoration:none}}a:hover{{text-decoration:underline}}button,input,select{{font:inherit}}.shell{{max-width:1560px;margin:auto;padding:26px}}header.hero{{background:linear-gradient(125deg,#17253d,#2b4169 55%,#5165ce);border-radius:24px;color:#fff;padding:34px;box-shadow:var(--shadow);position:relative;overflow:hidden}}header.hero:after{{content:"";position:absolute;width:320px;height:320px;border-radius:50%;right:-90px;top:-130px;background:rgba(39,194,165,.22)}}.eyebrow{{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--teal);font-weight:800}}.hero h1{{font-size:clamp(28px,4vw,48px);line-height:1.05;max-width:800px;margin:10px 0}}.hero p{{max-width:800px;color:#dce7f7;font-size:16px}}.metric-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:18px 0 26px}}.metric-card,.panel,.model-card{{background:var(--paper);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow)}}.metric-card{{padding:18px}}.metric-value{{font-size:27px;font-weight:800}}.metric-label{{font-weight:750;margin-top:2px}}.metric-detail,.muted{{color:var(--muted);font-size:12px}}nav.tabs{{display:flex;gap:8px;flex-wrap:wrap;margin:20px 0}}nav.tabs button{{border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:999px;padding:10px 16px;cursor:pointer;font-weight:700}}nav.tabs button.active{{background:var(--ink);color:#fff;border-color:var(--ink)}}section.tab{{display:none}}section.tab.active{{display:block}}.panel{{padding:22px;margin:14px 0}}.panel h2,.panel h3{{margin-top:0}}.grid-2{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:11px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);background:#f8fafd;position:sticky;top:0;z-index:1}}tr:hover td{{background:#fbfcff}}.table-wrap{{overflow:auto;max-height:720px;border:1px solid var(--line);border-radius:12px}}.toolbar{{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}}.toolbar input,.toolbar select{{border:1px solid var(--line);border-radius:9px;padding:9px 11px;background:#fff;min-width:190px}}.status{{display:inline-block;border-radius:999px;padding:3px 8px;font-size:11px;font-weight:800;background:#e9f7f3;color:#087760}}.status-review_required,.status-unresolved{{background:#fff1df;color:#92570a}}.status-fail,.status-contradicted{{background:#ffe8eb;color:#9d2937}}details summary{{cursor:pointer;color:#4251bd;font-weight:650}}pre{{white-space:pre-wrap;word-break:break-word;background:#f7f9fc;border-radius:9px;padding:12px;font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;max-height:360px;overflow:auto}}.evidence-link{{display:inline-block;margin:2px 4px 2px 0;padding:2px 7px;border-radius:99px;background:#eef1ff;font-size:11px}}.model-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:14px}}.model-card{{padding:18px}}.model-svg{{width:100%;height:auto;background:#fbfcff;border-radius:12px;margin-top:10px}}.svg-title{{font-size:16px;font-weight:800;fill:var(--ink)}}.svg-label{{font-size:11px;fill:var(--ink)}}.svg-empty{{font-size:12px;fill:var(--muted)}}.source-card{{border:1px solid var(--line);background:#fff;border-radius:12px;padding:16px;margin:10px 0;scroll-margin-top:20px}}.source-card h4{{margin:0 0 4px;font-size:14px;word-break:break-all}}.source-meta{{color:var(--muted);font-size:11px;margin-bottom:8px}}.callout{{border-left:4px solid var(--teal);padding:12px 16px;background:#effaf7;border-radius:8px}}.empty{{padding:30px;text-align:center;color:var(--muted)}}footer{{padding:28px 0;color:var(--muted);font-size:12px}}@media(max-width:700px){{.shell{{padding:12px}}header.hero{{padding:24px 20px}}th,td{{min-width:130px}}}}
 .insight-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:16px 0}}.insight-card{{background:linear-gradient(145deg,#f7fbff,#fff);border:1px solid var(--line);border-radius:14px;padding:16px}}.insight-card .metric-value{{font-size:24px}}.insight-card h3{{font-size:13px;margin:0 0 4px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}}.insight-bar-row{{margin:12px 0}}.insight-bar-label{{display:flex;justify-content:space-between;gap:12px;text-transform:capitalize}}.insight-bar-track{{height:8px;background:#edf1f7;border-radius:99px;overflow:hidden;margin:6px 0 3px}}.insight-bar-track span{{display:block;height:100%;border-radius:99px}}.insight-list{{margin:0;padding:0;list-style:none}}.insight-list li{{display:flex;justify-content:space-between;gap:12px;padding:9px 0;border-bottom:1px solid var(--line)}}.insight-list li:last-child{{border-bottom:0}}.concept-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:14px;margin-top:16px}}.concept-card{{background:#fff;border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 10px 28px rgba(23,37,61,.05);scroll-margin-top:20px}}.concept-card:hover{{border-color:#b9c4ff;box-shadow:0 14px 34px rgba(66,81,189,.12)}}.concept-card-head{{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}}.concept-term{{font-size:18px;font-weight:800;line-height:1.2}}.concept-card p{{color:#4e5e73;min-height:42px}}.concept-meta{{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0;color:var(--muted);font-size:12px}}.concept-meta span{{padding:5px 8px;background:#f5f7fb;border-radius:999px}}.concept-detail{{display:grid;gap:12px;padding-top:10px}}.concept-detail strong{{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}}.vocabulary-toolbar{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:14px 0}}.vocabulary-toolbar input,.vocabulary-toolbar select{{border:1px solid var(--line);border-radius:9px;padding:9px 11px;background:#fff;min-width:190px}}.vocabulary-toolbar output{{color:var(--muted);font-size:12px}}.fact-table{{margin-top:18px}}.status-case_management{{background:#eef1ff;color:#4251bd}}.status-human_review{{background:#ffe8eb;color:#9d2937}}.status-machine_repair{{background:#e9f7f3;color:#087760}}.status-presented{{background:#e9f7f3;color:#087760}}.status-unverified{{background:#fff1df;color:#92570a}}
 </style></head><body><div class="shell">
<header class="hero"><div class="eyebrow">Agent 12 · presentation and knowledge exploration</div><h1>Business knowledge, ready to review.</h1><p>A self-contained, source-traceable view of the extracted domain. Navigate from SBVR concepts to rules, decisions, workflows, review findings, and the exact evidence that supports each result.</p><div class="muted" style="color:#cbd9ee">Generated from {_safe(graph_file.name)} · no external assets or network calls required</div></header>
<div class="metric-grid">{_metric_card('Business rules', len(rules), 'All extracted rules shown')}{_metric_card('SBVR concepts', concept_supported, f'{vocabulary_coverage:.1f}% graph-supported coverage')}{_metric_card('Human-review queue', f'{human_review_count} ({report_data["human_review_rate"]:.1f}%)', 'Explicit human judgment required')}{_metric_card('Quality holds', f'{review_count} ({report_data["quality_hold_rate"]:.1f}%)', 'Fail-closed evidence or contract findings')}{_metric_card('Case-management cases', route_counts.get('case_management', 0), 'Evidence work outside the human queue')}{_metric_card('Grounded rules', f'{grounded_count} ({report_data["grounding_coverage_rate"]:.1f}%)', 'At least one source pointer')}{_metric_card('Source documents', len(source_documents), f'{len(chunk_list)} indexed chunks')}{_metric_card('Dependencies', len(edges), 'DAG edges available')}</div>
<nav class="tabs" aria-label="Report sections"><button class="active" data-tab="overview">Overview</button><button data-tab="vocabulary">SBVR vocabulary</button><button data-tab="rules">Rule explorer</button><button data-tab="models">Decision & process models</button><button data-tab="dependencies">Relationships</button><button data-tab="review">Review queue</button><button data-tab="sources">Source traceability</button></nav>
<section id="overview" class="tab active"><div class="grid-2"><div class="panel"><div class="eyebrow">Executive summary</div><h2>What this domain contains</h2><p>The report presents <strong>{len(rules)}</strong> rules across <strong>{len(categories)}</strong> categories and <strong>{concept_supported}</strong> SBVR-aligned concepts. The source graph supports <strong>{len(source_documents)}</strong> document roots and <strong>{len(edges)}</strong> dependency relationships.</p><div class="callout">Every displayed rule and concept has an evidence link when the upstream graph provides a source pointer. Missing pointers stay visible as unresolved rather than being replaced by invented citations.</div></div><div class="panel"><div class="eyebrow">Coverage and quality</div><h2>At a glance</h2><table><tr><td>Concept coverage</td><td><strong>{vocabulary_coverage:.1f}%</strong></td></tr><tr><td>Rule source-pointer coverage</td><td><strong>{report_data["grounding_coverage_rate"]:.1f}%</strong></td></tr><tr><td>Human-review queue</td><td><strong>{report_data["human_review_rate"]:.1f}%</strong> ({human_review_count} rules)</td></tr><tr><td>Case-management route</td><td><strong>{route_counts.get("case_management", 0) / max(1, len(rules)) * 100:.1f}%</strong> ({route_counts.get("case_management", 0)} rules)</td></tr><tr><td>Quality holds</td><td><strong>{report_data["quality_hold_rate"]:.1f}%</strong> ({review_count} rules)</td></tr></table></div></div><div class="grid-2"><div class="panel"><h3>Rule categories</h3><div class="table-wrap"><table><thead><tr><th>Category</th><th>Rules</th><th>Share</th></tr></thead><tbody>{category_rows or '<tr><td colspan="3">No categories reported.</td></tr>'}</tbody></table></div></div><div class="panel"><h3>Confidence distribution</h3><div class="table-wrap"><table><thead><tr><th>Band</th><th>Rules</th></tr></thead><tbody>{confidence_rows}</tbody></table></div></div></div></section>
<section id="vocabulary" class="tab"><div class="panel"><div class="eyebrow">SBVR-aligned business vocabulary</div><h2>Vocabulary workbench</h2><p>Explore the domain lexicon as typed concepts and fact types. The view is grounded in the input graph: definitions, usage counts, relationships, and evidence links are shown only when the upstream artifacts provide them.</p><div class="insight-grid"><div class="insight-card"><h3>Supported concepts</h3><div class="metric-value">{concept_supported}</div><div class="muted">{report_data["concept_coverage_rate"]:.1f}% graph-supported coverage</div></div><div class="insight-card"><h3>Evidence coverage</h3><div class="metric-value">{report_data["concept_evidence_coverage_rate"]:.1f}%</div><div class="muted">{concept_evidence_count} concepts have source evidence</div></div><div class="insight-card"><h3>Fact types</h3><div class="metric-value">{len(fact_types)}</div><div class="muted">{fact_grounded_count} grounded · {report_data["fact_type_grounding_rate"]:.1f}%</div></div><div class="insight-card"><h3>Unresolved / orphaned</h3><div class="metric-value">{report_data["concept_review_count"]} / {concept_orphan_count}</div><div class="muted">Unresolved kinds / no rule or fact links</div></div></div><div class="grid-2"><div class="panel"><h3>Concept type mix</h3><p class="muted">How the vocabulary is distributed across SBVR-aligned concept kinds.</p>{kind_bars}</div><div class="panel"><h3>Most connected concepts</h3><p class="muted">Concepts with the strongest links into rules and fact types.</p><ul class="insight-list">{top_concept_rows}</ul></div></div><div class="panel"><div class="eyebrow">Concept explorer</div><h3>Find a term, definition, or concept kind</h3><div class="vocabulary-toolbar"><input id="concept-search" type="search" placeholder="Search concepts and definitions…"><select id="concept-kind"><option value="">All kinds</option>{''.join(f'<option value="{_safe(kind)}">{_safe(kind.replace("_", " "))}</option>' for kind in sorted(concept_kind_counts, key=str.casefold))}</select><select id="concept-evidence"><option value="">All evidence states</option><option value="grounded">With source evidence</option><option value="unresolved">Evidence unresolved</option></select><output id="concept-count" for="concept-search"></output></div><div id="concept-grid" class="concept-grid">{''.join(concept_rows) or '<div class="empty">No concepts were reported.</div>'}</div></div><div id="fact-types" class="panel fact-table"><div class="eyebrow">SBVR fact types</div><h3>Relationships and grounding status</h3><p class="muted">Each endpoint links back to its concept card; evidence links land on the embedded source block.</p><div class="grid-2"><div class="table-wrap"><table><thead><tr><th>Grounding status</th><th>Fact types</th><th>Share</th></tr></thead><tbody>{fact_status_rows}</tbody></table></div><div class="callout"><strong>{len(fact_types)}</strong> fact types connect <strong>{len(concept_ids)}</strong> concepts. A fact type is a vocabulary relationship, not a workflow sequence.</div></div><div class="table-wrap" style="margin-top:14px"><table><thead><tr><th>Fact type</th><th>Subject</th><th>Verb</th><th>Object</th><th>Grounding and evidence</th></tr></thead><tbody>{''.join(fact_rows) or '<tr><td colspan="5">No fact types were reported.</td></tr>'}</tbody></table></div></div></div></section>
<section id="rules" class="tab"><div class="panel"><div class="eyebrow">Structured rule explorer</div><h2>Business rules</h2><div class="toolbar"><input id="rule-search" type="search" placeholder="Search ID, title, statement, category…"><select id="rule-category"><option value="">All categories</option>{''.join(f'<option>{_safe(category)}</option>' for category in sorted(categories, key=str.casefold))}</select><select id="rule-status"><option value="">All statuses</option><option value="review_required">Quality hold</option><option value="verified">Verified</option><option value="unresolved">Unresolved</option></select><select id="rule-route"><option value="">All routes</option>{route_options}</select><label class="muted" style="padding:9px 0"><input id="review-only" type="checkbox"> quality holds only</label><span id="rule-count" class="muted" style="padding:9px 0"></span></div><div class="table-wrap"><table id="rules-table"><thead><tr><th>Rule</th><th>Category</th><th>Natural-language statement</th><th>Formal logic</th><th>Confidence/status</th><th>Review route</th><th>Source evidence</th></tr></thead><tbody>{''.join(rule_rows) or '<tr><td colspan="7">No rules were reported.</td></tr>'}</tbody></table></div></div></section>
<section id="models" class="tab"><div class="panel"><div class="eyebrow">Business process and decision models</div><h2>Models generated by Agent 11</h2><p>DMN, BPMN, and CMMN are shown as review projections and linked by rule IDs. BPMN is displayed only when the upstream semantic-routing gate found explicit ordered workflow semantics; obvious rules remain in DMN/rule views without invented process flows.</p><div class="model-grid">{''.join(model_cards)}</div></div></section>
<section id="dependencies" class="tab"><div class="panel"><div class="eyebrow">Relationship and dependency view</div><h2>Rule-to-rule dependencies</h2><p>These are the dependency edges emitted by the knowledge-graph optimizer and DAG generator. They are not treated as BPMN sequence flows.</p>{_svg('Dependency coverage', [f'{edge.get("source_rule_id")} → {edge.get("target_rule_id")} · {edge.get("dependency_type", "unknown")}' for edge in edges], '#7c83fd')}<div class="table-wrap"><table><thead><tr><th>Source rule</th><th>Target rule</th><th>Type</th></tr></thead><tbody>{edge_rows}</tbody></table></div></div></section>
<section id="review" class="tab"><div class="panel"><div class="eyebrow">Review management</div><h2>Human-review queue and quality holds</h2><p><strong>Human-review queue</strong> contains only rules explicitly routed to human judgment. <strong>Quality holds</strong> remain fail-closed when evidence, contract, or relationship checks are incomplete; those items are routed to case management or machine repair and are not counted as human-review work.</p><div class="grid-2"><div class="callout"><strong>{human_review_count}</strong> rules are in the human-review queue (<strong>{report_data["human_review_rate"]:.1f}%</strong>).</div><div class="callout"><strong>{review_count}</strong> rules have quality holds (<strong>{report_data["quality_hold_rate"]:.1f}%</strong>); <strong>{nonhuman_quality_hold_count}</strong> are outside the human queue.</div></div><h3 style="margin-top:24px">Human-review queue ({human_review_count})</h3><div class="table-wrap"><table><thead><tr><th>Rule</th><th>Route</th><th>Why flagged</th><th>Confidence</th><th>Evidence</th></tr></thead><tbody>{''.join(human_review_rows) or '<tr><td colspan="5">No rules are currently routed to human review.</td></tr>'}</tbody></table></div><h3 style="margin-top:24px">Quality holds outside the human queue ({nonhuman_quality_hold_count})</h3><p class="muted">These items retain their review flag for auditability but are intended for case-management or deterministic repair workflows.</p><div class="table-wrap"><table><thead><tr><th>Rule</th><th>Route</th><th>Why flagged</th><th>Confidence</th><th>Evidence</th></tr></thead><tbody>{''.join(quality_hold_rows) or '<tr><td colspan="5">No non-human quality holds are currently recorded.</td></tr>'}</tbody></table></div></div></section>
<section id="sources" class="tab"><div class="panel"><div class="eyebrow">Source traceability</div><h2>Embedded source chunks</h2><p>These source blocks are embedded in this HTML file. Links from concepts, rules, and review items land on the exact referenced chunk/section without requiring filesystem access.</p>{''.join(source_blocks.values()) or '<div class="empty">No source references were present in the graph.</div>'}</div></section>
<footer>Policy Logic Forge Agent 12 · presentation-only artifact · source graph SHA-256: {_safe(hashlib.sha256(graph_file.read_bytes()).hexdigest())}</footer></div>
<script type="application/json" id="report-data">{_json_for_script(report_data)}</script><script>
const tabs=[...document.querySelectorAll('[data-tab]')], sections=[...document.querySelectorAll('section.tab')];
tabs.forEach(button=>button.addEventListener('click',()=>{{tabs.forEach(item=>item.classList.toggle('active',item===button));sections.forEach(section=>section.classList.toggle('active',section.id===button.dataset.tab));history.replaceState(null,'','#'+button.dataset.tab);}}));
const rows=[...document.querySelectorAll('#rules-table tbody .rule-row')], search=document.getElementById('rule-search'), category=document.getElementById('rule-category'), status=document.getElementById('rule-status'), route=document.getElementById('rule-route'), review=document.getElementById('review-only'), count=document.getElementById('rule-count');
function applyFilters(){{const query=(search.value||'').toLowerCase(), cat=category.value, state=status.value, selectedRoute=route.value, only=review.checked;let visible=0;rows.forEach(row=>{{const matches=(!query||row.dataset.search.includes(query))&&(!cat||row.dataset.category===cat)&&(!state||row.dataset.status===state)&&(!selectedRoute||row.dataset.route===selectedRoute)&&(!only||row.dataset.review==='true');row.hidden=!matches;if(matches)visible++;}});count.textContent=visible+' of '+rows.length+' rules shown';}}
[search,category,status,route,review].forEach(control=>control&&control.addEventListener('input',applyFilters));applyFilters();
const conceptCards=[...document.querySelectorAll('#concept-grid .concept-card')], conceptSearch=document.getElementById('concept-search'), conceptKind=document.getElementById('concept-kind'), conceptEvidence=document.getElementById('concept-evidence'), conceptCount=document.getElementById('concept-count');
function applyConceptFilters(){{const query=(conceptSearch.value||'').toLowerCase(), kind=conceptKind.value, evidence=conceptEvidence.value;let visible=0;conceptCards.forEach(card=>{{const matches=(!query||card.dataset.search.includes(query))&&(!kind||card.dataset.kind===kind)&&(!evidence||card.dataset.evidence===evidence);card.hidden=!matches;if(matches)visible++;}});conceptCount.textContent=visible+' of '+conceptCards.length+' concepts shown';}}
[conceptSearch,conceptKind,conceptEvidence].forEach(control=>control&&control.addEventListener('input',applyConceptFilters));applyConceptFilters();
if(location.hash&&document.getElementById(location.hash.slice(1))&&document.getElementById(location.hash.slice(1)).classList.contains('tab'))document.querySelector('[data-tab="'+location.hash.slice(1)+'"]').click();
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
    print(f"Human-review queue: {report['human_review_count']} ({report['human_review_rate']}%); quality holds: {report['quality_hold_count']} ({report['quality_hold_rate']}%); source-pointer coverage: {report['grounding_coverage_rate']}%", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
