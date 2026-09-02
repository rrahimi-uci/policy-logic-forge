"""
Compliance Knowledge Graph Optimizer Agent

This agent optimizes the extracted business rules by:
1. Deduplicating rationally identical rules (keeping minor variations)
2. Analyzing dependencies between rules
3. Creating optimized output with dependency graph and rationale

Uses OpenAI GPT-5 reasoning model for deep analysis.

Author: Reza Rahimi
Date: December 20, 2025
"""

import json
import sys
import os
import copy
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.prompt_manager import get_prompt_manager
from utils.llm_client import create_llm_client
from utils.config import get_config
from utils.rule_uniqueness import enforce_rule_uniqueness
from utils.rule_dependencies import Relation, build_fact_registry, derive_relations
from utils.rule_gating import gating_stats, make_entailment_oracle


_EXACT_LOGIC_FIELDS = (
    "schema_version", "rule_type", "condition_predicates", "condition_logic",
    "condition_basis", "outcomes", "variables", "applicability_scope",
    "scope_basis", "responsible_party", "counterparties", "exceptions",
    "exception_effects", "exception_basis", "workflow_semantics",
    "recommended_hit_policy", "versioning_status",
)


def _exact_logic_fingerprint(rule: Dict[str, Any]) -> str:
    """Stable fingerprint for globally exact semantic duplicates only."""
    payload = {field: rule.get(field) for field in _EXACT_LOGIC_FIELDS}
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _records(value: Any) -> List[Any]:
    if value in (None, "", []):
        return []
    return list(value) if isinstance(value, list) else [value]


def _merge_unique(left: Any, right: Any) -> List[Any]:
    merged: List[Any] = []
    for item in _records(left) + _records(right):
        if item not in merged:
            merged.append(item)
    return merged

# Helper for real-time output
def _print(msg):
    """Print with immediate flush for real-time console output."""
    print(msg, flush=True)


def _relation_to_dependency(relation: "Relation") -> Dict[str, Any]:
    """Adapt a derived relation onto the dependency shape consumers already read.

    ``confidence`` is retained because downstream readers expect the key, but a
    derived relation is not estimated -- it either satisfies its acceptance
    condition or it is not emitted -- so the payload says so rather than
    dressing a certainty up as a score.
    """
    payload = {
        "source_rule_id": relation.source_rule_id,
        "target_rule_id": relation.target_rule_id,
        "dependency_type": relation.kind,
        "symbols": list(relation.symbols),
        "basis": relation.basis,
        "rationale": relation.rationale,
        "structurally_supported": True,
        "strength": len(relation.symbols),
        "confidence": {"overall_score": 100.0, "basis": relation.basis,
                       "note": "derived from the rule contracts, not estimated"},
    }
    if relation.proof is not None:
        payload["proof"] = dict(relation.proof)
    return payload


class KnowledgeGraphOptimizer:
    """
    Agent that canonicalizes a business-rules knowledge graph.
    
    Features:
    - Conservative deduplication (only removes truly identical rules)
    - Typed deterministic dataflow, gating, conflict, and association analysis
    - Detailed rationale for all optimization decisions
    """
    
    def __init__(self, api_key: str, model: Optional[str] = None, reasoning_effort: Optional[str] = None):
        """
        Initialize the optimizer.
        
        Args:
            api_key: API key for LLM provider
            model: Optional override for reasoning model
            reasoning_effort: Optional override for reasoning effort level (none/low/medium/high/xhigh/max)
        """
        self.config = get_config()
        self.model = model or self.config.get_optimizer_model_name()
        self.reasoning_effort = reasoning_effort or self.config.get_reasoning_effort()
        self.client = create_llm_client(
            api_key=api_key,
            model=self.model,
            timeout=self.config.get_timeout(),
            max_retries=self.config.get_max_retries()
        )
        self.prompt_manager = get_prompt_manager()
        # config.get_max_workers() already implements "MAX_WORKERS env var,
        # else pipeline.max_workers (80)" — reading os.environ directly here
        # duplicated that logic with the wrong fallback (1, not 40), so any
        # run that didn't explicitly pass --workers silently serialized this
        # agent's entire dedup batch loop and cross-batch dependency pass
        # (both otherwise built to run on a ThreadPoolExecutor sized to
        # self.max_workers) despite the CLI's own --workers help text and
        # this class's docstring both describing a default of 40.
        self.max_workers = self.config.get_max_workers()
        
        print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║   Compliance Knowledge Graph Optimizer                              ║
