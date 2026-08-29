from __future__ import annotations

import json
from pathlib import Path

import pytest

from ui.backend.review_index import STAGES, ReviewIndex, build_review_index, stable_hash
from utils.agent_names import AGENT_IDS


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def make_run(root: Path, name: str = "fixture-run") -> Path:
    run = root / name
    for directory, filename in [
        ("agent_01-organized-documents", "_processing_results.json"),
        ("agent_02-entities", "entity_types_and_relationships.json"),
        ("agent_03-rules", "compliance_rules_with_entities.json"),
        ("agent_04-validation", "validation_report.json"),
        ("agent_05-rules-with-entities", "compliance_knowledge_graph.json"),
        ("agent_06-07-08-09-optimized", "kg_readiness_report.json"),
        ("agent_10-dag-generation", "dependency_dags.json"),
    ]:
        _write(run / directory / filename, {})
    rule = {
        "schema_version": "2.0",
        "rule_id": "r1",
        "rule_name": "Collect email",
        "rule_type": "collection",
        "description": "Collect email for account support.",
        "condition_predicates": [{"predicate_id": "p1", "variable": "account", "operator": "==", "value": True}],
        "condition_logic": {"predicate_ref": "p1"},
        "outcomes": [{"variable": "email_collected", "operator": "=", "value": True}],
        "variables": [{"name": "account", "role": "input", "type": "boolean"}, {"name": "email_collected", "role": "output", "type": "boolean"}],
        "recommended_hit_policy": "UNIQUE",
        "responsible_party": "FIRST_PARTY",
        "risk_level": "high",
        "requires_review": True,
        "review_reason": "check evidence",
        "confidence_score": 80,
        "contract_issues": ["example issue"],
        "readiness": {"status": "failed", "failed_requirements": ["source"]},
        "grounding": {"status": "failed", "counts": {"supported": 0, "insufficient_evidence": 1}},
        "source_reference": {"chunk_path": "site/privacy.txt", "section_id": "Collection", "source_text": "We collect your email."},
        "field_evidence": {"outcomes": [{"chunk_path": "site/privacy.txt", "section_id": "Collection", "source_text": "collect your email"}]},
        "execution": {"targets": ["DMN", "BPMN"], "dmn": {"input_columns": ["account"], "output_columns": ["email_collected"], "hit_policy": "UNIQUE"}, "bpmn": {"gateway_type": "exclusive", "lane": "FIRST_PARTY", "true_path_outcome_variables": ["email_collected"]}},
        "test_vectors": [],
        "exceptions": [],
        "related_rules": [],
    }
    optimized = {"metadata": {"model_used": "gpt-5.6-luna", "reasoning_effort": "high"}, "business_rules": [rule], "relationships": {"RULE_LINK": {"source_entity": "FIRST_PARTY", "target_entity": "INFORMATION_TYPE", "definition": "links an operator to information", "cardinality": "one-to-many", "examples": ["operator links data"], "business_rules": ["retain the association"]}}, "dependency_details": {"dependencies": [{"source_rule_id": "r1", "target_rule_id": "r2", "dependency_type": "sequential", "confidence": 70, "structurally_supported": True, "rationale": "before", "impact": "ordering"}], "conflicts": [{"entity": "EMAIL", "rule_ids": ["r1", "r2"], "status": "unresolved", "reasoning": "overlap", "resolution": ""}]}, "corpus_manifest": {"corpus_sha256": "corpus"}}
    _write(run / "agent_06-07-08-09-optimized" / "optimized_compliance_knowledge_graph.json", optimized)
    _write(run / "agent_01-organized-documents" / "site" / "privacy.txt", "not json")
    (run / "agent_01-organized-documents" / "site" / "privacy.txt").write_text("We collect your email.", encoding="utf-8")
    (run / "agent_03-rules" / "batch_results.jsonl").write_text('{"rule_id":"r1"}\n', encoding="utf-8")
    (run / "agent_06-07-08-09-optimized" / "agent_07_rule_checkpoint.jsonl").write_text('{"rule_id":"r1"}\n', encoding="utf-8")
    _write(run / "agent_04-validation" / "validation_report.json", {"failures": [{"rule_id": "r1", "check": "completeness", "issue": "missing field", "recommendation": "fix"}], "warnings": [{"check": "scope", "issue": "scope warning"}]})
    _write(run / "agent_10-dag-generation" / "dependency_dags.json", {"dags": [{"dag_id": "dag_1", "rule_ids": ["r1", "r2"], "edges": [{"source": "r1", "target": "r2"}], "is_acyclic": True}]})
    return run


