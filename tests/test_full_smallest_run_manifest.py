import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "results" / "aggregates" / "full_smallest_privacy" / "run_manifest.json"


def test_full_smallest_run_retains_fail_closed_status() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert manifest["status"] == "requires_review"
    assert manifest["configuration"]["reasoning_model"] == "gpt-5.6-luna"
    assert manifest["configuration"]["reasoning_effort"] == "high"
    assert manifest["stages"]["readiness_remediator"]["review"] == 0
    assert manifest["stages"]["grounding_verifier"]["rules_certified"] == "0/4"
    assert manifest["stages"]["dependency_dag"]["coverage"] == "4/4"
    assert manifest["retained_artifacts"]["metadata_only"] is True


def test_full_smallest_run_hashes_are_content_addressed() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert len(manifest["source"]["files"][0]["sha256"]) == 64
    assert all(len(value) == 64 for value in manifest["retained_artifacts"]["output_hashes"].values())
