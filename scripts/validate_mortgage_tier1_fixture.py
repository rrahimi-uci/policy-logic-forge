#!/usr/bin/env python3
"""Validate the checked-in mortgage Tier 1 fixture's internal consistency
(plan/regdelta-product-plan.md Phase 3, execution step 3).

Checks, independent of whether the fixture actually compiles or reproduces
the hand-labeled scenarios (see tests/test_mortgage_tier1_fixture.py for
that):

- every edited rule ID is one of the 41 rules marked ``requires_review:
  false`` in ``review_status.json``;
- every rule *not* edited is byte-for-byte identical between ``old_graph.json``
  and ``new_graph.json`` (the fixture cannot silently drift, and cannot
  silently un-flag a rule that is supposed to stay ``requires_review: true``);
- every rule ID referenced by a DAG edge or a scenario target exists
  somewhere in the fixture universe.

Exits non-zero and prints every violation found (not just the first) on
failure, so a single run surfaces the whole problem.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE_DIR = ROOT / "fixtures" / "regdelta" / "mortgage_tier1"


def _load(fixture_dir: Path) -> dict[str, Any]:
    return {
        "old": json.loads((fixture_dir / "old_graph.json").read_text(encoding="utf-8")),
        "new": json.loads((fixture_dir / "new_graph.json").read_text(encoding="utf-8")),
        "edit_manifest": json.loads((fixture_dir / "edit_manifest.json").read_text(encoding="utf-8")),
        "dag_edges": json.loads((fixture_dir / "dag_edges.json").read_text(encoding="utf-8")),
        "review_status": json.loads((fixture_dir / "review_status.json").read_text(encoding="utf-8")),
        "scenarios": json.loads((fixture_dir / "scenarios.json").read_text(encoding="utf-8")),
    }


def validate(fixture_dir: Path = DEFAULT_FIXTURE_DIR) -> list[str]:
    data = _load(fixture_dir)
    errors: list[str] = []

    old_by_id = {rule["rule_id"]: rule for rule in data["old"]["business_rules"]}
    new_by_id = {rule["rule_id"]: rule for rule in data["new"]["business_rules"]}
    review_status = data["review_status"]
    edited_ids = {edit["rule_id"] for edit in data["edit_manifest"]["edits"]}

    if set(old_by_id) != set(new_by_id):
        errors.append(f"old/new graph rule-ID sets differ: {set(old_by_id) ^ set(new_by_id)}")
    if set(old_by_id) != set(review_status):
        errors.append(f"review_status.json does not cover exactly the fixture universe: {set(old_by_id) ^ set(review_status)}")

    for rule_id in edited_ids:
        if review_status.get(rule_id) is not False:
            errors.append(f"edited rule {rule_id!r} is not requires_review:false in review_status.json")

    for rule_id in set(old_by_id) - edited_ids:
        if rule_id in old_by_id and rule_id in new_by_id and old_by_id[rule_id] != new_by_id[rule_id]:
            errors.append(f"un-edited rule {rule_id!r} differs between old_graph.json and new_graph.json")

    universe = set(old_by_id)
    for source, target in data["dag_edges"]["edges"]:
        if source not in universe:
            errors.append(f"dag edge source {source!r} is outside the fixture universe")
        if target not in universe:
            errors.append(f"dag edge target {target!r} is outside the fixture universe")

    for scenario in data["scenarios"]["scenarios"]:
        for rule_id in scenario.get("targets", []):
            if rule_id not in universe:
                errors.append(f"scenario {scenario['case_id']!r} targets {rule_id!r}, which is outside the fixture universe")
        for rule_id in scenario.get("expected", {}):
            if rule_id not in universe:
                errors.append(f"scenario {scenario['case_id']!r} expects a result for {rule_id!r}, which is outside the fixture universe")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-dir", type=Path, default=DEFAULT_FIXTURE_DIR)
    args = parser.parse_args()
    errors = validate(args.fixture_dir)
    if errors:
        print(f"{len(errors)} fixture consistency violation(s):")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("mortgage Tier 1 fixture is internally consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
