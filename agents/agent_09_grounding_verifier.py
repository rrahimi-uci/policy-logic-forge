#!/usr/bin/env python3
"""agent_09: independent, claim-level source-grounding certification."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import unicodedata
from typing import Any, Iterable, Mapping, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.agent_08_readiness_remediator import JsonlCheckpoint, _stable_hash
from utils.citations import (
    MAX_ANCHOR_SPAN_EXPANSION,
    MIN_REPAIR_CHARS,
    MIN_REPAIR_COVERAGE,
    normalise_text,
    normalise_text_preserve_case,
    repair_by_anchors,
    repair_citation,
    resolve_citation_span,
)
from utils.config import get_config
from utils.kg_readiness import mark_readiness, source_document_index
from utils.llm_client import create_llm_client
from utils.prompt_manager import get_prompt_manager
from utils.rule_contract import validate_rule_v2


VERDICTS = {"supported", "contradicted", "insufficient_evidence"}
MODEL_CLAIM_TYPES = {
    "description", "condition", "outcome", "party", "scope", "exception",
}
CORE_CLAIM_TYPES = {"description", "condition", "outcome"}
ENRICHMENT_CLAIM_TYPES = {"party", "scope", "exception"}
GROUNDING_DIMENSIONS = ("core_rule", "enrichment", "contract")
# condition_logic and test_vector are excluded on purpose: both are values the
# pipeline DERIVES from a rule's own condition_predicates/outcomes rather than
# facts a policy sentence ever states in those terms. Asking the grounding
# model for a literal source quote for "Conditions combine as {predicate_ref:
# p1}" or a synthesized {inputs -> expected_output} example has no possible
# verbatim answer, so it was scoring near-100% insufficient_evidence on every
# graph regardless of how well-grounded the rule actually was. Both are
# instead verified structurally in deterministic_rule_claims: condition_logic
# against validate_rule_v2's own predicate-coverage check, and test_vector
# against the rule's own declared variables/outcomes. See
# GroundingVerifier._verify_test_vector.
#
# rule_name (claim_type "generated_label") is excluded for the identical
# reason: it is a short display title the extraction pipeline invents for
# human review navigation (e.g. "Unpaid PACE Financing Bars Delivery"), never
# a sentence any source document states in those words. Confirmed against a
# real run's grounding report: the verifier consistently rejected it with
# reasoning like "does not state the supplied generated rule name" -- correct
# on its own terms, but that single claim then flipped the *entire rule* to
# grounding_status "failed" (see _finalize_rule_results/verify_graph, which
# fail a rule closed if *any* claim is unsupported), even when every
# source-derived claim (condition, outcome, party, scope, exception,
# description) was fully grounded. Verified structurally in
# deterministic_rule_claims instead: always "supported", since a generated
# label has no source-groundedness dimension to check beyond the
# non-emptiness extract_claims() already gates it on. The real `description`
# field stays a MODEL_CLAIM_TYPE -- unlike rule_name it is a real
# paraphrase/summary of source content, and the same real run's data shows it
# catching genuine extraction errors (e.g. a rule paraphrasing source
# "should be equal" as "must equal", or a permissive "may be excluded" as a
# definitive boolean outcome) that are worth keeping in front of a reviewer.


# Citation verification/repair lives in utils.citations so agent_07 (which
# CREATES citations in its completion resolver) and this module (which
# CERTIFIES them) cannot drift apart. Names kept private here for callers
# and tests that already import them.
_normalise_text = normalise_text
_normalise_text_preserve_case = normalise_text_preserve_case
_repair_by_anchors = repair_by_anchors
_repair_near_match = repair_citation


def _iter_references(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, Mapping):
                yield item


def _json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _write_text_atomic(path: Path, content: str) -> None:
    """Replace an artifact only after its complete content reaches disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def extract_claims(rule: Mapping[str, Any], graph: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Project every executable/source-bearing rule field into atomic claims."""
    claims: list[dict[str, Any]] = []

    def add(claim_id: str, field_path: str, claim_type: str, statement: str, structured: Any) -> None:
        claims.append({
            "claim_id": claim_id,
            "field_path": field_path,
            "claim_type": claim_type,
            "statement": statement,
            "structured": deepcopy(structured),
        })

    rule_name = str(rule.get("rule_name", "")).strip()
    if rule_name:
        add("rule_name", "rule_name", "generated_label", rule_name, rule_name)
    description = str(rule.get("description", "")).strip()
    if description:
        add("description", "description", "description", description, description)

    for index, predicate in enumerate(rule.get("condition_predicates", []) or []):
        if not isinstance(predicate, Mapping):
            continue
        predicate_id = str(predicate.get("predicate_id") or index)
        statement = f"{predicate.get('variable')} {predicate.get('operator')} {_json_value(predicate.get('value'))}"
        add(f"condition:{predicate_id}", f"condition_predicates[{index}]", "condition", statement, predicate)

    if rule.get("condition_logic") is not None:
        add(
            "condition_logic", "condition_logic", "condition_logic",
            f"Conditions combine as {_json_value(rule.get('condition_logic'))}", rule.get("condition_logic"),
        )

    for index, variable in enumerate(rule.get("variables", []) or []):
        if not isinstance(variable, Mapping):
            continue
        add(
            f"variable:{index}", f"variables[{index}]", "variable",
            f"Variable {variable.get('name')} has contract {_json_value(variable)}", variable,
        )

    for index, outcome in enumerate(rule.get("outcomes", []) or []):
        if not isinstance(outcome, Mapping):
            continue
        statement = f"{outcome.get('variable')} {outcome.get('operator')} {_json_value(outcome.get('value'))}"
        add(f"outcome:{index}", f"outcomes[{index}]", "outcome", statement, outcome)

    party = str(rule.get("responsible_party", "")).strip()
    if party:
        add("responsible_party", "responsible_party", "party", f"Responsible party is {party}", party)
    for index, party in enumerate(rule.get("counterparties", []) or []):
        if str(party).strip():
            add(f"counterparty:{index}", f"counterparties[{index}]", "party", f"Counterparty is {party}", party)
    for field in ("entity_type", "source_entity"):
        if str(rule.get(field, "")).strip():
            add(f"entity:{field}", field, "entity_attachment", f"{field} is {rule[field]}", rule[field])
    for index, entity in enumerate(rule.get("related_entities", []) or []):
        if str(entity).strip():
            add(
                f"entity:related:{index}", f"related_entities[{index}]", "entity_attachment",
                f"Rule is attached to entity {entity}", entity,
            )

    scope = rule.get("applicability_scope") or {}
    if isinstance(scope, Mapping):
        for key in ("loan_types", "occupancy_types", "transaction_types"):
            for index, value in enumerate(scope.get(key, []) or []):
                add(f"scope:{key}:{index}", f"applicability_scope.{key}[{index}]", "scope", f"Applies to {key}: {value}", value)
    scope_basis = rule.get("scope_basis")
    if scope_basis in {"explicitly_universal_in_source", "genuinely_unscoped"}:
        add("scope_basis", "scope_basis", "scope", f"Scope basis is {scope_basis}", scope_basis)

    for index, exception in enumerate(rule.get("exceptions", []) or []):
        if not isinstance(exception, Mapping):
            continue
        predicate_id = str(exception.get("predicate_id") or index)
        statement = f"Exception when {exception.get('variable')} {exception.get('operator')} {_json_value(exception.get('value'))}"
        add(f"exception:{predicate_id}", f"exceptions[{index}]", "exception", statement, exception)
    for index, effect in enumerate(rule.get("exception_effects", []) or []):
        if not isinstance(effect, Mapping):
            continue
        effect_id = str(effect.get("effect_id") or index)
        statement = f"Exception effect {effect.get('variable')} {effect.get('operator')} {_json_value(effect.get('value'))}"
        add(f"exception_effect:{effect_id}", f"exception_effects[{index}]", "exception", statement, effect)
    if rule.get("exception_basis") == "explicitly_none_in_source":
        add(
            "exception_basis", "exception_basis", "exception",
            "The complete cited source contains no exception to this rule", "explicitly_none_in_source",
        )

    for field in ("rule_type", "rule_category", "versioning_status"):
        if rule.get(field) is not None:
            add(field, field, "classification", f"{field} is {_json_value(rule[field])}", rule[field])
    if rule.get("recommended_hit_policy") is not None:
        add(
            "recommended_hit_policy", "recommended_hit_policy", "execution",
            f"The derived DMN hit policy is {rule['recommended_hit_policy']}", rule["recommended_hit_policy"],
        )
    if isinstance(rule.get("execution"), Mapping):
        add(
            "execution", "execution", "execution",
            f"The executable DMN/BPMN projection is {_json_value(rule['execution'])}", rule["execution"],
        )

    for index, vector in enumerate(rule.get("test_vectors", []) or []):
        if isinstance(vector, Mapping):
            add(
                f"test_vector:{index}", f"test_vectors[{index}]", "test_vector",
                f"Inputs {_json_value(vector.get('inputs'))} produce {_json_value(vector.get('expected_output'))}", vector,
            )

    return claims


class GroundingResolver(Protocol):
    model: str
    reasoning_effort: str

    def verify(self, packets: list[Mapping[str, Any]]) -> list[dict[str, Any]]: ...


class OpenAIGroundingResolver:
    def __init__(self, api_key: str, model: str, reasoning_effort: str) -> None:
        concurrency = max(1, int(os.getenv("KG_GROUNDING_LLM_CONCURRENCY", "32")))
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.client = create_llm_client(api_key=api_key, model=model, concurrency=concurrency)
        self.prompts = get_prompt_manager()

    @staticmethod
    def _parse(content: str) -> dict[str, Any]:
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        try:
            value = json.loads(content)
        except json.JSONDecodeError as original_error:
            # Long grounding batches can contain one malformed delimiter even
            # with provider JSON mode. Repair only that object in strict mode;
            # concatenated values and non-objects remain rejected.
            try:
                from json_repair import repair_json

                value = repair_json(content, return_objects=True, strict=True)
            except Exception:
                raise original_error
        if not isinstance(value, dict) or not isinstance(value.get("verifications"), list):
            raise ValueError("agent_09 response must contain a verifications list")
        return value

    @staticmethod
    def _split_packets(
        packets: list[Mapping[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
        """Split a packet batch by claim count without losing packet metadata."""
        total = sum(len(packet.get("claims", []) or []) for packet in packets)
        if total <= 1:
            return None
        target = max(1, total // 2)
        left: list[dict[str, Any]] = []
        right: list[dict[str, Any]] = []
        left_count = 0
        for packet in packets:
            claims = list(packet.get("claims", []) or [])
            if not claims:
                continue
            if left_count < target:
                take = min(len(claims), target - left_count)
                left.append({**dict(packet), "claims": claims[:take]})
                left_count += take
                if take < len(claims):
                    right.append({**dict(packet), "claims": claims[take:]})
            else:
                right.append({**dict(packet), "claims": claims})
        if not left or not right:
            return None
        return left, right

    def verify(self, packets: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
        prompt = self.prompts.format_prompt(
            "grounding_verification_batch",
            packets_json=json.dumps(packets, ensure_ascii=False),
        )
        attempts = max(1, int(os.getenv("KG_GROUNDING_PARSE_ATTEMPTS", "3")))
        max_tokens = max(2000, int(os.getenv("KG_GROUNDING_MAX_TOKENS", "16000")))
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                response = self.client.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                    reasoning_effort=self.reasoning_effort,
                )
                value = self._parse(response.choices[0].message.content or "")
                results = [dict(item) for item in value["verifications"] if isinstance(item, Mapping)]
                expected = Counter(
                    (str(packet["rule_id"]), str(claim["claim_id"]))
                    for packet in packets for claim in packet.get("claims", [])
                )
                returned = Counter((str(item.get("rule_id")), str(item.get("claim_id"))) for item in results)
                if returned != expected:
                    split = self._split_packets(packets)
                    if split is not None:
                        print(
                            "⚠️ agent_09 response coverage mismatch; splitting the claim batch",
                            flush=True,
                        )
                        return self.verify(split[0]) + self.verify(split[1])
                    # A single-claim response with the wrong identifier cannot
                    # be repaired by splitting. Return no usable result so the
                    # verifier finalizer records the claim as missing/review
                    # required instead of aborting the whole dataset run.
                    if sum(expected.values()) <= 1 and returned:
                        return []
                    raise ValueError(
                        f"verifier response coverage mismatch: expected {sum(expected.values())}, "
                        f"received {sum(returned.values())}"
                    )
                return results
            except Exception as exc:
                last_error = exc
                prompt += "\n\nReturn complete valid JSON only, with every requested rule_id and claim_id exactly once."
                print(f"⚠️ agent_09 request retry {attempt}/{attempts}: {exc}", flush=True)
        assert last_error is not None
        raise last_error


class GroundingVerifier:
    """Certify claims without modifying their substantive content."""

    CHECKPOINT_VERSION = 3

    def __init__(self, resolver: GroundingResolver | None) -> None:
        self.resolver = resolver

    @staticmethod
    def _chunk_for_path(corpus: Mapping[str, Any], path_value: str) -> Mapping[str, Any] | None:
        wanted = str(path_value or "").replace("\\", "/").lstrip("./")
        if not wanted:
            return None
        exact = [item for item in corpus.get("chunks", []) if str(item.get("chunk_path", "")).replace("\\", "/") == wanted]
        if exact:
            return exact[0]
        suffix = [
            item for item in corpus.get("chunks", [])
            if wanted.endswith(str(item.get("chunk_path", "")).replace("\\", "/"))
            or str(item.get("chunk_path", "")).replace("\\", "/").endswith(wanted)
        ]
        return suffix[0] if len(suffix) == 1 else None

    @classmethod
    def _evidence_records(
        cls,
        rules: Mapping[str, Any] | Iterable[Mapping[str, Any]],
        corpus: Mapping[str, Any],
        max_chars: int,
    ) -> list[dict[str, Any]]:
        candidates: list[tuple[Mapping[str, Any], str]] = []
        source_rules = [rules] if isinstance(rules, Mapping) else list(rules)
        for rule in source_rules:
            candidates.extend(
                (item, "source_reference")
                for item in _iter_references(rule.get("source_reference"))
            )
            field_evidence = rule.get("field_evidence")
            if isinstance(field_evidence, Mapping):
                for field_name, value in field_evidence.items():
                    candidates.extend(
                        (item, str(field_name)) for item in _iter_references(value)
                    )
            for parent_name, parent in (
                ("exceptions", rule.get("exception_verification")),
                ("applicability_scope", rule.get("scope_derivation")),
            ):
                if isinstance(parent, Mapping):
                    candidates.extend(
                        (item, parent_name)
                        for item in _iter_references(
                            parent.get("evidence") or parent.get("source_evidence")
                        )
                    )

        unique: dict[tuple[str, str, str], dict[str, Any]] = {}
        for item, supporting_field in candidates:
            key = (
                str(item.get("chunk_path", "")), str(item.get("section_id", "")),
                str(item.get("source_text", item.get("text", ""))),
            )
            if any(key):
                entry = unique.setdefault(key, {"item": item, "supports_fields": set()})
                entry["supports_fields"].add(supporting_field)

        records = []
        used_chars = 0
        for (chunk_path, section_id, quote), evidence_entry in sorted(unique.items()):
            chunk = cls._chunk_for_path(corpus, chunk_path)
            chunk_text = str((chunk or {}).get("text", ""))
            original_quote = quote
            span = resolve_citation_span(quote, chunk_text) if chunk else None
            quote_found = span is not None
            if span:
                quote = str(span["source_text"])
            remaining = max(0, max_chars - used_chars)
            context = ""
            if remaining and chunk_text:
                position = int(span["start_offset"]) if span else -1
                start = max(0, position - remaining // 3) if position >= 0 else 0
                context = chunk_text[start:start + remaining]
                used_chars += len(context)
            evidence_material = "|".join((
                chunk_path,
                section_id,
                str((chunk or {}).get("sha256", "")),
                str((span or {}).get("start_offset", -1)),
                str((span or {}).get("end_offset", -1)),
            ))
            record = {
                "evidence_id": "EV-" + hashlib.sha256(evidence_material.encode()).hexdigest()[:16],
                "chunk_path": chunk_path,
                "section_id": section_id,
                "chunk_sha256": (chunk or {}).get("sha256"),
                "source_text": quote,
                "source_text_found_in_chunk": quote_found,
                "start_offset": (span or {}).get("start_offset"),
                "end_offset": (span or {}).get("end_offset"),
                "context": context,
                "supports_fields": sorted(evidence_entry["supports_fields"]),
            }
            if span and span.get("source_text_repaired"):
                # Transparency/audit trail: a reviewer (or future analysis
                # of the grounding report) can see this citation was
                # corrected to a real corpus substring rather than accepted
                # as the extraction agent originally wrote it.
                record["source_text_repaired"] = True
                record["original_source_text"] = original_quote
            records.append(record)
        return records

    @classmethod
    def build_packet(
        cls,
        rule: Mapping[str, Any],
        corpus: Mapping[str, Any],
        max_chars: int,
        graph: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        claims = [claim for claim in extract_claims(rule) if claim.get("claim_type") in MODEL_CLAIM_TYPES]

        def provenance(parent: Any, count_field: str) -> dict[str, Any] | None:
            if not isinstance(parent, Mapping):
                return None
            return {
                "status": parent.get("status"),
                count_field: parent.get(count_field),
                "corpus_sha256": parent.get("corpus_sha256"),
                "searched_document_ids": parent.get("searched_document_ids"),
                "unresolved_reason": parent.get("unresolved_reason"),
            }

        evidence = cls._evidence_records(rule, corpus, max_chars)
        for claim in claims:
            field_name = cls._claim_evidence_field(claim)
            claim["eligible_evidence_ids"] = [
                item["evidence_id"]
                for item in evidence
                if field_name in item.get("supports_fields", [])
            ]

        return {
            "rule_id": str(rule.get("rule_id", "")),
            "claims": claims,
            "rule_logic": {
                "condition_predicates": rule.get("condition_predicates"),
                "condition_logic": rule.get("condition_logic"),
                "outcomes": rule.get("outcomes"),
                "exceptions": rule.get("exceptions"),
                "exception_effects": rule.get("exception_effects"),
            },
            "search_provenance": {
                "current_corpus_sha256": corpus.get("corpus_sha256"),
                "current_chunk_count": corpus.get("chunk_count"),
                "exception_verification": provenance(rule.get("exception_verification"), "searched_chunk_count"),
                "scope_derivation": provenance(rule.get("scope_derivation"), "reviewed_chunk_count"),
            },
            "evidence": evidence,
        }

    @staticmethod
    def _claim_evidence_field(claim: Mapping[str, Any]) -> str:
        field_path = str(claim.get("field_path") or "")
        if field_path == "description":
            return "source_reference"
        if field_path.startswith("counterparties"):
            return "counterparties"
        if field_path.startswith("applicability_scope"):
            return "applicability_scope"
        if field_path.startswith("exceptions") or field_path.startswith("exception_effects"):
            return "exceptions"
        return field_path.split("[", 1)[0].split(".", 1)[0]

    @classmethod
    def build_relationship_packets(
        cls,
        graph: Mapping[str, Any],
        corpus: Mapping[str, Any],
        max_chars: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Build bounded model packets and deterministic relationship checks."""
        rules = {
            str(rule.get("rule_id")): rule
            for rule in graph.get("business_rules", [])
            if isinstance(rule, Mapping) and rule.get("rule_id")
        }

        def logic(rule_id: str) -> dict[str, Any]:
            rule = rules[rule_id]
            return {
                "rule_id": rule_id,
                "condition_predicates": rule.get("condition_predicates"),
                "condition_logic": rule.get("condition_logic"),
                "outcomes": rule.get("outcomes"),
                "exceptions": rule.get("exceptions"),
                "exception_effects": rule.get("exception_effects"),
                "applicability_scope": rule.get("applicability_scope"),
            }

        def primary_evidence(rule_ids: Iterable[str]) -> list[dict[str, Any]]:
            minimal = [
                {"source_reference": rules[rule_id].get("source_reference")}
                for rule_id in rule_ids if rule_id in rules
            ]
            return cls._evidence_records(minimal, corpus, max_chars)

        packets: list[dict[str, Any]] = []
        deterministic: list[dict[str, Any]] = []
        details = graph.get("dependency_details")
        details = details if isinstance(details, Mapping) else {}
        for index, dependency in enumerate(details.get("dependencies", []) or []):
            if not isinstance(dependency, Mapping):
                continue
            # A relation derived from the rule contracts is not a claim about
            # the source text, so asking a model to find it there is both
            # wasteful and wrong: the derivation is the proof, and
            # rule_dependencies.revalidate_graph re-checks it whenever the
            # graph changes. Only narrative relations still need grounding.
            if str(dependency.get("basis") or "").strip().lower() in {"deterministic", "solver"}:
                deterministic.append({
                    "relationship_id": f"@dependency:{index}",
                    "field_path": f"dependency_details.dependencies[{index}]",
                    "status": "supported",
                    "affected_rule_ids": [
                        str(dependency.get("source_rule_id", "")),
                        str(dependency.get("target_rule_id", "")),
                    ],
                    "reasoning": (
                        f"Derived deterministically from the rule contracts on "
                        f"{', '.join(str(s) for s in (dependency.get('symbols') or [])) or 'shared symbols'}; "
                        "re-validated against the current graph."
                    ),
                })
                continue
            rule_ids = [str(dependency.get("source_rule_id", "")), str(dependency.get("target_rule_id", ""))]
            structured = {**dict(dependency), "affected_rule_ids": rule_ids}
            packets.append({
                "rule_id": f"@dependency:{index}",
                "packet_kind": "graph_relationship",
                "claims": [{
                    "claim_id": "relationship", "field_path": f"dependency_details.dependencies[{index}]",
                    "claim_type": "dependency",
                    "statement": f"Rule {rule_ids[0]} has a {dependency.get('dependency_type')} dependency on rule {rule_ids[1]}",
                    "structured": structured,
                }],
                "rule_logic": {"related_rules": [logic(value) for value in rule_ids if value in rules]},
                "evidence": primary_evidence(rule_ids),
            })

        for index, conflict in enumerate(details.get("conflicts", []) or []):
            if not isinstance(conflict, Mapping):
                continue
            rule_ids = [str(value) for value in conflict.get("rule_ids", []) if str(value) in rules]
            outcome_names = {
                rule_id: {
                    str(item.get("variable"))
                    for item in rules[rule_id].get("outcomes", [])
                    if isinstance(item, Mapping) and item.get("variable")
                }
                for rule_id in rule_ids
            }
            all_disjoint = len(rule_ids) >= 2 and all(
                outcome_names[left].isdisjoint(outcome_names[right])
                for left_index, left in enumerate(rule_ids)
                for right in rule_ids[left_index + 1:]
            )
            anchor_disjoint = len(rule_ids) >= 2 and all(
                outcome_names[rule_ids[0]].isdisjoint(outcome_names[other])
                for other in rule_ids[1:]
            )
            deterministic_disjoint_record = "disjoint outcome variable" in str(
                conflict.get("reasoning", "")
            ).casefold()
            if (
                conflict.get("status") == "non_conflict"
                and deterministic_disjoint_record
                and (all_disjoint or anchor_disjoint)
            ):
                deterministic.append({
                    "relationship_id": f"@conflict:{index}",
                    "field_path": f"dependency_details.conflicts[{index}]",
                    "status": "supported",
                    "affected_rule_ids": rule_ids,
                    "reasoning": "Independent outcome-variable comparison confirms the recorded disjoint-output non-conflict.",
                })
                continue
            structured = {**dict(conflict), "affected_rule_ids": rule_ids}
            packets.append({
                "rule_id": f"@conflict:{index}",
                "packet_kind": "graph_relationship",
                "claims": [{
                    "claim_id": "relationship", "field_path": f"dependency_details.conflicts[{index}]",
                    "claim_type": "conflict",
                    "statement": f"Rules {', '.join(rule_ids)} are classified as {conflict.get('status')}; "
                    f"resolution: {conflict.get('resolution')}",
                    "structured": structured,
                }],
                "rule_logic": {"related_rules": [logic(value) for value in rule_ids]},
                "evidence": primary_evidence(rule_ids),
            })
        return packets, deterministic

    @staticmethod
    def make_batches(
        packets: list[dict[str, Any]],
        max_rules: int,
        max_claims: int,
        max_batch_chars: int = 80000,
    ) -> list[list[dict[str, Any]]]:
        # A single unusually rich rule may exceed the claim ceiling. Split its
        # claim list into independently checkpointed fragments while repeating
        # the immutable rule/evidence context.
        fragments: list[dict[str, Any]] = []
        for packet in packets:
            claims = list(packet.get("claims", []))
            if not claims:
                fragments.append(packet)
                continue
            for start in range(0, len(claims), max_claims):
                fragment = dict(packet)
                fragment["claims"] = claims[start:start + max_claims]
                fragments.append(fragment)
        batches: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        claim_count = 0
        serialized_chars = 0
        for packet in fragments:
            packet_claims = len(packet.get("claims", []))
            packet_chars = len(json.dumps(packet, ensure_ascii=False, separators=(",", ":")))
            if current and (
                len(current) >= max_rules
                or claim_count + packet_claims > max_claims
                or serialized_chars + packet_chars > max_batch_chars
            ):
                batches.append(current)
                current, claim_count, serialized_chars = [], 0, 0
            current.append(packet)
            claim_count += packet_claims
            serialized_chars += packet_chars
        if current:
            batches.append(current)
        return batches

    @staticmethod
    def _canonical_evidence(
        result: Mapping[str, Any], packet: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        """Resolve a verifier-selected immutable evidence record."""
        evidence_id = str(result.get("evidence_id") or "")
        if not evidence_id:
            return None
        evidence = next((item for item in packet.get("evidence", []) if item.get("evidence_id") == evidence_id), None)
        if not evidence or evidence.get("source_text_found_in_chunk") is not True:
            return None
        return evidence

    @classmethod
    def _quote_is_authentic(cls, result: Mapping[str, Any], packet: Mapping[str, Any]) -> bool:
        """Compatibility predicate: authenticity comes from the evidence ID.

        The model selects an evidence record and judges entailment; deterministic
        code owns the quotation.  Requiring the model to retranscribe an already
        immutable source span created false failures when punctuation or spacing
        drifted even though the selected evidence record was authentic.
        """
        return cls._canonical_evidence(result, packet) is not None

    @staticmethod
    def _claim_dimension(claim: Mapping[str, Any]) -> str:
        claim_type = str(claim.get("claim_type") or "")
        if claim_type in CORE_CLAIM_TYPES:
            return "core_rule"
        if claim_type in ENRICHMENT_CLAIM_TYPES:
            return "enrichment"
        return "contract"

    @classmethod
    def _dimension_summary(
        cls, results: Iterable[Mapping[str, Any]], dimension: str
    ) -> dict[str, Any]:
        selected = [item for item in results if cls._claim_dimension(item) == dimension]
        counts = {
            verdict: sum(item.get("verdict") == verdict for item in selected)
            for verdict in VERDICTS
        }
        status = (
            "not_applicable" if not selected else
            "certified" if counts["contradicted"] == 0 and counts["insufficient_evidence"] == 0 else
            "failed"
        )
        return {
            "status": status,
            "claim_count": len(selected),
            "counts": counts,
            "failed_claim_ids": [
                str(item.get("claim_id")) for item in selected
                if item.get("verdict") != "supported"
            ],
        }

    @classmethod
    def _verdict_has_valid_evidence(
        cls,
        result: Mapping[str, Any],
        claim: Mapping[str, Any],
        packet: Mapping[str, Any],
    ) -> bool:
        if claim.get("claim_type") in {"dependency", "conflict"}:
            return bool(str(result.get("reasoning", "")).strip())
        if claim.get("claim_id") == "exception_basis" and claim.get("structured") == "explicitly_none_in_source":
            provenance = (packet.get("search_provenance") or {}).get("exception_verification") or {}
            return cls._quote_is_authentic(result, packet) or (
                provenance.get("status") == "explicitly_none_in_source"
                and provenance.get("corpus_sha256") == (packet.get("search_provenance") or {}).get("current_corpus_sha256")
                and provenance.get("searched_chunk_count") == (packet.get("search_provenance") or {}).get("current_chunk_count")
            )
        if "eligible_evidence_ids" not in claim:
            return cls._quote_is_authentic(result, packet)
        evidence_id = str(result.get("evidence_id") or "")
        eligible_ids = {str(value) for value in claim.get("eligible_evidence_ids", [])}
        return evidence_id in eligible_ids and cls._quote_is_authentic(result, packet)

    @staticmethod
    def _verify_test_vector(claim: Mapping[str, Any], rule: Mapping[str, Any]) -> tuple[str, str]:
        """Check a test vector references only variables/outcomes the rule itself declares.

        This is a referential-integrity check, not an arithmetic one: it does not
        evaluate condition_predicates against the vector's inputs to confirm the
        expected_output actually follows. It catches a test vector that names a
        variable or outcome the rule never declared — a real defect — without
        requiring the vector to be quotable from source prose, which it never is.
        """
        vector = claim.get("structured") if isinstance(claim.get("structured"), Mapping) else {}
        inputs = vector.get("inputs") if isinstance(vector.get("inputs"), Mapping) else {}
        expected = vector.get("expected_output") if isinstance(vector.get("expected_output"), Mapping) else {}
        variable_names = {
            str(v.get("name")) for v in (rule.get("variables") or [])
            if isinstance(v, Mapping) and v.get("name")
        }
        outcome_names = {
            str(o.get("variable")) for o in (rule.get("outcomes") or [])
            if isinstance(o, Mapping) and o.get("variable")
        }
        unknown_inputs = sorted(set(inputs) - variable_names)
        unknown_outputs = sorted(set(expected) - outcome_names)
        if unknown_inputs or unknown_outputs:
            parts = []
            if unknown_inputs:
                parts.append(f"input(s) {unknown_inputs} are not declared in this rule's variables")
            if unknown_outputs:
                parts.append(f"expected_output key(s) {unknown_outputs} match no declared outcome variable")
            return "insufficient_evidence", "; ".join(parts)
        if not inputs and not expected:
            return "insufficient_evidence", "Test vector has no inputs or expected_output to verify."
        return (
            "supported",
            "Test vector inputs and expected_output reference only variables and outcomes "
            "this rule itself declares; verified structurally against the rule's own "
            "contract, not against source prose.",
        )

    @classmethod
    def deterministic_rule_claims(cls, rule: Mapping[str, Any], entity_keys: Iterable[str]) -> list[dict[str, Any]]:
        """Verify derived contract fields structurally after source claims."""
        issues = validate_rule_v2(rule, entity_keys)
        default_reason = "Derived field is internally consistent with the uniform v2 rule contract."

        logic_issues = [issue for issue in issues if issue.path == "condition_logic"]
        logic_verdict = "supported" if not logic_issues else "insufficient_evidence"
        logic_reason = (
            "; ".join(f"{issue.path}: {issue.message}" for issue in logic_issues)
            if logic_issues else
            "Condition logic references each declared predicate exactly once; verified "
            "structurally against condition_predicates, not against source prose."
        )

        results = []
        for claim in extract_claims(rule):
            claim_type = claim.get("claim_type")
            if claim_type in MODEL_CLAIM_TYPES:
                continue
            if claim_type == "condition_logic":
                verdict, reason = logic_verdict, logic_reason
            elif claim_type == "test_vector":
                verdict, reason = cls._verify_test_vector(claim, rule)
            elif claim_type == "generated_label":
                verdict, reason = "supported", (
                    "rule_name is a display label the pipeline generates for human review "
                    "navigation, not a fact any source sentence states in these words; "
                    "verified structurally (non-empty, per extract_claims), not against "
                    "source prose."
                )
            else:
                field_path = str(claim.get("field_path", ""))
                if claim_type == "execution":
                    relevant_prefixes = ("condition_predicates", "condition_logic", "variables", "outcomes", "recommended_hit_policy", "execution")
                else:
                    relevant_prefixes = (field_path,)
                relevant = [
                    issue for issue in issues
                    if any(
                        prefix and (
                            issue.path == prefix
                            or issue.path.startswith(prefix + ".")
                            or issue.path.startswith(prefix + "[")
                        )
                        for prefix in relevant_prefixes
                    )
                ]
                verdict = "supported" if not relevant else "insufficient_evidence"
                reason = default_reason if not relevant else "; ".join(
                    f"{issue.path}: {issue.message}" for issue in relevant
                )
            results.append({
                **claim,
                "verdict": verdict,
                "evidence_id": None,
                "supporting_quote": None,
                "reasoning": reason,
            })
        return results

    @classmethod
    def _finalize_rule_results(
        cls,
        packet: Mapping[str, Any],
        raw_results: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        rule_id = str(packet.get("rule_id"))
        returned = {
            str(item.get("claim_id")): item
            for item in raw_results
            if str(item.get("rule_id")) == rule_id and item.get("claim_id")
        }
        finalized = []
        for claim in packet.get("claims", []):
            claim_id = str(claim.get("claim_id"))
            item = dict(returned.get(claim_id, {}))
            verdict = str(item.get("verdict", ""))
            reason = str(item.get("reasoning", "")).strip()
            provenance = packet.get("search_provenance") or {}
            current_digest = provenance.get("current_corpus_sha256")
            current_count = provenance.get("current_chunk_count")
            negative_provenance = None
            if claim_id == "exception_basis" and claim.get("structured") == "explicitly_none_in_source":
                negative_provenance = provenance.get("exception_verification") or {}
            elif claim_id == "scope_basis" and claim.get("structured") == "genuinely_unscoped":
                negative_provenance = provenance.get("scope_derivation") or {}
            provenance_certified = bool(
                isinstance(negative_provenance, Mapping)
                and current_digest
                and negative_provenance.get("status") == claim.get("structured")
                and negative_provenance.get("corpus_sha256") == current_digest
                and negative_provenance.get(
                    "searched_chunk_count" if claim_id == "exception_basis" else "reviewed_chunk_count"
                ) == current_count
            )
            if provenance_certified:
                # Absence claims cannot be grounded by quoting one sentence.
                # A complete, corpus-hash-bound search is the evidence. This
                # overrides an LLM's expected "insufficient" verdict without
                # weakening any positive source claim.
                verdict = "supported"
                reason = (
                    "Certified deterministically from matching complete-corpus search provenance "
                    "bound to the current corpus hash and chunk count."
                )
            elif verdict not in VERDICTS:
                verdict, reason = "insufficient_evidence", "Verifier omitted this claim or returned an invalid verdict."
            canonical_evidence = None
            if verdict in {"supported", "contradicted"} and not provenance_certified:
                if not cls._verdict_has_valid_evidence(item, claim, packet):
                    verdict = "insufficient_evidence"
                    reason = "Verifier did not select an authentic evidence record present in the corpus."
                else:
                    canonical_evidence = cls._canonical_evidence(item, packet)
            finalized.append({
                "claim_id": claim_id,
                "field_path": claim.get("field_path"),
                "claim_type": claim.get("claim_type"),
                "statement": claim.get("statement"),
                "structured": deepcopy(claim.get("structured")),
                "verdict": verdict,
                "evidence_id": item.get("evidence_id"),
                "supporting_quote": (
                    canonical_evidence.get("source_text")
                    if canonical_evidence is not None else item.get("supporting_quote")
                ),
                "supporting_quote_source": (
                    "canonical_evidence_record" if canonical_evidence is not None else "verifier_response"
                ),
                "reasoning": reason or "No verifier reasoning supplied.",
            })
        return finalized

    @staticmethod
    def _subject_hash(graph: Mapping[str, Any]) -> str:
        subject = deepcopy(dict(graph))
        metadata = subject.get("metadata")
        if isinstance(metadata, dict):
            metadata.pop("grounding_certification", None)
        return _stable_hash(subject)

    def verify_graph(
        self,
        graph: Mapping[str, Any],
        organized_dir: Path,
        output_dir: Path,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        working = deepcopy(dict(graph))
        corpus = source_document_index(str(organized_dir))
        rules = [dict(rule) for rule in working.get("business_rules", []) if isinstance(rule, Mapping)]
        workers = max(1, int(os.getenv("KG_GROUNDING_WORKERS", "40")))
        max_rules = max(1, int(os.getenv("KG_GROUNDING_RULES_PER_REQUEST", "4")))
        max_claims = max(1, int(os.getenv("KG_GROUNDING_CLAIMS_PER_REQUEST", "48")))
        max_chars = max(4000, int(os.getenv("KG_GROUNDING_EVIDENCE_CHARS_PER_RULE", "8000")))
        max_batch_chars = max(20000, int(os.getenv("KG_GROUNDING_MAX_BATCH_CHARS", "80000")))
        max_relationships = max(1, int(os.getenv("KG_GROUNDING_RELATIONSHIPS_PER_REQUEST", "12")))
        working["business_rules"] = rules
        rule_packets = [self.build_packet(rule, corpus, max_chars) for rule in rules]
        relationship_packets, deterministic_relationships = self.build_relationship_packets(
            working, corpus, max_chars
        )
        packets = rule_packets + relationship_packets
        batches = self.make_batches(rule_packets, max_rules, max_claims, max_batch_chars)
        batches.extend(self.make_batches(relationship_packets, max_relationships, max_claims, max_batch_chars))
        checkpoint = JsonlCheckpoint(output_dir / "agent_09_grounding_checkpoint.jsonl")
        raw_by_rule: dict[str, list[dict[str, Any]]] = {}
        unexpected_responses: list[dict[str, Any]] = []

        def verify_batch(batch: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
            key = "grounding:" + _stable_hash({
                "checkpoint_version": self.CHECKPOINT_VERSION,
                "model": getattr(self.resolver, "model", None),
                "reasoning": getattr(self.resolver, "reasoning_effort", None),
                "corpus_sha256": corpus.get("corpus_sha256"),
                "batch": batch,
            })
            cached = checkpoint.get(key)
            if isinstance(cached, list):
                print(f"↪ agent_09 checkpoint hit ({len(batch)} rules)", flush=True)
                return batch, cached
            result = self.resolver.verify(batch) if self.resolver is not None else []
            checkpoint.put(key, result)
            return batch, result

        print(
            f"▶ agent_09 grounding: {len(rules)} rules, {sum(len(p['claims']) for p in packets)} model claims, "
            f"{len(deterministic_relationships)} deterministic relationship checks, "
            f"{len(batches)} batches, {workers} workers",
            flush=True,
        )
        api_workers = max(1, int(os.getenv("KG_GROUNDING_LLM_CONCURRENCY", "32")))
        workers = min(workers, api_workers)
        with ThreadPoolExecutor(max_workers=min(workers, max(1, len(batches))), thread_name_prefix="kg-grounding") as executor:
            futures = [executor.submit(verify_batch, batch) for batch in batches]
            for future in as_completed(futures):
                batch, results = future.result()
                batch_pairs = {
                    (str(packet["rule_id"]), str(claim["claim_id"]))
                    for packet in batch for claim in packet.get("claims", [])
                }
                unexpected_responses.extend(
                    {"rule_id": item.get("rule_id"), "claim_id": item.get("claim_id")}
                    for item in results
                    if (str(item.get("rule_id")), str(item.get("claim_id"))) not in batch_pairs
                )
                for packet in batch:
                    rule_id = str(packet["rule_id"])
                    raw_by_rule.setdefault(rule_id, []).extend(
                        dict(item)
                        for item in results
                        if str(item.get("rule_id")) == rule_id
                        and str(item.get("claim_id")) in {
                            str(claim.get("claim_id")) for claim in packet.get("claims", [])
                        }
                    )

        packet_by_id = {str(packet["rule_id"]): packet for packet in packets}
        duplicate_responses = 0
        missing_responses = 0
        returned_responses = 0
        finalized_by_id: dict[str, list[dict[str, Any]]] = {}
        protocol_by_id: dict[str, dict[str, int]] = {}
        for subject_id, packet in packet_by_id.items():
            raw_results = raw_by_rule.get(subject_id, [])
            expected_ids = {str(item["claim_id"]) for item in packet["claims"]}
            returned_ids = [str(item.get("claim_id")) for item in raw_results if str(item.get("claim_id")) in expected_ids]
            returned_unique = set(returned_ids)
            duplicates = len(returned_ids) - len(returned_unique)
            missing = len(expected_ids - returned_unique)
            duplicate_responses += duplicates
            missing_responses += missing
            returned_responses += len(returned_unique)
            finalized_by_id[subject_id] = self._finalize_rule_results(packet, raw_results)
            protocol_by_id[subject_id] = {"returned": len(returned_unique), "missing": missing, "duplicates": duplicates}

        relationship_failures: list[dict[str, Any]] = []
        relationship_failures_by_rule: dict[str, list[str]] = {}
        relationship_results: list[dict[str, Any]] = []
        relationship_invalid_evidence = 0
        for packet in relationship_packets:
            subject_id = str(packet["rule_id"])
            results = finalized_by_id[subject_id]
            protocol = protocol_by_id[subject_id]
            invalid_records = sum(item.get("source_text_found_in_chunk") is not True for item in packet["evidence"])
            relationship_invalid_evidence += invalid_records
            supported_relationship = (
                bool(results)
                and all(item["verdict"] == "supported" for item in results)
                and protocol["missing"] == 0
                and protocol["duplicates"] == 0
            )
            result = {
                "relationship_id": subject_id,
                "field_path": results[0].get("field_path") if results else None,
                "status": "supported" if supported_relationship else "failed",
                "invalid_evidence_records": invalid_records,
                "claims": results,
            }
            relationship_results.append(result)
            if not supported_relationship:
                affected = list((packet["claims"][0].get("structured") or {}).get("affected_rule_ids", []))
                failure = {**result, "affected_rule_ids": affected}
                relationship_failures.append(failure)
                for affected_rule_id in affected:
                    relationship_failures_by_rule.setdefault(str(affected_rule_id), []).append(subject_id)

        failures = []
        rule_results: list[dict[str, Any]] = []
        deterministic_rule_results: list[dict[str, Any]] = []
        entity_keys = (working.get("entity_types") or {}).keys() if isinstance(working.get("entity_types"), Mapping) else []
        for rule in rules:
            rule_id = str(rule.get("rule_id"))
            packet = packet_by_id[rule_id]
            results = finalized_by_id[rule_id]
            deterministic_results = self.deterministic_rule_claims(rule, entity_keys)
            protocol = protocol_by_id[rule_id]
            combined_results = results + deterministic_results
            counts = {verdict: sum(item["verdict"] == verdict for item in combined_results) for verdict in VERDICTS}
            authentic_records = sum(item.get("source_text_found_in_chunk") is True for item in packet["evidence"])
            invalid_records = len(packet["evidence"]) - authentic_records
            repaired_records = sum(item.get("source_text_repaired") is True for item in packet["evidence"])
            failed_relationship_ids = relationship_failures_by_rule.get(rule_id, [])
            dimensions = {
                dimension: self._dimension_summary(combined_results, dimension)
                for dimension in GROUNDING_DIMENSIONS
            }
            certified = (
                bool(combined_results)
                and counts["contradicted"] == 0
                and counts["insufficient_evidence"] == 0
                and protocol["missing"] == 0
                and protocol["duplicates"] == 0
            )
            rule["grounding"] = {
                "status": "certified" if certified else "failed",
                "corpus_sha256": corpus.get("corpus_sha256"),
                "claim_count": len(combined_results),
                "model_claim_count": len(results),
                "deterministic_claim_count": len(deterministic_results),
                "counts": counts,
                "evidence_records": len(packet["evidence"]),
                "invalid_evidence_records": invalid_records,
                "repaired_evidence_records": repaired_records,
                "response_claims_returned": protocol["returned"],
                "missing_claim_responses": protocol["missing"],
                "duplicate_claim_responses": protocol["duplicates"],
                "failed_relationship_ids": failed_relationship_ids,
                "relationship_status": "failed" if failed_relationship_ids else "supported",
                "dimensions": dimensions,
                "claims": results,
                "deterministic_claims": deterministic_results,
            }
            prior_failures = [
                dict(item) for item in (rule.get("readiness") or {}).get("failed_requirements", [])
                if isinstance(item, Mapping) and item.get("requirement") != "grounding"
            ]
            if not certified:
                grounding_failure = {
                    "requirement": "grounding",
                    "reason": (
                        f"{counts['contradicted']} contradicted and {counts['insufficient_evidence']} insufficient claims; "
                        f"{invalid_records} evidence quotes not found in the cited corpus; "
                        f"{protocol['missing']} missing and {protocol['duplicates']} duplicate verifier responses"
                    ),
                }
                prior_failures.append(grounding_failure)
                failures.append({
                    "rule_id": rule_id,
                    **grounding_failure,
                    "claims": [item for item in combined_results if item["verdict"] != "supported"],
                })
            reviewed = mark_readiness(rule, prior_failures)
            rule.clear()
            rule.update(reviewed)
            rule_results.extend(results)
            deterministic_rule_results.extend(deterministic_results)

        working["business_rules"] = rules
        model_results = rule_results + [item for result in relationship_results for item in result["claims"]]
        deterministic_results = deterministic_rule_results + [
            {**item, "verdict": item.get("status")} for item in deterministic_relationships
        ]
        total_claims = len(model_results) + len(deterministic_results)
        supported = sum(item["verdict"] == "supported" for item in model_results + deterministic_results)
        contradicted = sum(item["verdict"] == "contradicted" for item in model_results + deterministic_results)
        insufficient = sum(item["verdict"] == "insufficient_evidence" for item in model_results + deterministic_results)
        invalid_evidence = sum((rule.get("grounding") or {}).get("invalid_evidence_records", 0) for rule in rules)
        repaired_evidence = sum((rule.get("grounding") or {}).get("repaired_evidence_records", 0) for rule in rules)
        dimension_report = {}
        for dimension in GROUNDING_DIMENSIONS:
            statuses = Counter(
                (((rule.get("grounding") or {}).get("dimensions") or {}).get(dimension) or {}).get(
                    "status", "not_reported"
                )
                for rule in rules
            )
            dimension_claims = Counter()
            for rule in rules:
                summary = (((rule.get("grounding") or {}).get("dimensions") or {}).get(dimension) or {})
                dimension_claims.update({
                    key: int(value) for key, value in (summary.get("counts") or {}).items()
                })
            dimension_report[dimension] = {
                "rule_status_counts": dict(statuses),
                "certified_rules": statuses.get("certified", 0),
                "failed_rules": statuses.get("failed", 0),
                "not_applicable_rules": statuses.get("not_applicable", 0),
                "hold_rate": round(statuses.get("failed", 0) / max(1, len(rules)) * 100, 2),
                "claim_counts": dict(dimension_claims),
            }
        relationship_dimension = {
            "supported_rules": sum(
                (rule.get("grounding") or {}).get("relationship_status") == "supported"
                for rule in rules
            ),
            "failed_rules": sum(
                (rule.get("grounding") or {}).get("relationship_status") == "failed"
                for rule in rules
            ),
        }
        relationship_dimension["hold_rate"] = round(
            relationship_dimension["failed_rules"] / max(1, len(rules)) * 100, 2
        )
        passed = (
            not failures
            and not relationship_failures
            and total_claims > 0
            and supported == total_claims
            and invalid_evidence == 0
            and not unexpected_responses
            and missing_responses == 0
            and duplicate_responses == 0
        )
        certification = {
            "pass": passed,
            "verifier_model": getattr(self.resolver, "model", None),
            "reasoning_effort": getattr(self.resolver, "reasoning_effort", None),
            "corpus_sha256": corpus.get("corpus_sha256"),
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        working.setdefault("metadata", {})["grounding_certification"] = certification
        certification["certified_graph_sha256"] = self._subject_hash(working)
        report = {
            **certification,
            "total_rules": len(rules),
            "rules_certified": len(rules) - len(failures),
            "rules_failed": len(failures),
            # Keep the strict quality-hold count separate from the operational
            # human queue.  A rule with evidence gaps remains fail-closed and
            # review-required, but only a positive contradiction (or an
            # explicit human finding) should consume scarce human-review
            # capacity.
            "rules_requiring_review": sum(bool(rule.get("requires_review")) for rule in rules),
            "review_required_rate": round(
                sum(bool(rule.get("requires_review")) for rule in rules) / max(1, len(rules)) * 100, 2
            ),
            "human_review_required_rules": sum(
                bool((rule.get("review_route") or {}).get("human_review_required"))
                for rule in rules
            ),
            "human_review_rate": round(
                sum(bool((rule.get("review_route") or {}).get("human_review_required")) for rule in rules)
                / max(1, len(rules)) * 100,
                2,
            ),
            "review_route_counts": dict(Counter(
                (rule.get("review_route") or {}).get("route", "none") for rule in rules
            )),
            "rule_grounding_pass": not failures,
            "relationship_grounding_pass": not relationship_failures,
            "grounding_dimensions": {
                **dimension_report,
                "relationship": relationship_dimension,
            },
            "total_claims": total_claims,
            "model_claims": len(model_results),
            "deterministic_claims": len(deterministic_results),
            "rule_claims": len(rule_results) + len(deterministic_rule_results),
            "relationship_claims": len(relationship_results) + len(deterministic_relationships),
            "supported_claims": supported,
            "contradicted_claims": contradicted,
            "insufficient_evidence_claims": insufficient,
            "invalid_evidence_records": invalid_evidence,
            "repaired_evidence_records": repaired_evidence,
            "response_claims_returned": returned_responses,
            "missing_claim_responses": missing_responses,
            "duplicate_claim_responses": duplicate_responses,
            "unexpected_claim_responses": len(unexpected_responses),
            "unexpected_responses": unexpected_responses,
            "claim_coverage_percent": round((returned_responses / max(1, len(model_results))) * 100, 2),
            "failures": failures,
            "relationship_verification": {
                "total_relationships": len(deterministic_relationships) + len(relationship_packets),
                "deterministically_supported": len(deterministic_relationships),
                "model_verified": len(relationship_packets),
                "model_failures": len(relationship_failures),
                "repeated_invalid_evidence_records": relationship_invalid_evidence,
                "deterministic_checks": deterministic_relationships,
                "model_results": relationship_results,
                "failures": relationship_failures,
            },
            "checkpoint_file": str(checkpoint.path),
        }
        return working, report

    @staticmethod
    def report_markdown(report: Mapping[str, Any]) -> str:
        lines = [
            "# Knowledge Graph Grounding Certification", "",
            f"- Overall: {'PASS' if report.get('pass') else 'FAIL'}",
            f"- Independent rule grounding: {'PASS' if report.get('rule_grounding_pass') else 'FAIL'}",
            f"- Rules independently certified: {report.get('rules_certified')} / {report.get('total_rules')}",
            f"- Quality-hold rules (fail-closed): {report.get('rules_requiring_review')} / {report.get('total_rules')} "
            f"({report.get('review_required_rate')}%)",
            f"- Human-review queue: {report.get('human_review_required_rules')} / {report.get('total_rules')} "
            f"({report.get('human_review_rate')}%)",
            f"- Review routes: {report.get('review_route_counts')}",
            f"- Dimensional grounding: {report.get('grounding_dimensions')}",
            f"- Relationship grounding: {'PASS' if report.get('relationship_grounding_pass') else 'FAIL'}",
            f"- Claims supported: {report.get('supported_claims')} / {report.get('total_claims')}",
            f"- Contradicted claims: {report.get('contradicted_claims')}",
            f"- Insufficient-evidence claims: {report.get('insufficient_evidence_claims')}",
            f"- Invalid evidence records: {report.get('invalid_evidence_records')}",
            f"- Repaired evidence records (near-match, corrected to real corpus text): {report.get('repaired_evidence_records')}", "",
            f"- Verifier response coverage: {report.get('response_claims_returned')} / {report.get('model_claims')} "
            f"({report.get('claim_coverage_percent')}%)",
            f"- Missing / duplicate / unexpected responses: {report.get('missing_claim_responses')} / "
            f"{report.get('duplicate_claim_responses')} / {report.get('unexpected_claim_responses')}", "",
            f"- Graph relationships checked: {(report.get('relationship_verification') or {}).get('total_relationships')}",
            f"- Deterministic / model relationship checks: "
            f"{(report.get('relationship_verification') or {}).get('deterministically_supported')} / "
            f"{(report.get('relationship_verification') or {}).get('model_verified')}",
            f"- Relationship failures: {(report.get('relationship_verification') or {}).get('model_failures')}", "",
        ]
        if report.get("failures"):
            lines.extend(["## Failed Rules", ""])
            for failure in report["failures"]:
                lines.append(f"- `{failure.get('rule_id')}` — {failure.get('reason')}")
        return "\n".join(lines) + "\n"

    def run(self, graph_path: Path, organized_dir: Path, output_dir: Path) -> dict[str, Any]:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        final_graph, report = self.verify_graph(graph, organized_dir, output_dir)
        _write_text_atomic(graph_path, json.dumps(final_graph, indent=2, ensure_ascii=False) + "\n")
        _write_text_atomic(
            output_dir / "kg_grounding_report.json",
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        )
        _write_text_atomic(output_dir / "kg_grounding_report.md", self.report_markdown(report))
        print(
            f"{'✅' if report['pass'] else '❌'} agent_09 completed: "
            f"{report['rules_certified']}/{report['total_rules']} rules and "
            f"{report['supported_claims']}/{report['total_claims']} claims certified",
            flush=True,
        )
        return report


def certification_issues(
    graph: Mapping[str, Any],
    report: Mapping[str, Any],
    corpus_sha256: str,
) -> list[str]:
    """Return deterministic reasons an agent_09 certificate is not reusable."""
    issues: list[str] = []
    metadata = graph.get("metadata")
    certificate = metadata.get("grounding_certification") if isinstance(metadata, Mapping) else None
    if report.get("pass") is not True:
        issues.append("grounding report does not pass")
    if not isinstance(certificate, Mapping) or certificate.get("pass") is not True:
        issues.append("graph metadata does not contain a passing grounding certificate")
        certificate = {}
    if not str(report.get("verifier_model") or "").strip():
        issues.append("grounding report does not identify the verifier model")
    if report.get("corpus_sha256") != corpus_sha256 or certificate.get("corpus_sha256") != corpus_sha256:
        issues.append("source corpus has changed since grounding verification")
    expected_hash = GroundingVerifier._subject_hash(graph)
    report_hash = report.get("certified_graph_sha256")
    certificate_hash = certificate.get("certified_graph_sha256")
    if report_hash != expected_hash or certificate_hash != expected_hash:
        issues.append("optimized graph has changed since grounding verification")
    rules = [rule for rule in graph.get("business_rules", []) if isinstance(rule, Mapping)]
    failed_rules = []
    for rule in rules:
        grounding = rule.get("grounding")
        if not isinstance(grounding, Mapping) or grounding.get("status") != "certified":
            failed_rules.append(str(rule.get("rule_id", "")))
    if failed_rules:
        issues.append(f"{len(failed_rules)} rules do not have certified claim-level grounding")
    if report.get("total_rules") != len(rules) or report.get("rules_certified") != len(rules):
        issues.append("grounding report rule totals do not match the optimized graph")
    if report.get("claim_coverage_percent") != 100.0:
        issues.append("verifier response coverage is below 100 percent")
    if isinstance(certificate, Mapping):
        for field in ("pass", "verifier_model", "reasoning_effort", "corpus_sha256", "certified_graph_sha256"):
            if certificate.get(field) != report.get(field):
                issues.append(f"graph certificate and grounding report disagree on {field}")
    per_rule_claim_counts = [
        rule["grounding"].get("claim_count")
        for rule in rules
        if isinstance(rule.get("grounding"), Mapping)
    ]
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in per_rule_claim_counts):
        issues.append("one or more rules have an invalid grounding claim count")
    claim_count = sum(value for value in per_rule_claim_counts if isinstance(value, int) and not isinstance(value, bool))
    if report.get("rule_claims") != claim_count:
        issues.append("grounding report claim totals do not match the optimized graph")
    relationship_report = report.get("relationship_verification")
    if not isinstance(relationship_report, Mapping) or relationship_report.get("model_failures") != 0:
        issues.append("one or more graph relationships failed independent verification")
    for field in (
        "contradicted_claims",
        "insufficient_evidence_claims",
        "invalid_evidence_records",
        "missing_claim_responses",
        "duplicate_claim_responses",
        "unexpected_claim_responses",
    ):
        if report.get(field) != 0:
            issues.append(f"grounding report has nonzero {field}")
    return issues


def main() -> None:
    config = get_config()
    resolver = OpenAIGroundingResolver(
        config.get_api_key(), config.get_optimizer_model_name(), config.get_reasoning_effort()
    )
    output_dir = config.get_optimized_dir()
    report = GroundingVerifier(resolver).run(
        output_dir / "optimized_compliance_knowledge_graph.json",
        config.get_organized_dir(),
        output_dir,
    )
    if not report["pass"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
