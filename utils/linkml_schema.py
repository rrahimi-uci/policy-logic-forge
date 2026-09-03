"""LinkML as the canonical form of the Business Information Model.

Everything the model can say -- classes, typed attributes, enumerations,
multiplicity, optionality, ranges, units, defaults, and provenance -- is
expressed once, as a LinkML schema.  Every other artifact is generated *from*
that schema rather than rendered independently, so the JSON Schema, the class
diagram, and the catalog cannot drift from each other or from the model.

Why LinkML rather than a bespoke JSON shape plus a hand-written diagram:

* It is a real schema language with a published metamodel, so the output can be
  **validated** instead of merely hoped correct -- :func:`validate_schema` runs
  the emitted schema through LinkML's own loader.
* Its generator ecosystem already produces JSON Schema, SHACL, OWL, SQL DDL,
  Pydantic/TypeScript/Java, GraphQL and documentation.  Those become
  regeneration commands rather than emitters this repository has to write and
  keep correct.
* It carries the things a policy-derived model actually needs and a plain class
  diagram cannot hold: units on slots, permissible values with descriptions,
  numeric bounds, and arbitrary annotations for source-rule provenance.

Unit placement is deliberate.  ``unit`` sits on the *slot*, never on the type,
because two ``Money`` attributes can legitimately be denominated differently;
folding the currency into the type would assert something the source never
said.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

__all__ = [
    "BUSINESS_TYPE_DEFINITIONS",
    "UNIT_ENCODINGS",
    "SUBSET_DESCRIPTIONS",
    "to_linkml",
    "dump_yaml",
    "validate_schema",
    "to_json_schema",
    "to_mermaid",
    "to_plantuml",
    "catalog_rows",
]

SCHEMA_ID_BASE = "https://github.com/rrahimi-uci/policy-logic-forge/information-model"

#: The high-level categories the model is partitioned into, emitted as LinkML
#: ``subsets`` -- the metamodel's own mechanism for grouping elements, so the
#: grouping survives into generated documentation and every downstream tool
#: rather than living only in this repository's reading of the model.
#:
#: Classes are grouped by what kind of thing they are; attributes by what kind
#: of value they hold. Both axes are derived from evidence the rules declare,
#: which is why they mean the same thing in any domain.
SUBSET_DESCRIPTIONS: dict[str, str] = {
    # class stereotypes
    "entity": "Things the business keeps state about and can identify.",
    "actor": "Parties that act on or are governed by the policy.",
    "event": "Things that happen at a point in time.",
    "process": "Ordered work the policy prescribes.",
    "value_object": "Composite values with no identity of their own.",
    # attribute categories
    "identifier": "Attributes that name or reference something.",
    "quantity": "Measured or counted values, including amounts, rates and ratios.",
    "temporal": "Points in time and durations.",
    "categorical": "Values drawn from a controlled vocabulary.",
    "flag": "Boolean state, most often the outcome of evaluating a rule.",
    "descriptive": "Free text carrying no further declared structure.",
}

#: The business types the deterministic layer assigns, declared as real LinkML
#: types so a consumer sees ``Money`` rather than ``float``.  ``typeof`` keeps
#: them anchored to a builtin, so every downstream generator still knows how to
#: serialise and validate them.
BUSINESS_TYPE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "Money": {"typeof": "decimal", "description":
              "A monetary amount. The denominating currency is carried by the slot's unit, "
              "not by this type, because two monetary attributes need not share a currency."},
    "Percentage": {"typeof": "decimal", "description":
                   "A proportion expressed as a percentage, ratio, or basis points, "
                   "as recorded by the slot's unit."},
    "Duration": {"typeof": "decimal", "description":
                 "An elapsed quantity of time, in the unit recorded on the slot."},
    "Quantity": {"typeof": "decimal", "description": "A counted or measured amount."},
    "Identifier": {"typeof": "string", "description":
                   "A business identifier for an entity, not a database key."},
    "Text": {"typeof": "string", "description": "Free-form business prose."},
}

#: Builtin LinkML types the model maps onto directly.
_BUILTIN_TYPES = {
    "Boolean": "boolean", "Integer": "integer", "Decimal": "decimal",
    "Date": "date", "DateTime": "datetime", "Time": "time", "String": "string",
}

#: How a declared unit is expressed as a LinkML ``UnitOfMeasure``. UCUM codes
#: are used where one genuinely exists; everything else carries a ``symbol``,
#: which satisfies the metamodel's requirement that a unit identify itself.
UNIT_ENCODINGS: dict[str, dict[str, str]] = {
    "usd": {"symbol": "USD", "descriptive_name": "US dollars"},
    "eur": {"symbol": "EUR", "descriptive_name": "euros"},
    "gbp": {"symbol": "GBP", "descriptive_name": "pounds sterling"},
    "currency": {"symbol": "currency", "descriptive_name": "an unspecified currency"},
    "usd_per_month": {"symbol": "USD/mo", "descriptive_name": "US dollars per month"},
    "percent": {"ucum_code": "%", "symbol": "%"},
    "%": {"ucum_code": "%", "symbol": "%"},
    "percentage": {"ucum_code": "%", "symbol": "%"},
    "ratio": {"ucum_code": "1", "symbol": "ratio", "descriptive_name": "a dimensionless ratio"},
    "basis_points": {"symbol": "bp", "descriptive_name": "basis points (one hundredth of a percent)"},
    "bps": {"symbol": "bp", "descriptive_name": "basis points"},
    "days": {"ucum_code": "d", "symbol": "days"},
    "business_days": {"symbol": "business days"},
    "months": {"ucum_code": "mo", "symbol": "months"},
    "years": {"ucum_code": "a", "symbol": "years"},
    "weeks": {"ucum_code": "wk", "symbol": "weeks"},
    "hours": {"ucum_code": "h", "symbol": "hours"},
    "count": {"ucum_code": "1", "symbol": "count"},
    "units": {"ucum_code": "1", "symbol": "units"},
    "loans": {"symbol": "loans"},
    "requests": {"symbol": "requests"},
}


def _safe(name: Any) -> str:
    """A LinkML-safe element name: letters, digits and underscores."""
    text = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in str(name or ""))
    return text.strip("_") or "unnamed"


def _bounds(attribute: Any) -> tuple[Any, Any]:
    """Pull numeric bounds out of the attribute's range constraint."""
    low = high = None
    for constraint in getattr(attribute, "constraints", ()):
        if constraint.kind != "range":
            continue
        for part in constraint.expression.split(" and "):
            tokens = part.strip().split()
            if len(tokens) == 3 and tokens[1] in (">=", "<="):
                try:
                    value = float(tokens[2])
                except ValueError:
                    continue
                value = int(value) if value == int(value) else value
                if tokens[1] == ">=":
                    low = value
                else:
                    high = value
    return low, high


