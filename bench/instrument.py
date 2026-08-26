"""Validation and invalidation rules for G3 instrument bundles."""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

from bench.stats import clustered_bootstrap


class InstrumentValidationError(ValueError):
    """Raised when an instrument bundle is malformed."""


REQUIRED_CONTROLS = {"positive", "random", "stratified", "biased", "leakage_canary", "permuted"}


def validate_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(bundle, Mapping):
        raise InstrumentValidationError("bundle must be an object")
    rows = bundle.get("observations")
    controls = bundle.get("controls")
    if not isinstance(rows, list) or not rows:
        raise InstrumentValidationError("observations must be a non-empty array")
    if not isinstance(controls, Mapping):
        raise InstrumentValidationError("controls must be an object")
    missing = sorted(REQUIRED_CONTROLS - set(controls))
    if missing:
        raise InstrumentValidationError(f"missing controls: {missing}")
    if any(not isinstance(controls[name], list) or not controls[name] for name in REQUIRED_CONTROLS):
        raise InstrumentValidationError("every control must contain at least one case")
    return {"observations": rows, "controls": {key: list(value) for key, value in controls.items()}}


def assess_bundle(bundle: Mapping[str, Any], *, bootstrap_replicates: int = 500) -> dict[str, Any]:
    normalized = validate_bundle(bundle)
    rows = normalized["observations"]
    invalid_reasons: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            invalid_reasons.append("non-object observation")
            continue
        if row.get("leakage_canary_accessible") is True:
            invalid_reasons.append("leakage canary accessible")
        if row.get("permuted_predictive") is True:
            invalid_reasons.append("permuted control remains predictive")
    try:
        estimate = clustered_bootstrap(rows, x_key="afs", y_key="oe", cluster_key="model_id",
                                       replicates=bootstrap_replicates)
    except Exception as exc:
        invalid_reasons.append(f"statistics invalid: {exc}")
        estimate = None
    status = "invalid" if invalid_reasons else ("underpowered" if estimate and estimate["status"] == "underpowered" else "valid")
    return {"schema_version": "g3-instrument/1.0", "status": status,
            "claimable": status == "valid", "reasons": invalid_reasons,
            "estimand": estimate, "controls": sorted(normalized["controls"]),
            "observation_unit": "model_system_run"}
