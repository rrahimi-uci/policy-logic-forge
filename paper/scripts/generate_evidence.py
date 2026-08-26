#!/usr/bin/env python3
"""Generate paper macros and a manifest from retained evidence artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected an object in {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tex_int(value: Any) -> str:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"expected a non-negative integer, got {value!r}")
    return f"{value:,}"


def _tex_status(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"expected a non-empty status, got {value!r}")
    return r"\textsc{" + value.replace("_", r"\_") + "}"


def _verify_optional_bundle(repo_root: Path, observation: dict[str, Any], sources: dict[str, Any], bundle_rel: str) -> None:
    """Verify the local non-redistributable bundle when it is available."""
    bundle = repo_root / bundle_rel
    if not bundle.is_dir():
        return
    for relative, expected in sources.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ValueError("source_artifacts must map relative paths to SHA-256 strings")
        path = bundle / relative
        if not path.is_file():
            raise ValueError(f"source artifact is missing from available bundle: {path}")
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(f"source artifact hash mismatch for {path}: {actual} != {expected}")
    coverage = _read_json(bundle / "agent_03-rules/chunk_coverage.json")
    readiness = _read_json(bundle / "agent_06-optimized/kg_readiness_report.json")
    grounding = _read_json(bundle / "agent_06-optimized/kg_grounding_report.json")
    dag_report = (bundle / "agent_10-dag-generation/dag_generation_report.md").read_text(encoding="utf-8")
    rules_match = re.search(r"Total rules:\s+(\d+)", dag_report)
    dag_match = re.search(r"DAGs generated:\s+(\d+)", dag_report)
    multi_match = re.search(r"Multi-rule[^:]*DAGs:\s+(\d+)", dag_report)
    cycle_match = re.search(r"^(\d+) DAG\(s\) contain a dependency cycle", dag_report, flags=re.MULTILINE)
    if rules_match is None or dag_match is None or multi_match is None or cycle_match is None:
        raise ValueError("DAG report does not contain the expected summary fields")
    checks = {
        "rules": int(rules_match.group(1)),
        "source_files": coverage.get("source_files_total"),
        "chunks": coverage.get("chunks_total"),
        "batches_total": coverage.get("batches_total"),
        "batches_processed": coverage.get("batches_processed"),
        "bytes_dropped": coverage.get("bytes_dropped"),
        "rules_ready": readiness.get("rules_ready"),
        "rules_review": readiness.get("rules_requiring_review"),
        "grounding_certified": grounding.get("rules_certified"),
        "grounding_failed": grounding.get("rules_failed"),
        "grounding_claim_coverage_percent": grounding.get("claim_coverage_percent"),
        "dags": int(dag_match.group(1)),
        "multi_rule_dags": int(multi_match.group(1)),
        "cycle_groups": int(cycle_match.group(1)),
    }
    for field, actual in checks.items():
        if observation.get(field) != actual:
            raise ValueError(f"observation mismatch for {field}: {observation.get(field)!r} != {actual!r}")


def generate(repo_root: Path, output_dir: Path) -> tuple[Path, Path]:
    paper_data = repo_root / "paper/data/privacy_operational_run.json"
    rule_recall = _read_json(repo_root / "results/aggregates/rule_recall.json")
    dependency = _read_json(repo_root / "results/aggregates/dependency_audit.json")
    replay = _read_json(repo_root / "results/aggregates/a1_replay.json")
    g3 = _read_json(repo_root / "results/aggregates/g3_instrument.json")
    mutation = _read_json(repo_root / "results/aggregates/lowering_mutation_score.json")
    privacy = _read_json(paper_data)
    observation = privacy.get("observation")
    if not isinstance(observation, dict):
        raise ValueError("paper observation must contain an object observation")
    sources = privacy.get("source_artifacts")
    if not isinstance(sources, dict):
        raise ValueError("paper observation must contain source_artifacts")
    bundle_rel = privacy.get("source_bundle")
    if not isinstance(bundle_rel, str) or not bundle_rel.strip():
        raise ValueError("paper observation must contain source_bundle")
    _verify_optional_bundle(repo_root, observation, sources, bundle_rel)

    macros = {
        "RuleRecallMatched": _tex_int(rule_recall["matched_rules"]),
        "RuleRecallGold": _tex_int(rule_recall["gold_rules"]),
        "RuleRecallStatus": _tex_status(rule_recall["status"]),
        "DependencyMatched": _tex_int(dependency["matched_edges"]),
        "DependencyGold": _tex_int(dependency["gold_edges"]),
        "DependencyStatus": _tex_status(dependency["status"]),
        "ReplayRows": _tex_int(replay["comparison"]["rows_compared"]),
        "ReplayExactRows": _tex_int(replay["comparison"]["exact_rows"]),
        "ReplayMismatchRows": _tex_int(replay["comparison"]["mismatch_rows"]),
        "ReplayStatus": _tex_status(replay["status"]),
        "GThreeStatus": _tex_status(g3["status"]),
        "MutationCases": _tex_int(mutation["case_count"]),
        "MutationKilled": _tex_int(mutation["mutations_killed"]),
        "MutationTotal": _tex_int(mutation["mutation_count"]),
        "PrivacyFiles": _tex_int(observation["source_files"]),
        "PrivacyChunks": _tex_int(observation["chunks"]),
        "PrivacyBatches": _tex_int(observation["batches_total"]),
        "PrivacyRules": _tex_int(observation["rules"]),
        "PrivacyReady": _tex_int(observation["rules_ready"]),
        "PrivacyReview": _tex_int(observation["rules_review"]),
        "PrivacyCertified": _tex_int(observation["grounding_certified"]),
        "PrivacyFailed": _tex_int(observation["grounding_failed"]),
        "PrivacyDags": _tex_int(observation["dags"]),
        "PrivacyMultiRuleDags": _tex_int(observation["multi_rule_dags"]),
        "PrivacyCycleGroups": _tex_int(observation["cycle_groups"]),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    macro_path = output_dir / "evidence_macros.tex"
    macro_text = "% Generated by paper/scripts/generate_evidence.py; do not edit.\n"
    macro_text += "\\newcommand{\\EvidenceStatus}{" + _tex_status(privacy["status"]) + "}\n"
    macro_text += "\\newcommand{\\EvidenceRunId}{" + str(privacy["run_id"]).replace("_", r"\_") + "}\n"
    for name, value in macros.items():
        macro_text += f"\\newcommand{{\\{name}}}{{{value}}}\n"
    macro_path.write_text(macro_text, encoding="utf-8")

    manifest = {
        "schema_version": "paper-evidence-manifest/1.0",
        "observation_file": "paper/data/privacy_operational_run.json",
        "observation_sha256": _sha256(paper_data),
        "source_aggregates": {
            "results/aggregates/rule_recall.json": _sha256(repo_root / "results/aggregates/rule_recall.json"),
            "results/aggregates/dependency_audit.json": _sha256(repo_root / "results/aggregates/dependency_audit.json"),
            "results/aggregates/a1_replay.json": _sha256(repo_root / "results/aggregates/a1_replay.json"),
            "results/aggregates/g3_instrument.json": _sha256(repo_root / "results/aggregates/g3_instrument.json"),
            "results/aggregates/lowering_mutation_score.json": _sha256(repo_root / "results/aggregates/lowering_mutation_score.json"),
        },
        "source_artifacts": sources,
        "macros": macros,
    }
    manifest_path = output_dir / "evidence_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return macro_path, manifest_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, default=Path("paper/build"))
    args = parser.parse_args()
    macro_path, manifest_path = generate(args.repo_root.resolve(), args.output_dir.resolve())
    print(f"evidence macros generated: {macro_path}")
    print(f"evidence manifest generated: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
