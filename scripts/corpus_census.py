#!/usr/bin/env python3
"""Run the corpus feature + expressiveness census (IR-2, plan/neurips-plan-2027.md
§3.6) against one or more knowledge-graph JSON files and write
docs/theory_coverage.md and docs/expressiveness_census.md. Use
``--manifest-out`` with an explicit run label and scope note to retain a
metadata-only, content-addressed run record alongside the reports.

    python3 scripts/corpus_census.py pipeline-output/*/agent_06-optimized/optimized_compliance_knowledge_graph.json
    python3 scripts/corpus_census.py --check-subset boolean,number,enum <graph.json>...

No API key, no network: this is pure aggregation over already-extracted v2
rule dicts via utils/corpus_census.py. A report may be labeled as a bounded
pilot with ``--scope-note``; that label is part of the generated artifact and
prevents a pilot from being mistaken for a corpus estimate.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import platform
import re
import sys
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from utils.corpus_census import census_report, coverage_at_subset, load_rules  # noqa: E402


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repository_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    commit = completed.stdout.strip()
    return commit if completed.returncode == 0 and commit else None


def _repository_dirty() -> bool | None:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    return bool(completed.stdout.strip()) if completed.returncode == 0 else None


def _display_path(path: Path) -> str:
    """Keep manifests portable without recording a developer's absolute path."""

    try:
        display = str(path.resolve().relative_to(_ROOT))
    except ValueError:
        display = path.name
    # Pipeline output may come from an older local run whose directory names
    # predate the repository-wide agent_01..agent_10 convention.  Manifests
    # are part of the naming surface, so normalize only the label we retain;
    # the source hash remains the authoritative artifact identity.
    return re.sub(r"\bagent-(\d+)-", lambda match: f"agent_{int(match.group(1)):02d}_", display)


