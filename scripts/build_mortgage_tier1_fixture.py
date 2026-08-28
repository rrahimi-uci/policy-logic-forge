#!/usr/bin/env python3
"""Build the mortgage Tier 1 RegDelta fixture (plan/regdelta-product-plan.md
Section 4.1 / Phase 3) from this checkout's real, already-retained mortgage
pipeline output. See scripts/regdelta_fixture_lib.py for the shared build
logic every per-domain fixture script uses.

Reads:
  pipeline-output/e2e-mortgage-20260827/agent_06-optimized/optimized_compliance_knowledge_graph.json
  pipeline-output/e2e-mortgage-20260827/agent_10-dag-generation/dependency_dags.json

Writes (checked in, so the fixture is reproducible without pipeline-output/,
which is gitignored and local-only):
  fixtures/regdelta/mortgage_tier1/{old_graph,new_graph,edit_manifest,dag_edges,review_status}.json

The fixture universe is the 41 mortgage rules currently marked
``requires_review: false`` plus every rule that is a direct DAG dependent of
one of those 41 (24 more, all but two of which are themselves still
``requires_review: true`` -- see plan/regdelta-product-plan.md Section 3 for
why that is the norm here, not an exception). Only three of the 41 -- all
carrying a clean, isolated numeric threshold predicate -- are actually
edited; every other rule in the universe is copied byte-for-byte into both
graphs.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from regdelta_fixture_lib import build


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_BATCH = ROOT / "pipeline-output" / "e2e-mortgage-20260827"
FIXTURE_DIR = ROOT / "fixtures" / "regdelta" / "mortgage_tier1"

EDITS: list[dict[str, Any]] = [
    {
        "rule_id": "R-120-004",
        "predicate_id": "p2",
        "old_value": 80,
        "new_value": 78,
        "new_effective_date": "2026-01-01",
        "rationale": (
            "Hand-authored Tier 1 edit (not a real Fannie Mae announcement): "
            "lower the LTV trigger for required primary mortgage insurance "
            "from 80% to 78%, a 'gt' predicate weakening (more loans require PMI)."
        ),
    },
    {
        "rule_id": "batch5_mortgage_pool_fixed_rate_submission_minimum",
        "predicate_id": "p2",
        "old_value": 1000000,
        "new_value": 1250000,
        "new_effective_date": "2026-01-01",
        "rationale": (
            "Hand-authored Tier 1 edit: raise the minimum aggregate principal "
            "balance for single-lender fixed-rate MBS pool submission from "
            "$1,000,000 to $1,250,000, a 'ge' predicate strengthening (fewer pools qualify)."
        ),
    },
    {
        "rule_id": "B32-A2-2-06-001",
        "predicate_id": "p5",
        "old_value": 2.5,
        "new_value": 3.0,
        "new_effective_date": "2026-01-01",
        "rationale": (
            "Hand-authored Tier 1 edit: raise the CU risk score ceiling for "
            "appraisal enforcement relief from 2.5 to 3.0, a 'le' predicate "
            "weakening (more loans qualify for relief)."
        ),
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-batch", type=Path, default=DEFAULT_SOURCE_BATCH, help="pipeline-output/<batch> directory to read agent_06/agent_10 output from")
    parser.add_argument("--out-dir", type=Path, default=FIXTURE_DIR)
    args = parser.parse_args()
    build(args.source_batch, args.out_dir, EDITS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