║   Conservative Deduplication + Typed Relationship Derivation        ║
╚══════════════════════════════════════════════════════════════════════╝
""", flush=True)
        print(f"Configuration:", flush=True)
        print(f"  Model: {self.model}", flush=True)
        print(f"  Reasoning Effort: {self.reasoning_effort}", flush=True)
        print(f"  Workers: {self.max_workers}", flush=True)

    def _rule_summary_v2(self, rule: Dict[str, Any], include_related_entities: bool = False) -> Dict[str, Any]:
        """Summarize a rule for the dedup/dependency LLM prompts, preferring
        the v2 structured contract over the legacy v1 prose fields.

        agent_03's compact prompts explicitly forbid the legacy `conditions`/
        `consequences` string fields for every domain this repo carries (see
        domain-prompts/*/business_rules_extraction_compact.txt), so a v2-only
        rule simply has neither field. All four summary sites in this class
        used to read only `conditions`/`consequences`, which meant a v2 rule's
        summary carried nothing but a truncated description and type — none
        of its condition_predicates, condition_logic, outcomes, variables,
        applicability_scope, or exceptions ever reached the dedup or
        dependency-analysis prompts.

        This reads whichever contract the rule actually carries: the v2
        structured fields when the rule has them, and the legacy prose
        fields otherwise, so an older v1 graph still summarizes exactly as
        it did before. `include_related_entities` exists because one of the
        four call sites (`_deduplicate_rules_single`) never included that
        field and the other three always did — preserved here rather than
        silently added to or dropped from any site.
        """
        summary: Dict[str, Any] = {
            'rule_id': rule.get('rule_id'),
            'rule_type': rule.get('rule_type'),
            'title': rule.get('title'),
            'description': rule.get('description', '')[:self.config.get_optimizer_description_truncation_length()],
        }
        is_v2 = bool(rule.get('condition_predicates') or rule.get('outcomes'))
        if is_v2:
            summary['condition_predicates'] = rule.get('condition_predicates', [])
            summary['condition_logic'] = rule.get('condition_logic')
            summary['outcomes'] = rule.get('outcomes', [])
            summary['variables'] = [
                {
                    'name': v.get('name'), 'type': v.get('type'), 'role': v.get('role'),
                    **({'fact_id': v.get('fact_id')} if v.get('fact_id') else {}),
                    **({'unit': v.get('unit')} if v.get('unit') else {}),
                }
                for v in rule.get('variables', []) or []
                if isinstance(v, dict)
            ]
            summary['applicability_scope'] = rule.get('applicability_scope')
            summary['exceptions'] = rule.get('exceptions', [])
            if rule.get('recommended_hit_policy'):
                summary['recommended_hit_policy'] = rule.get('recommended_hit_policy')
            if rule.get('responsible_party'):
                summary['responsible_party'] = rule.get('responsible_party')
        else:
            summary['conditions'] = rule.get('conditions', [])
            summary['consequences'] = rule.get('consequences', [])
        if include_related_entities:
            summary['related_entities'] = rule.get('related_entities', [])
        return summary

    def _json_request(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        label: str,
    ) -> Dict[str, Any]:
        """Request and parse JSON with bounded retries for truncation/parse errors."""
        try:
            attempts = max(1, int(os.getenv("KG_OPTIMIZER_PARSE_ATTEMPTS", "2")))
        except (TypeError, ValueError):
            attempts = 2

        last_error = None
        for attempt in range(1, attempts + 1):
            retry_messages = list(messages)
            if attempt > 1:
                retry_messages.append({
                    "role": "user",
                    "content": (
                        "The previous response was not valid JSON. Retry the same "
                        "analysis and return complete, parseable JSON only; do not "
                        "truncate any string or omit required closing brackets."
                    ),
                })
            try:
                response = self.client.chat_completion(
                    messages=retry_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    reasoning_effort=self.reasoning_effort,
                )
                content = response.choices[0].message.content if response and response.choices else None
                if not content:
                    raise ValueError("empty model response")
                return self._parse_json_response(content)
            except Exception as exc:
                last_error = exc
                if attempt < attempts:
                    print(
                        f"   ⚠️ {label} JSON attempt {attempt}/{attempts} failed; retrying: {exc}",
                        flush=True,
                    )
        raise last_error
    
    def _calculate_dependency_confidence(self, confidence_breakdown: dict) -> dict:
        """Calculate overall dependency confidence score from breakdown components."""
        if isinstance(confidence_breakdown, (int, float)):
            return {'overall_score': confidence_breakdown}
        
        weights = {
            'semantic_similarity': 0.25,
            'logical_connection': 0.30,
            'temporal_ordering': 0.20,
            'cross_reference': 0.15,
            'domain_relevance': 0.10
        }
        
        total_score = 0
        total_weight = 0
        
        for key, weight in weights.items():
            if key in confidence_breakdown:
                total_score += confidence_breakdown[key] * weight
                total_weight += weight
        
        # If no standard keys found, try to average whatever is there
        if total_weight == 0 and confidence_breakdown:
            values = [v for v in confidence_breakdown.values() if isinstance(v, (int, float))]
            if values:
                total_score = sum(values) / len(values)
                total_weight = 1
        
        overall = round(total_score / total_weight, 2) if total_weight > 0 else 50
        
        return {
            'overall_score': overall,
            'breakdown': confidence_breakdown
        }
    
    def load_business_rules(self, input_file: Path) -> Dict[str, Any]:
        """Load business rules from consolidated JSON file."""
        print(f"\n{'='*70}", flush=True)
        print(f"📖 LOADING BUSINESS RULES", flush=True)
        print(f"{'='*70}", flush=True)
        print(f"   Source file: {input_file.name}", flush=True)
        print(f"   Full path: {input_file}", flush=True)
        
        if not input_file.exists():
            raise FileNotFoundError(f"Business rules file not found: {input_file}")
        
        print(f"\n   ⏳ Reading JSON file...", flush=True)
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Use top-level business_rules array (agent_05 output format)
        # entity_types.business_rules contains rule IDs, not full rule objects
        rules = data.get('business_rules', [])
        
        print(f"\n   ✅ Data loaded successfully!", flush=True)
        print(f"   ┌──────────────────────────────────────┐", flush=True)
        print(f"   │ Business Rules:  {len(rules):>6}              │", flush=True)
        print(f"   │ Entity Types:    {len(data.get('entity_types', {})):>6}              │", flush=True)
        print(f"   │ Relationships:   {len(data.get('relationships', {})):>6}              │", flush=True)
        print(f"   └──────────────────────────────────────┘", flush=True)
        
        # Show rule type distribution if available
        if rules:
            rule_types = {}
            for rule in rules:
                rt = rule.get('rule_type', 'unknown')
                rule_types[rt] = rule_types.get(rt, 0) + 1
            print(f"\n   📊 Rule Distribution:", flush=True)
            print(f"      By Type: {', '.join(f'{k}({v})' for k, v in sorted(rule_types.items(), key=lambda x: -x[1])[:7])}", flush=True)
        
        return data
    
    def deduplicate_rules(self, rules: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Deduplicate rules, chunking large inputs to keep requests bounded."""
        batch_size = self.config.get_optimizer_dedup_batch_size()
        if len(rules) > batch_size:
            return self._deduplicate_rules_batched(rules, batch_size)
        return self._deduplicate_rules_single(rules)

    def _deduplicate_rules_batched(
        self, rules: List[Dict[str, Any]], batch_size: int
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Run conservative deduplication on bounded chunks in parallel.

        Semantic cross-chunk merges are intentionally not inferred: a missed
        merge is safer than combining rules whose numeric scope or source
        differs. A final global pass does merge exact structured duplicates,
        preserving all evidence, before relationships are derived.
        """
        import math

        chunks = [rules[i:i + batch_size] for i in range(0, len(rules), batch_size)]
        # Match the worker pool to the API gate.  A large executor full of
        # blocked threads can starve later chunks because semaphore wake-ups
        # are not FIFO, producing hour-long tail latency on an otherwise
        # healthy provider.
        api_gate = max(1, int(os.getenv("KG_LLM_CONCURRENCY", str(self.max_workers))))
        workers = min(self.max_workers, api_gate, len(chunks))
        print(
            f"📦 Large rule set detected - deduplication uses {len(chunks)} chunks "
            f"of ≤{batch_size} rules ({workers} workers)", flush=True
        )

        def _run(chunk):
            try:
                return self._deduplicate_rules_single(chunk)
            except Exception as exc:
                print(f"   ⚠️ Dedup chunk retained unchanged after error: {exc}", flush=True)
                return chunk, {"error": str(exc), "duplicate_groups": [], "total_removed": 0}

        results = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for result in executor.map(_run, chunks):
                results.append(result)

        deduplicated = []
        groups = []
        removed_ids = []
        errors = []
        for chunk_rules, metadata in results:
            deduplicated.extend(chunk_rules)
            analysis = metadata.get("deduplication_analysis", metadata)
            groups.extend(analysis.get("duplicate_groups", []))
            removed_ids.extend(metadata.get("rules_removed_ids", []))
            if metadata.get("error"):
                errors.append(metadata["error"])

        # Batching bounds model calls but cannot see exact duplicates split
        # across chunks. A deterministic global pass safely closes that gap:
        # it merges only byte-equivalent structured semantics and preserves
        # every source and field-evidence record.
        globally_deduplicated: List[Dict[str, Any]] = []
        primary_by_fingerprint: Dict[str, Dict[str, Any]] = {}
        cross_batch_groups: Dict[str, Dict[str, Any]] = {}
        for rule in deduplicated:
            fingerprint = _exact_logic_fingerprint(rule)
            primary = primary_by_fingerprint.get(fingerprint)
            if primary is None:
                primary_by_fingerprint[fingerprint] = rule
                globally_deduplicated.append(rule)
                continue
            primary_id = str(primary.get("rule_id") or "")
            duplicate_id = str(rule.get("rule_id") or "")
            removed_ids.append(duplicate_id)
            group = cross_batch_groups.setdefault(primary_id, {
                "primary_rule_id": primary_id,
                "duplicate_rule_ids": [],
                "rationale": "Exact structured semantics matched across deduplication batches.",
                "confidence": "deterministic_exact",
            })
            group["duplicate_rule_ids"].append(duplicate_id)
            merged_refs = _merge_unique(primary.get("source_reference"), rule.get("source_reference"))
            if merged_refs:
                primary["source_reference"] = merged_refs[0] if len(merged_refs) == 1 else merged_refs
            left_evidence = primary.get("field_evidence") if isinstance(primary.get("field_evidence"), dict) else {}
            right_evidence = rule.get("field_evidence") if isinstance(rule.get("field_evidence"), dict) else {}
            primary["field_evidence"] = {
                field: _merge_unique(left_evidence.get(field), right_evidence.get(field))
                for field in set(left_evidence) | set(right_evidence)
            }
            info = primary.setdefault("deduplication_info", {})
            info["merged_from"] = _merge_unique(info.get("merged_from"), duplicate_id)
            info["merge_count"] = len(info["merged_from"])

        deduplicated = globally_deduplicated
        groups.extend(cross_batch_groups.values())

        metadata = {
            "deduplication_analysis": {
                "duplicate_groups": groups,
                "batched_analysis": True,
                "batch_size": batch_size,
                "num_batches": len(chunks),
                "cross_batch_exact_groups": len(cross_batch_groups),
            },
            "rules_removed_ids": removed_ids,
            "total_removed": len(removed_ids),
            "rules_remaining": len(deduplicated),
        }
        if errors:
            metadata["errors"] = errors
        print(
            f"✅ Batched deduplication complete: {len(rules)} → "
            f"{len(deduplicated)} rules ({len(removed_ids)} removed)", flush=True
        )
        return deduplicated, metadata

    def _deduplicate_rules_single(self, rules: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Deduplicate rationally identical rules using GPT-5 reasoning.
        
        Returns:
            - Deduplicated rules list
            - Deduplication metadata with rationale
        """
        print(f"\n{'='*70}", flush=True)
        print(f"STEP 1: Deduplicating Business Rules", flush=True)
        print(f"{'='*70}", flush=True)
        print(f"Analyzing {len(rules)} rules for rational duplicates...", flush=True)
        print(f"Strategy: Conservative - only remove truly identical rules", flush=True)
        print(f"📊 Preparing {len(rules)} rules for deduplication analysis...", flush=True)
        
        # Prepare rules summary for analysis
        rules_summary = [self._rule_summary_v2(rule) for rule in rules]

        rules_json = json.dumps(rules_summary, indent=2)
        total_rules = len(rules)

        prompt = self.prompt_manager.format_prompt(
            "rule_deduplication",
            rules_json=rules_json,
            total_rules=total_rules
        )
        
        print(f"\n🤖 Calling LLM for deduplication analysis...", flush=True)
        print(f"   • Model: {self.model}", flush=True)
        print(f"   • Rules to analyze: {len(rules)}", flush=True)
        print(f"   • Prompt size: ~{len(rules_json)//4:,} tokens", flush=True)
        print(f"   • Strategy: Conservative (only remove truly identical rules)", flush=True)
        print(f"\n   ⏳ Processing (this may take 1-2 minutes)...", flush=True)
        print(f"      → Sending request to {self.model}...", flush=True)
        
        try:
            # Use configured reasoning model for deduplication
            print(f"      → Using {self.model} for deduplication...", flush=True)
            
            dedup_result = self._json_request(
                [{"role": "user", "content": prompt}],
                temperature=self.config.get_optimizer_dedup_temperature(),
                max_tokens=self.config.get_optimizer_dedup_max_tokens(),
                label="Deduplication",
            )
            print(f"      ✓ Parsed JSON response", flush=True)
            dup_groups = len(dedup_result.get('duplicate_groups', []))
            print(f"      ✓ Found {dup_groups} duplicate groups", flush=True)
            
        except Exception as e:
            print(f"❌ Error during deduplication: {e}", flush=True)
            return rules, {"error": str(e), "duplicate_groups": [], "statistics": {}}
        
        # Apply deduplication
        rules_to_remove = set()
        enhanced_rules = {}
        
        # Build rule lookup for collecting source_references from duplicates
        rule_lookup = {rule.get("rule_id"): rule for rule in rules}
        
        for group in dedup_result.get("duplicate_groups", []):
            primary_id = group["primary_rule_id"]
            duplicates = group["duplicate_rule_ids"]
            rules_to_remove.update(duplicates)
            
            # Collect all source_references from primary + duplicates into an array
            collected_refs = []
            # Collect field_evidence too — a removed duplicate's per-field
            # citations (scope_basis, outcomes, exceptions, ...) are real
            # evidence for the merged rule, not just its source_reference.
            # Dropping them silently loses a section's only citation whenever
            # that section was cited exclusively through a duplicate's
            # field_evidence, which corpus_manifest's "every corpus change
            # needs an explicit reason" check then correctly flags as an
            # unexplained removal — this preserves the evidence instead.
            collected_field_evidence: Dict[str, List[Any]] = {}
            for rid in [primary_id] + duplicates:
                r = rule_lookup.get(rid)
                if not r:
                    continue
                ref = r.get('source_reference', r.get('legacy_source_reference', ''))
                if isinstance(ref, dict) and ref.get('chunk_path'):
                    collected_refs.append(ref)
                elif isinstance(ref, list):
                    collected_refs.extend(ref)
                elif isinstance(ref, str) and ref:
                    collected_refs.append(ref)
                field_evidence = r.get('field_evidence')
                if isinstance(field_evidence, dict):
                    for field_path, entries in field_evidence.items():
                        entry_list = entries if isinstance(entries, list) else ([entries] if entries else [])
                        bucket = collected_field_evidence.setdefault(field_path, [])
                        for entry in entry_list:
                            if entry not in bucket:
                                bucket.append(entry)

            # Store enhanced information for primary rule
            enhanced_rules[primary_id] = {
                "merged_description": group["merged_description"],
                "deduplication_info": {
                    "merged_from": duplicates,
                    "merge_count": len(duplicates),
                    "rationale": group["rationale"],
                    "confidence": group.get("confidence", "medium"),
                    "similarity_score": group.get("similarity_score"),
                    "score_breakdown": group.get("score_breakdown", {}),
                    "primary_selection_reason": group.get("primary_selection_reason", "")
                },
                "merged_examples": group.get("merged_examples", []),
                "collected_references": collected_refs,
                "collected_field_evidence": collected_field_evidence
            }
        
        # Build deduplicated list
        deduplicated_rules = []
        for rule in rules:
            rule_id = rule.get("rule_id")
            
            if rule_id in rules_to_remove:
                continue  # Skip removed duplicates
            
            # Enhance primary rules with merged information
            if rule_id in enhanced_rules:
                rule["description"] = enhanced_rules[rule_id]["merged_description"]
                rule["deduplication_info"] = enhanced_rules[rule_id]["deduplication_info"]
                # Apply merged examples if available
                if enhanced_rules[rule_id].get("merged_examples"):
                    rule["examples"] = enhanced_rules[rule_id]["merged_examples"]
                # Update source_reference with collected references from all merged rules
                collected = enhanced_rules[rule_id].get("collected_references", [])
                if collected:
                    if len(collected) == 1:
                        # Single reference — keep as-is (object or string)
                        rule["source_reference"] = collected[0]
                    else:
                        # Multiple references — store as array
                        rule["source_reference"] = collected
                # Merge in field_evidence collected from every merged duplicate,
                # keeping the primary rule's own entries (added first, above)
                # rather than replacing them.
                collected_field_evidence = enhanced_rules[rule_id].get("collected_field_evidence", {})
                if collected_field_evidence:
                    existing_field_evidence = rule.get("field_evidence")
                    merged_field_evidence = dict(existing_field_evidence) if isinstance(existing_field_evidence, dict) else {}
                    for field_path, entries in collected_field_evidence.items():
                        merged_field_evidence[field_path] = entries
                    rule["field_evidence"] = merged_field_evidence

            deduplicated_rules.append(rule)
        
        metadata = {
            "deduplication_analysis": dedup_result,
            "rules_removed_ids": list(rules_to_remove),
            "total_removed": len(rules_to_remove),
            "rules_remaining": len(deduplicated_rules)
        }
        
        print(f"\n{'='*50}", flush=True)
        print(f"✅ DEDUPLICATION COMPLETE", flush=True)
        print(f"{'='*50}", flush=True)
        print(f"   • Original rules:       {len(rules):>6}", flush=True)
        print(f"   • Duplicate groups:     {len(dedup_result.get('duplicate_groups', [])):>6}", flush=True)
        print(f"   • Rules removed:        {len(rules_to_remove):>6}", flush=True)
        print(f"   • Rules remaining:      {len(deduplicated_rules):>6}", flush=True)
        print(f"   • Reduction:            {(len(rules_to_remove)/len(rules)*100):.1f}%" if len(rules) > 0 else "   • Reduction:            0.0%", flush=True)
        
        return deduplicated_rules, metadata
    
    def analyze_dependencies(self, rules: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Derive rule relationships deterministically from the rule contracts.

        This replaced an LLM proposal pass that was screened by a single
        structural check.  Three measured problems motivated the change, all
        from real runs in this repository:

        * The proposal pass read batched rule summaries with a hard cap on
          cross-batch comparisons, so on a 613-rule run roughly 96% of rule
          pairs were never examined.  It asserted 4 edges where 66 were
          derivable from the same contracts.
        * ``dependency_type`` accepted six values that were defined nowhere and
          were all validated by the same check -- correct for one of them,
          irrelevant to four.  No code branched on the value.
        * The check ran once, here, and later stages rewrite variables in
          place, so an edge could outlive the symbol that justified it.

        Derivation is a hash join over ``(symbol, rule)`` entries, so it is
        exhaustive at a cost linear in declared symbols rather than quadratic
        in rules.  ``utils.rule_dependencies`` owns the relation kinds and
        their acceptance conditions; this method adapts the result onto the
        ``dependency_details`` shape the rest of the pipeline already reads.
        """
        print(f"\n{'='*70}", flush=True)
        print(f"STEP 2: Deriving Rule Relationships", flush=True)
        print(f"{'='*70}", flush=True)
        print(f"Deriving relationships across {len(rules)} rules (deterministic, no model calls)...", flush=True)

        # Promote dataflow to gating where the solver can prove the target
        # cannot fire without the source's outcome. Best-effort by design: a
        # rule that does not lower, or a query the solver cannot close, leaves
        # the relation at the weaker `dataflow` claim rather than guessing.
        try:
            entails, gating_coverage = make_entailment_oracle({"business_rules": rules})
        except Exception as exc:  # a solver problem must not fail the stage
            print(f"   \u26a0\ufe0f  gating classification unavailable ({exc}); relations stay at dataflow", flush=True)
            entails, gating_coverage = None, {}

        derived = derive_relations(rules, entails=entails)

        accepted_dependencies = [_relation_to_dependency(relation) for relation in derived.dependencies]

        rule_dependencies_map: Dict[str, List[Dict[str, Any]]] = {}
        rule_dependents_map: Dict[str, List[Dict[str, Any]]] = {}
        for dependency in accepted_dependencies:
            source_id = dependency["source_rule_id"]
            target_id = dependency["target_rule_id"]
            rule_dependencies_map.setdefault(target_id, []).append({
                "depends_on_rule": source_id,
                "dependency_type": dependency["dependency_type"],
                "rationale": dependency["rationale"],
                "symbols": dependency["symbols"],
                "basis": dependency["basis"],
                "structurally_supported": True,
            })
            rule_dependents_map.setdefault(source_id, []).append({
                "dependent_rule": target_id,
                "dependency_type": dependency["dependency_type"],
            })

        rules_with_deps = []
        for rule in rules:
            rule_id = rule.get("rule_id")
            if rule_id in rule_dependencies_map:
                rule["dependencies"] = rule_dependencies_map[rule_id]
            if rule_id in rule_dependents_map:
                rule["dependent_rules"] = rule_dependents_map[rule_id]
            rules_with_deps.append(rule)

        by_kind: Dict[str, int] = {}
        for relation in derived.dependencies:
            by_kind[relation.kind] = by_kind.get(relation.kind, 0) + 1

        metadata = {
            "dependency_analysis": {
                "dependencies": accepted_dependencies,
                "rejected_dependencies": [],
                "derivation": "deterministic",
                "kinds": by_kind,
            },
            "total_dependencies": len(accepted_dependencies),
            "proposed_dependencies": len(accepted_dependencies),
            "rejected_dependencies": 0,
            "dependency_chains": [],
            "circular_dependencies": [],
            "conflicts": [],
            # Symmetric co-sensitivity, carried separately on purpose: it is not
            # a dependency and must never enter a topological ordering.
            "associations": [relation.as_dict() for relation in derived.associations],
            "conflict_candidates": [relation.as_dict() for relation in derived.conflicts],
            "relation_refusals": [refusal.as_dict() for refusal in derived.refusals],
            "rules_with_dependencies": len(rule_dependencies_map),
            "rules_with_dependents": len(rule_dependents_map),
            "gating_coverage": gating_coverage,
            "fact_registry": build_fact_registry(rules),
        }

        print(f"  \u2022 Dependencies derived:    {len(accepted_dependencies):>5}  {by_kind or '{}'}", flush=True)
        print(f"  \u2022 Conflict candidates:     {len(derived.conflicts):>5}", flush=True)
        print(f"  \u2022 Associations (symmetric):{len(derived.associations):>5}", flush=True)
        print(f"  \u2022 Rules with dependencies: {len(rule_dependencies_map):>5}", flush=True)
        if gating_coverage:
            print(f"  \u2022 Gating check: {gating_stats(gating_coverage)}", flush=True)

        return rules_with_deps, metadata

    def optimize_parallel(self, rules: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
        """
        Deduplicate first, then derive relationships from the canonical rules.

        The method name is retained for CLI/checkpoint compatibility.  These
        operations are deliberately sequential: deriving edges from rules that
        are subsequently removed can leave stale associations, conflicts, and
        proof metadata in the optimized graph.
        
        Returns:
            - Deduplicated rules with dependencies
            - Deduplication metadata
            - Dependency metadata
        """
        print(f"\n{'='*70}", flush=True)
        print(f"🚀 CANONICAL OPTIMIZATION: Deduplication → Relationship Analysis", flush=True)
        print(f"{'='*70}", flush=True)
        try:
            deduplicated_rules, dedup_metadata = self.deduplicate_rules(copy.deepcopy(rules))
            print("✓ Task 1: Deduplication completed", flush=True)
        except Exception as exc:
            print(f"✗ Task 1: Deduplication failed; retaining all rules: {exc}", flush=True)
            deduplicated_rules = copy.deepcopy(rules)
            dedup_metadata = {"error": str(exc), "total_removed": 0}

        deduplicated_rules, fixes = enforce_rule_uniqueness(deduplicated_rules)
        dedup_metadata["uniqueness_fixes"] = fixes
        if fixes["id_fixes"] or fixes["name_fixes"]:
            print(
                f"   ⚠️  Canonicalized {fixes['id_fixes']} duplicate rule_id(s) and "
                f"{fixes['name_fixes']} duplicate rule_name(s) before relationship derivation",
                flush=True,
            )

        try:
            deduplicated_rules, dep_metadata = self.analyze_dependencies(deduplicated_rules)
            print("✓ Task 2: Relationship analysis completed on canonical rules", flush=True)
        except Exception as exc:
            print(f"✗ Task 2: Relationship analysis failed: {exc}", flush=True)
            dep_metadata = {"error": str(exc), "total_dependencies": 0}
        
        print(f"\n{'='*70}", flush=True)
        print(f"✅ CANONICAL OPTIMIZATION COMPLETE", flush=True)
        print(f"{'='*70}", flush=True)
        print(f"Results:", flush=True)
        print(f"  • Original rules: {len(rules)}", flush=True)
        print(f"  • Rules after deduplication: {len(deduplicated_rules)}", flush=True)
        print(f"  • Rules removed: {dedup_metadata.get('total_removed', 0)}", flush=True)
        print(f"  • Dependencies found: {dep_metadata.get('total_dependencies', 0)}", flush=True)
        print(f"  • Relationship basis: canonical post-deduplication rule set", flush=True)
        
        return deduplicated_rules, dedup_metadata, dep_metadata
    
    def save_optimized_results(self,
                               optimized_rules: List[Dict[str, Any]],
                               dedup_metadata: Dict[str, Any],
                               dep_metadata: Dict[str, Any],
                               original_data: Dict[str, Any],
                               output_dir: Path):
        """Save optimized results with all metadata and rationale."""
        print(f"\n{'='*70}", flush=True)
        print(f"STEP 3: Saving Optimized Results", flush=True)
        print(f"{'='*70}", flush=True)
        
        # Create output directory if it doesn't exist
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Create comprehensive optimized output
        optimized_output = {
            "metadata": {
                "optimizer_version": "1.0",
                "timestamp": timestamp,
                "model_used": self.model,
                "reasoning_effort": self.reasoning_effort,
                "original_rule_count": len(original_data.get("business_rules", [])),
                "optimized_rule_count": len(optimized_rules),
                "rules_removed_count": dedup_metadata.get("total_removed", 0),
                "dependencies_added_count": dep_metadata.get("total_dependencies", 0)
            },
            "optimization_summary": {
                "deduplication": {
                    "strategy": "Conservative - only remove rationally identical rules",
                    "duplicate_groups": len(dedup_metadata.get("deduplication_analysis", {}).get("duplicate_groups", [])),
                    "rules_removed": dedup_metadata.get("total_removed", 0),
                    "rationale": "Analyzed all rules for rational duplicates. Removed only those expressing identical business logic while preserving rules with meaningful differences in thresholds, contexts, or conditions.",
                    "analysis_notes": dedup_metadata.get("deduplication_analysis", {}).get("analysis_notes", "")
                },
                "dependency_analysis": {
                    "strategy": "Typed deterministic relationship derivation after deduplication",
                    "dependencies_found": dep_metadata.get("total_dependencies", 0),
                    "dependency_chains": len(dep_metadata.get("dependency_chains", [])),
                    "conflicts_identified": len(dep_metadata.get("conflicts", [])),
                    "rules_with_dependencies": dep_metadata.get("rules_with_dependencies", 0),
                    "rationale": "Derived dataflow only from compatible fact assignments and reads, promoted gating only with a reproducible solver proof, and kept symmetric associations and conflict candidates outside execution ordering.",
                    "analysis_notes": dep_metadata.get("dependency_analysis", {}).get("analysis_notes", "")
                }
            },
            "business_rules": optimized_rules,
            "fact_registry": dep_metadata.get("fact_registry", {}),
            "deduplication_details": dedup_metadata.get("deduplication_analysis", {}),
            "dependency_details": {
                "dependencies": dep_metadata.get("dependency_analysis", {}).get("dependencies", []),
                "dependency_chains": dep_metadata.get("dependency_chains", []),
                "conflicts": dep_metadata.get("conflicts", []),
                # Derived alongside the dependencies and kept separate: both are
                # symmetric, so neither may enter a topological ordering.
                "associations": dep_metadata.get("associations", []),
                "conflict_candidates": dep_metadata.get("conflict_candidates", []),
                "relation_refusals": dep_metadata.get("relation_refusals", []),
                "derivation": dep_metadata.get("dependency_analysis", {}).get("derivation", "deterministic"),
            },
            "entity_types": original_data.get("entity_types", {}),
            "relationships": original_data.get("relationships", [])
        }
        
        # Save optimized JSON
        json_file = output_dir / "optimized_compliance_knowledge_graph.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(optimized_output, f, indent=2, ensure_ascii=False)
        print(f"✓ Saved: {json_file.name}", flush=True)
        
        print(f"\n✅ All optimized files saved to: {output_dir}", flush=True)
    
    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """Parse JSON from response, handling markdown code blocks."""
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            # Try to extract JSON from markdown code blocks
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            try:
                return json.loads(text.strip())
            except json.JSONDecodeError as e2:
                print(f"⚠️  JSON parse error: {e}", flush=True)
                print(f"   First 500 chars of response: {text[:500]}", flush=True)
                print(f"⚠️  Failed to parse JSON even after extracting from code blocks: {e2}", flush=True)
                raise e2 from e
    
    def optimize(self, input_file: Path, output_dir: Path) -> Dict[str, Any]:
        """
        Main optimization workflow.
        
        Args:
            input_file: Path to compliance_knowledge_graph.json
            output_dir: Directory to save optimized outputs
            
        Returns:
            Summary statistics
        """
        print("\n" + "=" * 80, flush=True)
        print("🧠 agent_06: COMPLIANCE KNOWLEDGE GRAPH OPTIMIZER", flush=True)
        print("=" * 80, flush=True)
        print(f"\n📋 Purpose: Optimize the knowledge graph for quality and usability", flush=True)
        print(f"\n   This agent performs two key optimizations:", flush=True)
        print(f"   ┌─────────────────────────────────────────────────────────────┐", flush=True)
        print(f"   │ Step 1: DEDUPLICATION                                       │", flush=True)
        print(f"   │   • Identify rationally identical rules                     │", flush=True)
        print(f"   │   • Merge duplicates while preserving unique information    │", flush=True)
        print(f"   │   • Conservative approach - only remove true duplicates     │", flush=True)
        print(f"   ├─────────────────────────────────────────────────────────────┤", flush=True)
        print(f"   │ Step 2: TYPED RELATIONSHIP DERIVATION                       │", flush=True)
        print(f"   │   • Derive type-, unit-, and scope-compatible dataflow       │", flush=True)
        print(f"   │   • Promote logical gating only with a solver proof          │", flush=True)
        print(f"   │   • Keep associations/conflicts outside execution ordering  │", flush=True)
        print(f"   ├─────────────────────────────────────────────────────────────┤", flush=True)
        print(f"   │ Step 3: SAVE OPTIMIZED OUTPUTS                              │", flush=True)
        print(f"   │   • Optimized knowledge graph JSON                          │", flush=True)
        print(f"   └─────────────────────────────────────────────────────────────┘", flush=True)
        print(flush=True)
        
        # Load original data
        original_data = self.load_business_rules(input_file)
        
        # Extract all business rules - try top-level first, then entity_types structure
        rules = original_data.get("business_rules", [])
        
        # If no top-level rules, try extracting from entity_types structure
        if not rules and 'entity_types' in original_data:
            for entity_name, entity_data in original_data['entity_types'].items():
                entity_rules = entity_data.get('business_rules', [])
                # Add entity context to each rule
                for rule in entity_rules:
                    rule['entity_type'] = entity_name
                    rules.append(rule)
        
        if not rules:
            print("\n❌ No business rules found to optimize", flush=True)
            return {
                "original_count": 0,
                "optimized_count": 0,
                "removed_count": 0,
                "dependencies_count": 0
            }
        
        # Relationship derivation must run after deduplication so every stored
        # edge and fact-registry entry references the canonical graph.
        optimized_rules, dedup_metadata, dep_metadata = self.optimize_parallel(rules)

        # Step 3: Save Results
        self.save_optimized_results(
            optimized_rules,
            dedup_metadata,
            dep_metadata,
            original_data,
            output_dir
        )
        
        return {
            "original_count": len(rules),
            "optimized_count": len(optimized_rules),
            "removed_count": dedup_metadata.get("total_removed", 0),
            "dependencies_count": dep_metadata.get("total_dependencies", 0)
        }


def main():
    """Main entry point for the optimizer agent."""
    # Load configuration
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from utils.config import get_config
    
    config = get_config()
    
    # Configuration
    API_KEY = config.get_api_key()
    MODEL = config.get_optimizer_model_name()  # From config.json optimizer.model
    REASONING_EFFORT = config.get_reasoning_effort()
    OUTPUT_DIR = config.get_optimized_dir()
    
    # Input file from agent_05 output
    input_file = config.get_rules_with_entities_dir() / "compliance_knowledge_graph.json"
    
    if not input_file.exists():
        print(f"❌ Error: Input file not found: {input_file}", flush=True)
        print(f"   Please run the pipeline through agent_05 (consolidation) first.", flush=True)
        sys.exit(1)
    
    # Initialize optimizer
    optimizer = KnowledgeGraphOptimizer(
        api_key=API_KEY,
        model=MODEL,
        reasoning_effort=REASONING_EFFORT
    )
    
    # Run optimization
    try:
        result = optimizer.optimize(input_file, OUTPUT_DIR)
        
        print("\n" + "=" * 80, flush=True)
        print("✅ OPTIMIZATION COMPLETE", flush=True)
        print("=" * 80, flush=True)
        print(f"Results:", flush=True)
        print(f"  • Original rules:        {result['original_count']}", flush=True)
        print(f"  • Duplicates removed:    {result['removed_count']}", flush=True)
        print(f"  • Optimized rules:       {result['optimized_count']}", flush=True)
        print(f"  • Dependencies added:    {result['dependencies_count']}", flush=True)
        print(f"\nOptimized files (with 'optimized-' prefix):", flush=True)
        print(f"  • optimized_compliance_knowledge_graph.json", flush=True)
        print(f"\nLocation: {OUTPUT_DIR}", flush=True)
        
    except Exception as e:
        print(f"\n❌ Error during optimization: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
