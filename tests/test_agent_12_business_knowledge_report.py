import json
from pathlib import Path

from agents.agent_12_business_knowledge_report import (
    _bar_chart_svg,
    _automation_readiness,
    _bpmn_flow_html,
    _cmmn_plan_html,
    _condition_expression,
    _dependency_graph_layout,
    _dependency_graph_svg,
    _dmn_table_html,
    _donut_chart_svg,
    _formal_logic_html,
    _model_badges_html,
    _outcome_badge_html,
    _outcome_cards_html,
    _outcome_chip_html,
    _outcome_kind,
    _parse_bpmn_processes,
    _parse_cmmn_cases,
    _parse_dmn_decisions,
    _percentile,
    _rule_connectivity,
    _rule_model_diagrams_html,
    _traceability_html,
    generate,
    main,
)
from utils.executable_models import build_dags_bpmn, build_graph_dmn
from utils.semantic_artifacts import build_review_cmmn


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
    # Nodes carry a stable id for the Dependencies tab's click-to-highlight JS.
    assert 'data-node-id="R-0"' in svg


def test_rule_connectivity_computes_true_degree_not_bfs_depth():
    """True in+out degree is a different question from the BFS 'degree lane'
    depth _dependency_graph_layout computes for visual layout -- R-2 sits at
    BFS depth 2 (two hops from the root) but has degree 2 (one in, one out),
    same as R-1 which sits at depth 1. The two must not be conflated."""
    edges = [
        {"source_rule_id": "R-0", "target_rule_id": "R-1", "dependency_type": "prerequisite"},
        {"source_rule_id": "R-1", "target_rule_id": "R-2", "dependency_type": "condition"},
    ]
    connectivity = _rule_connectivity(edges, ["R-0", "R-1", "R-2", "R-isolated"])
    assert connectivity["degree_buckets"] == {"0": 1, "1–2": 3, "3–5": 0, "6–10": 0, "11+": 0}
    assert connectivity["most_connected"][0] == ("R-1", 2)
    assert connectivity["isolated_rule_ids"] == ["R-isolated"]


def test_automation_readiness_is_policy_neutral_and_ignores_review_flags():
    rule = _graph()["business_rules"][0]
    first = _automation_readiness(rule)
    rule["requires_review"] = False
    rule["review_route"] = {"route": "none"}
    second = _automation_readiness(rule)

    assert first == second
    assert 0 <= first["score"] <= 100
    assert sum(first["weights"].values()) == 100
    assert set(first["components"]) == set(first["weights"])


def test_model_badges_html_marks_present_and_absent_kinds():
    model_rule_ids = {"DMN": {"R-1", "R-2"}, "BPMN": {"R-1"}, "CMMN": set()}
    html = _model_badges_html("R-1", model_rule_ids)
    assert html.count("model-badge-yes") == 2  # DMN, BPMN
    assert html.count("model-badge-no") == 1  # CMMN
    assert ">DMN<" in html and ">BPMN<" in html and ">CMMN<" in html


def test_rule_model_diagrams_html_renders_only_kinds_this_rule_has():
    lookup = {
        "DMN": {"R-1": {"inputs": [{"name": "active", "type": "boolean"}], "outputs": [], "input_entries": [], "output_entries": []}},
        "BPMN": {}, "CMMN": {},
    }
    html = _rule_model_diagrams_html("R-1", lookup)
    assert "rule-model-diagrams" in html
    assert html.count("rule-model-block") == 1
    assert "DMN" in html


def test_rule_model_diagrams_html_empty_state_when_no_models_exist():
    assert "No executable model" in _rule_model_diagrams_html("R-9", {"DMN": {}, "BPMN": {}, "CMMN": {}})


def test_traceability_html_renders_full_path_with_evidence_entities_dependencies_and_model():
    rule = {
        "source_reference": {"chunk_path": "policy/001.txt", "section_id": "s1", "source_text": "Customer consent is required."},
        "related_entities": ["CUSTOMER"],
        "dependencies": [{"depends_on_rule": "R-2"}],
    }
    html = _traceability_html(rule, "R-1", ["source-abc123"], {"DMN": {"R-1"}, "BPMN": set(), "CMMN": set()})
    assert "trace-path" in html
    assert 'href="#source-abc123"' in html
    assert "CUSTOMER" in html
    assert 'href="#rule-R-2"' in html
    assert ">DMN<" in html


