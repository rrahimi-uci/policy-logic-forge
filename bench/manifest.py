"""Retention and estimator manifest for stochastic benchmark runs.

The benchmark protocol has two separate concerns that are easy to conflate:
retaining every model/condition/run observation, and aggregating those
observations for a reported estimator.  This module keeps the observations
losslessly in a small JSON contract and makes estimator comparisons explicit.

In particular, a ``macro_mean`` and a ``best_of_k`` estimator may both be
declared, but a comparison entry containing one of each is rejected.  The
anchor's best-of-five result therefore cannot silently be compared with a
mean-over-five result.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "benchmark-run-manifest/1.0"
RUN_STATUSES = {"completed", "refused", "failed"}
ESTIMATOR_METHODS = {"macro_mean", "best_of_k"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ManifestValidationError(ValueError):
    """Raised when a run-retention or estimator manifest is invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ManifestValidationError(message)


def _nonempty_string(value: Any, field_name: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class RunRecord:
    """One retained stochastic observation.

    A failed or refused run is retained as a record with a reason rather than
    being omitted from the denominator.  A completed run must point to its
    retained output and content hash.
    """

    model_id: str
    condition: str
    run_id: int
    status: str = "completed"
    artifact_path: str | None = None
    artifact_sha256: str | None = None
    metrics: Mapping[str, float] = field(default_factory=dict)
    reason: str | None = None

    @property
    def key(self) -> tuple[str, str, int]:
        return self.model_id, self.condition, self.run_id

    def validate(self) -> None:
        _nonempty_string(self.model_id, "run.model_id")
        _nonempty_string(self.condition, "run.condition")
        _require(isinstance(self.run_id, int) and not isinstance(self.run_id, bool) and self.run_id >= 1,
                 "run.run_id must be a positive integer")
        _require(self.status in RUN_STATUSES, f"run.status must be one of {sorted(RUN_STATUSES)}")

        if self.status == "completed":
            _require(isinstance(self.artifact_path, str) and bool(self.artifact_path.strip()),
                     "completed runs require artifact_path")
            _require(isinstance(self.artifact_sha256, str) and _SHA256.fullmatch(self.artifact_sha256),
                     "completed runs require a lowercase 64-character artifact_sha256")
            _require(self.reason in (None, ""), "completed runs must not carry a failure/refusal reason")
        else:
            _require(isinstance(self.reason, str) and bool(self.reason.strip()),
                     f"{self.status} runs require reason")

        _require(isinstance(self.metrics, Mapping), "run.metrics must be an object")
        for metric, value in self.metrics.items():
            _nonempty_string(metric, "run.metrics key")
            _require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value),
                     f"run.metrics[{metric!r}] must be a finite number")

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "model_id": self.model_id,
            "condition": self.condition,
            "run_id": self.run_id,
            "status": self.status,
            "artifact_path": self.artifact_path,
            "artifact_sha256": self.artifact_sha256,
            "metrics": dict(self.metrics),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RunRecord":
        _require(isinstance(raw, Mapping), "each run must be an object")
        record = cls(
            model_id=raw.get("model_id"),
            condition=raw.get("condition"),
            run_id=raw.get("run_id"),
            status=raw.get("status", "completed"),
            artifact_path=raw.get("artifact_path"),
            artifact_sha256=raw.get("artifact_sha256"),
            metrics=raw.get("metrics", {}),
            reason=raw.get("reason"),
        )
        record.validate()
        return record


