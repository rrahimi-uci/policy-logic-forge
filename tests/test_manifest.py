"""BENCH-3 tests for run retention and estimator comparability."""

from __future__ import annotations

from dataclasses import replace

import pytest

from bench.manifest import (
    EstimatorComparison,
    EstimatorSpec,
    ManifestValidationError,
    RunManifest,
    RunRecord,
    expected_run_grid,
    load_manifest,
    write_manifest,
)


def _manifest() -> RunManifest:
    expected = expected_run_grid(["model-a", "model-b"], ["baseline"], 2)
    runs = tuple(
        RunRecord(
            model_id=model_id,
            condition=condition,
            run_id=run_id,
            status="completed" if run_id == 1 else "refused",
            artifact_path=f"runs/{model_id}/{condition}/{run_id}.json" if run_id == 1 else None,
            artifact_sha256="a" * 64 if run_id == 1 else None,
            metrics={"oe": 0.5} if run_id == 1 else {},
            reason=None if run_id == 1 else "unsupported interface",
        )
        for model_id, condition, run_id in expected
    )
    return RunManifest(
        benchmark_id="dutch-anchor",
        split_manifest="bench/splits/dutch_58.json",
        expected_runs=expected,
        runs=runs,
        estimators=(
            EstimatorSpec("mean_oe", "oe", "macro_mean"),
            EstimatorSpec("mean_oe_srl", "oe", "macro_mean"),
            EstimatorSpec("best_oe", "oe", "best_of_k", run_selection="best_of_k", k=2),
        ),
        comparisons=(EstimatorComparison("mean_condition_comparison", ("mean_oe", "mean_oe_srl")),),
        provenance={"seed": 7, "provider": "test"},
    )


def test_expected_grid_is_deterministic_and_complete():
    assert expected_run_grid(["a", "b"], ["baseline", "srl"], 2) == (
        ("a", "baseline", 1),
        ("a", "baseline", 2),
        ("a", "srl", 1),
        ("a", "srl", 2),
        ("b", "baseline", 1),
        ("b", "baseline", 2),
        ("b", "srl", 1),
        ("b", "srl", 2),
    )


def test_manifest_retains_completed_refused_and_failed_runs(tmp_path):
    manifest = _manifest()
    manifest.validate()
    path = tmp_path / "manifest.json"
    write_manifest(path, manifest)
    loaded = load_manifest(path)

    assert len(loaded.runs) == len(loaded.expected_runs) == 4
    assert {run.status for run in loaded.runs} == {"completed", "refused"}
    assert loaded.as_dict()["retention"] == {"all_runs_retained": True, "expected_run_count": 4}
    assert loaded.estimators[2].method == "best_of_k"


def test_missing_or_duplicate_run_is_rejected():
    manifest = _manifest()
    missing = replace(manifest, runs=manifest.runs[:-1])
    with pytest.raises(ManifestValidationError, match="exactly one retained record"):
        missing.validate()

    duplicate = replace(manifest, runs=manifest.runs + (manifest.runs[0],))
    with pytest.raises(ManifestValidationError, match="duplicate model/condition/run"):
        duplicate.validate()


def test_completed_run_requires_content_addressed_artifact():
    manifest = _manifest()
    runs = list(manifest.runs)
    runs[0] = replace(runs[0], artifact_sha256=None)
    invalid = replace(manifest, runs=tuple(runs))
    with pytest.raises(ManifestValidationError, match="artifact_sha256"):
        invalid.validate()


def test_best_of_k_cannot_be_compared_with_mean():
    manifest = _manifest()
    invalid = replace(
        manifest,
        comparisons=(EstimatorComparison("invalid", ("mean_oe", "best_oe")),),
    )
    with pytest.raises(ManifestValidationError, match="best-of-k estimator cannot be compared"):
        invalid.validate()


def test_refused_and_failed_runs_require_reason():
    manifest = _manifest()
    runs = list(manifest.runs)
    runs[1] = replace(runs[1], reason=None)
    invalid = replace(manifest, runs=tuple(runs))
    with pytest.raises(ManifestValidationError, match="refused runs require reason"):
        invalid.validate()

    runs = list(manifest.runs)
    runs[1] = replace(runs[1], status="failed", reason="")
    invalid = replace(manifest, runs=tuple(runs))
    with pytest.raises(ManifestValidationError, match="failed runs require reason"):
        invalid.validate()
