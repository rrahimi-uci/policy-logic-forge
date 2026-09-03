#!/usr/bin/env python3
"""agent_07: evidence-backed completion for DMN/BPMN-ready graph rules."""

from __future__ import annotations

import json
import hashlib
import os
import re
import sys
import threading
import time
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.citations import normalise_text, repair_citation
from utils.config import get_config
from utils.feel_expression import compile_feel_expression, evaluate_feel_expression
from utils.rule_dependencies import prune_dangling_related_rules, revalidate_graph
from utils.rule_gating import make_entailment_oracle
from utils.kg_readiness import (
    CANONICAL_ENTITY_RE,
    cited_sections,
    corpus_manifest,
    dependency_edges,
    derive_dependency_chains,
    entity_rule_groups,
    final_rule_issues,
    mark_readiness,
    naming_issues,
    referential_integrity_issues,
    source_document_index,
    source_document_roots,
)
from utils.llm_client import create_llm_client
from utils.prompt_manager import get_prompt_manager
from utils.rule_contract import annotate_rule_contract, quarantine_non_actor_counterparties
from utils.rule_contract import EXCEPTION_BASES, FACT_ID_RE, SCOPE_BASES, validate_rule_v2
from utils.scope import newly_populated_dimension_count, populated_scope
from utils.semantic_routing import bpmn_eligibility

# Completion fields that every downstream reader (kg_readiness.final_rule_issues,
# this module's own searched_chunk_count/corpus_sha256 stamping) treats as a
# structured object and calls .get() on directly. A resolver returning anything
# else for one of these — a plain string, most often — must not overwrite the
# rule's existing value; see the two field-copy loops in this file.
_DICT_SHAPED_COMPLETION_FIELDS = {"exception_verification", "scope_derivation", "applicability_scope"}

_TRANSIENT_CONFLICT_ERROR_MARKERS = (
    "timeout",
    "timed out",
    "connection",
    "socket",
    "internalservererror",
    "internal server error",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "server error",
    " overloaded",
    "overloaded_error",
    " 500",
    " 502",
    " 503",
    " 504",
)


def _is_transient_conflict_error(exc: BaseException) -> bool:
    """Return whether a conflict-analysis failure is safe to retry.

    Conflict analysis is an auxiliary request: a provider timeout should not
    permanently become an unresolved business conflict when a bounded retry
    can recover it.  Provider SDK exceptions do not share one common type, so
    classify by the standard HTTP status attribute plus transport/backpressure
    markers while leaving validation and content-policy errors fail-closed.
    """

    status = getattr(exc, "status_code", None)
    try:
        if status is not None and int(status) >= 500:
            return True
    except (TypeError, ValueError):
        pass
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in text for marker in _TRANSIENT_CONFLICT_ERROR_MARKERS)


def _analyse_entity_with_retries(
    analyser,
    entity: str,
    summaries: list[Mapping[str, Any]],
    *,
    scope_label: str,
    attempts: int | None = None,
    backoff_seconds: float | None = None,
    sleep_fn=time.sleep,
):
    """Run one conflict-analysis request with bounded transient retries."""

    if attempts is None:
        try:
            attempts = max(1, int(os.getenv("KG_CONFLICT_ANALYSIS_ATTEMPTS", "3")))
        except (TypeError, ValueError):
            attempts = 3
    if backoff_seconds is None:
        try:
            backoff_seconds = max(0.0, float(os.getenv("KG_CONFLICT_ANALYSIS_BACKOFF_SECONDS", "10")))
        except (TypeError, ValueError):
            backoff_seconds = 10.0

    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return analyser(entity, summaries)
        except Exception as exc:
            last_error = exc
            if attempt >= attempts or not _is_transient_conflict_error(exc):
                raise
            delay = backoff_seconds * (2 ** (attempt - 1))
            print(
                f"⚠️ agent_07 transient conflict-analysis error for {scope_label!r}; "
                f"retry {attempt + 1}/{attempts} in {delay:g}s ({exc})",
                flush=True,
            )
            sleep_fn(delay)
    # The loop always returns or raises; keep a defensive raise for static
    # type checkers and unusual custom iterables for ``attempts``.
    assert last_error is not None
    raise last_error


def _build_token_index(search_chunks: list[tuple[Mapping[str, Any], str, str]]) -> dict[str, list[int]]:
    """Build an inverted token/marker index for bounded evidence retrieval."""
    index: dict[str, list[int]] = {}
    for position, (_chunk, lower, path_lower) in enumerate(search_chunks):
        tokens = set(re.findall(r"[a-z][a-z0-9_-]{3,}", lower))
        tokens.update(re.findall(r"[a-z][a-z0-9_-]{3,}", path_lower))
        # Paths encode useful source identity using underscores and numeric
        # prefixes (``1070_wnep_com``). Keep the original tokens for stable
        # compatibility, but also index separator-delimited components so a
        # rule mentioning ``WNEP`` can retrieve its own package without a
        # domain-specific map.
        tokens.update(re.findall(r"[a-z][a-z0-9]{2,}", re.sub(r"[^a-z0-9]+", " ", path_lower)))
        normalized_path = re.sub(r"[^a-z0-9]", "", path_lower)
        if normalized_path:
            tokens.add("__pathnorm__:" + normalized_path)
        for marker in ("except", "unless", "notwithstanding", "however", "waiver", "exempt"):
            if marker in lower:
                tokens.add("__marker__:" + marker)
        for token in tokens:
            index.setdefault(token, []).append(position)
    return index


def _conflict_batch_groups(
    member_ids: list[str],
    outcome_variables,
    max_rules_per_call: int,
) -> list[list[str]]:
    """Partition overlapping-rule components without duplicate model work.

    A rule can assign several output variables, so independently batching each
    variable sends the same rule repeatedly (and scales badly for generic
    entities such as ``DATA_CONTROLLER``). Build connected components of the
    output-variable overlap graph, then split each component into bounded
    deterministic batches. Pairs crossing a batch boundary remain covered by
    the caller's fail-closed unresolved fallback.
    """
    limit = max(2, int(max_rules_per_call))
    ids = sorted({str(rule_id) for rule_id in member_ids})
    buckets: dict[str, set[str]] = {}
    for rule_id in ids:
        for variable in outcome_variables(rule_id):
            buckets.setdefault(str(variable), set()).add(rule_id)

    adjacency = {rule_id: set() for rule_id in ids}
    for bucket in buckets.values():
        if len(bucket) < 2:
            continue
        for rule_id in bucket:
            adjacency[rule_id].update(bucket - {rule_id})

    components: list[list[str]] = []
    unvisited = set(ids)
    while unvisited:
        root = min(unvisited)
        stack = [root]
        unvisited.remove(root)
        component: list[str] = []
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbour in sorted(adjacency[current] & unvisited, reverse=True):
                unvisited.remove(neighbour)
                stack.append(neighbour)
        component.sort()
        if len(component) >= 2:
            components.append(component)

    return [component[start:start + limit] for component in components for start in range(0, len(component), limit)]


def _conflict_candidate_pairs(
    member_ids: list[str],
    overlapping_ids: set[str],
    max_rules_per_call: int,
) -> set[tuple[str, str]] | None:
    """Return pairs needing coverage, or ``None`` when pair expansion is unsafe.

    Small groups retain exact pair coverage.  For a large source-scoped group,
    rules whose output variables are pairwise disjoint are mechanically safe;
    only pairs touching an overlapping-output rule can be ambiguous.  Even
    that reduced cartesian product can be enormous for pathological graphs, so
    callers fail closed with one unresolved group instead of materialising an
    unbounded set.
    """
    ids = sorted({str(rule_id) for rule_id in member_ids})
    if len(ids) <= max(2, int(max_rules_per_call)):
        return set(combinations(ids, 2))
    overlap = sorted(set(str(rule_id) for rule_id in overlapping_ids) & set(ids))
    if len(overlap) < 1:
        return set()
    try:
        max_pairs = max(1, int(os.getenv("KG_CONFLICT_MAX_COVERAGE_PAIRS", "10000")))
    except (TypeError, ValueError):
        max_pairs = 10000
    if len(overlap) * (len(ids) - 1) > max_pairs:
        return None
    return {
        tuple(sorted((rule_id, other)))
        for rule_id in overlap
        for other in ids
        if other != rule_id
    }


