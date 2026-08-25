"""Corpus feature census (IR-2, plan/neurips-plan-2027.md §3.6).

The compiler IR's supported type/operator subset must be frozen from a
*measurement* of what real v2 rule graphs actually contain, not from a guess
made before any measurement exists. Freezing first and measuring after is
exactly how proposal §9.4's blocker was missed for two review passes:
refusing the `string` theory silently refuses 34 of the anchor's 58 testable
models (the Requirements half, where the anchor scores *higher*), which drops
the primary instrument-validation endpoint to n=24 -- a sample size at which
its own declared success criterion (rho >= 0.6, 95% CI lower bound > 0.3)
fails even at the true target effect.

This module is deliberately provider-free and dependency-free (no LLM calls,
no third-party libraries): it is pure aggregation over already-extracted v2
rule dicts, so it can run against any batch's
`optimized_compliance_knowledge_graph.json` (or an Agent-4 pre-optimization
graph) the moment one exists, with no API key and no network.

Two censuses, both returned by `census_report()`:

- **Type-theory census** (`variable_type_census`, `value_type_census`,
  `operator_census`): frequency of each v2 variable type, predicate/outcome
  value type, and comparison operator actually used. This is what a
  compiler's supported-subset decision should be measured against.
- **Expressiveness census** (`expressiveness_signal`): a coarse, keyword-based
  triage of how much of a rule's own text (`description`, `rule_name`)
  reads as needing deontic modality, temporal validity, an open-ended
  vague standard, or discretionary authority -- none of which a bounded
  decision-table semantics can carry (proposal §14.6). This is a triage
  signal for bounding ambition, not a legal classifier, and every function
  here says so in its own docstring rather than only here.

As of this commit, no real extraction has been run in this repository (see
README.md "Data and licensing" -- corpora are downloaded, not vendored, and
no committed pipeline output exists), so this module ships as a tool with
unit tests against synthetic v2 rule fixtures, not as a report against real
data. Running it against a real optimized graph is the literal next step
once one exists (see docs/theory_coverage.md once populated).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from utils.rule_contract import OPERATORS, VALUE_TYPES, VARIABLE_TYPES

# Coarse, deliberately conservative keyword buckets for the expressiveness
# census (proposal §14.6). A hit means the rule's own natural-language text
# CONTAINS wording associated with a phenomenon a decision-table semantics
# cannot carry -- it is a lower bound on how much content is inexpressible,
# never an exact count, and false negatives (wording the list misses) are
# expected and acceptable for a triage signal.
DEONTIC_MODALITY_KEYWORDS = (
    "shall", "must", " may ", "is prohibited", "is permitted", "is required",
    "is obligated", "has the right to", "is entitled to",
)
TEMPORAL_VALIDITY_KEYWORDS = (
    "effective date", "expires", "supersede", "sunset", "as of", "until such time",
    "no longer in effect", "superseded by",
)
VAGUE_STANDARD_KEYWORDS = (
    "reasonable", "material adverse", "substantially", "good faith",
    "commercially reasonable", "best efforts", "undue",
)
DISCRETIONARY_AUTHORITY_KEYWORDS = (
    "may determine", "in its discretion", "at its sole discretion",
    "as it deems", "in its sole judgment", "may waive",
)

EXPRESSIVENESS_BUCKETS = {
    "deontic_modality": DEONTIC_MODALITY_KEYWORDS,
    "temporal_validity": TEMPORAL_VALIDITY_KEYWORDS,
    "vague_standard": VAGUE_STANDARD_KEYWORDS,
    "discretionary_authority": DISCRETIONARY_AUTHORITY_KEYWORDS,
}


def _rules_from_graph(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Read business_rules from an optimized (Agent 5+) or raw (Agent 3)
    graph shape -- matching cli/extract.py's own `_count_business_rules`
    fallback so this tool works against either stage's output."""
    if isinstance(graph.get("business_rules"), list):
        return [r for r in graph["business_rules"] if isinstance(r, Mapping)]
    rules: list[dict[str, Any]] = []
    for bucket in ("entity_types", "relationships"):
        for entry in (graph.get(bucket) or {}).values():
            if isinstance(entry, Mapping):
                rules.extend(r for r in entry.get("business_rules", []) or [] if isinstance(r, Mapping))
    return rules


def load_rules(path: str | Path) -> list[dict[str, Any]]:
    """Load rules from one knowledge-graph JSON file on disk."""
    graph = json.loads(Path(path).read_text(encoding="utf-8"))
    return _rules_from_graph(graph)


def _rule_text(rule: Mapping[str, Any]) -> str:
    return " ".join(
        str(rule.get(field, "") or "") for field in ("rule_name", "description")
    ).lower()


def _variable_types_in_rule(rule: Mapping[str, Any]) -> set[str]:
    return {
        str(v.get("type"))
        for v in (rule.get("variables") or [])
        if isinstance(v, Mapping) and v.get("type") in VARIABLE_TYPES
    }


