#!/usr/bin/env python3
"""agent_08: focused, checkpointed remediation of readiness failures only."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
from itertools import combinations
import json
import os
from pathlib import Path
import sys
import threading
from typing import Any, Iterable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.agent_07_executable_readiness import (
    ExecutableReadinessCompleter,
    OpenAIEvidenceResolver,
    required_inputs,
    _build_token_index,
    _compact_readiness_rule,
    _normalise_rule_contract,
    _project_execution,
    _report_markdown,
)
from utils.config import get_config
from utils.rule_dependencies import prune_dangling_related_rules, revalidate_graph
from utils.rule_gating import make_entailment_oracle
from utils.kg_readiness import source_document_index
from utils.llm_client import create_llm_client
from utils.prompt_manager import get_prompt_manager
from utils.rule_contract import validate_rule_v2


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _chunks(values: list[Any], size: int) -> Iterable[list[Any]]:
    for start in range(0, len(values), max(1, size)):
        yield values[start:start + max(1, size)]


def _source_reference_section_id(rule: Mapping[str, Any]) -> str:
    """Return a deterministic section key for either source-reference shape.

    ``agent_03`` accepts one source-reference object or a list of objects when
    a rule's evidence spans multiple excerpts. Remediation batching only needs
    a stable sort key, so list-shaped evidence uses its first non-empty section
    identifier instead of assuming the object form.
    """

    reference = rule.get("source_reference")
    if isinstance(reference, Mapping):
        return str(reference.get("section_id", ""))
    if isinstance(reference, list):
        section_ids = sorted(
            str(item.get("section_id", ""))
            for item in reference
            if isinstance(item, Mapping) and str(item.get("section_id", ""))
        )
        return section_ids[0] if section_ids else ""
    return ""


class JsonlCheckpoint:
    """Append-only result cache keyed by immutable prompt inputs."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._items: dict[str, Any] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, Mapping) and item.get("key"):
                    self._items[str(item["key"])] = item.get("result")

    def get(self, key: str) -> Any:
        return deepcopy(self._items.get(key))

    def put(self, key: str, result: Any) -> None:
        row = json.dumps({"key": key, "result": result}, ensure_ascii=False)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(row + "\n")
            self._items[key] = deepcopy(result)


class OpenAIRemediationResolver:
    def __init__(self, api_key: str, model: str, reasoning_effort: str) -> None:
        concurrency = max(1, int(os.getenv("KG_REMEDIATION_LLM_CONCURRENCY", "32")))
        self.concurrency = concurrency
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
            # JSON mode can still yield a single malformed delimiter on long
            # high-reasoning responses. Repair only that object in strict mode;
            # concatenated values and non-objects remain rejected.
            try:
                from json_repair import repair_json

                value = repair_json(content, return_objects=True, strict=True)
            except Exception:
                raise original_error
        if not isinstance(value, dict):
            raise ValueError("agent_08 response must be a JSON object")
        return value

    def complete(self, prompt_name: str, field: str, payload: Any, max_tokens: int) -> list[dict[str, Any]]:
        prompt = self.prompts.format_prompt(prompt_name, **payload)
        attempts = max(1, int(os.getenv("KG_REMEDIATION_PARSE_ATTEMPTS", "3")))
        error: Exception | None = None
        for attempt in range(1, attempts + 1):
            response = self.client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                reasoning_effort=self.reasoning_effort,
            )
            try:
                result = self._parse(response.choices[0].message.content or "")
                items = result.get(field)
                if not isinstance(items, list):
                    raise ValueError(f"agent_08 response lacks list field {field!r}")
                return [dict(item) for item in items if isinstance(item, Mapping)]
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                error = exc
                prompt += "\n\nReturn a complete valid JSON object only. Include every requested item exactly once."
                print(f"⚠️ agent_08 JSON retry {attempt}/{attempts}: {exc}", flush=True)
        assert error is not None
        raise error