class EvidenceResolver(Protocol):
    def complete_rule(self, rule: Mapping[str, Any], corpus: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def complete_rules(self, rules: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]: ...
    def analyse_entity(self, entity: str, rules: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]: ...


class OpenAIEvidenceResolver:
    """Source interpreter. It never performs graph/corpus integrity decisions."""

    def __init__(self, api_key: str, model: str, reasoning_effort: str) -> None:
        try:
            readiness_concurrency = max(1, int(os.getenv("KG_READINESS_LLM_CONCURRENCY", "32")))
        except (TypeError, ValueError):
            readiness_concurrency = 32
        self.readiness_concurrency = readiness_concurrency
        self.client = create_llm_client(
            api_key=api_key,
            model=model,
            concurrency=readiness_concurrency,
        )
        self.reasoning_effort = reasoning_effort
        self.prompts = get_prompt_manager()

    @staticmethod
    def _parse(content: str) -> Mapping[str, Any]:
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        try:
            value = json.loads(content)
        except json.JSONDecodeError as original_error:
            # JSON mode still occasionally returns a single trailing comma or
            # unterminated delimiter. Repair only that one object; strict mode
            # rejects concatenated top-level values and non-object payloads.
            try:
                from json_repair import repair_json

                value = repair_json(content, return_objects=True, strict=True)
            except Exception:
                raise original_error
        if not isinstance(value, Mapping):
            raise ValueError("readiness response must be an object")
        return value

    def _json_completion(self, prompt: str, max_tokens: int) -> Mapping[str, Any]:
        """Request JSON with bounded retries for occasional malformed model output."""
        attempts = max(1, int(os.getenv("KG_READINESS_PARSE_ATTEMPTS", "3")))
        retry_prompt = prompt
        last_error: Exception | None = None
        for attempt in range(attempts):
            response = self.client.chat_completion(
                messages=[{"role": "user", "content": retry_prompt}], temperature=0,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                reasoning_effort=self.reasoning_effort,
            )
            content = response.choices[0].message.content or ""
            try:
                return self._parse(content)
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                last_error = exc
                retry_prompt = (
                    prompt
                    + "\n\nYour previous response was not valid JSON. Retry now. "
                    "Return one complete JSON object only, with double-quoted keys and strings; "
                    "do not include markdown fences or explanatory text."
                )
                if attempt + 1 < attempts:
                    print(f"⚠️ Readiness JSON parse retry {attempt + 1}/{attempts - 1}", flush=True)
        assert last_error is not None
        raise last_error

    def complete_rule(self, rule: Mapping[str, Any], corpus: Mapping[str, Any]) -> Mapping[str, Any]:
        prompt = self.prompts.format_prompt(
            "executable_readiness_completion",
            rule_json=json.dumps(rule, ensure_ascii=False),
            corpus_json=json.dumps(corpus, ensure_ascii=False),
        )
        return self._json_completion(prompt, int(os.getenv("KG_READINESS_MAX_TOKENS", "6000")))

    def complete_rules(self, rules: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        prompt = self.prompts.format_prompt(
            "executable_readiness_batch_completion",
            rules_json=json.dumps(rules, ensure_ascii=False),
        )
        value = self._json_completion(prompt, int(os.getenv("KG_READINESS_BATCH_MAX_TOKENS", "16000")))
        completions = value.get("completions", [])
        return completions if isinstance(completions, list) else []

    def analyse_entity(self, entity: str, rules: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        prompt = self.prompts.format_prompt(
            "entity_conflict_analysis",
            entity_key=entity,
            rules_json=json.dumps(rules, ensure_ascii=False),
        )
        value = self._json_completion(prompt, int(os.getenv("KG_CONFLICT_MAX_TOKENS", "6000")))
        analyses = value.get("analyses", [])
        return analyses if isinstance(analyses, list) else []


_READINESS_RULE_FIELDS = (
    "rule_id", "rule_name", "rule_type", "description", "condition_predicates",
    "condition_logic", "condition_basis", "outcomes", "variables", "recommended_hit_policy",
    "versioning_status", "applicability_scope", "scope_basis", "inference_reasoning",
    "responsible_party", "counterparties", "exceptions", "exception_effects", "exception_basis",
    "exception_verification", "scope_derivation", "source_reference", "test_vectors",
    "workflow_semantics",
)


def _compact_readiness_rule(rule: Mapping[str, Any]) -> dict[str, Any]:
    """Keep resolver requests bounded without changing the persisted rule.

    Optimizer annotations (dependency arrays, entity definitions, prior
    readiness reports, and field-evidence duplicates) can dominate a request
    while adding no information to the evidence completion task. The complete
    rule remains the fingerprint/output source; only this transport projection
    is compacted.
    """
    return {
        field: deepcopy(rule[field])
        for field in _READINESS_RULE_FIELDS
        if field in rule
    }


def _project_execution(rule: Mapping[str, Any]) -> dict[str, Any]:
    """Project decisions mechanically and workflows only from explicit order.

    A responsible party and an output make a decision assignable, but do not
    establish a process. BPMN therefore requires source-evidenced
    ``workflow_semantics``; absent or ambiguous workflows stay in DMN and may
    be routed to CMMN review instead of being fabricated as a linear process.
    """
    variables = [item for item in rule.get("variables", []) if isinstance(item, Mapping)]
    inputs = [str(item.get("name")) for item in variables if item.get("role") in {"input", "derived"}]
    outputs = [str(item.get("name")) for item in variables if item.get("role") == "output"]
    unconditional = (
        rule.get("condition_logic") == {"constant": True}
        and rule.get("condition_basis") == "unconditional_explicit_in_source"
    )
    targets = ["DMN"] if outputs and (inputs or unconditional) else []
    execution: dict[str, Any] = {"targets": targets}
    if "DMN" in targets:
        execution["dmn"] = {"input_columns": inputs, "output_columns": outputs, "hit_policy": rule.get("recommended_hit_policy")}
    eligible, omission_reasons = bpmn_eligibility(rule, require_certified=False)
    if eligible:
        targets.append("BPMN")
        workflow = rule["workflow_semantics"]
        execution["bpmn"] = {
            "lane": workflow.get("actor_role"),
            "trigger_event": workflow.get("trigger_event"),
            "ordered_steps": deepcopy(workflow.get("ordered_steps", [])),
            "basis": workflow.get("basis"),
        }
    else:
        execution["bpmn_omission_reasons"] = omission_reasons
    return execution


LEGACY_ENTITY_NAMES = {
    "ManufacturedHome": "MANUFACTURED_HOME",
    "MortgageBackedSecurity": "MORTGAGE_BACKED_SECURITY",
    "MortgagePool": "MORTGAGE_POOL",
    "RepresentationAndWarranty": "REPRESENTATION_AND_WARRANTY",
    "SecurityInstrument": "SECURITY_INSTRUMENT",
    "SpecialFeatureCode": "SPECIAL_FEATURE_CODE",
}

LEGACY_VALUE_TYPES = {
    # JSON/model schemas frequently distinguish integer from number, while
    # Rule Contract v2 deliberately uses one numeric type.  This conversion
    # loses no precision: the integral allowed_range/value remains intact.
    "integer": "number",
    "array": "list",
    "enum_array": "list",
    "enum_list": "list",
    # "enum_set" (a set of enum values checked with "in", e.g. a predicate
    # over {"detached dwelling", "condo unit", ...}) is the exact same shape
    # as the already-mapped "enum_array"/"string_array" -- just another
    # plural the model reached for. Found via a real mortgage run: this was
    # the single condition_predicates[].value_type behind a hard
    # schema_consistency invariant failure that also fanned out into four
    # separate false grounding-claim failures for the same rule (variable,
    # execution, classification, entity_attachment all share
    # deterministic_rule_claims' validate_rule_v2 fallback check).
    "enum_set": "list",
    # Same shape again, found on a real mortgage-v2 run: a set of numbers
    # checked with "in" (e.g. loan_term_years in [10, 15, 20, 30]) is
    # "number_array" with a different name, not a distinct type.
    "number_set": "list",
    "number_array": "list",
    "list_number": "list",
    "number_list": "list",
    "string_array": "list",
    "string_list": "list",
    # A single categorical value (e.g. transaction_type == "not_assumed"),
    # as opposed to enum_set/enum_array's set-of-values shape above.
    "enum_value": "enum",
    # A [min, max] pair, e.g. property_unit_count between [1, 4].
    "number_range": "range",
    # Models occasionally use the prompt's descriptive ``free_text`` label
    # where the v2 contract requires the canonical ``string`` value_type.
    "free_text": "string",
    # ``text`` is a common model synonym for a free-form string in exception
    # predicates.  It carries no additional semantics and is safe to map to
    # the v2 contract's canonical string value type.
    "text": "string",
    # ``source_text`` is the extraction label for a literal explanation in an
    # exception. It has the same runtime shape as the contract's string type.
    "source_text": "string",
    # A bare ``set`` is another extraction spelling for a membership list.
    # The v2 contract intentionally has one collection type (``list``), so
    # this alias is safe for both enum and scalar membership predicates.
    "set": "list",
    # A membership predicate over a declared enum is represented by the
    # contract's list value type; ``enum_reference`` is an extraction-only
    # label for that same literal set.
    "enum_reference": "list",
    # Structured lookup outcomes have appeared under both spellings in real
    # provider output. They are not scalar literals and therefore must not be
    # coerced to string. ``conditional_map`` is the pipeline's canonical
    # review-only spelling: validation still records the unsupported lowering
    # capability, while readiness treats it as deferred instead of failing the
    # entire graph schema invariant.
    "mapping": "conditional_map",
    "conditional_mapping": "conditional_map",
}
# Deliberately NOT normalised: outcome value_types "formula"/"expression"
# (e.g. "min(0.10 * new_refinance_loan_balance, 15000)") and "object" (a
# dict-shaped lookup table). Unlike the aliases above, these aren't a
# renamed spelling of an existing scalar value_type -- they're a genuinely
# different, currently-unsupported shape (a computed expression or a
# structured lookup, not a literal constant). Coercing them to "string"
# would pass validation but silently misrepresent them to any downstream
# consumer (DMN/BPMN, LExec IR) that assumes value_type "string" means a
# literal value -- exactly the kind of silent approximation this pipeline's
# fail-closed philosophy exists to prevent. These rules correctly stay
# flagged for review until the v2 contract gains real support for computed
# outcome values.

LEGACY_OPERATORS = {
    "=": "==",
    "not in": "not_in",
    "BETWEEN": "in",
    # "contains_any" is the model's reasonable-but-undocumented name for
    # exactly what "in" already means (does the actual value match any of a
    # given set) — same cross-pollination pattern as the other legacy
    # aliases here, just for operators instead of value/variable types.
    "contains_any": "in",
    "IN": "in",
    "NOT_IN": "not_in",
    # ``excludes`` is the natural-language spelling emitted for a string
    # exclusion predicate.  It has the same closed-world meaning as the
    # contract's ``not_in`` operator and is safe to canonicalize.
    "excludes": "not_in",
}

LEGACY_VARIABLE_ROLES = {
    # Exception-only roles are descriptive extraction labels, not separate
    # runtime types.  Their values still participate as ordinary inputs or
    # outputs in the v2 rule contract.
    "exception_trigger": "input",
    "exception_input": "input",
    "exception_output": "output",
}


def _to_screaming_snake_case(name: str) -> str:
    """CreditScore -> CREDIT_SCORE; PostClosingQCReview -> POST_CLOSING_QC_REVIEW.

    Verified against all 24 entity names from one real extraction run,
    including acronym runs (QC) and short words (Of) — every already-canonical
    name passes through unchanged, so applying this to a name that doesn't
    need it is always a no-op.
    """
    step1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    step2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", step1)
    # Collapse any run of underscores/non-alphanumerics the substitutions above
    # can introduce next to a name's own separators (e.g. "Mixed_Case" already
    # has an underscore where step1 also inserts one) and strip the ends, so
    # the result always matches CANONICAL_ENTITY_RE rather than failing it
    # with a double underscore.
    step3 = re.sub(r"[^A-Za-z0-9]+", "_", step2).strip("_")
    return step3.upper()


def _build_entity_name_map(graph: Any) -> dict[str, str]:
    """Map every non-canonical entity_types key in *graph* to its
    SCREAMING_SNAKE_CASE form, merged over the fixed legacy list.

    The extraction prompt asks for entity type keys in this form, but nothing
    enforces it at extraction time — agent_02 has produced PascalCase names
    (CreditScore, DocumentCustodian, ...) for entire graphs, and the fixed
    LEGACY_ENTITY_NAMES list only ever covered six specific names discovered
    reactively in earlier datasets. Building the map from the graph's own
    entity_types generalizes the fix to whatever a given run actually
    produced, instead of requiring every new bad name to be added by hand.

    A rule's own `responsible_party`/`counterparties` references are scanned
    too: a reference can be non-canonical even when the entity it refers to
    is already canonical everywhere in entity_types (e.g. one rule citing
    "Borrower" as a counterparty while entity_types only ever defines
    "BORROWER") — that name never appears as an entity_types key, so it would
    otherwise never become a normalization candidate at all.
    """
    mapping = dict(LEGACY_ENTITY_NAMES)
    entity_types = graph.get("entity_types") if isinstance(graph, Mapping) else None
    known_canonical_keys: set[str] = set(mapping.values())
    if isinstance(entity_types, Mapping):
        for key in entity_types:
            key_str = str(key)
            if not key_str:
                continue
            if CANONICAL_ENTITY_RE.fullmatch(key_str):
                known_canonical_keys.add(key_str)
                continue
            canonical = _to_screaming_snake_case(key_str)
            if canonical and canonical != key_str:
                mapping.setdefault(key_str, canonical)
                known_canonical_keys.add(canonical)

    # A rule's own reference can be non-canonical even when the entity it
    # refers to is already canonical everywhere in entity_types (e.g. one
    # rule citing "Borrower" as a counterparty while entity_types only ever
    # defines "BORROWER") — that string never appears as an entity_types key,
    # so without this it would never become a normalization candidate at
    # all. Only remap a reference when its canonical form is already a known
    # entity: an unrelated typo ("Boroower") must stay exactly as written so
    # it keeps failing naming_issues visibly, rather than being silently
    # rewritten to a differently-wrong, canonical-looking name nobody defined.
    rules = graph.get("business_rules") if isinstance(graph, Mapping) else None
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, Mapping):
                continue
            references = [rule.get("responsible_party"), *(rule.get("counterparties") or [])]
            for reference in references:
                key_str = str(reference) if reference else ""
                if not key_str or key_str in mapping or CANONICAL_ENTITY_RE.fullmatch(key_str):
                    continue
                canonical = _to_screaming_snake_case(key_str)
                if canonical and canonical != key_str and canonical in known_canonical_keys:
                    mapping[key_str] = canonical
    return mapping


def _normalise_graph_entity_names(value: Any, mapping: Mapping[str, str] | None = None) -> Any:
    """Replace exact entity identifiers — the fixed legacy list plus any
    non-canonical entity_types key found in *value* itself — including
    dictionary keys.

    `mapping` is computed once from the top-level graph on the outermost call
    and threaded through the recursion; callers normally pass only `value`.
    """
    if mapping is None:
        mapping = _build_entity_name_map(value)
    if isinstance(value, dict):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            normalised_key = mapping.get(str(key), key)
            normalised_item = _normalise_graph_entity_names(item, mapping)
            if normalised_key in result and result[normalised_key] != normalised_item:
                raise ValueError(f"entity-name normalization collision at {normalised_key!r}")
            result[normalised_key] = normalised_item
        return result
    if isinstance(value, list):
        return [_normalise_graph_entity_names(item, mapping) for item in value]
    if isinstance(value, str):
        return mapping.get(value, value)
    return value


def _normalise_value_type(value: Any) -> Any:
    return LEGACY_VALUE_TYPES.get(str(value), value)


def _normalise_operator(value: Any) -> Any:
    return LEGACY_OPERATORS.get(str(value), value)


def _normalise_variable_role(value: Any) -> Any:
    return LEGACY_VARIABLE_ROLES.get(str(value), value)


def _compact_identifier(value: Any) -> str:
    """Compare field references while ignoring separators/case.

    This is intentionally used only to reconcile a reference with a unique
    declared variable in the *same* rule (for example ``he loc_...`` versus
    ``he_loc_...``), never to invent a new variable or map an arbitrary name.
    """
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _declared_identifier_aliases(variables: list[Any]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    collisions: set[str] = set()
    for variable in variables:
        if not isinstance(variable, Mapping):
            continue
        name = str(variable.get("name", "")).strip()
        compact = _compact_identifier(name)
        if not name or not compact:
            continue
        if compact in aliases and aliases[compact] != name:
            collisions.add(compact)
        else:
            aliases[compact] = name
    for compact in collisions:
        aliases.pop(compact, None)
    return aliases


def _canonical_fact_id(value: Any, fallback: Any, used: set[str]) -> str:
    """Return a stable, unique v2 fact identifier.

    Extraction models occasionally copy an output's fact id onto a related
    input, or emit display-style identifiers containing spaces/punctuation.
    Fact ids are local structural identifiers, so repairing their spelling
    from the declared variable name does not make a new business claim.  A
    deterministic numeric suffix handles the rare case where two variable
    names canonicalize to the same id.
    """
    candidate = str(value or "").strip().casefold()
    if not FACT_ID_RE.fullmatch(candidate):
        candidate = str(fallback or "").strip().casefold()
    candidate = re.sub(r"[^a-z0-9]+", "_", candidate).strip("_")
    if not candidate:
        candidate = "fact"
    if candidate[0].isdigit():
        candidate = f"fact_{candidate}"
    base = candidate
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _evidence_pointer(value: Any) -> dict[str, str] | None:
    # source_reference is documented (rule_contract_v2.txt, every domain
    # prompt) as a single object, but agent_03 sometimes emits a list of
    # citations for a rule whose justification spans more than one excerpt —
    # agent_09's own _iter_references already treats that as legitimate.
    # Take the first usable entry rather than discarding real evidence: on
    # one ContractNLI pilot run, a rule with source_reference shaped this way
    # and no exceptions left field_evidence.exceptions empty, which is a hard
    # v2 schema violation that fails the whole pipeline outright.
    if isinstance(value, list):
        value = next((item for item in value if isinstance(item, Mapping)), None)
    if not isinstance(value, Mapping):
        return None
    pointer = {
        "chunk_path": str(value.get("chunk_path", "")).strip(),
        "section_id": str(value.get("section_id", "")).strip(),
        "source_text": str(value.get("source_text", value.get("text", value.get("quote", "")))).strip(),
    }
    return pointer if all(pointer.values()) else None


_CONDITIONAL_SOURCE_CUE = re.compile(
    r"\b(if|when|whenever|unless|provided\s+that|only\s+if|in\s+the\s+event\s+that)\b",
    re.IGNORECASE,
)
_UNCONDITIONAL_SOURCE_ASSERTION = re.compile(
    r"\b(must|shall|is\s+required\s+to|are\s+required\s+to|requires?)\b",
    re.IGNORECASE,
)


def _has_explicit_unconditional_source(rule: Mapping[str, Any]) -> bool:
    """Recognize a direct unconditional obligation without inventing a trigger.

    This intentionally covers only source text with an explicit modal and no
    conditional cue. Definitions, calculations, headings, and mixed
    conditional/unconditional passages remain unresolved for a model or SME.
    """

    pointer = _evidence_pointer(rule.get("source_reference"))
    text = str((pointer or {}).get("source_text", "")).strip()
    return bool(text and _UNCONDITIONAL_SOURCE_ASSERTION.search(text) and not _CONDITIONAL_SOURCE_CUE.search(text))


def _invert_predicate(predicate: Mapping[str, Any], predicate_id: str) -> dict[str, Any]:
    inverse = {"==": "!=", "!=": "==", ">": "<=", ">=": "<", "<": ">=", "<=": ">", "in": "not_in", "not_in": "in"}
    result = deepcopy(dict(predicate))
    result["predicate_id"] = predicate_id
    operator = _normalise_operator(result.get("operator"))
    if operator in inverse:
        result["operator"] = inverse[operator]
    elif result.get("value_type") == "boolean" and isinstance(result.get("value"), bool):
        result["operator"] = "=="
        result["value"] = not result["value"]
    else:
        result["operator"] = "!="
    return result


def _restore_legacy_outcome_operators(graph: dict[str, Any], baseline: Mapping[str, Any]) -> None:
    """Restore comparison operators on a replay from the immutable pre-readiness graph."""
    baseline_operators = {
        (str(rule.get("rule_id")), str(outcome.get("variable"))): outcome.get("operator")
        for rule in baseline.get("business_rules", [])
        if isinstance(rule, Mapping)
        for outcome in rule.get("outcomes", []) or []
        if isinstance(outcome, Mapping) and outcome.get("operator") != "="
    }
    for rule in graph.get("business_rules", []) or []:
        if not isinstance(rule, dict):
            continue
        baseline_rule = next(
            (
                item for item in baseline.get("business_rules", [])
                if isinstance(item, Mapping) and str(item.get("rule_id")) == str(rule.get("rule_id"))
            ),
            None,
        )
        for outcome in rule.get("outcomes", []) or []:
            if not isinstance(outcome, dict):
                continue
            current_name = str(outcome.get("variable"))
            operator = baseline_operators.get((str(rule.get("rule_id")), current_name))
            if operator is not None:
                outcome["operator"] = operator
                continue
            if not isinstance(baseline_rule, Mapping):
                continue
            for baseline_outcome in baseline_rule.get("outcomes", []) or []:
                if not isinstance(baseline_outcome, Mapping) or baseline_outcome.get("operator") == "=":
                    continue
                original_name = str(baseline_outcome.get("variable"))
                if _threshold_output_name(original_name, baseline_outcome.get("operator")) != current_name:
                    continue
                baseline_variable = next(
                    (
                        item for item in baseline_rule.get("variables", []) or []
                        if isinstance(item, Mapping) and str(item.get("name")) == original_name
                    ),
                    None,
                )
                declared_names = {
                    str(item.get("name")) for item in rule.get("variables", []) or [] if isinstance(item, Mapping)
                }
                vector_uses_original = any(
                    isinstance(vector, Mapping) and original_name in (vector.get("inputs") or {})
                    for vector in rule.get("test_vectors", []) or []
                )
                if vector_uses_original and isinstance(baseline_variable, Mapping) and original_name not in declared_names:
                    restored_variable = deepcopy(dict(baseline_variable))
                    restored_variable["role"] = "input"
                    rule.setdefault("variables", []).append(restored_variable)
                break


def _threshold_output_name(variable_name: str, operator: Any) -> str:
    lowered = variable_name.lower()
    if operator == "<=" and not any(token in lowered for token in ("max", "maximum")):
        return f"maximum_allowed_{variable_name}"
    if operator == ">=" and not any(token in lowered for token in ("min", "minimum")):
        return f"minimum_required_{variable_name}"
    if str(operator).upper() == "IN" and "allowed" not in lowered:
        return f"allowed_{variable_name}_values"
    return variable_name


def _coerce_unresolved_basis(rule: dict[str, Any], basis_field: str, valid_values: set[str], verification_field: str, unresolved_value: str) -> None:
    """Coerce an off-schema *_basis string into the correct unresolved final
    state, preserving the model's own explanation rather than discarding it.

    Both scope_basis and exception_basis have been observed holding a
    free-text explanation instead of an enum member — sometimes the model's
    own reasoning wholesale ("unresolved_in_source_exception_not_structurable
    _with_available_rule_variables (source states...)"), sometimes a compact
    ad hoc label ("explicit_in_source_but_details_not_in_evidence_packet").
    Every real case observed is semantically an unresolved state the model
    couldn't cleanly structure — not a new final state and not one of the
    documented ones — so it is normalized to the one unresolved bucket that
    already exists for this field, with the original string kept as the
    reviewable reason rather than silently dropped or left as a raw v2
    schema violation with no actionable path.
    """
    value = rule.get(basis_field)
    if isinstance(value, str) and value in valid_values:
        return
    if value is None:
        verification = rule.get(verification_field)
        verification_map = dict(verification) if isinstance(verification, Mapping) else {}
        verification_map.setdefault(
            "unresolved_reason",
            f"No valid {basis_field} was produced by extraction or evidence completion.",
        )
        rule[verification_field] = verification_map
        rule[basis_field] = unresolved_value
        return
    verification = rule.get(verification_field)
    verification_map = dict(verification) if isinstance(verification, Mapping) else {}
    if not str(verification_map.get("unresolved_reason", "")).strip():
        # Models occasionally return an object/list in place of the enum. Keep
        # the complete value as a reviewable, JSON-safe string and move the
        # field to the documented unresolved state. This prevents contract
        # validation from attempting an unhashable set lookup while retaining
        # the evidence needed for human review.
        verification_map["unresolved_reason"] = value if isinstance(value, str) else repr(value)
    rule[verification_field] = verification_map
    rule[basis_field] = unresolved_value


def _derive_equality_test_vector(rule: Mapping[str, Any]) -> dict[str, Any] | None:
    """Build one source-derived example for a pure equality conjunction.

    Predicate literals become inputs and source-defined outcomes become
    expected outputs. Mixed/OR logic, comparisons, unsafe expressions, and
    contradictory assignments remain unresolved. Numeric FEEL and
    variable-reference outcomes are evaluated only after assigning
    deterministic values to declared inputs.
    """

    predicates = {
        str(item.get("predicate_id")): item
        for item in (rule.get("condition_predicates") or [])
        if isinstance(item, Mapping) and str(item.get("predicate_id", "")).strip()
    }
    if not predicates:
        return None

    def conjunction_refs(node: Any) -> list[str] | None:
        if isinstance(node, Mapping) and set(node) == {"predicate_ref"}:
            return [str(node.get("predicate_ref"))]
        if isinstance(node, Mapping) and set(node) == {"all"} and isinstance(node.get("all"), list) and node["all"]:
            result: list[str] = []
            for child in node["all"]:
                child_refs = conjunction_refs(child)
                if child_refs is None:
                    return None
                result.extend(child_refs)
            return result
        return None

    refs = conjunction_refs(rule.get("condition_logic"))
    if refs is None or len(refs) != len(set(refs)) or set(refs) != set(predicates):
        return None
    inputs: dict[str, Any] = {}
    for predicate_id in refs:
        predicate = predicates[predicate_id]
        if predicate.get("operator") != "==" or predicate.get("value_type") == "variable_reference":
            return None
        name = str(predicate.get("variable") or "").strip()
        if not name:
            return None
        value = deepcopy(predicate.get("value"))
        if name in inputs and inputs[name] != value:
            return None
        inputs[name] = value
    definitions = {
        str(item.get("name", "")).strip(): item
        for item in (rule.get("variables") or [])
        if isinstance(item, Mapping) and str(item.get("name", "")).strip()
    }

    def sample_value(definition: Mapping[str, Any]) -> Any:
        value_type = definition.get("type")
        if value_type == "number":
            allowed_range = definition.get("allowed_range")
            if (
                isinstance(allowed_range, list)
                and allowed_range
                and isinstance(allowed_range[0], (int, float))
                and not isinstance(allowed_range[0], bool)
            ):
                return max(1, allowed_range[0])
            return 1
        if value_type == "boolean":
            return True
        if value_type == "enum" and isinstance(definition.get("allowed_values"), list) and definition["allowed_values"]:
            return deepcopy(definition["allowed_values"][0])
        if value_type == "date":
            return "2000-01-01"
        if value_type == "date_time":
            return "2000-01-01T00:00:00"
        if value_type == "time":
            return "00:00:00"
        if value_type == "duration":
            return "P1D"
        if value_type == "string":
            return "example"
        return None

    expected: dict[str, Any] = {}
    for outcome in rule.get("outcomes", []) or []:
        if not isinstance(outcome, Mapping) or outcome.get("operator") != "=":
            return None
        name = str(outcome.get("variable") or "").strip()
        if not name:
            return None
        value_type = outcome.get("value_type")
        if value_type in {"number", "boolean", "enum", "date", "date_time", "time", "duration", "string", "list"}:
            expected[name] = deepcopy(outcome.get("value"))
            continue
        if value_type == "variable_reference":
            reference = str(outcome.get("value") or "").strip()
            definition = definitions.get(reference)
            if not isinstance(definition, Mapping) or definition.get("role") not in {"input", "derived"}:
                return None
            if reference not in inputs:
                sampled = sample_value(definition)
                if sampled is None:
                    return None
                inputs[reference] = sampled
            expected[name] = deepcopy(inputs[reference])
            continue
        if value_type == "feel_expression":
            for variable_name, definition in definitions.items():
                if definition.get("role") == "input" and definition.get("type") == "number" and variable_name not in inputs:
                    inputs[variable_name] = sample_value(definition)
            evaluated = evaluate_feel_expression(outcome.get("value"), inputs)
            if evaluated is None:
                return None
            expected[name] = evaluated
            continue
        return None
    if not expected or _evidence_pointer(rule.get("source_reference")) is None:
        return None
    return {
        "inputs": inputs,
        "expected_output": expected,
        "vector_basis": "derived_from_source",
        "boundary_condition": False,
    }


def _normalise_rule_contract(rule: dict[str, Any]) -> dict[str, Any]:
    """Normalize legacy extraction shapes without changing rule/source identity."""
    _coerce_unresolved_basis(rule, "exception_basis", EXCEPTION_BASES, "exception_verification", "unresolved_after_full_document_search")
    _coerce_unresolved_basis(rule, "scope_basis", SCOPE_BASES, "scope_derivation", "unresolved_after_source_review")

    # Some model completions preserve named-party detail by wrapping the
    # canonical entity type in an object.  The v2 contract requires party
    # references themselves to be canonical strings. Unwrap only an explicit
    # entity identifier (the providers have used ``entity_type``, ``entity``,
    # and ``name_ref`` for this same field) and retain the richer record
    # separately for review/UI use. A name-only record remains a structured
    # candidate and is left for the contract/remediation path rather than
    # guessed into an ontology type.
    party_details = [
        deepcopy(item)
        for item in (rule.get("counterparty_details") or [])
        if isinstance(item, Mapping)
    ]
    responsible_party = rule.get("responsible_party")
    if isinstance(responsible_party, Mapping):
        entity_type = next(
            (
                responsible_party.get(key)
                for key in ("entity_type", "entity", "name_ref")
                if isinstance(responsible_party.get(key), str)
                and responsible_party.get(key).strip()
            ),
            None,
        )
        if isinstance(entity_type, str) and entity_type.strip():
            rule["responsible_party"] = entity_type.strip()
            party_details.append(deepcopy(dict(responsible_party)))
    counterparties = rule.get("counterparties")
    if counterparties is None:
        rule["counterparties"] = []
    elif isinstance(counterparties, Mapping):
        counterparties = [counterparties]
    if isinstance(counterparties, list):
        normalized_counterparties = []
        for counterparty in counterparties:
            if isinstance(counterparty, Mapping):
                entity_type = next(
                    (
                        counterparty.get(key)
                        for key in ("entity_type", "entity", "name_ref")
                        if isinstance(counterparty.get(key), str)
                        and counterparty.get(key).strip()
                    ),
                    None,
                )
                if isinstance(entity_type, str) and entity_type.strip():
                    normalized_counterparties.append(entity_type.strip())
                    party_details.append(deepcopy(dict(counterparty)))
                else:
                    normalized_counterparties.append(counterparty)
            else:
                normalized_counterparties.append(counterparty)
        rule["counterparties"] = normalized_counterparties
    if party_details:
        unique_details = {
            json.dumps(item, sort_keys=True, ensure_ascii=False): item
            for item in party_details
        }
        rule["counterparty_details"] = list(unique_details.values())
    variables = rule.get("variables")
    if not isinstance(variables, list):
        variables = []
        rule["variables"] = variables
    for variable in variables:
        if not isinstance(variable, dict):
            continue
        # variables[].type shares VARIABLE_TYPES with condition_predicates/
        # outcomes/exceptions' value_type, but only this loop's own two
        # special cases (datetime, string) were ever normalised here — the
        # LEGACY_VALUE_TYPES alias table used everywhere else was never
        # applied to it, so a variable typed "string_array"/"enum_array"
        # (the model's reasonable-but-undocumented plural of an accepted
        # type, exactly like the aliases already mapped below) failed v2
        # validation outright instead of normalising to "list" like its
        # value_type counterparts already do.
        variable["type"] = _normalise_value_type(variable.get("type"))
        if variable.get("type") == "datetime":
            variable["type"] = "date_time"
        if variable.get("type") == "string":
            variable["free_text"] = True
        variable["role"] = _normalise_variable_role(variable.get("role"))

    # ``document_task`` is a common descriptive label in model output, but
    # the executable contract represents a document-handling activity as a
    # human/user task.  Canonicalize this losslessly before validation and
    # BPMN projection rather than rejecting an otherwise source-explicit
    # workflow.
    workflow = rule.get("workflow_semantics")
    if isinstance(workflow, dict) and isinstance(workflow.get("ordered_steps"), list):
        for step in workflow["ordered_steps"]:
            if isinstance(step, dict) and step.get("kind") == "document_task":
                step["kind"] = "user_task"

    declared_aliases = _declared_identifier_aliases(variables)

    def normalise_declared_reference(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        declared = declared_aliases.get(_compact_identifier(value))
        return declared if declared is not None else value

    for field in ("condition_predicates", "outcomes", "exceptions"):
        values = rule.get(field)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            if field != "outcomes":
                item["operator"] = _normalise_operator(item.get("operator"))
                # ``is_applicable`` is an extraction spelling for a boolean
                # truth test, not a new comparison operator.  Canonicalize it
                # only when the value is explicitly boolean so no semantics
                # are guessed for other shapes.
                if item.get("operator") == "is_applicable" and isinstance(item.get("value"), bool):
                    item["operator"] = "=="
            item["value_type"] = _normalise_value_type(item.get("value_type"))
            item["variable"] = normalise_declared_reference(item.get("variable"))
            # The predicate value, rather than the declared variable, is a
            # collection for membership operators. Providers sometimes copy
            # the variable's scalar type (for example number) into value_type
            # while returning [2, 3, 4]. Preserve both the typed variable and
            # list values by canonicalizing only this unambiguous shape.
            if (
                field != "outcomes"
                and item.get("operator") in {"in", "not_in"}
                and isinstance(item.get("value"), list)
            ):
                item["value_type"] = "list"
            if item.get("value_type") == "boolean" and isinstance(item.get("value"), str):
                lowered = item["value"].strip().lower()
                if lowered in {"true", "false"}:
                    item["value"] = lowered == "true"
    variable_by_name = {
        str(variable.get("name", "")).strip().lower(): variable
        for variable in variables
        if isinstance(variable, dict) and str(variable.get("name", "")).strip()
    }
    for outcome in rule.get("outcomes", []) or []:
        if not isinstance(outcome, dict):
            continue
        original_name = str(outcome.get("variable", "")).strip()
        original_operator = outcome.get("operator")
        output_name = _threshold_output_name(original_name, original_operator)
        variable = variable_by_name.get(original_name.lower())
        if output_name != original_name and variable is not None:
            predicate_variables = {
                str(predicate.get("variable", "")).strip().lower()
                for predicate in rule.get("condition_predicates", []) or []
                if isinstance(predicate, Mapping)
            }
            vector_uses_original = any(
                isinstance(vector, Mapping) and original_name in (vector.get("inputs") or {})
                for vector in rule.get("test_vectors", []) or []
            )
            if original_name.lower() in predicate_variables or vector_uses_original:
                output_variable = deepcopy(variable)
                output_variable["name"] = output_name
                output_variable["role"] = "output"
                variables.append(output_variable)
                variable["role"] = "input"
                variable = output_variable
            else:
                variable["name"] = output_name
            variable_by_name.pop(original_name.lower(), None)
            variable_by_name[output_name.lower()] = variable
            outcome["variable"] = output_name
            for vector in rule.get("test_vectors", []) or []:
                expected = vector.get("expected_output") if isinstance(vector, Mapping) else None
                if isinstance(expected, dict) and original_name in expected:
                    expected[output_name] = expected.pop(original_name)
        if variable is not None:
            variable["role"] = "output"
        outcome["operator"] = "="

        # A literal list is a list regardless of the model's stale scalar
        # label.  Preserve the values and make the contract type truthful;
        # downstream lowerers can still refuse unsupported list-valued outputs
        # explicitly rather than failing schema validation on a type lie.
        if isinstance(outcome.get("value"), list) and outcome.get("value_type") == "number":
            outcome["value_type"] = "list"

    # Outcome records are the source of truth for their assigned variable.
    # Older extraction batches sometimes emitted a variable_reference outcome
    # without repeating the output declaration in ``variables``. When the
    # reference resolves to a declared variable, copy only that variable's
    # type/constraints and give the new declaration an output role. This is a
    # structural repair (not a semantic guess) and keeps the source-backed
    # outcome executable without inventing a literal value.
    variable_by_name = {
        str(variable.get("name", "")).strip().lower(): variable
        for variable in variables
        if isinstance(variable, dict) and str(variable.get("name", "")).strip()
    }
    for outcome in rule.get("outcomes", []) or []:
        if not isinstance(outcome, Mapping):
            continue
        output_name = str(outcome.get("variable", "")).strip()
        if not output_name or output_name.lower() in variable_by_name:
            continue
        value_type = _normalise_value_type(outcome.get("value_type"))
        template: Mapping[str, Any] | None = None
        if value_type == "variable_reference":
            reference_name = str(outcome.get("value", "")).strip()
            canonical_reference = declared_aliases.get(_compact_identifier(reference_name), reference_name)
            outcome["value"] = canonical_reference
            template = variable_by_name.get(canonical_reference.lower())
        if template is not None:
            output_variable = deepcopy(dict(template))
            output_variable["name"] = output_name
            output_variable["role"] = "output"
            variables.append(output_variable)
            variable_by_name[output_name.lower()] = output_variable
        elif value_type in {"number", "boolean", "enum", "date", "date_time", "time", "duration", "string", "list"}:
            output_variable = {"name": output_name, "type": value_type, "role": "output"}
            if value_type == "string":
                output_variable["free_text"] = True
            if value_type == "enum":
                literal = outcome.get("value")
                output_variable["allowed_values"] = literal if isinstance(literal, list) else [literal]
            variables.append(output_variable)
            variable_by_name[output_name.lower()] = output_variable

    predicates = rule.get("condition_predicates")
    if not isinstance(predicates, list):
        predicates = []
        rule["condition_predicates"] = predicates
    if not predicates and _has_explicit_unconditional_source(rule):
        rule["condition_logic"] = {"constant": True}
        rule["condition_basis"] = "unconditional_explicit_in_source"
    # A known provider slip shifts a declared variable name into predicate_id
    # and emits variable=null. Recover it only when that identifier resolves
    # uniquely to a variable declared by the same rule. Keep predicate_id
    # unchanged because condition_logic may already reference that descriptive
    # ID. Arbitrary missing variables remain invalid and fail closed.
    for predicate in predicates:
        if not isinstance(predicate, dict) or str(predicate.get("variable") or "").strip():
            continue
        candidate = str(predicate.get("predicate_id") or "").strip()
        declared = declared_aliases.get(_compact_identifier(candidate))
        if declared is not None:
            predicate["variable"] = declared
    # Every atomic predicate must have an ID before condition_logic is
    # resolved. Assign the first available deterministic pN identifier to
    # missing IDs so a logic tree such as ``predicate_ref: p4`` can resolve to
    # the fourth extracted predicate instead of becoming an unknown reference.
    used_predicate_ids = {
        str(predicate.get("predicate_id"))
        for predicate in predicates
        if isinstance(predicate, Mapping) and str(predicate.get("predicate_id", "")).strip()
    }
    next_predicate_number = 1
    for predicate in predicates:
        if not isinstance(predicate, dict) or str(predicate.get("predicate_id", "")).strip():
            continue
        while f"p{next_predicate_number}" in used_predicate_ids:
            next_predicate_number += 1
        predicate["predicate_id"] = f"p{next_predicate_number}"
        used_predicate_ids.add(predicate["predicate_id"])
        next_predicate_number += 1
    predicate_by_id = {
        str(predicate.get("predicate_id")): predicate
        for predicate in predicates
        if isinstance(predicate, dict) and predicate.get("predicate_id")
    }
    referenced_predicates: dict[str, int] = {}

    def resolve_predicate_id(value: Any) -> str:
        """Resolve a positional pN reference to an existing atomic predicate.

        Some model responses give an atomic predicate a descriptive ID (for
        example its variable name) while the logic tree still refers to the
        predicate by its positional ``pN`` label. Reconcile that deterministic
        alias only when the requested position exists; unrelated unknown IDs
        remain untouched and continue to fail closed.
        """
        predicate_id = str(value)
        if predicate_id in predicate_by_id:
            return predicate_id
        match = re.fullmatch(r"p(\d+)", predicate_id, flags=re.IGNORECASE)
        if match:
            index = int(match.group(1)) - 1
            if 0 <= index < len(predicates):
                candidate = predicates[index]
                candidate_id = str(candidate.get("predicate_id", "")).strip() if isinstance(candidate, Mapping) else ""
                if candidate_id in predicate_by_id:
                    return candidate_id
        return predicate_id

    def normalise_logic(node: Any) -> dict[str, Any] | None:
        if not isinstance(node, Mapping):
            return None
        if node.get("variable") and node.get("operator") is not None:
            predicate = deepcopy(dict(node))
            predicate_id = str(predicate.get("predicate_id") or f"p{len(predicates) + 1}")
            while predicate_id in predicate_by_id:
                predicate_id = f"p{len(predicates) + 1}"
            predicate["predicate_id"] = predicate_id
            predicate["operator"] = _normalise_operator(predicate.get("operator"))
            predicate["value_type"] = _normalise_value_type(predicate.get("value_type"))
            predicate["variable"] = normalise_declared_reference(predicate.get("variable"))
            predicates.append(predicate)
            predicate_by_id[predicate_id] = predicate
            return {"predicate_ref": predicate_id}
        if "predicate_ref" in node:
            predicate_id = resolve_predicate_id(node.get("predicate_ref"))
            if node.get("negate") is True and predicate_id in predicate_by_id:
                negated_id = f"{predicate_id}_negated"
                suffix = 2
                while negated_id in predicate_by_id:
                    negated_id = f"{predicate_id}_negated_{suffix}"
                    suffix += 1
                negated = _invert_predicate(predicate_by_id[predicate_id], negated_id)
                predicates.append(negated)
                predicate_by_id[negated_id] = negated
                return {"predicate_ref": negated_id}
            referenced_predicates[predicate_id] = referenced_predicates.get(predicate_id, 0) + 1
            if referenced_predicates[predicate_id] > 1 and predicate_id in predicate_by_id:
                duplicate_id = f"{predicate_id}_copy_{referenced_predicates[predicate_id]}"
                while duplicate_id in predicate_by_id:
                    referenced_predicates[predicate_id] += 1
                    duplicate_id = f"{predicate_id}_copy_{referenced_predicates[predicate_id]}"
                duplicate = deepcopy(predicate_by_id[predicate_id])
                duplicate["predicate_id"] = duplicate_id
                predicates.append(duplicate)
                predicate_by_id[duplicate_id] = duplicate
                return {"predicate_ref": duplicate_id}
            return {"predicate_ref": predicate_id}
        for branch in ("all", "any"):
            if branch in node and isinstance(node[branch], list):
                children = [normalise_logic(child) for child in node[branch]]
                return {branch: [child for child in children if child is not None]}
        return None

    logic = rule.get("condition_logic")
    if not (isinstance(logic, str) and logic in {"AND", "OR"}):
        normalised_logic = normalise_logic(logic)

        def logic_refs(node: Any) -> list[str]:
            if not isinstance(node, Mapping):
                return []
            if set(node) == {"predicate_ref"}:
                return [str(node["predicate_ref"])]
            return [ref for value in node.values() if isinstance(value, list) for child in value for ref in logic_refs(child)]

        referenced = set(logic_refs(normalised_logic))
        missing = [
            str(predicate.get("predicate_id"))
            for predicate in predicates
            if isinstance(predicate, Mapping) and predicate.get("predicate_id") and str(predicate.get("predicate_id")) not in referenced
        ]
        if normalised_logic is None:
            children = [{"predicate_ref": predicate_id} for predicate_id in missing]
            if not children and rule.get("condition_basis") == "unconditional_explicit_in_source":
                normalised_logic = {"constant": True}
            else:
                normalised_logic = children[0] if len(children) == 1 else {"all": children}
        elif missing:
            normalised_logic = {"all": [normalised_logic, *({"predicate_ref": predicate_id} for predicate_id in missing)]}
        rule["condition_logic"] = normalised_logic

    def flatten_logic(node: Any, prefix: str, output: list[dict[str, Any]]) -> None:
        if isinstance(node, Mapping):
            if node.get("variable") and node.get("operator") is not None:
                item = dict(node)
                item.setdefault("predicate_id", f"{prefix}_{len(output) + 1}")
                item["operator"] = _normalise_operator(item.get("operator"))
                item["value_type"] = _normalise_value_type(item.get("value_type"))
                item["variable"] = normalise_declared_reference(item.get("variable"))
                if item.get("value_type") == "boolean" and isinstance(item.get("value"), str):
                    lowered = item["value"].strip().lower()
                    if lowered in {"true", "false"}:
                        item["value"] = lowered == "true"
                output.append(item)
                return
            for value in node.values():
                flatten_logic(value, prefix, output)
        elif isinstance(node, list):
            for value in node:
                flatten_logic(value, prefix, output)

    exceptions = rule.get("exceptions")
    if isinstance(exceptions, list):
        flattened: list[dict[str, Any]] = []
        for index, exception in enumerate(exceptions):
            if not isinstance(exception, Mapping):
                continue
            if exception.get("variable") and exception.get("operator") is not None:
                item = dict(exception)
                item.setdefault("predicate_id", str(exception.get("exception_id") or f"ex{index + 1}"))
                item["operator"] = _normalise_operator(item.get("operator"))
                item["value_type"] = _normalise_value_type(item.get("value_type"))
                item["variable"] = normalise_declared_reference(item.get("variable"))
                flattened.append(item)
                continue
            prefix = str(exception.get("exception_id") or f"ex{index + 1}")
            flatten_logic(exception.get("logic", exception), prefix, flattened)
        rule["exceptions"] = flattened

    # Flattening nested exception logic can repeat the parent predicate ID
    # (e.g. e1, e1, ex1_3).  IDs are only references, so suffix duplicates in
    # encounter order while retaining every predicate and its semantics.
    seen_exception_ids: set[str] = set()
    for index, exception in enumerate(rule.get("exceptions", []) or []):
        if not isinstance(exception, dict):
            continue
        base_id = str(exception.get("predicate_id") or f"ex{index + 1}").strip() or f"ex{index + 1}"
        predicate_id = base_id
        suffix = 2
        while predicate_id in seen_exception_ids:
            predicate_id = f"{base_id}_copy_{suffix}"
            suffix += 1
        exception["predicate_id"] = predicate_id
        seen_exception_ids.add(predicate_id)

    # A recurring extraction error places alternate *outcome assignments* in
    # ``exceptions``.  Evaluating an output as an input predicate is invalid
    # and can invert the rule.  Preserve those assignments verbatim in the
    # explicit non-executable ``exception_effects`` audit field, and leave only
    # genuine input circumstances in ``exceptions``.  Downstream readiness
    # keeps the rule review-gated until branch semantics are represented; no
    # evidence or alternate value is discarded merely to pass validation.
    output_names = {
        str(variable.get("name", "")).strip().casefold()
        for variable in variables
        if isinstance(variable, Mapping) and variable.get("role") == "output"
    }
    preserved_effects = [
        dict(item)
        for item in (rule.get("exception_effects") or [])
        if isinstance(item, Mapping)
    ]
    input_exceptions: list[dict[str, Any]] = []
    for exception in rule.get("exceptions", []) or []:
        if not isinstance(exception, dict):
            continue
        if str(exception.get("variable", "")).strip().casefold() not in output_names:
            input_exceptions.append(exception)
            continue
        effect = deepcopy(exception)
        effect["operator"] = "="
        effect["effect_id"] = str(effect.pop("predicate_id", "") or f"effect_{len(preserved_effects) + 1}")
        if effect not in preserved_effects:
            preserved_effects.append(effect)
    rule["exceptions"] = input_exceptions
    if preserved_effects:
        rule["exception_effects"] = preserved_effects
        if not input_exceptions:
            verification = rule.get("exception_verification")
            verification_map = dict(verification) if isinstance(verification, Mapping) else {}
            verification_map["status"] = "unresolved"
            verification_map.setdefault(
                "unresolved_reason",
                "Alternate exception outcomes were preserved, but no source-stated input trigger is structurally associated with them.",
            )
            rule["exception_verification"] = verification_map
            rule["exception_basis"] = "unresolved_after_full_document_search"
    else:
        rule.pop("exception_effects", None)

    variable_by_name = {
        str(variable.get("name", "")).strip().lower(): variable
        for variable in variables
        if isinstance(variable, dict) and str(variable.get("name", "")).strip()
    }
    for index, exception in enumerate(rule.get("exceptions", []) or []):
        if not isinstance(exception, dict):
            continue
        exception.setdefault("predicate_id", f"ex{index + 1}")
        name = str(exception.get("variable", "")).strip()
        existing_variable = variable_by_name.get(name.lower())
        if not exception.get("value_type") and existing_variable is not None:
            exception["value_type"] = existing_variable.get("type")
        if not name or existing_variable is not None:
            continue
        value = exception.get("value")
        value_type = exception.get("value_type")
        # ``input_reference`` is emitted when the model recognizes that the
        # exception compares two inputs. Canonicalize it only when the
        # referenced input is declared in this rule; otherwise retain the
        # extraction label so the capability gap remains visibly deferred
        # instead of silently turning an unresolved name into a literal.
        if value_type == "input_reference":
            reference = variable_by_name.get(str(value).strip().lower())
            if reference is not None:
                exception["value_type"] = "variable_reference"
                value_type = "variable_reference"
        variable_type = value_type if value_type in {"number", "boolean", "enum", "date", "date_time", "time", "duration", "string"} else "string"
        variable: dict[str, Any] = {"name": name, "type": variable_type, "role": "input"}
        if variable_type == "string":
            variable["free_text"] = True
        if variable_type == "enum":
            variable["allowed_values"] = value if isinstance(value, list) else [value]
        variables.append(variable)
        variable_by_name[name.lower()] = variable

    # Older extraction batches occasionally used descriptive role labels such
    # as ``condition``/``result``/``context``. The v2 contract has only
    # input/output/derived; infer the canonical role from how the variable is
    # actually used in this rule. This is a local structural repair, not a
    # source-claim inference: a variable used by a predicate is an input, one
    # assigned by an outcome is an output, and an ambiguous/unused variable is
    # retained conservatively as derived.
    predicate_names = {
        str(item.get("variable", "")).strip().casefold()
        for item in [*(rule.get("condition_predicates", []) or []), *(rule.get("exceptions", []) or [])]
        if isinstance(item, Mapping) and str(item.get("variable", "")).strip()
    }
    outcome_names = {
        str(item.get("variable", "")).strip().casefold()
        for item in (rule.get("outcomes", []) or [])
        if isinstance(item, Mapping) and str(item.get("variable", "")).strip()
    }
    for variable in variables:
        if not isinstance(variable, Mapping):
            continue
        role = str(variable.get("role", "")).strip().casefold()
        if role in {"input", "output", "derived"}:
            continue
        name = str(variable.get("name", "")).strip().casefold()
        if name in outcome_names and name not in predicate_names:
            variable["role"] = "output"
        elif name in predicate_names and name not in outcome_names:
            variable["role"] = "input"
        else:
            variable["role"] = "derived"

    # Remediation patches and repeated normalization can independently add the
    # same declaration (most often when two outcomes converge on a threshold
    # output). The v2 contract requires unique variable names. Merge duplicate
    # declarations deterministically, retaining every non-empty constraint and
    # preferring an output role when either declaration is an output. This is
    # a structural/idempotence repair; it does not alter any outcome value or
    # source evidence.
    merged_variables: list[dict[str, Any]] = []
    merged_by_name: dict[str, dict[str, Any]] = {}
    for variable in variables:
        if not isinstance(variable, dict):
            continue
        name = str(variable.get("name", "")).strip()
        if not name:
            continue
        key = name.casefold()
        existing = merged_by_name.get(key)
        if existing is None:
            merged = dict(variable)
            merged_variables.append(merged)
            merged_by_name[key] = merged
            continue
        for field, value in variable.items():
            if field not in existing or existing.get(field) in (None, "", [], {}):
                existing[field] = deepcopy(value)
        roles = {str(existing.get("role", "")).casefold(), str(variable.get("role", "")).casefold()}
        if "output" in roles:
            existing["role"] = "output"
        elif "input" in roles:
            existing["role"] = "input"
    rule["variables"] = merged_variables

    # Fact ids are local identifiers, not source assertions.  Normalize them
    # after duplicate variable declarations have been merged so every rule
    # satisfies the v2 uniqueness contract before readiness is evaluated.
    used_fact_ids: set[str] = set()
    for variable in merged_variables:
        if not isinstance(variable, dict):
            continue
        variable["fact_id"] = _canonical_fact_id(
            variable.get("fact_id"), variable.get("name"), used_fact_ids
        )

    # Promote only validated arithmetic over declared numeric variables to a
    # real DMN FEEL expression.  Unsupported prose, lookup objects, collection
    # folds, and unknown functions retain their original value_type and remain
    # review-required.  The source spelling is preserved for grounding/audit.
    for outcome in rule.get("outcomes", []) or []:
        if not isinstance(outcome, dict) or outcome.get("value_type") not in {"formula", "expression"}:
            continue
        original_expression = outcome.get("value")
        compiled = compile_feel_expression(
            original_expression,
            merged_variables,
            output_variable=str(outcome.get("variable") or ""),
        )
        if compiled is None:
            continue
        outcome["source_expression"] = original_expression
        outcome["value"] = compiled
        outcome["value_type"] = "feel_expression"

    verification = rule.get("exception_verification")
    if (
        rule.get("exception_basis") == "explicit_in_source"
        and not rule.get("exceptions")
        and isinstance(verification, dict)
        and str(verification.get("unresolved_reason", "")).strip()
    ):
        rule["exception_basis"] = "unresolved_after_full_document_search"
        verification["status"] = "unresolved_after_full_document_search"

    if not rule.get("test_vectors"):
        derived_vector = _derive_equality_test_vector(rule)
        if derived_vector is not None:
            rule["test_vectors"] = [derived_vector]

    for vector in rule.get("test_vectors", []) or []:
        if not isinstance(vector, dict):
            continue
        basis = str(vector.get("vector_basis", ""))
        if basis.startswith("source_attested"):
            vector["vector_basis"] = "source_attested"
        elif basis.startswith("derived") or basis == "source_derived":
            vector["vector_basis"] = "derived_from_source"

    evidence = rule.setdefault("field_evidence", {})
    if isinstance(evidence, dict):
        source_pointer = _evidence_pointer(rule.get("source_reference"))
        exception_pointers = [
            pointer
            for item in (rule.get("exception_verification") or {}).get("evidence", [])
            if (pointer := _evidence_pointer(item)) is not None
        ] if isinstance(rule.get("exception_verification"), Mapping) else []
        for field_path in (
            "condition_predicates", "outcomes", "responsible_party", "scope_basis",
            "versioning_status", "exceptions", "test_vectors",
        ):
            existing = evidence.get(field_path)
            if isinstance(existing, list) and existing:
                continue
            pointers = exception_pointers if field_path == "exceptions" and exception_pointers else ([source_pointer] if source_pointer else [])
            evidence[field_path] = pointers
    _complete_predicate_value_types(rule)
    return rule


def _is_unusable_empty_rule(rule: Mapping[str, Any]) -> bool:
    """Identify a phantom extraction record with no source or executable data.

    A rule ID alone is not evidence.  Dropping this specific empty shape keeps
    a malformed placeholder from poisoning schema/readiness statistics while
    leaving every source-backed rule (including incomplete ones) reviewable.
    """
    source = rule.get("source_reference")
    has_source = isinstance(source, Mapping) and any(str(source.get(k, "")).strip() for k in ("chunk_path", "section_id", "source_text"))
    return (
        not has_source
        and not isinstance(source, list)
        and not rule.get("variables")
        and not rule.get("condition_predicates")
        and not rule.get("outcomes")
        and not rule.get("test_vectors")
        and not (isinstance(rule.get("execution"), Mapping) and (rule["execution"].get("targets") or []))
    )


def _is_deferred_contract_issue(issue: Mapping[str, Any], rule: Mapping[str, Any]) -> bool:
    """Return whether a contract finding is a known downstream capability gap.

    These findings remain attached to the rule and therefore continue to set
    ``requires_review``.  They are not *pipeline* invariant failures because
    the source-backed rule can still proceed through remediation/export with a
    visible lowering refusal (computed formulas/objects, provider-specific
    predicates, and field-evidence completion).  Unknown structural errors do
    not receive this exception.
    """
    code = str(issue.get("code", ""))
    # These rule-local representation slips are safe to carry into Agent 08's
    # focused contract/remediation pass. They must remain attached to the rule
    # (and therefore keep it review-required), but they should not abort the
    # graph-level readiness stage before the remediator can repair them. The
    # classification is intentionally code-based and source/domain agnostic:
    # no missing party, predicate, or operator is ever silently invented here.
    if code in {
        "unknown_counterparty",
        "unknown_predicate_reference",
        "invalid_predicate_operator",
    }:
        return True
    if code == "missing_field_evidence":
        return True
    if code == "missing_evidence_reference_field":
        # The malformed citation is removed by _normalise_field_evidence_references;
        # the resulting empty field remains an evidence-limited review item.
        return True
    if code in {"missing_condition_predicates", "empty_condition_logic_branch"}:
        # Some source-backed policy statements are unconditional assertions
        # (for example, a document revision date or an automatic collection
        # disclosure). They still cannot be executed as a conditional DMN row,
        # but treating the representation gap as deferred lets the pipeline
        # complete while the rule stays explicitly review-required.
        return bool(rule.get("outcomes"))
    if code == "missing_test_vectors":
        # A source-backed rule may be fully grounded while its executable
        # examples are still a capability gap. Keep it review-required, but
        # allow downstream model/export stages to run and expose the gap.
        return bool(rule.get("outcomes"))
    if code in {
        "invalid_hit_policy",
        "missing_versioning_status",
        "missing_responsible_party",
        "invalid_vector_basis",
        "undefined_predicate_variable",
        "missing_workflow_evidence",
    }:
        # These are rule-local lowering/metadata gaps. They remain explicit
        # readiness failures on the rule, but do not make the entire graph
        # structurally unusable or prevent grounding/report generation.
        return True
    if code == "invalid_outcome_value_type":
        path = str(issue.get("path", ""))
        try:
            index = int(path.split("[")[1].split("]")[0])
            value_type = (rule.get("outcomes") or [])[index].get("value_type")
        except (IndexError, TypeError, ValueError, AttributeError):
            value_type = None
        return value_type in {"formula", "expression", "object", "variable_expression", "conditional_map"}
    if code == "invalid_variable_type":
        path = str(issue.get("path", ""))
        try:
            index = int(path.split("[")[1].split("]")[0])
            value_type = (rule.get("variables") or [])[index].get("type")
        except (IndexError, TypeError, ValueError, AttributeError):
            value_type = None
        return value_type in {"formula", "expression", "object", "variable_expression", "conditional_map"}
    if code == "invalid_predicate_value_type":
        path = str(issue.get("path", ""))
        try:
            index = int(path.split("[")[1].split("]")[0])
            value_type = (rule.get("condition_predicates") or [])[index].get("value_type")
        except (IndexError, TypeError, ValueError, AttributeError):
            value_type = None
        return value_type in {"variable_expression", "formula", "expression"}
    if code == "invalid_exception_value_type":
        path = str(issue.get("path", ""))
        try:
            index = int(path.split("[")[1].split("]")[0])
            value_type = (rule.get("exceptions") or [])[index].get("value_type")
        except (IndexError, TypeError, ValueError, AttributeError):
            value_type = None
        # Computed exception expressions and unresolved input references are
        # not representable by the current v2 scalar contract. Preserve their
        # original shape and route them for human review rather than coercing
        # them into a misleading literal type.
        return value_type in {"formula", "expression", "object", "variable_expression", "conditional_map", "input_reference"}
    if code == "undefined_exception_variable_reference":
        path = str(issue.get("path", ""))
        try:
            index = int(path.split("[")[1].split("]")[0])
            value_type = (rule.get("exceptions") or [])[index].get("value_type")
        except (IndexError, TypeError, ValueError, AttributeError):
            value_type = None
        return value_type == "input_reference"
    if code == "invalid_exception_operator":
        path = str(issue.get("path", ""))
        try:
            index = int(path.split("[")[1].split("]")[0])
            operator = (rule.get("exceptions") or [])[index].get("operator")
        except (IndexError, TypeError, ValueError, AttributeError):
            operator = None
        return operator == "determined_by"
    return False


_EXCEPTION_CUE_MARKERS = (
    "except",
    "unless",
    "notwithstanding",
    "waiver",
    "exempt",
    "exception",
    "does not apply",
)


def _infer_literal_value_type(value: Any, variable: Mapping[str, Any] | None, operator: Any) -> str | None:
    """Infer a missing predicate type from its literal without changing meaning.

    Candidate extraction occasionally omits ``value_type`` on exception
    predicates even though the value is a boolean/number and the referenced
    variable is declared.  The v2 contract requires the type, and this narrow
    inference is deterministic: booleans and numbers are unambiguous; lists
    are collections; strings use a declared compatible type or fall back to a
    free-form string.  Unsupported operators remain untouched and continue to
    fail contract validation.
    """
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, list):
        return "list"
    if isinstance(value, str):
        declared = variable.get("type") if isinstance(variable, Mapping) else None
        declared = _normalise_value_type(declared)
        if declared in {"date", "date_time", "time", "duration", "enum", "number", "boolean", "list", "range", "string"}:
            return declared
        if operator in {"in", "not_in"}:
            return "enum"
        return "string"
    return None


def _complete_predicate_value_types(rule: dict[str, Any]) -> None:
    """Fill only omitted/legacy predicate types from declared variables/literals."""
    variables = {
        str(item.get("name", "")).strip().lower(): item
        for item in rule.get("variables", []) or []
        if isinstance(item, Mapping) and str(item.get("name", "")).strip()
    }
    for field in ("condition_predicates", "exceptions"):
        for item in rule.get(field, []) or []:
            if not isinstance(item, dict):
                continue
            value_type = _normalise_value_type(item.get("value_type"))
            if value_type is not None:
                item["value_type"] = value_type
                continue
            inferred = _infer_literal_value_type(
                item.get("value"),
                variables.get(str(item.get("variable", "")).strip().lower()),
                item.get("operator"),
            )
            if inferred is not None:
                item["value_type"] = inferred


_SOURCE_RECOVERY_STOPWORDS = frozenset({
    "about", "after", "also", "and", "are", "before", "being", "between", "both", "but", "can", "could",
    "does", "from", "for", "has", "have", "into", "may", "must", "not", "only", "our", "should", "that",
    "the", "their", "there", "these", "this", "those", "under", "when", "where", "which", "will", "with", "you",
})


def _recover_source_reference(rule: dict[str, Any], packet: Mapping[str, Any]) -> bool:
    """Attach a citation only when bounded lexical retrieval is unambiguous.

    Agent 03 can produce a semantically useful rule while omitting the source
    pointer. A later readiness pass should be able to recover an obvious
    pointer, but must not turn a loose keyword hit into asserted evidence.
    This helper therefore requires a configurable token-overlap floor and a
    margin over the runner-up. Ambiguous candidates remain review-required.
    """
    if _evidence_pointer(rule.get("source_reference")) is not None:
        return False
    passages = packet.get("candidate_passages")
    if not isinstance(passages, list):
        return False
    query = {
        token.casefold()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", " ".join(str(rule.get(key, "")) for key in ("rule_name", "description")))
        if token.casefold() not in _SOURCE_RECOVERY_STOPWORDS
    }
    if len(query) < 4:
        return False
    candidates: list[tuple[float, dict[str, Any]]] = []
    rule_id_tokens = {
        token.casefold()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", re.sub(r"[^A-Za-z0-9]+", " ", str(rule.get("rule_id", ""))))
        if token.casefold() not in {"rule", "batch"}
    }
    for passage in passages:
        if not isinstance(passage, Mapping):
            continue
        text = str(passage.get("text") or "")
        if not text or not str(passage.get("chunk_path") or "").strip() or not str(passage.get("section_id") or "").strip():
            continue
        tokens = {
            token.casefold()
            for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", text)
            if token.casefold() not in _SOURCE_RECOVERY_STOPWORDS
        }
        overlap = len(query & tokens) / max(1, len(query))
        anchor_hits = min(1.0, float(passage.get("anchor_hits") or 0) / max(1, len(query)))
        candidates.append((overlap * 0.9 + anchor_hits * 0.1, dict(passage)))
    if not candidates:
        return False
    # If the stable rule ID names a source package, restrict recovery to that
    # package before comparing prose similarity. This prevents a generic
    # phrase such as "international transfer" from selecting an unrelated
    # policy that happens to use the same language.
    scoped = [
        item for item in candidates
        if rule_id_tokens.intersection({
            token.casefold()
            for token in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", re.sub(r"[^A-Za-z0-9]+", " ", str(item[1].get("chunk_path", ""))))
        })
    ]
    if scoped:
        candidates = scoped
    candidates.sort(key=lambda item: (-item[0], str(item[1].get("chunk_path"))))
    best_score, best = candidates[0]
    runner_up = candidates[1][0] if len(candidates) > 1 else 0.0
    try:
        min_score = float(os.getenv("KG_READINESS_SOURCE_RECOVERY_MIN_OVERLAP", "0.55"))
        min_margin = float(os.getenv("KG_READINESS_SOURCE_RECOVERY_MIN_MARGIN", "0.12"))
    except (TypeError, ValueError):
        min_score, min_margin = 0.55, 0.12
    if best_score < min_score or best_score - runner_up < min_margin:
        return False
    rule["source_reference"] = {
        "chunk_path": str(best["chunk_path"]),
        "section_id": str(best["section_id"]),
        "source_text": str(best["text"]),
        "reference_verified": False,
        "recovery_method": "bounded_lexical_retrieval",
        "recovery_score": round(best_score, 4),
    }
    return True


def _evidence_text(rule: Mapping[str, Any], verification: Mapping[str, Any]) -> str:
    """Return only cited source text used to classify exception evidence."""
    values: list[str] = []
    reference = rule.get("source_reference")
    references = reference if isinstance(reference, list) else [reference]
    for item in references:
        if isinstance(item, Mapping):
            values.append(str(item.get("source_text", "")))
    for field in ("evidence", "source_evidence"):
        entries = verification.get(field)
        if isinstance(entries, list):
            for item in entries:
                if isinstance(item, Mapping):
                    values.append(str(item.get("source_text") or item.get("quote") or item.get("text") or ""))
        elif isinstance(entries, str):
            values.append(entries)
    direct = verification.get("direct_evidence")
    if isinstance(direct, Mapping):
        values.append(str(direct.get("source_text", "")))
    elif isinstance(direct, list):
        values.extend(str(item) for item in direct)
    return " ".join(values).casefold()


def _normalise_final_evidence_states(rule: dict[str, Any], corpus: Mapping[str, Any]) -> None:
    """Repair deterministic resolver-state mistakes after complete-corpus search.

    The model sometimes calls a rule's own source condition an ``explicit``
    exception while returning no exception predicates.  When the recorded
    complete search has no exception cue in the cited text, the correct final
    state is the machine-observed no-cue state.  Likewise, a directly cited
    scope with at least one populated dimension is explicit evidence even if a
    resolver leaves an ``unresolved``/candidate label behind.  Ambiguous
    exception cues and genuinely empty scopes remain review-gated.
    """
    verification = rule.get("exception_verification")
    verification_map = verification if isinstance(verification, dict) else {}
    expected_count = int(corpus.get("chunk_count", 0) or 0)
    expected_digest = str(corpus.get("corpus_sha256") or "")
    complete_search = (
        verification_map.get("searched_chunk_count") == expected_count
        and bool(expected_digest)
        and verification_map.get("corpus_sha256") == expected_digest
    )
    if rule.get("exception_basis") == "explicitly_none_in_source" and complete_search:
        # ``exception_basis`` is the contract field; resolver responses have
        # historically used free-form synonyms in the companion status. Bind
        # the status to the same final state only after the deterministic
        # complete-corpus search fingerprint is current. Agent 09 can then
        # certify the absence claim without trusting a loose status string.
        verification_map["status"] = "explicitly_none_in_source"
        rule["exception_verification"] = verification_map
    if (
        not rule.get("exceptions")
        and rule.get("exception_basis") in {"explicit_in_source", "unresolved_after_full_document_search"}
        and complete_search
        and not any(marker in _evidence_text(rule, verification_map) for marker in _EXCEPTION_CUE_MARKERS)
    ):
        rule["exception_basis"] = "no_exception_cue_found_in_complete_search"
        verification_map["status"] = "no_exception_cue_found_in_complete_search"
        verification_map["searched_chunk_count"] = expected_count
        verification_map["corpus_sha256"] = expected_digest
        verification_map.setdefault("searched_document_ids", ["organized_corpus"])
        rule["exception_verification"] = verification_map

    scope = rule.get("applicability_scope")
    scope_map = scope if isinstance(scope, Mapping) else {}
    has_dimension = bool(populated_scope(scope_map))
    derivation = rule.get("scope_derivation")
    derivation_map = derivation if isinstance(derivation, Mapping) else {}
    complete_scope_review = (
        derivation_map.get("reviewed_chunk_count") == expected_count
        and bool(expected_digest)
        and derivation_map.get("corpus_sha256") == expected_digest
    )
    if rule.get("scope_basis") == "genuinely_unscoped" and complete_scope_review:
        derivation_map = dict(derivation_map)
        derivation_map["status"] = "genuinely_unscoped"
        rule["scope_derivation"] = derivation_map
    scope_evidence = derivation_map.get("evidence") or derivation_map.get("source_evidence")
    if (not isinstance(scope_evidence, list) or not scope_evidence) and isinstance(rule.get("field_evidence"), Mapping):
        scope_evidence = rule["field_evidence"].get("scope_basis")
    if (
        rule.get("scope_basis") in {"inferred", "unresolved_after_source_review"}
        and has_dimension
        and isinstance(scope_evidence, list)
        and scope_evidence
    ):
        original_basis = rule.get("scope_basis")
        rule["scope_basis"] = "explicit_in_source"
        derivation_map = dict(derivation_map)
        derivation_map.setdefault(
            "resolution_note",
            f"Normalized {original_basis} to explicit_in_source because populated scope dimensions have direct source evidence.",
        )
        rule["scope_derivation"] = derivation_map


def _semantic_output_value(value: Any, value_type: Any) -> tuple[str, Any]:
    """Return a conservative comparison key for cross-rule output values."""
    if value_type == "boolean" and isinstance(value, bool):
        return ("decision", "eligible" if value else "ineligible")
    if value_type == "enum" and isinstance(value, str):
        lowered = value.strip().casefold()
        if lowered in {"eligible", "ineligible", "not_eligible"}:
            return ("decision", "ineligible" if lowered == "not_eligible" else lowered)
    return (str(value_type or type(value).__name__), str(value).strip().casefold())


def _normalise_conflict_entries(
    entries: list[dict[str, Any]],
    rules_by_id: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Downgrade conservative unresolved records that are mechanically safe.

    Agent 07's conflict prompt is intentionally fail-closed, but model
    responses often mark equivalent assignments (``eligible`` vs ``true``) as
    unresolved even though both rules write the same semantic result.  Such a
    record must not gate either rule.  Real opposite assignments and semantic
    relationships over different output names remain unresolved/conflicting.
    """
    normalized: list[dict[str, Any]] = []

    def pair_entry(left_id: str, right_id: str, template: Mapping[str, Any]) -> dict[str, Any]:
        """Return a pair-level finding with deterministic safe cases resolved.

        A model may conservatively return one unresolved group for a large
        entity. Treating that group as a conflict for every member overstates
        the review queue: rules with disjoint output variables cannot assign a
        contradictory value to the same DMN slot. Reduce the group to pairs,
        resolve only that mechanically provable case, and preserve unresolved
        status for pairs that still share an output assignment.
        """
        current = dict(template)
        current["rule_ids"] = [left_id, right_id]
        left_outcomes = {
            str(item.get("variable")): (item.get("value"), item.get("value_type"))
            for item in rules_by_id[left_id].get("outcomes", []) or []
            if isinstance(item, Mapping) and item.get("variable")
        }
        right_outcomes = {
            str(item.get("variable")): (item.get("value"), item.get("value_type"))
            for item in rules_by_id[right_id].get("outcomes", []) or []
            if isinstance(item, Mapping) and item.get("variable")
        }
        shared = set(left_outcomes) & set(right_outcomes)
        equivalent = bool(shared) and all(
            _semantic_output_value(*left_outcomes[name])
            == _semantic_output_value(*right_outcomes[name])
            for name in shared
        )
        if not shared or equivalent:
            current.update({
                "status": "non_conflict",
                "reasoning": (
                    "The rules have disjoint outcome variables, or their shared "
                    "assignments are semantically equivalent after boolean/enum normalization."
                ),
                "resolution": "No conflict; preserve each rule's output mapping.",
            })
        elif not str(current.get("reasoning", "")).strip() or str(current.get("reasoning", "")).startswith("No entity-local conflict analysis"):
            current["reasoning"] = "The rules share an outcome variable and no safe co-firing determination was returned."
            current["resolution"] = "Manual review required."
        return current

    for entry in entries:
        current = dict(entry)
        rule_ids = [str(value) for value in current.get("rule_ids", []) if str(value) in rules_by_id]
        unresolved_status = current.get("status") == "unresolved" or (
            current.get("status") == "conflict" and not str(current.get("resolution", "")).strip()
        )
        if unresolved_status and len(rule_ids) > 2:
            # Preserve the analyzer's explanation on each pair, while making
            # the readiness gate depend only on the pair that can actually
            # co-fire into a shared output.
            normalized.extend(
                pair_entry(left_id, right_id, current)
                for index, left_id in enumerate(sorted(set(rule_ids)))
                for right_id in sorted(set(rule_ids))[index + 1:]
            )
            continue
        if current.get("status") != "unresolved":
            normalized.append(current)
            continue
        if len(rule_ids) < 2:
            normalized.append(current)
            continue
        by_variable: dict[str, list[tuple[Any, Any]]] = {}
        for rule_id in rule_ids:
            for outcome in rules_by_id[rule_id].get("outcomes", []) or []:
                if not isinstance(outcome, Mapping) or not outcome.get("variable"):
                    continue
                by_variable.setdefault(str(outcome["variable"]), []).append(
                    (outcome.get("value"), outcome.get("value_type"))
                )
        shared = {name: values for name, values in by_variable.items() if len(values) > 1}
        equivalent = bool(shared) and all(
            len({_semantic_output_value(value, value_type) for value, value_type in values}) == 1
            for values in shared.values()
        )
        if equivalent:
            current.update({
                "status": "non_conflict",
                "reasoning": "Shared outcome assignments are semantically equivalent after boolean/enum normalization; both rules may co-fire.",
                "resolution": "No conflict; preserve the equivalent output assignment.",
            })
        normalized.append(current)
    return normalized


def _ensure_referenced_entity_placeholders(graph: dict[str, Any]) -> None:
    """Keep canonical rule-party references resolvable without inventing facts."""
    entity_types = graph.get("entity_types")
    if not isinstance(entity_types, dict):
        return
    references = []
    for rule in graph.get("business_rules", []) or []:
        if not isinstance(rule, Mapping):
            continue
        references.extend([rule.get("responsible_party"), *(rule.get("counterparties") or [])])
    for reference in references:
        value = str(reference or "").strip()
        if not value or value in entity_types or not CANONICAL_ENTITY_RE.fullmatch(value):
            continue
        entity_types[value] = {
            "name": value,
            "type": "REFERENCED_ENTITY",
            "description": "Referenced by an extracted rule; standalone entity definition was not returned by agent_02.",
            "key_attributes": [],
            "examples": [],
            "provenance": {"basis": "rule_reference", "source": "agent_03"},
        }


def _verify_completion_evidence(rule: dict[str, Any], corpus: Mapping[str, Any]) -> None:
    """Verify -- and where possible repair -- the citations agent_07's own
    completion resolver invents, in place.

    agent_03 verifies every citation it produces against the corpus
    (_verify_source_references), which is why its source_reference citations
    measure ~98% verbatim on a real mortgage run. The completion resolver
    used here produces NEW citations for exception_verification.evidence and
    scope_derivation.evidence, and nothing verified them: the same run
    measured those at 29% and 25% non-verbatim respectively -- 346 citations,
    the single largest source of the invalid evidence agent_09 later rejects,
    hours downstream and far from the cause.

    Repairs use the same corpus-anchored strategies agent_09 applies
    (utils.citations), so a repaired citation is always literal chunk text
    and never the resolver's paraphrase. A citation that cannot be repaired
    is left exactly as-is rather than dropped: removing it would silently
    change which rules look evidence-backed, and agent_09 still independently
    rejects it. This only ever makes a citation more faithful to the source.
    """
    chunk_text_by_path: dict[str, str] = {
        str(chunk.get("chunk_path", "")): str(chunk.get("text", ""))
        for chunk in corpus.get("chunks", [])
        if isinstance(chunk, Mapping)
    }

    def _chunk_for(path: str) -> str | None:
        if not path:
            return None
        direct = chunk_text_by_path.get(path)
        if direct is not None:
            return direct
        # Same suffix tolerance agent_09's _chunk_for_path uses, and only
        # when it is unambiguous.
        candidates = [
            text for known, text in chunk_text_by_path.items()
            if known.endswith(path) or path.endswith(known)
        ]
        return candidates[0] if len(candidates) == 1 else None

    for parent_field in ("exception_verification", "scope_derivation"):
        parent = rule.get(parent_field)
        if not isinstance(parent, dict):
            continue
        for evidence_field in ("evidence", "source_evidence"):
            entries = parent.get(evidence_field)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                quote = entry.get("source_text") or entry.get("quote") or entry.get("text")
                chunk_text = _chunk_for(str(entry.get("chunk_path") or ""))
                if not quote or not chunk_text:
                    entry["source_text_found_in_chunk"] = False
                    continue
                if normalise_text(quote) in normalise_text(chunk_text):
                    entry["source_text_found_in_chunk"] = True
                    continue
                repaired = repair_citation(str(quote), chunk_text)
                if repaired is None:
                    entry["source_text_found_in_chunk"] = False
                    continue
                key = "source_text" if entry.get("source_text") else (
                    "quote" if entry.get("quote") else "text"
                )
                entry[key] = repaired
                entry["source_text_repaired"] = True
                entry["source_text_found_in_chunk"] = True


def _sync_completion_field_evidence(rule: dict[str, Any]) -> None:
    """Attach completion evidence to the exact structured fields it supports."""
    field_evidence = rule.setdefault("field_evidence", {})
    if not isinstance(field_evidence, dict):
        return

    def records(parent_name: str) -> list[dict[str, Any]]:
        parent = rule.get(parent_name)
        if not isinstance(parent, Mapping):
            return []
        candidates = parent.get("evidence") or parent.get("source_evidence") or []
        return [
            dict(item) for item in candidates
            if isinstance(item, Mapping)
            and item.get("source_text_found_in_chunk") is True
        ]

    exception_records = records("exception_verification")
    if rule.get("exceptions") and exception_records:
        field_evidence["exceptions"] = exception_records

    scope = rule.get("applicability_scope")
    scope_records = records("scope_derivation")
    if isinstance(scope, Mapping) and any(scope.get(key) for key in scope) and scope_records:
        field_evidence["applicability_scope"] = scope_records


def _normalise_field_evidence_references(rule: dict[str, Any]) -> None:
    """Canonicalize field citations while preserving fail-closed gaps.

    A malformed citation must not remain as a partially populated object: it
    makes the schema gate fail before downstream remediation can run. Keep
    only complete pointers (accepting the legacy ``quote``/``text`` aliases),
    canonicalize them to ``source_text``, and leave an empty field for the
    readiness checker to mark as evidence-limited. No new evidence is
    invented and unresolved fields therefore remain review-required.
    """
    evidence = rule.get("field_evidence")
    if not isinstance(evidence, dict):
        return
    for field, records in list(evidence.items()):
        if not isinstance(records, list):
            continue
        normalized: list[dict[str, Any]] = []
        for record in records:
            if not isinstance(record, Mapping):
                continue
            pointer = _evidence_pointer(record)
            if pointer is None:
                continue
            normalized.append({**dict(record), **pointer})
        evidence[field] = normalized


def _report_markdown(report: Mapping[str, Any]) -> str:
    corpus = report["invariants"]["corpus_integrity"]
    lines = ["# Sections added", ""]
    lines.extend([f"- {item['section_id']}: {item['reason']}" for item in corpus["sections_added"]] or ["- None."])
    lines += ["", "# Sections removed", ""]
    lines.extend([f"- {item['section_id']}: {item['reason']}" for item in corpus["sections_removed"]] or ["- None."])
    lines += ["", "# Executable KG readiness self-report", "", "## Invariant validation", ""]
    for name, result in report["invariants"].items():
        lines.append(f"- {name}: {'PASS' if result['pass'] else 'FAIL'} — {result['evidence']}")
    lines += ["", "## Conflicts and dependency chains", ""]
    lines.append(f"- Entities checked: {report['conflicts_and_dependencies']['entities_checked']}")
    lines.append(f"- Conflicts found: {report['conflicts_and_dependencies']['conflicts_found']}")
    lines.append(f"- Dependency chains derived: {report['conflicts_and_dependencies']['dependency_chains_derived']}")
    lines += ["", "## Exception recheck", ""]
    for key, value in report["exception_recheck"].items():
        if key != "unresolved_rules": lines.append(f"- {key.replace('_', ' ')}: {value}")
    lines += ["", "## Scope derivation", ""]
    for key, value in report["scope_derivation"].items():
        if key != "examples": lines.append(f"- {key.replace('_', ' ')}: {value}")
    return "\n".join(lines) + "\n"


class ExecutableReadinessCompleter:
    """Completes evidence fields and emits a non-silent pass/fail self-report."""

    # Bump whenever completion prompt/contract semantics change so an older
    # model response cannot silently bypass newly required fields or states.
    CHECKPOINT_VERSION = 3

    def __init__(self, resolver: EvidenceResolver | None = None) -> None:
        self.resolver = resolver
        self.checkpoint_path: Path | None = None
        self._checkpoint_lock = threading.Lock()
        self._checkpoint: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _fingerprint(rule: Mapping[str, Any], packet: Mapping[str, Any]) -> str:
        payload = json.dumps(
            {
                "checkpoint_version": ExecutableReadinessCompleter.CHECKPOINT_VERSION,
                "rule": rule,
                "packet": packet,
            }, sort_keys=True,
            ensure_ascii=False, separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _load_checkpoint(
        self,
        valid_rule_ids: set[str] | None = None,
        corpus_sha256: str | None = None,
    ) -> None:
        self._checkpoint = {}
        if self.checkpoint_path is None or not self.checkpoint_path.exists():
            return
        for line in self.checkpoint_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, Mapping) and row.get("key") and isinstance(row.get("rule"), Mapping):
                rule = row["rule"]
                # Checkpoint keys are content fingerprints, but old runs can
                # still contain a completely different corpus. Reject those
                # rows before any model request so a resumed run cannot spend
                # work on stale rule IDs or accidentally mix datasets.
                if valid_rule_ids is not None and str(rule.get("rule_id")) not in valid_rule_ids:
                    continue
                if corpus_sha256:
                    observed_hashes = {
                        value
                        for container_name in ("exception_verification", "scope_derivation")
                        for value in [
                            (rule.get(container_name) or {}).get("corpus_sha256")
                            if isinstance(rule.get(container_name), Mapping) else None
                        ]
                        if value
                    }
                    # A checkpoint without a corpus fingerprint is legacy and
                    # cannot be proven safe to reuse after chunk repair.
                    if observed_hashes != {corpus_sha256}:
                        continue
                self._checkpoint[str(row["key"])] = dict(rule)

    def _save_checkpoint(self, key: str, rule: Mapping[str, Any]) -> None:
        if self.checkpoint_path is None:
            return
        row = json.dumps({"key": key, "rule": rule}, ensure_ascii=False)
        with self._checkpoint_lock:
            self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            with self.checkpoint_path.open("a", encoding="utf-8") as handle:
                handle.write(row + "\n")
            self._checkpoint[key] = deepcopy(dict(rule))

    @staticmethod
    def _evidence_packet(rule: Mapping[str, Any], corpus: Mapping[str, Any]) -> dict[str, Any]:
        """Search every chunk locally, then send the relevant evidence packet.

        The search record proves the complete available organized corpus was
        inspected by the deterministic retriever. The model receives direct
        candidates, including every exception-marker hit, rather than an
        unbounded document dump.
        """
        source = rule.get("source_reference", {})
        if isinstance(source, list):
            # See _evidence_pointer's comment: a rule can legitimately cite
            # more than one excerpt; use the first for retrieval anchoring.
            source = next((item for item in source if isinstance(item, Mapping)), {})
        # Treat a partial/list-shaped citation as unresolved for retrieval;
        # its text may be stale and must not bias source recovery.
        quote = source.get("source_text", "") if isinstance(source, Mapping) and _evidence_pointer(rule.get("source_reference")) is not None else ""
        # Rule IDs often preserve the source package identifier even when the
        # natural-language title does not. Include that stable identifier in
        # retrieval anchors; it is metadata, not a semantic claim.
        text = " ".join(str(rule.get(key, "")) for key in ("rule_id", "rule_name", "description")) + " " + str(quote)
        # A previous pass may identify an exact cross-section whose criteria
        # were outside the first bounded packet. Include that evidence limit in
        # retrieval anchors so remediation can fetch the named section.
        # Resolver-generated evidence can itself contain a stale or unrelated
        # citation. Do not let that metadata steer recovery when the primary
        # source pointer is missing; it remains useful as a supplemental
        # anchor only after a source reference already exists.
        if _evidence_pointer(rule.get("source_reference")) is not None:
            text += " " + json.dumps({
                "exception_verification": rule.get("exception_verification"),
                "scope_derivation": rule.get("scope_derivation"),
            }, ensure_ascii=False)
        anchors = {token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", text)}
        # Also split stable identifiers/titles on separators. A greedy token
        # such as ``rule_147_wnep_international_transfer`` otherwise hides the
        # useful package token ``wnep`` from the inverted index.
        identifier_text = " ".join(str(rule.get(key, "")) for key in ("rule_id", "rule_name"))
        rule_id_anchors = {
            token.lower()
            for token in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", re.sub(r"[^A-Za-z0-9]+", " ", str(rule.get("rule_id", ""))))
            if token.lower() not in {"rule", "batch"}
        }
        anchors.update(
            token.lower()
            for token in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", re.sub(r"[^A-Za-z0-9]+", " ", identifier_text))
        )
        markers = {"except", "unless", "notwithstanding", "however", "waiver", "exempt"}
        matches = []
        search_chunks = corpus.get("_search_index")
        if not isinstance(search_chunks, list):
            search_chunks = [
                (chunk, str(chunk.get("text", "")).lower(), str(chunk.get("chunk_path", "")).lower())
                for chunk in corpus.get("chunks", [])
                if isinstance(chunk, Mapping)
            ]
        token_index = corpus.get("_token_index")
        if isinstance(token_index, Mapping):
            # Common prose terms occur in nearly every chunk and provide no
            # retrieval signal.  Prefer the rarest anchors and cap the set so
            # one rule cannot trigger millions of inverted-index operations.
            anchors = set(sorted(
                anchors,
                key=lambda anchor: (len(token_index.get(anchor, ())), -len(anchor), anchor),
            )[:32])
            # Score by inverted-index hits rather than rechecking every anchor
            # against every candidate chunk (which is quadratic for large
            # remediation cohorts).
            scores: dict[int, int] = {}
            for anchor in anchors:
                for index in token_index.get(anchor, ()):
                    scores[index] = scores.get(index, 0) + 1
                normalized_anchor = re.sub(r"[^a-z0-9]", "", anchor)
                for index in token_index.get("__pathnorm__:" + normalized_anchor, ()):
                    scores[index] = scores.get(index, 0) + 1
            candidate_indexes = set(scores)
            for marker in markers:
                candidate_indexes.update(token_index.get("__marker__:" + marker, ()))
            iterable = ((search_chunks[index], scores.get(index, 0)) for index in sorted(candidate_indexes) if index < len(search_chunks))
        else:
            iterable = ((item, None) for item in search_chunks)
        for item, indexed_score in iterable:
            chunk, lower, path_lower = item
            normalized_path = re.sub(r"[^a-z0-9]", "", path_lower)
            score = indexed_score if indexed_score is not None else sum(
                anchor in lower or anchor in path_lower or re.sub(r"[^a-z0-9]", "", anchor) in normalized_path
                for anchor in anchors
            )
            # A package/domain token in a chunk path is a stronger identity
            # signal than the same generic word in policy prose. Weight those
            # separator-delimited path hits so bounded packets retain the
            # likely source package even when common terms dominate the text
            # score (without introducing a dataset-specific domain map).
            path_tokens = set(re.findall(r"[a-z][a-z0-9]{2,}", re.sub(r"[^a-z0-9]+", " ", path_lower)))
            # Only stable rule-id components receive the path bonus. Common
            # prose terms such as ``information`` and ``services`` occur in
            # many packages and would otherwise overpower the identity hit.
            score += 8 * sum(anchor in path_tokens for anchor in rule_id_anchors)
            if score or any(marker in lower for marker in markers):
                matches.append({"chunk_path": chunk.get("chunk_path"), "section_id": chunk.get("section_id"), "text": chunk.get("text"), "anchor_hits": score})
        matches.sort(key=lambda item: (-item["anchor_hits"], str(item["chunk_path"])))
        # The complete corpus is searched above, but sending every matching
        # chunk to the model can create 200K+ token prompts for a single rule.
        # Preserve proof of complete coverage while sending a bounded,
        # relevance-ranked evidence packet. The cited source chunk is retained
        # whenever available, followed by the strongest anchor/exception hits.
        try:
            max_candidates = max(1, int(os.getenv("KG_READINESS_MAX_CANDIDATES", "12")))
            max_chars = max(4000, int(os.getenv("KG_READINESS_MAX_EVIDENCE_CHARS", "12000")))
        except (TypeError, ValueError):
            max_candidates, max_chars = 12, 24000
        cited_path = str(source.get("chunk_path", "")) if isinstance(source, Mapping) else ""
        ordered = []
        section_refs = {
            re.sub(r"[^a-z0-9]", "", match.lower())
            for match in re.findall(r"\b[A-Z]\d+(?:[-.]\d+){2,}\b", text)
        }
        if section_refs:
            ordered.extend(
                item for item in matches
                if any(reference in re.sub(r"[^a-z0-9]", "", str(item.get("chunk_path", "")).lower()) for reference in section_refs)
            )
        if cited_path:
            ordered.extend(item for item in matches if str(item.get("chunk_path")) == cited_path and item not in ordered)
        ordered.extend(item for item in matches if item not in ordered)
        bounded = []
        used_chars = 0
        for item in ordered:
            if len(bounded) >= max_candidates:
                break
            text_value = str(item.get("text", ""))
            remaining = max_chars - used_chars
            if remaining <= 0:
                break
            clipped = text_value[:remaining]
            bounded.append({**item, "text": clipped})
            used_chars += len(clipped)
        return {
            "searched_chunk_count": corpus.get("chunk_count", 0),
            "corpus_sha256": corpus.get("corpus_sha256"),
            "candidate_passages": bounded,
        }

    def _complete_evidence(self, rule: dict[str, Any], corpus: Mapping[str, Any]) -> dict[str, Any]:
        if self.resolver is None:
            return rule
        completion = dict(self.resolver.complete_rule(rule, corpus))
        # The resolver may only update evidence-derived fields, never IDs, rules,
        # dependencies, or source provenance established by earlier stages.
        for field in ("exceptions", "exception_basis", "exception_verification", "applicability_scope", "scope_basis", "scope_derivation"):
            if field not in completion:
                continue
            if field in _DICT_SHAPED_COMPLETION_FIELDS and not isinstance(completion[field], Mapping):
                # A malformed resolver response (e.g. a plain string where a
                # structured object was expected) must not silently corrupt
                # the rule — keep whatever was already there and let
                # final_rule_issues flag the rule as still needing evidence,
                # rather than crash a later isinstance-unguarded read of it.
                continue
            rule[field] = completion[field]
        verification = rule.get("exception_verification")
        if isinstance(verification, dict):
            # Search coverage is evidence produced by the local complete-corpus
            # traversal, never a model claim.
            verification["searched_chunk_count"] = corpus.get("searched_chunk_count", 0)
            verification["corpus_sha256"] = corpus.get("corpus_sha256")
            verification.setdefault("searched_document_ids", ["organized_corpus"])
        derivation = rule.get("scope_derivation")
        if isinstance(derivation, dict):
            derivation["reviewed_chunk_count"] = corpus.get("searched_chunk_count", 0)
            derivation["corpus_sha256"] = corpus.get("corpus_sha256")
        return rule

    def complete(
        self,
        baseline: Mapping[str, Any],
        graph: Mapping[str, Any],
        organized_dir: str,
        *,
        skip_evidence: bool | None = None,
        skip_conflicts: bool | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        final_graph = _normalise_graph_entity_names(deepcopy(dict(graph)))
        _ensure_referenced_entity_placeholders(final_graph)
        entity_catalog = (
            final_graph.get("entity_types")
            if isinstance(final_graph.get("entity_types"), Mapping)
            else {}
        )
        _restore_legacy_outcome_operators(final_graph, baseline)
        corpus = source_document_index(organized_dir)
        # Build retrieval-normalization data once. Without this index every
        # rule lowercased and regex-normalized the entire corpus independently,
        # making large runs CPU-bound before their first LLM request.
        corpus["_search_index"] = [
            (chunk, str(chunk.get("text", "")).lower(), str(chunk.get("chunk_path", "")).lower())
            for chunk in corpus.get("chunks", [])
            if isinstance(chunk, Mapping)
        ]
        corpus["_token_index"] = _build_token_index(corpus["_search_index"])
        rules = [
            quarantine_non_actor_counterparties(rule, entity_catalog)
            for rule in final_graph.get("business_rules", [])
            if isinstance(rule, Mapping) and not _is_unusable_empty_rule(rule)
        ]
        # Keep the exported graph aligned with the rules actually evaluated;
        # this also prevents a phantom empty record from being counted as a
        # readiness failure downstream.
        final_graph["business_rules"] = rules
        baseline_rules = [rule for rule in baseline.get("business_rules", []) if isinstance(rule, Mapping)]
        initial_chunk_rechecks = sum(rule.get("exception_basis") == "not_found_in_chunk_recheck_needed" for rule in baseline_rules)
        before_scope = {str(rule.get("rule_id")): deepcopy(rule.get("applicability_scope")) for rule in baseline_rules}
        try:
            readiness_workers = max(1, int(os.getenv("KG_READINESS_WORKERS", "40")))
        except (TypeError, ValueError):
            readiness_workers = 40

        self._load_checkpoint(
            {str(rule.get("rule_id")) for rule in rules if rule.get("rule_id")},
            str(corpus.get("corpus_sha256") or "") or None,
        )

        def finish_rule(index: int, original: Mapping[str, Any], completion: Mapping[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
            rule = deepcopy(dict(original))
            if not isinstance(rule.get("applicability_scope"), dict):
                rule["applicability_scope"] = {}
            packet = self._evidence_packet(rule, corpus)
            cache_key = self._fingerprint(rule, packet)
            cached = self._checkpoint.get(cache_key)
            if cached is not None:
                cached_rule = deepcopy(cached)
                _recover_source_reference(cached_rule, packet)
                return index, cached_rule
            if completion is None:
                try:
                    rule = self._complete_evidence(rule, packet)
                except Exception as exc:
                    # A single rule's own evidence-completion request can
                    # fail for reasons no retry fixes: the provider rejected
                    # the prompt outright (real case: OpenAI's content-policy
                    # filter flagged one rule's text among ~2600, well past
                    # the SDK's own transient-error retries), a persistent
                    # network fault, etc. No further fallback exists below
                    # this rule's own individual request -- crashing the
                    # entire multi-hour run over one unprocessable rule would
                    # discard every other rule's completed work for nothing.
                    # Flag it closed instead: mark_readiness (see the caller
                    # loop) turns this into an explicit, visible review
                    # reason, exactly like any other unresolved evidence gap.
                    rule["_evidence_completion_error"] = str(exc)
            else:
                for field in ("exceptions", "exception_basis", "exception_verification", "applicability_scope", "scope_basis", "scope_derivation"):
                    if field not in completion:
                        continue
                    if field in _DICT_SHAPED_COMPLETION_FIELDS and not isinstance(completion[field], Mapping):
                        continue
                    rule[field] = deepcopy(completion[field])
                verification = rule.get("exception_verification")
                if isinstance(verification, dict):
                    verification["searched_chunk_count"] = corpus.get("chunk_count", 0)
                    verification["corpus_sha256"] = corpus.get("corpus_sha256")
                    verification.setdefault("searched_document_ids", ["organized_corpus"])
                derivation = rule.get("scope_derivation")
                if isinstance(derivation, dict):
                    derivation["reviewed_chunk_count"] = corpus.get("chunk_count", 0)
                    derivation["corpus_sha256"] = corpus.get("corpus_sha256")
            _recover_source_reference(rule, packet)
            # Re-apply the universal shape guard after the merge. Dimension
            # names are domain-owned; this stage must not inject mortgage keys
            # into privacy, contracts, or any future domain.
            if not isinstance(rule.get("applicability_scope"), dict):
                rule["applicability_scope"] = {}
            _verify_completion_evidence(rule, corpus)
            _sync_completion_field_evidence(rule)
            rule = _normalise_rule_contract(rule)
            _normalise_field_evidence_references(rule)
            _normalise_final_evidence_states(rule, corpus)
            # Re-validate against the now-normalised values. agent_03 stamped
            # contract_issues/requires_review against the raw model output at
            # extraction time; _normalise_rule_contract above can alias a
            # legacy operator/value_type into canonical form afterward, which
            # left those annotations stale (observed on a real run: ~97% of
            # rules still carried invalid_predicate_operator issues against
            # operators that were visibly valid in the same JSON). This only
            # ever adds requires_review=True for a genuine remaining issue —
            # annotate_rule_contract() never clears a True set for another
            # reason (e.g. an unresolved evidence gap) elsewhere in this file.
            rule = annotate_rule_contract(rule, entity_catalog)
            rule["execution"] = _project_execution(rule)
            self._save_checkpoint(cache_key, rule)
            return index, rule

        def complete_batch(batch: list[tuple[int, Mapping[str, Any]]]) -> list[tuple[int, dict[str, Any]]]:
            requests = []
            pending = []
            completed = []
            for index, original in batch:
                packet = self._evidence_packet(original, corpus)
                cache_key = self._fingerprint(original, packet)
                if cache_key in self._checkpoint:
                    # Checkpoints may have been produced by an older contract
                    # normalizer. Re-run the non-destructive normalization and
                    # annotation on cache hits so validator fixes take effect
                    # on resumed runs and stale review metadata is not carried
                    # into the final readiness report.
                    cached_rule = _normalise_rule_contract(deepcopy(self._checkpoint[cache_key]))
                    _verify_completion_evidence(cached_rule, corpus)
                    _sync_completion_field_evidence(cached_rule)
                    _normalise_field_evidence_references(cached_rule)
                    _normalise_final_evidence_states(cached_rule, corpus)
                    cached_rule = annotate_rule_contract(cached_rule, entity_catalog)
                    cached_rule["execution"] = _project_execution(cached_rule)
                    _recover_source_reference(cached_rule, packet)
                    completed.append((index, cached_rule))
                else:
                    requests.append({"rule": _compact_readiness_rule(original), "evidence_packet": packet})
                    pending.append((index, original))
            if not pending:
                return completed
            if self.resolver is not None and hasattr(self.resolver, "complete_rules"):
                try:
                    response = self.resolver.complete_rules(requests)
                except Exception as exc:
                    # The whole batch's combined prompt was rejected -- most
                    # often because one rule among the ~4 batched together
                    # tripped the provider's content-policy filter, which
                    # rejects the entire request, not just that rule's share
                    # of it. Retry each rule in this batch on its own: a rule
                    # that wasn't the actual cause gets a normal individual
                    # completion (see finish_rule's completion=None path);
                    # only the genuinely bad rule fails again, in isolation,
                    # where finish_rule's own try/except turns it into an
                    # explicit review flag instead of losing this whole batch.
                    print(f"⚠️ agent_07 batch completion failed ({exc}); retrying its {len(pending)} rules individually", flush=True)
                    completed.extend(finish_rule(index, original) for index, original in pending)
                    return completed
                by_id = {
                    str(item.get("rule_id")): item for item in response
                    if isinstance(item, Mapping) and item.get("rule_id")
                }
                for index, original in pending:
                    completion = by_id.get(str(original.get("rule_id")))
                    completed.append(finish_rule(index, original, completion))
            else:
                completed.extend(finish_rule(index, original) for index, original in pending)
            return completed

        if skip_evidence is None:
            skip_evidence = os.getenv("KG_READINESS_SKIP_EVIDENCE", "").lower() in {"1", "true", "yes"}
        if skip_evidence:
            print(f"▶ agent_07 rule evidence: reusing {len(rules)} completed rules", flush=True)
            existing_rules = rules
            rules = []
            for rule in existing_rules:
                normalized = _normalise_rule_contract(rule)
                _verify_completion_evidence(normalized, corpus)
                _sync_completion_field_evidence(normalized)
                _normalise_field_evidence_references(normalized)
                _normalise_final_evidence_states(normalized, corpus)
                _recover_source_reference(normalized, self._evidence_packet(normalized, corpus))
                rules.append(annotate_rule_contract(normalized, entity_catalog))
            for rule in rules:
                rule["execution"] = _project_execution(rule)
        else:
            batch_size = max(1, int(os.getenv("KG_READINESS_RULES_PER_REQUEST", "4")))
            indexed = list(enumerate(rules))
            batches = [indexed[start:start + batch_size] for start in range(0, len(indexed), batch_size)]
            api_workers = max(1, int(os.getenv("KG_READINESS_LLM_CONCURRENCY", "32")))
            readiness_workers = min(readiness_workers, api_workers)
            print(f"▶ agent_07 rule evidence: {len(rules)} rules in {len(batches)} batches, "
                  f"{readiness_workers} workers, {getattr(self.resolver, 'readiness_concurrency', 'bounded') if self.resolver else 0} API concurrency", flush=True)
            completed_rules: list[dict[str, Any] | None] = [None] * len(rules)
            with ThreadPoolExecutor(max_workers=readiness_workers, thread_name_prefix="kg-readiness") as executor:
                futures = [executor.submit(complete_batch, batch) for batch in batches]
                for future in as_completed(futures):
                    for index, completed in future.result():
                        completed_rules[index] = completed
            rules = [rule for rule in completed_rules if rule is not None]
        final_graph["business_rules"] = rules

        edges = dependency_edges(final_graph)
        chains, cycles = derive_dependency_chains(edges)
        final_graph.setdefault("dependency_details", {})["dependencies"] = edges
        final_graph["dependency_details"]["dependency_chains"] = chains
        final_graph["dependency_details"]["circular_dependencies"] = cycles

        conflict_entries: list[dict[str, Any]] = []
        ids = {str(rule.get("rule_id")): rule for rule in rules}
        # Conflict analysis is meaningful only within a shared source
        # package. The corpus can contain many independent policies that use
        # the same generic entity (for example ``ENTITY`` or ``DATA``);
        # comparing those rules creates false co-firing conflicts. Rules with
        # no usable citation stay in one conservative unscoped group, while a
        # rule citing multiple packages participates in each asserted scope.
        all_rules_by_id = {str(rule.get("rule_id")): rule for rule in rules if rule.get("rule_id")}
        scoped_groups: dict[str, list[str]] = {}
        for entity, member_ids in entity_rule_groups(final_graph).items():
            by_scope: dict[str, set[str]] = {}
            for rule_id in member_ids:
                roots = source_document_roots(all_rules_by_id.get(str(rule_id), {}))
                scopes = roots or {"__unscoped__"}
                for scope in scopes:
                    by_scope.setdefault(scope, set()).add(str(rule_id))
            for scope, scoped_ids in by_scope.items():
                if len(scoped_ids) > 1:
                    scoped_groups[f"{entity}::source:{scope}"] = sorted(scoped_ids)
        groups = scoped_groups

        def outcome_variables(rule_id: str) -> set[str]:
            outcomes = ids[rule_id].get("outcomes", []) or []
            return {str(item.get("variable")) for item in outcomes if isinstance(item, Mapping) and item.get("variable")}

        def analyse_group(entity: str, member_ids: list[str]) -> list[dict[str, Any]]:
            display_entity = entity.split("::source:", 1)[0]
            summaries = [{key: ids[rule_id].get(key) for key in ("rule_id", "condition_predicates", "condition_logic", "outcomes", "applicability_scope", "exceptions", "recommended_hit_policy")} for rule_id in member_ids]
            try:
                max_rules_per_call = max(2, int(os.getenv("KG_CONFLICT_MAX_RULES_PER_CALL", "32")))
            except (TypeError, ValueError):
                max_rules_per_call = 32

            # Large generic groups (for example LENDER/ENTITY) can contain
            # hundreds of rules. Only rules sharing an outcome variable can
            # produce contradictory DMN assignments; disjoint-output pairs are
            # proven non-conflicting mechanically and never sent in a giant
            # prompt. This keeps conflict prompts bounded and pair coverage
            # complete without weakening the conflict requirement.
            output_buckets: dict[str, list[str]] = {}
            for rule_id in member_ids:
                for variable in outcome_variables(rule_id):
                    output_buckets.setdefault(variable, []).append(rule_id)
            overlapping_ids = {rule_id for bucket in output_buckets.values() if len(bucket) > 1 for rule_id in bucket}
            entries: list[dict[str, Any]] = []
            if len(overlapping_ids) == 0:
                # A source-scoped group whose rules write pairwise-disjoint
                # variables is safe by construction. Do not spend a model
                # call asking it to rediscover this fact, and do not create a
                # broad unresolved group that would put every rule on the
                # human queue.
                return [{
                    "entity": entity,
                    "status": "non_conflict",
                    "rule_ids": sorted(member_ids),
                    "reasoning": "These rules have pairwise disjoint outcome variables, so simultaneous firing cannot assign contradictory values.",
                    "resolution": "No conflict; preserve each rule's distinct output mapping.",
                }]
            if len(member_ids) <= max_rules_per_call:
                try:
                    analyses = _analyse_entity_with_retries(
                        self.resolver.analyse_entity,
                        display_entity,
                        [item for item in summaries if str(item.get("rule_id")) in overlapping_ids],
                        scope_label=entity,
                    ) if self.resolver else []
                except Exception as exc:
                    # A final provider rejection (for example a content-policy
                    # filter) still remains fail-closed. Transient transport
                    # and provider-5xx failures have already received bounded
                    # retries in _analyse_entity_with_retries.
                    print(f"⚠️ agent_07 conflict analysis failed for entity {entity!r} ({exc}); marking unresolved", flush=True)
                    analyses = []
                entries.extend(dict(item) for item in analyses if isinstance(item, Mapping))
            else:
                # One dominant entity (e.g. a generic LENDER/FIRST_PARTY
                # bucket) can hold most of a graph's rules, splitting into
                # dozens of independent output-variable batches — each is
                # its own LLM call with no dependency on the others. This
                # used to dispatch them one at a time in a plain loop, which
                # on a real run left this entire conflict-analysis phase
                # running at an effective concurrency of 1 even though the
                # outer per-entity ThreadPoolExecutor (and the shared LLM
                # concurrency gate) had far more room to give it.
                batch_id_groups = _conflict_batch_groups(
                    member_ids, outcome_variables, max_rules_per_call,
                )

                def _call_bucket(batch_ids: list[str]) -> list[dict[str, Any]]:
                    try:
                        analyses = _analyse_entity_with_retries(
                            self.resolver.analyse_entity,
                            display_entity,
                            [item for item in summaries if str(item.get("rule_id")) in batch_ids],
                            scope_label=f"{entity} bucket",
                        ) if self.resolver else []
                    except Exception as exc:
                        # Keep non-transient or exhausted failures explicit;
                        # transient transport/provider failures were retried
                        # by _analyse_entity_with_retries first.
                        print(f"⚠️ agent_07 conflict analysis failed for entity {entity!r} bucket ({exc}); marking unresolved", flush=True)
                        analyses = []
                    return [dict(item) for item in analyses if isinstance(item, Mapping)]

                if batch_id_groups:
                    with ThreadPoolExecutor(max_workers=min(readiness_workers, len(batch_id_groups)), thread_name_prefix="kg-conflict-bucket") as bucket_executor:
                        for bucket_entries in bucket_executor.map(_call_bucket, batch_id_groups):
                            entries.extend(bucket_entries)

                # Cover all pairs that cannot share an output assignment with
                # compact deterministic entries. The model is reserved for
                # the materially ambiguous overlapping-output pairs.
                non_overlapping_ids = sorted(set(member_ids) - overlapping_ids)
                if len(non_overlapping_ids) > 1:
                    entries.append({
                        "entity": entity,
                        "status": "non_conflict",
                        "rule_ids": non_overlapping_ids,
                        "reasoning": "These rules have pairwise disjoint outcome variables, so simultaneous firing cannot assign contradictory values.",
                        "resolution": "No conflict; preserve each rule's distinct output mapping.",
                    })
                for rule_id in sorted(overlapping_ids):
                    disjoint_ids = [other for other in member_ids if other != rule_id and outcome_variables(rule_id).isdisjoint(outcome_variables(other))]
                    if disjoint_ids:
                        entries.append({
                            "entity": entity,
                            "status": "non_conflict",
                            "rule_ids": [rule_id, *sorted(disjoint_ids)],
                            "reasoning": "The rules have disjoint outcome variables, so simultaneous firing cannot assign contradictory values.",
                            "resolution": "No conflict; preserve each rule's distinct output mapping.",
                        })
            if not entries:
                entries = [{"entity": entity, "status": "unresolved", "rule_ids": member_ids, "reasoning": "No entity-local conflict analysis was returned.", "resolution": "Manual review required."}]
            expected_pairs = _conflict_candidate_pairs(member_ids, overlapping_ids, max_rules_per_call)
            if expected_pairs is None:
                # The potentially ambiguous cross-bucket product itself is
                # too large to enumerate safely. Preserve fail-closed
                # semantics with one bounded unresolved group; downstream
                # readiness marks every affected rule for review without
                # allocating quadratic pair state.
                if len(overlapping_ids) > 1:
                    entries.append({
                        "entity": entity,
                        "status": "unresolved",
                        "rule_ids": sorted(overlapping_ids),
                        "reasoning": "The overlapping-output conflict set is too large for bounded pair enumeration; cross-bucket interactions were not exhaustively resolved.",
                        "resolution": "Manual review required for the unresolved overlapping-output group.",
                    })
                expected_pairs = set()
            # For a large group, avoid combinations() over a giant
            # non-overlapping deterministic entry. Only candidate pairs above
            # can be materially ambiguous; the bounded nested loop keeps the
            # coverage calculation linear in the source group size when the
            # overlap set is small.
            member_set = set(member_ids)
            covered_pairs: set[tuple[str, str]] = set()
            for analysis in entries:
                analysis_ids = [str(rule_id) for rule_id in analysis.get("rule_ids", []) if str(rule_id) in member_set]
                if len(member_ids) <= max_rules_per_call:
                    covered_pairs.update(combinations(sorted(analysis_ids), 2))
                elif expected_pairs:
                    analysis_overlap = set(analysis_ids) & overlapping_ids
                    for rule_id in analysis_overlap:
                        covered_pairs.update(
                            tuple(sorted((rule_id, other)))
                            for other in analysis_ids
                            if other != rule_id
                        )
            # The prompt asks the model for "every material pair or an
            # unresolved group with a specific reason" — it is not instructed
            # to enumerate every combinatorial pair, so a small group's
            # single-call response legitimately omits pairs it judged
            # obviously safe. Apply the same mechanical disjoint-outcome
            # proof the >max_rules_per_call branch already uses before
            # falling back to a generic "unresolved" filler, so a small
            # group gets the same non_conflict coverage a large group would.
            for pair in sorted(expected_pairs - covered_pairs):
                rule_a, rule_b = pair
                if outcome_variables(rule_a).isdisjoint(outcome_variables(rule_b)):
                    entries.append({
                        "entity": entity,
                        "status": "non_conflict",
                        "rule_ids": list(pair),
                        "reasoning": "The rules have disjoint outcome variables, so simultaneous firing cannot assign contradictory values.",
                        "resolution": "No conflict; preserve each rule's distinct output mapping.",
                    })
                else:
                    entries.append({
                        "entity": entity,
                        "status": "unresolved",
                        "rule_ids": list(pair),
                        "reasoning": "The entity-local analyser did not return a co-firing determination for this pair, and the rules share an outcome variable so disjointness cannot resolve it mechanically.",
                        "resolution": "Manual review required.",
                    })
            return entries

        if skip_conflicts is None:
            skip_conflicts = os.getenv("KG_READINESS_SKIP_CONFLICTS", "").lower() in {"1", "true", "yes"}
        existing_conflicts = (final_graph.get("dependency_details") or {}).get("conflicts", [])
        if skip_conflicts and isinstance(existing_conflicts, list) and existing_conflicts:
            print(f"▶ agent_07 conflicts: reusing {len(existing_conflicts)} completed analyses", flush=True)
            conflict_entries = [deepcopy(dict(item)) for item in existing_conflicts if isinstance(item, Mapping)]
        else:
            entity_results: dict[str, list[dict[str, Any]]] = {}
            api_workers = max(1, int(os.getenv("KG_READINESS_LLM_CONCURRENCY", "32")))
            conflict_workers = min(readiness_workers, api_workers)
            with ThreadPoolExecutor(max_workers=min(conflict_workers, max(1, len(groups))), thread_name_prefix="kg-conflict") as executor:
                futures = {executor.submit(analyse_group, entity, member_ids): entity for entity, member_ids in groups.items()}
                for future in as_completed(futures):
                    entity_results[futures[future]] = future.result()
            for entity in groups:
                conflict_entries.extend(entity_results.get(entity, []))
        conflict_entries = _normalise_conflict_entries(conflict_entries, ids)
        final_graph["dependency_details"]["conflicts"] = conflict_entries

        naming = naming_issues(final_graph)
        references = referential_integrity_issues(final_graph)
        entity_keys = list(entity_catalog.keys())
        conflict_by_rule: dict[str, list[dict[str, Any]]] = {}
        for conflict in conflict_entries:
            if len({str(value) for value in conflict.get("rule_ids", [])}) < 2:
                # Conflict readiness concerns interactions between distinct
                # rules. Legacy self-analysis records are not co-firing edges.
                continue
            for rule_id in conflict.get("rule_ids", []):
                conflict_by_rule.setdefault(str(rule_id), []).append(conflict)
        reviewed_rules = []
        contract_error_count = 0
        deferred_contract_error_count = 0
        final_contract_error_count = 0
        for rule in rules:
            contract_issues = [issue.as_dict() for issue in validate_rule_v2(rule, entity_catalog)]
            deferred_contract_error_count += sum(_is_deferred_contract_issue(issue, rule) for issue in contract_issues)
            contract_error_count += sum(not _is_deferred_contract_issue(issue, rule) for issue in contract_issues)
            issues = contract_issues
            final_issues = final_rule_issues(rule, entity_keys)
            final_contract_error_count += sum(not issue.get("evidence_limited") for issue in final_issues)
            issues.extend(final_issues)
            for conflict in conflict_by_rule.get(str(rule.get("rule_id")), []):
                if conflict.get("status") == "unresolved" or (conflict.get("status") == "conflict" and not str(conflict.get("resolution", "")).strip()):
                    issues.append({"requirement": "conflicts", "reason": conflict.get("reasoning", "entity-local conflict is unresolved")})
            if any(item.get("rule_id") == str(rule.get("rule_id")) for item in references):
                issues.append({"requirement": "referential_integrity", "reason": "rule has a dangling dependency reference"})
            completion_error = rule.pop("_evidence_completion_error", None)
            if completion_error:
                issues.append({"requirement": "evidence_completion", "reason": f"Provider rejected this rule's completion request and no further evidence could be gathered: {completion_error}"})
            reviewed_rules.append(mark_readiness(rule, issues))
        final_graph["business_rules"] = reviewed_rules
        baseline_sections = cited_sections(baseline)
        final_sections = cited_sections(final_graph)
        evidence_added_sections = final_sections - baseline_sections
        evidence_removed_sections = baseline_sections - final_sections
        corpus_change_reasons = {
            section: "Added as field-level evidence during the required full-document readiness review; the source document corpus is unchanged."
            for section in evidence_added_sections
        }
        corpus_change_reasons.update({
            section: "No longer cited after readiness evidence normalization; the source document corpus is unchanged and the affected rule remains traceable through its validated replacement citations."
            for section in evidence_removed_sections
        })
        manifest = corpus_manifest(baseline, final_graph, corpus_change_reasons)
        final_graph["corpus_manifest"] = manifest

        exception_bases = [rule.get("exception_basis") for rule in reviewed_rules]
        scope_bases = [rule.get("scope_basis") for rule in reviewed_rules]
        examples = [{"rule_id": rule.get("rule_id"), "before": before_scope.get(str(rule.get("rule_id"))), "after": rule.get("applicability_scope"), "scope_basis": rule.get("scope_basis")} for rule in reviewed_rules if before_scope.get(str(rule.get("rule_id"))) != rule.get("applicability_scope")][:5]
        non_conflicts = [entry for entry in conflict_entries if entry.get("status") == "non_conflict"]
        conflicts = [entry for entry in conflict_entries if entry.get("status") == "conflict"]
        unresolved = [rule for rule in reviewed_rules if rule.get("requires_review")]
        report = {
            "invariants": {
                "corpus_integrity": {"pass": manifest["pass"], "evidence": f"{len(manifest['input_sections'])} input and {len(manifest['final_sections'])} final cited sections; every change has an explicit reason.", **manifest},
                "naming_consistency": {"pass": not naming, "evidence": f"{len(entity_keys)} entity type keys checked; {len(naming)} violations.", "violations": naming},
                # Gated on contract_error_count alone (genuine v2 structural
                # violations — a malformed rule shape no amount of further
                # evidence-gathering can fix) rather than also on
                # final_contract_error_count (evidence/provenance gaps on an
                # otherwise well-formed rule). final_contract_error_count is
                # exactly what makes a rule requires_review — folding it into
                # this invariant made schema_consistency fail on every real
                # run that had any review-required rule, which always fires
                # main()'s SystemExit(2) before the SystemExit(3) branch that
                # launches agent_08 is ever reached, silently defeating the
                # auto-remediation this README documents. Both counts stay in
                # the evidence string for visibility.
                "schema_consistency": {
                    "pass": contract_error_count == 0,
                    "evidence": (
                        f"{len(reviewed_rules)} rules checked; {contract_error_count} blocking v2, "
                        f"{deferred_contract_error_count} deferred-capability v2, and "
                        f"{final_contract_error_count} final-readiness contract violations."
                    ),
                    "blocking_v2_violations": contract_error_count,
                    "deferred_capability_v2_violations": deferred_contract_error_count,
                },
                "referential_integrity": {"pass": not references, "evidence": f"{len(edges)} dependency edges checked; {len(references)} dangling references.", "violations": references},
            },
            "conflicts_and_dependencies": {"entities_checked": len(groups), "conflicts_found": len(conflicts), "dependency_chains_derived": len(chains), "conflict_examples": conflicts[:3], "non_conflict_examples": non_conflicts[:max(10, 3)], "conflict_example_shortfall": max(0, 3 - len(conflicts)), "non_conflict_example_shortfall": max(0, 3 - len(non_conflicts)), "cycles": cycles},
            "exception_recheck": {"rules_starting_with_not_found_in_chunk_recheck_needed": initial_chunk_rechecks, "resolved_to_explicit_in_source": exception_bases.count("explicit_in_source"), "resolved_to_explicitly_none_in_source": exception_bases.count("explicitly_none_in_source"), "resolved_to_no_cue_after_complete_search": exception_bases.count("no_exception_cue_found_in_complete_search"), "remaining_unresolved": exception_bases.count("unresolved_after_full_document_search"), "unresolved_rules": [{"rule_id": rule.get("rule_id"), "reason": (rule.get("exception_verification") or {}).get("unresolved_reason")} for rule in reviewed_rules if rule.get("exception_basis") == "unresolved_after_full_document_search"]},
            "scope_derivation": {"newly_populated_from_source_evidence": sum(newly_populated_dimension_count(before_scope.get(str(rule.get("rule_id"))), rule.get("applicability_scope")) for rule in reviewed_rules), "confirmed_explicitly_universal_in_source": scope_bases.count("explicitly_universal_in_source"), "confirmed_genuinely_unscoped": scope_bases.count("genuinely_unscoped"), "examples": examples},
            "rules_ready": sum(not rule.get("requires_review") for rule in reviewed_rules),
            "rules_requiring_review": len(unresolved),
            "review_required_rate_percent": round(len(unresolved) / max(1, len(reviewed_rules)) * 100, 2),
            "review_routes": {
                route: sum((rule.get("review_route") or {}).get("route") == route for rule in reviewed_rules)
                for route in ("none", "machine_repair", "case_management", "human_review")
            },
            "human_review_required_rules": sum(bool((rule.get("review_route") or {}).get("human_review_required")) for rule in reviewed_rules),
            "human_review_rate_percent": round(
                sum(bool((rule.get("review_route") or {}).get("human_review_required")) for rule in reviewed_rules)
                / max(1, len(reviewed_rules)) * 100,
                2,
            ),
            "rules_with_preserved_exception_effects": sum(bool(rule.get("exception_effects")) for rule in reviewed_rules),
        }
        return final_graph, report

    def run(self, baseline_path: Path, graph_path: Path, organized_dir: Path, output_dir: Path) -> dict[str, Any]:
        baseline, graph = json.loads(baseline_path.read_text()), json.loads(graph_path.read_text())
        self.checkpoint_path = output_dir / "agent_07_rule_checkpoint.jsonl"
        final_graph, report = self.complete(baseline, graph, str(organized_dir))
        output_dir.mkdir(parents=True, exist_ok=True)
        # This stage rewrites variables in place, which can invalidate a
        # relation derived before the rewrite. Re-check before writing so a
        # stale relation is dropped loudly rather than shipped attested.
        try:
            entails, _gating_stats = make_entailment_oracle(final_graph, document_id="agent_07-revalidation")
        except Exception:
            entails = None
        revalidation = revalidate_graph(final_graph, stage="agent_07", entails=entails)
        if revalidation["dropped"]:
            print(f"⚠️  agent_07 dropped {len(revalidation['dropped'])} rule relationship(s) "
                  f"invalidated by this stage's edits", flush=True)
        report["relation_revalidation"] = revalidation
        # ``related_rules`` is model-authored and never validated anywhere else,
        # so it is the one channel that can ship references to rules that were
        # deduplicated away -- or that never existed at all.
        related_integrity = prune_dangling_related_rules(final_graph, stage="agent_07")
        if related_integrity["dropped"]:
            print(f"⚠️  agent_07 dropped {len(related_integrity['dropped'])} related_rules "
                  f"reference(s) naming rules that are not in the graph", flush=True)
        report["related_rules_integrity"] = related_integrity
        graph_path.write_text(json.dumps(final_graph, indent=2, ensure_ascii=False) + "\n")
        (output_dir / "corpus_manifest.json").write_text(json.dumps(final_graph["corpus_manifest"], indent=2) + "\n")
        (output_dir / "kg_readiness_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        (output_dir / "kg_readiness_report.md").write_text(_report_markdown(report))
        print(f"✅ agent_07 completed: {report['rules_ready']} ready, {report['rules_requiring_review']} require review", flush=True)
        return report


def required_inputs(config) -> list[Path]:
    """Upstream artifacts this stage cannot start without."""
    return [
        config.get_rules_with_entities_dir() / "compliance_knowledge_graph.json",
        config.get_optimized_dir() / "optimized_compliance_knowledge_graph.json",
    ]


def main() -> None:
    config = get_config()
    # Reported as a missing artifact rather than an unhandled FileNotFoundError:
    # a traceback tells an operator nothing about which stage to run first, and
    # the exit code it produced (1) is not one the orchestrator can route.
    missing = [str(path) for path in required_inputs(config) if not path.exists()]
    if missing:
        print("ERROR: required upstream artifact(s) missing: " + ", ".join(missing), flush=True)
        print("   Run the pipeline through agent_06 first.", flush=True)
        raise SystemExit(2)
    resolver = OpenAIEvidenceResolver(config.get_api_key(), config.get_optimizer_model_name(), config.get_reasoning_effort())
    completer = ExecutableReadinessCompleter(resolver)
    baseline = config.get_rules_with_entities_dir() / "compliance_knowledge_graph.json"
    output_dir = config.get_optimized_dir()
    report = completer.run(baseline, output_dir / "optimized_compliance_knowledge_graph.json", config.get_organized_dir(), output_dir)
    invariant_pass = all(result["pass"] for result in report["invariants"].values())
    if not invariant_pass:
        print("❌ agent_07 invariant validation failed; inspect kg_readiness_report.json.", flush=True)
        raise SystemExit(2)
    if report["rules_requiring_review"]:
        print("⚠️ agent_07 found rules requiring focused agent_08 remediation.", flush=True)
        raise SystemExit(3)


if __name__ == "__main__":
    main()
