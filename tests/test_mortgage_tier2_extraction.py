"""Phase 4 acceptance test (plan/regdelta-product-plan.md): confirm the real
agents 01-06 extraction over a hand-authored errata excerpt independently
recovers the same field-level values Tier 1 hand-edited.

Uses the checked-in, retained extraction output in
fixtures/regdelta/mortgage_tier2_extraction/ (see that directory's README
for how it was produced and how to regenerate it) rather than
pipeline-output/, which is gitignored and local-only.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.compare_tier2_extraction import citation_code, compare


ROOT = Path(__file__).resolve().parents[1]
TIER1_DIR = ROOT / "fixtures" / "regdelta" / "mortgage_tier1"
TIER2_GRAPH = ROOT / "fixtures" / "regdelta" / "mortgage_tier2_extraction" / "optimized_compliance_knowledge_graph.json"


def test_citation_code_survives_independent_paraphrasing():
    # Tier 1's own citation string vs. the real extraction's independently
    # paraphrased section_id for the same provision.
    assert citation_code("B7-1-01, Provision of Mortgage Insurance (04/02/2025)") == "B7-1-01"
    assert citation_code("Mortgage Insurance Requirement for High-LTV Conventional First Mortgages (B7-1-01; 04/02/2025)") == "B7-1-01"
    assert citation_code(None) is None
    assert citation_code("no citation code here") is None


def test_all_three_tier1_edits_are_recovered_by_the_real_extraction():
    report = compare(TIER1_DIR, TIER2_GRAPH)
    assert report["edits_checked"] == 3
    assert report["edits_recovered"] == 3
    for result in report["results"]:
        assert result["recovered"], result
        assert result["tier2_rules_at_citation"], f"no real rule found at {result['citation_code']}"


def test_tier2_rules_use_independent_ids_and_variable_names():
    # The real extraction assigning its own IDs/variable names is exactly
    # why Tier 2 exists (see utils.rule_alignment's module docstring) --
    # confirm the checked-in fixture actually demonstrates that, rather
    # than accidentally matching Tier 1 by ID.
    tier1_ids = {rule["rule_id"] for rule in json.loads((TIER1_DIR / "old_graph.json").read_text())["business_rules"]}
    tier2_ids = {rule["rule_id"] for rule in json.loads(TIER2_GRAPH.read_text())["business_rules"]}
    assert tier1_ids.isdisjoint(tier2_ids)
