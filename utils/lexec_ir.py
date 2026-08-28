"""LExec IR v1 lowering and validation.

The extraction graph is a useful interchange format, but it is not an
executable semantics.  This module is the deliberately small, fail-closed
boundary between the two formats.  It lowers the supported v2 constructs to
``plan/lexec-ir-v1.schema.json`` and records a review-required refusal for
anything that cannot be represented without guessing.

The implementation is dependency-free.  The JSON Schema remains the public
shape contract; :func:`validate_ir` adds the cross-reference and recursive
formula checks that JSON Schema alone cannot express here.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "lexec-ir/1.0"
NULL_MODEL = "kleene_three_valued"
SUPPORTED_THEORIES = {"bool", "int", "real", "enum", "string"}
SUPPORTED_MODALITIES = {"obligation", "permission", "prohibition", "definition", "none"}
SUPPORTED_HIT_POLICIES = {"UNIQUE", "ANY", "PRIORITY", "COLLECT"}
CONSUMED_FIELDS = {
    "schema_version", "rule_id", "id", "rule_type", "condition_predicates", "condition_logic", "outcomes", "variables",
    "recommended_hit_policy", "applicability_scope", "scope_basis", "responsible_party", "counterparties", "exceptions",
    "exception_basis", "mandatory", "effective_date", "expiration_date", "versioning_status", "jurisdiction",
    "source_reference", "field_evidence",
}
IGNORED_FIELD_REASONS = {
    "rule_name": "NON_EXECUTABLE_METADATA", "description": "NON_EXECUTABLE_METADATA", "inference_reasoning": "NON_EXECUTABLE_METADATA",
    "test_vectors": "NON_EXECUTABLE_METADATA", "examples": "NON_EXECUTABLE_METADATA", "superseded_by": "NON_EXECUTABLE_METADATA",
    "risk_level": "NON_EXECUTABLE_METADATA", "related_rules": "NON_EXECUTABLE_METADATA", "enforcement_action": "NON_EXECUTABLE_METADATA",
    "data_points_required": "NON_EXECUTABLE_METADATA", "audit_frequency": "NON_EXECUTABLE_METADATA", "entity_or_relationship": "NON_EXECUTABLE_METADATA",
    "entity_type": "NON_EXECUTABLE_METADATA", "relationship_definition": "NON_EXECUTABLE_METADATA", "dependencies": "NON_EXECUTABLE_METADATA",
    "execution": "NON_EXECUTABLE_METADATA", "dependent_rules": "NON_EXECUTABLE_METADATA", "deduplication_info": "NON_EXECUTABLE_METADATA",
    # ``entity_definition`` is agent_05's descriptive entity/relationship-type
    # context (see agent_05_rules_with_entities_merger.py); its sibling
    # ``relationship_definition`` was already classified above.  ``conditions``
    # and ``consequences`` are the legacy prose fields the extraction prompt
    # historically emitted alongside the structured v2 contract; current
    # prompts (e.g. domain-prompts/*/business_rules_extraction_compact.txt)
    # explicitly instruct the model not to emit them because the structured
    # fields fully supersede them, but older/shared-prompt runs (e.g. the
    # mortgage domain) still produce them.
    "entity_definition": "NON_EXECUTABLE_METADATA", "conditions": "NON_EXECUTABLE_METADATA", "consequences": "NON_EXECUTABLE_METADATA",
    "confidence_score": "AUDIT_STATUS_NOT_EXECUTABLE", "exception_verification": "AUDIT_STATUS_NOT_EXECUTABLE", "scope_derivation": "AUDIT_STATUS_NOT_EXECUTABLE",
    "grounding": "AUDIT_STATUS_NOT_EXECUTABLE", "requires_review": "AUDIT_STATUS_NOT_EXECUTABLE", "review_reason": "AUDIT_STATUS_NOT_EXECUTABLE",
    "reference_verified": "AUDIT_STATUS_NOT_EXECUTABLE", "reference_verification_note": "AUDIT_STATUS_NOT_EXECUTABLE",
    "contract_issues": "AUDIT_STATUS_NOT_EXECUTABLE", "readiness": "AUDIT_STATUS_NOT_EXECUTABLE",
}
HEX64 = re.compile(r"^[a-f0-9]{64}$")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


class LoweringRefusal(ValueError):
    """An input construct cannot be lowered without a semantic assumption."""

    def __init__(self, code: str, construct: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.construct = construct
        self.detail = detail


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _normalise_name(value: Any) -> str:
    return str(value or "").strip().lower()


def _safe_identifier(value: Any, fallback: str = "symbol") -> str:
    value = _normalise_name(value)
    value = re.sub(r"[^a-z0-9_]+", "_", value).strip("_")
    if not value or not value[0].isalpha():
        value = f"{fallback}_{value}" if value else fallback
    return value


def _iter_rules(graph: Any) -> list[Mapping[str, Any]]:
    if isinstance(graph, list):
        return [item for item in graph if isinstance(item, Mapping)]
    if not isinstance(graph, Mapping):
        raise TypeError("graph must be an object or an array of rule objects")
    for key in ("business_rules", "rules", "compliance_rules"):
        value = graph.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    # A single v2 rule is a convenient fixture form.
    if "condition_predicates" in graph or "outcomes" in graph:
        return [graph]
    return []


def _find_hashes(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"corpus_sha256", "source_sha256"} and isinstance(item, str) and HEX64.fullmatch(item):
                yield item
            yield from _find_hashes(item)
    elif isinstance(value, list):
        for item in value:
            yield from _find_hashes(item)


def _source_hash(graph: Any, explicit: str | None) -> str:
    if explicit is not None:
        if not HEX64.fullmatch(explicit):
            raise ValueError("source_sha256 must be a lowercase SHA-256 digest")
        return explicit
    first = next(iter(_find_hashes(graph)), None)
    if first:
        return first
    texts: list[str] = []
    for rule in _iter_rules(graph):
        ref = rule.get("source_reference")
        if isinstance(ref, Mapping) and isinstance(ref.get("source_text"), str):
            texts.append(ref["source_text"])
        for values in (rule.get("field_evidence"),):
            if isinstance(values, Mapping):
                for entries in values.values():
                    if isinstance(entries, list):
                        texts.extend(str(entry.get("source_text")) for entry in entries if isinstance(entry, Mapping) and entry.get("source_text"))
    return _sha256_text("\n".join(texts))


def _all_references(rule: Mapping[str, Any], field: str | None = None) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = []
    if field and isinstance(rule.get("field_evidence"), Mapping):
        values = rule["field_evidence"].get(field)
        if isinstance(values, list):
            result.extend(item for item in values if isinstance(item, Mapping))
    if result:
        return result
    ref = rule.get("source_reference")
    if isinstance(ref, Mapping):
        return [ref]
    if isinstance(ref, list):
        return [item for item in ref if isinstance(item, Mapping)]
    return []


def _span(ref: Mapping[str, Any], source_sha256: str) -> dict[str, Any]:
    chunk = str(ref.get("chunk_path") or "<synthetic-input>").strip()
    section = str(ref.get("section_id") or "unresolved").strip()
    text = str(ref.get("source_text") or "").strip()
    if not text:
        raise LoweringRefusal("MISSING_PROVENANCE", "source_reference", "A non-empty source_text is required for provenance.")
    start = ref.get("start_offset")
    end = ref.get("end_offset")
    if not isinstance(start, int) or not isinstance(end, int):
        # v2 currently provides word positions rather than character offsets.
        # The quoted source text is therefore the only honest span available;
        # offsets are explicitly excerpt-local and are documented as such.
        start, end = 0, len(text)
    if start < 0 or end <= start:
        raise LoweringRefusal("INVALID_PROVENANCE", "source_reference", "Source span offsets must be non-empty and non-negative.")
    return {
        "chunk_path": chunk,
        "section_id": section,
        "start_offset": start,
        "end_offset": end,
        "source_sha256": source_sha256,
    }


def _provenance(rule: Mapping[str, Any], source_sha256: str, field: str | None = None) -> list[dict[str, Any]]:
    refs = _all_references(rule, field)
    if not refs:
        refs = [{"source_text": _canonical({"rule_id": rule.get("rule_id"), "field": field}), "section_id": "synthetic-input"}]
    spans: list[dict[str, Any]] = []
    for ref in refs:
        try:
            spans.append(_span(ref, source_sha256))
        except LoweringRefusal:
            # Keep the refusal itself provenance-bearing.  A short synthetic
            # span makes the failure inspectable without pretending it came
            # from source prose.
            spans.append(_span({"chunk_path": "<missing-source>", "section_id": "synthetic-input", "source_text": _canonical(ref)}, source_sha256))
    return spans


def _literal(value: Any, theory: str) -> dict[str, Any]:
    if theory not in SUPPORTED_THEORIES:
        raise LoweringRefusal("UNSUPPORTED_THEORY", "literal", f"Theory {theory!r} is not supported by LExec IR v1.")
    if theory == "bool" and not isinstance(value, bool):
        raise LoweringRefusal("TYPE_MISMATCH", "literal", "Boolean literal is not a boolean.")
    if theory in {"int", "real"} and (isinstance(value, bool) or not isinstance(value, (int, float))):
        raise LoweringRefusal("TYPE_MISMATCH", "literal", "Numeric literal is not numeric.")
    if theory == "int" and isinstance(value, float) and not value.is_integer():
        raise LoweringRefusal("TYPE_MISMATCH", "literal", "A real value cannot be used as an integer literal.")
    if theory in {"enum", "string"} and not isinstance(value, str):
        raise LoweringRefusal("TYPE_MISMATCH", "literal", "Enum and string literals must be strings.")
    return {"literal": value, "type": theory}


def _theory(variable: Mapping[str, Any]) -> str:
    kind = variable.get("type")
    if kind == "boolean":
        return "bool"
    if kind == "number":
        allowed = variable.get("allowed_range")
        if isinstance(allowed, list) and any(isinstance(item, float) and not item.is_integer() for item in allowed if item is not None):
            return "real"
        return "real"
    if kind in {"enum", "string"}:
        return kind
    raise LoweringRefusal("UNSUPPORTED_VARIABLE_TYPE", "variable", f"Variable type {kind!r} has no LExec v1 theory.")


def _operand(value: Any, value_type: str, variables: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if value_type == "variable_reference":
        name = _normalise_name(value)
        if name not in variables:
            raise LoweringRefusal("UNDEFINED_VARIABLE", "variable_reference", f"Variable reference {name!r} is undefined.")
        return {"symbol": _safe_identifier(name)}
    theory = {"boolean": "bool", "number": "real", "enum": "enum", "string": "string"}.get(value_type)
    if theory is None:
        raise LoweringRefusal("UNSUPPORTED_VALUE_TYPE", "operand", f"Value type {value_type!r} is not supported by LExec IR v1.")
    return _literal(value, theory)


def _formula_for_predicate(predicate: Mapping[str, Any], variables: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    variable = _normalise_name(predicate.get("variable"))
    if variable not in variables:
        raise LoweringRefusal("UNDEFINED_VARIABLE", "predicate", f"Predicate variable {variable!r} is undefined.")
    op = predicate.get("operator")
    value_type = str(predicate.get("value_type") or "")
    variable_type = variables[variable].get("type")
    expected_type = {"boolean": "boolean", "number": "number", "enum": "enum", "string": "string"}.get(value_type)
    if expected_type and variable_type != expected_type and not (value_type == "string" and variable_type == "string"):
        raise LoweringRefusal("TYPE_MISMATCH", "predicate", f"Predicate value type {value_type!r} does not match variable type {variable_type!r}.")
    left = {"symbol": _safe_identifier(variable)}
    if op == "is_null":
        return {"op": "is_null", "arg": left}
    if op not in {"==", "!=", ">", ">=", "<", "<=", "in", "not_in", "contains"}:
        raise LoweringRefusal("UNSUPPORTED_OPERATOR", "predicate", f"Operator {op!r} is not supported by LExec IR v1.")
    if op in {"in", "not_in"} and isinstance(predicate.get("value"), list):
        values = [_formula_for_predicate({**predicate, "operator": "==", "value": item, "value_type": "enum" if value_type == "enum" else "string"}, variables) for item in predicate["value"]]
        if not values:
            raise LoweringRefusal("EMPTY_SET", "predicate", "Membership predicates require at least one value.")
        formula = {"op": "or", "args": values}
        return {"op": "not", "arg": formula} if op == "not_in" else formula
    if op in {"in", "not_in"} and value_type == "range":
        right = _literal(_canonical(predicate.get("value")), "string")
        formula = {"op": "in_binned_range", "left": left, "right": right}
        return {"op": "not", "arg": formula} if op == "not_in" else formula
    if op == "contains":
        right = _operand(predicate.get("value"), "string", variables)
        return {"op": "contains", "left": left, "right": right}
    ir_op = {"==": "eq", "!=": "ne", ">": "gt", ">=": "ge", "<": "lt", "<=": "le", "in": "contains", "not_in": "contains"}.get(op)
    if ir_op is None:
        raise LoweringRefusal("UNSUPPORTED_OPERATOR", "predicate", f"Operator {op!r} is unsupported.")
    right = _operand(predicate.get("value"), value_type, variables)
    formula = {"op": ir_op, "left": left, "right": right}
    return {"op": "not", "arg": formula} if op == "not_in" else formula


def _logic(node: Any, predicates: Mapping[str, Mapping[str, Any]], variables: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if isinstance(node, str) and node in {"AND", "OR"}:
        op = "and" if node == "AND" else "or"
        return {"op": op, "args": [_formula_for_predicate(item, variables) for item in predicates.values()]}
    if not isinstance(node, Mapping):
        raise LoweringRefusal("INVALID_CONDITION_LOGIC", "condition_logic", "Condition logic must be a v2 logic object or AND/OR.")
    if set(node) == {"predicate_ref"}:
        predicate_id = str(node.get("predicate_ref"))
        if predicate_id not in predicates:
            raise LoweringRefusal("UNKNOWN_PREDICATE_REFERENCE", "condition_logic", f"Unknown predicate {predicate_id!r}.")
        return _formula_for_predicate(predicates[predicate_id], variables)
    branches = [key for key in ("all", "any") if key in node]
    if len(branches) != 1 or len(node) != 1 or not isinstance(node[branches[0]], list) or not node[branches[0]]:
        raise LoweringRefusal("INVALID_CONDITION_LOGIC", "condition_logic", "A logic node must contain one non-empty all/any branch.")
    return {"op": "and" if branches[0] == "all" else "or", "args": [_logic(child, predicates, variables) for child in node[branches[0]]]}


def _domain(variable: Mapping[str, Any], theory: str, predicates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if theory == "bool":
        return {"kind": "boolean"}
    if theory == "enum":
        values = variable.get("allowed_values")
        if not isinstance(values, list) or not values:
            raise LoweringRefusal("MISSING_ENUM_DOMAIN", "variable", "Enum variables require allowed_values.")
        return {"kind": "enum", "values": values}
    if theory == "string":
        if variable.get("free_text") is not True:
            raise LoweringRefusal("UNJUSTIFIED_STRING", "variable", "String variables require free_text=true.")
        ops: list[str] = []
        for predicate in predicates:
            if _normalise_name(predicate.get("variable")) != _normalise_name(variable.get("name")):
                continue
            op = predicate.get("operator")
            if op in {"==", "in"}:
                ops.append("eq")
            elif op == "contains":
                ops.append("contains")
            elif op == "is_null":
                ops.append("is_null")
            elif op in {">", ">=", "<", "<=", "not_in"}:
                raise LoweringRefusal("UNSUPPORTED_STRING_OPERATOR", "variable", f"String operator {op!r} is not representable.")
        return {"kind": "string", "predicates": sorted(set(ops or ["eq"]))}
    # v1 intentionally treats all v2 numbers as real; no implicit integer
    # claim is made until the corpus census establishes an integer theory.
    allowed = variable.get("allowed_range")
    if isinstance(allowed, list) and len(allowed) == 2 and all(item is None or (isinstance(item, (int, float)) and not isinstance(item, bool)) for item in allowed):
        return {"kind": "interval", "minimum": allowed[0], "maximum": allowed[1], "minimum_inclusive": True, "maximum_inclusive": True}
    return {"kind": "interval", "minimum": None, "maximum": None, "minimum_inclusive": True, "maximum_inclusive": True}


def _modality(rule: Mapping[str, Any]) -> str:
    kind = _normalise_name(rule.get("rule_type"))
    if any(token in kind for token in ("prohibit", "restriction", "forbidden")):
        return "prohibition"
    if kind in {"definition", "calculation"}:
        return "definition"
    if rule.get("mandatory") is True:
        return "obligation"
    if rule.get("mandatory") is False:
        return "permission"
    return "none"


# Categorical applicability_scope fields with a representable IR predicate.
# Each becomes a free-text string symbol checked by equality against the
# scope list's values; unlike ``jurisdictions``/``parties``/effective dates
# (retained as ``metadata`` only -- see below), these are folded into
# ``scope.predicate`` and are therefore genuinely evaluated, not merely
# recorded.  A rule listing several values for one field is satisfied when
# any of them matches (an implicit "or"); several *different* fields must
# all be satisfied (an implicit "and").
_SCOPE_DIMENSION_SYMBOLS = {
    "loan_types": "loan_type",
    "transaction_types": "transaction_type",
    "occupancy_types": "occupancy_type",
}


def _scope_dimension_symbol(symbol_id: str, rule: Mapping[str, Any], source_sha256: str) -> dict[str, Any]:
    return {
        "id": symbol_id,
        "theory": "string",
        "role": "input",
        "domain": {"kind": "string", "predicates": ["eq"]},
        "unit": None,
        "derived_expression": None,
        "provenance": _provenance(rule, source_sha256, "applicability_scope"),
    }


def _scope(rule: Mapping[str, Any], source_sha256: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    basis = rule.get("scope_basis")
    scope = rule.get("applicability_scope")
    if scope is not None and not isinstance(scope, Mapping):
        raise LoweringRefusal("INVALID_SCOPE", "applicability_scope", "Applicability scope must be an object.")
    scope = scope or {}
    dimension_formulas: list[dict[str, Any]] = []
    dimension_symbols: list[dict[str, Any]] = []
    for field, symbol_id in _SCOPE_DIMENSION_SYMBOLS.items():
        values = scope.get(field)
        if not values:
            continue
        if not isinstance(values, list) or any(not isinstance(item, str) or not item for item in values):
            raise LoweringRefusal("INVALID_SCOPE", field, f"{field!r} must be a non-empty list of non-empty strings.")
        clauses = [{"op": "eq", "left": {"symbol": symbol_id}, "right": _literal(value, "string")} for value in values]
        dimension_formulas.append(clauses[0] if len(clauses) == 1 else {"op": "or", "args": clauses})
        dimension_symbols.append(_scope_dimension_symbol(symbol_id, rule, source_sha256))
    unsupported = {
        key: value
        for key, value in scope.items()
        if value not in (None, [], "") and key not in {"jurisdictions", "jurisdiction", *_SCOPE_DIMENSION_SYMBOLS}
    }
    if unsupported:
        raise LoweringRefusal("UNREPRESENTABLE_SCOPE", "applicability_scope", f"Scope fields cannot be represented: {sorted(unsupported)}.")
    jurisdictions = scope.get("jurisdictions", scope.get("jurisdiction", rule.get("jurisdiction", [])))
    if jurisdictions is None:
        jurisdictions = []
    elif isinstance(jurisdictions, str):
        # A single-jurisdiction issuer is commonly recorded as a bare string
        # (e.g. rule["jurisdiction"] == "Fannie Mae Selling Guide") rather
        # than a one-element list; normalise without changing its meaning.
        jurisdictions = [jurisdictions] if jurisdictions else []
    if not isinstance(jurisdictions, list) or any(not isinstance(item, str) for item in jurisdictions):
        raise LoweringRefusal("INVALID_SCOPE", "jurisdiction", "Jurisdictions must be a list of strings.")
    metadata: dict[str, Any] = {
        "jurisdictions": list(jurisdictions),
        "parties": [item for item in [rule.get("responsible_party"), *(rule.get("counterparties") or [])] if item],
        "authority": None,
        "effective_from": rule.get("effective_date"),
        "effective_to": rule.get("expiration_date"),
        "document_version": rule.get("versioning_status"),
    }
    # "explicit" is the canonical value the executable-readiness prompts
    # actually declare (prompts/executable_readiness_completion.txt); the
    # other four are documented synonyms/companions accepted by
    # utils/rule_contract.py's SCOPE_BASES for the same reasons given there.
    # "inferred" and "unresolved_after_source_review" are deliberately
    # excluded: neither is a final, evidence-backed scope determination.
    if basis not in {None, "explicit", "genuinely_unscoped", "explicit_in_source", "explicitly_universal_in_source", "explicitly_none_in_source"}:
        raise LoweringRefusal("UNRESOLVED_SCOPE", "scope_basis", f"Scope basis {basis!r} is not frozen for LExec v1.")
    predicate = None
    if dimension_formulas:
        predicate = dimension_formulas[0] if len(dimension_formulas) == 1 else {"op": "and", "args": dimension_formulas}
    return {"predicate": predicate, "metadata": metadata}, dimension_symbols


def _lower_rule(rule: Mapping[str, Any], source_sha256: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rule_id = str(rule.get("rule_id") or rule.get("id") or "").strip()
    if not rule_id:
        raise LoweringRefusal("MISSING_RULE_ID", "rule", "Every lowered rule requires rule_id.")
    if not _all_references(rule):
        raise LoweringRefusal("MISSING_PROVENANCE", "source_reference", "Every lowered rule requires at least one source reference.")
    if "schema_version" in rule and rule.get("schema_version") != "2.0":
        raise LoweringRefusal("UNSUPPORTED_SOURCE_SCHEMA", "schema_version", "Only v2 source rules can be lowered to LExec IR v1.")
    if rule.get("superseded_by"):
        raise LoweringRefusal("UNREPRESENTABLE_VERSIONING", "superseded_by", "Supersession is semantically material but has no v1 effect; review is required.")
    unknown_fields = set(rule) - CONSUMED_FIELDS - set(IGNORED_FIELD_REASONS)
    if unknown_fields:
        raise LoweringRefusal("UNCLASSIFIED_FIELD", "rule", f"Input fields require an explicit classification: {sorted(unknown_fields)}.")
    hit_policy = str(rule.get("recommended_hit_policy") or "UNIQUE")
    if hit_policy not in SUPPORTED_HIT_POLICIES:
        raise LoweringRefusal("UNSUPPORTED_HIT_POLICY", "recommended_hit_policy", f"Hit policy {hit_policy!r} is not supported.")
    base_provenance = _provenance(rule, source_sha256)
    variables = { _normalise_name(item.get("name")): item for item in (rule.get("variables") or []) if isinstance(item, Mapping) and item.get("name") }
    if not variables:
        raise LoweringRefusal("MISSING_VARIABLES", "variables", "Every lowered rule requires typed variables.")
    predicates = {str(item.get("predicate_id")): item for item in (rule.get("condition_predicates") or []) if isinstance(item, Mapping) and item.get("predicate_id")}
    if not predicates:
        raise LoweringRefusal("MISSING_PREDICATES", "condition_predicates", "Every lowered rule requires one atomic predicate.")
    symbols: list[dict[str, Any]] = []
    for variable in variables.values():
        theory = _theory(variable)
        if variable.get("role") not in {"input", "derived", "output"}:
            raise LoweringRefusal("INVALID_VARIABLE_ROLE", "variable", f"Variable {variable.get('name')!r} has an invalid role.")
        if not IDENTIFIER.fullmatch(_safe_identifier(variable.get("name"))):
            raise LoweringRefusal("INVALID_SYMBOL_ID", "variable", f"Variable {variable.get('name')!r} cannot become an IR symbol id.")
        refs = _provenance(rule, source_sha256, "condition_predicates" if variable.get("role") != "output" else "outcomes")
        symbols.append({
            "id": _safe_identifier(variable["name"]),
            "theory": theory,
            "role": variable.get("role"),
            "domain": _domain(variable, theory, list(predicates.values())),
            "unit": variable.get("unit"),
            "derived_expression": None,
            "provenance": refs,
        })
    condition = _logic(rule.get("condition_logic"), predicates, variables)
    effects: list[dict[str, Any]] = []
    outcomes = rule.get("outcomes")
    if not isinstance(outcomes, list) or not outcomes:
        raise LoweringRefusal("MISSING_OUTCOMES", "outcomes", "Every lowered rule requires one outcome.")
    outcome_targets: set[str] = set()
    for outcome in outcomes:
        if not isinstance(outcome, Mapping):
            raise LoweringRefusal("INVALID_OUTCOME", "outcomes", "Outcome must be an object.")
        target_name = _normalise_name(outcome.get("variable"))
        target = variables.get(target_name)
        if target is None or target.get("role") != "output":
            raise LoweringRefusal("INVALID_OUTCOME_TARGET", "outcomes", f"Outcome target {target_name!r} is not a declared output.")
        if target_name in outcome_targets:
            raise LoweringRefusal("DUPLICATE_OUTCOME_TARGET", "outcomes", f"Outcome target {target_name!r} is assigned more than once.")
        outcome_targets.add(target_name)
        if outcome.get("operator") != "=":
            raise LoweringRefusal("UNSUPPORTED_OUTCOME_OPERATOR", "outcomes", "Only assignment outcomes are supported.")
        if outcome.get("value_type") == "enum" and outcome.get("value") not in (target.get("allowed_values") or []):
            raise LoweringRefusal("ENUM_VALUE_OUT_OF_DOMAIN", "outcomes", f"Outcome value {outcome.get('value')!r} is not in {target_name!r}'s enum domain.")
        effects.append({
            "kind": "assignment",
            "modality": _modality(rule),
            "target": _safe_identifier(target_name),
            "value": _operand(outcome.get("value"), str(outcome.get("value_type") or ""), variables),
            "provenance": _provenance(rule, source_sha256, "outcomes"),
        })
    exceptions: list[dict[str, Any]] = []
    for index, exception in enumerate(rule.get("exceptions") or []):
        if not isinstance(exception, Mapping):
            raise LoweringRefusal("INVALID_EXCEPTION", "exceptions", "Exception must be a predicate object.")
        exceptions.append({
            "id": str(exception.get("predicate_id") or f"exception_{index + 1}"),
            "condition": _formula_for_predicate(exception, variables),
            "provenance": _provenance(rule, source_sha256, "exceptions"),
        })
    scope, scope_symbols = _scope(rule, source_sha256)
    lowered = {
        "id": rule_id,
        "scope": scope,
        "condition": condition,
        "exceptions": exceptions,
        "effects": effects,
        "provenance": base_provenance,
    }
    return lowered, [*symbols, *scope_symbols]


def _refusal(rule: Mapping[str, Any], source_sha256: str, exc: LoweringRefusal) -> dict[str, Any]:
    return {
        "rule_id": str(rule.get("rule_id") or rule.get("id") or "") or None,
        "code": exc.code,
        "construct": exc.construct,
        "detail": exc.detail,
        "requires_review": True,
        "provenance": _provenance(rule, source_sha256),
    }


def lower_graph(
    graph: Any,
    *,
    document_id: str | None = None,
    source_sha256: str | None = None,
    source_paths: Sequence[str] | None = None,
    corpus_id: str | None = None,
    split: str | None = None,
) -> dict[str, Any]:
    """Lower a v2 graph, refusing each rule that cannot be represented.

    The result always has the complete v1 envelope.  A refused rule is never
    partially emitted; it appears only in ``refusals`` with
    ``requires_review: true``.  This makes downstream backends safe to run on
    the returned ``rules`` collection.
    """

    digest = _source_hash(graph, source_sha256)
    rules = _iter_rules(graph)
    paths = list(source_paths or [])
    if not paths:
        paths = sorted({str(ref.get("chunk_path")) for rule in rules for ref in _all_references(rule) if ref.get("chunk_path")})
    if not paths:
        paths = ["<synthetic-input>"]
    ir: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "document_unit": {
            "document_id": document_id or "lowered-graph",
            "source_sha256": digest,
            "source_paths": paths,
            "corpus_id": corpus_id,
            "split": split,
        },
        "semantics": {
            "null_model": NULL_MODEL,
            "unknown_at_table_boundary": "refuse",
            "exception_reading": "defeater_or",
        },
        "symbols": [],
        "rules": [],
        "tables": [],
        "refusals": [],
        "ignored_fields": [],
    }
    symbol_by_id: dict[str, dict[str, Any]] = {}
    for rule in rules:
        rule_id = str(rule.get("rule_id") or rule.get("id") or "") or None
        for field, reason in IGNORED_FIELD_REASONS.items():
            if field in rule:
                ir["ignored_fields"].append({"rule_id": rule_id, "field": field, "reason": reason})
        try:
            lowered, symbols = _lower_rule(rule, digest)
        except LoweringRefusal as exc:
            ir["refusals"].append(_refusal(rule, digest, exc))
            continue
        ir["rules"].append(lowered)
        pending_symbols: dict[str, dict[str, Any]] = {}
        conflict: str | None = None
        for symbol in symbols:
            existing = symbol_by_id.get(symbol["id"]) or pending_symbols.get(symbol["id"])
            if existing is None:
                pending_symbols[symbol["id"]] = symbol
            elif _canonical({k: existing[k] for k in ("theory", "role", "domain", "unit")}) != _canonical({k: symbol[k] for k in ("theory", "role", "domain", "unit")}):
                conflict = symbol["id"]
                break
        if conflict is not None:
            ir["refusals"].append(_refusal(rule, digest, LoweringRefusal("SYMBOL_CONFLICT", "symbol", f"Symbol {conflict!r} has incompatible declarations.")))
            ir["rules"].pop()
            continue
        symbol_by_id.update(pending_symbols)
    ir["symbols"] = sorted(symbol_by_id.values(), key=lambda item: item["id"])
    groups: dict[tuple[tuple[str, ...], str], list[str]] = defaultdict(list)
    for rule in ir["rules"]:
        signature = tuple(sorted(effect["target"] for effect in rule["effects"]))
        source_rule = next((item for item in rules if str(item.get("rule_id") or item.get("id")) == rule["id"]), {})
        hit_policy = str(source_rule.get("recommended_hit_policy") or "UNIQUE")
        if hit_policy not in SUPPORTED_HIT_POLICIES:
            ir["refusals"].append(_refusal(source_rule, digest, LoweringRefusal("UNSUPPORTED_HIT_POLICY", "recommended_hit_policy", f"Hit policy {hit_policy!r} is not supported.")))
            continue
        groups[(signature, hit_policy)].append(rule["id"])
    for index, ((signature, hit_policy), rule_ids) in enumerate(sorted(groups.items(), key=lambda item: (item[0][0], item[0][1]))):
        ir["tables"].append({
            "id": f"table_{index + 1}",
            "rule_ids": sorted(rule_ids),
            "output_signature": list(signature),
            "hit_policy": hit_policy,
            "policy_proof": {
                "status": "unknown",
                "method": "unproved",
                "solver": None,
                "query_sha256": None,
                "witnesses": [],
            },
        })
    errors = validate_ir(ir)
    if errors:
        raise ValueError("lowered IR failed v1 validation: " + "; ".join(errors))
    return ir


def _validate_operand(value: Any, symbols: Mapping[str, Mapping[str, Any]], path: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, Mapping):
        return [f"{path}: operand must be an object"]
    if set(value) == {"symbol"}:
        symbol = value.get("symbol")
        if not isinstance(symbol, str) or symbol not in symbols:
            errors.append(f"{path}: unknown symbol {symbol!r}")
        return errors
    literal_type = value.get("type")
    if set(value) != {"literal", "type"} or not isinstance(literal_type, str) or literal_type not in SUPPORTED_THEORIES | {"null"}:
        return [f"{path}: malformed literal operand"]
    literal = value.get("literal")
    if literal_type == "null" and literal is not None:
        errors.append(f"{path}: null literal must be null")
    if literal_type == "bool" and not isinstance(literal, bool):
        errors.append(f"{path}: bool literal is not boolean")
    if literal_type in {"int", "real"} and (isinstance(literal, bool) or not isinstance(literal, (int, float)) or not math.isfinite(literal)):
        errors.append(f"{path}: numeric literal is invalid")
    if literal_type in {"enum", "string"} and not isinstance(literal, str):
        errors.append(f"{path}: text literal is not a string")
    return errors


def _validate_formula(value: Any, symbols: Mapping[str, Mapping[str, Any]], path: str = "formula") -> list[str]:
    if not isinstance(value, Mapping):
        return [f"{path}: formula must be an object"]
    op = value.get("op")
    errors: list[str] = []
    if not isinstance(op, str):
        return [f"{path}: unsupported formula operator {op!r}"]
    if op in {"and", "or"}:
        args = value.get("args")
        if not isinstance(args, list) or not args:
            return [f"{path}: {op} requires non-empty args"]
        for index, arg in enumerate(args):
            errors.extend(_validate_formula(arg, symbols, f"{path}.args[{index}]"))
    elif op == "not":
        errors.extend(_validate_formula(value.get("arg"), symbols, f"{path}.arg"))
    elif op == "is_null":
        errors.extend(_validate_operand(value.get("arg"), symbols, f"{path}.arg"))
    elif op in {"eq", "ne", "lt", "le", "gt", "ge", "contains", "in_binned_range"}:
        errors.extend(_validate_operand(value.get("left"), symbols, f"{path}.left"))
        errors.extend(_validate_operand(value.get("right"), symbols, f"{path}.right"))
    else:
        errors.append(f"{path}: unsupported formula operator {op!r}")
    return errors


def validate_ir(ir: Any) -> list[str]:
    """Return deterministic structural/semantic errors for an LExec IR value."""

    if not isinstance(ir, Mapping):
        return ["IR must be an object"]
    required = {"schema_version", "document_unit", "semantics", "symbols", "rules", "tables", "refusals", "ignored_fields"}
    errors = [f"missing top-level field {key}" for key in sorted(required - set(ir))]
    if set(ir) - required:
        errors.append("unexpected top-level fields: " + ", ".join(sorted(set(ir) - required)))
    if ir.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version must be lexec-ir/1.0")
    unit = ir.get("document_unit")
    if not isinstance(unit, Mapping) or not isinstance(unit.get("document_id"), str) or not HEX64.fullmatch(str(unit.get("source_sha256", ""))) or not isinstance(unit.get("source_paths"), list) or not unit["source_paths"]:
        errors.append("document_unit is malformed")
    semantics = ir.get("semantics")
    if not isinstance(semantics, Mapping):
        errors.append("semantics must be an object")
    else:
        if semantics.get("null_model") != NULL_MODEL:
            errors.append("semantics.null_model must be kleene_three_valued")
        if not isinstance(semantics.get("unknown_at_table_boundary"), str) or semantics.get("unknown_at_table_boundary") not in {"refuse", "no_match", "explicit_unknown"}:
            errors.append("semantics.unknown_at_table_boundary is invalid")
        if not isinstance(semantics.get("exception_reading"), str) or semantics.get("exception_reading") not in {"unset", "defeater_or", "conjunctive", "ignored"}:
            errors.append("semantics.exception_reading is invalid")
    raw_symbols = ir.get("symbols")
    if not isinstance(raw_symbols, list):
        errors.append("symbols must be an array")
    symbols = raw_symbols if isinstance(raw_symbols, list) else []
    symbol_map: dict[str, Mapping[str, Any]] = {}
    for index, symbol in enumerate(symbols):
        path = f"symbols[{index}]"
        if not isinstance(symbol, Mapping) or not IDENTIFIER.fullmatch(str(symbol.get("id", ""))):
            errors.append(f"{path}: malformed symbol")
            continue
        if symbol["id"] in symbol_map:
            errors.append(f"{path}: duplicate symbol id")
        symbol_map[symbol["id"]] = symbol
        if not isinstance(symbol.get("theory"), str) or symbol.get("theory") not in SUPPORTED_THEORIES or not isinstance(symbol.get("role"), str) or symbol.get("role") not in {"input", "derived", "output"}:
            errors.append(f"{path}: invalid theory or role")
        raw_symbol_provenance = symbol.get("provenance")
        if not isinstance(raw_symbol_provenance, list) or not raw_symbol_provenance:
            errors.append(f"{path}: provenance is required")
            raw_symbol_provenance = []
        for span_index, span in enumerate(raw_symbol_provenance):
            errors.extend(_validate_span(span, f"{path}.provenance[{span_index}]"))
    raw_rules = ir.get("rules")
    if not isinstance(raw_rules, list):
        errors.append("rules must be an array")
    rule_ids: set[str] = set()
    for index, rule in enumerate(raw_rules if isinstance(raw_rules, list) else []):
        path = f"rules[{index}]"
        if not isinstance(rule, Mapping) or not isinstance(rule.get("id"), str) or not rule["id"]:
            errors.append(f"{path}: malformed rule")
            continue
        if rule["id"] in rule_ids:
            errors.append(f"{path}: duplicate rule id")
        rule_ids.add(rule["id"])
        errors.extend(_validate_formula(rule.get("condition"), symbol_map, f"{path}.condition"))
        raw_effects = rule.get("effects")
        if not isinstance(raw_effects, list) or not raw_effects:
            errors.append(f"{path}: effects are required")
            effects = []
        else:
            effects = raw_effects
        effect_targets: set[str] = set()
        for effect_index, effect in enumerate(effects):
            ep = f"{path}.effects[{effect_index}]"
            if not isinstance(effect, Mapping):
                errors.append(f"{ep}: malformed effect")
                continue
            if effect.get("kind") != "assignment" or not isinstance(effect.get("modality"), str) or effect.get("modality") not in SUPPORTED_MODALITIES:
                errors.append(f"{ep}: malformed effect")
            target = effect.get("target")
            if isinstance(target, str):
                if target in effect_targets:
                    errors.append(f"{ep}: duplicate effect target {target!r}")
                effect_targets.add(target)
            if not isinstance(target, str) or target not in symbol_map or symbol_map[target].get("role") != "output":
                errors.append(f"{ep}: target is not an output symbol")
            errors.extend(_validate_operand(effect.get("value"), symbol_map, f"{ep}.value"))
        raw_rule_provenance = rule.get("provenance", [])
        if not isinstance(raw_rule_provenance, list):
            errors.append(f"{path}.provenance: provenance must be an array")
            raw_rule_provenance = []
        for span_index, span in enumerate(raw_rule_provenance):
            errors.extend(_validate_span(span, f"{path}.provenance[{span_index}]"))
        raw_exceptions = rule.get("exceptions", [])
        if not isinstance(raw_exceptions, list):
            errors.append(f"{path}.exceptions: exceptions must be an array")
            raw_exceptions = []
        for exception_index, exception in enumerate(raw_exceptions):
            if not isinstance(exception, Mapping):
                errors.append(f"{path}.exceptions[{exception_index}]: exception must be an object")
                continue
            errors.extend(_validate_formula(exception.get("condition"), symbol_map, f"{path}.exceptions[{exception_index}].condition"))
    raw_tables = ir.get("tables")
    if not isinstance(raw_tables, list):
        errors.append("tables must be an array")
    for index, table in enumerate(raw_tables if isinstance(raw_tables, list) else []):
        path = f"tables[{index}]"
        if not isinstance(table, Mapping):
            errors.append(f"{path}: malformed table")
            continue
        table_rule_ids = table.get("rule_ids")
        if not isinstance(table_rule_ids, list) or not table_rule_ids:
            errors.append(f"{path}: rule_ids must be a non-empty array")
        elif any(not isinstance(rid, str) or not rid for rid in table_rule_ids):
            errors.append(f"{path}: rule_ids must contain non-empty strings")
        else:
            errors.extend(f"{path}: unknown rule id {rid!r}" for rid in table_rule_ids if rid not in rule_ids)
        if not isinstance(table.get("hit_policy"), str) or table.get("hit_policy") not in SUPPORTED_HIT_POLICIES:
            errors.append(f"{path}: invalid hit policy")
    raw_refusals = ir.get("refusals")
    if not isinstance(raw_refusals, list):
        errors.append("refusals must be an array")
    for index, refusal in enumerate(raw_refusals if isinstance(raw_refusals, list) else []):
        path = f"refusals[{index}]"
        if not isinstance(refusal, Mapping) or refusal.get("requires_review") is not True or not re.fullmatch(r"[A-Z][A-Z0-9_]+", str(refusal.get("code", ""))):
            errors.append(f"{path}: malformed refusal")
            continue
        raw_refusal_provenance = refusal.get("provenance", [])
        if not isinstance(raw_refusal_provenance, list):
            errors.append(f"{path}.provenance: provenance must be an array")
            raw_refusal_provenance = []
        for span_index, span in enumerate(raw_refusal_provenance):
            errors.extend(_validate_span(span, f"{path}.provenance[{span_index}]"))
    raw_ignored = ir.get("ignored_fields")
    if not isinstance(raw_ignored, list):
        errors.append("ignored_fields must be an array")
    for index, ignored in enumerate(raw_ignored if isinstance(raw_ignored, list) else []):
        path = f"ignored_fields[{index}]"
        if not isinstance(ignored, Mapping) or not isinstance(ignored.get("field"), str) or not isinstance(ignored.get("reason"), str) or ignored.get("reason") not in {"NON_EXECUTABLE_METADATA", "AUDIT_STATUS_NOT_EXECUTABLE"}:
            errors.append(f"{path}: malformed ignored-field classification")
    return errors


def _validate_span(span: Any, path: str) -> list[str]:
    if not isinstance(span, Mapping):
        return [f"{path}: span must be an object"]
    if not all(isinstance(span.get(key), str) and span.get(key) for key in ("chunk_path", "section_id")):
        return [f"{path}: span source identifiers are required"]
    if not isinstance(span.get("start_offset"), int) or not isinstance(span.get("end_offset"), int) or span["start_offset"] < 0 or span["end_offset"] <= span["start_offset"]:
        return [f"{path}: span offsets are invalid"]
    if not HEX64.fullmatch(str(span.get("source_sha256", ""))):
        return [f"{path}: span source_sha256 is invalid"]
    return []


def assert_valid_ir(ir: Any) -> None:
    """Raise ``ValueError`` if *ir* is not valid LExec IR v1."""

    errors = validate_ir(ir)
    if errors:
        raise ValueError("; ".join(errors))
