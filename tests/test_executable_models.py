import xml.etree.ElementTree as ET

from utils.executable_models import (
    BPMN_NS, CTC_NS, DMN_NS, build_dags_bpmn, build_graph_dmn,
    validate_executable_models,
)


def _graph():
    return {"business_rules": [
        {"rule_id": "R-1", "rule_name": "Allow", "requires_review": False,
         "grounding": {"status": "certified"},
         "condition_predicates": [{"variable": "active", "operator": "==", "value": True}],
         "variables": [{"name": "active", "type": "boolean", "role": "input"}],
         "outcomes": [{"variable": "decision", "value": "allow"}],
         "execution": {"dmn": {"hit_policy": "UNIQUE"}},
         "source_reference": {"chunk_path": "policy.txt", "section_id": "s1"}},
        {"rule_id": "R-2", "requires_review": True, "grounding": {"status": "failed"},
         "condition_predicates": [{"variable": "x", "operator": "unknown", "value": 1}],
         "variables": [{"name": "x", "type": "number", "role": "input"}],
         "outcomes": [{"variable": "decision", "value": "hold"}],
         "source_reference": {"chunk_path": "policy.txt", "section_id": "s2"}},
    ]}


def _explicit_workflow():
    return {
        "kind": "prescriptive_process",
        "basis": "explicit_in_source",
        "trigger_event": "Application received",
        "actor_role": "SELLER_SERVICER",
        "ordered_steps": [
            {"step_id": "review", "name": "Review application", "kind": "user_task"},
            {"step_id": "decide", "name": "Apply eligibility decision", "kind": "business_rule_task"},
        ],
        "evidence": [{"chunk_path": "policy.txt", "section_id": "s1", "source_text": "After receipt, review the application and apply the eligibility decision."}],
    }


def test_graph_dmn_is_valid_and_unsupported_predicates_fail_closed():
    graph = _graph()
    document = build_graph_dmn(graph)
    root = ET.fromstring(document)
    decisions = list(root.iter(f"{{{DMN_NS}}}decision"))
    assert len(decisions) == 2
    assert decisions[1].get(f"{{{CTC_NS}}}requiresReview") == "true"
    rows = list(root.iter(f"{{{DMN_NS}}}rule"))
    assert rows[1].find(f"{{{DMN_NS}}}inputEntry/{{{DMN_NS}}}text").text == "false"


def test_bpmn_uses_only_explicit_workflow_order_and_omits_dependency_only_rules():
    graph = _graph()
    graph["business_rules"][0]["responsible_party"] = "SELLER_SERVICER"
    graph["business_rules"][0]["workflow_semantics"] = _explicit_workflow()
    dags = {"dags": [{"dag_id": "d1", "rule_ids": ["R-1", "R-2"],
                      "topological_order": ["d1_cycle_1"],
                      "cycle_groups": [{"group_id": "d1_cycle_1", "rule_ids": ["R-1", "R-2"]}]}]}
    dmn = build_graph_dmn(graph)
    bpmn = build_dags_bpmn(graph, dags)
    assert validate_executable_models(dmn, bpmn, ["R-1", "R-2"], ["R-1"]) == []
    root = ET.fromstring(bpmn)
    assert len(list(root.iter(f"{{{BPMN_NS}}}process"))) == 1
    assert len(list(root.iter(f"{{{BPMN_NS}}}userTask"))) == 1
    assert len(list(root.iter(f"{{{BPMN_NS}}}businessRuleTask"))) == 1


def test_validation_rejects_wrong_bpmn_eligibility_coverage():
    graph = _graph()
    assert validate_executable_models(
        build_graph_dmn(graph), build_dags_bpmn(graph, {"dags": []}),
        ["R-1", "R-2"], ["R-1"],
    )
