"""Build and query a provenance-first read model for pipeline run bundles.

The indexer accepts the existing folder layout (including historical runs that
do not have ``run_manifest.json``) and never mutates the source bundle.  Every
record carries an artifact path and stable hash so consumers can show exactly
where a value came from and detect stale review annotations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


STAGES: tuple[dict[str, Any], ...] = (
    {"id": "agent_01", "name": "Document organizer", "directory": "agent_01-organized-documents", "artifacts": ["_processing_results.json"]},
    {"id": "agent_02", "name": "Entity extractor", "directory": "agent_02-entities", "artifacts": ["entity_types_and_relationships.json", "entity_iteration_checkpoint.json"]},
    {"id": "agent_03", "name": "Rules extractor", "directory": "agent_03-rules", "artifacts": ["compliance_rules_with_entities.json", "batch_results.jsonl", "chunk_coverage.json"]},
    {"id": "agent_04", "name": "Rule validator", "directory": "agent_04-validation", "artifacts": ["validation_report.json"]},
    {"id": "agent_05", "name": "Rules with entities", "directory": "agent_05-rules-with-entities", "artifacts": ["compliance_knowledge_graph.json"]},
    {"id": "agent_06", "name": "Knowledge graph optimizer", "directory": "agent_06-optimized", "artifacts": ["optimized_compliance_knowledge_graph.json", "kg_readiness_report.json", "kg_grounding_report.json"]},
    {"id": "agent_07", "name": "Executable readiness", "directory": "agent_06-optimized", "artifacts": ["agent_07_rule_checkpoint.jsonl"], "embedded": True},
    {"id": "agent_08", "name": "Readiness remediation", "directory": "agent_06-optimized", "artifacts": ["agent_08_checkpoint.jsonl", "agent_08_remediation_report.json"], "embedded": True},
    {"id": "agent_09", "name": "Grounding verifier", "directory": "agent_06-optimized", "artifacts": ["agent_09_grounding_checkpoint.jsonl", "kg_grounding_report.json"], "embedded": True},
    {"id": "agent_10", "name": "DAG generator", "directory": "agent_10-dag-generation", "artifacts": ["dependency_dags.json"]},
    {"id": "agent_11", "name": "Semantic model generator", "directory": "agent_11-executable-models", "artifacts": ["compliance_decisions.dmn", "compliance_workflows.bpmn", "compliance_reviews.cmmn", "semantic_vocabulary_profile.json", "executable_model_report.json"]},
)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def stable_hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"{path.name}: {exc}"


def _read_jsonl(path: Path) -> tuple[list[Any], list[str]]:
    rows: list[Any] = []
    errors: list[str] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    errors.append(f"{path.name}:{line_number}: {exc}")
    except FileNotFoundError:
        pass
    except OSError as exc:
        errors.append(f"{path.name}: {exc}")
    return rows, errors


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _sbvr_rule_projection(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Build a provenance-labelled SBVR-aligned view for one rule.

    The canonical SBVR profile is emitted by Agent 11. The read model also
    exposes this small per-rule projection so reviewers can understand a
    compliance package without opening the global profile. Names are kept as
    contract terms and every displayed concept records its basis; generated
    labels are never presented as source quotations.
    """
    field_evidence = _safe_dict(raw.get("field_evidence"))

    def evidence_for(field: str) -> list[dict[str, Any]]:
        return [item for item in _safe_list(field_evidence.get(field)) if isinstance(item, dict)]

    concepts: list[dict[str, Any]] = []
    responsible = str(raw.get("responsible_party") or "").strip()
    if responsible:
        concepts.append({
            "concept_id": responsible,
            "preferred_term": responsible.replace("_", " ").title(),
            "concept_kind": "actor_role",
            "basis": "rule_contract",
            "source_evidence": evidence_for("responsible_party"),
        })
    for party in _safe_list(raw.get("counterparties")):
        value = str(party or "").strip()
        if value and value not in {item["concept_id"] for item in concepts}:
            concepts.append({
                "concept_id": value,
                "preferred_term": value.replace("_", " ").title(),
                "concept_kind": "actor_role",
                "basis": "rule_contract",
                "source_evidence": evidence_for("counterparties"),
            })
    for variable in _safe_list(raw.get("variables")):
        if not isinstance(variable, dict):
            continue
        value = str(variable.get("name") or "").strip()
        if not value or value in {item["concept_id"] for item in concepts}:
            continue
        concepts.append({
            "concept_id": value,
            "preferred_term": value.replace("_", " ").title(),
            "concept_kind": "decision_variable",
            "role": str(variable.get("role") or "unknown"),
            "basis": "rule_contract",
            "source_evidence": evidence_for("variables"),
        })

    outcomes = [item for item in _safe_list(raw.get("outcomes")) if isinstance(item, dict)]
    source_ref = raw.get("source_reference")
    source_evidence = [item for item in _safe_list(source_ref) if isinstance(item, dict)]
    if isinstance(source_ref, dict):
        source_evidence = [source_ref]
    fact_types = [{
        "fact_type_id": str(raw.get("rule_id") or "rule"),
        "subject_concept": responsible or None,
        "verb_term": str(raw.get("rule_name") or raw.get("rule_type") or "policy decision").replace("_", " ").casefold(),
        "object_concepts": [str(item.get("variable")) for item in outcomes if str(item.get("variable") or "").strip()],
        "basis": "rule_contract",
        "grounding_status": _safe_dict(raw.get("grounding")).get("status", "unverified"),
        "source_evidence": source_evidence,
    }]
    return {
        "profile_type": "sbvr_aligned_rule_projection",
        "conformance": "derived_from_rule_contract",
        "concepts": concepts,
        "fact_types": fact_types,
    }


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-") or "run"


