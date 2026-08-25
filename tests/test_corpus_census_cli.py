"""CLI and provenance tests for the IR-2 census runner."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from scripts.corpus_census import _display_path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "corpus_census.py"


def _graph() -> dict:
    return {
        "business_rules": [
            {
                "rule_id": "R1",
                "rule_name": "The recipient shall protect information.",
                "description": "The recipient shall protect information.",
                "variables": [{"name": "active", "type": "boolean", "role": "input"}],
                "condition_predicates": [{"variable": "active", "operator": "==", "value_type": "boolean"}],
                "outcomes": [{"variable": "decision", "operator": "=", "value_type": "enum"}],
            }
        ]
    }


def test_cli_writes_reports_and_content_addressed_manifest(tmp_path):
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_graph()), encoding="utf-8")
    out_dir = tmp_path / "reports"
    manifest_path = tmp_path / "manifest.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--check-subset",
            "boolean,number,enum",
            "--out-dir",
            str(out_dir),
            "--run-label",
            "fixture-ir2",
            "--scope-note",
            "Synthetic contract fixture; not a corpus estimate.",
            "--manifest-out",
            str(manifest_path),
            str(graph_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Subset ['boolean', 'number', 'enum']: 1/1 rules covered (100.0%)" in completed.stdout
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "ir2-census-run/1.0"
    assert manifest["task_id"] == "IR-2"
    assert manifest["status"] == "exploratory"
    assert manifest["census"]["rule_count"] == 1
    assert manifest["subset"]["covered_rules"] == 1
    source = manifest["inputs"]["graphs"][0]
    assert source["path"] == "graph.json"
    assert source["sha256"] == hashlib.sha256(graph_path.read_bytes()).hexdigest()
    for output in manifest["outputs"]:
        output_path = out_dir / output["path"]
        assert output_path.exists()
        assert output["sha256"] == hashlib.sha256(output_path.read_bytes()).hexdigest()


def test_manifest_requires_explicit_run_scope_note(tmp_path):
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_graph()), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest-out",
            str(tmp_path / "manifest.json"),
            "--run-label",
            "missing-scope",
            str(graph_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "requires both --run-label and --scope-note" in completed.stderr


def test_manifest_path_labels_use_current_agent_identifier_convention():
    legacy = ROOT / "pipeline-output" / "run" / ("agent" + "-5-" + "optimized") / "graph.json"
    assert _display_path(legacy) == "pipeline-output/run/agent_05_optimized/graph.json"
