"""Content-addressed benchmark bundle and release-boundary validation.

Run retention (``bench.manifest``) records what happened.  This module checks
that a retained bundle can be reproduced from files on disk and that a release
allowlist cannot accidentally publish source, gold, or other local-only data.
No benchmark data is downloaded or generated here.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


SCHEMA_VERSION = "benchmark-run-bundle/1.0"
RELEASE_CLASSES = {"redistributable", "aggregate_only", "local_only", "restricted"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ROLES = {
    "aggregate",
    "generated",
    "gold",
    "metadata",
    "raw_input",
    "raw_output",
    "requirements_lock",
    "run_manifest",
    "script",
    "source",
}
_NON_RELEASE_ROLES = {"gold", "raw_input", "raw_output", "source"}


class BundleValidationError(ValueError):
    """Raised when a bundle is malformed, tampered with, or unsafe to release."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BundleValidationError(message)


def _safe_relative_path(value: Any, field_name: str = "path") -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{field_name} must be a non-empty path")
    candidate = PurePosixPath(value)
    _require(not candidate.is_absolute(), f"{field_name} must be relative")
    _require("\\" not in value, f"{field_name} must use POSIX separators")
    _require(".." not in candidate.parts and "." not in candidate.parts,
             f"{field_name} must not contain traversal segments")
    return value


def sha256_file(path: str | Path) -> str:
    """Return the lowercase SHA-256 digest of a regular file."""
    target = Path(path)
    _require(target.is_file() and not target.is_symlink(), f"not a regular file: {target}")
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_inside(root: Path, relative_path: str) -> Path:
    root_resolved = root.resolve()
    target = (root / relative_path)
    _require(not target.is_symlink(), f"symlink artifacts are not allowed: {relative_path}")
    resolved = target.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise BundleValidationError(f"artifact escapes bundle root: {relative_path}") from exc
    return resolved


@dataclass(frozen=True)
class ArtifactRecord:
    """One content-addressed file and its release classification."""

    path: str
    sha256: str
    size_bytes: int
    role: str
    release_class: str

    def validate(self) -> None:
        _safe_relative_path(self.path, "artifact.path")
        _require(bool(_SHA256.fullmatch(self.sha256)),
                 "artifact.sha256 must be a lowercase 64-character digest")
        _require(isinstance(self.size_bytes, int) and not isinstance(self.size_bytes, bool) and self.size_bytes >= 0,
                 "artifact.size_bytes must be a non-negative integer")
        _require(self.role in _ROLES, f"artifact.role must be one of {sorted(_ROLES)}")
        _require(self.release_class in RELEASE_CLASSES,
                 f"artifact.release_class must be one of {sorted(RELEASE_CLASSES)}")

    @classmethod
    def from_file(cls, root: str | Path, relative_path: str, *, role: str,
                  release_class: str) -> "ArtifactRecord":
        _safe_relative_path(relative_path, "artifact.path")
        target = _resolve_inside(Path(root), relative_path)
        record = cls(
            path=relative_path,
            sha256=sha256_file(target),
            size_bytes=target.stat().st_size,
            role=role,
            release_class=release_class,
        )
        record.validate()
        return record

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "role": self.role,
            "release_class": self.release_class,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ArtifactRecord":
        _require(isinstance(raw, Mapping), "each artifact must be an object")
        record = cls(
            path=raw.get("path"),
            sha256=raw.get("sha256"),
            size_bytes=raw.get("size_bytes"),
            role=raw.get("role"),
            release_class=raw.get("release_class"),
        )
        record.validate()
        return record


