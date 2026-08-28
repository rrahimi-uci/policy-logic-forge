#!/usr/bin/env python3
"""Compare a real Tier 2 extraction against Tier 1's hand-authored edits
(plan/regdelta-product-plan.md Section 4.2 / Phase 4).

Tier 1 hand-edits a fork of the real mortgage graph; Tier 2 independently
re-extracts a short hand-authored "errata" excerpt reflecting the same
edits in natural prose, through the real agents 01-06. Alignment cannot be
by rule ID here -- the real extraction assigns its own IDs and its own
variable names (this is exactly the alignment problem Tier 2 exists to
demonstrate; see utils.rule_alignment's module docstring) -- so this script
aligns by the regulatory citation code embedded in each side's
``source_reference.section_id`` (e.g. "B7-1-01"), which survives even
though the surrounding text is independently paraphrased on each side.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
_CITATION = re.compile(r"\b([A-Z][0-9]+(?:-[0-9]+)*(?:\.[0-9]+)*-?[0-9]*)\b")


def citation_code(section_id: str | None) -> str | None:
    """Extract a regulatory citation code (e.g. "B7-1-01") from a section_id
    string, regardless of which side's paraphrasing surrounds it."""
    if not section_id:
        return None
    match = _CITATION.search(section_id)
    return match.group(1) if match else None


def _rules_by_citation(graph: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_citation: dict[str, list[dict[str, Any]]] = {}
    for rule in graph.get("business_rules", []):
        code = citation_code((rule.get("source_reference") or {}).get("section_id"))
        if code:
            by_citation.setdefault(code, []).append(rule)
    return by_citation


def _value_present(rules: list[dict[str, Any]], expected_value: Any) -> bool:
    for rule in rules:
        for predicate in rule.get("condition_predicates", []) or []:
            if predicate.get("value") == expected_value:
                return True
        for outcome in rule.get("outcomes", []) or []:
            if outcome.get("value") == expected_value:
                return True
    return False


def compare(tier1_dir: Path, tier2_graph_path: Path) -> dict[str, Any]:
    old_graph = json.loads((tier1_dir / "old_graph.json").read_text(encoding="utf-8"))
    edit_manifest = json.loads((tier1_dir / "edit_manifest.json").read_text(encoding="utf-8"))["edits"]
    old_by_id = {rule["rule_id"]: rule for rule in old_graph["business_rules"]}
    tier2_graph = json.loads(tier2_graph_path.read_text(encoding="utf-8"))
    tier2_by_citation = _rules_by_citation(tier2_graph)

    results = []
    for edit in edit_manifest:
        old_rule = old_by_id[edit["rule_id"]]
        code = citation_code(old_rule["source_reference"]["section_id"])
        tier2_rules = tier2_by_citation.get(code, [])
        recovered = _value_present(tier2_rules, edit["new_value"])
        results.append({
            "tier1_rule_id": edit["rule_id"],
            "citation_code": code,
            "old_value": edit["old_value"],
            "new_value": edit["new_value"],
            "tier2_rules_at_citation": [r["rule_id"] for r in tier2_rules],
            "recovered": recovered,
        })

    return {
        "schema_version": "regdelta-tier2-comparison/1.0",
        "edits_checked": len(results),
        "edits_recovered": sum(1 for r in results if r["recovered"]),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier1-dir", type=Path, default=ROOT / "fixtures" / "regdelta" / "mortgage_tier1")
    parser.add_argument("--tier2-graph", type=Path, default=ROOT / "fixtures" / "regdelta" / "mortgage_tier2_extraction" / "optimized_compliance_knowledge_graph.json")
    parser.add_argument("--out", type=Path, default=None, help="Write the comparison report as JSON to this path")
    args = parser.parse_args()
    report = compare(args.tier1_dir, args.tier2_graph)
    print(json.dumps(report, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["edits_recovered"] == report["edits_checked"] else 1


if __name__ == "__main__":
    sys.exit(main())