def test_traceability_html_shows_empty_states_when_nothing_is_linked():
    html = _traceability_html({}, "R-9", [], {"DMN": set(), "BPMN": set(), "CMMN": set()})
    assert "No source pointer" in html
    assert "None recorded" in html  # entities
    assert "No dependencies" in html
    assert "No executable model" in html


def test_bar_chart_svg_renders_one_bar_per_item_scaled_to_the_max():
    svg = _bar_chart_svg([("Category A", 10), ("Category B", 5)])
    assert svg.count('class="chart-bar"') == 2
    assert "Category A" in svg and "Category B" in svg


def test_bar_chart_svg_empty_state():
    assert "No data available" in _bar_chart_svg([])


def test_donut_chart_svg_renders_one_segment_per_nonzero_item_with_a_legend():
    svg = _donut_chart_svg([("Route A", 3), ("Route B", 0), ("Route C", 1)])
    assert svg.count('class="chart-donut-seg"') == 2  # zero-count items are skipped
    assert "Route A" in svg and "Route C" in svg and "Route B" not in svg
    assert ">4<" in svg  # total in the donut center


def test_donut_chart_svg_empty_state():
    assert "No data available" in _donut_chart_svg([])


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
    assert 0 <= manifest["automation_readiness_score_average"] <= 100
    assert manifest["automation_readiness_score_median"] == manifest["automation_readiness_score_average"]
    assert manifest["automation_readiness_score_p10"] == manifest["automation_readiness_score_average"]
    assert manifest["automation_readiness_score_minimum"] == manifest["automation_readiness_score_average"]
    assert manifest["automation_readiness_score_maximum"] == manifest["automation_readiness_score_average"]
    assert sum(manifest["automation_readiness_score_weights"].values()) == 100
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
    # New analytics fields feeding the Overview dashboard's charts.
    assert manifest["model_type_counts"] == {"DMN": 1, "BPMN": 1, "CMMN": 1}
    assert manifest["degree_buckets"]["1–2"] == 1  # R-1's self-referencing edge
    assert manifest["isolated_rule_count"] == 0
    assert "rule_summary" in manifest and 0 <= manifest["rule_summary"]["R-1"]["automation_readiness_score"] <= 100
    assert manifest["dependency_edges"]
    assert "Presentation &amp; Knowledge Exploration" in report
    assert "Business knowledge, made transparent." in report
    assert "A self-contained, source-traceable view of the extracted domain knowledge." in report
    assert "Every rule is linked to its source and assigned a neutral <strong>0–100 Automation Readiness Score</strong>" in report
    assert "Your environment, risk tolerance, and domain policies determine the appropriate acceptance threshold." in report
    assert 'id="scoring-definition" class="panel score-definition"' in report
    assert '<a class="hero-score-link" href="#scoring-definition">View scoring definition ↓</a>' in report
    assert "How the Automation Readiness Score is calculated" in report
    assert "0.40 Core + 0.20 Context + 0.15 Contract + 0.10 Evidence + 0.10 Execution + 0.05 Relationships" in report
    for component, weight in (("Core grounding", "40%"), ("Context grounding", "20%"), ("Contract integrity", "15%"), ("Evidence integrity", "10%"), ("Executability", "10%"), ("Relationship support", "5%")):
        assert component in report
        assert f"<td>{weight}</td>" in report
    assert "SBVR vocabulary" in report
    assert "Vocabulary workbench" in report
    assert "Decision variables are not SBVR concepts" in report
    assert "Executable symbol registry" in report
    for removed_card in ("Quarantined claims", "Core support", "Context support", "Source documents", "Dependencies"):
        assert f'<div class="metric-label">{removed_card}</div>' not in report
    metric_labels = (
        "Total business rules",
        "Average and median readiness score",
        "10th-percentile readiness score",
        "Grounding claim support",
        "Contract integrity",
        "Relationship support",
        "Rules below the user-selected threshold",
        "Contradicted and insufficient-evidence claims",
    )
    assert report.count('<div class="metric-card') == len(metric_labels)
    for label in metric_labels:
        assert f'<div class="metric-label">{label}</div>' in report
    for removed_card in ("Score range", "SBVR concepts", "Decision variables", "Source pointers", "Grounding claims"):
        assert f'<div class="metric-label">{removed_card}</div>' not in report
    assert 'id="readiness-threshold"' in report
    assert "none is assumed" in report
    assert "updateThresholdMetric" in report
    assert "Concept type mix" in report
    assert "Most connected concepts" in report
    assert 'id="concept-search"' in report
    assert 'id="concept-grid"' in report
    assert 'id="fact-types"' in report
    assert "applyConceptFilters" in report
    assert "logic-expression" in report
    assert "Raw structured contract" in report
    assert "75.0%" in report
    assert "score origin not recorded" in report
    assert "Score factors" in report
    assert "1 contradiction · 2 evidence gaps" in report
    assert "4/7 claims supported" in report
    assert 'data-kind="actor_role"' in report
    assert 'href="#concept-CUSTOMER"' in report
    assert 'href="#fact-CUSTOMER_OWNS_ACCOUNT"' in report
    assert "Customer consent" in report
    assert "Customer consent is required before processing." in report
    # Models stay inline and the policy-neutral score explorer covers all rules.
    assert 'data-tab="models"' not in report
    assert 'id="score-table"' not in report
    assert 'data-tab="scores"' not in report
    assert "no acceptance threshold" in report.lower()
    assert "quality hold" not in report.lower()
    assert "Directed rule relationship graph" in report
    assert "Dependency topology" in report
    assert "dependency-graph-svg" in report
    assert 'id="dep-side-panel"' in report
    assert "degree 0" in report
    assert "source_rule_id → target_rule_id" in report
    # Per-rule model badges/diagrams replace the removed Models tab.
    assert "model-badges" in report
    assert "model-badge-yes" in report
    assert "trace-path" in report
    assert "report-data" in report
    assert 'href="#source-' in report
    assert "no external assets" in report.lower()
    assert json.loads((tmp_path / "report" / "business_knowledge_report_manifest.json").read_text())["validation"] == "pass"