def _ifabsent(default: Any) -> str | None:
    """LinkML's ``ifabsent`` encoding for a simple default value."""
    if default is None:
        return None
    if isinstance(default, bool):
        return "true" if default else "false"
    if isinstance(default, int) and not isinstance(default, bool):
        return f"int({default})"
    if isinstance(default, float):
        return f"float({default})"
    if isinstance(default, str) and default:
        return f"string({default})"
    return None


def to_linkml(
    model: Any,
    *,
    name: str = "business_information_model",
    domain: str = "",
    description: str = "",
) -> dict[str, Any]:
    """Express an :class:`InformationModel` as a LinkML schema dictionary."""
    prefix = _safe(name)
    schema: dict[str, Any] = {
        "id": f"{SCHEMA_ID_BASE}/{_safe(domain) or prefix}",
        "name": prefix,
        "title": f"Business information model{f' — {domain}' if domain else ''}",
        "description": description or (
            "Business information model derived from a grounding-certified policy "
            "knowledge graph. Attribute types, units, permissible values, bounds and "
            "multiplicity are derived from what the source rules declare; the class each "
            "attribute belongs to is a modelling judgment, recorded with its evidence."
        ),
        "license": "https://spdx.org/licenses/MIT.html",
        "prefixes": {
            "linkml": "https://w3id.org/linkml/",
            prefix: f"{SCHEMA_ID_BASE}/{_safe(domain) or prefix}/",
        },
        "default_prefix": prefix,
        "default_range": "string",
        "imports": ["linkml:types"],
        "subsets": {},
        "types": {},
        "enums": {},
        "classes": {},
    }

    from utils.information_model import categorise_attribute

    used_subsets: set[str] = set()

    # Only declare the business types the model actually uses.
    used_types = {a.type for k in model.classes for a in k.attributes}
    for type_name, definition in BUSINESS_TYPE_DEFINITIONS.items():
        if type_name in used_types:
            schema["types"][type_name] = dict(definition)

    for enum_name, enumeration in sorted(model.enumerations.items()):
        if enum_name not in used_types:
            continue                    # an enumeration nothing references is noise
        schema["enums"][_safe(enum_name)] = {
            "description": (
                f"Controlled vocabulary observed on "
                f"{', '.join(enumeration.source_symbols[:3])}"
                f"{' and others' if len(enumeration.source_symbols) > 3 else ''}."
            ),
            "permissible_values": {
                _safe(value): {"title": str(value)} for value in enumeration.values
            },
        }

    for klass in model.classes:
        attributes: dict[str, Any] = {}
        for attribute in klass.attributes:
            slot: dict[str, Any] = {}
            range_name = attribute.type
            slot["range"] = _BUILTIN_TYPES.get(range_name, _safe(range_name))
            if attribute.required:
                slot["required"] = True
            if attribute.multiplicity.endswith("*"):
                slot["multivalued"] = True
            low, high = _bounds(attribute)
            if low is not None:
                slot["minimum_value"] = low
            if high is not None:
                slot["maximum_value"] = high
            unit = UNIT_ENCODINGS.get(attribute.unit)
            if unit:
                slot["unit"] = dict(unit)
            ifabsent = _ifabsent(attribute.default)
            if ifabsent:
                slot["ifabsent"] = ifabsent
            slot["description"] = (
                f"{attribute.type_reason.capitalize()}."
                if attribute.type_reason else f"Business attribute {attribute.symbol}."
            )
            # Provenance and review state travel with the slot so a generated
            # schema can still be traced back to the policy text it came from.
            annotations: dict[str, Any] = {
                "source_symbol": attribute.symbol,
                "type_basis": attribute.type_basis,
            }
            if attribute.source_rule_ids:
                annotations["source_rules"] = ", ".join(attribute.source_rule_ids[:8])
            if attribute.source_passages:
                annotations["source_passages"] = ", ".join(attribute.source_passages[:4])
            if attribute.needs_review:
                annotations["needs_review"] = "true"
                if attribute.review_reasons:
                    annotations["review_reasons"] = "; ".join(attribute.review_reasons)
            slot["annotations"] = annotations
            slot["in_subset"] = [categorise_attribute(attribute)]
            used_subsets.add(categorise_attribute(attribute))
            attributes[_safe(attribute.name)] = slot

        entry: dict[str, Any] = {
            "description": klass.description or f"Business entity {klass.concept_id}.",
            "in_subset": [klass.stereotype],
            "attributes": attributes,
        }
        used_subsets.add(klass.stereotype)
        annotations = {"concept_id": klass.concept_id, "stereotype": klass.stereotype}
        if klass.source_passages:
            annotations["source_passages"] = ", ".join(klass.source_passages[:4])
        if klass.needs_review:
            annotations["needs_review"] = "true"
            if klass.review_reasons:
                annotations["review_reasons"] = "; ".join(klass.review_reasons)
        entry["annotations"] = annotations
        schema["classes"][_safe(klass.name)] = entry

    # Associations become slots on the source class: LinkML models a
    # relationship as a slot whose range is another class, which is also what
    # makes the generated JSON Schema and SQL DDL come out right.
    for relationship in model.relationships:
        source = _safe(relationship.source)
        target = _safe(relationship.target)
        if source not in schema["classes"] or target not in schema["classes"]:
            continue
        slot_name = _safe(relationship.verb) or f"related_{target.lower()}"
        schema["classes"][source]["attributes"][slot_name] = {
            "range": target,
            "multivalued": relationship.target_multiplicity.endswith("*"),
            "required": relationship.source_multiplicity.startswith("1"),
            "description": f"{relationship.source} {relationship.verb} {relationship.target}.",
            "in_subset": ["identifier"],
            "annotations": {
                "element_kind": "relationship",
                "relationship_kind": relationship.kind,
                "basis": relationship.basis,
                "needs_review": "true" if relationship.needs_review else "false",
                "review_reasons": (
                    "cardinality is a stated default: SBVR fact types record direction but "
                    "never multiplicity" if relationship.needs_review else ""
                ),
            },
        }
        used_subsets.add("identifier")

    # Declare only the subsets the model actually populates: an empty grouping
    # is a category the reader would look for and never find.
    for subset in sorted(used_subsets):
        schema["subsets"][subset] = {
            "description": SUBSET_DESCRIPTIONS.get(subset, f"Elements categorised as {subset}."),
        }
    return schema


