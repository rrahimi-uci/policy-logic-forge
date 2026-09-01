"""Quality-budget and non-mutating claim-admission contracts."""

from __future__ import annotations

import pytest

from utils.claim_admission import TARGETS, classify_claim
from utils.quality_budget import QualityBudgetError, summarize_quality_budget


def _report() -> dict:
    return {
        "total_rules": 10,
        "rules_certified": 6,
        "rules_failed": 4,
        "rules_requiring_review": 5,
        "human_review_required_rules": 2,
        "total_claims": 20,
        "supported_claims": 15,
        "contradicted_claims": 2,
        "insufficient_evidence_claims": 3,
        "failures": [
            {"rule_id": "r1", "claims": [{"claim_type": "party", "verdict": "insufficient_evidence"}]},
            {"rule_id": "r2", "claims": [{"claim_type": "scope", "verdict": "insufficient_evidence"}]},
            {"rule_id": "r3", "claims": [{"claim_type": "description", "verdict": "contradicted"}]},
            {"rule_id": "r4", "claims": [
                {"claim_type": "condition", "verdict": "contradicted"},
                {"claim_type": "outcome", "verdict": "insufficient_evidence"},
            ]},
        ],
        "relationship_verification": {
            "total_relationships": 3,
            "failures": [{"affected_rule_ids": ["r2", "r5"]}],
        },
    }


def test_quality_budget_uses_floor_so_display_rounding_cannot_create_a_false_pass():
    report = _report()
    report.update({
        "total_rules": 628, "rules_certified": 111, "rules_failed": 517,
        "rules_requiring_review": 522, "human_review_required_rules": 82,
    })
    report["failures"] = [
        {"rule_id": f"r{index}", "claims": [{"claim_type": "party", "verdict": "insufficient_evidence"}]}
        for index in range(517)
    ]

    summary = summarize_quality_budget(report, target_rate_percent=10)

    assert summary["target"] == {
        "rate_percent": 10.0,
        "maximum_held_rules": 62,
        "passes_target": False,
        "quality_holds_to_clear": 460,
        "failed_rules_to_resolve": 455,
        "human_reviews_to_resolve": 20,
    }


def test_quality_budget_reports_claim_and_relationship_cohorts():
    summary = summarize_quality_budget(_report(), target_rate_percent=10)

    assert summary["failed_rule_claims"]["total"] == 5
    assert summary["failed_rule_claims"]["affected_rules"] == 4
    assert summary["failure_families"] == {
        "claim_verdict_failure_rules": 4,
        "evidence_authenticity_failure_rules": 0,
        "other_claim_free_failure_rules": 0,
        "all_failed_rules_reconciled": True,
    }
    assert summary["cohorts"] == {
        "only_party_or_scope": 2,
        "only_current_enrichment": 2,
        "has_current_core": 2,
        "has_decision_material_failure": 2,
        "only_description_or_party": 2,
        "only_party": 1,
    }
    assert summary["relationships"] == {
        "total_relationships": 3,
        "failed_relationships": 1,
        "affected_rules": 2,
        "overlap_with_failed_rules": 1,
        "overlap_with_claim_failure_rules": 1,
    }


def test_quality_budget_rejects_changed_or_inconsistent_denominators():
    report = _report()
    report["rules_failed"] = 3
    with pytest.raises(QualityBudgetError, match="must equal total_rules"):
        summarize_quality_budget(report)


def test_frozen_mortgage_baseline_preserves_the_original_denominator_and_budget():
    import json
    from pathlib import Path

    baseline_path = Path(__file__).parents[1] / "quality-baselines" / "mortgage-20260830.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    assert baseline["counts"]["total_rules"] == 628
    assert baseline["counts"]["rules_requiring_review"] == 522
    assert baseline["target_10_percent"] == {
        "maximum_held_rules": 62,
        "quality_holds_to_clear": 460,
    }
    assert sum(baseline["failure_families"].values()) == baseline["counts"]["rules_failed"]


def test_quality_budget_reconciles_claim_free_evidence_authenticity_failures():
    report = _report()
    report.update({"rules_certified": 5, "rules_failed": 5})
    report["failures"].append({
        "rule_id": "r5",
        "claims": [],
        "reason": (
            "0 contradicted and 0 insufficient claims; "
            "1 evidence quotes not found in the cited corpus; "
            "0 missing and 0 duplicate verifier responses"
        ),
    })

    summary = summarize_quality_budget(report)

    assert summary["failure_families"] == {
        "claim_verdict_failure_rules": 4,
        "evidence_authenticity_failure_rules": 1,
        "other_claim_free_failure_rules": 0,
        "all_failed_rules_reconciled": True,
    }


def test_quality_budget_reports_other_claim_free_failures_as_operational():
    report = _report()
    report["failures"][-1] = {"rule_id": "r4", "claims": [], "reason": "unknown"}

    summary = summarize_quality_budget(report)

    assert summary["failure_families"] == {
        "claim_verdict_failure_rules": 3,
        "evidence_authenticity_failure_rules": 0,
        "other_claim_free_failure_rules": 1,
        "all_failed_rules_reconciled": True,
    }


@pytest.mark.parametrize(
    "claim,origin,required_for,quarantine_allowed",
    [
        ({"field_path": "description", "claim_type": "description"}, "presentation", (), True),
        ({"field_path": "counterparties[0]", "claim_type": "party"}, "source_bearing", ("bpmn", "cmmn"), False),
        ({"field_path": "condition_predicates[0]", "claim_type": "condition"}, "source_bearing", ("dmn", "lexec"), False),
        ({"field_path": "exceptions[0]", "claim_type": "exception"}, "source_bearing", ("dmn", "lexec"), False),
        ({"field_path": "responsible_party", "claim_type": "party"}, "source_bearing", ("bpmn", "cmmn"), False),
        ({"field_path": "condition_logic", "claim_type": "condition_logic"}, "derived", ("dmn", "lexec"), False),
    ],
)
def test_claim_requiredness_is_target_specific_and_conservative(
    claim, origin, required_for, quarantine_allowed
):
    requirement = classify_claim(claim)
    assert requirement.origin == origin
    assert requirement.required_for == required_for
    assert requirement.quarantine_allowed is quarantine_allowed


def test_unknown_claims_fail_closed_for_every_target():
    requirement = classify_claim({"field_path": "future_field", "claim_type": "future_claim"})
    assert requirement.required_for == TARGETS
    assert requirement.quarantine_allowed is False


def test_missing_claim_identity_also_fails_closed():
    requirement = classify_claim({})
    assert requirement.required_for == TARGETS
    assert requirement.origin == "unknown"