def test_agent_12_rule_explorer_scores_every_rule_without_policy_labels(tmp_path: Path):
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

    assert set(manifest["rule_summary"]) == {"R-1", "R-2"}
    assert all("automation_readiness_score" in item for item in manifest["rule_summary"].values())
    assert report.count('class="rule-row"') == 2
    assert 'id="rule-score-min"' in report
    assert 'id="rule-score-max"' in report
    assert 'data-tab="scores"' not in report
    assert "case management" not in report
    assert "quality hold" not in report.lower()


def test_percentile_uses_linear_interpolation_and_handles_boundaries():
    values = [0, 10, 20, 30, 40]
    assert _percentile(values, 0.5) == 20.0
    assert _percentile(values, 0.1) == 4.0
    assert _percentile(values, -1) == 0.0
    assert _percentile(values, 2) == 40.0
    assert _percentile([], 0.5) == 0.0


def test_agent_12_omits_empty_confidence_distribution(tmp_path: Path):
    graph = _graph()
    for rule in graph["business_rules"]:
        rule.pop("confidence_score", None)
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(json.dumps(graph), encoding="utf-8")

    manifest = generate(graph_file, None, tmp_path / "models", tmp_path / "report")
    report = (tmp_path / "report" / "business_knowledge_report.html").read_text(encoding="utf-8")

    assert manifest["confidence_distribution"] == {}
    assert manifest["confidence_source_counts"] == {"not_reported": 1}
    assert "Confidence distribution" not in report
    assert "Confidence provenance:" not in report


def test_outcome_kind_classifies_booleans_numbers_lists_and_text():
    assert _outcome_kind(True, "boolean") == "true"
    assert _outcome_kind(False, "boolean") == "false"
    assert _outcome_kind("true", "boolean") == "true"  # value_type-declared boolean stored as a string
    assert _outcome_kind(42, None) == "number"
    assert _outcome_kind(3.5, "number") == "number"
    assert _outcome_kind(["a", "b"], None) == "list"
    assert _outcome_kind("manual_underwriting", "enum") == "text"


def test_outcome_badge_renders_true_false_as_pills_not_raw_python_bool():
    assert '<span class="outcome-badge type-true">TRUE</span>' == _outcome_badge_html(True, "boolean")
    assert '<span class="outcome-badge type-false">FALSE</span>' == _outcome_badge_html(False, "boolean")


def test_outcome_badge_explodes_a_list_into_individual_chips():
    html = _outcome_badge_html(["financial condition", "staffing"], "list")
    assert html.count("outcome-value-item") == 2
    assert "financial condition" in html and "staffing" in html


