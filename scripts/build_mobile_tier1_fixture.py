#!/usr/bin/env python3
"""Build the mobile_app_privacy Tier 1 RegDelta fixture (plan/regdelta-product-plan.md
Phase 5: expand to the remaining domains), from this checkout's real,
retained e2e-mobile-20260826 pipeline output. See
scripts/regdelta_fixture_lib.py for the shared build logic.

Unlike mortgage's fixture, neither edited rule here has a compilable
downstream DAG dependent: of the 79 mobile rules currently
requires_review:false, 11 have outgoing DAG edges, but none of the 5 with a
numeric condition_predicate do (checked directly against
pipeline-output/e2e-mobile-20260826/agent_10-dag-generation/dependency_dags.json).
This is reported honestly rather than forced -- age-gate rules in this
corpus tend to be DAG leaves, not something with an obvious "the same fact
feeds a later obligation" pattern the way mortgage's PMI/insurance-evidence
pair does. The fixture is smaller in scope (Direct/Potential coincide;
Recompute and unresolved-review are not exercised) but still real,
independently derived data with hand-labeled scenarios.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from regdelta_fixture_lib import build


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_BATCH = ROOT / "pipeline-output" / "e2e-mobile-20260826"
FIXTURE_DIR = ROOT / "fixtures" / "regdelta" / "mobile_tier1"

EDITS: list[dict[str, Any]] = [
    {
        "rule_id": "batch115-uds-minors-marketing-exclusion",
        "predicate_id": "p1",
        "old_value": 18,
        "new_value": 21,
        "new_effective_date": "2026-01-01",
        "rationale": (
            "Hand-authored Tier 1 edit: raise the marketing-plan/referral-reward "
            "age exclusion from under 18 to under 21, an 'lt' predicate weakening "
            "(more users are excluded)."
        ),
    },
    {
        "rule_id": "batch252_children_under_13_parental_consent",
        "predicate_id": "p1",
        "old_value": 13,
        "new_value": 14,
        "new_effective_date": "2026-01-01",
        "rationale": (
            "Hand-authored Tier 1 edit: raise the parental-consent age "
            "threshold for children's personal information from under 13 to "
            "under 14, an 'lt' predicate weakening (more users require consent)."
        ),
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-batch", type=Path, default=DEFAULT_SOURCE_BATCH)
    parser.add_argument("--out-dir", type=Path, default=FIXTURE_DIR)
    args = parser.parse_args()
    build(args.source_batch, args.out_dir, EDITS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
