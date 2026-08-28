"""Shared logic for building a RegDelta Tier 1 fixture (plan/regdelta-product-plan.md
Section 4.1) from one domain's real, retained pipeline output: the
requires_review:false rules plus their direct agent_10 DAG dependents, with
a small set of hand-authored single-predicate edits applied to a fork.

See scripts/build_mortgage_tier1_fixture.py for the first, most-documented
use of this; per-domain scripts (e.g. build_<domain>_tier1_fixture.py) share
this module rather than duplicating it.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping


def clean_rule_ids(rules: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(rule_id for rule_id, rule in rules.items() if not rule.get("requires_review"))


def direct_dependents(dag_path: Path, sources: set[str]) -> tuple[set[str], list[tuple[str, str]]]:
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


def apply_edit(rule: dict[str, Any], edit: Mapping[str, Any]) -> None:
    predicate = next(p for p in rule["condition_predicates"] if p["predicate_id"] == edit["predicate_id"])
    assert predicate["value"] == edit["old_value"], (rule["rule_id"], predicate["value"], edit["old_value"])
    predicate["value"] = edit["new_value"]
    rule["effective_date"] = edit["new_effective_date"]
    ref = rule.get("source_reference")
    if isinstance(ref, dict) and isinstance(ref.get("source_text"), str):
        old_text, new_text = str(edit["old_value"]), str(edit["new_value"])
        if old_text in ref["source_text"]:
            ref["source_text"] = ref["source_text"].replace(old_text, new_text)


def build(source_batch: Path, out_dir: Path, edits: list[dict[str, Any]]) -> None:
    graph = json.loads((source_batch / "agent_06-optimized" / "optimized_compliance_knowledge_graph.json").read_text(encoding="utf-8"))
    rules = {rule["rule_id"]: rule for rule in graph["business_rules"]}
    clean_ids = clean_rule_ids(rules)
    dependents, edges = direct_dependents(source_batch / "agent_10-dag-generation" / "dependency_dags.json", set(clean_ids))
    universe = sorted(set(clean_ids) | dependents)
    edited_ids = {edit["rule_id"] for edit in edits}
    assert edited_ids <= set(clean_ids), f"edits must target clean rules; missing: {edited_ids - set(clean_ids)}"

    old_rules = [deepcopy(rules[rule_id]) for rule_id in universe]
    new_rules = deepcopy(old_rules)
    new_by_id = {rule["rule_id"]: rule for rule in new_rules}
    for edit in edits:
        apply_edit(new_by_id[edit["rule_id"]], edit)

    review_status = {rule_id: bool(rules[rule_id].get("requires_review")) for rule_id in universe}
    universe_edges = [[source, target] for source, target in sorted(set(edges)) if source in set(universe) and target in set(universe)]

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "old_graph.json").write_text(json.dumps({"business_rules": old_rules}, indent=2) + "\n", encoding="utf-8")
    (out_dir / "new_graph.json").write_text(json.dumps({"business_rules": new_rules}, indent=2) + "\n", encoding="utf-8")
    (out_dir / "edit_manifest.json").write_text(json.dumps({"schema_version": "regdelta-tier1-edit-manifest/1.0", "edits": edits}, indent=2) + "\n", encoding="utf-8")
    (out_dir / "dag_edges.json").write_text(json.dumps({"edges": universe_edges}, indent=2) + "\n", encoding="utf-8")
    (out_dir / "review_status.json").write_text(json.dumps(review_status, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    new_dependents = dependents - set(clean_ids)
    print(f"universe: {len(universe)} rules ({len(clean_ids)} editable, {len(new_dependents)} new review-required dependents, {len(dependents) - len(new_dependents)} dependents already among the editable set)")
    print(f"edited: {sorted(edited_ids)}")
    print(f"dag edges within universe: {len(universe_edges)}")
    print(f"wrote fixture to {out_dir}")
