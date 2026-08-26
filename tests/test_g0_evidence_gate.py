"""Integrated consistency gate for the three G0 evidence surfaces."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_g0_evidence import G0EvidenceError, _validate_fixture_report, validate_all
from utils.rule_recall import evaluate_fixture


ROOT = Path(__file__).resolve().parent.parent


def test_gate_accepts_all_retained_g0_artifacts():
    checks = validate_all(ROOT)

    assert checks == (
        "PIPE-2B fixture report",
        "PIPE-4 fixture report",
        "IR-2 NDA pilot manifest",
        "IR-2 privacy pilot manifest",
        "IR-2 current-naming manifest",
    )


def test_gate_rejects_stale_fixture_report(tmp_path):
    report_path = tmp_path / "rule_recall.json"
    report = evaluate_fixture(ROOT / "tests/fixtures/rule_recall_gold")
    report["precision"] = 1.0
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(G0EvidenceError, match="stale or differs"):
        _validate_fixture_report(
            label="PIPE-2B",
            fixture=ROOT / "tests/fixtures/rule_recall_gold",
            report_path=report_path,
            evaluator=evaluate_fixture,
        )


def test_gate_rejects_malformed_manifest_output_hash(tmp_path):
    source = ROOT / "results/aggregates/ir2_full_smallest_privacy/run_manifest.json"
    manifest = json.loads(source.read_text(encoding="utf-8"))
    manifest["outputs"][0]["sha256"] = "0" * 64
    target = tmp_path / "run_manifest.json"
    target.write_text(json.dumps(manifest), encoding="utf-8")

    from scripts.validate_g0_evidence import _validate_ir2_manifest

    with pytest.raises(G0EvidenceError, match="retained output is missing|hash mismatch"):
        _validate_ir2_manifest(target, root=ROOT)
