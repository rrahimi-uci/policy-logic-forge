#!/usr/bin/env python3
"""Validate the retained, provider-free evidence for the three G0 queue items.

This gate checks that the PIPE-2B and PIPE-4 reports are regenerated from the
checked-in fixture contracts, and that every retained IR-2 report hash still
matches its manifest.  It deliberately does not turn fixture-only or
exploratory artifacts into corpus claims: real licensed frames and human
annotation remain external prerequisites.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.dependency_audit import evaluate_fixture as evaluate_dependency_fixture  # noqa: E402
from utils.rule_recall import evaluate_fixture as evaluate_rule_recall_fixture  # noqa: E402


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class G0EvidenceError(ValueError):
    """Raised when a retained G0 artifact is stale or malformed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise G0EvidenceError(message)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise G0EvidenceError(f"cannot read JSON artifact {path}: {exc}") from exc
    _require(isinstance(value, dict), f"JSON artifact must be an object: {path}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise G0EvidenceError(f"cannot hash artifact {path}: {exc}") from exc
    return digest.hexdigest()


def _hash(value: Any, *, label: str) -> str:
    _require(isinstance(value, str) and bool(_SHA256.fullmatch(value)), f"{label} must be a lowercase SHA-256")
    return value


def _relative_path(value: Any, *, label: str) -> Path:
    _require(isinstance(value, str) and bool(value.strip()), f"{label} must be a non-empty relative path")
    path = Path(value)
    _require(not path.is_absolute() and ".." not in path.parts, f"{label} must not escape the repository")
    return path


def _validate_fixture_report(
    *,
    label: str,
    fixture: Path,
    report_path: Path,
    evaluator: Callable[[Path], dict[str, Any]],
) -> None:
    expected = evaluator(fixture)
    actual = _read_json(report_path)
    _require(actual == expected, f"{label} report is stale or differs from its fixture evaluation: {report_path}")
    _require(actual.get("status") == "fixture_only", f"{label} report must remain fixture_only")


def _validate_common_manifest(manifest: Mapping[str, Any], path: Path) -> None:
    _require(manifest.get("schema_version") == "ir2-census-run/1.0", f"{path}: unsupported IR-2 schema")
    _require(manifest.get("task_id") == "IR-2", f"{path}: task_id must be IR-2")
    _require(manifest.get("status") == "exploratory", f"{path}: IR-2 manifest must remain exploratory")
    _require(isinstance(manifest.get("scope_note"), str) and manifest["scope_note"].strip(), f"{path}: scope_note is required")
    repository = manifest.get("repository")
    _require(isinstance(repository, Mapping), f"{path}: repository provenance is required")
    _require(isinstance(repository.get("commit"), str) and bool(_COMMIT.fullmatch(repository["commit"])), f"{path}: repository.commit is invalid")
    _require(isinstance(repository.get("dirty"), bool), f"{path}: repository.dirty must be boolean")
    census = manifest.get("census")
    _require(isinstance(census, Mapping), f"{path}: census metadata is required")
    _require(isinstance(census.get("rule_count"), int) and not isinstance(census["rule_count"], bool) and census["rule_count"] >= 0, f"{path}: census.rule_count is invalid")
    _hash(census.get("report_sha256"), label=f"{path}: census.report_sha256")


def _validate_ir2_manifest(path: Path, *, root: Path) -> None:
    manifest = _read_json(path)
    _validate_common_manifest(manifest, path)

    inputs = manifest.get("inputs")
    _require(isinstance(inputs, Mapping), f"{path}: inputs metadata is required")
    graphs = inputs.get("graphs")
    _require(isinstance(graphs, list) and graphs, f"{path}: at least one input graph is required")
    for index, graph in enumerate(graphs):
        _require(isinstance(graph, Mapping), f"{path}: inputs.graphs[{index}] must be an object")
        _relative_path(graph.get("path"), label=f"{path}: inputs.graphs[{index}].path")
        _require(isinstance(graph.get("bytes"), int) and not isinstance(graph["bytes"], bool) and graph["bytes"] >= 0, f"{path}: inputs.graphs[{index}].bytes is invalid")
        _hash(graph.get("sha256"), label=f"{path}: inputs.graphs[{index}].sha256")

    outputs = manifest.get("outputs")
    _require(isinstance(outputs, list) and outputs, f"{path}: output hashes are required")
    for index, output in enumerate(outputs):
        _require(isinstance(output, Mapping), f"{path}: outputs[{index}] must be an object")
        relative = _relative_path(output.get("path"), label=f"{path}: outputs[{index}].path")
        artifact = root / relative
        _require(artifact.is_file(), f"{path}: retained output is missing: {relative}")
        _require(isinstance(output.get("bytes"), int) and not isinstance(output["bytes"], bool) and output["bytes"] == artifact.stat().st_size, f"{path}: byte count mismatch for {relative}")
        expected_hash = _hash(output.get("sha256"), label=f"{path}: outputs[{index}].sha256")
        _require(_sha256_file(artifact) == expected_hash, f"{path}: hash mismatch for {relative}")


def _validate_legacy_ir2_manifest(path: Path) -> None:
    manifest = _read_json(path)
    _require(isinstance(manifest.get("run_id"), str) and manifest["run_id"].strip(), f"{path}: run_id is required")
    _require(manifest.get("status") == "exploratory_pilot", f"{path}: legacy IR-2 run must remain exploratory_pilot")
    _require(isinstance(manifest.get("scope_note"), str) and manifest["scope_note"].strip(), f"{path}: scope_note is required")
    source = manifest.get("source")
    _require(isinstance(source, Mapping), f"{path}: source metadata is required")
    files = source.get("files")
    _require(isinstance(files, list) and files, f"{path}: source file hashes are required")
    for index, entry in enumerate(files):
        _require(isinstance(entry, Mapping), f"{path}: source.files[{index}] must be an object")
        _relative_path(entry.get("name"), label=f"{path}: source.files[{index}].name")
        _hash(entry.get("sha256"), label=f"{path}: source.files[{index}].sha256")
    artifacts = manifest.get("artifacts")
    _require(isinstance(artifacts, Mapping), f"{path}: artifacts metadata is required")
    _hash(artifacts.get("graph_sha256"), label=f"{path}: artifacts.graph_sha256")


def validate_all(root: Path = ROOT) -> tuple[str, ...]:
    checks: list[tuple[str, Callable[[], None]]] = [
        (
            "PIPE-2B fixture report",
            lambda: _validate_fixture_report(
                label="PIPE-2B",
                fixture=root / "tests/fixtures/rule_recall_gold",
                report_path=root / "results/aggregates/rule_recall.json",
                evaluator=evaluate_rule_recall_fixture,
            ),
        ),
        (
            "PIPE-4 fixture report",
            lambda: _validate_fixture_report(
                label="PIPE-4",
                fixture=root / "tests/fixtures/dependency_gold",
                report_path=root / "results/aggregates/dependency_audit.json",
                evaluator=evaluate_dependency_fixture,
            ),
        ),
        (
            "IR-2 NDA pilot manifest",
            lambda: _validate_legacy_ir2_manifest(root / "results/aggregates/ir2_nda_pilot/run_manifest.json"),
        ),
        (
            "IR-2 privacy pilot manifest",
            lambda: _validate_ir2_manifest(root / "results/aggregates/ir2_full_smallest_privacy/run_manifest.json", root=root),
        ),
        (
            "IR-2 current-naming manifest",
            lambda: _validate_ir2_manifest(root / "results/aggregates/ir2_agent_naming_smallest/run_manifest.json", root=root),
        ),
    ]
    completed: list[str] = []
    for label, check in checks:
        check()
        completed.append(label)
    return tuple(completed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        checks = validate_all()
    except G0EvidenceError as exc:
        print(f"G0 evidence gate failed: {exc}", file=sys.stderr)
        return 1
    for label in checks:
        print(f"PASS {label}")
    print("G0 evidence gate passed: retained artifacts are internally consistent and non-claiming.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
