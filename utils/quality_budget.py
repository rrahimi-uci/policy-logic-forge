"""Deterministic quality-hold cohort and release-budget accounting.

This module does not change a grounding verdict.  It makes the denominator,
failure cohorts, and exact integer budget for a target hold rate explicit so a
pipeline cannot appear to pass through rounding, dropped rules, or a changed
cohort.  It accepts the public ``kg_grounding_report.json`` contract and emits
a compact, reproducible JSON summary suitable for CI and before/after runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


VERDICTS = ("supported", "contradicted", "insufficient_evidence")
CURRENT_CORE_TYPES = frozenset({"description", "condition", "outcome"})
CURRENT_ENRICHMENT_TYPES = frozenset({"party", "scope", "exception", "test_vector", "execution"})
DECISION_MATERIAL_TYPES = frozenset({"condition", "outcome", "exception", "scope"})
PRESENTATION_OR_PARTY_TYPES = frozenset({"description", "party"})


class QualityBudgetError(ValueError):
    """Raised when a grounding report is internally inconsistent."""


def _as_nonnegative_int(report: Mapping[str, Any], key: str) -> int:
    value = report.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise QualityBudgetError(f"{key} must be a non-negative integer (got {value!r})")
    return value


def _failed_claims(failures: Iterable[Mapping[str, Any]]) -> list[tuple[str, Mapping[str, Any]]]:
    rows: list[tuple[str, Mapping[str, Any]]] = []
    for failure in failures:
        rule_id = str(failure.get("rule_id") or "").strip()
        if not rule_id:
            raise QualityBudgetError("every rule failure must contain rule_id")
        claims = failure.get("claims")
        if not isinstance(claims, list):
            raise QualityBudgetError(f"failure {rule_id!r} must contain a claims list")
        for claim in claims:
            if not isinstance(claim, Mapping):
                raise QualityBudgetError(f"failure {rule_id!r} contains a non-object claim")
            verdict = str(claim.get("verdict") or "")
            if verdict not in {"contradicted", "insufficient_evidence"}:
                raise QualityBudgetError(
                    f"failure {rule_id!r} contains non-failing verdict {verdict!r}"
                )
            rows.append((rule_id, claim))
    return rows


def _cohort_count(rule_types: Mapping[str, set[str]], *, allowed: set[str] | frozenset[str] | None = None,
                  intersects: set[str] | frozenset[str] | None = None) -> int:
    count = 0
    for claim_types in rule_types.values():
        if allowed is not None and claim_types <= allowed:
            count += 1
        elif intersects is not None and claim_types & intersects:
            count += 1
    return count


def summarize_quality_budget(report: Mapping[str, Any], *, target_rate_percent: float = 10.0) -> dict[str, Any]:
    """Return exact failure cohorts and the integer budget for ``target_rate_percent``.

    The target count uses ``floor``.  For example, 10% of 628 is 62.8, so 62
    held rules pass and 63 do not.  This is intentionally stricter than
    rounding the displayed percentage.
    """

    if not isinstance(target_rate_percent, (int, float)) or isinstance(target_rate_percent, bool):
        raise QualityBudgetError("target_rate_percent must be numeric")
    if not 0 <= float(target_rate_percent) <= 100:
        raise QualityBudgetError("target_rate_percent must be between 0 and 100")

    total_rules = _as_nonnegative_int(report, "total_rules")
    rules_certified = _as_nonnegative_int(report, "rules_certified")
    rules_failed = _as_nonnegative_int(report, "rules_failed")
    held_rules = _as_nonnegative_int(report, "rules_requiring_review")
    human_rules = _as_nonnegative_int(report, "human_review_required_rules")
    total_claims = _as_nonnegative_int(report, "total_claims")
    claim_counts = {verdict: _as_nonnegative_int(report, f"{verdict}_claims") for verdict in VERDICTS}

    if rules_certified + rules_failed != total_rules:
        raise QualityBudgetError("rules_certified + rules_failed must equal total_rules")
    if sum(claim_counts.values()) != total_claims:
        raise QualityBudgetError("supported + contradicted + insufficient claims must equal total_claims")
    if held_rules > total_rules or human_rules > held_rules:
        raise QualityBudgetError("human_review_required_rules <= rules_requiring_review <= total_rules is required")

    failures = report.get("failures")
    if not isinstance(failures, list):
        raise QualityBudgetError("failures must be a list")
    failure_rule_ids: list[str] = []
    claim_free_rule_ids: set[str] = set()
    evidence_authenticity_rule_ids: set[str] = set()
    for failure in failures:
        if not isinstance(failure, Mapping):
            raise QualityBudgetError("failures must contain JSON objects")
        rule_id = str(failure.get("rule_id") or "").strip()
        if not rule_id:
            raise QualityBudgetError("every rule failure must contain rule_id")
        failure_rule_ids.append(rule_id)
        claims = failure.get("claims")
        if isinstance(claims, list) and not claims:
            claim_free_rule_ids.add(rule_id)
            reason = str(failure.get("reason") or "")
            if "evidence quotes not found in the cited corpus" in reason:
                evidence_authenticity_rule_ids.add(rule_id)

    if len(failure_rule_ids) != rules_failed:
        raise QualityBudgetError(
            f"failures contains {len(failure_rule_ids)} records but rules_failed is {rules_failed}"
        )
    if len(set(failure_rule_ids)) != len(failure_rule_ids):
        raise QualityBudgetError("failures must contain exactly one record per failed rule")

    rows = _failed_claims(failures)
    rule_types: dict[str, set[str]] = defaultdict(set)
    type_claims: dict[str, int] = defaultdict(int)
    type_rules: dict[str, set[str]] = defaultdict(set)
    verdict_claims: dict[str, int] = defaultdict(int)
    verdict_rules: dict[str, set[str]] = defaultdict(set)
    for rule_id, claim in rows:
        claim_type = str(claim.get("claim_type") or "unknown")
        verdict = str(claim.get("verdict"))
        rule_types[rule_id].add(claim_type)
        type_claims[claim_type] += 1
        type_rules[claim_type].add(rule_id)
        verdict_claims[verdict] += 1
        verdict_rules[verdict].add(rule_id)
    claim_failure_rule_ids = set(rule_types)
    failure_ids_without_claims = set(failure_rule_ids) - claim_failure_rule_ids
    if failure_ids_without_claims != claim_free_rule_ids:
        raise QualityBudgetError("claim-bearing and claim-free failure families do not reconcile")
    operational_rule_ids = claim_free_rule_ids - evidence_authenticity_rule_ids

    relationship = report.get("relationship_verification")
    relationship = relationship if isinstance(relationship, Mapping) else {}
    relationship_failures = relationship.get("failures")
    relationship_failures = relationship_failures if isinstance(relationship_failures, list) else []
    affected_relationship_rules = {
        str(rule_id)
        for failure in relationship_failures if isinstance(failure, Mapping)
        for rule_id in (failure.get("affected_rule_ids") or [])
        if str(rule_id).strip()
    }

    target_max = math.floor(total_rules * float(target_rate_percent) / 100.0)
    claim_type_rows = [
        {"claim_type": claim_type, "failed_claims": type_claims[claim_type], "affected_rules": len(type_rules[claim_type])}
        for claim_type in sorted(type_claims, key=lambda value: (-len(type_rules[value]), value))
    ]
    return {
        "schema_version": "quality-budget/1",
        "denominator": {"total_rules": total_rules, "total_claims": total_claims},
        "baseline": {
            "rules_certified": rules_certified,
            "rules_failed": rules_failed,
            "rules_requiring_review": held_rules,
            "human_review_required_rules": human_rules,
            "claim_counts": claim_counts,
        },
        "target": {
            "rate_percent": float(target_rate_percent),
            "maximum_held_rules": target_max,
            "passes_target": held_rules <= target_max,
            "quality_holds_to_clear": max(0, held_rules - target_max),
            "failed_rules_to_resolve": max(0, rules_failed - target_max),
            "human_reviews_to_resolve": max(0, human_rules - target_max),
        },
        "failed_rule_claims": {
            "total": len(rows),
            "affected_rules": len(claim_failure_rule_ids),
            "by_verdict": {
                verdict: {"failed_claims": verdict_claims[verdict], "affected_rules": len(verdict_rules[verdict])}
                for verdict in ("contradicted", "insufficient_evidence")
            },
            "by_claim_type": claim_type_rows,
        },
        "failure_families": {
            "claim_verdict_failure_rules": len(claim_failure_rule_ids),
            "evidence_authenticity_failure_rules": len(evidence_authenticity_rule_ids),
            "other_claim_free_failure_rules": len(operational_rule_ids),
            "all_failed_rules_reconciled": (
                len(claim_failure_rule_ids | claim_free_rule_ids) == rules_failed
            ),
        },
        "cohorts": {
            "only_party_or_scope": _cohort_count(rule_types, allowed=frozenset({"party", "scope"})),
            "only_current_enrichment": _cohort_count(rule_types, allowed=CURRENT_ENRICHMENT_TYPES),
            "has_current_core": _cohort_count(rule_types, intersects=CURRENT_CORE_TYPES),
            "has_decision_material_failure": _cohort_count(rule_types, intersects=DECISION_MATERIAL_TYPES),
            "only_description_or_party": _cohort_count(rule_types, allowed=PRESENTATION_OR_PARTY_TYPES),
            "only_party": _cohort_count(rule_types, allowed=frozenset({"party"})),
        },
        "relationships": {
            "total_relationships": int(relationship.get("total_relationships") or 0),
            "failed_relationships": len(relationship_failures),
            "affected_rules": len(affected_relationship_rules),
            "overlap_with_failed_rules": len(affected_relationship_rules & set(failure_rule_ids)),
            "overlap_with_claim_failure_rules": len(affected_relationship_rules & claim_failure_rule_ids),
        },
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path, help="kg_grounding_report.json")
    parser.add_argument("--target-rate", type=float, default=10.0, help="maximum hold rate percentage")
    parser.add_argument("--output", type=Path, help="write JSON here instead of stdout")
    args = parser.parse_args(argv)

    report = json.loads(args.report.read_text(encoding="utf-8"))
    if not isinstance(report, Mapping):
        raise QualityBudgetError("grounding report must be a JSON object")
    summary = summarize_quality_budget(report, target_rate_percent=args.target_rate)
    summary["input"] = {"path": str(args.report), "sha256": _sha256(args.report)}
    rendered = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
