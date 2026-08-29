import json

import agents.agent_11_executable_model_generator as agent_11
from agents.agent_11_executable_model_generator import generate


def test_agent_11_persists_valid_models_and_report(tmp_path):
    graph = {
        "business_rules": [{
            "rule_id": "r1", "rule_name": "Decision", "requires_review": True,
            "condition_predicates": [{"variable": "ok", "operator": "==", "value": True}],
            "variables": [{"name": "ok", "type": "boolean", "role": "input"}],
            "outcomes": [{"variable": "result", "operator": "=", "value": "allow"}],
            "source_reference": {"chunk_path": "policy.txt", "section_id": "s1"},
        }]
    }
    graph_file = tmp_path / "graph.json"
    dags_file = tmp_path / "dags.json"
    graph_file.write_text(json.dumps(graph), encoding="utf-8")
    dags_file.write_text(json.dumps({"dags": [{"dag_id": "d1", "rule_ids": ["r1"], "topological_order": ["r1"]}]}), encoding="utf-8")
    report = generate(graph_file, dags_file, tmp_path / "out")
    assert report["rule_count"] == 1
    assert report["review_required_rules"] == 1
    assert report["review_required_rate"] == 100.0
    assert report["human_review_required_rules"] == 0
    assert report["human_review_rate"] == 0.0
    assert report["review_route_counts"]["none"] == 1
    assert (tmp_path / "out" / "compliance_decisions.dmn").is_file()
    assert (tmp_path / "out" / "compliance_workflows.bpmn").is_file()
    assert (tmp_path / "out" / "compliance_reviews.cmmn").is_file()
    assert (tmp_path / "out" / "semantic_vocabulary_profile.json").is_file()
    assert report["bpmn_rule_count"] == 0
    assert report["bpmn_omitted_rule_count"] == 1
    assert len(report["source_graph_sha256"]) == 64
    assert len(report["source_dags_sha256"]) == 64
    assert json.loads((tmp_path / "out" / "executable_model_report.json").read_text())["validation"] == "pass"
    # This fixture's rule has no predicate_id, so it is cleanly refused (not
    # an exception) by LExec compilation -- 0 compiled, 1 refused. That the
    # DMN/BPMN outputs above landed regardless, and generate() did not
    # raise, is the point: a fail-closed refusal is not a crash.
    assert report["lexec_compilation"]["rules_compiled"] == 0
    assert report["lexec_compilation"]["rules_refused"] == 1
    assert (tmp_path / "out" / "lexec_ir.json").is_file()


def test_agent_11_also_persists_lexec_compilation_artifacts_when_it_succeeds(tmp_path):
    graph = {
        "business_rules": [{
            "schema_version": "2.0", "rule_id": "r1", "rule_type": "constraint", "requires_review": False,
            "condition_predicates": [{"predicate_id": "p1", "variable": "ltv_ratio_percent", "operator": ">", "value": 80, "value_type": "number"}],
            "condition_logic": {"predicate_ref": "p1"},
            "outcomes": [{"variable": "pmi_required", "operator": "=", "value": True, "value_type": "boolean"}],
            "variables": [
                {"name": "ltv_ratio_percent", "type": "number", "role": "input"},
                {"name": "pmi_required", "type": "boolean", "role": "output"},
            ],
            "recommended_hit_policy": "UNIQUE",
            "applicability_scope": {}, "scope_basis": "genuinely_unscoped", "exceptions": [], "mandatory": True,
            "source_reference": {"chunk_path": "policy.txt", "section_id": "s1", "source_text": "LTV over 80% requires PMI.", "start_offset": 0, "end_offset": 26},
        }]
    }
    graph_file = tmp_path / "graph.json"
    dags_file = tmp_path / "dags.json"
    graph_file.write_text(json.dumps(graph), encoding="utf-8")
    dags_file.write_text(json.dumps({"dags": [{"dag_id": "d1", "rule_ids": ["r1"], "topological_order": ["r1"]}]}), encoding="utf-8")
    report = generate(graph_file, dags_file, tmp_path / "out")
    assert report["lexec_compilation"]["rules_compiled"] == 1
    assert report["lexec_compilation"]["table_proof_statuses"] == {"proved": 1}
    lexec_ir = json.loads((tmp_path / "out" / "lexec_ir.json").read_text())
    assert lexec_ir["tables"][0]["policy_proof"]["status"] == "proved"
    assert json.loads((tmp_path / "out" / "compilation_report.json").read_text())["rules_compiled"] == 1
    assert json.loads((tmp_path / "out" / "proof_records.json").read_text())["proofs"][0]["policy_proof"]["status"] == "proved"


class _Config:
    def __init__(self, root):
        self.root = root

    def get_optimized_dir(self):
        return self.root / "optimized"

    def get_dag_dir(self):
        return self.root / "dag"

    def get_executable_models_dir(self):
        return self.root / "models"


def test_agent_11_main_reports_missing_upstream_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_11, "get_config", lambda: _Config(tmp_path))
    assert agent_11.main() == 2


def test_agent_11_main_runs_from_configured_pipeline_paths(tmp_path, monkeypatch):
    optimized = tmp_path / "optimized"
    dag = tmp_path / "dag"
    optimized.mkdir(); dag.mkdir()
    graph = {"business_rules": [{
        "rule_id": "r1", "condition_predicates": [{"variable": "ok", "operator": "==", "value": True}],
        "variables": [{"name": "ok", "type": "boolean", "role": "input"}],
        "outcomes": [{"variable": "result", "value": "allow"}],
        "source_reference": {"chunk_path": "p.txt", "section_id": "s"},
    }]}
    (optimized / "optimized_compliance_knowledge_graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (dag / "dependency_dags.json").write_text(json.dumps({"dags": [{"dag_id": "d", "rule_ids": ["r1"], "topological_order": ["r1"]}]}), encoding="utf-8")
    monkeypatch.setattr(agent_11, "get_config", lambda: _Config(tmp_path))
    assert agent_11.main() == 0
    assert (tmp_path / "models" / "compliance_decisions.dmn").is_file()


def test_lower_and_prove_never_raises_on_a_malformed_graph(tmp_path):
    # "not a graph" has neither a business_rules key nor a list shape, so
    # utils.lexec_ir.lower_graph raises TypeError building it -- confirming
    # that surfaces as a warning and a None return, never an exception that
    # would take down the whole agent_11 run.
    assert agent_11._lower_and_prove("not a graph", tmp_path, document_id="x") is None
    assert not (tmp_path / "lexec_ir.json").exists()