def dump_yaml(schema: Mapping[str, Any]) -> str:
    """Serialise the schema as LinkML's canonical YAML."""
    import yaml

    return yaml.safe_dump(dict(schema), sort_keys=False, allow_unicode=True, width=100)


def validate_schema(schema: Mapping[str, Any]) -> list[str]:
    """Load the schema through LinkML itself; return problems, empty when valid.

    Emitting YAML that merely looks like LinkML would be the easiest place for
    this whole stage to be quietly wrong, so the schema is round-tripped through
    the real metamodel rather than trusted.
    """
    try:
        from linkml_runtime.utils.schemaview import SchemaView
    except ImportError:
        return ["linkml-runtime is not installed; schema was emitted but not validated"]
    try:
        view = SchemaView(dump_yaml(schema))
        view.all_classes()
        view.all_enums()
        view.all_types()
    except Exception as exc:
        return [f"{type(exc).__name__}: {exc}"]
    return []


# ---------------------------------------------------------------------------
# projections generated from the canonical schema
# ---------------------------------------------------------------------------

_JSON_TYPES = {
    "boolean": "boolean", "integer": "integer", "decimal": "number",
    "float": "number", "double": "number", "string": "string",
    "date": "string", "datetime": "string", "time": "string", "uri": "string",
}
_JSON_FORMATS = {"date": "date", "datetime": "date-time", "time": "time", "uri": "uri"}


