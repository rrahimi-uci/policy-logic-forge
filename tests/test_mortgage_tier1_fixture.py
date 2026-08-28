"""Phase 3 acceptance test: run the real compiler/alignment/diff/propagation
engine over the checked-in mortgage Tier 1 fixture and check 100% agreement
with the hand-labeled scenarios (plan/regdelta-product-plan.md Section 4.1
and Phase 3).

The fixture itself -- old_graph.json/new_graph.json/edit_manifest.json/
dag_edges.json/review_status.json/scenarios.json -- is real data: a 65-rule
subset of the actual e2e-mortgage-20260827 pipeline run, forked with three
hand-authored edits by scripts/build_mortgage_tier1_fixture.py. See that
script and plan/regdelta-product-plan.md Section 3 for the real R-120-004/
R-120-003 provenance behind this fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_mortgage_tier1_fixture import validate
from utils.regdelta_engine import diff_graphs


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "fixtures" / "regdelta" / "mortgage_tier1"


def _load_fixture() -> dict:
    return {
        "old_graph": json.loads((FIXTURE_DIR / "old_graph.json").read_text(encoding="utf-8")),
        "new_graph": json.loads((FIXTURE_DIR / "new_graph.json").read_text(encoding="utf-8")),
        "edit_manifest": json.loads((FIXTURE_DIR / "edit_manifest.json").read_text(encoding="utf-8")),
        "dag_edges": json.loads((FIXTURE_DIR / "dag_edges.json").read_text(encoding="utf-8")),
        "review_status": json.loads((FIXTURE_DIR / "review_status.json").read_text(encoding="utf-8")),
        "scenarios": json.loads((FIXTURE_DIR / "scenarios.json").read_text(encoding="utf-8")),
    }


@pytest.fixture(scope="module")
def fixture_data() -> dict:
    return _load_fixture()


@pytest.fixture(scope="module")
def report(fixture_data: dict) -> dict:
    data = fixture_data
    universe = sorted(data["review_status"])
    dag_edges = [tuple(edge) for edge in data["dag_edges"]["edges"]]
    scenarios = [
        {"case_id": s["case_id"], "inputs": s["inputs"], "targets": s["targets"]}
        for s in data["scenarios"]["scenarios"]
    ]
    return diff_graphs(
        data["old_graph"], data["new_graph"],
        universe_rule_ids=universe, dag_edges=dag_edges, review_status=data["review_status"],
        scenarios=scenarios, pair_id="mortgage-tier1",
    )


def test_fixture_is_internally_consistent():
    assert validate(FIXTURE_DIR) == []


def test_universe_size_and_edited_rule_count(fixture_data: dict):
    assert len(fixture_data["review_status"]) == 65
    assert sum(1 for v in fixture_data["review_status"].values() if not v) == 41
    assert sum(1 for v in fixture_data["review_status"].values() if v) == 24
    assert len(fixture_data["edit_manifest"]["edits"]) == 3


def test_edited_rules_are_directly_changed(report: dict):
    direct = set(report["downstream_impacts"]["direct"])
    assert direct == {"R-120-004", "batch5_mortgage_pool_fixed_rate_submission_minimum"}
    # B32-A2-2-06-001 was edited too, but fails to compile on both sides (a
    # real cross-rule enum-domain conflict on "property_type" -- see
    # scripts/build_mortgage_tier1_fixture.py), so it can never be "direct".


def test_b32_is_reported_refused_not_silently_changed_or_dropped(report: dict):
    status = report["downstream_impacts"]["statuses"]["B32-A2-2-06-001"]
    assert status["status"] == "refused-unsupported-construct"


def test_known_downstream_dependents_are_reached_and_unresolved_review(report: dict):
    potential = set(report["downstream_impacts"]["potential"])
    assert {"R-120-004", "R-120-003", "batch5_mortgage_pool_fixed_rate_submission_minimum", "B8-MBS-LOAN-001", "B8-MBS-LOAN-002"} <= potential
    statuses = report["downstream_impacts"]["statuses"]
    for rule_id in ("R-120-003", "B8-MBS-LOAN-001", "B8-MBS-LOAN-002"):
        assert statuses[rule_id]["status"] == "unresolved-review", rule_id


def test_recompute_is_empty_for_this_fixture(report: dict):
    # Every downstream dependent reached from an edit in this fixture is
    # itself requires_review -- see plan/regdelta-product-plan.md Section 6.5
    # for why that makes Recompute trivially empty here (there is nothing to
    # safely re-execute; everything reachable is either Direct or
    # unresolved-review).
    assert report["downstream_impacts"]["recompute"] == []


def test_every_hand_labeled_scenario_matches_exactly(fixture_data: dict, report: dict):
    cases_by_id = {case["case_id"]: case for case in report["affected_cases"]}
    mismatches: list[str] = []
    for scenario in fixture_data["scenarios"]["scenarios"]:
        case_id = scenario["case_id"]
        actual_case = cases_by_id[case_id]
        for rule_id, expected in scenario["expected"].items():
            if "differs" in expected:
                actual = actual_case["rule_results"].get(rule_id)
                if actual is None:
                    mismatches.append(f"{case_id}/{rule_id}: rule did not compile on both sides (no rule_result at all)")
                    continue
                if actual["old"]["status"] != expected["old_status"]:
                    mismatches.append(f"{case_id}/{rule_id}: old status {actual['old']['status']!r} != expected {expected['old_status']!r}")
                if actual["new"]["status"] != expected["new_status"]:
                    mismatches.append(f"{case_id}/{rule_id}: new status {actual['new']['status']!r} != expected {expected['new_status']!r}")
                if actual["differs"] != expected["differs"]:
                    mismatches.append(f"{case_id}/{rule_id}: differs={actual['differs']} != expected {expected['differs']}")
            else:
                actual_status = report["downstream_impacts"]["statuses"][rule_id]["status"]
                if actual_status != expected["status"]:
                    mismatches.append(f"{case_id}/{rule_id}: status {actual_status!r} != expected {expected['status']!r}")
    assert not mismatches, "\n".join(mismatches)


def test_every_witness_corresponds_to_a_hand_labeled_differing_case(fixture_data: dict, report: dict):
    expected_differing = {
        (scenario["case_id"], rule_id)
        for scenario in fixture_data["scenarios"]["scenarios"]
        for rule_id, expected in scenario["expected"].items()
        if expected.get("differs") is True
    }
    actual_witnesses = {(w["case_id"], w["rule_id"]) for w in report["witnesses"]}
    assert actual_witnesses == expected_differing


def test_566_rules_outside_the_universe_are_never_claimed(report: dict):
    # This fixture's universe is 65 of mortgage's 631 rules; the other 566
    # are simply not part of `universe_rule_ids` here, so they have no
    # status entry at all -- Phase 7 (full-population rollout) is what
    # reports refusal for them explicitly, not this fixture.
    assert len(report["downstream_impacts"]["statuses"]) == 65
