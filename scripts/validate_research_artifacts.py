#!/usr/bin/env python3
"""Validate retained research-stage result artifacts without running providers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
REQUIRED = {
    "a2_replication.json": ("a2-replication/1.0", {"completed", "blocked", "unrun"}),
    "j1.json": ("anchor-harness/1.0", {"completed", "disagreement", "invalid", "timeout", "unrun"}),
    "exception_readings.json": ("exception-reading/1.0", {"selected", "unrun"}),
    "perturb_iaa.json": ("perturbation/1.0", {"valid", "review", "unrun"}),
    "g3_instrument.json": ("g3-instrument/1.0", {"valid", "underpowered", "invalid", "unrun"}),
    "assumption_review.json": ("assumptions/1.0", {"completed", "unrun"}),
    "g4_cegir.json": ("cegir-ablation/1.0", {"completed", "unrun"}),
    "reward_red_team.json": ("reward-audit/1.0", {"pass", "fail", "unrun"}),
    "g5_training.json": ("g5-training/1.0", {"completed", "blocked", "unrun"}),
}


class ArtifactValidationError(ValueError):
    """Raised when a retained artifact is malformed or overclaims evidence."""


def validate(root: Path = ROOT) -> tuple[str, ...]:
    aggregate_root = root / "results" / "aggregates"
    checked: list[str] = []
    for filename, (schema, statuses) in REQUIRED.items():
        path = aggregate_root / filename
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ArtifactValidationError(f"{filename}: cannot load JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ArtifactValidationError(f"{filename}: root must be an object")
        if payload.get("schema_version") != schema:
            raise ArtifactValidationError(f"{filename}: schema_version must be {schema!r}")
        status = payload.get("status")
        if status not in statuses:
            raise ArtifactValidationError(f"{filename}: unsupported status {status!r}")
        if payload.get("claimable") is True and status not in {"completed", "valid", "pass", "selected"}:
            raise ArtifactValidationError(f"{filename}: non-terminal status cannot be claimable")
        if status in {"unrun", "blocked", "invalid", "underpowered", "review", "fail", "disagreement", "timeout"} and payload.get("claimable") is not False:
            raise ArtifactValidationError(f"{filename}: non-claiming status must set claimable=false")
        if filename == "a2_replication.json" and status == "blocked":
            blocked_on = payload.get("blocked_on")
            if not isinstance(blocked_on, list) or not blocked_on or not all(isinstance(item, str) and item for item in blocked_on):
                raise ArtifactValidationError("a2_replication.json: blocked status requires a non-empty blocked_on list")
        checked.append(filename)
    return tuple(checked)


def main() -> int:
    try:
        checked = validate()
    except ArtifactValidationError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"Research artifacts valid: {len(checked)} artifact(s), no overclaiming statuses.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
