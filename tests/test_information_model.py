"""Tests for utils/information_model.py — the Business Information Model core.

The requirement these protect is that attribute types are *business* types with
defensible evidence behind them, not a wall of ``String``. Declared facts (unit,
allowed values, range) must beat name guessing, name guessing must be flagged as
such, and nothing may be quietly filed under a class the evidence doesn't
support.
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.information_model import (  # noqa: E402
    ATTRIBUTE_CATEGORIES,
    Attribute,
    build_model,
    catalog_rows,
    categorise_attribute,
    collect_attributes,
    extract_enumerations,
    infer_business_type,
    model_inventory,
    pascal_case,
    reconcile_types,
    refines,
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
    assert row["constraints"] and row["source_rules"] == "R1"
    assert row["unit"] == "%"   # the declared unit survives into the catalog


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


# ---------------------------------------------------------------------------
# the agent's guards on model proposals
# ---------------------------------------------------------------------------

def _unassigned(symbol, type_="Boolean"):
    from utils.information_model import Attribute
    return Attribute(name=symbol, symbol=symbol, type=type_, type_basis="declared",
                     type_reason="test fixture")


def test_a_proposed_class_of_pure_compliance_flags_is_rejected():
    """A class whose attributes are all yes/no rule outcomes is not an entity.

    The prompt forbids this and a real run produced it anyway -- a `Lender`
    whose eight attributes all recorded whether a policy had been met. Those
    are evaluation results, not what a lender is, so the rule is enforced in
    code rather than hoped for in the prompt.
    """
    from agents.agent_12_business_information_model import _apply_assignments
    from utils.information_model import InformationModel

    model = InformationModel(unassigned=[_unassigned(f"flag_{i}") for i in range(4)])
    stats = _apply_assignments(model, [
        {"symbol": f"flag_{i}", "owner": None, "new_class": "Lender",
         "confidence": "clear", "reasoning": "r"} for i in range(4)
    ], concept_of={})

    assert stats["rejected_flag_class"] == 1
    assert [k.name for k in model.classes] == []
    assert len(model.unassigned) == 4
    assert all("compliance flags" in " ".join(a.review_reasons) for a in model.unassigned)


def test_a_proposed_class_with_real_business_state_is_accepted():
    from agents.agent_12_business_information_model import _apply_assignments
    from utils.information_model import InformationModel

    model = InformationModel(unassigned=[
        _unassigned("policy_number", "Identifier"),
        _unassigned("coverage_amount", "Money"),
        _unassigned("is_active"),
    ])
    stats = _apply_assignments(model, [
        {"symbol": s, "owner": None, "new_class": "InsurancePolicy",
         "confidence": "clear", "reasoning": "r"}
        for s in ("policy_number", "coverage_amount", "is_active")
    ], concept_of={})

    assert stats["rejected_flag_class"] == 0
    assert [k.name for k in model.classes] == ["InsurancePolicy"]
    assert model.unassigned == []


def test_a_proposal_naming_an_unknown_symbol_is_discarded():
    """The model may not introduce attributes that were never extracted."""
    from agents.agent_12_business_information_model import _apply_assignments
    from utils.information_model import InformationModel

    model = InformationModel(unassigned=[_unassigned("real_symbol")])
    stats = _apply_assignments(model, [
        {"symbol": "invented_symbol", "owner": None, "new_class": "X",
         "confidence": "clear", "reasoning": "r"}
    ], concept_of={})
    assert stats["rejected_unknown_symbol"] == 1
    assert len(model.unassigned) == 1


def test_an_unclear_verdict_leaves_the_attribute_unassigned_and_annotated():
    """Unplaced is a correct answer, and the reason travels with it."""
    from agents.agent_12_business_information_model import _apply_assignments
    from utils.information_model import InformationModel

    model = InformationModel(unassigned=[_unassigned("ambiguous")])
    stats = _apply_assignments(model, [
        {"symbol": "ambiguous", "owner": None, "new_class": None,
         "confidence": "unclear", "reasoning": "could belong to loan or property"}
    ], concept_of={})
    assert stats["unclear"] == 1 and len(model.unassigned) == 1
    assert "loan or property" in " ".join(model.unassigned[0].review_reasons)


def test_a_proposed_value_object_becomes_a_stereotyped_class():
    """A composite with no identity of its own is a value object, not an entity."""
    from agents.agent_12_business_information_model import _apply_assignments
    from utils.information_model import InformationModel, to_mermaid, to_plantuml

    model = InformationModel(unassigned=[
        _unassigned("street_line", "String"), _unassigned("postal_code", "String"),
    ])
    stats = _apply_assignments(model, [
        {"symbol": s, "owner": None, "new_class": None, "value_object": "Address",
         "confidence": "clear", "reasoning": "r"}
        for s in ("street_line", "postal_code")
    ], concept_of={})

    assert stats["value_objects"] == 1
    address = next(k for k in model.classes if k.name == "Address")
    assert address.stereotype == "value_object" and len(address.attributes) == 2
    assert model.unassigned == []
    assert "<<value_object>>" in to_mermaid(model)
    assert "<<value_object>>" in to_plantuml(model)


def test_a_single_component_value_object_is_refused():
    """Wrapping one attribute in a value object just adds a hop."""
    from agents.agent_12_business_information_model import _apply_assignments
    from utils.information_model import InformationModel

    model = InformationModel(unassigned=[_unassigned("street_line", "String")])
    stats = _apply_assignments(model, [
        {"symbol": "street_line", "owner": None, "value_object": "Address",
         "confidence": "clear", "reasoning": "r"}
    ], concept_of={})
    assert stats["value_objects"] == 0
    assert len(model.unassigned) == 1
    assert "too few components" in " ".join(model.unassigned[0].review_reasons)


# ---------------------------------------------------------------------------
# refinement vs contradiction
# ---------------------------------------------------------------------------

def test_refinement_is_not_a_contradiction():
    """Rules routinely describe the same symbol at different precisions.

    One names a closed value set, another calls it free text. The set loses
    nothing the text declared, so this is an under-specification to reconcile,
    not a disagreement to escalate.
    """
    assert refines("OccupancyType", "Text")       # an enumeration narrows free text
    assert refines("Identifier", "String")
    assert refines("Money", "Decimal")
    assert refines("Integer", "Decimal")


def test_types_in_different_families_never_refine_each_other():
    """The check has to stay narrow or it becomes a silent type-coercion pass."""
    assert not refines("Boolean", "Text")
    assert not refines("OccupancyType", "Boolean")
    assert not refines("Money", "Percentage")     # both decimal, neither narrower
    assert not refines("Percentage", "Money")
    assert not refines("Date", "Text")
    assert not refines("Money", "Money")          # a type does not refine itself


def test_reconcile_picks_the_narrowest_reading():
    assert reconcile_types(["OccupancyType", "Text"]) == "OccupancyType"
    assert reconcile_types(["Money", "Decimal"]) == "Money"
    assert reconcile_types(["Text"]) == "Text"
    assert reconcile_types(["Identifier", "Text", "String"]) == "Identifier"


def test_reconcile_refuses_when_the_rules_genuinely_disagree():
    assert reconcile_types(["Boolean", "ParentalConsent"]) is None
    assert reconcile_types(["Money", "Percentage"]) is None
    assert reconcile_types(["OccupancyType", "LoanPurpose"]) is None   # two closed sets
    assert reconcile_types([]) is None


def test_an_under_specified_declaration_is_reported_for_review_not_as_an_error():
    """This is the case that dominated real runs: 24 of 28 reported errors were
    a closed value set in one rule and a bare string in another."""
    rules = [
        _rule("R1", variables=[_var("occupancy_type", type="enum",
                                    allowed_values=["primary", "second"])]),
        _rule("R2", variables=[_var("occupancy_type", type="string", free_text=True)]),
    ]
    attributes, conflicts = collect_attributes({"business_rules": rules})
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict["level"] == "refinement"
    assert conflict["severity"] == "review"
    assert conflict["resolved_to"] == "OccupancyType"
    # and the narrower reading is the one the attribute actually gets
    assert attributes["occupancy_type"].type == "OccupancyType"


def test_the_narrow_reading_wins_regardless_of_declaration_order():
    """Ordering by evidence alone let a `string` beat the enumeration that
    refines it on tie-break, silently discarding a real constraint."""
    for order in ([0, 1], [1, 0]):
        rules = [
            _rule("R1", variables=[_var("occupancy_type", type="enum",
                                        allowed_values=["primary", "second"])]),
            _rule("R2", variables=[_var("occupancy_type", type="string", free_text=True)]),
        ]
        attributes, _ = collect_attributes({"business_rules": [rules[i] for i in order]})
        assert attributes["occupancy_type"].type == "OccupancyType"


def test_a_genuine_contradiction_is_still_an_error():
    rules = [
        _rule("R1", variables=[_var("parental_consent", type="enum",
                                    allowed_values=["given", "withheld"])]),
        _rule("R2", variables=[_var("parental_consent", type="boolean")]),
    ]
    _, conflicts = collect_attributes({"business_rules": rules})
    assert len(conflicts) == 1
    assert conflicts[0]["level"] == "contradiction"
    assert conflicts[0]["severity"] == "error"
    assert "resolved_to" not in conflicts[0]


def test_validation_reports_conflicts_at_the_severity_they_carry():
    """Exit code 3 keys off errors, so a refinement must not trigger it."""
    rules = [
        _rule("R1", variables=[_var("occupancy_type", type="enum",
                                    allowed_values=["primary", "second"])],
              entities=["LOAN"]),
        _rule("R2", variables=[_var("occupancy_type", type="string", free_text=True)],
              entities=["LOAN"]),
        _rule("R3", variables=[_var("parental_consent", type="enum",
                                    allowed_values=["given", "withheld"])], entities=["LOAN"]),
        _rule("R4", variables=[_var("parental_consent", type="boolean")], entities=["LOAN"]),
    ]
    graph = {"entity_types": {"LOAN": {"concept_kind": "business_object"}},
             "business_rules": rules}
    report = validate_model(build_model(graph, {}), graph, {})
    consistency = [f for f in report["findings"] if f["check"] == "type_consistency"]
    by_severity = {f["subject"]: f["severity"] for f in consistency}
    assert by_severity["occupancy_type"] == "review"
    assert by_severity["parental_consent"] == "error"
    assert "reconciled to OccupancyType" in next(
        f["detail"] for f in consistency if f["subject"] == "occupancy_type")


# ---------------------------------------------------------------------------
# high-level categories and the element inventory
# ---------------------------------------------------------------------------

def _attr(name, type_):
    return Attribute(name=name, symbol=name, type=type_, type_basis="declared", type_reason="t")


def test_every_business_type_lands_in_a_declared_category():
    for type_ in ("Money", "Percentage", "Quantity", "Integer", "Decimal",
                  "Date", "DateTime", "Time", "Duration", "Boolean",
                  "Text", "String", "Identifier", "SomeEnumeration"):
        assert categorise_attribute(_attr("x", type_)) in ATTRIBUTE_CATEGORIES


def test_categories_group_by_the_kind_of_value_held():
    assert categorise_attribute(_attr("a", "Money")) == "quantity"
    assert categorise_attribute(_attr("a", "Duration")) == "temporal"
    assert categorise_attribute(_attr("a", "Boolean")) == "flag"
    assert categorise_attribute(_attr("a", "Identifier")) == "identifier"
    assert categorise_attribute(_attr("a", "Text")) == "descriptive"
    # anything not a builtin or business type is a closed vocabulary
    assert categorise_attribute(_attr("a", "OccupancyType")) == "categorical"


def test_inventory_counts_every_element_kind():
    rules = [
        _rule("R1", entities=["LOAN"], variables=[
            _var("principal_amount", unit="usd"),
            _var("term_months", unit="months"),
            _var("occupancy_type", type="enum", allowed_values=["primary", "second"]),
            _var("eligible", type="boolean", role="output"),
        ], predicates=["principal_amount", "term_months", "occupancy_type"],
              outcomes=["eligible"]),
    ]
    graph = {"entity_types": {"LOAN": {"concept_kind": "business_object"}},
             "business_rules": rules}
    inventory = model_inventory(build_model(graph, {}))

    assert inventory["classes"]["total"] == 1
    assert inventory["classes"]["by_stereotype"] == {"entity": 1}
    categories = inventory["attributes"]["by_category"]
    assert categories["quantity"] == 1        # principal_amount
    assert categories["temporal"] == 1        # term_months
    assert categories["categorical"] == 1     # occupancy_type
    assert categories["flag"] == 1            # eligible
    assert inventory["attributes"]["total"] == 4
    assert set(categories) == set(ATTRIBUTE_CATEGORIES)


def test_inventory_separates_detected_enumerations_from_referenced_ones():
    """The schema drops enumerations no class references, so reporting only the
    total leaves the two artifacts disagreeing with no way to explain it."""
    rules = [
        _rule("R1", entities=["LOAN"], variables=[
            _var("occupancy_type", type="enum", allowed_values=["primary", "second"]),
        ], predicates=["occupancy_type"]),
        # declared by a rule naming no entity, so it cannot be assigned
        _rule("R2", variables=[
            _var("loan_purpose", type="enum", allowed_values=["purchase", "refinance"]),
        ], predicates=["loan_purpose"]),
    ]
    graph = {"entity_types": {"LOAN": {"concept_kind": "business_object"}},
             "business_rules": rules}
    enums = model_inventory(build_model(graph, {}))["enumerations"]
    assert enums["total"] == 2
    assert enums["referenced_by_a_class"] == 1
    assert enums["single_valued"] == 0


def test_inventory_flags_single_valued_enumerations():
    rules = [_rule("R1", entities=["LOAN"], variables=[
        _var("status", type="enum", allowed_values=["only"]),
    ], predicates=["status"])]
    graph = {"entity_types": {"LOAN": {"concept_kind": "business_object"}},
             "business_rules": rules}
    assert model_inventory(build_model(graph, {}))["enumerations"]["single_valued"] == 1


def test_the_validation_report_carries_the_inventory():
    graph = {"entity_types": {"LOAN": {"concept_kind": "business_object"}},
             "business_rules": [_rule("R1", entities=["LOAN"], variables=[
                 _var("principal_amount", unit="usd")], predicates=["principal_amount"])]}
    report = validate_model(build_model(graph, {}), graph, {})
    assert report["inventory"]["attributes"]["by_category"]["quantity"] == 1


def test_information_model_batches_run_concurrently_but_collect_in_source_order():
    from agents.agent_12_business_information_model import _assign_batches

    class Synthesiser:
        def __init__(self):
            self.lock = threading.Lock()
            self.active = 0
            self.max_active = 0

        def assign(self, batch, _class_names):
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            try:
                # Force later batches to complete first so output ordering is
                # verified independently from completion ordering.
                time.sleep(0.01 * (4 - batch[0]["index"]))
                return [{"index": batch[0]["index"]}]
            finally:
                with self.lock:
                    self.active -= 1

    synthesiser = Synthesiser()
    batches = [[{"index": index}] for index in range(4)]

    assignments = _assign_batches(synthesiser, batches, ["Loan"], workers=4)

    assert synthesiser.max_active > 1
    assert [item["index"] for item in assignments] == [0, 1, 2, 3]


def test_information_model_batch_failure_is_retried_sequentially(capsys):
    from agents.agent_12_business_information_model import _assign_batches

    class Synthesiser:
        def __init__(self):
            self.calls = {}

        def assign(self, batch, _class_names):
            index = batch[0]["index"]
            self.calls[index] = self.calls.get(index, 0) + 1
            if index == 1 and self.calls[index] == 1:
                raise RuntimeError("bad batch")
            return [{"index": index}]

    synthesiser = Synthesiser()
    assignments = _assign_batches(
        synthesiser, [[{"index": index}] for index in range(3)], ["Loan"], workers=3
    )

    assert [item["index"] for item in assignments] == [0, 1, 2]
    assert synthesiser.calls[1] == 2
    output = capsys.readouterr().out
    assert "batch 2/3 concurrent attempt failed; queued for sequential retry" in output
    assert "recovered batch 2/3 on sequential retry" in output


def test_information_model_persistent_batch_failure_is_isolated(capsys):
    from agents.agent_12_business_information_model import _assign_batches

    class Synthesiser:
        def assign(self, batch, _class_names):
            if batch[0]["index"] == 1:
                raise RuntimeError("persistently bad batch")
            return [{"index": batch[0]["index"]}]

    assignments = _assign_batches(
        Synthesiser(), [[{"index": index}] for index in range(3)], ["Loan"], workers=3
    )

    assert [item["index"] for item in assignments] == [0, 2]
    assert "batch 2/3 failed after sequential retry" in capsys.readouterr().out
