"""Explicit metric contracts for artifact-free and oracle-labelled signals."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence


class MetricValidationError(ValueError):
    """Raised when a metric row violates its provenance contract."""


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise MetricValidationError(f"{field} must be a finite number")
    return float(value)


def validate_observation(row: Mapping[str, Any]) -> None:
    if not isinstance(row, Mapping):
        raise MetricValidationError("observation must be an object")
    for field in ("model_id", "system", "run_id"):
        if not isinstance(row.get(field), str) or not str(row[field]).strip():
            raise MetricValidationError(f"{field} must be non-empty")
    for field in ("eligible_units", "compiled_units", "afs", "soe", "oe"):
        _number(row.get(field), field)
    eligible, compiled = float(row["eligible_units"]), float(row["compiled_units"])
    if eligible < 0 or compiled < 0 or compiled > eligible:
        raise MetricValidationError("compiled_units must be between zero and eligible_units")
    if not 0 <= float(row["afs"]) <= 1 or not 0 <= float(row["soe"]) <= 1 or not 0 <= float(row["oe"]) <= 1:
        raise MetricValidationError("AFS, sOE, and OE must be in [0, 1]")


def enrich_observation(row: Mapping[str, Any]) -> dict[str, Any]:
    """Add EY and CQI while retaining the provenance of every measure."""
    validate_observation(row)
    result = dict(row)
    eligible, compiled = float(row["eligible_units"]), float(row["compiled_units"])
    result["ey"] = compiled / eligible if eligible else None
    result["cqi"] = float(row["oe"]) if compiled else None
    result["metric_contract"] = {
        "afs": "artifact_free_source_signal",
        "soe": "source_originated_execution_gold_labeled",
        "oe": "oracle_execution_gold_artifact",
        "ey": "executable_yield",
        "cqi": "conditional_quality_not_correctness",
    }
    return result


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    enriched = [enrich_observation(row) for row in rows]
    if not enriched:
        raise MetricValidationError("at least one observation is required")
    return {
        "observation_unit": "model_system_run",
        "rows": len(enriched),
        "eligible_units": sum(float(row["eligible_units"]) for row in enriched),
        "compiled_units": sum(float(row["compiled_units"]) for row in enriched),
        "mean_afs": sum(float(row["afs"]) for row in enriched) / len(enriched),
        "mean_soe": sum(float(row["soe"]) for row in enriched) / len(enriched),
        "mean_oe": sum(float(row["oe"]) for row in enriched) / len(enriched),
        "mean_ey": sum(float(row["ey"]) for row in enriched if row["ey"] is not None) / max(1, sum(row["ey"] is not None for row in enriched)),
        "claim_boundary": "AFS is artifact-free; sOE is gold-labeled; CQI is not correctness.",
    }
