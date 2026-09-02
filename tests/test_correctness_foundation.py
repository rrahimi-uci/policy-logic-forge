"""Regression tests for the cross-stage correctness foundation."""
from agents.agent_02_entity_extractor import EntityRelationshipExtractor
from agents.agent_06_knowledge_graph_optimizer import KnowledgeGraphOptimizer


def test_agent_02_reports_measured_catalog_integrity_not_fabricated_coverage():
    catalog = {
        "entity_types": {
            "PERSON": {
                "definition": "A data subject.",
                "concept_kind": "actor_role",
                "attributes": ["a", "b", "c", "d", "e"],
                "source_evidence": [{"chunk_path": "d/1.txt", "source_text": "a person"}],
            }
        },
        "relationships": {},
    }

    metrics = EntityRelationshipExtractor.analyze_extraction_quality(
        object(), extraction_results=catalog, iteration=2
    )

    assert metrics["overall_score"] == 100.0
    assert metrics["coverage_score"] is None
    assert "not measured" in metrics["coverage_scope"]
    assert metrics["business_rules_score"] is None


def test_agent_06_derives_relationships_only_after_deduplication():
    optimizer = object.__new__(KnowledgeGraphOptimizer)
    observed = {}

    def deduplicate(_rules):
        return [
            {"rule_id": "A", "rule_name": "A"},
            {"rule_id": "B", "rule_name": "B"},
        ], {"total_removed": 1}

    def analyze(canonical_rules):
        observed["ids"] = [rule["rule_id"] for rule in canonical_rules]
        return canonical_rules, {"total_dependencies": 0}

    optimizer.deduplicate_rules = deduplicate
    optimizer.analyze_dependencies = analyze

    optimized, dedup_metadata, _ = optimizer.optimize_parallel([
        {"rule_id": "A"}, {"rule_id": "B"}, {"rule_id": "REMOVED"}
    ])

    assert observed["ids"] == ["A", "B"]
    assert [rule["rule_id"] for rule in optimized] == ["A", "B"]
    assert dedup_metadata["total_removed"] == 1


def test_agent_06_closes_exact_duplicate_gap_across_llm_batches(monkeypatch):
    optimizer = object.__new__(KnowledgeGraphOptimizer)
    optimizer.max_workers = 1
    optimizer._deduplicate_rules_single = lambda rules: (
        rules, {"deduplication_analysis": {"duplicate_groups": []}, "rules_removed_ids": []}
    )
    monkeypatch.setenv("KG_LLM_CONCURRENCY", "1")
    base = {
        "schema_version": "2.0",
        "rule_type": "obligation",
        "condition_predicates": [],
        "condition_logic": {"constant": True},
        "outcomes": [{"variable": "retain", "operator": "=", "value": True}],
        "variables": [{"name": "retain", "type": "boolean", "role": "output"}],
        "applicability_scope": {"jurisdiction": ["US"]},
    }
    first = {**base, "rule_id": "R-1", "source_reference": {"chunk_path": "a.txt"}}
    second = {**base, "rule_id": "R-2", "source_reference": {"chunk_path": "b.txt"}}

    rules, metadata = optimizer._deduplicate_rules_batched([first, second], batch_size=1)

    assert [rule["rule_id"] for rule in rules] == ["R-1"]
    assert metadata["rules_removed_ids"] == ["R-2"]
    assert metadata["deduplication_analysis"]["cross_batch_exact_groups"] == 1
    assert len(rules[0]["source_reference"]) == 2
