"""IR-2 (plan/neurips-plan-2027.md §3.6): the corpus feature census must run
*before* the compiler's supported type/operator subset is frozen.

Proposal §9.4 shows what freezing-before-measuring costs: refusing the
`string` theory silently refuses 34 of the anchor's 58 testable models,
which drops the primary instrument-validation endpoint to n=24 -- a sample
size at which its own declared success criterion fails even at the true
target effect. `utils/corpus_census.py` is the tool that makes that kind of
blocker visible by measurement instead of by omission.

These tests exercise the census against synthetic v2 rule fixtures.  A bounded
local pilot may be retained as aggregate evidence, but it is not a substitute
for a full-corpus report or a coverage claim.
"""

import json

import pytest

from utils.corpus_census import (
    census_report,
    contract_issue_census,
    coverage_at_subset,
    dependency_census,
    field_presence_census,
    expressiveness_signal,
    exception_basis_census,
    hit_policy_census,
    load_rules,
    operator_census,
    scope_basis_census,
    table_census,
    theories_required_by,
    value_type_census,
    variable_type_census,
)


def _rule(rule_id="R1", variables=(), predicates=(), outcomes=(), text=""):
    return {
        "rule_id": rule_id,
        "rule_name": text,
        "description": text,
        "variables": list(variables),
        "condition_predicates": list(predicates),
        "outcomes": list(outcomes),
    }


def _var(name, type_, role="input"):
    return {"name": name, "type": type_, "role": role}


def _predicate(variable, operator, value_type):
    return {"predicate_id": f"p_{variable}", "variable": variable, "operator": operator, "value_type": value_type}


def _outcome(variable, value_type):
    return {"variable": variable, "operator": "=", "value_type": value_type}


# ─────────────────────────────────────────────────────────────────────────
# variable_type_census
# ─────────────────────────────────────────────────────────────────────────

def test_variable_type_census_counts_rules_not_occurrences():
    """Two boolean variables in one rule must count that rule once."""
    rules = [
        _rule("R1", variables=[_var("a", "boolean"), _var("b", "boolean")]),
        _rule("R2", variables=[_var("c", "string")]),
    ]
    counts = variable_type_census(rules)
    assert counts["boolean"] == 1
    assert counts["string"] == 1
    assert counts["number"] == 0


def test_variable_type_census_includes_every_v2_type_even_at_zero():
    """A type nobody uses must still appear at 0 -- silently omitting it
    would make "not measured" indistinguishable from "measured as zero"."""
    counts = variable_type_census([])
    assert counts["date"] == 0
    assert counts["duration"] == 0
    assert set(counts) == {"number", "boolean", "enum", "date", "date_time", "duration", "string", "list"}


def test_variable_type_census_a_rule_using_two_types_counts_in_both():
    rules = [_rule("R1", variables=[_var("a", "boolean"), _var("b", "string")])]
    counts = variable_type_census(rules)
    assert counts["boolean"] == 1
    assert counts["string"] == 1


def test_malformed_variables_are_ignored_not_fatal():
    rules = [_rule("R1", variables=["not-a-dict", {"name": "x"}, {"name": "y", "type": "not-a-real-type"}])]
    counts = variable_type_census(rules)
    assert sum(counts.values()) == 0


# ─────────────────────────────────────────────────────────────────────────
# value_type_census / operator_census
# ─────────────────────────────────────────────────────────────────────────

def test_value_type_census_reads_both_predicates_and_outcomes():
    rules = [_rule(
        "R1",
        predicates=[_predicate("x", "==", "number")],
        outcomes=[_outcome("y", "boolean")],
    )]
    counts = value_type_census(rules)
    assert counts["number"] == 1
    assert counts["boolean"] == 1
    assert counts["range"] == 0
    assert counts["variable_reference"] == 0


def test_operator_census_counts_each_operator_once_per_rule():
    rules = [_rule("R1", predicates=[
        _predicate("x", "==", "number"),
        _predicate("y", "==", "number"),   # same operator again -- still one rule
        _predicate("z", "in", "enum"),
    ])]
    counts = operator_census(rules)
    assert counts["=="] == 1
    assert counts["in"] == 1
    assert counts[">"] == 0