def to_json_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """A JSON Schema for the model, derived from the LinkML schema.

    Uses LinkML's own generator so the output tracks the language rather than
    this repository's reading of it. A direct translation of the same schema
    stands in if the generator is unavailable or fails — which keeps a run
    producing artifacts, so the payload records under ``x-generated-by`` which
    path produced it and a fallback names the reason. A silent fallback would
    let this file quietly claim to be LinkML's output when it is ours.
    """
    try:
        from linkml.generators.jsonschemagen import JsonSchemaGenerator

        import json as _json
        payload = _json.loads(JsonSchemaGenerator(dump_yaml(schema)).serialize())
        payload["x-generated-by"] = "linkml.generators.jsonschemagen"
        return payload
    except Exception as exc:      # generator absent, or broken on this schema
        fallback_reason = f"{type(exc).__name__}: {exc}"

    definitions: dict[str, Any] = {}
    for enum_name, enum in (schema.get("enums") or {}).items():
        definitions[enum_name] = {
            "type": "string",
            "enum": [v.get("title", k) for k, v in (enum.get("permissible_values") or {}).items()],
            "description": enum.get("description", ""),
        }
    for class_name, klass in (schema.get("classes") or {}).items():
        properties: dict[str, Any] = {}
        required: list[str] = []
        for slot_name, slot in (klass.get("attributes") or {}).items():
            rng = slot.get("range", "string")
            if rng in (schema.get("enums") or {}):
                node: dict[str, Any] = {"$ref": f"#/$defs/{rng}"}
            elif rng in (schema.get("classes") or {}):
                node = {"$ref": f"#/$defs/{rng}"}
            else:
                base = (schema.get("types", {}).get(rng, {}) or {}).get("typeof", rng)
                node = {"type": _JSON_TYPES.get(base, "string")}
                if base in _JSON_FORMATS:
                    node["format"] = _JSON_FORMATS[base]
                for bound, key in (("minimum_value", "minimum"), ("maximum_value", "maximum")):
                    if slot.get(bound) is not None:
                        node[key] = slot[bound]
            if slot.get("description"):
                node["description"] = slot["description"]
            if slot.get("multivalued"):
                node = {"type": "array", "items": node}
            properties[slot_name] = node
            if slot.get("required"):
                required.append(slot_name)
        definitions[class_name] = {
            "type": "object", "title": class_name,
            "description": klass.get("description", ""),
            "properties": properties,
            **({"required": required} if required else {}),
            "additionalProperties": False,
        }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": schema.get("id"),
        "title": schema.get("title"),
        "description": schema.get("description"),
        "$defs": definitions,
        "x-generated-by": "utils.linkml_schema fallback",
        "x-fallback-reason": fallback_reason,
    }


