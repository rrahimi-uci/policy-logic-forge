#!/usr/bin/env python3
"""Compare two completed Policy Logic Forge optimized graphs with RegDelta."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.kg_readiness import dependency_edges
from utils.regdelta_engine import diff_graphs


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"graph must be an object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-graph", required=True, type=Path)
    parser.add_argument("--new-graph", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--pair-id", default="policy-comparison")
    args = parser.parse_args()

    old_graph, new_graph = _load(args.old_graph), _load(args.new_graph)
    old_rules = [rule for rule in old_graph.get("business_rules", []) if isinstance(rule, dict)]
    new_rules = [rule for rule in new_graph.get("business_rules", []) if isinstance(rule, dict)]
    universe = sorted({str(rule.get("rule_id")) for rule in old_rules + new_rules if rule.get("rule_id")})
    review_status = {
        str(rule["rule_id"]): bool(rule.get("requires_review"))
        for rule in old_rules + new_rules if rule.get("rule_id")
    }
    report = diff_graphs(
        old_graph,
        new_graph,
        universe_rule_ids=universe,
        dag_edges=[(edge["source_rule_id"], edge["target_rule_id"]) for edge in dependency_edges(old_graph)],
        review_status=review_status,
        pair_id=args.pair_id,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}: {len(report['rule_alignments'])} alignments, {report['metrics']['direct_count']} direct changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())