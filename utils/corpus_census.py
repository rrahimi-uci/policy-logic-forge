"""Corpus feature census (IR-2 in plan/tasks.json).

The compiler IR's supported type/operator subset must be frozen from a
*measurement* of what real v2 rule graphs actually contain, not from a guess
made before any measurement exists. Freezing first and measuring after is
exactly how the legacy research design's blocker was missed for two review passes:
refusing the `string` theory silently refuses 34 of the anchor's 58 testable
models (the Requirements half, where the anchor scores *higher*), which drops
the primary instrument-validation endpoint to n=24 -- a sample size at which
its own declared success criterion (rho >= 0.6, 95% CI lower bound > 0.3)
fails even at the true target effect.

This module is deliberately provider-free and dependency-free (no LLM calls,
no third-party libraries): it is pure aggregation over already-extracted v2
rule dicts, so it can run against any batch's
`optimized_compliance_knowledge_graph.json` (or an ``agent_05``
pre-optimization graph) with no API key and no network.  It also reports malformed or incomplete
contract fields instead of silently dropping them from the supported-subset
census.

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

The repository may retain aggregate reports from bounded local pilots, but it
does not vendor source corpora or pipeline output (see README.md "Data and
licensing"). A pilot report is evidence that the tool ran against real output;
it is not a corpus-wide estimate and must carry an explicit scope note.
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

# Fields whose presence is material to the IR-2 review.  Empty arrays are
# counted as present: ``exceptions: []`` and an omitted ``exceptions`` field
# have different provenance and readiness meanings in contract v2.
CENSUS_FIELDS = (
    "applicability_scope",
    "scope_basis",
    "recommended_hit_policy",
    "exceptions",
    "exception_basis",
    "test_vectors",
    "field_evidence",
    "source_reference",
    "condition_logic",
)

# A generated graph may carry dependencies on each rule (after agent_06) or a
# top-level dependency_details object.  The latter is intentionally measured by
# the CLI when loading a graph; these aliases cover rule-level handoffs and
# decision-table projections without assuming one producer's exact spelling.
DEPENDENCY_FIELDS = ("dependencies", "dependency_ids", "related_rules")
TABLE_FIELDS = ("decision_table", "table", "table_rows", "decision_table_rows")


def _rules_from_graph(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Read business_rules from an optimized (agent_06+) or raw (agent_03)
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


def _theories_required_for_coverage(rule: Mapping[str, Any]) -> set[str]:
    """Return every declared theory, retaining malformed declarations.

    Unknown or malformed variable types must become explicit refusals in a
    candidate subset check.  Silently dropping them would make an unsupported
    rule appear covered.
    """

    variables = rule.get("variables")
    if variables is None or variables == []:
        return set()
    if not isinstance(variables, list):
        return {"<malformed_variables>"}
    required: set[str] = set()
    for variable in variables:
        if not isinstance(variable, Mapping):
            required.add("<malformed_variable>")
            continue
        raw_type = variable.get("type")
        type_name = str(raw_type).strip() if raw_type is not None else ""
        required.add(type_name or "<missing_variable_type>")
    return required


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


def _categorical_census(rules: Iterable[Mapping[str, Any]], field: str) -> dict[str, int]:
    """Count values for a scalar rule field, retaining an explicit missing bucket."""
    counts: Counter[str] = Counter()
    for rule in rules:
        value = rule.get(field)
        key = "<missing>" if value is None or value == "" else str(value)
        counts[key] += 1
    return dict(sorted(counts.items()))


def scope_basis_census(rules: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Count final/candidate scope evidence states, including missing values."""
    return _categorical_census(rules, "scope_basis")


