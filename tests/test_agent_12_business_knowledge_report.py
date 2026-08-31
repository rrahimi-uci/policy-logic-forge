import json
import xml.etree.ElementTree as ET
from pathlib import Path

from agents.agent_12_business_knowledge_report import _dependency_graph_layout, _dependency_graph_svg, generate, main


def _graph():
    return {
        "entity_types": {
            "CUSTOMER": {"concept_kind": "actor_role", "definition": "A policy customer.", "source_evidence": [{"chunk_path": "policy/001.txt", "section_id": "s1", "source_text": "Customer means a person using the service."}]},
        },
        "relationships": {
            "CUSTOMER_OWNS_ACCOUNT": {"source_entity": "CUSTOMER", "target_entity": "ACCOUNT", "source_evidence": [{"chunk_path": "policy/001.txt", "section_id": "s1", "source_text": "Customer owns an account."}]},
        },
        "business_rules": [
            {
                "rule_id": "R-1", "rule_name": "Customer consent", "rule_type": "consent", "requires_review": True,
                "description": "A customer must consent before processing.", "confidence_score": 75,
                "condition_predicates": [{"variable": "consent", "operator": "==", "value": True}],
                "outcomes": [{"variable": "processing_allowed", "operator": "=", "value": False}],
                "variables": [{"name": "consent", "type": "boolean", "role": "input"}, {"name": "processing_allowed", "type": "boolean", "role": "output"}],
                "related_entities": ["CUSTOMER"], "source_reference": {"chunk_path": "policy/001.txt", "section_id": "s1", "source_text": "Customer consent is required before processing."},
                "quarantined_claims": [{"field_path": "counterparties", "value": "POLICY_RECORD", "reason": "not an actor"}],
                "grounding": {
                    "status": "failed",
                    "counts": {"supported": 4, "contradicted": 1, "insufficient_evidence": 2},
                    "invalid_evidence_records": 0,
                    "relationship_status": "failed",
                    "dimensions": {
                        "core_rule": {"status": "failed"},
                        "enrichment": {"status": "certified"},
                        "contract": {"status": "certified"},
                    },
                },
                "readiness": {"failed_sections": [7]}, "review_route": {"route": "human_review", "human_review_required": True, "reasons": ["Evidence needs confirmation"]},
            },
        ],
        "dependency_details": {"dependencies": [{"source_rule_id": "R-1", "target_rule_id": "R-1", "dependency_type": "self"}]},
    }


def test_dependency_graph_preserves_direction_and_assigns_degree_layers():
    layout = _dependency_graph_layout(
        [
            {"source_rule_id": "R-0", "target_rule_id": "R-1", "dependency_type": "prerequisite"},
            {"source_rule_id": "R-1", "target_rule_id": "R-2", "dependency_type": "condition"},
            {"source_rule_id": "R-2", "target_rule_id": "R-1", "dependency_type": "back-link"},
            {"source_rule_id": "R-2", "target_rule_id": "R-2", "dependency_type": "self"},
        ],
        ["R-0", "R-isolated"],
    )

    assert layout["layers"] == {0: ["R-0", "R-isolated"], 1: ["R-1"], 2: ["R-2"]}
    assert layout["degrees"] == {"R-0": 0, "R-1": 1, "R-2": 2, "R-isolated": 0}
    assert layout["isolated_nodes"] == ["R-isolated"]
    svg = _dependency_graph_svg(layout)
    assert 'aria-label="Directed dependency graph layered by degree"' in svg
    assert 'marker-end="url(#dependency-arrow)"' in svg
    assert 'data-source="R-0" data-target="R-1"' in svg
    assert 'data-source="R-2" data-target="R-1"' in svg
    assert 'data-degree="2"' in svg