def variable_type_census(rules: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Count rules declaring at least one variable of each v2 type.

    A rule using both a `boolean` and a `string` variable counts once in
    each bucket -- this measures which *theories a compiler subset must
    support*, so a rule needing two theories should not be hideable by only
    counting its "primary" type.
    """
    counts: Counter[str] = Counter({t: 0 for t in VARIABLE_TYPES})
    for rule in rules:
        for t in _variable_types_in_rule(rule):
            counts[t] += 1
    return dict(counts)


def value_type_census(rules: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Count rules using each v2 predicate/outcome value_type at least once
    (the 10-type superset: the 8 variable types plus `range` and
    `variable_reference` -- see utils/rule_contract.py's VALUE_TYPES)."""
    counts: Counter[str] = Counter({t: 0 for t in VALUE_TYPES})
    for rule in rules:
        types_in_rule: set[str] = set()
        for predicate in (rule.get("condition_predicates") or []):
            if isinstance(predicate, Mapping) and predicate.get("value_type") in VALUE_TYPES:
                types_in_rule.add(predicate["value_type"])
        for outcome in (rule.get("outcomes") or []):
            if isinstance(outcome, Mapping) and outcome.get("value_type") in VALUE_TYPES:
                types_in_rule.add(outcome["value_type"])
        for t in types_in_rule:
            counts[t] += 1
    return dict(counts)


def operator_census(rules: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Count rules using each of the 8 v2 comparison operators at least once."""
    counts: Counter[str] = Counter({op: 0 for op in OPERATORS})
    for rule in rules:
        ops_in_rule = {
            p.get("operator")
            for p in (rule.get("condition_predicates") or [])
            if isinstance(p, Mapping) and p.get("operator") in OPERATORS
        }
        for op in ops_in_rule:
            counts[op] += 1
    return dict(counts)


def theories_required_by(rule: Mapping[str, Any]) -> set[str]:
    """The set of v2 variable types this single rule needs supported.

    Used by `coverage_at_subset` to answer "if the compiler supports only
    subset S, how many rules lower without a refusal?" -- the question
    proposal §9.4 shows the whole primary endpoint depends on getting right
    *before* the subset is frozen, not after.
    """
    return _variable_types_in_rule(rule)


def coverage_at_subset(rules: Iterable[Mapping[str, Any]], supported_theories: Iterable[str]) -> dict[str, Any]:
    """How many rules lower without a refusal under a candidate supported
    subset, and which ones are refused and why.

    This is the check proposal §9.4 and plan §3.6 both demand run *before*
    `SUPPORTED_THEORIES` is frozen: "the frozen subset must cover >= 55 of
    the 58 anchor models" was the plan's acceptance criterion for the Dutch
    corpus; this function is the general form of that check for any corpus.
    """
    supported = set(supported_theories)
    rules = list(rules)
    total = len(rules)
    refused: list[dict[str, Any]] = []
    for rule in rules:
        required = theories_required_by(rule)
        missing = required - supported
        if missing:
            refused.append({"rule_id": rule.get("rule_id"), "missing_theories": sorted(missing)})
    covered = total - len(refused)
    return {
        "supported_theories": sorted(supported),
        "total_rules": total,
        "covered_rules": covered,
        "coverage_fraction": (covered / total) if total else 1.0,
        "refused_rules": refused,
    }


def expressiveness_signal(rules: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Coarse, provider-free triage of source text needing modality,
    temporal validity, vague standards, or discretionary authority -- none
    of which a bounded decision-table semantics can express (proposal
    §14.6). Reports per-bucket rule counts and the fraction of rules
    matching at least one bucket; deliberately not a rule-content classifier
    or a legal determination of unexpressibility.
    """
    rules = list(rules)
    total = len(rules)
    bucket_counts: dict[str, int] = {name: 0 for name in EXPRESSIVENESS_BUCKETS}
    any_bucket = 0
    for rule in rules:
        text = _rule_text(rule)
        hit_any = False
        for bucket, keywords in EXPRESSIVENESS_BUCKETS.items():
            if any(keyword in text for keyword in keywords):
                bucket_counts[bucket] += 1
                hit_any = True
        if hit_any:
            any_bucket += 1
    return {
        "total_rules": total,
        "bucket_counts": bucket_counts,
        "rules_matching_any_bucket": any_bucket,
        "fraction_matching_any_bucket": (any_bucket / total) if total else 0.0,
    }


def census_report(rules: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The combined report `docs/theory_coverage.md` / `docs/expressiveness_census.md`
    (plan §3.6) are generated from."""
    rules = list(rules)
    return {
        "total_rules": len(rules),
        "variable_type_census": variable_type_census(rules),
        "value_type_census": value_type_census(rules),
        "operator_census": operator_census(rules),
        "expressiveness_signal": expressiveness_signal(rules),
    }