def exception_basis_census(rules: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Count exception evidence states, including explicit empty/missing states."""
    return _categorical_census(rules, "exception_basis")


def hit_policy_census(rules: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Count recommended decision-table hit policies, including missing values."""
    return _categorical_census(rules, "recommended_hit_policy")


def rule_type_census(rules: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Count domain rule types, retaining rules with no type as ``<missing>``."""
    return _categorical_census(rules, "rule_type")


def field_presence_census(rules: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """Report present/missing counts for fields that affect executability.

    Presence is key-based rather than truthiness-based, so an explicit empty
    list/object remains visible as an asserted value.  This is important for
    distinguishing ``exceptions: []`` from a model that omitted the field.
    """
    rules = list(rules)
    total = len(rules)
    report: dict[str, dict[str, int]] = {}
    for field in CENSUS_FIELDS:
        present = sum(1 for rule in rules if field in rule and rule.get(field) is not None)
        report[field] = {"present": present, "missing": total - present}
    return report


def _nonempty_field(rule: Mapping[str, Any], field: str) -> bool:
    """Whether a rule carries a non-empty dependency/table representation."""
    value = rule.get(field)
    if isinstance(value, (list, dict, str)):
        return bool(value)
    return value is not None


def dependency_census(rules: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Count rule-level dependency representations and directed edges.

    Top-level graph dependency metadata is handled by ``scripts/corpus_census``
    because this provider-free utility intentionally accepts only rule dicts.
    """
    rules = list(rules)
    represented = [rule for rule in rules if any(_nonempty_field(rule, field) for field in DEPENDENCY_FIELDS)]
    edge_count = 0
    for rule in rules:
        for field in DEPENDENCY_FIELDS:
            value = rule.get(field)
            if isinstance(value, list):
                edge_count += len(value)
            elif isinstance(value, dict):
                edge_count += len(value)
    return {
        "rules_with_dependencies": len(represented),
        "rules_without_dependencies": len(rules) - len(represented),
        "dependency_edges": edge_count,
    }


def table_census(rules: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Count rules carrying a non-empty decision-table projection."""
    rules = list(rules)
    represented = [rule for rule in rules if any(_nonempty_field(rule, field) for field in TABLE_FIELDS)]
    return {
        "rules_with_tables": len(represented),
        "rules_without_tables": len(rules) - len(represented),
    }


def contract_issue_census(rules: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Expose contract/review failures instead of excluding malformed rules.

    Invalid operators/value types are counted directly because older or
    provider-specific producers may not attach ``contract_issues``.  Attached
    issue codes and ``requires_review`` are also retained for triage.
    """
    rules = list(rules)
    issue_codes: Counter[str] = Counter()
    issue_severities: Counter[str] = Counter()
    invalid_predicate_operators = 0
    invalid_predicate_value_types = 0
    invalid_outcome_value_types = 0
    invalid_variable_types = 0
    malformed_variable_entries = 0
    invalid_variable_type_values: Counter[str] = Counter()
    for rule in rules:
        variables = rule.get("variables") or []
        if not isinstance(variables, list):
            malformed_variable_entries += 1
        else:
            for variable in variables:
                if not isinstance(variable, Mapping):
                    malformed_variable_entries += 1
                    continue
                if variable.get("type") not in VARIABLE_TYPES:
                    invalid_variable_types += 1
                    value = str(variable.get("type") or "<missing>")
                    invalid_variable_type_values[value] += 1
        for predicate in rule.get("condition_predicates") or []:
            if isinstance(predicate, Mapping):
                if predicate.get("operator") not in OPERATORS:
                    invalid_predicate_operators += 1
                if predicate.get("value_type") not in VALUE_TYPES:
                    invalid_predicate_value_types += 1
        for outcome in rule.get("outcomes") or []:
            if isinstance(outcome, Mapping) and outcome.get("value_type") not in VALUE_TYPES:
                invalid_outcome_value_types += 1
        issues = rule.get("contract_issues") or []
        if isinstance(issues, list):
            for issue in issues:
                if not isinstance(issue, Mapping):
                    continue
                issue_codes[str(issue.get("code") or "<missing>")] += 1
                issue_severities[str(issue.get("severity") or "<missing>")] += 1
    rules_with_issues = sum(bool(rule.get("contract_issues")) for rule in rules)
    rules_requiring_review = sum(rule.get("requires_review") is True for rule in rules)
    return {
        "rules_with_contract_issues": rules_with_issues,
        "rules_without_contract_issues": len(rules) - rules_with_issues,
        "rules_requiring_review": rules_requiring_review,
        "invalid_predicate_operators": invalid_predicate_operators,
        "invalid_predicate_value_types": invalid_predicate_value_types,
        "invalid_outcome_value_types": invalid_outcome_value_types,
        "invalid_variable_types": invalid_variable_types,
        "invalid_variable_type_values": dict(sorted(invalid_variable_type_values.items())),
        "malformed_variable_entries": malformed_variable_entries,
        "issue_codes": dict(sorted(issue_codes.items())),
        "issue_severities": dict(sorted(issue_severities.items())),
    }


def theories_required_by(rule: Mapping[str, Any]) -> set[str]:
    """The theories this rule needs, retaining malformed declarations.

    Used by `coverage_at_subset` to answer "if the compiler supports only
    subset S, how many rules lower without a refusal?" -- the question
    proposal §9.4 shows the whole primary endpoint depends on getting right
    *before* the subset is frozen, not after. Unknown types and malformed
    variable entries are returned as explicit markers so they cannot be
    mistaken for covered rules.
    """
    return _theories_required_for_coverage(rule)


def coverage_at_subset(rules: Iterable[Mapping[str, Any]], supported_theories: Iterable[str]) -> dict[str, Any]:
    """How many rules lower without a refusal under a candidate supported
    subset, and which ones are refused and why.

    This is the check proposal §9.4 and plan §3.6 both demand run *before*
    `SUPPORTED_THEORIES` is frozen: "the frozen subset must cover >= 55 of
    the 58 anchor models" was the plan's acceptance criterion for the Dutch
    corpus; this function is the general form of that check for any corpus.
    """
    supported = set(supported_theories) & VARIABLE_TYPES
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
        "rule_type_census": rule_type_census(rules),
        "variable_type_census": variable_type_census(rules),
        "value_type_census": value_type_census(rules),
        "operator_census": operator_census(rules),
        "scope_basis_census": scope_basis_census(rules),
        "exception_basis_census": exception_basis_census(rules),
        "hit_policy_census": hit_policy_census(rules),
        "field_presence_census": field_presence_census(rules),
        "dependency_census": dependency_census(rules),
        "table_census": table_census(rules),
        "contract_issue_census": contract_issue_census(rules),
        "expressiveness_signal": expressiveness_signal(rules),
    }