def test_outcome_cards_render_one_card_per_outcome_with_readable_and_raw_name():
    outcomes = [
        {"variable": "loan_eligible_for_sale", "value": True, "value_type": "boolean"},
        {"variable": "minimum_down_payment_percentage", "value": 3, "value_type": "number"},
    ]
    html = _outcome_cards_html(outcomes)
    assert html.count("outcome-card") == 2
    assert "Loan eligible for sale" in html  # humanized label
    assert "loan_eligible_for_sale" in html  # raw variable name retained
    assert '<span class="outcome-badge type-true">TRUE</span>' in html
    assert '<span class="outcome-badge type-number"' in html and ">3<" in html


def test_outcome_cards_report_none_declared_for_empty_outcomes():
    assert "None declared" in _outcome_cards_html([])


def test_outcome_chip_marks_boolean_outcomes_for_banner_styling():
    true_chip = _outcome_chip_html({"variable": "eligible", "value": True})
    false_chip = _outcome_chip_html({"variable": "eligible", "value": False})
    assert 'outcome-chip ov-true' in true_chip
    assert 'outcome-chip ov-false' in false_chip
    assert "eligible" in true_chip and "true" in true_chip


def test_formal_logic_html_wraps_multiple_outcomes_as_separate_chips_and_cards():
    """A rule with several outcomes must not collapse into one AND-joined
    sentence -- each outcome gets its own banner chip and its own card in
    the Outcomes panel."""

    rule = {
        "condition_predicates": [{"variable": "loan_secured_by_manufactured_home", "operator": "==", "value": True}],
        "outcomes": [
            {"variable": "underwriting_system", "value": "DU", "value_type": "enum"},
            {"variable": "property_type_identification_required", "value": True, "value_type": "boolean"},
            {"variable": "project_type_identification_required", "value": True, "value_type": "boolean"},
        ],
        "exceptions": [], "variables": [],
    }
    html = _formal_logic_html(rule)
    assert html.count('class="outcome-chip') == 3  # one banner chip per outcome
    assert html.count('class="outcome-card"') == 3  # one card per outcome
    assert '<div class="logic-if">' in html and '<div class="logic-then-row">' in html
    # No stray "?" placeholder where an outcome lacks an explicit operator.
    assert " ? " not in html


def test_formal_logic_html_falls_back_when_no_outcomes_declared():
    html = _formal_logic_html({"condition_predicates": [], "outcomes": [], "exceptions": [], "variables": []})
    assert "evaluate outcome" in html
    assert "None declared" in html  # empty Outcomes panel


def _model_source_graph():
    """One BPMN-eligible rule (explicit ordered workflow with a business-rule
    task, for decision_ref cross-linking) and one CMMN-eligible rule (routed
    to case_management) -- built the same shape as
    tests/test_executable_models.py's own fixtures, so parsing is tested
    against real utils.executable_models/utils.semantic_artifacts generator
    output, not hand-approximated XML."""

    return {"business_rules": [
        {
            "rule_id": "R-1", "rule_name": "Allow processing", "requires_review": False,
            "grounding": {"status": "certified"},
            "condition_predicates": [{"variable": "active", "operator": "==", "value": True}],
            "variables": [{"name": "active", "type": "boolean", "role": "input"}],
            "outcomes": [{"variable": "decision", "value": "allow"}],
            "execution": {"dmn": {"hit_policy": "UNIQUE"}},
            "source_reference": {"chunk_path": "policy.txt", "section_id": "s1"},
            "responsible_party": "SELLER_SERVICER",
            "workflow_semantics": {
                "kind": "prescriptive_process", "basis": "explicit_in_source",
                "trigger_event": "Application received", "actor_role": "SELLER_SERVICER",
                "ordered_steps": [
                    {"step_id": "review", "name": "Review application", "kind": "user_task"},
                    {"step_id": "decide", "name": "Apply eligibility decision", "kind": "business_rule_task"},
                ],
                "evidence": [{"chunk_path": "policy.txt", "section_id": "s1", "source_text": "After receipt, review the application and apply the eligibility decision."}],
            },
        },
        {
            "rule_id": "R-2", "rule_name": "Escalate for review", "requires_review": True,
            "grounding": {"status": "failed"},
            "condition_predicates": [{"variable": "flagged", "operator": "==", "value": True}],
            "variables": [{"name": "flagged", "type": "boolean", "role": "input"}],
            "outcomes": [{"variable": "decision", "value": "hold"}],
            "source_reference": {"chunk_path": "policy.txt", "section_id": "s2"},
            "review_route": {"route": "case_management", "human_review_required": False, "reasons": ["Evidence gap"]},
        },
    ]}