def _range_label(schema: Mapping[str, Any], slot: Mapping[str, Any]) -> str:
    rng = str(slot.get("range") or "string")
    label = {v: k for k, v in _BUILTIN_TYPES.items()}.get(rng, rng)
    return f"{label}[]" if slot.get("multivalued") else label


def to_mermaid(schema: Mapping[str, Any], *, max_attributes: int = 12,
               max_enums: int = 30, include_enums: bool = True) -> str:
    """A Mermaid ``classDiagram`` rendered from the canonical schema."""
    lines = ["classDiagram"]
    if include_enums:
        for enum_name, enum in sorted((schema.get("enums") or {}).items())[:max_enums]:
            values = list((enum.get("permissible_values") or {}))
            lines.append(f"    class {enum_name} {{")
            lines.append("        <<enumeration>>")
            for value in values[:8]:
                lines.append(f"        {value}")
            if len(values) > 8:
                lines.append(f"        {len(values) - 8}_more")
            lines.append("    }")
    relationships: list[str] = []
    for class_name, klass in (schema.get("classes") or {}).items():
        stereotype = (klass.get("annotations") or {}).get("stereotype", "entity")
        lines.append(f"    class {class_name} {{")
        if stereotype != "entity":
            lines.append(f"        <<{stereotype}>>")
        shown = 0
        for slot_name, slot in (klass.get("attributes") or {}).items():
            rng = str(slot.get("range") or "")
            if rng in (schema.get("classes") or {}):
                multiplicity = "0..*" if slot.get("multivalued") else ("1" if slot.get("required") else "0..1")
                relationships.append(f'    {class_name} --> "{multiplicity}" {rng} : {slot_name}')
                continue
            if shown >= max_attributes:
                continue
            optional = "" if slot.get("required") else "?"
            lines.append(f"        +{_range_label(schema, slot)} {slot_name}{optional}")
            shown += 1
        remaining = sum(
            1 for s in (klass.get("attributes") or {}).values()
            if str(s.get("range") or "") not in (schema.get("classes") or {})
        ) - shown
        if remaining > 0:
            lines.append(f"        +{remaining} more attributes")
        lines.append("    }")
    lines.extend(relationships)
    return "\n".join(lines)