class ReadinessRemediator:
    """Repair evidence-limited rules and unresolved conflict pairs, then revalidate."""

    RULE_FIELDS = (
        "exceptions", "exception_basis", "exception_verification",
        "applicability_scope", "scope_basis", "scope_derivation",
    )
    # v4 understands contract findings emitted as ``code`` and the expanded
    # rule contract; v3 responses must be regenerated under this protocol.
    CHECKPOINT_VERSION = 4

    @staticmethod
    def _unresolved_conflict_fallback(batch: list[dict[str, Any]], error: Exception) -> list[dict[str, Any]]:
        """Convert a failed provider response into explicit review items."""
        return [
            {
                "entity": candidate.get("entity", ""),
                "rule_ids": candidate.get("rule_ids", []),
                "status": "unresolved",
                "reasoning": f"Conflict remediation failed: {error}",
                "resolution": "Manual review required.",
            }
            for candidate in batch
        ]

    def __init__(self, resolver: OpenAIRemediationResolver | None) -> None:
        self.resolver = resolver

    @staticmethod
    def _failed_requirements(rule: Mapping[str, Any]) -> set[str]:
        routed: set[str] = set()
        for item in (rule.get("readiness") or {}).get("failed_requirements", []):
            if not isinstance(item, Mapping):
                continue
            requirement = str(item.get("requirement", "")).strip()
            code = str(item.get("code", "")).strip()
            if requirement:
                routed.add(requirement)
            if code:
                routed.add(f"code:{code}")
                # Contract validators use ``code`` rather than ``requirement``.
                # Route the source-sensitive families to the same repair path
                # as their final-readiness counterparts instead of silently
                # omitting them from every Agent 08 request.
                if "exception" in code:
                    routed.add("exceptions")
                elif "scope" in code:
                    routed.add("scope")
                else:
                    routed.add("contract")
        return routed

    @staticmethod
    def _apply_rule_patch(rule: dict[str, Any], patch: Mapping[str, Any], corpus: Mapping[str, Any]) -> dict[str, Any]:
        existing = {str(item.get("name", "")).lower() for item in rule.get("variables", []) if isinstance(item, Mapping)}
        for variable in patch.get("variables_to_add", []) or []:
            if not isinstance(variable, Mapping) or not str(variable.get("name", "")).strip():
                continue
            item = dict(variable)
            name = str(item["name"]).strip()
            if name.lower() in existing:
                continue
            item["name"] = name
            item["role"] = "input"
            if item.get("type") == "string":
                item["free_text"] = True
            if item.get("type") == "enum" and not item.get("allowed_values"):
                continue
            rule.setdefault("variables", []).append(item)
            existing.add(name.lower())
        for field in ReadinessRemediator.RULE_FIELDS:
            if field in patch:
                rule[field] = deepcopy(patch[field])
        verification = rule.get("exception_verification")
        if isinstance(verification, dict):
            verification["searched_chunk_count"] = int(corpus.get("chunk_count", 0))
            verification["corpus_sha256"] = corpus.get("corpus_sha256")
            verification.setdefault("searched_document_ids", ["organized_corpus"])
        derivation = rule.get("scope_derivation")
        if isinstance(derivation, dict):
            derivation["reviewed_chunk_count"] = int(corpus.get("chunk_count", 0))
            derivation["corpus_sha256"] = corpus.get("corpus_sha256")
        rule = _normalise_rule_contract(rule)
        rule["execution"] = _project_execution(rule)
        return rule

    def _rule_batches(
        self,
        rules: list[dict[str, Any]],
        corpus: Mapping[str, Any],
        batch_size: int,
    ) -> list[list[dict[str, Any]]]:
        completer = ExecutableReadinessCompleter()
        packets = []
        for rule in rules:
            failures = self._failed_requirements(rule)
            if failures.isdisjoint({"exceptions", "scope"}):
                continue
            packets.append({
                # Do not resend full extraction/grounding payloads.  Remediation
                # may patch only readiness fields, while the compact projection
                # keeps prompts bounded and preserves the original graph in the
                # stage output.
                "rule": _compact_readiness_rule(rule),
                "failed_requirements": sorted(failures),
                "failed_findings": [
                    dict(item)
                    for item in (rule.get("readiness") or {}).get("failed_requirements", [])
                    if isinstance(item, Mapping)
                ],
                "evidence_packet": completer._evidence_packet(rule, corpus),
            })
        packets.sort(key=lambda item: (
            _source_reference_section_id(item["rule"]),
            str(item["rule"].get("rule_id", "")),
        ))
        return list(_chunks(packets, batch_size))

    @staticmethod
    def _conflict_candidates(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
        # Dependency analysis can contain very large unresolved groups (for
        # example, hundreds of rules sharing one output variable).  Expanding
        # every group into a Cartesian product is both unbounded and redundant
        # because the model can only remediate a bounded request set.  Keep a
        # deterministic prefix and leave the remainder fail-closed for review.
        max_candidates = max(1, int(os.getenv("KG_REMEDIATION_MAX_CONFLICT_PAIRS", "5000")))
        rules = {str(rule.get("rule_id")): rule for rule in graph.get("business_rules", []) if isinstance(rule, Mapping)}
        unique: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
        conflicts = (graph.get("dependency_details") or {}).get("conflicts", [])
        for index, entry in enumerate(conflicts or []):
            if not isinstance(entry, Mapping):
                continue
            status = entry.get("status")
            if status != "unresolved" and not (status == "conflict" and not str(entry.get("resolution", "")).strip()):
                continue
            ids = tuple(sorted({str(value) for value in entry.get("rule_ids", []) if str(value) in rules}))
            if len(ids) < 2:
                continue
            entity = str(entry.get("entity", ""))
            for pair in combinations(ids, 2):
                key = (entity, pair)
                unique[key] = {
                    "entity": entity,
                    "rule_ids": list(pair),
                    "original_indexes": [index],
                    "rules": [{
                        field: rules[rule_id].get(field)
                        for field in (
                            "rule_id", "description", "condition_predicates", "condition_logic", "outcomes",
                            "applicability_scope", "exceptions", "recommended_hit_policy",
                            "source_reference",
                        )
                    } for rule_id in pair],
                }
                if len(unique) >= max_candidates:
                    return [unique[key] for key in sorted(unique)]
        return [unique[key] for key in sorted(unique)]

    @staticmethod
    def _normalise_multi_value_outputs(
        rules: list[dict[str, Any]],
        variable_names: set[str] | None = None,
    ) -> set[str]:
        """Enforce one graph-wide type for evidence-confirmed collected outputs.

        A DMN output variable cannot be scalar in one rule and a collection in
        another. Existing list declarations are authoritative evidence that the
        shared variable is multi-valued; remediation patches can add more names.
        """
        names = set(variable_names or ())
        for rule in rules:
            for outcome in rule.get("outcomes", []) or []:
                if isinstance(outcome, Mapping) and (
                    outcome.get("value_type") == "list" or isinstance(outcome.get("value"), list)
                ):
                    names.add(str(outcome.get("variable", "")))
        names.discard("")
        for rule in rules:
            touched = False
            for variable in rule.get("variables", []) or []:
                if isinstance(variable, dict) and str(variable.get("name")) in names:
                    variable["type"] = "list"
                    variable.pop("free_text", None)
                    variable.pop("allowed_values", None)
                    touched = True
            for outcome in rule.get("outcomes", []) or []:
                if not isinstance(outcome, dict) or str(outcome.get("variable")) not in names:
                    continue
                if not isinstance(outcome.get("value"), list):
                    outcome["value"] = [str(outcome.get("value"))]
                outcome["value_type"] = "list"
                touched = True
            for vector in rule.get("test_vectors", []) or []:
                expected = vector.get("expected_output") if isinstance(vector, Mapping) else None
                if not isinstance(expected, dict):
                    continue
                for name in names:
                    if name in expected and not isinstance(expected[name], list):
                        expected[name] = [str(expected[name])]
                        touched = True
            if touched:
                rule["recommended_hit_policy"] = "COLLECT"
                _normalise_rule_contract(rule)
                rule["execution"] = _project_execution(rule)
        return names

    @staticmethod
    def _resolve_collected_output_conflicts(
        conflicts: list[dict[str, Any]],
        rules_by_id: Mapping[str, dict[str, Any]],
        multi_value_names: set[str],
    ) -> None:
        """Resolve a collision when every shared output is a typed collection."""
        for entry in conflicts:
            if entry.get("status") not in {"conflict", "unresolved"}:
                continue
            involved = [rules_by_id.get(str(rule_id)) for rule_id in entry.get("rule_ids", [])]
            if len(involved) != 2 or any(rule is None for rule in involved):
                continue
            left, right = involved
            left_names = {str(item.get("variable")) for item in left.get("outcomes", []) if isinstance(item, Mapping)}
            right_names = {str(item.get("variable")) for item in right.get("outcomes", []) if isinstance(item, Mapping)}
            shared = left_names & right_names
            if not shared or not shared.issubset(multi_value_names):
                continue
            if any(rule.get("recommended_hit_policy") != "COLLECT" for rule in involved):
                continue
            entry["status"] = "non_conflict"
            entry["reasoning"] = (
                f"The rules may co-fire, but their shared outputs {sorted(shared)} are "
                "graph-wide typed collections and both rules use COLLECT. Distinct values "
                "are accumulated rather than assigned to one scalar slot."
            )
            entry["resolution"] = (
                "Apply the graph-wide list contract and COLLECT all applicable values for "
                + ", ".join(sorted(shared)) + "."
            )

    def remediate(
        self,
        baseline: Mapping[str, Any],
        graph: Mapping[str, Any],
        organized_dir: Path,
        output_dir: Path,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        # The optimized graph can contain hundreds of megabytes of evidence
        # payloads.  A full deepcopy here needlessly blocks the stage before
        # its first request.  Only the rule/conflict structures are mutated;
        # retain immutable evidence arrays by reference.
        working = dict(graph)
        working["business_rules"] = [
            # Rule payloads already belong exclusively to this stage's loaded
            # graph; a shallow record copy avoids duplicating large evidence
            # arrays while still isolating top-level field assignments.
            dict(rule) for rule in graph.get("business_rules", []) if isinstance(rule, Mapping)
        ]
        dependency_details = dict(graph.get("dependency_details") or {})
        dependency_details["conflicts"] = [
            deepcopy(entry) for entry in dependency_details.get("conflicts", []) if isinstance(entry, Mapping)
        ]
        working["dependency_details"] = dependency_details
        corpus = source_document_index(str(organized_dir))
        # Reuse the same normalized retrieval index as Agent 07.  Without it,
        # each review rule repeatedly lowercases and scans every chunk before
        # remediation requests are submitted, making large corpora CPU-bound.
        corpus["_search_index"] = [
            (chunk, str(chunk.get("text", "")).lower(), str(chunk.get("chunk_path", "")).lower())
            for chunk in corpus.get("chunks", [])
            if isinstance(chunk, Mapping)
        ]
        corpus["_token_index"] = _build_token_index(corpus["_search_index"])
        rules = [dict(rule) for rule in working.get("business_rules", []) if isinstance(rule, Mapping)]
        initial_review = sum(bool(rule.get("requires_review")) for rule in rules)
        workers = max(1, int(os.getenv("KG_REMEDIATION_WORKERS", "40")))
        rule_batch_size = max(1, int(os.getenv("KG_REMEDIATION_RULES_PER_REQUEST", "4")))
        pair_batch_size = max(1, int(os.getenv("KG_REMEDIATION_PAIRS_PER_REQUEST", "12")))
        passes = max(1, int(os.getenv("KG_REMEDIATION_MAX_PASSES", "2")))
        checkpoint = JsonlCheckpoint(output_dir / "agent_08_checkpoint.jsonl")
        history = []

        for pass_number in range(1, passes + 1):
            review_ids = {str(rule.get("rule_id")) for rule in rules if rule.get("requires_review")}
            print(f"▶ agent_08 pass {pass_number}/{passes}: {len(review_ids)} review rules", flush=True)
            if not review_ids:
                break

            rule_batches = self._rule_batches([rule for rule in rules if str(rule.get("rule_id")) in review_ids], corpus, rule_batch_size)
            rule_results: dict[str, dict[str, Any]] = {}

            def resolve_rule_batch(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
                key = "rules:" + _stable_hash({
                    "model": getattr(self.resolver, "model", None),
                    "reasoning": getattr(self.resolver, "reasoning_effort", None),
                    "checkpoint_version": self.CHECKPOINT_VERSION,
                    "corpus": corpus.get("corpus_sha256"),
                    "batch": batch,
                })
                cached = checkpoint.get(key)
                if isinstance(cached, list):
                    print(f"↪ agent_08 rule checkpoint hit ({len(batch)} rules)", flush=True)
                    return cached
                if self.resolver is None:
                    return []
                result = self.resolver.complete(
                    "readiness_rule_remediation", "remediations",
                    {"remediation_json": json.dumps(batch, ensure_ascii=False)},
                    int(os.getenv("KG_REMEDIATION_RULE_MAX_TOKENS", "12000")),
                )
                checkpoint.put(key, result)
                return result

            api_workers = max(1, int(os.getenv("KG_REMEDIATION_LLM_CONCURRENCY", "32")))
            workers = min(workers, api_workers)
            with ThreadPoolExecutor(max_workers=min(workers, max(1, len(rule_batches))), thread_name_prefix="kg-remediate-rule") as executor:
                futures = [executor.submit(resolve_rule_batch, batch) for batch in rule_batches]
                for future in as_completed(futures):
                    for patch in future.result():
                        if patch.get("rule_id") in review_ids:
                            rule_results[str(patch["rule_id"])] = patch

            for index, rule in enumerate(rules):
                patch = rule_results.get(str(rule.get("rule_id")))
                if patch:
                    rules[index] = self._apply_rule_patch(rule, patch, corpus)
            working["business_rules"] = rules

            candidates = self._conflict_candidates(working)
            conflict_batches = list(_chunks(candidates, pair_batch_size))
            resolved_pairs: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}

            def resolve_conflict_batch(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
                key = "conflicts:" + _stable_hash({
                    "model": getattr(self.resolver, "model", None),
                    "reasoning": getattr(self.resolver, "reasoning_effort", None),
                    "checkpoint_version": self.CHECKPOINT_VERSION,
                    "batch": batch,
                })
                cached = checkpoint.get(key)
                if isinstance(cached, list):
                    print(f"↪ agent_08 conflict checkpoint hit ({len(batch)} pairs)", flush=True)
                    return cached
                if self.resolver is None:
                    return []
                result = self.resolver.complete(
                    "readiness_conflict_remediation", "analyses",
                    {"conflicts_json": json.dumps(batch, ensure_ascii=False)},
                    int(os.getenv("KG_REMEDIATION_CONFLICT_MAX_TOKENS", "12000")),
                )
                checkpoint.put(key, result)
                return result

            api_workers = max(1, int(os.getenv("KG_REMEDIATION_LLM_CONCURRENCY", "32")))
            workers = min(workers, api_workers)
            with ThreadPoolExecutor(max_workers=min(workers, max(1, len(conflict_batches))), thread_name_prefix="kg-remediate-conflict") as executor:
                futures = []
                for batch in conflict_batches:
                    future = executor.submit(resolve_conflict_batch, batch)
                    # Keep the input attached for fail-closed fallback handling
                    # if the provider raises before returning a result.
                    future._c2c_conflict_batch = batch
                    futures.append(future)
                for future in as_completed(futures):
                    try:
                        analyses = future.result()
                    except Exception as exc:
                        # A transient provider/network failure must not abort the
                        # complete remediation run. Preserve every affected pair
                        # as explicitly unresolved so the fail-closed report and
                        # a subsequent checkpointed rerun can address it.
                        batch = getattr(future, "_c2c_conflict_batch", [])
                        print(f"⚠️ conflict remediation batch failed; retaining review items: {exc}", flush=True)
                        analyses = self._unresolved_conflict_fallback(batch, exc)
                    for analysis in analyses:
                        ids = tuple(sorted({str(value) for value in analysis.get("rule_ids", [])}))
                        if len(ids) == 2:
                            resolved_pairs[(str(analysis.get("entity", "")), ids)] = analysis

            valid_policies = {"UNIQUE", "FIRST", "PRIORITY", "COLLECT", "ANY"}
            rule_by_id = {str(rule.get("rule_id")): rule for rule in rules}
            confirmed_multi_value_names = self._normalise_multi_value_outputs(rules)

            def apply_rule_patch(patch: Mapping[str, Any]) -> None:
                target = rule_by_id.get(str(patch.get("rule_id")))
                if target is None:
                    return
                for rename in patch.get("condition_variable_renames", []) or []:
                    if not isinstance(rename, Mapping):
                        continue
                    old, new = str(rename.get("from", "")).strip(), str(rename.get("to", "")).strip()
                    if not old or not new or old == new:
                        continue
                    for collection in ("variables", "condition_predicates", "exceptions"):
                        for item in target.get(collection, []) or []:
                            if isinstance(item, dict) and item.get("name" if collection == "variables" else "variable") == old:
                                item["name" if collection == "variables" else "variable"] = new
                    for vector in target.get("test_vectors", []) or []:
                        inputs = vector.get("inputs") if isinstance(vector, Mapping) else None
                        if isinstance(inputs, dict) and old in inputs and new not in inputs:
                            inputs[new] = inputs.pop(old)
                for update in patch.get("multi_value_outputs", []) or []:
                    if not isinstance(update, Mapping):
                        continue
                    variable_name = str(update.get("variable", ""))
                    if variable_name:
                        confirmed_multi_value_names.add(variable_name)
                    for variable in target.get("variables", []) or []:
                        if isinstance(variable, dict) and str(variable.get("name")) == variable_name:
                            variable["type"] = "list"
                            variable.pop("free_text", None)
                            variable.pop("allowed_values", None)
                    for outcome in target.get("outcomes", []) or []:
                        if isinstance(outcome, dict) and str(outcome.get("variable")) == variable_name:
                            if not isinstance(outcome.get("value"), list):
                                outcome["value"] = [str(outcome.get("value"))]
                            outcome["value_type"] = "list"
                    for vector in target.get("test_vectors", []) or []:
                        expected = vector.get("expected_output") if isinstance(vector, Mapping) else None
                        if isinstance(expected, dict) and variable_name in expected and not isinstance(expected[variable_name], list):
                            expected[variable_name] = [str(expected[variable_name])]
                    target["recommended_hit_policy"] = "COLLECT"
                _normalise_rule_contract(target)
                target["execution"] = _project_execution(target)

            conflict_entries = (working.get("dependency_details") or {}).get("conflicts", []) or []
            new_conflicts = []
            for entry in conflict_entries:
                if not isinstance(entry, Mapping):
                    continue
                ids = tuple(sorted({str(value) for value in entry.get("rule_ids", []) if str(value) in rule_by_id}))
                needs_replacement = entry.get("status") == "unresolved" or (
                    entry.get("status") == "conflict" and not str(entry.get("resolution", "")).strip()
                )
                selected_entries: list[dict[str, Any]] = []
                if needs_replacement and len(ids) >= 2:
                    for pair in combinations(ids, 2):
                        replacement = resolved_pairs.get((str(entry.get("entity", "")), pair))
                        if replacement is not None:
                            selected_entries.append(deepcopy(dict(replacement)))
                        else:
                            selected_entries.append({
                                "entity": str(entry.get("entity", "")),
                                "rule_ids": list(pair),
                                "status": "unresolved",
                                "reasoning": "agent_08 did not return this expanded group pair.",
                                "resolution": "",
                            })
                else:
                    selected_entries = [deepcopy(dict(entry))]
                for selected in selected_entries:
                    for patch in selected.pop("rule_patches", []) or []:
                        if isinstance(patch, Mapping):
                            apply_rule_patch(patch)
                    for update in selected.pop("hit_policy_updates", []) or []:
                        if not isinstance(update, Mapping):
                            continue
                        target = rule_by_id.get(str(update.get("rule_id")))
                        policy = update.get("recommended_hit_policy")
                        if target is not None and policy in valid_policies:
                            target["recommended_hit_policy"] = policy
                            target["execution"] = _project_execution(target)
                    new_conflicts.append(selected)
            deduplicated_conflicts: dict[str, dict[str, Any]] = {}
            for entry in new_conflicts:
                key = _stable_hash({
                    "entity": entry.get("entity"), "rule_ids": sorted(entry.get("rule_ids", [])),
                    "status": entry.get("status"), "reasoning": entry.get("reasoning"),
                    "resolution": entry.get("resolution"),
                })
                deduplicated_conflicts[key] = entry
            working.setdefault("dependency_details", {})["conflicts"] = list(deduplicated_conflicts.values())
            confirmed_multi_value_names = self._normalise_multi_value_outputs(
                rules, confirmed_multi_value_names
            )
            self._resolve_collected_output_conflicts(
                working["dependency_details"]["conflicts"], rule_by_id, confirmed_multi_value_names
            )

            # Re-run every deterministic gate while reusing the completed
            # evidence/conflict records. This is the only authority that can
            # remove requires_review after remediation.
            working, report = ExecutableReadinessCompleter().complete(
                baseline, working, str(organized_dir), skip_evidence=True, skip_conflicts=True
            )
            rules = [dict(rule) for rule in working.get("business_rules", []) if isinstance(rule, Mapping)]
            remaining = int(report["rules_requiring_review"])
            history.append({
                "pass": pass_number,
                "rules_entering": len(review_ids),
                "rule_batches": len(rule_batches),
                "conflict_pairs": len(candidates),
                "conflict_batches": len(conflict_batches),
                "rules_remaining": remaining,
            })
            print(f"✓ agent_08 pass {pass_number}: {len(review_ids) - remaining} newly ready; {remaining} remain", flush=True)
            if remaining == 0 or remaining >= len(review_ids):
                break

        final_graph, final_report = ExecutableReadinessCompleter().complete(
            baseline, working, str(organized_dir), skip_evidence=True, skip_conflicts=True
        )
        final_report["remediation"] = {
            "rules_initially_requiring_review": initial_review,
            "rules_made_ready": initial_review - final_report["rules_requiring_review"],
            "rules_remaining": final_report["rules_requiring_review"],
            "passes": history,
            "checkpoint_file": str(checkpoint.path),
        }
        return final_graph, final_report

    def run(self, baseline_path: Path, graph_path: Path, organized_dir: Path, output_dir: Path) -> dict[str, Any]:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        final_graph, report = self.remediate(baseline, graph, organized_dir, output_dir)
        # Remediation renames and retypes variables (a list-typed output becomes
        # an ``allowed_*_values`` form, for instance), so relations derived
        # earlier must be re-checked before this graph is written.
        try:
            entails, _gating_stats = make_entailment_oracle(final_graph, document_id="agent_08-revalidation")
        except Exception:
            entails = None
        revalidation = revalidate_graph(final_graph, stage="agent_08", entails=entails)
        if revalidation["dropped"]:
            print(f"⚠️  agent_08 dropped {len(revalidation['dropped'])} rule relationship(s) "
                  f"invalidated by remediation", flush=True)
        report["relation_revalidation"] = revalidation
        related_integrity = prune_dangling_related_rules(final_graph, stage="agent_08")
        if related_integrity["dropped"]:
            print(f"⚠️  agent_08 dropped {len(related_integrity['dropped'])} related_rules "
                  f"reference(s) naming rules that are not in the graph", flush=True)
        report["related_rules_integrity"] = related_integrity
        graph_path.write_text(json.dumps(final_graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (output_dir / "corpus_manifest.json").write_text(json.dumps(final_graph["corpus_manifest"], indent=2) + "\n", encoding="utf-8")
        (output_dir / "kg_readiness_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (output_dir / "kg_readiness_report.md").write_text(_report_markdown(report), encoding="utf-8")
        (output_dir / "agent_08_remediation_report.json").write_text(json.dumps(report["remediation"], indent=2) + "\n", encoding="utf-8")
        print(f"✅ agent_08 completed: {report['rules_ready']} ready, {report['rules_requiring_review']} require review", flush=True)
        return report


def main() -> None:
    config = get_config()
    # Same contract as agent_07: name the artifact that is missing instead of
    # dying on an unhandled FileNotFoundError deep inside the run.
    missing = [str(path) for path in required_inputs(config) if not path.exists()]
    if missing:
        print("ERROR: required upstream artifact(s) missing: " + ", ".join(missing), flush=True)
        print("   Run the pipeline through agent_07 first.", flush=True)
        raise SystemExit(2)
    resolver = OpenAIRemediationResolver(
        config.get_api_key(),
        config.get_optimizer_model_name(),
        config.get_reasoning_effort(),
    )
    output_dir = config.get_optimized_dir()
    report = ReadinessRemediator(resolver).run(
        config.get_rules_with_entities_dir() / "compliance_knowledge_graph.json",
        output_dir / "optimized_compliance_knowledge_graph.json",
        config.get_organized_dir(),
        output_dir,
    )
    if not all(item["pass"] for item in report["invariants"].values()):
        raise SystemExit(2)
    if report["rules_requiring_review"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