@dataclass(frozen=True)
class EstimatorSpec:
    """A named, reproducible aggregation over retained run records."""

    estimator_id: str
    metric: str
    method: str
    aggregation_unit: str = "model"
    run_selection: str = "all_runs"
    k: int | None = None

    def validate(self) -> None:
        _nonempty_string(self.estimator_id, "estimator.estimator_id")
        _nonempty_string(self.metric, "estimator.metric")
        _require(self.method in ESTIMATOR_METHODS,
                 f"estimator.method must be one of {sorted(ESTIMATOR_METHODS)}")
        _require(self.aggregation_unit == "model",
                 "estimator.aggregation_unit must be 'model' for the preregistered benchmark")
        if self.method == "macro_mean":
            _require(self.run_selection == "all_runs", "macro_mean requires run_selection='all_runs'")
            _require(self.k is None, "macro_mean must not set k")
        else:
            _require(self.run_selection == "best_of_k", "best_of_k requires run_selection='best_of_k'")
            _require(isinstance(self.k, int) and not isinstance(self.k, bool) and self.k >= 1,
                     "best_of_k requires a positive integer k")

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "estimator_id": self.estimator_id,
            "metric": self.metric,
            "method": self.method,
            "aggregation_unit": self.aggregation_unit,
            "run_selection": self.run_selection,
            "k": self.k,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "EstimatorSpec":
        _require(isinstance(raw, Mapping), "each estimator must be an object")
        spec = cls(
            estimator_id=raw.get("estimator_id"),
            metric=raw.get("metric"),
            method=raw.get("method"),
            aggregation_unit=raw.get("aggregation_unit", "model"),
            run_selection=raw.get("run_selection", "all_runs"),
            k=raw.get("k"),
        )
        spec.validate()
        return spec


@dataclass(frozen=True)
class EstimatorComparison:
    """An explicitly comparable set of estimator IDs."""

    comparison_id: str
    estimator_ids: tuple[str, ...]

    def validate(self, estimators: Mapping[str, EstimatorSpec]) -> None:
        _nonempty_string(self.comparison_id, "comparison.comparison_id")
        _require(len(self.estimator_ids) >= 2, "comparison requires at least two estimators")
        _require(len(set(self.estimator_ids)) == len(self.estimator_ids),
                 "comparison.estimator_ids must be unique")
        missing = [estimator_id for estimator_id in self.estimator_ids if estimator_id not in estimators]
        _require(not missing, f"comparison references unknown estimators: {missing}")
        selected = [estimators[estimator_id] for estimator_id in self.estimator_ids]
        methods = {spec.method for spec in selected}
        _require(not ({"macro_mean", "best_of_k"} <= methods),
                 "best-of-k estimator cannot be compared with a mean estimator")
        _require(len({spec.metric for spec in selected}) == 1,
                 "comparison estimators must use the same metric")
        _require(len({spec.aggregation_unit for spec in selected}) == 1,
                 "comparison estimators must use the same aggregation unit")
        _require(len({(spec.method, spec.k) for spec in selected}) == 1,
                 "comparison estimators must use the same estimator method and k")

    def as_dict(self) -> dict[str, Any]:
        return {"comparison_id": self.comparison_id, "estimator_ids": list(self.estimator_ids)}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "EstimatorComparison":
        _require(isinstance(raw, Mapping), "each comparison must be an object")
        ids = raw.get("estimator_ids")
        _require(isinstance(ids, list) and all(isinstance(item, str) for item in ids),
                 "comparison.estimator_ids must be a string array")
        return cls(comparison_id=raw.get("comparison_id"), estimator_ids=tuple(ids))


