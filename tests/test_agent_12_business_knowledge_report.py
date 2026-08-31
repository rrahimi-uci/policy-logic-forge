import json
import xml.etree.ElementTree as ET
from pathlib import Path

from agents.agent_12_business_knowledge_report import (
    _bpmn_flow_html,
    _cmmn_plan_html,
    _dependency_graph_layout,
    _dependency_graph_svg,
    _dmn_table_html,
    _formal_logic_html,
    _model_kind_section_html,
    _model_links_html,
    _outcome_badge_html,
    _outcome_cards_html,
    _outcome_chip_html,
    _outcome_kind,
    _parse_bpmn_processes,
    _parse_cmmn_cases,
    _parse_dmn_decisions,
    _review_route_meta,
    _route_badge_html,
    _route_card_html,
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


def test_review_route_meta_covers_every_known_semantic_routing_value():
    """utils/semantic_routing.py::classify_review_route only ever emits these
    four routes, plus agent_12's own 'unclassified' fallback -- every one
    must have a real icon/label/description, not the generic unknown-route
    fallback."""

    for route in ("none", "human_review", "machine_repair", "case_management", "unclassified"):
        icon, label, description = _review_route_meta(route)
        assert icon and label and description
        assert label != _review_route_meta("totally-unknown-route")[1]


def test_review_route_meta_falls_back_gracefully_for_an_unrecognized_route():
    icon, label, description = _review_route_meta("some_future_route")
    assert icon == "❔"
    assert label == "Some future route"  # humanized, not a raw enum dump
    assert description


def test_route_badge_preserves_lowercase_route_text_for_filter_compatibility():
    """The compact toolbar filter/data-route attribute rely on the raw,
    lowercase, underscore-free route text still being present verbatim."""

    html = _route_badge_html("case_management")
    assert "case management" in html  # raw text preserved
    assert "Case management" in html  # human label added
    assert 'class="status status-case_management route-badge"' in html


def test_route_card_shows_icon_label_description_and_hold_state():
    html = _route_card_html("human_review", has_hold=True, reason_items=["Evidence contradicted the source"])
    assert 'class="route-card route-human_review"' in html
    assert "Human review" in html
    assert "judgment call" in html  # the plain-language description
    assert '<span class="route-hold route-hold-yes">Quality hold</span>' in html
    assert "Evidence contradicted the source" in html
    assert "Why (1)" in html


def test_route_card_shows_no_hold_state_and_default_reason_for_a_clean_route():
    html = _route_card_html("none", has_hold=False, reason_items=[])
    assert '<span class="route-hold route-hold-no">No quality hold</span>' in html
    assert "No review reason recorded." in html
    assert "Why (0)" in html


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


def test_model_kind_section_html_builds_select_and_hides_all_but_first_item():
    items = [{"rule_id": "R-1", "name": "First"}, {"rule_id": "R-2", "name": "Second"}]
    html = _model_kind_section_html("DMN", items, lambda item: f'<div class="stub">{item["rule_id"]}</div>')
    assert 'id="model-dmn-select"' in html
    assert html.count("<option") == 2
    assert 'id="model-dmn-item-R-1" data-rule-id="R-1">' in html  # first item visible
    assert 'id="model-dmn-item-R-2" data-rule-id="R-2" hidden>' in html  # rest start hidden
    assert 'data-items="model-dmn-items"' in html
    assert 'data-select="model-dmn-select"' in html


def test_model_kind_section_html_empty_state_has_no_select():
    html = _model_kind_section_html("BPMN", [], lambda item: "")
    assert "No applicable elements were generated." in html
    assert "<select" not in html


def test_model_links_html_only_links_kinds_with_an_item_for_this_rule():
    model_rule_ids = {"DMN": {"R-1", "R-2"}, "BPMN": {"R-1"}, "CMMN": set()}
    html = _model_links_html("R-1", model_rule_ids)
    assert "DMN" in html and "BPMN" in html and "CMMN" not in html
    assert 'href="#model-dmn-item-R-1"' in html
    assert 'href="#model-bpmn-item-R-1"' in html


def test_model_links_html_empty_when_rule_has_no_models():
    assert _model_links_html("R-9", {"DMN": {"R-1"}, "BPMN": set(), "CMMN": set()}) == ""


def test_agent_12_renders_real_dmn_bpmn_cmmn_diagrams_and_navigation_js(tmp_path: Path):
    """End-to-end: real generator output flows through to real diagrams, a
    working selector, rule<->model deep links, and the cross-tab/details
    navigation fix (the reported 'clicking links does nothing' bug)."""

    graph = _model_source_graph()
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(json.dumps(graph), encoding="utf-8")
    models = tmp_path / "models"
    models.mkdir()
    _write_real_models(models, graph)

    manifest = generate(graph_file, None, models, tmp_path / "report")
    report = (tmp_path / "report" / "business_knowledge_report.html").read_text(encoding="utf-8")

    assert manifest["rule_count"] == 2
    # Real structural diagrams, not the old bar-chart placeholder:
    assert 'class="dmn-table"' in report
    assert 'class="bpmn-flow"' in report
    assert 'class="cmmn-plan"' in report
    assert "DMN-backed" in report
    # Select-one-to-inspect controls, one per kind, each with pre-rendered
    # (hidden-until-selected) diagram blocks:
    assert 'id="model-dmn-select"' in report
    assert 'id="model-bpmn-select"' in report
    assert 'id="model-cmmn-select"' in report
    assert 'class="model-diagram-item"' in report
    # Rule row -> model deep links (only for kinds each rule actually has):
    assert 'href="#model-dmn-item-R-1"' in report
    assert 'href="#model-bpmn-item-R-1"' in report
    assert 'href="#model-cmmn-item-R-2"' in report
    # The universal cross-tab/details reveal fix:
    assert "function revealTarget(id)" in report
    assert "function activateTab(tabId)" in report
    assert "function showModelItem(groupEl,ruleId)" in report
    assert "el.scrollIntoView(" in report
    assert "nav-highlight" in report


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
