"""Tests for utils/information_model.py — the Business Information Model core.

The requirement these protect is that attribute types are *business* types with
defensible evidence behind them, not a wall of ``String``. Declared facts (unit,
allowed values, range) must beat name guessing, name guessing must be flagged as
such, and nothing may be quietly filed under a class the evidence doesn't
support.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.information_model import (  # noqa: E402
    build_model,
    catalog_rows,
    collect_attributes,
    extract_enumerations,
    infer_business_type,
    pascal_case,
    to_mermaid,
    to_plantuml,
    validate_model,
)


def _var(name, **kw):
    return {"name": name, "type": kw.pop("type", "number"), "role": kw.pop("role", "input"), **kw}


def _rule(rule_id, *, variables=(), predicates=(), outcomes=(), entities=()):
    return {
        "rule_id": rule_id,
        "variables": list(variables),
        "condition_predicates": [{"predicate_id": f"p{i}", "variable": v, "operator": "==", "value": True}
                                 for i, v in enumerate(predicates, 1)],
        "outcomes": [{"variable": v, "operator": "=", "value": True} for v in outcomes],
        "related_entities": list(entities),
        "source_reference": {"chunk_path": "policy.txt", "section_id": "s1"},
    }


# ---------------------------------------------------------------------------
# type inference — declared evidence beats names
# ---------------------------------------------------------------------------

def test_declared_currency_unit_yields_money():
    inference = infer_business_type(_var("some_opaque_name", unit="usd"))
    assert inference.type == "Money" and inference.basis == "declared"
    assert not inference.needs_review


def test_declared_percent_and_basis_points_yield_percentage():
    for unit in ("percent", "%", "ratio", "basis_points"):
        assert infer_business_type(_var("x", unit=unit)).type == "Percentage"


def test_declared_time_units_yield_duration():
    for unit in ("days", "business_days", "months", "years"):
        assert infer_business_type(_var("x", unit=unit)).type == "Duration"


def test_declared_unit_outranks_a_conflicting_name():
    """``..._days`` looks like a Duration, but a declared usd unit wins.

    Name patterns are the weakest signal available and must never override
    something the extractor actually read off the source.
    """
    inference = infer_business_type(_var("settlement_days", unit="usd"))
    assert inference.type == "Money" and inference.basis == "declared"


def test_a_periodic_monetary_unit_is_flagged_as_a_rate():
    """``usd_per_month`` is Money, but collapsing away the period loses meaning."""
    inference = infer_business_type(_var("gross_monthly_rent", unit="usd_per_month"))
    assert inference.type == "Money" and inference.needs_review
    assert "rate" in inference.reason


def test_allowed_values_make_an_enumeration_even_when_declared_string():
    """A string with a closed value set is a loosely-typed enumeration.

    Modelling it as text would discard a real business constraint.
    """
    inference = infer_business_type(_var("occupancy_type", type="string",
                                         allowed_values=["primary", "second", "investment"]))
    assert inference.type == "OccupancyType" and inference.basis == "declared"


def test_integral_range_yields_integer_without_a_unit():
    inference = infer_business_type(_var("unit_count", type="number", allowed_range=[1, 4]))
    assert inference.type == "Integer" and inference.basis == "derived"


def test_name_based_inference_is_marked_for_review():
    inference = infer_business_type(_var("origination_fee_amount", type="number"))
    assert inference.type == "Money" and inference.basis == "heuristic"
    assert inference.needs_review


def test_an_unevidenced_string_is_never_quietly_accepted():
    """The single likeliest modelling mistake, so it is always surfaced."""
    inference = infer_business_type(_var("free_form_note", type="string"))
    assert inference.type == "String" and inference.basis == "fallback"
    assert inference.needs_review


def test_declared_free_text_is_text_not_a_bare_string():
    inference = infer_business_type(_var("comment", type="string", free_text=True))
    assert inference.type == "Text" and inference.basis == "declared"


# ---------------------------------------------------------------------------
# collection, enumerations, constraints
# ---------------------------------------------------------------------------

def test_conflicting_declarations_are_reported_not_reconciled():
    """Two rules typing the same symbol differently is a real disagreement.

    Picking a winner silently would hide an extraction defect.
    """
    rules = [
        _rule("R1", variables=[_var("ltv_ratio", unit="percent")]),
        _rule("R2", variables=[_var("ltv_ratio", type="string")]),
    ]
    _, conflicts = collect_attributes({"business_rules": rules})
    assert len(conflicts) == 1 and conflicts[0]["symbol"] == "ltv_ratio"


def test_strongest_evidence_wins_when_declarations_disagree():
    rules = [
        _rule("R1", variables=[_var("ltv_ratio", type="string")]),
        _rule("R2", variables=[_var("ltv_ratio", unit="percent")]),
    ]
    attributes, _ = collect_attributes({"business_rules": rules})
    assert attributes["ltv_ratio"].type == "Percentage"


def test_required_reflects_whether_a_rule_tests_the_attribute():
    """A rule cannot be evaluated without the values it tests; an outcome may
    legitimately be absent beforehand."""
    rules = [_rule("R1", variables=[_var("a"), _var("b", role="output")],
                   predicates=["a"], outcomes=["b"])]
    attributes, _ = collect_attributes({"business_rules": rules})
    assert attributes["a"].required and attributes["a"].multiplicity == "1"
    assert not attributes["b"].required and attributes["b"].multiplicity == "0..1"


def test_a_list_typed_variable_becomes_a_many_multiplicity():
    rules = [_rule("R1", variables=[_var("codes", type="list")])]
    attributes, _ = collect_attributes({"business_rules": rules})
    assert attributes["codes"].multiplicity == "0..*"


def test_range_and_value_constraints_reach_the_attribute():
    rules = [_rule("R1", variables=[
        _var("ltv_ratio", unit="percent", allowed_range=[0, 97]),
        _var("occupancy", type="enum", allowed_values=["primary", "second"]),
    ])]
    attributes, _ = collect_attributes({"business_rules": rules})
    kinds = {c.kind for c in attributes["ltv_ratio"].constraints}
    assert "range" in kinds
    assert any(c.kind == "allowed_values" for c in attributes["occupancy"].constraints)


def test_identical_value_sets_share_one_enumeration():
    """Two attributes constraining the same set describe one vocabulary."""
    rules = [_rule("R1", variables=[
        _var("occupancy_type", type="enum", allowed_values=["primary", "second"]),
        _var("borrower_occupancy_type", type="enum", allowed_values=["second", "primary"]),
    ])]
    attributes, _ = collect_attributes({"business_rules": rules})
    enums = extract_enumerations(attributes)
    assert len(enums) == 1
    name = next(iter(enums))
    assert attributes["occupancy_type"].type == name
    assert attributes["borrower_occupancy_type"].type == name


# ---------------------------------------------------------------------------
# class assignment
# ---------------------------------------------------------------------------

_PROFILE = {"concepts": [
    {"concept_id": "MORTGAGE_LOAN", "concept_kind": "business_object", "definition": "A loan."},
    {"concept_id": "LENDER", "concept_kind": "actor_role", "definition": "A lender."},
]}


def test_actors_do_not_absorb_the_attributes_of_rules_they_perform():
    """A lender applies the rule; the loan holds the ratio.

    Without this, whichever actor appears most often accumulates nearly every
    attribute and the model stops being a domain model.
    """
    graph = {
        "business_rules": [_rule("R1", variables=[_var("ltv_ratio", unit="percent")],
                                 entities=["MORTGAGE_LOAN", "LENDER"])],
        "entity_types": {"MORTGAGE_LOAN": {"concept_kind": "business_object"},
                         "LENDER": {"concept_kind": "actor_role"}},
    }
    model = build_model(graph, _PROFILE)
    owners = {k.name: [a.symbol for a in k.attributes] for k in model.classes}
    assert owners.get("MortgageLoan") == ["ltv_ratio"]
    assert "Lender" not in owners


def test_an_attribute_no_business_object_claims_is_left_unassigned():
    """Unplaced is a correct answer; misfiled is not."""
    graph = {
        "business_rules": [_rule("R1", variables=[_var("x", unit="usd")], entities=["LENDER"])],
        "entity_types": {"LENDER": {"concept_kind": "actor_role"}},
    }
    model = build_model(graph, _PROFILE)
    assert [a.symbol for a in model.unassigned] == ["x"]


def test_screaming_snake_concepts_become_readable_class_names():
    assert pascal_case("MORTGAGE_BACKED_SECURITY") == "MortgageBackedSecurity"
    assert pascal_case("occupancy_type") == "OccupancyType"


# ---------------------------------------------------------------------------
# rendering and validation
# ---------------------------------------------------------------------------

def _sample_model():
    graph = {
        "business_rules": [_rule("R1", variables=[
            _var("ltv_ratio", unit="percent", allowed_range=[0, 97]),
            _var("occupancy_type", type="enum", allowed_values=["primary", "second"]),
        ], predicates=["ltv_ratio"], entities=["MORTGAGE_LOAN"])],
        "entity_types": {"MORTGAGE_LOAN": {"concept_kind": "business_object"}},
    }
    return graph, build_model(graph, _PROFILE)


def test_mermaid_carries_types_multiplicity_and_enumerations():
    _, model = _sample_model()
    diagram = to_mermaid(model)
    assert diagram.startswith("classDiagram")
    assert "class MortgageLoan {" in diagram
    assert "<<enumeration>>" in diagram
    assert "Percentage" in diagram


def test_plantuml_is_well_formed_and_typed():
    _, model = _sample_model()
    diagram = to_plantuml(model)
    assert diagram.startswith("@startuml") and diagram.rstrip().endswith("@enduml")
    assert "ltvRatio : Percentage" in diagram


def test_catalog_row_carries_type_multiplicity_constraints_and_sources():
    _, model = _sample_model()
    row = next(r for r in catalog_rows(model) if r["attribute"] == "ltvRatio")
    assert row["type"] == "Percentage" and row["multiplicity"] == "1" and row["required"]
    assert row["constraints"] and row["source_rule_ids"] == ["R1"]


def test_validation_reports_every_check_and_repairs_nothing():
    graph, model = _sample_model()
    before = [a.type for k in model.classes for a in k.attributes]
    report = validate_model(model, graph, _PROFILE)
    assert len(report["checks"]) == 10
    assert set(report["counts"]["by_check"]) == set(report["checks"])
    assert [a.type for k in model.classes for a in k.attributes] == before


def test_validation_flags_a_type_that_rests_on_no_declared_evidence():
    graph = {
        "business_rules": [_rule("R1", variables=[_var("mystery", type="string")],
                                 predicates=["mystery"], entities=["MORTGAGE_LOAN"])],
        "entity_types": {"MORTGAGE_LOAN": {"concept_kind": "business_object"}},
    }
    model = build_model(graph, _PROFILE)
    report = validate_model(model, graph, _PROFILE)
    assert any(f["check"] == "type_defensibility" for f in report["findings"])


def test_validation_flags_a_controlled_vocabulary_left_as_a_primitive():
    """Check 6: an attribute with permitted values must be an enumeration."""
    graph, model = _sample_model()
    attribute = model.classes[0].attributes[0]
    attribute.allowed_values = ("a", "b")
    attribute.type = "String"
    report = validate_model(model, graph, _PROFILE)
    assert any(f["check"] == "enumeration_usage" and f["severity"] == "error"
               for f in report["findings"])


def test_empty_graph_produces_an_empty_model_rather_than_failing():
    model = build_model({"business_rules": []}, {})
    assert model.as_dict()["counts"]["classes"] == 0
    assert to_mermaid(model).startswith("classDiagram")