@dataclass(frozen=True)
class RunManifest:
    """Complete retention manifest for one benchmark execution."""

    benchmark_id: str
    split_manifest: str
    expected_runs: tuple[tuple[str, str, int], ...]
    runs: tuple[RunRecord, ...]
    estimators: tuple[EstimatorSpec, ...]
    comparisons: tuple[EstimatorComparison, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def validate(self) -> None:
        _require(self.schema_version == SCHEMA_VERSION, f"schema_version must be {SCHEMA_VERSION!r}")
        _nonempty_string(self.benchmark_id, "benchmark_id")
        _nonempty_string(self.split_manifest, "split_manifest")
        _require(isinstance(self.provenance, Mapping), "provenance must be an object")

        expected = []
        for item in self.expected_runs:
            _require(isinstance(item, tuple) and len(item) == 3, "expected_runs entries must be (model_id, condition, run_id)")
            record = RunRecord(model_id=item[0], condition=item[1], run_id=item[2])
            _nonempty_string(record.model_id, "expected_runs.model_id")
            _nonempty_string(record.condition, "expected_runs.condition")
            _require(isinstance(record.run_id, int) and not isinstance(record.run_id, bool) and record.run_id >= 1,
                     "expected_runs.run_id must be a positive integer")
            expected.append(record.key)
        _require(len(set(expected)) == len(expected), "expected_runs contains duplicate keys")

        actual = []
        for run in self.runs:
            run.validate()
            actual.append(run.key)
        _require(len(set(actual)) == len(actual), "runs contains duplicate model/condition/run keys")
        _require(set(actual) == set(expected),
                 "runs must contain exactly one retained record for every expected run")

        estimator_map: dict[str, EstimatorSpec] = {}
        for estimator in self.estimators:
            estimator.validate()
            _require(estimator.estimator_id not in estimator_map,
                     f"duplicate estimator_id: {estimator.estimator_id}")
            estimator_map[estimator.estimator_id] = estimator
        comparison_ids: set[str] = set()
        for comparison in self.comparisons:
            _require(comparison.comparison_id not in comparison_ids,
                     f"duplicate comparison_id: {comparison.comparison_id}")
            comparison_ids.add(comparison.comparison_id)
            comparison.validate(estimator_map)

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "benchmark_id": self.benchmark_id,
            "split_manifest": self.split_manifest,
            "retention": {"all_runs_retained": True, "expected_run_count": len(self.expected_runs)},
            "expected_runs": [
                {"model_id": model_id, "condition": condition, "run_id": run_id}
                for model_id, condition, run_id in self.expected_runs
            ],
            "runs": [run.as_dict() for run in self.runs],
            "estimators": [estimator.as_dict() for estimator in self.estimators],
            "comparisons": [comparison.as_dict() for comparison in self.comparisons],
            "provenance": dict(self.provenance),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RunManifest":
        _require(isinstance(raw, Mapping), "manifest root must be an object")
        retention = raw.get("retention")
        _require(isinstance(retention, Mapping) and retention.get("all_runs_retained") is True,
                 "retention.all_runs_retained must be true")
        expected_raw = raw.get("expected_runs")
        _require(isinstance(expected_raw, list), "expected_runs must be an array")
        expected = []
        for item in expected_raw:
            _require(isinstance(item, Mapping), "expected_runs entries must be objects")
            expected.append((item.get("model_id"), item.get("condition"), item.get("run_id")))
        runs_raw = raw.get("runs")
        estimators_raw = raw.get("estimators")
        comparisons_raw = raw.get("comparisons", [])
        _require(isinstance(runs_raw, list), "runs must be an array")
        _require(isinstance(estimators_raw, list), "estimators must be an array")
        _require(isinstance(comparisons_raw, list), "comparisons must be an array")
        manifest = cls(
            benchmark_id=raw.get("benchmark_id"),
            split_manifest=raw.get("split_manifest"),
            expected_runs=tuple(expected),
            runs=tuple(RunRecord.from_dict(item) for item in runs_raw),
            estimators=tuple(EstimatorSpec.from_dict(item) for item in estimators_raw),
            comparisons=tuple(EstimatorComparison.from_dict(item) for item in comparisons_raw),
            provenance=raw.get("provenance", {}),
            schema_version=raw.get("schema_version"),
        )
        manifest.validate()
        return manifest


def expected_run_grid(model_ids: Iterable[str], conditions: Iterable[str], runs_per_condition: int) -> tuple[tuple[str, str, int], ...]:
    """Build deterministic expected run keys for a frozen benchmark grid."""
    _require(isinstance(runs_per_condition, int) and runs_per_condition >= 1,
             "runs_per_condition must be a positive integer")
    return tuple(
        (model_id, condition, run_id)
        for model_id in model_ids
        for condition in conditions
        for run_id in range(1, runs_per_condition + 1)
    )


def write_manifest(path: str | Path, manifest: RunManifest) -> None:
    """Validate and write a deterministic JSON retention manifest."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_manifest(path: str | Path) -> RunManifest:
    """Load and validate a retention manifest from JSON."""
    return RunManifest.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
