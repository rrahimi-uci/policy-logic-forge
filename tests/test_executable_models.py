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


def test_graph_dmn_is_valid_and_unsupported_predicates_fail_closed():
    graph = _graph()
    document = build_graph_dmn(graph)
    root = ET.fromstring(document)
    decisions = list(root.iter(f"{{{DMN_NS}}}decision"))
    assert len(decisions) == 2
    assert decisions[1].get(f"{{{CTC_NS}}}requiresReview") == "true"
    rows = list(root.iter(f"{{{DMN_NS}}}rule"))
    assert rows[1].find(f"{{{DMN_NS}}}inputEntry/{{{DMN_NS}}}text").text == "false"


def test_bpmn_expands_cycle_groups_and_covers_every_rule():
    graph = _graph()
    dags = {"dags": [{"dag_id": "d1", "rule_ids": ["R-1", "R-2"],
                      "topological_order": ["d1_cycle_1"],
                      "cycle_groups": [{"group_id": "d1_cycle_1", "rule_ids": ["R-1", "R-2"]}]}]}
    dmn = build_graph_dmn(graph)
    bpmn = build_dags_bpmn(graph, dags)
    assert validate_executable_models(dmn, bpmn, ["R-1", "R-2"]) == []
    assert len(list(ET.fromstring(bpmn).iter(f"{{{BPMN_NS}}}businessRuleTask"))) == 2


def test_validation_rejects_missing_rule_coverage():
    graph = _graph()
    assert validate_executable_models(build_graph_dmn(graph), build_dags_bpmn(graph, {"dags": []}), ["R-1", "R-2"])
