"""Deterministic, dependency-free statistics for instrument validation.

Rows remain at the model × system × run observation unit.  Confidence
intervals resample model clusters, never individual rows, so repeated runs do
not inflate the effective sample size.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence


class StatsValidationError(ValueError):
    """Raised for malformed statistical inputs."""


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise StatsValidationError(f"{field} must be a finite number")
    return float(value)


def _rank(values: Sequence[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda pair: pair[1])
    result = [0.0] * len(values)
    index = 0
    while index < len(indexed):
        end = index + 1
        while end < len(indexed) and indexed[end][1] == indexed[index][1]:
            end += 1
        rank = (index + 1 + end) / 2.0
        for position, _ in indexed[index:end]:
            result[position] = rank
        index = end
    return result


def spearman_correlation(x: Sequence[float], y: Sequence[float]) -> float:
    """Return tie-aware Spearman rho; constant vectors return ``nan``."""
    if len(x) != len(y) or len(x) < 2:
        raise StatsValidationError("x and y must have equal length >= 2")
    x_values = [_finite(value, "x") for value in x]
    y_values = [_finite(value, "y") for value in y]
    xr, yr = _rank(x_values), _rank(y_values)
    x_mean, y_mean = sum(xr) / len(xr), sum(yr) / len(yr)
    numerator = sum((a - x_mean) * (b - y_mean) for a, b in zip(xr, yr))
    denominator = math.sqrt(sum((a - x_mean) ** 2 for a in xr) * sum((b - y_mean) ** 2 for b in yr))
    return numerator / denominator if denominator else math.nan


def _validate_rows(rows: Iterable[Mapping[str, Any]], x_key: str, y_key: str, cluster_key: str) -> list[dict[str, Any]]:
    normalized = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise StatsValidationError(f"row[{index}] must be an object")
        cluster = row.get(cluster_key)
        if not isinstance(cluster, str) or not cluster.strip():
            raise StatsValidationError(f"row[{index}].{cluster_key} must be a non-empty string")
        normalized.append({**row, x_key: _finite(row.get(x_key), f"row[{index}].{x_key}"),
                           y_key: _finite(row.get(y_key), f"row[{index}].{y_key}"), cluster_key: cluster})
    if len({row[cluster_key] for row in normalized}) < 2:
        raise StatsValidationError("at least two independent clusters are required")
    return normalized


def clustered_bootstrap(
    rows: Iterable[Mapping[str, Any]],
    *,
    x_key: str = "afs",
    y_key: str = "oe",
    cluster_key: str = "model_id",
    replicates: int = 2000,
    seed: int = 2027,
    alpha: float = 0.05,
    min_clusters: int = 8,
) -> dict[str, Any]:
    """Estimate rho and a percentile model-clustered bootstrap interval."""
    if not isinstance(replicates, int) or replicates < 100:
        raise StatsValidationError("replicates must be an integer >= 100")
    if not isinstance(seed, int):
        raise StatsValidationError("seed must be an integer")
    if not 0 < alpha < 1:
        raise StatsValidationError("alpha must be between 0 and 1")
    normalized = _validate_rows(rows, x_key, y_key, cluster_key)
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in normalized:
        clusters[row[cluster_key]].append(row)
    cluster_ids = sorted(clusters)
    point = spearman_correlation([row[x_key] for row in normalized], [row[y_key] for row in normalized])
    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(replicates):
        selected = [cluster_ids[rng.randrange(len(cluster_ids))] for _ in cluster_ids]
        boot_rows = [row for cluster_id in selected for row in clusters[cluster_id]]
        value = spearman_correlation([row[x_key] for row in boot_rows], [row[y_key] for row in boot_rows])
        if math.isfinite(value):
            samples.append(value)
    if not samples:
        raise StatsValidationError("bootstrap produced no finite estimates")
    samples.sort()
    lower_index = max(0, min(len(samples) - 1, int((alpha / 2) * len(samples))))
    upper_index = max(0, min(len(samples) - 1, int((1 - alpha / 2) * len(samples)) - 1))
    cluster_count = len(cluster_ids)
    return {
        "estimand": "spearman(afs,oe)",
        "observation_unit": "model_system_run",
        "cluster_key": cluster_key,
        "estimate": None if not math.isfinite(point) else point,
        "ci": {"level": 1 - alpha, "lower": samples[lower_index], "upper": samples[upper_index]},
        "replicates": replicates,
        "seed": seed,
        "clusters": cluster_count,
        "effective_clusters": cluster_count,
        "status": "underpowered" if cluster_count < min_clusters else "valid",
        "min_clusters": min_clusters,
    }