def test_agent_12_generates_self_contained_report_with_traceability(tmp_path: Path):
    graph_file = tmp_path / "graph.json"
    dags_file = tmp_path / "dags.json"
    models = tmp_path / "models"
    organized = tmp_path / "organized" / "policy"
    models.mkdir(); organized.mkdir(parents=True)
    (organized / "001.txt").write_text("Customer consent is required before processing.", encoding="utf-8")
    graph_file.write_text(json.dumps(_graph()), encoding="utf-8")
    dags_file.write_text(json.dumps({"dags": [{"dag_id": "d1", "rule_ids": ["R-1"]}]}), encoding="utf-8")
    (models / "compliance_decisions.dmn").write_bytes(b'<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/" xmlns:ctc="https://github.com/rrahimi-uci/policy-logic-forge/executable/1"><decision ctc:ruleId="R-1"/></definitions>')
    (models / "compliance_workflows.bpmn").write_bytes(b'<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL/" xmlns:ctc="https://github.com/rrahimi-uci/policy-logic-forge/executable/1"><process ctc:ruleId="R-1"/></definitions>')
    (models / "compliance_reviews.cmmn").write_bytes(b'<definitions xmlns="http://www.omg.org/spec/CMMN/20151109/MODEL" xmlns:ctc="https://github.com/rrahimi-uci/policy-logic-forge/executable/1"><case ctc:ruleId="R-1"/></definitions>')

    manifest = generate(graph_file, dags_file, models, tmp_path / "report", organized)
    report = (tmp_path / "report" / "business_knowledge_report.html").read_text(encoding="utf-8")

    assert manifest["rule_count"] == 1
    assert manifest["concept_count"] == 2  # governed concepts only: CUSTOMER and ACCOUNT
    assert manifest["decision_variable_count"] == 2
    assert manifest["rule_local_decision_variable_count"] == 2
    assert manifest["reusable_decision_variable_count"] == 0
    assert manifest["concept_coverage_rate"] == 100.0
    assert manifest["review_required_rate"] == 100.0
    assert manifest["human_review_rate"] == 100.0
    assert manifest["quality_hold_count"] == 1
    assert manifest["quality_hold_rate"] == 100.0
    assert manifest["review_route_counts"] == {"human_review": 1}
    assert manifest["fact_type_count"] == 1
    assert manifest["fact_type_grounding_rate"] == 0.0
    assert manifest["concept_evidence_coverage_rate"] == 100.0
    assert manifest["confidence_distribution"] == {"75–89%": 1}
    assert manifest["confidence_source_counts"] == {"unattributed_score": 1}
    assert manifest["grounding_claim_counts"] == {"contradicted": 1, "insufficient_evidence": 2, "supported": 4}
    assert manifest["grounding_claim_support_rate"] == 57.1
    assert manifest["grounding_dimensions"]["core_rule"]["failed_count"] == 1
    assert manifest["grounding_dimensions"]["enrichment"]["certified_count"] == 1
    assert manifest["grounding_dimensions"]["contract"]["certified_count"] == 1
    assert manifest["grounding_dimensions"]["relationship"]["failed_count"] == 1
    assert manifest["quarantined_claim_count"] == 1
    assert manifest["rules_with_quarantined_claims"] == 1
    assert manifest["grounded_rule_count"] == 0
    assert manifest["grounding_coverage_rate"] == 0.0
    assert manifest["source_pointer_count"] == 1
    assert manifest["source_pointer_coverage_rate"] == 100.0
    assert "SBVR vocabulary" in report
    assert "Vocabulary workbench" in report
    assert "Decision variables are not SBVR concepts" in report
    assert "Executable symbol registry" in report
    assert "Core-rule holds" in report
    assert "Enrichment holds" in report
    assert "Quarantined claims" in report
    assert "Concept type mix" in report
    assert "Most connected concepts" in report
    assert 'id="concept-search"' in report
    assert 'id="concept-grid"' in report
    assert 'id="fact-types"' in report
    assert "applyConceptFilters" in report
    assert "Readiness, grounding and confidence" in report
    assert "logic-expression" in report
    assert "Raw structured contract" in report
    assert "75.0%" in report
    assert "score origin not recorded" in report
    assert "Grounding not certified" in report
    assert "1 contradiction · 2 evidence gaps" in report
    assert "4/7 claims supported" in report
    assert 'data-kind="actor_role"' in report
    assert 'href="#concept-CUSTOMER"' in report
    assert 'href="#fact-CUSTOMER_OWNS_ACCOUNT"' in report
    assert "Customer consent" in report
    assert "Customer consent is required before processing." in report
    assert "Human-review queue (1)" in report
    assert "Quality holds outside the human queue (0)" in report
    assert "Explicit human judgment required" in report
    assert "data-tab=\"models\"" in report
    assert "Directed rule relationship graph" in report
    assert "Dependency topology" in report
    assert "dependency-graph-svg" in report
    assert "degree 0" in report
    assert "source_rule_id → target_rule_id" in report
    assert report.count("Open highlighted XML") == 3
    assert report.count('class="xml-viewer"') == 3
    assert report.count('class="xml-line"') >= 3
    assert 'class="xml-tag"' in report
    assert 'class="xml-attr"' in report
    assert 'class="xml-value"' in report
    assert "0001" in report
    assert "compliance_decisions.dmn" in report
    assert "compliance_workflows.bpmn" in report
    assert "compliance_reviews.cmmn" in report
    assert "report-data" in report
    assert 'href="#source-' in report
    assert "no external assets" in report.lower()
    assert json.loads((tmp_path / "report" / "business_knowledge_report_manifest.json").read_text())["validation"] == "pass"


def test_agent_12_separates_human_queue_from_nonhuman_quality_holds(tmp_path: Path):
    graph = _graph()
    graph["business_rules"].append({
        "rule_id": "R-2", "rule_name": "Evidence follow-up", "rule_type": "documentation",
        "requires_review": True, "description": "Evidence must be confirmed.",
        "review_route": {"route": "case_management", "human_review_required": False, "reasons": ["Evidence gap"]},
    })
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(json.dumps(graph), encoding="utf-8")

    manifest = generate(graph_file, None, tmp_path / "models", tmp_path / "report")
    report = (tmp_path / "report" / "business_knowledge_report.html").read_text(encoding="utf-8")

    assert manifest["review_required_count"] == 2
    assert manifest["human_review_count"] == 1
    assert manifest["nonhuman_quality_hold_count"] == 1
    assert manifest["review_route_counts"] == {"case_management": 1, "human_review": 1}
    assert "Human-review queue (1)" in report
    assert "Quality holds outside the human queue (1)" in report
    assert "case management" in report
    assert 'id="rule-route"' in report
    assert 'data-route="case_management"' in report


def test_agent_12_handles_missing_optional_upstream_models(tmp_path: Path):
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(json.dumps({"business_rules": []}), encoding="utf-8")
    manifest = generate(graph_file, None, tmp_path / "missing-models", tmp_path / "report")
    assert manifest["rule_count"] == 0
    assert manifest["model_info"]["DMN"]["exists"] is False


def test_agent_12_main_reports_missing_graph(tmp_path, monkeypatch):
    class Config:
        def get_optimized_dir(self): return tmp_path / "optimized"
        def get_dag_dir(self): return tmp_path / "dag"
        def get_executable_models_dir(self): return tmp_path / "models"
        def get_organized_dir(self): return tmp_path / "organized"
        def get_pipeline_base_path(self): return tmp_path

    monkeypatch.setattr("agents.agent_12_business_knowledge_report.get_config", lambda: Config())
    assert main([]) == 2
