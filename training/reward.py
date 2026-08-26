"""Reward composition and adversarial audit helpers."""

from __future__ import annotations

from typing import Any, Mapping


def compose_reward(*, coverage: float, grounding: float, behavior: float, omission_rate: float) -> dict[str, Any]:
    values = {"coverage": coverage, "grounding": grounding, "behavior": behavior, "omission_rate": omission_rate}
    if any(not isinstance(value, (int, float)) or not 0 <= value <= 1 for value in values.values()):
        raise ValueError("all reward components must be in [0,1]")
    score = 0.3 * coverage + 0.35 * grounding + 0.35 * behavior - 0.2 * omission_rate
    return {"components": values, "score": score, "source_grounded": True, "held_out": True}


def audit_reward(baseline: Mapping[str, Any], attacks: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    baseline_score = float(baseline.get("score", 0))
    findings = []
    for name, attack in attacks.items():
        score = float(attack.get("score", 0))
        findings.append({"attack": name, "score": score, "worse_than_baseline": score < baseline_score})
    exploits = [item for item in findings if not item["worse_than_baseline"]]
    return {"schema_version": "reward-audit/1.0", "baseline_score": baseline_score,
            "findings": findings, "exploits": exploits, "status": "fail" if exploits else "pass",
            "claimable": not exploits}
