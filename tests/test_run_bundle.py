"""BENCH-4 tests for content-addressed bundles and release boundaries."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from bench.run_bundle import (
    ArtifactRecord,
    BundleManifest,
    BundleValidationError,
    load_bundle_manifest,
    verify_bundle,
    write_bundle_manifest,
)


def _bundle_root(tmp_path: Path) -> tuple[Path, BundleManifest]:
    (tmp_path / "aggregate.json").write_text('{"oe": 0.5}\n', encoding="utf-8")
    (tmp_path / "run_manifest.json").write_text('{"schema_version": "benchmark-run-manifest/1.0"}\n', encoding="utf-8")
    (tmp_path / "requirements-lock.txt").write_text("pytest==9.1.1\n", encoding="utf-8")
    (tmp_path / "gold.json").write_text('{"restricted": true}\n', encoding="utf-8")

    artifacts = (
        ArtifactRecord.from_file(tmp_path, "aggregate.json", role="aggregate", release_class="aggregate_only"),
        ArtifactRecord.from_file(tmp_path, "run_manifest.json", role="run_manifest", release_class="redistributable"),
        ArtifactRecord.from_file(tmp_path, "requirements-lock.txt", role="requirements_lock", release_class="redistributable"),
        ArtifactRecord.from_file(tmp_path, "gold.json", role="gold", release_class="restricted"),
    )
    return tmp_path, BundleManifest(
        bundle_id="bundle-001",
        run_manifest_path="run_manifest.json",
        requirements_lock_path="requirements-lock.txt",
        artifacts=artifacts,
        release_allowlist=("aggregate.json", "run_manifest.json", "requirements-lock.txt"),
        provenance={"repository_commit": "abc123"},
    )


def test_valid_bundle_round_trips_and_verifies_release_boundary(tmp_path):
    root, manifest = _bundle_root(tmp_path)
    path = root / "bundle.json"
    write_bundle_manifest(path, manifest)

    loaded = load_bundle_manifest(path)
    verification = verify_bundle(root, loaded, release=True)

    assert verification.bundle_id == "bundle-001"
    assert set(verification.checked_artifacts) == {
        "aggregate.json", "run_manifest.json", "requirements-lock.txt", "gold.json"
    }
    assert verification.release_artifacts == (
        "aggregate.json", "run_manifest.json", "requirements-lock.txt"
    )


def test_tampering_is_detected_by_size_or_hash(tmp_path):
    root, manifest = _bundle_root(tmp_path)
    (root / "aggregate.json").write_text('{"oe": 0.9}\n', encoding="utf-8")

    with pytest.raises(BundleValidationError, match="artifact (size|SHA-256) mismatch"):
        verify_bundle(root, manifest)


def test_release_allowlist_cannot_include_gold_or_restricted_artifacts(tmp_path):
    root, manifest = _bundle_root(tmp_path)
    invalid = replace(manifest, release_allowlist=manifest.release_allowlist + ("gold.json",))

    with pytest.raises(BundleValidationError, match="non-releasable|raw/restricted"):
        invalid.validate()


def test_missing_required_lock_or_run_manifest_is_rejected(tmp_path):
    root, manifest = _bundle_root(tmp_path)
    without_lock = replace(manifest, requirements_lock_path="missing-lock.txt")
    with pytest.raises(BundleValidationError, match="requirements_lock_path must identify an artifact"):
        without_lock.validate()

    without_manifest = replace(manifest, run_manifest_path="missing-run.json")
    with pytest.raises(BundleValidationError, match="run_manifest_path must identify an artifact"):
        without_manifest.validate()


def test_duplicate_and_traversal_artifacts_are_rejected(tmp_path):
    root, manifest = _bundle_root(tmp_path)
    duplicate = replace(manifest, artifacts=manifest.artifacts + (manifest.artifacts[0],))
    with pytest.raises(BundleValidationError, match="duplicate artifact path"):
        duplicate.validate()

    with pytest.raises(BundleValidationError, match="traversal"):
        ArtifactRecord.from_file(root, "../outside.json", role="aggregate", release_class="aggregate_only")


def test_release_verification_requires_an_explicit_nonempty_allowlist(tmp_path):
    root, manifest = _bundle_root(tmp_path)
    no_allowlist = replace(manifest, release_allowlist=())
    no_allowlist.validate()

    with pytest.raises(BundleValidationError, match="non-empty allowlist"):
        verify_bundle(root, no_allowlist, release=True)
