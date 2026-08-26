"""Independent coverage inventory used only during reward development."""

from __future__ import annotations

import hashlib
from typing import Any, Iterable, Mapping


def build_inventory(source_units: Iterable[Mapping[str, Any]], *, author: str = "independent") -> dict[str, Any]:
    units = []
    for index, unit in enumerate(source_units):
        if not isinstance(unit, Mapping) or not isinstance(unit.get("unit_id"), str) or not unit["unit_id"].strip():
            raise ValueError(f"source_units[{index}] requires unit_id")
        units.append({"unit_id": unit["unit_id"], "category": unit.get("category", "unclassified"),
                      "required": bool(unit.get("required", True))})
    if not units:
        raise ValueError("source_units must not be empty")
    digest = hashlib.sha256("\n".join(sorted(item["unit_id"] for item in units)).encode()).hexdigest()
    return {"schema_version": "coverage-inventory/1.0", "author": author,
            "inventory_sha256": digest, "units": units, "training_only": True,
            "held_out_overlap": False}


def coverage_score(inventory: Mapping[str, Any], observed_unit_ids: Iterable[str]) -> float:
    if not inventory.get("training_only") or inventory.get("held_out_overlap"):
        raise ValueError("inventory must be independent training-only data")
    required = {item["unit_id"] for item in inventory.get("units", []) if item.get("required")}
    observed = {str(value) for value in observed_unit_ids}
    return len(required & observed) / len(required) if required else 1.0
