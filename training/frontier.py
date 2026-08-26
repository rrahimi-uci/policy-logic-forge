"""Provider/GPU-gated reward frontier reporting."""

from __future__ import annotations

from typing import Any, Iterable, Mapping


def build_frontier(runs: Iterable[Mapping[str, Any]], *, authorization: bool = False) -> dict[str, Any]:
    """Validate a retained Pareto frontier without pretending training ran.

    ``authorization`` is an explicit boundary: callers cannot accidentally
    launch paid-provider or GPU work by importing this module.
    """
    rows = list(runs)
    if not authorization:
        return {"schema_version": "g5-training/1.0", "status": "blocked",
                "claimable": False, "reason": "GPU/provider authorization is required", "runs": []}
    if not rows:
        raise ValueError("runs must be non-empty after authorization")
    required = {"coverage", "grounding", "behavior", "omission_rate", "model_size"}
    normalized = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping) or not required <= set(row):
            raise ValueError(f"run[{index}] is missing frontier fields")
        normalized.append(dict(row))
    return {"schema_version": "g5-training/1.0", "status": "completed",
            "claimable": True, "reason": None, "runs": normalized,
            "frontier_definition": "maximize coverage, grounding, behavior; minimize omission_rate and model_size"}
