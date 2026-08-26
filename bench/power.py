"""Preregistered sensitivity/power calculations for clustered Spearman tests."""

from __future__ import annotations

import math
from typing import Any, Iterable


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def fisher_z(value: float) -> float:
    if not -1 < value < 1:
        raise ValueError("correlation must be strictly between -1 and 1")
    return math.atanh(value)


def approximate_power(cluster_count: int, true_rho: float, *, null_rho: float = 0.30, alpha: float = 0.05) -> float:
    """Approximate two-sided power with a cluster-count effective n.

    This is a sensitivity curve, not a replacement for simulation.  The
    resulting report labels it explicitly as an approximation.
    """
    if cluster_count < 4:
        raise ValueError("cluster_count must be >= 4")
    if not -1 < true_rho < 1 or not -1 < null_rho < 1:
        raise ValueError("correlations must be strictly between -1 and 1")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    standard_error = 1 / math.sqrt(cluster_count - 3)
    delta = abs(fisher_z(true_rho) - fisher_z(null_rho)) / standard_error
    critical = 1.959963984540054 if alpha == 0.05 else abs(__import__("statistics").NormalDist().inv_cdf(1 - alpha / 2))
    return _normal_cdf(-critical - delta) + 1 - _normal_cdf(critical - delta)


def build_power_curve(cluster_counts: Iterable[int], effect_sizes: Iterable[float], *, null_rho: float = 0.30, alpha: float = 0.05) -> dict[str, Any]:
    counts = [int(value) for value in cluster_counts]
    effects = [float(value) for value in effect_sizes]
    if not counts or not effects:
        raise ValueError("cluster_counts and effect_sizes must be non-empty")
    points = [{"clusters": count, "true_rho": effect,
               "power": approximate_power(count, effect, null_rho=null_rho, alpha=alpha)}
              for count in counts for effect in effects]
    return {"method": "fisher_z_cluster_sensitivity", "null": {"rho": null_rho, "alpha": alpha},
            "points": points, "claimable": False,
            "note": "Approximate sensitivity only; final inference uses model-clustered bootstrap."}