@dataclass(frozen=True)
class BundleManifest:
    """Bundle index plus the explicit set of files safe to release."""

    bundle_id: str
    run_manifest_path: str
    requirements_lock_path: str
    artifacts: tuple[ArtifactRecord, ...]
    release_allowlist: tuple[str, ...]
    provenance: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def validate(self) -> None:
        _require(self.schema_version == SCHEMA_VERSION, f"schema_version must be {SCHEMA_VERSION!r}")
        _require(isinstance(self.bundle_id, str) and bool(self.bundle_id.strip()),
                 "bundle_id must be a non-empty string")
        _safe_relative_path(self.run_manifest_path, "run_manifest_path")
        _safe_relative_path(self.requirements_lock_path, "requirements_lock_path")
        _require(isinstance(self.provenance, Mapping), "provenance must be an object")
        _require(self.artifacts, "artifacts must not be empty")

        records: dict[str, ArtifactRecord] = {}
        for artifact in self.artifacts:
            artifact.validate()
            _require(artifact.path not in records, f"duplicate artifact path: {artifact.path}")
            records[artifact.path] = artifact
        _require(self.run_manifest_path in records,
                 "run_manifest_path must identify an artifact")
        _require(records[self.run_manifest_path].role == "run_manifest",
                 "run_manifest_path artifact must have role='run_manifest'")
        _require(self.requirements_lock_path in records,
                 "requirements_lock_path must identify an artifact")
        _require(records[self.requirements_lock_path].role == "requirements_lock",
                 "requirements_lock_path artifact must have role='requirements_lock'")

        _require(len(set(self.release_allowlist)) == len(self.release_allowlist),
                 "release_allowlist contains duplicate paths")
        for path in self.release_allowlist:
            _safe_relative_path(path, "release_allowlist path")
            _require(path in records, f"release_allowlist references unknown artifact: {path}")
            artifact = records[path]
            _require(artifact.release_class in {"redistributable", "aggregate_only"},
                     f"release_allowlist contains non-releasable artifact: {path}")
            _require(artifact.role not in _NON_RELEASE_ROLES,
                     f"release_allowlist contains raw/restricted role: {path}")

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "bundle_id": self.bundle_id,
            "run_manifest_path": self.run_manifest_path,
            "requirements_lock_path": self.requirements_lock_path,
            "artifacts": [artifact.as_dict() for artifact in self.artifacts],
            "release_allowlist": list(self.release_allowlist),
            "provenance": dict(self.provenance),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "BundleManifest":
        _require(isinstance(raw, Mapping), "bundle manifest root must be an object")
        artifacts = raw.get("artifacts")
        allowlist = raw.get("release_allowlist")
        _require(isinstance(artifacts, list), "artifacts must be an array")
        _require(isinstance(allowlist, list) and all(isinstance(item, str) for item in allowlist),
                 "release_allowlist must be a string array")
        manifest = cls(
            bundle_id=raw.get("bundle_id"),
            run_manifest_path=raw.get("run_manifest_path"),
            requirements_lock_path=raw.get("requirements_lock_path"),
            artifacts=tuple(ArtifactRecord.from_dict(item) for item in artifacts),
            release_allowlist=tuple(allowlist),
            provenance=raw.get("provenance", {}),
            schema_version=raw.get("schema_version"),
        )
        manifest.validate()
        return manifest


@dataclass(frozen=True)
class BundleVerification:
    """Successful verification details; failures raise BundleValidationError."""

    bundle_id: str
    checked_artifacts: tuple[str, ...]
    release_artifacts: tuple[str, ...]


def write_bundle_manifest(path: str | Path, manifest: BundleManifest) -> None:
    """Validate and write a deterministic bundle index."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_bundle_manifest(path: str | Path) -> BundleManifest:
    """Load and structurally validate a bundle index."""
    return BundleManifest.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def verify_bundle(root: str | Path, manifest: BundleManifest | str | Path, *, release: bool = False) -> BundleVerification:
    """Verify all recorded files and, optionally, the publishable boundary.

    ``release=True`` validates only the explicit allowlist boundary; local-only
    and restricted artifacts may remain in the bundle but cannot be released.
    """
    bundle_root = Path(root)
    checked = manifest if isinstance(manifest, BundleManifest) else load_bundle_manifest(manifest)
    checked.validate()
    if release:
        _require(bool(checked.release_allowlist), "release verification requires a non-empty allowlist")

    for artifact in checked.artifacts:
        target = _resolve_inside(bundle_root, artifact.path)
        _require(target.is_file(), f"artifact is missing or not a file: {artifact.path}")
        _require(target.stat().st_size == artifact.size_bytes,
                 f"artifact size mismatch: {artifact.path}")
        _require(sha256_file(target) == artifact.sha256,
                 f"artifact SHA-256 mismatch: {artifact.path}")

    release_paths = checked.release_allowlist if release else ()
    return BundleVerification(
        bundle_id=checked.bundle_id,
        checked_artifacts=tuple(artifact.path for artifact in checked.artifacts),
        release_artifacts=tuple(release_paths),
    )
