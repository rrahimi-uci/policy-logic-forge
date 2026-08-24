#!/usr/bin/env python3
"""Run the corpus feature + expressiveness census (IR-2, neurips-plan-2027.md
§3.6) against one or more knowledge-graph JSON files and write
docs/theory_coverage.md and docs/expressiveness_census.md.

    python3 scripts/corpus_census.py pipeline-output/*/agent-5-optimized/optimized_compliance_knowledge_graph.json
    python3 scripts/corpus_census.py --check-subset boolean,number,enum <graph.json>...

No API key, no network: this is pure aggregation over already-extracted v2
rule dicts via utils/corpus_census.py. As of this commit no real pipeline
output is committed to this repo (see README.md "Data and licensing"), so
running this script against a real graph is the literal next step once one
exists -- it is not run as part of this commit.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from utils.corpus_census import census_report, coverage_at_subset, load_rules  # noqa: E402


def _markdown_table(rows: list[tuple[str, int]], headers: tuple[str, str]) -> str:
    lines = [f"| {headers[0]} | {headers[1]} |", "| --- | ---: |"]
    lines += [f"| `{name}` | {count} |" for name, count in rows]
    return "\n".join(lines)


def _theory_coverage_markdown(report: dict) -> str:
    lines = [
        "# Corpus feature census (theory coverage)",
        "",
        f"- Total rules: {report['total_rules']}",
        "",
        "## Variable type census (rules using >=1 variable of this type)",
        "",
        _markdown_table(sorted(report["variable_type_census"].items()), ("type", "rules")),
        "",
        "## Value type census (predicate/outcome value_type)",
        "",
        _markdown_table(sorted(report["value_type_census"].items()), ("value_type", "rules")),
        "",
        "## Operator census",
        "",
        _markdown_table(sorted(report["operator_census"].items()), ("operator", "rules")),
        "",
    ]
    return "\n".join(lines) + "\n"


def _expressiveness_markdown(report: dict) -> str:
    signal = report["expressiveness_signal"]
    lines = [
        "# Expressiveness census",
        "",
        "Coarse, keyword-based triage of source text needing deontic modality,",
        "temporal validity, an open-ended vague standard, or discretionary",
        "authority -- none of which a bounded decision-table semantics can",
        "express (proposal §14.6). A lower bound, not a legal classification.",
        "",
        f"- Total rules: {signal['total_rules']}",
        f"- Rules matching at least one bucket: {signal['rules_matching_any_bucket']} "
        f"({signal['fraction_matching_any_bucket']:.1%})",
        "",
        _markdown_table(sorted(signal["bucket_counts"].items()), ("bucket", "rules")),
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("graphs", nargs="+", help="Knowledge-graph JSON files to census")
    parser.add_argument("--check-subset", default=None,
                         help="Comma-separated variable types; report coverage_at_subset against them")
    parser.add_argument("--out-dir", default=str(_ROOT / "docs"), help="Where to write the two report files")
    args = parser.parse_args()

    rules = []
    for path in args.graphs:
        rules.extend(load_rules(path))

    if not rules:
        print("No rules found in the given graph(s).", flush=True)
        sys.exit(1)

    report = census_report(rules)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "theory_coverage.md").write_text(_theory_coverage_markdown(report), encoding="utf-8")
    (out_dir / "expressiveness_census.md").write_text(_expressiveness_markdown(report), encoding="utf-8")
    print(f"✓ Wrote {out_dir / 'theory_coverage.md'}", flush=True)
    print(f"✓ Wrote {out_dir / 'expressiveness_census.md'}", flush=True)

    if args.check_subset:
        subset = [t.strip() for t in args.check_subset.split(",") if t.strip()]
        coverage = coverage_at_subset(rules, subset)
        pct = coverage["coverage_fraction"] * 100
        print(
            f"\nSubset {subset}: {coverage['covered_rules']}/{coverage['total_rules']} "
            f"rules covered ({pct:.1f}%)", flush=True,
        )
        if coverage["refused_rules"]:
            print(f"  {len(coverage['refused_rules'])} rule(s) would be refused, e.g.:", flush=True)
            for entry in coverage["refused_rules"][:5]:
                print(f"    - {entry['rule_id']}: missing {entry['missing_theories']}", flush=True)


if __name__ == "__main__":
    main()