def _status_from_rule(rule: Mapping[str, Any]) -> str:
    if rule.get("requires_review"):
        return "requires_review"
    readiness = _safe_dict(rule.get("readiness"))
    grounding = _safe_dict(rule.get("grounding"))
    if readiness.get("status") in {"failed", "requires_review", "review"}:
        return "readiness_failed"
    if grounding.get("status") in {"failed", "insufficient", "contradicted"}:
        return "grounding_failed"
    if grounding.get("status") in {"certified", "passed"} and readiness.get("status") in {"ready", "certified"}:
        return "certified"
    return "unresolved"


def _evidence_record(
    *,
    evidence_id: str,
    run_id: str,
    rule_id: str,
    field_path: str,
    value: Mapping[str, Any],
    source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source = source or value
    chunk_path = str(source.get("chunk_path") or "")
    section_id = str(source.get("section_id") or "")
    quote = source.get("source_text") or source.get("supporting_quote") or ""
    return {
        "evidence_id": evidence_id,
        "run_id": run_id,
        "rule_id": rule_id,
        "field_path": field_path,
        "chunk_path": chunk_path,
        "section_id": section_id,
        "quote": str(quote),
        "source_text": str(source.get("source_text") or quote),
        "verdict": source.get("verdict", "source_attested"),
        "reasoning": source.get("reasoning"),
        "artifact_path": source.get("artifact_path"),
    }


@dataclass(frozen=True)
class ReviewIndex:
    """In-memory normalized index used by the API and tests."""

    run_id: str
    source_dir: Path
    run_summary: dict[str, Any]
    stages: list[dict[str, Any]]
    rules: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    documents: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]
    comparison_keys: list[dict[str, Any]]

    @classmethod
    def from_directory(cls, run_dir: str | Path) -> "ReviewIndex":
        source_dir = Path(run_dir).expanduser().resolve()
        if not source_dir.is_dir():
            raise FileNotFoundError(f"pipeline run directory does not exist: {source_dir}")
        run_id = _slug(source_dir.name)
        diagnostics: list[dict[str, Any]] = []

        stages = _build_stages(source_dir, diagnostics)
        optimized_path = source_dir / "agent_06-optimized" / "optimized_compliance_knowledge_graph.json"
        optimized, error = _read_json(optimized_path)
        if error:
            diagnostics.append(_diagnostic("error", "indexer", error, str(optimized_path.relative_to(source_dir))))
        optimized = _safe_dict(optimized)
        rules = _build_rules(optimized, run_id, str(optimized_path.relative_to(source_dir)))
        relationships = _build_relationships(optimized, source_dir, run_id)
        documents = _build_documents(source_dir, run_id, diagnostics)
        evidence = _build_evidence(rules, run_id)
        _add_grounding_diagnostics(rules, diagnostics)
        _add_validation_diagnostics(source_dir, diagnostics)
        _add_contract_diagnostics(rules, diagnostics)
        _add_index_diagnostics(stages, documents, diagnostics)
        _finalize_stage_metrics(stages, diagnostics)
        comparison_keys = _build_comparison_keys(rules, relationships)

        summary = _build_summary(
            run_id=run_id,
            source_dir=source_dir,
            stages=stages,
            rules=rules,
            relationships=relationships,
            documents=documents,
            evidence=evidence,
            diagnostics=diagnostics,
            optimized=optimized,
        )
        return cls(run_id, source_dir, summary, stages, rules, relationships, documents, evidence, diagnostics, comparison_keys)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_summary": self.run_summary,
            "stages": self.stages,
            "rules": self.rules,
            "relationships": self.relationships,
            "documents": self.documents,
            "evidence": self.evidence,
            "diagnostics": self.diagnostics,
            "comparison_keys": self.comparison_keys,
        }

    def get_rule(self, rule_id: str) -> dict[str, Any] | None:
        return next((row for row in self.rules if row["rule_id"] == rule_id), None)

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        return next((row for row in self.documents if row["document_id"] == document_id), None)

    def get_evidence(self, evidence_id: str) -> dict[str, Any] | None:
        return next((row for row in self.evidence if row["evidence_id"] == evidence_id), None)

    def queue(self, name: str) -> list[dict[str, Any]]:
        if name == "requires_review":
            return [r for r in self.rules if r["requires_review"]]
        if name == "human_review":
            return [r for r in self.rules if (r.get("review_route") or {}).get("human_review_required") is True]
        if name == "grounding_failed":
            return [r for r in self.rules if r["grounding_status"] in {"failed", "insufficient", "contradicted"}]
        if name == "readiness_failed":
            return [r for r in self.rules if r["readiness_status"] in {"failed", "requires_review", "review"}]
        if name == "unresolved_conflicts":
            ids = {rid for rel in self.relationships if rel["kind"] == "conflict" and rel["status"] == "unresolved" for rid in rel["rule_ids"]}
            return [r for r in self.rules if r["rule_id"] in ids]
        if name == "all_open":
            return [r for r in self.rules if r["machine_status"] != "certified"]
        raise KeyError(f"unknown review queue: {name}")

    def search(self, query: str, *, kind: str | None = None, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query = query.strip().lower()
        if not query:
            return []
        candidates: list[dict[str, Any]] = []
        for row in self.rules:
            if kind and kind != "rule":
                continue
            haystack = " ".join(str(row.get(k, "")) for k in ("rule_id", "rule_name", "description", "rule_type", "responsible_party", "review_reason", "inference_reasoning"))
            haystack += " " + _json(row.get("condition_predicates", [])) + " " + _json(row.get("outcomes", [])) + " " + _json(row.get("variables", []))
            haystack += " " + " ".join(e["quote"] + " " + str(e.get("reasoning") or "") for e in row.get("evidence", []))
            if query in haystack.lower() and (not status or row["machine_status"] == status):
                candidates.append({"kind": "rule", "id": row["rule_id"], "title": row["rule_name"], "snippet": _snippet(haystack, query), "status": row["machine_status"], "score": _score(haystack, query)})
        if not kind or kind in {"document", "source_chunk"}:
            for row in self.documents:
                haystack = f"{row['document_id']} {row['path']} {row.get('section_id','')} {row.get('text','')}"
                if query in haystack.lower() and (not status or status == "source"):
                    candidates.append({"kind": "document", "id": row["document_id"], "title": row["path"], "snippet": _snippet(haystack, query), "status": "source", "score": _score(haystack, query)})
        if not kind or kind == "evidence":
            for row in self.evidence:
                haystack = _json(row)
                if query in haystack.lower() and (not status or row.get("verdict") == status):
                    candidates.append({"kind": "evidence", "id": row["evidence_id"], "title": f"{row['rule_id']} · {row['field_path']}", "snippet": _snippet(row.get("quote", "") or row.get("source_text", ""), query), "status": str(row.get("verdict", "source_attested")), "score": _score(haystack, query)})
        if not kind or kind == "relationship":
            for row in self.relationships:
                haystack = _json(row)
                if query in haystack.lower() and (not status or row.get("status") == status):
                    candidates.append({"kind": "relationship", "id": row["relationship_id"], "title": f"{row['kind']} relationship", "snippet": _snippet(str(row.get("rationale") or row.get("resolution") or row.get("impact") or ""), query), "status": str(row.get("status", "unknown")), "score": _score(haystack, query)})
        if not kind or kind == "diagnostic":
            for row in self.diagnostics:
                haystack = _json(row)
                if query in haystack.lower():
                    candidates.append({"kind": "diagnostic", "id": row["diagnostic_id"], "title": row["check"], "snippet": _snippet(row.get("message", ""), query), "status": row["severity"], "score": _score(haystack, query)})
        return sorted(candidates, key=lambda row: (-row["score"], row["title"]))[: max(1, min(limit, 500))]

    def write(self, output_dir: str | Path) -> Path:
        destination = Path(output_dir).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        _write_json(destination / "run_summary.json", self.run_summary)
        _write_json(destination / "stage_index.json", self.stages)
        _write_json(destination / "run_manifest.json", {"run_id": self.run_id, "batch_name": self.run_id, "source_dir": self.run_summary["source_dir"], "status": self.run_summary["status"], "generated_at": self.run_summary["generated_at"], "executed_agents": [stage["stage_id"] for stage in self.stages if stage["status"] != "missing"], "stages": self.stages, "corpus_sha256": self.run_summary.get("corpus_sha256"), "optimized_graph_sha256": self.run_summary.get("optimized_graph_sha256"), "model": self.run_summary.get("model"), "reasoning_effort": self.run_summary.get("reasoning_effort"), "metadata": self.run_summary.get("metadata", {})})
        _write_json(destination / "stage_status.json", [{key: stage.get(key) for key in ("stage_id", "name", "status", "started_at", "finished_at", "input_counts", "output_counts", "warning_count", "failure_count", "checkpoint_records", "primary_artifacts", "artifacts")} for stage in self.stages])
        _write_json(destination / "diagnostics.json", self.diagnostics)
        _write_json(destination / "comparison_keys.json", self.comparison_keys)
        _write_jsonl(destination / "rule_index.jsonl", self.rules)
        _write_jsonl(destination / "relationship_index.jsonl", self.relationships)
        _write_jsonl(destination / "document_index.jsonl", self.documents)
        _write_jsonl(destination / "evidence_index.jsonl", self.evidence)
        _build_search_db(destination / "search.sqlite", self)
        return destination


def build_review_index(run_dir: str | Path, output_dir: str | Path | None = None) -> ReviewIndex:
    index = ReviewIndex.from_directory(run_dir)
    if output_dir is not None:
        index.write(output_dir)
    return index


def _build_stages(source_dir: Path, diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = []
    for spec in STAGES:
        directory = source_dir / spec["directory"]
        artifacts: list[dict[str, Any]] = []
        for name in spec["artifacts"]:
            path = directory / name
            if path.is_file():
                try:
                    size = path.stat().st_size
                except OSError:
                    size = 0
                artifacts.append({"name": name, "path": str(path.relative_to(source_dir)), "size_bytes": size, "present": True})
                if name.endswith(".jsonl"):
                    _, parse_errors = _read_jsonl(path)
                    diagnostics.extend(_diagnostic("error", spec["id"], message, str(path.relative_to(source_dir))) for message in parse_errors)
        status = "completed" if artifacts else "missing"
        if spec.get("embedded") and artifacts:
            status = "completed_embedded"
        if directory.exists() and not artifacts:
            status = "incomplete"
            diagnostics.append(_diagnostic("warning", spec["id"], "stage directory exists but expected artifacts are missing", spec["directory"]))
        checkpoint_records = _checkpoint_count(directory, spec["artifacts"])
        mtimes = []
        for artifact in artifacts:
            try:
                mtimes.append((directory / Path(artifact["path"]).name).stat().st_mtime)
            except OSError:
                continue
        stages.append({"stage_id": spec["id"], "name": spec["name"], "directory": spec["directory"], "status": status, "embedded": bool(spec.get("embedded")), "artifacts": artifacts, "checkpoint_records": checkpoint_records, "started_at": datetime.fromtimestamp(min(mtimes), timezone.utc).isoformat() if mtimes else None, "finished_at": datetime.fromtimestamp(max(mtimes), timezone.utc).isoformat() if mtimes else None, "input_counts": {}, "output_counts": {"artifact_files": len(artifacts), "checkpoint_records": checkpoint_records}, "warning_count": 0, "failure_count": 0, "primary_artifacts": [artifact["path"] for artifact in artifacts]})
    return stages


def _checkpoint_count(directory: Path, names: Iterable[str]) -> int:
    count = 0
    for name in names:
        if not name.endswith(".jsonl"):
            continue
        rows, _ = _read_jsonl(directory / name)
        count += len(rows)
    return count


def _finalize_stage_metrics(stages: list[dict[str, Any]], diagnostics: list[dict[str, Any]]) -> None:
    """Attach scoped diagnostic totals without changing canonical artifacts."""
    embedded_present = any(stage.get("embedded") and stage.get("status") != "missing" for stage in stages)
    for stage in stages:
        prefix = stage["directory"].rstrip("/") + "/"
        if stage.get("embedded"):
            # Agents 07–09 share agent_06's directory in the current bundle;
            # use diagnostic ownership to avoid counting the same finding three
            # times in the stage monitor.
            owner_checks = {"agent_07": set(), "agent_08": {"contract"}, "agent_09": {"grounding"}}
            scoped = [item for item in diagnostics if item.get("check") in owner_checks.get(stage["stage_id"], set())]
        else:
            scoped = [item for item in diagnostics if item.get("artifact_path") == stage["directory"] or str(item.get("artifact_path", "")).startswith(prefix)]
            if stage["stage_id"] == "agent_06" and embedded_present:
                scoped = [item for item in scoped if item.get("check") not in {"contract", "grounding"}]
        stage["warning_count"] = sum(item.get("severity") == "warning" for item in scoped)
        stage["failure_count"] = sum(item.get("severity") == "error" for item in scoped)


def _build_rules(optimized: Mapping[str, Any], run_id: str, artifact_path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in _safe_list(optimized.get("business_rules")):
        if not isinstance(raw, dict):
            continue
        readiness = _safe_dict(raw.get("readiness"))
        grounding = _safe_dict(raw.get("grounding"))
        evidence = []
        for field_path, records in _safe_dict(raw.get("field_evidence")).items():
            for index, record in enumerate(_safe_list(records)):
                if isinstance(record, dict):
                    evidence.append(_evidence_record(evidence_id=f"{raw.get('rule_id','unknown')}:{field_path}:{index}", run_id=run_id, rule_id=str(raw.get("rule_id", "")), field_path=field_path, value=record, source=record))
        source_value = raw.get("source_reference")
        source_refs = [item for item in _safe_list(source_value) if isinstance(item, dict)]
        if isinstance(source_value, dict):
            source_refs = [source_value]
        for index, source_ref in enumerate(source_refs):
            evidence.insert(0, _evidence_record(evidence_id=f"{raw.get('rule_id','unknown')}:source_reference:{index}", run_id=run_id, rule_id=str(raw.get("rule_id", "")), field_path="source_reference", value=source_ref, source=source_ref))
        deduped: dict[str, dict[str, Any]] = {stable_hash({k: e.get(k) for k in ("field_path", "chunk_path", "section_id", "quote")}): e for e in evidence}
        machine_status = _status_from_rule(raw)
        structural = {k: raw.get(k) for k in ("rule_id", "rule_name", "rule_type", "description", "condition_predicates", "condition_logic", "outcomes", "variables", "recommended_hit_policy", "responsible_party", "exceptions", "mandatory", "risk_level")}
        evidence_shape = [{k: e.get(k) for k in ("field_path", "chunk_path", "section_id", "quote")} for e in deduped.values()]
        rows.append({
            "rule_id": str(raw.get("rule_id", "")),
            "rule_name": str(raw.get("rule_name") or raw.get("name") or raw.get("rule_id") or "Unnamed rule"),
            "description": raw.get("description", ""),
            # `.get(key, "unknown")` only substitutes when the key is absent;
            # real pipeline output can carry an explicit `null` for a field
            # the extraction agent left unclassified (e.g. risk_level), which
            # would otherwise flow straight through as None and crash any
            # frontend code that assumes these are always non-empty strings
            # (see the review-workbench white-screen bug this fixed).
            "rule_type": raw.get("rule_type") or "unknown",
            "risk_level": raw.get("risk_level") or "unknown",
            "mandatory": bool(raw.get("mandatory", False)),
            "requires_review": bool(raw.get("requires_review", False)),
            "review_reason": raw.get("review_reason"),
            "readiness_status": readiness.get("status") or "unknown",
            "readiness_failures": _safe_list(readiness.get("failed_requirements")),
            "grounding_status": grounding.get("status") or "unknown",
            "grounding_counts": _safe_dict(grounding.get("counts")),
            "confidence_score": raw.get("confidence_score"),
            "source_reference": source_value if isinstance(source_value, (dict, list)) else {},
            "field_evidence": _safe_dict(raw.get("field_evidence")),
            "evidence": list(deduped.values()),
            "condition_predicates": _safe_list(raw.get("condition_predicates")),
            "condition_logic": _safe_dict(raw.get("condition_logic")),
            "outcomes": _safe_list(raw.get("outcomes")),
            "variables": _safe_list(raw.get("variables")),
            "related_rules": _safe_list(raw.get("related_rules")),
            "contract_issues": _safe_list(raw.get("contract_issues")),
            "execution": _safe_dict(raw.get("execution")),
            # Keep the source-explicit workflow contract in the read model so
            # the UI can distinguish a real BPMN projection from a simple
            # decision.  This is intentionally the normalized contract, not
            # a UI-specific complexity guess.
            "workflow_semantics": _safe_dict(raw.get("workflow_semantics")),
            "review_route": _safe_dict(raw.get("review_route")),
            "sbvr_projection": _sbvr_rule_projection(raw),
            "recommended_hit_policy": raw.get("recommended_hit_policy"),
            "scope_basis": raw.get("scope_basis"),
            "applicability_scope": _safe_dict(raw.get("applicability_scope")),
            "responsible_party": raw.get("responsible_party"),
            "counterparties": _safe_list(raw.get("counterparties")),
            "exceptions": _safe_list(raw.get("exceptions")),
            "inference_reasoning": raw.get("inference_reasoning"),
            "test_vectors": _safe_list(raw.get("test_vectors")),
            "machine_status": machine_status,
            "artifact_path": artifact_path,
            "structural_hash": stable_hash(structural),
            "evidence_hash": stable_hash(evidence_shape),
        })
    return rows


def _build_relationships(optimized: Mapping[str, Any], source_dir: Path, run_id: str) -> list[dict[str, Any]]:
    details = _safe_dict(optimized.get("dependency_details"))
    relationships: list[dict[str, Any]] = []
    # The optimized graph also carries entity-type relationship definitions.
    # Keep them in the read model for evidence/search, while the layered rule
    # topology explicitly excludes them and only admits rule-to-rule edges.
    for name, raw in _safe_dict(optimized.get("relationships")).items():
        if not isinstance(raw, dict):
            continue
        relationships.append({"relationship_id": f"entity:{name}", "kind": "entity_relationship", "entity": str(name), "source_entity": raw.get("source_entity"), "target_entity": raw.get("target_entity"), "rule_ids": [], "status": "defined", "rationale": raw.get("definition", ""), "impact": raw.get("cardinality", ""), "examples": _safe_list(raw.get("examples")), "business_rules": _safe_list(raw.get("business_rules")), "artifact_path": "agent_06-optimized/optimized_compliance_knowledge_graph.json"})
    for index, raw in enumerate(_safe_list(details.get("dependencies"))):
        if not isinstance(raw, dict):
            continue
        source = str(raw.get("source_rule_id") or raw.get("from_rule_id") or "")
        target = str(raw.get("target_rule_id") or raw.get("to_rule_id") or "")
        relationships.append({"relationship_id": f"dependency:{source}:{target}:{index}", "kind": "dependency", "source_rule_id": source, "target_rule_id": target, "rule_ids": [source, target], "dependency_type": raw.get("dependency_type", "related"), "status": "supported" if raw.get("structurally_supported") else "inferred", "confidence": raw.get("confidence"), "strength": raw.get("strength"), "rationale": raw.get("rationale", ""), "impact": raw.get("impact", ""), "artifact_path": "agent_06-optimized/optimized_compliance_knowledge_graph.json"})
    for index, raw in enumerate(_safe_list(details.get("conflicts"))):
        if not isinstance(raw, dict):
            continue
        ids = [str(rid) for rid in _safe_list(raw.get("rule_ids"))]
        conflict_status = raw.get("status", "unknown")
        relationships.append({"relationship_id": f"conflict:{raw.get('entity','unknown')}:{index}", "kind": "conflict" if conflict_status in {"conflict", "unresolved"} else "conflict_candidate", "entity": raw.get("entity"), "rule_ids": ids, "source_rule_id": ids[0] if ids else None, "target_rule_id": ids[1] if len(ids) > 1 else None, "status": conflict_status, "rationale": raw.get("reasoning", ""), "resolution": raw.get("resolution", ""), "artifact_path": "agent_06-optimized/optimized_compliance_knowledge_graph.json"})
    dags_path = source_dir / "agent_10-dag-generation" / "dependency_dags.json"
    dags, _ = _read_json(dags_path)
    for dag in _safe_list(_safe_dict(dags).get("dags")):
        if not isinstance(dag, dict):
            continue
        dag_id = dag.get("dag_id", "dag_unknown")
        rule_ids = [str(rid) for rid in _safe_list(dag.get("rule_ids"))]
        for edge_index, edge in enumerate(_safe_list(dag.get("edges"))):
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("source") or edge.get("from") or edge.get("source_rule_id") or "")
            target = str(edge.get("target") or edge.get("to") or edge.get("target_rule_id") or "")
            relationships.append({"relationship_id": f"dag:{dag_id}:{edge_index}", "kind": "dag_edge", "dag_id": dag_id, "rule_ids": rule_ids, "source_rule_id": source, "target_rule_id": target, "status": "acyclic" if dag.get("is_acyclic", True) else "cyclic", "rationale": "topological dependency DAG", "artifact_path": "agent_10-dag-generation/dependency_dags.json"})
    return relationships


def _build_documents(source_dir: Path, run_id: str, diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    root = source_dir / "agent_01-organized-documents"
    documents: list[dict[str, Any]] = []
    if not root.is_dir():
        return documents
    for path in sorted(root.rglob("*.txt")):
        try:
            text = path.read_text(encoding="utf-8")
            relative = str(path.relative_to(root))
            stat = path.stat()
        except (OSError, UnicodeDecodeError) as exc:
            diagnostics.append(_diagnostic("warning", "document_index", str(exc), str(path.relative_to(source_dir))))
            continue
        document_id = stable_hash({"run_id": run_id, "path": relative})[:20]
        documents.append({"document_id": document_id, "run_id": run_id, "path": relative, "section_id": relative.rsplit("/", 1)[-1][:-4], "text": text, "word_count": len(text.split()), "size_bytes": stat.st_size, "source_hash": hashlib.sha256(text.encode()).hexdigest(), "artifact_path": str(path.relative_to(source_dir))})
    return documents


def _build_evidence(rules: list[dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rule in rules:
        normalized: list[dict[str, Any]] = []
        for item in rule["evidence"]:
            key = stable_hash({k: item.get(k) for k in ("rule_id", "field_path", "chunk_path", "section_id", "quote")})
            if key in seen:
                continue
            seen.add(key)
            item = dict(item)
            item["evidence_id"] = key[:24]
            item["run_id"] = run_id
            normalized.append(item)
            evidence.append(item)
        # Rule detail embeds the same canonical IDs exposed by /evidence/{id}.
        rule["evidence"] = normalized
    return evidence


def _add_grounding_diagnostics(rules: list[dict[str, Any]], diagnostics: list[dict[str, Any]]) -> None:
    for rule in rules:
        grounding = rule["grounding_status"]
        if grounding in {"failed", "insufficient", "contradicted"}:
            diagnostics.append(_diagnostic("error", "grounding", f"Rule grounding status is {grounding}", rule["artifact_path"], rule["rule_id"]))
        if not rule["evidence"]:
            diagnostics.append(_diagnostic("warning", "evidence", "Rule has no field evidence or source reference", rule["artifact_path"], rule["rule_id"]))


def _add_validation_diagnostics(source_dir: Path, diagnostics: list[dict[str, Any]]) -> None:
    path = source_dir / "agent_04-validation" / "validation_report.json"
    report, error = _read_json(path)
    if error:
        diagnostics.append(_diagnostic("error", "validation", error, str(path.relative_to(source_dir))))
        return
    report = _safe_dict(report)
    for severity, key in (("error", "failures"), ("warning", "warnings")):
        for item in _safe_list(report.get(key)):
            if not isinstance(item, dict):
                continue
            diagnostics.append(_diagnostic(severity, str(item.get("check", "validation")), str(item.get("issue") or item.get("message") or "validation finding"), str(path.relative_to(source_dir)), item.get("rule_id"), item.get("recommendation")))


def _add_contract_diagnostics(rules: list[dict[str, Any]], diagnostics: list[dict[str, Any]]) -> None:
    for rule in rules:
        for issue in rule["contract_issues"]:
            diagnostics.append(_diagnostic("error", "contract", str(issue), rule["artifact_path"], rule["rule_id"]))


def _add_index_diagnostics(stages: list[dict[str, Any]], documents: list[dict[str, Any]], diagnostics: list[dict[str, Any]]) -> None:
    if not documents:
        diagnostics.append(_diagnostic("warning", "document_index", "No source chunks were discovered", "agent_01-organized-documents"))
    missing = [stage["stage_id"] for stage in stages if stage["status"] == "missing"]
    if missing:
        diagnostics.append(_diagnostic("error", "stage_index", f"Expected stage artifacts are missing: {', '.join(missing)}", "pipeline-output"))


def _build_comparison_keys(rules: list[dict[str, Any]], relationships: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"artifact_type": "rule", "artifact_id": row["rule_id"], "structural_hash": row["structural_hash"], "evidence_hash": row["evidence_hash"]} for row in rules] + [{"artifact_type": "relationship", "artifact_id": row["relationship_id"], "structural_hash": stable_hash({k: row.get(k) for k in ("kind", "source_rule_id", "target_rule_id", "source_entity", "target_entity", "dependency_type", "status", "rule_ids")}), "evidence_hash": stable_hash({k: row.get(k) for k in ("rationale", "impact", "resolution", "examples", "business_rules")})} for row in relationships]


def _build_summary(*, run_id: str, source_dir: Path, stages: list[dict[str, Any]], rules: list[dict[str, Any]], relationships: list[dict[str, Any]], documents: list[dict[str, Any]], evidence: list[dict[str, Any]], diagnostics: list[dict[str, Any]], optimized: Mapping[str, Any]) -> dict[str, Any]:
    statuses = Counter(r["machine_status"] for r in rules)
    readiness = Counter(r["readiness_status"] for r in rules)
    grounding = Counter(r["grounding_status"] for r in rules)
    conflicts = [r for r in relationships if r["kind"] == "conflict"]
    unresolved_conflicts = [r for r in conflicts if r["status"] == "unresolved"]
    human_review_rules = [
        r for r in rules
        if isinstance(r.get("review_route"), Mapping)
        and r["review_route"].get("human_review_required") is True
    ]
    metadata = _safe_dict(optimized.get("metadata"))
    grounding_metadata = _safe_dict(metadata.get("grounding_certification"))
    corpus_hash = _safe_dict(optimized.get("corpus_manifest")).get("corpus_sha256") or metadata.get("corpus_sha256") or grounding_metadata.get("corpus_sha256")
    certified_hash = metadata.get("certified_graph_sha256") or metadata.get("optimized_graph_sha256") or grounding_metadata.get("certified_graph_sha256")
    return {
        "run_id": run_id,
        "source_dir": str(source_dir),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "requires_review" if any(d["severity"] == "error" for d in diagnostics) else "ready_for_review",
        "stage_count": len(stages),
        "completed_stage_count": sum(s["status"] in {"completed", "completed_embedded"} for s in stages),
        "rule_count": len(rules),
        "document_count": len(documents),
        "evidence_count": len(evidence),
        "relationship_count": len(relationships),
        "diagnostic_count": len(diagnostics),
        "error_count": sum(d["severity"] == "error" for d in diagnostics),
        "warning_count": sum(d["severity"] == "warning" for d in diagnostics),
        "review_queue_count": sum(r["requires_review"] for r in rules),
        "human_review_required_rules": len(human_review_rules),
        "human_review_rate": round(len(human_review_rules) / max(1, len(rules)) * 100, 2),
        "unresolved_conflict_count": len(unresolved_conflicts),
        "rule_status_counts": dict(statuses),
        "readiness_counts": dict(readiness),
        "grounding_counts": dict(grounding),
        "corpus_manifest": _safe_dict(optimized.get("corpus_manifest")),
        "metadata": metadata,
        "corpus_sha256": corpus_hash,
        "optimized_graph_sha256": certified_hash,
        "model": metadata.get("model_used"),
        "reasoning_effort": metadata.get("reasoning_effort"),
        "queues": {"requires_review": statuses.get("requires_review", 0), "human_review": len(human_review_rules), "grounding_failed": sum(r["grounding_status"] in {"failed", "insufficient", "contradicted"} for r in rules), "readiness_failed": sum(r["readiness_status"] in {"failed", "requires_review", "review"} for r in rules), "unresolved_conflicts": len({rid for rel in unresolved_conflicts for rid in rel["rule_ids"]})},
    }


def _diagnostic(severity: str, check: str, message: str, artifact_path: str, artifact_id: str | None = None, recommendation: str | None = None) -> dict[str, Any]:
    return {"diagnostic_id": stable_hash({"severity": severity, "check": check, "message": message, "artifact_path": artifact_path, "artifact_id": artifact_id})[:24], "severity": severity, "check": check, "message": message, "artifact_path": artifact_path, "artifact_id": artifact_id, "recommendation": recommendation}


def _snippet(text: str, query: str, width: int = 180) -> str:
    lower = text.lower()
    start = max(0, lower.find(query) - 55)
    return text[start : start + width].replace("\n", " ").strip()


def _score(text: str, query: str) -> int:
    lower = text.lower()
    return min(100, lower.count(query) * 10 + (35 if lower.startswith(query) else 0))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(_json(row) + "\n")


def _build_search_db(path: Path, index: ReviewIndex) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript("DROP TABLE IF EXISTS search; CREATE VIRTUAL TABLE search USING fts5(kind, artifact_id UNINDEXED, title, body, status UNINDEXED);")
        for rule in index.rules:
            body = " ".join([str(rule.get(k, "")) for k in ("rule_id", "description", "rule_type", "responsible_party", "review_reason", "inference_reasoning")] + [_json(rule.get("condition_predicates", [])), _json(rule.get("outcomes", [])), _json(rule.get("variables", []))] + [e.get("quote", "") + " " + str(e.get("reasoning") or "") for e in rule["evidence"]])
            conn.execute("INSERT INTO search(kind,artifact_id,title,body,status) VALUES (?,?,?,?,?)", ("rule", rule["rule_id"], rule["rule_name"], body, rule["machine_status"]))
        for doc in index.documents:
            conn.execute("INSERT INTO search(kind,artifact_id,title,body,status) VALUES (?,?,?,?,?)", ("document", doc["document_id"], doc["path"], doc["text"], "source"))
        for evidence in index.evidence:
            conn.execute("INSERT INTO search(kind,artifact_id,title,body,status) VALUES (?,?,?,?,?)", ("evidence", evidence["evidence_id"], f"{evidence['rule_id']} {evidence['field_path']}", evidence.get("quote", "") + " " + evidence.get("source_text", "") + " " + str(evidence.get("reasoning") or ""), evidence.get("verdict", "source_attested")))
        for relationship in index.relationships:
            conn.execute("INSERT INTO search(kind,artifact_id,title,body,status) VALUES (?,?,?,?,?)", ("relationship", relationship["relationship_id"], relationship["kind"], _json(relationship), relationship.get("status", "unknown")))
        for diagnostic in index.diagnostics:
            conn.execute("INSERT INTO search(kind,artifact_id,title,body,status) VALUES (?,?,?,?,?)", ("diagnostic", diagnostic["diagnostic_id"], diagnostic["check"], diagnostic["message"], diagnostic["severity"]))


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    index = build_review_index(args.run_dir, args.output)
    print(json.dumps(index.run_summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
