"""Deterministic core of the Business Information Model.

The pipeline already carries most of what a domain model needs, in a form
stronger than prose: every rule variable declares a ``type``, and many also
declare a ``unit``, an ``allowed_values`` set, or an ``allowed_range``.  A
mortgage graph of 614 rules carries 712 variables with enumerated values and
445 with numeric ranges, and its units are real business units -- ``usd``,
``percent``, ``basis_points``, ``months``.  That is enough to derive business
types, enumerations, multiplicity, and constraints *deterministically*, rather
than asking a model to guess them back out of names.

What this module does **not** decide is which class an attribute belongs to,
whether a cluster of attributes is really a value object, or what a
relationship's cardinality is.  Those are genuine business judgments; they are
made elsewhere, and everything here records enough provenance for such a
judgment to be audited or refused.

Every inference carries a ``basis`` saying what evidence produced it:

``declared``   the rule contract stated it outright (a ``unit`` of ``usd``, an
               ``allowed_values`` set).  Trustworthy.
``derived``    computed from declared facts (an integral ``allowed_range``
               implies ``Integer``).  Trustworthy.
``heuristic``  read off the attribute's *name*.  Useful, and wrong often
               enough that anything resting on it alone is flagged for review
               rather than presented as settled.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "BUSINESS_TYPES",
    "TypeInference",
    "Attribute",
    "Enumeration",
    "Constraint",
    "infer_business_type",
    "collect_attributes",
    "extract_enumerations",
    "pascal_case",
    "to_mermaid",
    "to_plantuml",
    "catalog_rows",
    "Relationship",
    "Klass",
    "InformationModel",
    "Finding",
    "build_model",
    "assign_attributes",
    "build_relationships",
    "VALIDATION_CHECKS",
    "CLASS_CONCEPT_KINDS",
    "camel_case",
    "validate_model",
]

#: Business types this module will assign.  Deliberately not a superset of
#: every UML primitive: each entry has to be derivable from something the rule
#: contract actually declares, or it would be decoration.
BUSINESS_TYPES = (
    "Money", "Percentage", "Integer", "Decimal", "Quantity",
    "Boolean", "Date", "DateTime", "Time", "Duration",
    "Identifier", "Text", "String",
)

#: Units observed in real graphs, mapped to the business type they imply.
#: Declared units are the strongest single signal available -- stronger than
#: any name pattern -- because the extractor had to read them off the source.
UNIT_TYPES: dict[str, str] = {
    "usd": "Money", "eur": "Money", "gbp": "Money", "currency": "Money",
    "dollars": "Money", "usd_per_month": "Money",
    "percent": "Percentage", "%": "Percentage", "percentage": "Percentage",
    "ratio": "Percentage", "basis_points": "Percentage", "bps": "Percentage",
    "days": "Duration", "business_days": "Duration", "months": "Duration",
    "years": "Duration", "weeks": "Duration", "hours": "Duration",
    "count": "Integer", "units": "Integer", "loans": "Integer",
}

#: Name suffixes/fragments that *suggest* a type when nothing was declared.
#: Ordered most to least specific; every match is recorded as ``heuristic``.
_NAME_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(_id|_identifier|_number)$", "Identifier"),
    (r"(_amount|_balance|_price|_cost|_fee|_payment|_proceeds|_income)$", "Money"),
    (r"(_ratio|_rate|_percent|_percentage|_ltv|_cltv|_hcltv|_dti)$", "Percentage"),
    (r"(_days|_months|_years|_weeks|_hours|_period|_term)$", "Duration"),
    (r"(_count|_units|_number_of_[a-z_]+)$", "Integer"),
    (r"(_date)$", "Date"),
    (r"(_timestamp|_datetime)$", "DateTime"),
)

_INTEGRAL_UNITS = {"count", "units", "loans", "days", "business_days", "months", "years", "weeks"}


def pascal_case(name: Any) -> str:
    """``occupancy_type`` -> ``OccupancyType``. Stable and reversible enough
    that a reviewer can find the source variable from the model."""
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", str(name or "")) if part]
    # Source concept ids are SCREAMING_SNAKE (``MORTGAGE_BACKED_SECURITY``);
    # keeping the shouting would produce MORTGAGEBACKEDSECURITY, which is not a
    # class name anyone would write. Fold an all-caps part to title case, but
    # leave mixed-case input alone so an already-camel name survives intact.
    normalised = [part.capitalize() if part.isupper() else part[:1].upper() + part[1:] for part in parts]
    return "".join(normalised) or "Unnamed"


def camel_case(name: Any) -> str:
    """``principal_amount`` -> ``principalAmount``, for attribute names."""
    pascal = pascal_case(name)
    return pascal[:1].lower() + pascal[1:] if pascal else "unnamed"


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


@dataclass(frozen=True)
class TypeInference:
    """A business type plus the evidence that produced it."""

    type: str
    basis: str                      # declared | derived | heuristic | fallback
    reason: str
    needs_review: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"type": self.type, "basis": self.basis, "reason": self.reason,
                "needs_review": self.needs_review}


def _integral(values: Iterable[Any]) -> bool:
    seen = False
    for value in values:
        if value is None:
            continue
        seen = True
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if float(value) != int(float(value)):
            return False
    return seen


def infer_business_type(
    variable: Mapping[str, Any],
    *,
    enum_type_name: str | None = None,
) -> TypeInference:
    """Infer the business type of one declared variable.

    Order matters: declared facts are consulted before names, so a variable
    that says ``unit: usd`` becomes ``Money`` regardless of what it is called,
    and only a variable with nothing declared falls through to its name.
    """
    declared = _norm(variable.get("type"))
    unit = _norm(variable.get("unit"))
    name = _norm(variable.get("name"))
    values = variable.get("allowed_values")
    rng = variable.get("allowed_range")

    # 1. A closed value set is an enumeration, whatever the declared type says.
    #    This deliberately overrides `string`: a variable declared string with
    #    a fixed set of permitted values is an enumeration that was typed
    #    loosely, and modelling it as text would discard a real constraint.
    if isinstance(values, list) and values:
        return TypeInference(
            enum_type_name or pascal_case(name) or "Enumeration",
            "declared",
            f"declares {len(values)} allowed value(s)",
        )

    if declared == "boolean":
        return TypeInference("Boolean", "declared", "declared boolean")
    if declared in ("date", "date_time", "time"):
        return TypeInference(
            {"date": "Date", "date_time": "DateTime", "time": "Time"}[declared],
            "declared", f"declared {declared}",
        )
    if declared == "duration":
        return TypeInference("Duration", "declared", "declared duration")

    # 2. A declared unit outranks any name pattern.
    if unit in UNIT_TYPES:
        inferred = UNIT_TYPES[unit]
        if "_per_" in unit:
            # e.g. ``usd_per_month``: the amount is real, but so is the period,
            # and collapsing it to a bare Money loses that the value is a rate.
            return TypeInference(
                inferred, "declared",
                f"declared unit {unit!r}; carries a period, so this is a rate rather than a one-off amount",
                needs_review=True,
            )
        if inferred == "Integer" and declared == "number":
            return TypeInference("Integer", "declared", f"unit {unit!r} counts whole items")
        return TypeInference(inferred, "declared", f"declared unit {unit!r}")

    if declared == "number":
        if isinstance(rng, list) and _integral(rng):
            return TypeInference("Integer", "derived", "allowed_range is integral")
        for pattern, inferred in _NAME_PATTERNS:
            if re.search(pattern, name) and inferred in ("Money", "Percentage", "Integer", "Duration"):
                return TypeInference(inferred, "heuristic", f"name matches {pattern!r}", needs_review=True)
        return TypeInference("Decimal", "derived", "numeric with no unit or range to narrow it")

    if declared == "list":
        return TypeInference("String", "derived", "list element type is not declared", needs_review=True)

    if declared == "string":
        if variable.get("free_text") is True:
            return TypeInference("Text", "declared", "declared free text")
        for pattern, inferred in _NAME_PATTERNS:
            if re.search(pattern, name):
                return TypeInference(inferred, "heuristic", f"name matches {pattern!r}", needs_review=True)
        # A string that is neither free text nor obviously identified is the
        # single most likely modelling mistake in the whole model, so it is
        # never quietly accepted.
        return TypeInference(
            "String", "fallback",
            "declared string with no free_text flag, allowed values, or name signal",
            needs_review=True,
        )

    for pattern, inferred in _NAME_PATTERNS:
        if re.search(pattern, name):
            return TypeInference(inferred, "heuristic", f"name matches {pattern!r}", needs_review=True)
    return TypeInference("String", "fallback", f"no declared type ({declared or 'missing'})", needs_review=True)


@dataclass
class Constraint:
    """A business rule expressed against one attribute."""

    kind: str                       # range | allowed_values | comparison | required
    expression: str
    source_rule_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "expression": self.expression,
                "source_rule_ids": list(self.source_rule_ids)}


@dataclass
class Attribute:
    """One business attribute, with everything needed to defend it."""

    name: str
    symbol: str                     # the underlying pipeline variable name
    type: str
    type_basis: str
    type_reason: str
    unit: str = ""                  # as declared by the rule, e.g. usd / percent / months
    multiplicity: str = "1"
    required: bool = True
    default: Any = None
    allowed_values: tuple[str, ...] = ()
    constraints: list[Constraint] = field(default_factory=list)
    source_rule_ids: tuple[str, ...] = ()
    source_passages: tuple[str, ...] = ()
    needs_review: bool = False
    review_reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "symbol": self.symbol, "type": self.type,
            "type_basis": self.type_basis, "type_reason": self.type_reason, "unit": self.unit,
            "multiplicity": self.multiplicity, "required": self.required,
            "default": self.default, "allowed_values": list(self.allowed_values),
            "constraints": [c.as_dict() for c in self.constraints],
            "source_rule_ids": list(self.source_rule_ids),
            "source_passages": list(self.source_passages),
            "needs_review": self.needs_review,
            "review_reasons": list(self.review_reasons),
        }


@dataclass
class Enumeration:
    """A controlled vocabulary lifted out of the rules that constrain it."""

    name: str
    values: tuple[str, ...]
    source_symbols: tuple[str, ...] = ()
    source_rule_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "values": list(self.values),
                "source_symbols": list(self.source_symbols),
                "source_rule_ids": list(self.source_rule_ids)}


# ---------------------------------------------------------------------------
# collection
# ---------------------------------------------------------------------------

def _rules(graph: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [r for r in (graph.get("business_rules") or []) if isinstance(r, Mapping)]


def _passages(rule: Mapping[str, Any]) -> set[str]:
    out = set()
    ref = rule.get("source_reference")
    for item in (ref if isinstance(ref, list) else [ref]):
        if isinstance(item, Mapping):
            path = _norm(item.get("chunk_path") or item.get("document"))
            section = _norm(item.get("section_id") or item.get("section"))
            if path or section:
                out.add(f"{path}#{section}" if section else path)
    return out


def collect_attributes(graph: Mapping[str, Any]) -> tuple[dict[str, Attribute], list[dict[str, Any]]]:
    """Merge every declaration of each variable across all rules.

    Returns the merged attributes and a list of *type conflicts* -- the same
    symbol declared with incompatible types by different rules. Those are
    reported, never silently reconciled: picking a winner would hide a real
    disagreement in the source extraction.
    """
    declarations: dict[str, list[tuple[str, Mapping[str, Any]]]] = defaultdict(list)
    read_by: dict[str, set[str]] = defaultdict(set)
    written_by: dict[str, set[str]] = defaultdict(set)
    passages: dict[str, set[str]] = defaultdict(set)

    for rule in _rules(graph):
        rid = str(rule.get("rule_id") or "")
        rule_passages = _passages(rule)
        for variable in rule.get("variables") or []:
            if not isinstance(variable, Mapping) or not variable.get("name"):
                continue
            symbol = _norm(variable.get("name"))
            declarations[symbol].append((rid, variable))
            passages[symbol] |= rule_passages
        for predicate in rule.get("condition_predicates") or []:
            if isinstance(predicate, Mapping) and predicate.get("variable"):
                read_by[_norm(predicate["variable"])].add(rid)
        for outcome in rule.get("outcomes") or []:
            if isinstance(outcome, Mapping) and outcome.get("variable"):
                written_by[_norm(outcome["variable"])].add(rid)

    attributes: dict[str, Attribute] = {}
    conflicts: list[dict[str, Any]] = []

    for symbol, decls in sorted(declarations.items()):
        inferences = {}
        for rid, variable in decls:
            inference = infer_business_type(variable)
            inferences.setdefault(inference.type, []).append(rid)

        # Prefer the type with the strongest evidence, and report disagreement
        # at both levels. Inference can reconcile a loosely-declared `string`
        # with a properly united `number` into the same business type, which is
        # the right model -- but the underlying rules still disagree about what
        # the attribute *is*, and that is an extraction defect a reviewer should
        # see rather than one the model quietly absorbs.
        declared_types = {_norm(v.get("type")) for _, v in decls if _norm(v.get("type"))}
        if len(inferences) > 1:
            conflicts.append({
                "symbol": symbol,
                "level": "business_type",
                "types": {t: sorted(set(ids)) for t, ids in inferences.items()},
                "detail": "the same attribute resolves to incompatible business types across rules",
            })
        elif len(declared_types) > 1:
            conflicts.append({
                "symbol": symbol,
                "level": "declared_type",
                "types": {t: sorted({rid for rid, v in decls if _norm(v.get("type")) == t})
                          for t in sorted(declared_types)},
                "detail": ("rules declare this attribute with different primitive types; they agree "
                           "on the business type only after inference"),
            })

        best = max(
            (infer_business_type(v) for _, v in decls),
            key=lambda i: {"declared": 3, "derived": 2, "heuristic": 1, "fallback": 0}.get(i.basis, 0),
        )

        unit = ""
        values: list[str] = []
        default = None
        ranges: list[Any] = []
        is_list = False
        for _, variable in decls:
            if not unit and _norm(variable.get("unit")):
                unit = _norm(variable.get("unit"))
            if isinstance(variable.get("allowed_values"), list):
                for value in variable["allowed_values"]:
                    text = str(value)
                    if text not in values:
                        values.append(text)
            if variable.get("default") is not None and default is None:
                default = variable.get("default")
            if isinstance(variable.get("allowed_range"), list):
                ranges.append(variable["allowed_range"])
            if _norm(variable.get("type")) == "list":
                is_list = True

        constraints: list[Constraint] = []
        for bounds in ranges[:1]:
            if isinstance(bounds, list) and len(bounds) == 2 and any(b is not None for b in bounds):
                low, high = bounds
                parts = []
                if low is not None:
                    parts.append(f"{camel_case(symbol)} >= {low}")
                if high is not None:
                    parts.append(f"{camel_case(symbol)} <= {high}")
                constraints.append(Constraint("range", " and ".join(parts),
                                              tuple(sorted({rid for rid, _ in decls}))))
        if values:
            constraints.append(Constraint(
                "allowed_values",
                f"{camel_case(symbol)} in {{{', '.join(values[:8])}{' …' if len(values) > 8 else ''}}}",
                tuple(sorted({rid for rid, _ in decls})),
            ))

        review_reasons = []
        if best.needs_review:
            review_reasons.append(best.reason)
        if len(inferences) > 1:
            review_reasons.append("declared with conflicting types across rules")

        # An attribute a rule *tests* must have a value for that rule to be
        # evaluated at all; one that is only ever assigned is an outcome and
        # may legitimately be absent beforehand.
        required = bool(read_by.get(symbol))

        attributes[symbol] = Attribute(
            name=camel_case(symbol),
            symbol=symbol,
            type=best.type,
            type_basis=best.basis,
            type_reason=best.reason,
            unit=unit,
            multiplicity="0..*" if is_list else ("1" if required else "0..1"),
            required=required,
            default=default,
            allowed_values=tuple(values),
            constraints=constraints,
            source_rule_ids=tuple(sorted({rid for rid, _ in decls if rid})),
            source_passages=tuple(sorted(passages.get(symbol, ()))),
            needs_review=bool(review_reasons),
            review_reasons=tuple(review_reasons),
        )

    return attributes, conflicts


def extract_enumerations(attributes: Mapping[str, Attribute]) -> dict[str, Enumeration]:
    """Lift controlled vocabularies into named enumerations.

    Attributes whose permitted values are identical share one enumeration:
    two rules constraining the same set are describing the same business
    vocabulary, and duplicating it per attribute would be noise dressed as
    precision.
    """
    by_values: dict[tuple[str, ...], list[Attribute]] = defaultdict(list)
    for attribute in attributes.values():
        if attribute.allowed_values:
            by_values[tuple(sorted(attribute.allowed_values))].append(attribute)

    enumerations: dict[str, Enumeration] = {}
    for values, members in sorted(by_values.items(), key=lambda item: -len(item[1])):
        # Name after the shortest member symbol: the least qualified name is
        # almost always the general concept the others are specialisations of.
        anchor = min(members, key=lambda a: (len(a.symbol), a.symbol))
        name = pascal_case(anchor.symbol)
        suffix = 2
        while name in enumerations:
            name, suffix = f"{pascal_case(anchor.symbol)}{suffix}", suffix + 1
        enumerations[name] = Enumeration(
            name=name,
            values=tuple(sorted(values)),
            source_symbols=tuple(sorted(a.symbol for a in members)),
            source_rule_ids=tuple(sorted({r for a in members for r in a.source_rule_ids})),
        )
        for member in members:
            member.type = name
            member.type_basis = "declared"
            member.type_reason = f"controlled vocabulary of {len(values)} value(s)"
    return enumerations


# ---------------------------------------------------------------------------
# classes and relationships
# ---------------------------------------------------------------------------

#: SBVR concept kinds that become UML classes. ``decision_variable`` is
#: excluded on purpose: those are attributes of something else, and promoting
#: them would produce a class per predicate rather than a domain model.
CLASS_CONCEPT_KINDS = frozenset({"business_object", "actor_role", "evidence_object", "event", "process"})


@dataclass
class Relationship:
    """A directed association between two classes."""

    source: str
    target: str
    verb: str
    source_multiplicity: str = "1"
    target_multiplicity: str = "0..*"
    kind: str = "association"       # association | composition | aggregation | specialization
    basis: str = "declared"
    source_rule_ids: tuple[str, ...] = ()
    needs_review: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source, "target": self.target, "verb": self.verb,
            "source_multiplicity": self.source_multiplicity,
            "target_multiplicity": self.target_multiplicity,
            "kind": self.kind, "basis": self.basis,
            "source_rule_ids": list(self.source_rule_ids),
            "needs_review": self.needs_review,
        }


@dataclass
class Klass:
    """A UML class in the business information model."""

    name: str
    concept_id: str
    description: str = ""
    stereotype: str = "entity"      # entity | value_object | actor | event | process
    attributes: list[Attribute] = field(default_factory=list)
    source_passages: tuple[str, ...] = ()
    needs_review: bool = False
    review_reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "concept_id": self.concept_id,
            "description": self.description, "stereotype": self.stereotype,
            "attributes": [a.as_dict() for a in self.attributes],
            "source_passages": list(self.source_passages),
            "needs_review": self.needs_review,
            "review_reasons": list(self.review_reasons),
        }


@dataclass
class InformationModel:
    classes: list[Klass] = field(default_factory=list)
    enumerations: dict[str, Enumeration] = field(default_factory=dict)
    relationships: list[Relationship] = field(default_factory=list)
    unassigned: list[Attribute] = field(default_factory=list)
    type_conflicts: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "business-information-model/1.0",
            "classes": [k.as_dict() for k in self.classes],
            "enumerations": [e.as_dict() for e in self.enumerations.values()],
            "relationships": [r.as_dict() for r in self.relationships],
            "unassigned_attributes": [a.as_dict() for a in self.unassigned],
            "type_conflicts": self.type_conflicts,
            "counts": {
                "classes": len(self.classes),
                "enumerations": len(self.enumerations),
                "relationships": len(self.relationships),
                "attributes": sum(len(k.attributes) for k in self.classes),
                "unassigned_attributes": len(self.unassigned),
            },
        }


def _stereotype_for(kind: str) -> str:
    return {
        "actor_role": "actor", "event": "event", "process": "process",
        "evidence_object": "entity", "business_object": "entity",
    }.get(_norm(kind), "entity")


def assign_attributes(
    graph: Mapping[str, Any],
    attributes: Mapping[str, Attribute],
    class_ids: Sequence[str],
    *,
    actor_ids: Iterable[str] = (),
) -> tuple[dict[str, list[Attribute]], list[Attribute]]:
    """Assign each attribute to the class its rules are actually about.

    The signal is ``related_entities``: every rule declaring the attribute
    names the entities it concerns, so an attribute whose declaring rules point
    overwhelmingly at one entity belongs to that entity. Where the evidence is
    split or absent the attribute is left *unassigned* rather than filed under
    a guess -- an attribute on the wrong class is worse than one a reviewer is
    asked about.

    Actor concepts are excluded from ownership entirely. A rule names the party
    responsible for applying it, and that party is not what the rule's variables
    describe: a lender does not own a loan's LTV ratio. Without this exclusion
    the vote files nearly everything under whichever actor appears most often,
    which on a real mortgage graph put 1,454 attributes on ``LENDER`` and 10 on
    ``MortgageLoan``. Attributes that only actors claim are returned unassigned,
    for a modelling pass that can reason about what they actually describe.
    """
    known = {_norm(c) for c in class_ids}
    votes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for rule in _rules(graph):
        owners = known - {_norm(a) for a in actor_ids}
        entities = [
            _norm(value) for value in (rule.get("related_entities") or [])
            if _norm(value) in owners
        ]
        for extra in ("source_entity", "entity_or_relationship"):
            value = _norm(rule.get(extra))
            if value in owners:
                entities.append(value)
        if not entities:
            continue
        for variable in rule.get("variables") or []:
            if isinstance(variable, Mapping) and variable.get("name"):
                symbol = _norm(variable["name"])
                for entity in entities:
                    votes[symbol][entity] += 1

    assigned: dict[str, list[Attribute]] = defaultdict(list)
    unassigned: list[Attribute] = []
    for symbol, attribute in attributes.items():
        tally = votes.get(symbol)
        if not tally:
            unassigned.append(attribute)
            continue
        ranked = sorted(tally.items(), key=lambda item: (-item[1], item[0]))
        top, top_votes = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else 0
        if top_votes == runner_up:
            # A genuine tie is ambiguity, not a coin toss.
            attribute.needs_review = True
            attribute.review_reasons = attribute.review_reasons + (
                f"declaring rules point equally at {ranked[0][0]} and {ranked[1][0]}",
            )
            unassigned.append(attribute)
            continue
        assigned[top].append(attribute)
    return assigned, unassigned


def build_relationships(
    profile: Mapping[str, Any],
    class_names: Mapping[str, str],
) -> list[Relationship]:
    """Turn SBVR fact types into directed associations.

    A fact type states subject/verb/object but carries no cardinality, so the
    multiplicity here is a stated default rather than a finding, and every
    relationship is flagged for review on exactly that point.
    """
    relationships: list[Relationship] = []
    for fact in (profile.get("fact_types") or []):
        if not isinstance(fact, Mapping):
            continue
        subject = class_names.get(_norm(fact.get("subject_concept")))
        target = class_names.get(_norm(fact.get("object_concept")))
        if not subject or not target or subject == target:
            continue
        relationships.append(Relationship(
            source=subject, target=target,
            verb=str(fact.get("verb_term") or "relates to"),
            basis="declared",
            needs_review=True,
        ))
    return sorted({(r.source, r.target, r.verb): r for r in relationships}.values(),
                  key=lambda r: (r.source, r.target, r.verb))


def build_model(
    graph: Mapping[str, Any],
    profile: Mapping[str, Any] | None = None,
) -> InformationModel:
    """Assemble the deterministic skeleton of the information model."""
    profile = profile if isinstance(profile, Mapping) else {}
    attributes, conflicts = collect_attributes(graph)
    enumerations = extract_enumerations(attributes)

    concepts: dict[str, Mapping[str, Any]] = {}
    for concept in (profile.get("concepts") or []):
        if isinstance(concept, Mapping) and concept.get("concept_id"):
            concepts[_norm(concept["concept_id"])] = concept
    for entity_id, entity in (graph.get("entity_types") or {}).items():
        key = _norm(entity_id)
        if key not in concepts:
            concepts[key] = {
                "concept_id": entity_id,
                "definition": (entity or {}).get("definition") if isinstance(entity, Mapping) else "",
                "concept_kind": (entity or {}).get("concept_kind") if isinstance(entity, Mapping) else "",
            }

    class_ids = [
        cid for cid, concept in concepts.items()
        if _norm(concept.get("concept_kind")) in CLASS_CONCEPT_KINDS
        or not _norm(concept.get("concept_kind"))     # untyped entity: still a candidate
    ]
    actor_ids = [
        cid for cid, concept in concepts.items()
        if _norm(concept.get("concept_kind")) == "actor_role"
    ]
    assigned, unassigned = assign_attributes(graph, attributes, class_ids, actor_ids=actor_ids)

    classes: list[Klass] = []
    class_names: dict[str, str] = {}
    for cid in sorted(class_ids):
        concept = concepts[cid]
        members = sorted(assigned.get(cid, []), key=lambda a: a.name)
        if not members:
            continue                    # a class with no attributes is a label, not a model element
        name = pascal_case(concept.get("concept_id") or cid)
        class_names[cid] = name
        reasons = []
        if not _norm(concept.get("definition")):
            reasons.append("no business definition was supplied by the source vocabulary")
        classes.append(Klass(
            name=name,
            concept_id=str(concept.get("concept_id") or cid),
            description=str(concept.get("definition") or ""),
            stereotype=_stereotype_for(concept.get("concept_kind")),
            attributes=members,
            source_passages=tuple(sorted({p for a in members for p in a.source_passages})[:8]),
            needs_review=bool(reasons),
            review_reasons=tuple(reasons),
        ))

    return InformationModel(
        classes=classes,
        enumerations=enumerations,
        relationships=build_relationships(profile, class_names),
        unassigned=sorted(unassigned, key=lambda a: a.name),
        type_conflicts=conflicts,
    )


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def _canonical(model: "InformationModel") -> dict[str, Any]:
    from utils.linkml_schema import to_linkml

    return to_linkml(model)


def to_mermaid(model: "InformationModel", **kwargs: Any) -> str:
    """A Mermaid ``classDiagram``, rendered from the canonical LinkML schema.

    Rendering goes through LinkML rather than straight off these dataclasses so
    the diagram, the JSON Schema and the catalog are all projections of one
    artifact and cannot disagree with each other.
    """
    from utils.linkml_schema import to_mermaid as render

    return render(_canonical(model), **kwargs)


def to_plantuml(model: "InformationModel", **kwargs: Any) -> str:
    """A PlantUML class diagram, rendered from the canonical LinkML schema."""
    from utils.linkml_schema import to_plantuml as render

    return render(_canonical(model), **kwargs)


def catalog_rows(model: "InformationModel") -> list[dict[str, Any]]:
    """One row per attribute, read off the canonical LinkML schema."""
    from utils.linkml_schema import catalog_rows as rows

    return rows(_canonical(model))


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    """One validation result, tied to the check that produced it."""

    check: str
    severity: str                   # error | warning | review
    subject: str
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"check": self.check, "severity": self.severity,
                "subject": self.subject, "detail": self.detail}


#: The ten checks, in the order they are reported. Named so a finding can be
#: traced back to the requirement it enforces rather than read as free text.
VALIDATION_CHECKS = (
    "concept_representation",
    "attribute_presence",
    "type_defensibility",
    "type_consistency",
    "relationship_direction_and_multiplicity",
    "enumeration_usage",
    "constraint_coverage",
    "no_superfluous_elements",
    "source_consistency",
    "ambiguity_flagged",
)


def validate_model(
    model: InformationModel,
    graph: Mapping[str, Any],
    profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the ten model checks and report findings without repairing them.

    Repair is deliberately out of scope: a validator that silently fixes what
    it finds cannot also tell you how good the model was. Every finding names
    its subject so it can be acted on individually.
    """
    profile = profile if isinstance(profile, Mapping) else {}
    findings: list[Finding] = []
    modelled = {_norm(k.concept_id) for k in model.classes}

    # 1. Every important business concept has a representation.
    for concept in (profile.get("concepts") or []):
        if not isinstance(concept, Mapping):
            continue
        cid = _norm(concept.get("concept_id"))
        if not cid or cid in modelled:
            continue
        if _norm(concept.get("concept_kind")) in CLASS_CONCEPT_KINDS:
            findings.append(Finding(
                "concept_representation", "review", str(concept.get("concept_id")),
                "governed concept has no class, because no attribute could be attributed to it",
            ))

    # 2. Every class carries meaningful attributes.
    for klass in model.classes:
        if not klass.attributes:
            findings.append(Finding("attribute_presence", "error", klass.name,
                                    "class has no attributes"))
        elif all(a.type == "Boolean" for a in klass.attributes) and len(klass.attributes) > 3:
            findings.append(Finding(
                "attribute_presence", "review", klass.name,
                "every attribute is Boolean, which usually means rule flags were modelled "
                "instead of the business state behind them",
            ))

    # 3/4. Types are defensible, and consistent for the same attribute.
    for klass in model.classes:
        for attribute in klass.attributes:
            if attribute.type_basis == "fallback":
                findings.append(Finding(
                    "type_defensibility", "review", f"{klass.name}.{attribute.name}",
                    f"type rests on no declared evidence: {attribute.type_reason}",
                ))
            elif attribute.type_basis == "heuristic":
                findings.append(Finding(
                    "type_defensibility", "review", f"{klass.name}.{attribute.name}",
                    f"type inferred from the attribute name alone: {attribute.type_reason}",
                ))
    for conflict in model.type_conflicts:
        findings.append(Finding(
            "type_consistency", "error", str(conflict.get("symbol")),
            f"declared as {', '.join(sorted(conflict.get('types', {})))} by different rules",
        ))

    # 5. Relationships carry a defensible direction and multiplicity.
    for rel in model.relationships:
        if rel.needs_review:
            findings.append(Finding(
                "relationship_direction_and_multiplicity", "review",
                f"{rel.source} -> {rel.target}",
                "fact types state direction but never cardinality; multiplicity is a default, not a finding",
            ))

    # 6. Controlled vocabularies became enumerations.
    for klass in model.classes:
        for attribute in klass.attributes:
            if attribute.allowed_values and attribute.type in BUSINESS_TYPES:
                findings.append(Finding(
                    "enumeration_usage", "error", f"{klass.name}.{attribute.name}",
                    f"has {len(attribute.allowed_values)} controlled values but is typed "
                    f"{attribute.type} instead of an enumeration",
                ))

    # 7. Constraints found in the policy reached the model.
    constrained = sum(1 for k in model.classes for a in k.attributes if a.constraints)
    total_attributes = sum(len(k.attributes) for k in model.classes)
    if total_attributes and constrained == 0:
        findings.append(Finding("constraint_coverage", "error", "model",
                                "no attribute carries a constraint, though the rules declare ranges and value sets"))

    # 8. Nothing superfluous.
    for name, enum in model.enumerations.items():
        if len(enum.values) < 2:
            findings.append(Finding("no_superfluous_elements", "review", name,
                                    "enumeration has fewer than two values, so it constrains nothing"))
    for klass in model.classes:
        if len(klass.attributes) == 1 and klass.attributes[0].type == "Boolean":
            findings.append(Finding(
                "no_superfluous_elements", "review", klass.name,
                "single boolean attribute: likely a rule flag rather than a business entity",
            ))

    # 9. The model reflects the source graph.
    declared_symbols = {
        _norm(v.get("name"))
        for rule in _rules(graph)
        for v in (rule.get("variables") or [])
        if isinstance(v, Mapping) and v.get("name")
    }
    modelled_symbols = {a.symbol for k in model.classes for a in k.attributes}
    missing = declared_symbols - modelled_symbols - {a.symbol for a in model.unassigned}
    if missing:
        findings.append(Finding(
            "source_consistency", "error", "model",
            f"{len(missing)} declared variable(s) appear in neither a class nor the unassigned list",
        ))
    if model.unassigned:
        findings.append(Finding(
            "source_consistency", "review", "model",
            f"{len(model.unassigned)} attribute(s) could not be attributed to a class from "
            "the rules' own related_entities and are held for review rather than filed by guess",
        ))

    # 10. Ambiguity surfaced rather than resolved.
    for attribute in model.unassigned:
        if attribute.needs_review:
            findings.append(Finding("ambiguity_flagged", "review", attribute.name,
                                    "; ".join(attribute.review_reasons)))

    by_check: dict[str, int] = {check: 0 for check in VALIDATION_CHECKS}
    by_severity: dict[str, int] = {"error": 0, "warning": 0, "review": 0}
    for finding in findings:
        by_check[finding.check] = by_check.get(finding.check, 0) + 1
        by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1

    return {
        "schema_version": "business-information-model-validation/1.0",
        "checks": list(VALIDATION_CHECKS),
        "passed": [c for c, n in by_check.items() if n == 0],
        "findings": [f.as_dict() for f in findings],
        "counts": {"by_check": by_check, "by_severity": by_severity, "total": len(findings)},
        "coverage": {
            "classes": len(model.classes),
            "attributes": total_attributes,
            "attributes_with_constraints": constrained,
            "enumerations": len(model.enumerations),
            "unassigned_attributes": len(model.unassigned),
        },
    }