def to_plantuml(schema: Mapping[str, Any], *, max_attributes: int = 12) -> str:
    """A PlantUML class diagram rendered from the canonical schema."""
    lines = ["@startuml", "hide empty members", "skinparam classAttributeIconSize 0"]
    for enum_name, enum in sorted((schema.get("enums") or {}).items())[:30]:
        values = list((enum.get("permissible_values") or {}))
        lines.append(f"enum {enum_name} {{")
        for value in values[:8]:
            lines.append(f"  {value}")
        if len(values) > 8:
            lines.append(f"  .. {len(values) - 8} more ..")
        lines.append("}")
    associations: list[str] = []
    for class_name, klass in (schema.get("classes") or {}).items():
        stereotype = (klass.get("annotations") or {}).get("stereotype", "entity")
        suffix = "" if stereotype == "entity" else f" <<{stereotype}>>"
        lines.append(f"class {class_name}{suffix} {{")
        shown = 0
        for slot_name, slot in (klass.get("attributes") or {}).items():
            rng = str(slot.get("range") or "")
            if rng in (schema.get("classes") or {}):
                multiplicity = "0..*" if slot.get("multivalued") else ("1" if slot.get("required") else "0..1")
                associations.append(f'{class_name} --> "{multiplicity}" {rng} : {slot_name}')
                continue
            if shown >= max_attributes:
                continue
            optional = "" if slot.get("required") else " {optional}"
            multiplicity = "[0..*]" if slot.get("multivalued") else ""
            lines.append(f"  +{slot_name} : {_range_label(schema, slot)}{multiplicity}{optional}")
            shown += 1
        lines.append("}")
    lines.extend(associations)
    lines.append("@enduml")
    return "\n".join(lines)


def catalog_rows(schema: Mapping[str, Any]) -> list[dict[str, Any]]:
    """One row per attribute, read off the canonical schema."""
    rows: list[dict[str, Any]] = []
    enums = schema.get("enums") or {}
    for class_name, klass in (schema.get("classes") or {}).items():
        for slot_name, slot in (klass.get("attributes") or {}).items():
            annotations = slot.get("annotations") or {}
            rng = str(slot.get("range") or "")
            bounds = []
            if slot.get("minimum_value") is not None:
                bounds.append(f">= {slot['minimum_value']}")
            if slot.get("maximum_value") is not None:
                bounds.append(f"<= {slot['maximum_value']}")
            rows.append({
                "class": class_name,
                "class_stereotype": (klass.get("annotations") or {}).get("stereotype", "entity"),
                "attribute": slot_name,
                # The catalog is the artifact people filter, so the element's
                # kind and category have to be columns in it, not something the
                # reader reconstructs from the type.
                "element_kind": annotations.get(
                    "element_kind", "relationship" if rng in (schema.get("classes") or {}) else "attribute"),
                "category": (slot.get("in_subset") or [""])[0],
                "type": rng,
                "type_basis": annotations.get("type_basis", ""),
                "multiplicity": "0..*" if slot.get("multivalued")
                                else ("1" if slot.get("required") else "0..1"),
                "required": bool(slot.get("required")),
                "unit": (slot.get("unit") or {}).get("symbol", ""),
                "default": slot.get("ifabsent", ""),
                "allowed_values": [
                    v.get("title", k) for k, v in
                    ((enums.get(rng) or {}).get("permissible_values") or {}).items()
                ][:12],
                "constraints": bounds,
                "description": slot.get("description", ""),
                "source_rules": annotations.get("source_rules", ""),
                "source_passages": annotations.get("source_passages", ""),
                "needs_review": annotations.get("needs_review") == "true",
                "review_reasons": annotations.get("review_reasons", ""),
            })
    return rows
