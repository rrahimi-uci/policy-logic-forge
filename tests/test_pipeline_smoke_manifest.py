"""Metadata contract for the retained high-effort pipeline smoke run."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "results" / "aggregates" / "config_high_smoke" / "run_manifest.json"


def test_smoke_manifest_is_metadata_only_and_passed() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert manifest["status"] == "smoke_pass"
    assert manifest["configuration"]["reasoning_model"] == "gpt-5.6-luna"
    assert manifest["configuration"]["reasoning_effort"] == "high"
    # This retained artifact records the historical 32k-cap smoke protocol;
    # current defaults are asserted by the client/configuration tests.
    assert manifest["configuration"]["reasoning_max_completion_tokens"] == 32768
    assert manifest["retained_artifacts"]["metadata_only"] is True
    assert manifest["retained_artifacts"]["source_and_pipeline_output"] == "local-only and not redistributed"


def test_smoke_manifest_records_complete_stage_statuses_and_hashes() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert all(stage["status"] == "pass" for stage in manifest["stages"].values())
    assert manifest["stages"]["dependency_dag"]["coverage"] == "5/5"
    assert all(len(digest) == 64 for digest in manifest["retained_artifacts"]["output_hashes"].values())