def test_index_normalizes_artifacts_and_queues(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    index = ReviewIndex.from_directory(run)
    assert index.run_id == "fixture-run"
    assert index.run_summary["corpus_sha256"] == "corpus"
    assert index.rules[0]["machine_status"] == "requires_review"
    assert len(index.queue("requires_review")) == 1
    assert len(index.queue("grounding_failed")) == 1
    assert len(index.queue("readiness_failed")) == 1
    assert len(index.queue("unresolved_conflicts")) == 1
    assert len(index.queue("all_open")) == 1
    assert index.search("email")[0]["kind"] == "rule"
    assert index.search("privacy", kind="document")[0]["kind"] == "document"
    assert index.search("missing", kind="diagnostic")[0]["kind"] == "diagnostic"
    assert index.search("overlap", kind="relationship")[0]["kind"] == "relationship"
    assert any(row["kind"] == "entity_relationship" and row["source_entity"] == "FIRST_PARTY" for row in index.relationships)
    assert index.search("collect your email", kind="evidence")[0]["kind"] == "evidence"
    assert index.rules[0]["evidence"][0]["evidence_id"] == index.evidence[0]["evidence_id"]
    projection = index.rules[0]["sbvr_projection"]
    assert projection["profile_type"] == "sbvr_aligned_rule_projection"
    assert projection["conformance"] == "derived_from_rule_contract"
    assert projection["fact_types"][0]["fact_type_id"] == "r1"
    assert any(concept["concept_id"] == "FIRST_PARTY" for concept in projection["concepts"])
    assert index.stages[0]["primary_artifacts"] == ["agent_01-organized-documents/_processing_results.json"]
    assert index.stages[0]["stage_number"] == 1
    assert next(item for item in index.stages if item["stage_id"] == "agent_11")["stage_number"] == 11
    assert "output_counts" in index.stages[0]
    assert index.get_rule("unknown") is None
    assert stable_hash({"a": 1}) == stable_hash({"a": 1})
    with pytest.raises(KeyError):
        index.queue("nope")


def test_review_index_uses_the_same_canonical_agent_sequence_as_the_pipeline() -> None:
    assert tuple(stage["id"] for stage in STAGES) == AGENT_IDS
    assert [stage.get("id") for stage in STAGES] == [f"agent_{number:02d}" for number in range(1, 12)]


def test_index_reads_legacy_shared_optimized_directory(tmp_path: Path) -> None:
    """Retained pre-rename bundles remain readable after new runs switch names."""
    run = make_run(tmp_path)
    canonical = run / "agent_06-07-08-09-optimized"
    legacy = run / "agent_06-optimized"
    canonical.rename(legacy)

    index = ReviewIndex.from_directory(run)

    optimized_stage = next(item for item in index.stages if item["stage_id"] == "agent_06")
    assert optimized_stage["directory"] == "agent_06-optimized"
    assert index.rules[0]["artifact_path"] == "agent_06-optimized/optimized_compliance_knowledge_graph.json"
    assert index.relationships[0]["artifact_path"] == "agent_06-optimized/optimized_compliance_knowledge_graph.json"


def test_index_treats_an_explicit_null_status_field_as_unknown_not_none(tmp_path: Path) -> None:
    """Real pipeline output can carry an explicit `"risk_level": null` for a
    rule the extraction agent left unclassified (confirmed against the real
    mortgage run's optimized_compliance_knowledge_graph.json). `.get(key,
    "unknown")` only substitutes when the key is *absent*, so an explicit
    null used to leak straight through as None -- which crashed the review
    workbench's frontend (it assumes these are always non-empty strings and
    calls `.replaceAll()` on them) with a full white-screen render failure.
    """
    run = make_run(tmp_path)
    graph_path = run / "agent_06-07-08-09-optimized" / "optimized_compliance_knowledge_graph.json"
    graph = json.loads(graph_path.read_text())
    rule = graph["business_rules"][0]
    rule["risk_level"] = None
    rule["rule_type"] = None
    rule["readiness"]["status"] = None
    rule["grounding"]["status"] = None
    graph_path.write_text(json.dumps(graph), encoding="utf-8")

    row = ReviewIndex.from_directory(run).rules[0]
    assert row["risk_level"] == "unknown"
    assert row["rule_type"] == "unknown"
    assert row["readiness_status"] == "unknown"
    assert row["grounding_status"] == "unknown"


def test_index_preserves_and_indexes_multiple_source_references(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    graph_path = run / "agent_06-optimized" / "optimized_compliance_knowledge_graph.json"
    graph = json.loads(graph_path.read_text())
    graph["business_rules"][0]["source_reference"] = [
        {"chunk_path": "site/privacy-a.txt", "section_id": "A", "source_text": "Collect email."},
        {"chunk_path": "site/privacy-b.txt", "section_id": "B", "source_text": "Use email for support."},
    ]
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    index = ReviewIndex.from_directory(run)
    row = index.rules[0]
    assert isinstance(row["source_reference"], list)
    assert len([item for item in row["evidence"] if item["field_path"] == "source_reference"]) == 2


def test_index_writes_contract_and_search_database(tmp_path: Path) -> None:
    index = build_review_index(make_run(tmp_path), tmp_path / "index")
    output = tmp_path / "index"
    for name in ("run_summary.json", "run_manifest.json", "stage_index.json", "stage_status.json", "rule_index.jsonl", "relationship_index.jsonl", "document_index.jsonl", "evidence_index.jsonl", "comparison_keys.json", "search.sqlite"):
        assert (output / name).exists(), name
    payload = json.loads((output / "run_summary.json").read_text())
    assert payload["rule_count"] == 1
    assert index.to_dict()["run_id"] == "fixture-run"


def test_index_surfaces_executable_model_stage(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    for filename, body in (("compliance_decisions.dmn", "<definitions />"), ("compliance_workflows.bpmn", "<definitions />"), ("compliance_reviews.cmmn", "<definitions />"), ("semantic_vocabulary_profile.json", "{}"), ("executable_model_report.json", "{}")):
        (run / "agent_11-executable-models" / filename).parent.mkdir(parents=True, exist_ok=True)
        (run / "agent_11-executable-models" / filename).write_text(body, encoding="utf-8")
    index = ReviewIndex.from_directory(run)
    stage = next(item for item in index.stages if item["stage_id"] == "agent_11")
    assert stage["status"] == "completed"
    assert {item["name"] for item in stage["artifacts"]} == {"compliance_decisions.dmn", "compliance_workflows.bpmn", "compliance_reviews.cmmn", "semantic_vocabulary_profile.json", "executable_model_report.json"}


def test_missing_run_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ReviewIndex.from_directory(tmp_path / "missing")


def test_malformed_checkpoint_is_a_visible_failure(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    with (run / "agent_03-rules" / "batch_results.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("not-json\n")
    index = ReviewIndex.from_directory(run)
    assert index.run_summary["status"] == "requires_review"
    assert any(item["check"] == "agent_03" and item["severity"] == "error" for item in index.diagnostics)