def test_metadata_censuses_retain_missing_values():
    rules = [_rule("R1", variables=[_var("a", "boolean")])]
    rules[0].update({
        "scope_basis": "explicit",
        "exception_basis": "explicitly_none_in_source",
        "recommended_hit_policy": "UNIQUE",
    })
    assert scope_basis_census(rules) == {"explicit": 1}
    assert exception_basis_census(rules) == {"explicitly_none_in_source": 1}
    assert hit_policy_census(rules) == {"UNIQUE": 1}
    assert scope_basis_census([_rule("missing")]) == {"<missing>": 1}


def test_field_presence_distinguishes_empty_arrays_from_omitted_fields():
    explicit_empty = _rule("R1")
    explicit_empty["exceptions"] = []
    omitted = _rule("R2")
    counts = field_presence_census([explicit_empty, omitted])
    assert counts["exceptions"] == {"present": 1, "missing": 1}


def test_dependency_and_table_censuses_count_nonempty_projections():
    rules = [_rule("R1"), _rule("R2")]
    rules[0]["dependencies"] = [{"depends_on_rule": "R2"}]
    rules[0]["table_rows"] = [{"when": "x", "then": "y"}]
    assert dependency_census(rules) == {
        "rules_with_dependencies": 1,
        "rules_without_dependencies": 1,
        "dependency_edges": 1,
    }
    assert table_census(rules) == {"rules_with_tables": 1, "rules_without_tables": 1}


def test_contract_issue_census_exposes_invalid_predicate_operator_and_review():
    rule = _rule(
        "R1",
        variables=[_var("x", "string")],
        predicates=[_predicate("x", "=", "string")],
    )
    rule.update({
        "requires_review": True,
        "contract_issues": [{"code": "invalid_predicate_operator", "severity": "error"}],
    })
    report = contract_issue_census([rule])
    assert report["invalid_predicate_operators"] == 1
    assert report["rules_with_contract_issues"] == 1
    assert report["rules_requiring_review"] == 1
    assert report["issue_codes"] == {"invalid_predicate_operator": 1}


# ─────────────────────────────────────────────────────────────────────────
# theories_required_by / coverage_at_subset — the §9.4 blocker, generalized
# ─────────────────────────────────────────────────────────────────────────

def test_theories_required_by_a_single_rule():
    rule = _rule("R1", variables=[_var("a", "boolean"), _var("b", "string")])
    assert theories_required_by(rule) == {"boolean", "string"}


def test_coverage_at_subset_reproduces_the_proposal_9_4_finding():
    """The exact shape of proposal §9.4's finding, at small scale: refusing
    `string` refuses every rule that needs it, and the refusal is named."""
    rules = [
        _rule("boolean_only", variables=[_var("a", "boolean")]),
        _rule("needs_string", variables=[_var("b", "string")]),
        _rule("needs_string_2", variables=[_var("c", "string"), _var("d", "boolean")]),
    ]

    without_string = coverage_at_subset(rules, {"boolean", "number", "enum"})
    assert without_string["covered_rules"] == 1
    assert without_string["coverage_fraction"] == pytest.approx(1 / 3)
    refused_ids = {r["rule_id"] for r in without_string["refused_rules"]}
    assert refused_ids == {"needs_string", "needs_string_2"}
    for entry in without_string["refused_rules"]:
        assert "string" in entry["missing_theories"]

    with_string = coverage_at_subset(rules, {"boolean", "string", "number", "enum"})
    assert with_string["covered_rules"] == 3
    assert with_string["coverage_fraction"] == 1.0
    assert with_string["refused_rules"] == []


def test_coverage_at_subset_on_empty_corpus_is_vacuously_complete():
    coverage = coverage_at_subset([], {"boolean"})
    assert coverage["total_rules"] == 0
    assert coverage["coverage_fraction"] == 1.0
    assert coverage["refused_rules"] == []


# ─────────────────────────────────────────────────────────────────────────
# expressiveness_signal
# ─────────────────────────────────────────────────────────────────────────

