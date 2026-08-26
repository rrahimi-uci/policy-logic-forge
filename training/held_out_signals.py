"""Held-out grounding and behavioural signals; never reward self-generated vectors."""

from __future__ import annotations

from typing import Any, Iterable, Mapping


def build_signals(cases: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = []
    for index, case in enumerate(cases):
        if not isinstance(case, Mapping) or not isinstance(case.get("case_id"), str):
            raise ValueError(f"cases[{index}] requires case_id")
        if case.get("self_generated") is True:
            raise ValueError("self-generated vectors cannot be held-out signals")
        grounding = case.get("grounding")
        behavior = case.get("behavior")
        if not isinstance(grounding, (int, float)) or not 0 <= grounding <= 1:
            raise ValueError(f"cases[{index}].grounding must be in [0,1]")
        if not isinstance(behavior, (int, float)) or not 0 <= behavior <= 1:
            raise ValueError(f"cases[{index}].behavior must be in [0,1]")
        rows.append({"case_id": case["case_id"], "grounding": float(grounding), "behavior": float(behavior)})
    if not rows:
        raise ValueError("cases must not be empty")
    return {"schema_version": "held-out-signals/1.0", "signals": rows,
            "held_out": True, "self_generated_reward": False}
