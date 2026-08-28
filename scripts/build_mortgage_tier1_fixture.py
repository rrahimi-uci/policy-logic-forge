#!/usr/bin/env python3
"""Build the mortgage Tier 1 RegDelta fixture (plan/regdelta-product-plan.md
Section 4.1 / Phase 3) from this checkout's real, already-retained mortgage
pipeline output.

Reads:
  pipeline-output/e2e-mortgage-20260827/agent_06-optimized/optimized_compliance_knowledge_graph.json
  pipeline-output/e2e-mortgage-20260827/agent_10-dag-generation/dependency_dags.json

Writes (checked in, so the fixture is reproducible without pipeline-output/,
which is gitignored and local-only):
  fixtures/regdelta/mortgage_tier1/old_graph.json
  fixtures/regdelta/mortgage_tier1/new_graph.json
  fixtures/regdelta/mortgage_tier1/edit_manifest.json
  fixtures/regdelta/mortgage_tier1/dag_edges.json
  fixtures/regdelta/mortgage_tier1/review_status.json
  fixtures/regdelta/mortgage_tier1/scenarios.json

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
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_BATCH = ROOT / "pipeline-output" / "e2e-mortgage-20260827"
FIXTURE_DIR = ROOT / "fixtures" / "regdelta" / "mortgage_tier1"

# (rule_id, predicate_id, old_value, new_value, new_effective_date, rationale)
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


def _clean_rule_ids(rules: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(rule_id for rule_id, rule in rules.items() if not rule.get("requires_review"))


def _direct_dependents(dag_path: Path, sources: set[str]) -> tuple[set[str], list[tuple[str, str]]]:
    dags = json.loads(dag_path.read_text(encoding="utf-8"))["dags"]
    targets: set[str] = set()
    edges: list[tuple[str, str]] = []
    for dag in dags:
        for edge in dag.get("edges", []):
            source, target = edge.get("source_rule_id"), edge.get("target_rule_id")
            if source in sources:
                targets.add(target)
                edges.append((source, target))
    return targets, edges


def _apply_edit(rule: dict[str, Any], edit: Mapping[str, Any]) -> None:
    predicate = next(p for p in rule["condition_predicates"] if p["predicate_id"] == edit["predicate_id"])
    assert predicate["value"] == edit["old_value"], (rule["rule_id"], predicate["value"], edit["old_value"])
    predicate["value"] = edit["new_value"]
    rule["effective_date"] = edit["new_effective_date"]
    ref = rule.get("source_reference")
    if isinstance(ref, dict) and isinstance(ref.get("source_text"), str):
        old_text, new_text = str(edit["old_value"]), str(edit["new_value"])
        if old_text in ref["source_text"]:
            ref["source_text"] = ref["source_text"].replace(old_text, new_text)


def build(source_batch: Path, out_dir: Path) -> None:
    graph = json.loads((source_batch / "agent_06-optimized" / "optimized_compliance_knowledge_graph.json").read_text(encoding="utf-8"))
    rules = {rule["rule_id"]: rule for rule in graph["business_rules"]}
    clean_ids = _clean_rule_ids(rules)
    dependents, edges = _direct_dependents(source_batch / "agent_10-dag-generation" / "dependency_dags.json", set(clean_ids))
    universe = sorted(set(clean_ids) | dependents)
    edited_ids = {edit["rule_id"] for edit in EDITS}
    assert edited_ids <= set(clean_ids), f"edits must target clean rules; missing: {edited_ids - set(clean_ids)}"

    old_rules = [deepcopy(rules[rule_id]) for rule_id in universe]
    new_rules = deepcopy(old_rules)
    new_by_id = {rule["rule_id"]: rule for rule in new_rules}
    for edit in EDITS:
        _apply_edit(new_by_id[edit["rule_id"]], edit)

    review_status = {rule_id: bool(rules[rule_id].get("requires_review")) for rule_id in universe}
    universe_edges = [[source, target] for source, target in sorted(set(edges)) if source in set(universe) and target in set(universe)]

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "old_graph.json").write_text(json.dumps({"business_rules": old_rules}, indent=2) + "\n", encoding="utf-8")
    (out_dir / "new_graph.json").write_text(json.dumps({"business_rules": new_rules}, indent=2) + "\n", encoding="utf-8")
    (out_dir / "edit_manifest.json").write_text(json.dumps({"schema_version": "regdelta-tier1-edit-manifest/1.0", "edits": EDITS}, indent=2) + "\n", encoding="utf-8")
    (out_dir / "dag_edges.json").write_text(json.dumps({"edges": universe_edges}, indent=2) + "\n", encoding="utf-8")
    (out_dir / "review_status.json").write_text(json.dumps(review_status, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    new_dependents = dependents - set(clean_ids)
    print(f"universe: {len(universe)} rules ({len(clean_ids)} editable, {len(new_dependents)} new review-required dependents, {len(dependents) - len(new_dependents)} dependents already among the editable set)")
    print(f"edited: {sorted(edited_ids)}")
    print(f"dag edges within universe: {len(universe_edges)}")
    print(f"wrote fixture to {out_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-batch", type=Path, default=DEFAULT_SOURCE_BATCH, help="pipeline-output/<batch> directory to read agent_06/agent_10 output from")
    parser.add_argument("--out-dir", type=Path, default=FIXTURE_DIR)
    args = parser.parse_args()
    build(args.source_batch, args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