def _write_real_models(models_dir: Path, graph: dict) -> None:
    dags = {"dags": [{"dag_id": "d1", "rule_ids": ["R-1", "R-2"],
                       "topological_order": ["d1_cycle_1"],
                       "cycle_groups": [{"group_id": "d1_cycle_1", "rule_ids": ["R-1", "R-2"]}]}]}
    (models_dir / "compliance_decisions.dmn").write_bytes(build_graph_dmn(graph))
    (models_dir / "compliance_workflows.bpmn").write_bytes(build_dags_bpmn(graph, dags))
    (models_dir / "compliance_reviews.cmmn").write_bytes(build_review_cmmn(graph))


def test_parse_dmn_decisions_reads_real_generator_output(tmp_path):
    graph = _model_source_graph()
    _write_real_models(tmp_path, graph)
    decisions = _parse_dmn_decisions(tmp_path / "compliance_decisions.dmn")
    by_id = {d["rule_id"]: d for d in decisions}
    assert set(by_id) == {"R-1", "R-2"}
    r1 = by_id["R-1"]
    assert r1["inputs"] == [{"name": "active", "type": "boolean"}]
    assert r1["outputs"] == [{"name": "decision", "type": "string"}]
    assert r1["input_entries"] == ["true"]
    assert r1["output_entries"] == ['"allow"']  # _feel() quotes non-numeric/boolean FEEL literals
    assert r1["hit_policy"] == "UNIQUE"
    assert r1["grounding_status"] == "certified"


def test_parse_bpmn_processes_preserves_document_order_and_decision_ref(tmp_path):
    graph = _model_source_graph()
    _write_real_models(tmp_path, graph)
    processes = _parse_bpmn_processes(tmp_path / "compliance_workflows.bpmn")
    assert len(processes) == 1  # only R-1 has explicit ordered workflow semantics
    process = processes[0]
    assert process["rule_id"] == "R-1"
    assert process["trigger_event"] == "Application received"
    assert process["actor_role"] == "SELLER_SERVICER"
    assert [node["kind"] for node in process["nodes"]] == ["start", "user_task", "business_rule_task", "end"]
    business_rule_node = process["nodes"][2]
    assert business_rule_node["name"] == "Apply eligibility decision"
    assert business_rule_node["decision_ref"]  # cross-links back to its DMN decision


def test_parse_cmmn_cases_reads_real_generator_output(tmp_path):
    graph = _model_source_graph()
    _write_real_models(tmp_path, graph)
    cases = _parse_cmmn_cases(tmp_path / "compliance_reviews.cmmn")
    assert len(cases) == 1  # only R-2 is routed to case_management/human_review
    case = cases[0]
    assert case["rule_id"] == "R-2"
    assert case["review_route"] == "case_management"
    assert [item["kind"] for item in case["items"]] == ["human_task", "milestone"]


def test_model_parsers_return_empty_list_for_a_missing_or_unparseable_file(tmp_path):
    missing = tmp_path / "does-not-exist.dmn"
    assert _parse_dmn_decisions(missing) == []
    assert _parse_bpmn_processes(missing) == []
    assert _parse_cmmn_cases(missing) == []
    broken = tmp_path / "broken.dmn"
    broken.write_text("not xml <<<", encoding="utf-8")
    assert _parse_dmn_decisions(broken) == []


def test_dmn_table_html_renders_input_and_output_columns():
    decision = {
        "hit_policy": "UNIQUE",
        "inputs": [{"name": "active", "type": "boolean"}],
        "outputs": [{"name": "decision", "type": "string"}],
        "input_entries": ["true"], "output_entries": ["allow"],
    }
    html = _dmn_table_html(decision)
    assert '<th class="dmn-col-input">active' in html
    assert '<th class="dmn-col-output">decision' in html
    assert '<td class="dmn-col-input"><code>true</code></td>' in html
    assert '<td class="dmn-col-output"><code>allow</code></td>' in html
    assert "UNIQUE" in html