def _run_manifest(
    graph_paths: list[Path],
    rules: list[dict],
    report: dict,
    output_paths: list[Path],
    *,
    run_label: str,
    scope_note: str,
    subset: dict | None,
    repository_commit: str | None,
    repository_dirty: bool | None,
) -> dict:
    return {
        "schema_version": "ir2-census-run/1.0",
        "task_id": "IR-2",
        "run_id": run_label,
        "status": "exploratory",
        "scope_note": scope_note,
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "repository": {
            # Capture state before writing reports so generated output does
            # not make an otherwise clean source checkout appear dirty.
            "commit": repository_commit,
            "dirty": repository_dirty,
            "python": platform.python_version(),
        },
        "inputs": {
            "graph_count": len(graph_paths),
            "graphs": [
                {
                    "path": _display_path(path),
                    "bytes": path.stat().st_size,
                    "sha256": _sha256_file(path),
                }
                for path in graph_paths
            ],
        },
        "census": {
            "rule_count": len(rules),
            "report_sha256": hashlib.sha256(
                json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        },
        "subset": subset,
        "outputs": [
            {"path": _display_path(path), "bytes": path.stat().st_size, "sha256": _sha256_file(path)}
            for path in output_paths
        ],
    }


def _markdown_table(rows: list[tuple[str, int]], headers: tuple[str, str]) -> str:
    lines = [f"| {headers[0]} | {headers[1]} |", "| --- | ---: |"]
    lines += [f"| `{name}` | {count} |" for name, count in rows]
    return "\n".join(lines)


def _context_lines(run_label: str | None, scope_note: str | None) -> list[str]:
    lines: list[str] = []
    if run_label:
        lines.append(f"- Run: {run_label}")
    if scope_note:
        lines.append(f"- Scope: {scope_note}")
    if lines:
        lines.append("")
    return lines


def _count_table(rows: dict[str, int], headers: tuple[str, str] = ("category", "rules")) -> str:
    return _markdown_table(sorted(rows.items()), headers)


def _presence_table(presence: dict[str, dict[str, int]]) -> str:
    lines = ["| field | present | missing |", "| --- | ---: | ---: |"]
    for field, counts in sorted(presence.items()):
        lines.append(f"| `{field}` | {counts['present']} | {counts['missing']} |")
    return "\n".join(lines)


def _theory_coverage_markdown(report: dict, run_label: str | None = None, scope_note: str | None = None) -> str:
    lines = [
        "# Corpus feature census (theory coverage)",
        "",
        f"- Total rules: {report['total_rules']}",
        *_context_lines(run_label, scope_note),
        "## Rule type census",
        "",
        _count_table(report["rule_type_census"]),
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
        "## Scope, exception, and hit-policy census",
        "",
        "### Scope basis",
        "",
        _count_table(report["scope_basis_census"]),
        "",
        "### Exception basis",
        "",
        _count_table(report["exception_basis_census"]),
        "",
        "### Recommended hit policy",
        "",
        _count_table(report["hit_policy_census"]),
        "",
        "## Field presence",
        "",
        _presence_table(report["field_presence_census"]),
        "",
        "## Dependencies and decision-table projections",
        "",
        _count_table(report["dependency_census"]),
        "",
        _count_table(report["table_census"]),
        "",
        "## Contract and review signals",
        "",
        f"- Rules with contract issues: {report['contract_issue_census']['rules_with_contract_issues']}",
        f"- Rules requiring review: {report['contract_issue_census']['rules_requiring_review']}",
        f"- Invalid predicate operators: {report['contract_issue_census']['invalid_predicate_operators']}",
        f"- Invalid predicate value types: {report['contract_issue_census']['invalid_predicate_value_types']}",
        f"- Invalid outcome value types: {report['contract_issue_census']['invalid_outcome_value_types']}",
        f"- Invalid variable types: {report['contract_issue_census']['invalid_variable_types']}",
        f"- Malformed variable entries: {report['contract_issue_census']['malformed_variable_entries']}",
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _expressiveness_markdown(report: dict, run_label: str | None = None, scope_note: str | None = None) -> str:
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
        *_context_lines(run_label, scope_note),
        f"- Rules matching at least one bucket: {signal['rules_matching_any_bucket']} "
        f"({signal['fraction_matching_any_bucket']:.1%})",
        "",
        _markdown_table(sorted(signal["bucket_counts"].items()), ("bucket", "rules")),
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("graphs", nargs="+", help="Knowledge-graph JSON files to census")
    parser.add_argument("--check-subset", default=None,
                         help="Comma-separated variable types; report coverage_at_subset against them")
    parser.add_argument("--out-dir", default=str(_ROOT / "docs"), help="Where to write the two report files")
    parser.add_argument("--run-label", default=None, help="Stable label included in generated report provenance")
    parser.add_argument("--scope-note", default=None,
                         help="Explicit scope/boundary note included in generated reports")
    parser.add_argument("--manifest-out", default=None,
                        help="Write a metadata-only IR-2 run manifest at this path")
    args = parser.parse_args()

    if args.manifest_out and (not args.run_label or not args.scope_note):
        parser.error("--manifest-out requires both --run-label and --scope-note")

    graph_paths = [Path(path) for path in args.graphs]
    rules = []
    for path in graph_paths:
        rules.extend(load_rules(path))

    if not rules:
        print("No rules found in the given graph(s).", flush=True)
        sys.exit(1)

    report = census_report(rules)
    repository_commit = _repository_commit()
    repository_dirty = _repository_dirty()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    theory_path = out_dir / "theory_coverage.md"
    expressiveness_path = out_dir / "expressiveness_census.md"
    theory_path.write_text(
        _theory_coverage_markdown(report, args.run_label, args.scope_note), encoding="utf-8"
    )
    expressiveness_path.write_text(
        _expressiveness_markdown(report, args.run_label, args.scope_note), encoding="utf-8"
    )
    print(f"✓ Wrote {theory_path}", flush=True)
    print(f"✓ Wrote {expressiveness_path}", flush=True)

    subset_result = None
    if args.check_subset:
        subset = [t.strip() for t in args.check_subset.split(",") if t.strip()]
        subset_result = coverage_at_subset(rules, subset)
        pct = subset_result["coverage_fraction"] * 100
        print(
            f"\nSubset {subset}: {subset_result['covered_rules']}/{subset_result['total_rules']} "
            f"rules covered ({pct:.1f}%)", flush=True,
        )
        if subset_result["refused_rules"]:
            print(f"  {len(subset_result['refused_rules'])} rule(s) would be refused, e.g.:", flush=True)
            for entry in subset_result["refused_rules"][:5]:
                print(f"    - {entry['rule_id']}: missing {entry['missing_theories']}", flush=True)

    if args.manifest_out:
        manifest_path = Path(args.manifest_out)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        output_paths = [theory_path, expressiveness_path]
        manifest = _run_manifest(
            graph_paths,
            rules,
            report,
            output_paths,
            run_label=args.run_label,
            scope_note=args.scope_note,
            subset=subset_result,
            repository_commit=repository_commit,
            repository_dirty=repository_dirty,
        )
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"✓ Wrote {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
