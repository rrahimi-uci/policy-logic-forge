import xml.etree.ElementTree as ET

from utils.kg_readiness import final_rule_issues, mark_readiness
from utils.semantic_artifacts import CMMN_NS, build_review_cmmn, build_sbvr_profile, validate_review_cmmn
from utils.semantic_routing import bpmn_eligibility, classify_review_route


def workflow_rule():
    return {
        "rule_id": "R-1",
        "rule_name": "Explicit process",
        "responsible_party": "SERVICER",
        "requires_review": False,
        "grounding": {"status": "certified"},
        "workflow_semantics": {
            "kind": "prescriptive_process",
            "basis": "explicit_in_source",
            "trigger_event": "Request received",
            "actor_role": "SERVICER",
            "ordered_steps": [
                {"step_id": "s1", "name": "Review request", "kind": "user_task"},
                {"step_id": "s2", "name": "Send decision", "kind": "send_task"},
            ],
            "evidence": [{
                "chunk_path": "policy.txt", "section_id": "s1",
                "source_text": "After receiving a request, review it and send the decision.",
            }],
        },
    }


def test_bpmn_requires_explicit_order_and_certified_rule():
    rule = workflow_rule()
    assert bpmn_eligibility(rule) == (True, [])
    rule["workflow_semantics"].pop("evidence")
    assert bpmn_eligibility(rule)[0] is False
    rule = workflow_rule()
    rule["requires_review"] = True
    assert "rule requires review" in bpmn_eligibility(rule)[1]


def test_review_route_keeps_fail_closed_status_but_reserves_human_queue_for_judgment():
    machine = mark_readiness({}, [{"requirement": "contract", "reason": "missing generated field"}])
    case = mark_readiness({}, [{"requirement": "exceptions", "reason": "source search is incomplete", "evidence_limited": True}])
    human = mark_readiness({}, [{"requirement": "grounding", "reason": "source conflict contradicted the rule"}])

    assert machine["requires_review"] is True and machine["review_route"]["route"] == "machine_repair"
    assert case["requires_review"] is True and case["review_route"]["route"] == "case_management"
    assert human["review_route"]["route"] == "human_review"
    assert classify_review_route([])["route"] == "none"


def test_zero_grounding_contradictions_stay_in_case_management():
    """A zero count in Agent 09's summary must not trigger human review."""
    case = mark_readiness({}, [{
        "requirement": "grounding",
        "reason": "0 contradicted and 3 insufficient claims; 0 evidence quotes not found",
    }])
    assert case["requires_review"] is True
    assert case["review_route"] == {
        "route": "case_management",
        "human_review_required": False,
        "reasons": ["0 contradicted and 3 insufficient claims; 0 evidence quotes not found"],
    }


def test_positive_grounding_contradiction_enters_human_review():
    human = mark_readiness({}, [{
        "requirement": "grounding",
        "reason": "2 contradicted and 1 insufficient claims",
    }])
    assert human["review_route"]["route"] == "human_review"
    assert human["review_route"]["human_review_required"] is True


def test_complete_negative_exception_search_is_ready_without_claiming_source_said_none():
    rule = {
        "applicability_scope": {"loan_types": [], "occupancy_types": [], "transaction_types": []},
        "scope_basis": "genuinely_unscoped",
        "scope_derivation": {"reviewed_chunk_count": 3},
        "exception_basis": "no_exception_cue_found_in_complete_search",
        "exception_verification": {"searched_chunk_count": 3, "corpus_sha256": "abc"},
        "execution": {"targets": ["DMN"], "dmn": {}},
    }
    issues = final_rule_issues(rule, set())
    assert not any(issue["requirement"] == "exceptions" for issue in issues)


def test_sbvr_profile_preserves_explicit_types_and_flags_untyped_concepts():
    profile = build_sbvr_profile({
        "entity_types": {
            "SERVICER": {"definition": "A servicing organization.", "concept_kind": "actor_role"},
            "LOAN": {"definition": "A governed loan."},
        },
        "relationships": {
            "SERVICES": {"source_entity": "SERVICER", "target_entity": "LOAN", "grounding": {"status": "supported"}},
        },
    })
    assert profile["conformance"] == "pipeline_profile_not_full_sbvr_exchange"
    assert profile["unresolved_concept_ids"] == ["LOAN"]
    assert profile["fact_types"][0]["grounding_status"] == "supported"


def test_cmmn_contains_only_case_and_human_routes():
    graph = {"business_rules": [
        {"rule_id": "machine", "review_route": {"route": "machine_repair"}},
        {"rule_id": "case", "review_route": {"route": "case_management"}},
        {"rule_id": "human", "review_route": {"route": "human_review"}},
    ]}
    document = build_review_cmmn(graph)
    assert validate_review_cmmn(document, {"case", "human"}) == []
    assert len(list(ET.fromstring(document).iter(f"{{{CMMN_NS}}}case"))) == 2