def test_expressiveness_signal_flags_deontic_modality():
    rules = [_rule("R1", text="The Recipient shall not disclose Confidential Information.")]
    signal = expressiveness_signal(rules)
    assert signal["bucket_counts"]["deontic_modality"] == 1
    assert signal["rules_matching_any_bucket"] == 1


def test_expressiveness_signal_flags_vague_standards():
    rules = [_rule("R1", text="The Servicer must use commercially reasonable efforts.")]
    signal = expressiveness_signal(rules)
    assert signal["bucket_counts"]["vague_standard"] == 1


def test_expressiveness_signal_flags_discretionary_authority():
    rules = [_rule("R1", text="The Lender may determine, in its sole discretion, whether to grant an exception.")]
    signal = expressiveness_signal(rules)
    assert signal["bucket_counts"]["discretionary_authority"] == 1


def test_expressiveness_signal_a_rule_can_hit_multiple_buckets():
    rules = [_rule("R1", text="The agreement shall expire on the effective date unless extended in the Lender's sole discretion, subject to a reasonable notice period.")]
    signal = expressiveness_signal(rules)
    hit_buckets = [b for b, count in signal["bucket_counts"].items() if count == 1]
    assert len(hit_buckets) >= 3
    assert signal["rules_matching_any_bucket"] == 1


def test_expressiveness_signal_a_clean_structured_rule_hits_nothing():
    rules = [_rule("R1", text="Credit score threshold check for loan eligibility.")]
    signal = expressiveness_signal(rules)
    assert signal["rules_matching_any_bucket"] == 0
    assert signal["fraction_matching_any_bucket"] == 0.0


def test_expressiveness_signal_on_empty_corpus_reports_zero_not_undefined():
    signal = expressiveness_signal([])
    assert signal["total_rules"] == 0
    assert signal["fraction_matching_any_bucket"] == 0.0


# ─────────────────────────────────────────────────────────────────────────
# census_report — the combined output the CLI script writes
# ─────────────────────────────────────────────────────────────────────────

def test_census_report_combines_coverage_and_failure_censuses():
    rules = [_rule(
        "R1",
        variables=[_var("a", "boolean")],
        predicates=[_predicate("a", "==", "boolean")],
        text="The Servicer shall notify the Borrower.",
    )]
    report = census_report(rules)
    assert report["total_rules"] == 1
    assert report["variable_type_census"]["boolean"] == 1
    assert report["value_type_census"]["boolean"] == 1
    assert report["operator_census"]["=="] == 1
    assert report["scope_basis_census"] == {"<missing>": 1}
    assert report["dependency_census"]["rules_without_dependencies"] == 1
    assert report["table_census"]["rules_without_tables"] == 1
    assert report["contract_issue_census"]["rules_without_contract_issues"] == 1
    assert report["expressiveness_signal"]["bucket_counts"]["deontic_modality"] == 1


# ─────────────────────────────────────────────────────────────────────────
# load_rules — reading both graph shapes (Agent 5 optimized vs Agent 3 raw)
# ─────────────────────────────────────────────────────────────────────────

def test_load_rules_reads_flat_business_rules_shape(tmp_path):
    graph = {"business_rules": [_rule("R1"), _rule("R2")]}
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(graph), encoding="utf-8")

    rules = load_rules(path)
    assert {r["rule_id"] for r in rules} == {"R1", "R2"}


def test_load_rules_reads_nested_entity_relationship_shape(tmp_path):
    """Agent 3's raw output nests rules under entity_types/relationships
    instead of a flat business_rules list -- cli/extract.py's own
    _count_business_rules has the same fallback for this reason."""
    graph = {
        "entity_types": {"BORROWER": {"business_rules": [_rule("R1")]}},
        "relationships": {"OWNS": {"business_rules": [_rule("R2")]}},
    }
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(graph), encoding="utf-8")

    rules = load_rules(path)
    assert {r["rule_id"] for r in rules} == {"R1", "R2"}


def test_load_rules_on_empty_graph_returns_empty_list(tmp_path):
    path = tmp_path / "graph.json"
    path.write_text(json.dumps({}), encoding="utf-8")
    assert load_rules(path) == []
