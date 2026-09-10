#!/usr/bin/env python3
"""Compare two completed Policy Logic Forge optimized graphs with RegDelta."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.kg_readiness import dependency_edges
from utils.llm_client import create_llm_client
from utils.prompt_manager import get_prompt_manager
from utils.regdelta_engine import diff_graphs
from utils.semantic_rule_comparison import score_rule_pairs


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"graph must be an object: {path}")
    return value


def _load_rubric(path: Path) -> dict[str, Any]:
    value = _load(path)
    if not value:
        raise ValueError(f"semantic scoring rubric must not be empty: {path}")
    return value


def _semantic_pairs(
    old_rules: list[dict[str, Any]], new_rules: list[dict[str, Any]],
    alignments: list[dict[str, Any]], maximum: int,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Bound semantic candidates to unmatched rules of the same declared type."""
    aligned_old = {item["old_rule_ids"][0] for item in alignments if item["kind"] == "one_to_one"}
    aligned_new = {item["new_rule_ids"][0] for item in alignments if item["kind"] == "one_to_one"}
    old_unmatched = sorted((rule for rule in old_rules if rule.get("rule_id") not in aligned_old), key=lambda rule: str(rule.get("rule_id")))
    new_unmatched = sorted((rule for rule in new_rules if rule.get("rule_id") not in aligned_new), key=lambda rule: str(rule.get("rule_id")))
    pairs = [
        (old, new) for old in old_unmatched for new in new_unmatched
        if str(old.get("rule_type") or "").casefold() == str(new.get("rule_type") or "").casefold()
    ]
    return pairs[:maximum]


def _canonical_comparison_context(
    old_rules: list[dict[str, Any]], new_rules: list[dict[str, Any]], alignments: list[dict[str, Any]],
) -> tuple[list[str], dict[str, bool], list[tuple[str, str]]]:
    """Use old IDs for aligned pairs and union old/new dependency edges.

    The union is conservative: a downstream rule reachable in either document
    version is reviewed. New graph IDs are translated to their aligned old ID.
    """
    new_to_canonical = {
        item["new_rule_ids"][0]: item["old_rule_ids"][0]
        for item in alignments if item["kind"] == "one_to_one"
    }
    canonical_new = lambda rule_id: new_to_canonical.get(str(rule_id), str(rule_id))
    universe = {str(rule["rule_id"]) for rule in old_rules if rule.get("rule_id")}
    universe.update(canonical_new(rule["rule_id"]) for rule in new_rules if rule.get("rule_id") and rule.get("rule_id") not in new_to_canonical)
    review_status: dict[str, bool] = {}
    for rule in old_rules:
        if rule.get("rule_id"):
            rule_id = str(rule["rule_id"])
            review_status[rule_id] = review_status.get(rule_id, False) or bool(rule.get("requires_review"))
    for rule in new_rules:
        if rule.get("rule_id"):
            rule_id = canonical_new(rule["rule_id"])
            review_status[rule_id] = review_status.get(rule_id, False) or bool(rule.get("requires_review"))
    return sorted(universe), review_status, new_to_canonical


def _union_edges(old_graph: dict[str, Any], new_graph: dict[str, Any], new_to_canonical: dict[str, str]) -> list[tuple[str, str]]:
    translate = lambda rule_id: new_to_canonical.get(str(rule_id), str(rule_id))
    old_edges = {(str(edge["source_rule_id"]), str(edge["target_rule_id"])) for edge in dependency_edges(old_graph)}
    new_edges = {(translate(edge["source_rule_id"]), translate(edge["target_rule_id"])) for edge in dependency_edges(new_graph)}
    return sorted(old_edges | new_edges)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-graph", required=True, type=Path)
    parser.add_argument("--new-graph", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--pair-id", default="policy-comparison")
    parser.add_argument("--semantic", action="store_true", help="Add review-only LLM semantic candidates for unmatched same-type rules")
    parser.add_argument("--semantic-max-pairs", type=int, default=100, help="Maximum unmatched pairs to score when --semantic is set")
    parser.add_argument("--semantic-batch-size", type=int, default=12)
    parser.add_argument("--model", default=None, help="Optional model override for --semantic")
    parser.add_argument("--semantic-prompt-file", type=Path, help="Prompt template override for --semantic")
    parser.add_argument("--semantic-rubric-file", type=Path, help="JSON rubric that defines how --semantic scores equivalency")
    args = parser.parse_args()

    old_graph, new_graph = _load(args.old_graph), _load(args.new_graph)
    old_rules = [rule for rule in old_graph.get("business_rules", []) if isinstance(rule, dict)]
    new_rules = [rule for rule in new_graph.get("business_rules", []) if isinstance(rule, dict)]
    from utils.rule_alignment import align_rules
    alignments = align_rules(old_rules, new_rules)
    universe, review_status, new_to_canonical = _canonical_comparison_context(old_rules, new_rules, alignments)
    report = diff_graphs(
        old_graph,
        new_graph,
        universe_rule_ids=universe,
        dag_edges=_union_edges(old_graph, new_graph, new_to_canonical),
        review_status=review_status,
        pair_id=args.pair_id,
    )
    report["dependency_edge_policy"] = "union of old and new graph edges; new endpoints translated through accepted alignments"
    if args.semantic:
        if args.semantic_max_pairs < 1:
            parser.error("--semantic-max-pairs must be positive")
        pairs = _semantic_pairs(old_rules, new_rules, report["rule_alignments"], args.semantic_max_pairs)
        prompt_path = args.semantic_prompt_file
        prompt = prompt_path.read_text(encoding="utf-8") if prompt_path else get_prompt_manager().load_prompt("rule_matcher_batch")
        rubric = _load_rubric(args.semantic_rubric_file) if args.semantic_rubric_file else None
        report["semantic_candidates"] = score_rule_pairs(
            pairs,
            client=create_llm_client(model=args.model),
            prompt=prompt,
            scoring_rubric=rubric,
            batch_size=args.semantic_batch_size,
        )
        report["semantic_comparison"] = {
            "enabled": True,
            "candidate_pair_count": len(pairs),
            "candidate_limit": args.semantic_max_pairs,
            "alignment_effect": "none; all candidates require review",
            "prompt_source": str(prompt_path) if prompt_path else "prompts/rule_matcher_batch.txt",
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "scoring_rubric": rubric,
            "scoring_rubric_sha256": (
                hashlib.sha256(json.dumps(rubric, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
                if rubric is not None else None
            ),
        }
    else:
        report["semantic_candidates"] = []
        report["semantic_comparison"] = {"enabled": False, "alignment_effect": "none"}
    report["semantic_contradictions"] = [
        candidate for candidate in report["semantic_candidates"]
        if candidate["relationship"] == "CONTRADICTORY"
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}: {len(report['rule_alignments'])} alignments, {report['metrics']['direct_count']} direct changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())