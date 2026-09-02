"""Tests for utils/linkml_schema.py — LinkML as the canonical model form.

The point of putting LinkML at the centre is that the model becomes something
that can be *validated* rather than merely inspected, and that every other
artifact is a projection of one source. These tests pin both: the emitted
schema loads through LinkML's own metamodel, and the diagram, JSON Schema and
catalog all read the same facts back out of it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.information_model import build_model  # noqa: E402
from utils.linkml_schema import (  # noqa: E402
    BUSINESS_TYPE_DEFINITIONS,
    catalog_rows,
    dump_yaml,
    to_json_schema,
    to_linkml,
    to_mermaid,
    to_plantuml,
    validate_schema,
)

_PROFILE = {"concepts": [
    {"concept_id": "MORTGAGE_LOAN", "concept_kind": "business_object", "definition": "A mortgage loan."},
    {"concept_id": "LENDER", "concept_kind": "actor_role", "definition": "A lender."},
]}


def _graph():
    return {
        "entity_types": {"MORTGAGE_LOAN": {"concept_kind": "business_object"},
                         "LENDER": {"concept_kind": "actor_role"}},
        "business_rules": [{
            "rule_id": "R1",
            "related_entities": ["MORTGAGE_LOAN"],
            "source_reference": {"chunk_path": "guide.txt", "section_id": "b2"},
            "variables": [
                {"name": "principal_amount", "type": "number", "role": "input", "unit": "usd"},
                {"name": "ltv_ratio", "type": "number", "role": "input", "unit": "percent",
                 "allowed_range": [0, 97]},
                {"name": "term_months", "type": "number", "role": "input", "unit": "months"},
                {"name": "occupancy_type", "type": "enum", "role": "input",
                 "allowed_values": ["primary", "second", "investment"]},
                {"name": "special_codes", "type": "list", "role": "input"},
                {"name": "eligible", "type": "boolean", "role": "output"},
            ],
            "condition_predicates": [
                {"predicate_id": "p1", "variable": "principal_amount", "operator": ">", "value": 0},
                {"predicate_id": "p2", "variable": "ltv_ratio", "operator": "<=", "value": 97},
                {"predicate_id": "p3", "variable": "term_months", "operator": "<=", "value": 360},
                {"predicate_id": "p4", "variable": "occupancy_type", "operator": "==", "value": "primary"},
            ],
            "outcomes": [{"variable": "eligible", "operator": "=", "value": True}],
        }],
    }


def _schema():
    return to_linkml(build_model(_graph(), _PROFILE), domain="mortgage")


# ---------------------------------------------------------------------------
# the schema is real LinkML, not YAML that resembles it
# ---------------------------------------------------------------------------

def test_the_emitted_schema_loads_through_linkmls_own_metamodel():
    """The easiest way for this stage to be quietly wrong is to emit plausible
    YAML that no LinkML tool will accept, so the schema is round-tripped."""
    assert validate_schema(_schema()) == []


def test_schema_declares_the_required_top_level_keys():
    schema = _schema()
    for key in ("id", "name", "prefixes", "default_prefix", "default_range", "imports"):
        assert key in schema, key
    assert "linkml:types" in schema["imports"]
    assert schema["default_prefix"] in schema["prefixes"]


def test_business_types_are_declared_as_real_types_anchored_to_builtins():
    """A consumer should see ``Money``, not ``float`` — but every generator
    still needs to know how to serialise it."""
    schema = _schema()
    assert "Money" in schema["types"] and schema["types"]["Money"]["typeof"] == "decimal"
    assert "Percentage" in schema["types"] and "Duration" in schema["types"]
    for definition in BUSINESS_TYPE_DEFINITIONS.values():
        assert definition["typeof"] in ("decimal", "string", "integer")


def test_only_the_types_actually_used_are_declared():
    """An unused type declaration is schema noise, and check 8 forbids it."""
    schema = _schema()
    assert "Quantity" not in schema["types"]


# ---------------------------------------------------------------------------
# the facts the goal asks for survive into the schema
# ---------------------------------------------------------------------------

def test_units_sit_on_the_slot_not_the_type():
    """Two Money attributes can be denominated differently, so folding the
    currency into the type would assert something the source never said."""
    loan = _schema()["classes"]["MortgageLoan"]["attributes"]
    assert loan["principalAmount"]["unit"]["symbol"] == "USD"
    assert loan["ltvRatio"]["unit"]["ucum_code"] == "%"
    assert loan["termMonths"]["unit"]["ucum_code"] == "mo"
    assert "unit" not in BUSINESS_TYPE_DEFINITIONS["Money"]


def test_numeric_bounds_become_minimum_and_maximum_value():
    ltv = _schema()["classes"]["MortgageLoan"]["attributes"]["ltvRatio"]
    assert ltv["minimum_value"] == 0 and ltv["maximum_value"] == 97


def test_required_and_multivalued_carry_multiplicity():
    loan = _schema()["classes"]["MortgageLoan"]["attributes"]
    assert loan["ltvRatio"]["required"] is True
    assert loan["specialCodes"]["multivalued"] is True
    assert not loan["eligible"].get("required")     # an outcome may be absent beforehand


def test_controlled_values_become_an_enum_range_with_permissible_values():
    schema = _schema()
    occupancy = schema["classes"]["MortgageLoan"]["attributes"]["occupancyType"]
    enum = schema["enums"][occupancy["range"]]
    assert set(v["title"] for v in enum["permissible_values"].values()) == {
        "primary", "second", "investment"}


def test_provenance_travels_with_every_slot():
    """A generated schema must still be traceable to the policy it came from."""
    slot = _schema()["classes"]["MortgageLoan"]["attributes"]["ltvRatio"]
    annotations = slot["annotations"]
    assert annotations["source_symbol"] == "ltv_ratio"
    assert "R1" in annotations["source_rules"]
    assert "guide.txt#b2" in annotations["source_passages"]
    assert annotations["type_basis"] == "declared"


def test_actor_classes_do_not_appear_when_they_own_nothing():
    assert "Lender" not in _schema()["classes"]


# ---------------------------------------------------------------------------
# projections agree with the canonical schema
# ---------------------------------------------------------------------------

def test_json_schema_carries_types_bounds_enums_and_required():
    payload = to_json_schema(_schema())
    body = str(payload)
    assert "MortgageLoan" in body
    assert "97" in body            # the maximum survived into JSON Schema
    assert "investment" in body    # the controlled vocabulary survived


def test_json_schema_is_produced_by_linkmls_own_generator():
    """``linkml`` is a declared dependency, so the real generator must run —
    the fallback exists only for a broken generator, never as the norm."""
    payload = to_json_schema(_schema())
    assert payload["x-generated-by"] == "linkml.generators.jsonschemagen"
    assert "x-fallback-reason" not in payload


def test_a_failed_generator_falls_back_but_says_so(monkeypatch):
    """A fallback that stayed silent would let the artifact claim to be
    LinkML's output when it is this module's approximation of it."""
    import builtins

    real_import = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name.startswith("linkml.generators"):
            raise ImportError("simulated: generator unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    payload = to_json_schema(_schema())
    assert payload["x-generated-by"] == "utils.linkml_schema fallback"
    assert "simulated: generator unavailable" in payload["x-fallback-reason"]
    assert "MortgageLoan" in payload["$defs"]      # still a usable schema
    assert payload["$defs"]["MortgageLoan"]["properties"]["ltvRatio"]["maximum"] == 97


def test_mermaid_renders_from_the_schema_with_types_and_stereotypes():
    diagram = to_mermaid(_schema())
    assert diagram.startswith("classDiagram")
    assert "class MortgageLoan {" in diagram
    assert "Money principalAmount" in diagram
    assert "<<enumeration>>" in diagram


def test_plantuml_is_well_formed_and_typed():
    diagram = to_plantuml(_schema())
    assert diagram.startswith("@startuml") and diagram.rstrip().endswith("@enduml")
    assert "principalAmount : Money" in diagram


def test_catalog_reads_the_same_facts_back_out_of_the_schema():
    """Catalog, diagram and JSON Schema are projections of one artifact, so a
    fact recorded once must appear identically in all of them."""
    rows = {r["attribute"]: r for r in catalog_rows(_schema())}
    ltv = rows["ltvRatio"]
    assert ltv["type"] == "Percentage" and ltv["unit"] == "%"
    assert ltv["constraints"] == [">= 0", "<= 97"]
    assert ltv["required"] and ltv["multiplicity"] == "1"
    assert rows["specialCodes"]["multiplicity"] == "0..*"
    assert set(rows["occupancyType"]["allowed_values"]) == {"primary", "second", "investment"}


def test_yaml_round_trips_to_the_same_schema():
    import yaml

    schema = _schema()
    assert yaml.safe_load(dump_yaml(schema)) == schema


def test_an_empty_model_still_produces_a_valid_schema():
    schema = to_linkml(build_model({"business_rules": []}, {}))
    assert validate_schema(schema) == []
    assert schema["classes"] == {}