def test_dmn_table_html_empty_state_for_a_structureless_decision():
    assert "No decision table structure" in _dmn_table_html({"inputs": [], "outputs": []})


def test_bpmn_flow_html_marks_dmn_backed_task_and_connects_steps_with_arrows():
    process = {"nodes": [
        {"kind": "start", "name": "Start"},
        {"kind": "business_rule_task", "name": "Apply eligibility decision", "decision_ref": "decision_R-1"},
        {"kind": "end", "name": "End"},
    ]}
    html = _bpmn_flow_html(process)
    assert html.count('<div class="bpmn-node ') == 3  # outer node divs only, not the icon/label/sub spans
    assert html.count('class="bpmn-arrow"') == 2
    assert "DMN-backed" in html
    assert "Apply eligibility decision" in html


def test_bpmn_flow_html_empty_state_for_no_ordered_steps():
    assert "No ordered workflow steps" in _bpmn_flow_html({"nodes": []})


def test_cmmn_plan_html_renders_unordered_items_without_arrows():
    case = {"items": [{"kind": "human_task", "name": "Review grounded findings"}, {"kind": "milestone", "name": "Review resolved"}]}
    html = _cmmn_plan_html(case)
    assert html.count('<div class="cmmn-item ') == 2  # outer item divs only, not the icon/kind/name children
    assert "→" not in html  # case items carry no forced sequence
    assert "Review grounded findings" in html and "Review resolved" in html


def test_cmmn_plan_html_empty_state_for_no_case_plan_items():
    assert "No case plan items" in _cmmn_plan_html({"items": []})


def test_agent_12_renders_real_dmn_bpmn_cmmn_diagrams_inline_per_rule(tmp_path: Path):
    """End-to-end: real generator output flows through to real diagrams
    rendered inline inside each rule's own row (the Models tab is gone), with
    working model-availability badges and the cross-tab/details navigation
    fix (the historically reported 'clicking links does nothing' bug)."""

    graph = _model_source_graph()
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(json.dumps(graph), encoding="utf-8")
    models = tmp_path / "models"
    models.mkdir()
    _write_real_models(models, graph)

    manifest = generate(graph_file, None, models, tmp_path / "report")
    report = (tmp_path / "report" / "business_knowledge_report.html").read_text(encoding="utf-8")

    assert manifest["rule_count"] == 2
    assert manifest["model_type_counts"] == {"DMN": 2, "BPMN": 1, "CMMN": 1}
    # Real structural diagrams, rendered inline per rule, not in a separate tab:
    assert 'data-tab="models"' not in report
    assert 'class="dmn-table"' in report
    assert 'class="bpmn-flow"' in report
    assert 'class="cmmn-plan"' in report
    assert "DMN-backed" in report
    assert "rule-model-diagrams" in report
    # Model-availability badges, always visible (not just linked):
    assert "model-badge-yes" in report and "model-badge-no" in report
    # The universal cross-tab/details reveal fix -- still present, minus the
    # removed model-select wiring:
    assert "function revealTarget(id)" in report
    assert "function activateTab(tabId)" in report
    assert "showModelItem" not in report
    assert "el.scrollIntoView(" in report
    assert "nav-highlight" in report
    # Dependencies tab's click-to-highlight interactivity:
    assert "selectDepNode" in report
    assert "dep-side-panel" in report


def test_agent_12_handles_missing_optional_upstream_models(tmp_path: Path):
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(json.dumps({"business_rules": []}), encoding="utf-8")
    manifest = generate(graph_file, None, tmp_path / "missing-models", tmp_path / "report")
    assert manifest["rule_count"] == 0
    assert manifest["model_info"]["DMN"]["exists"] is False


def test_condition_expression_renders_explicit_unconditional_rule():
    assert (
        _condition_expression([], {"constant": True})
        == "ALWAYS (explicitly stated in the source)"
    )


def test_agent_12_main_reports_missing_graph(tmp_path, monkeypatch):
    class Config:
        def get_optimized_dir(self): return tmp_path / "optimized"
        def get_dag_dir(self): return tmp_path / "dag"
        def get_executable_models_dir(self): return tmp_path / "models"
        def get_organized_dir(self): return tmp_path / "organized"
        def get_pipeline_base_path(self): return tmp_path

    monkeypatch.setattr("agents.agent_12_business_knowledge_report.get_config", lambda: Config())
    assert main([]) == 2
