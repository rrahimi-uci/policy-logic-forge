"""
Data contract tests for the agent pipeline.

Verifies that prompt output schemas (what we ask the LLM to produce) contain
the exact field names that downstream agent code reads.  Tests cover BOTH the
AML and mortgage domains so that a prompt edit in one domain that breaks the
pipeline is caught immediately.

Contracts validated
──────────────────
 Prompt file                    → Consumer agent(s)
 ──────────────────────────────────────────────────────
 entity_extraction.txt          → agent_02 / agent_05
 entity_refinement.txt          → agent_02 (meta-agent loop)
 business_rules_extraction.txt  → agent_03 / agent_05
 rule_deduplication.txt         → agent_06
 dependency_analysis.txt        → agent_06 / agent_10
 rule_matcher_batch.txt         → upstream comparison matcher/verifier (not shipped here)
 document_structure_analysis.txt→ agent_01
 entity_resolution.txt          → agent_02 (multi-doc)
 rule_resolution.txt            → agent_03 (multi-doc)
"""

import json
import re
import sys
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DOMAINS = [
    # Benchmark-corpus domains (CUAD, ContractNLI, OPP-115, MAPP) — the only
    # five domains this repo carries prompt packs for. The source pipeline's
    # version of this list also has mortgage/aml/healthcare/commercial_lending;
    # dropped here since this repo has no prompts for them (see README.md
    # "Scope" for why: no paired public benchmark corpus, no license check
    # done on the GSE/product source text those domains used).
    "commercial_contracts", "nda_confidentiality", "privacy_policy", "mobile_app_privacy",
    "deonticbench",
]
DOMAIN_PROMPTS = PROJECT_ROOT / "domain-prompts"
SHARED_PROMPTS = PROJECT_ROOT / "prompts"

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_prompt(domain: str, name: str) -> str:
    """Load a prompt file, domain-specific first, shared fallback."""
    domain_path = DOMAIN_PROMPTS / domain / f"{name}.txt"
    if domain_path.exists():
        return domain_path.read_text(encoding="utf-8")
    shared_path = SHARED_PROMPTS / f"{name}.txt"
    if shared_path.exists():
        return shared_path.read_text(encoding="utf-8")
    pytest.skip(f"Prompt {name}.txt not found for domain={domain}")


def _extract_json_blocks(text: str) -> list[str]:
    """Return all JSON-ish blocks (```json...```) from a prompt file."""
    blocks = re.findall(r"```json\s*\n(.*?)```", text, re.DOTALL)
    if not blocks:
        # Try bare { ... } blocks (some prompts omit fences)
        blocks = re.findall(r"(\{[\s\S]*?\n\})", text)
    return blocks


def _json_field_names(json_text: str) -> set[str]:
    """Extract quoted keys from a JSON-ish template (may contain placeholders)."""
    return set(re.findall(r'"([a-z_][a-z0-9_]*)"(?:\s*:)', json_text, re.IGNORECASE))


def _prompt_contains_field(prompt_text: str, field: str) -> bool:
    """Check whether a field name appears as a JSON key in the prompt."""
    # Match "field_name": or "field_name" : (with optional whitespace)
    return bool(re.search(rf'"{re.escape(field)}"\s*:', prompt_text))


def _prompt_contains_any(prompt_text: str, *values: str) -> bool:
    """Check whether any of the given string values appears in the prompt."""
    return any(v in prompt_text for v in values)


# ─────────────────────────────────────────────────────────────────────────────
# 0. Structural: every domain has all expected prompt files
# ─────────────────────────────────────────────────────────────────────────────

EXPECTED_PROMPT_FILES = [
    "business_rules_extraction",
    "dependency_analysis",
    "document_structure_analysis",
    "entity_extraction",
    "entity_refinement",
    "entity_resolution",
    "rule_deduplication",
    "rule_matcher",
    "rule_matcher_batch",
    "rule_resolution",
    "validation_report",
]


class TestPromptFileExistence:
    """Every domain directory must contain all expected prompt files."""

    @pytest.mark.parametrize("domain", DOMAINS)
    @pytest.mark.parametrize("prompt_name", EXPECTED_PROMPT_FILES)
    def test_prompt_file_exists(self, domain, prompt_name):
        path = DOMAIN_PROMPTS / domain / f"{prompt_name}.txt"
        assert path.exists(), f"Missing {domain}/{prompt_name}.txt"

    @pytest.mark.parametrize("prompt_name", EXPECTED_PROMPT_FILES)
    def test_shared_prompt_file_exists(self, prompt_name):
        path = SHARED_PROMPTS / f"{prompt_name}.txt"
        assert path.exists(), f"Missing shared prompts/{prompt_name}.txt"

    @pytest.mark.parametrize("domain", DOMAINS)
    @pytest.mark.parametrize("prompt_name", EXPECTED_PROMPT_FILES)
    def test_prompt_file_not_empty(self, domain, prompt_name):
        path = DOMAIN_PROMPTS / domain / f"{prompt_name}.txt"
        assert path.stat().st_size > 100, f"{domain}/{prompt_name}.txt is too small"


# ─────────────────────────────────────────────────────────────────────────────
# 1. rule_deduplication  →  agent_06 (deduplicate_rules)
#
#    agent_06 reads:
#      dedup_result.get("duplicate_groups", [])
#      group["primary_rule_id"]
#      group["duplicate_rule_ids"]
#      group["merged_description"]
#      group["rationale"]
#      group.get("confidence", "medium")
#      group.get("similarity_score")
#      group.get("score_breakdown", {})
#      group.get("primary_selection_reason", "")
#      group.get("merged_examples", [])
# ─────────────────────────────────────────────────────────────────────────────

class TestRuleDeduplicationContract:
    """rule_deduplication.txt must produce fields that agent_06 reads."""

    REQUIRED_TOP_LEVEL = ["duplicate_groups"]
    REQUIRED_GROUP_FIELDS = [
        "primary_rule_id",
        "duplicate_rule_ids",
        "merged_description",
        "rationale",
    ]
    OPTIONAL_GROUP_FIELDS = [
        "confidence",
        "similarity_score",
        "score_breakdown",
        "primary_selection_reason",
        "merged_examples",
    ]

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_top_level_duplicate_groups_key(self, domain):
        prompt = _load_prompt(domain, "rule_deduplication")
        assert _prompt_contains_field(prompt, "duplicate_groups"), (
            f"{domain}/rule_deduplication.txt must instruct LLM to output "
            f'"duplicate_groups" (agent_06 line ~213)'
        )

    @pytest.mark.parametrize("domain", DOMAINS)
    @pytest.mark.parametrize("field", REQUIRED_GROUP_FIELDS)
    def test_required_group_field_present(self, domain, field):
        prompt = _load_prompt(domain, "rule_deduplication")
        assert _prompt_contains_field(prompt, field), (
            f'{domain}/rule_deduplication.txt must include "{field}" in '
            f"duplicate_groups (agent_06 reads it)"
        )

    @pytest.mark.parametrize("domain", DOMAINS)
    @pytest.mark.parametrize("field", OPTIONAL_GROUP_FIELDS)
    def test_optional_group_field_present(self, domain, field):
        prompt = _load_prompt(domain, "rule_deduplication")
        assert _prompt_contains_field(prompt, field), (
            f'{domain}/rule_deduplication.txt should include "{field}" in '
            f"duplicate_groups for full agent_06 compatibility"
        )

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_no_legacy_merge_decisions_key(self, domain):
        """Ensure old 'merge_decisions' key is NOT present (agent_06 never reads it)."""
        prompt = _load_prompt(domain, "rule_deduplication")
        assert not _prompt_contains_field(prompt, "merge_decisions"), (
            f'{domain}/rule_deduplication.txt still contains "merge_decisions" — '
            f"agent_06 reads duplicate_groups, not merge_decisions"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. dependency_analysis  →  agent_06 (analyze_dependencies) + agent_10
#
#    agent_06 reads from LLM response:
#      dep_result.get("dependencies", [])
#      dep["source_rule_id"]
#      dep["target_rule_id"]
#      dep["dependency_type"]
#      dep["rationale"]
#      dep["impact"]
#      dep.get("strength", 3)
#      dep_result.get("dependency_chains", [])
#      dep_result.get("circular_dependencies", [])
#
#    agent_06 writes to rule (agent_10 reads):
#      rule["dependencies"][i]["depends_on_rule"]
#      rule["dependencies"][i]["dependency_type"]
# ─────────────────────────────────────────────────────────────────────────────

class TestDependencyAnalysisContract:
    """dependency_analysis.txt must produce fields that agent_06 reads."""

    REQUIRED_DEP_FIELDS = [
        "source_rule_id",
        "target_rule_id",
        "dependency_type",
        "rationale",
        "impact",
    ]
    VALID_DEPENDENCY_TYPES = [
        "prerequisite",
        "sequential",
        "conditional",
        "complementary",
        "contradictory",
        "override",
        "validation",
    ]

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_top_level_dependencies_key(self, domain):
        prompt = _load_prompt(domain, "dependency_analysis")
        assert _prompt_contains_field(prompt, "dependencies"), (
            f'{domain}/dependency_analysis.txt must instruct "dependencies" array'
        )

    @pytest.mark.parametrize("domain", DOMAINS)
    @pytest.mark.parametrize("field", REQUIRED_DEP_FIELDS)
    def test_required_dependency_field(self, domain, field):
        prompt = _load_prompt(domain, "dependency_analysis")
        assert _prompt_contains_field(prompt, field), (
            f'{domain}/dependency_analysis.txt must include "{field}" '
            f"(agent_06 reads dep[\"{field}\"])"
        )

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_strength_field(self, domain):
        prompt = _load_prompt(domain, "dependency_analysis")
        assert _prompt_contains_field(prompt, "strength"), (
            f'{domain}/dependency_analysis.txt must include "strength" '
            f"(agent_06 reads dep.get('strength', 3))"
        )

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_circular_dependencies_key(self, domain):
        prompt = _load_prompt(domain, "dependency_analysis")
        assert _prompt_contains_field(prompt, "circular_dependencies") or \
               _prompt_contains_any(prompt, "circular_dependencies"), (
            f'{domain}/dependency_analysis.txt should include "circular_dependencies"'
        )

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_dependency_chains_key(self, domain):
        prompt = _load_prompt(domain, "dependency_analysis")
        assert _prompt_contains_field(prompt, "dependency_chains") or \
               _prompt_contains_any(prompt, "dependency_chains"), (
            f'{domain}/dependency_analysis.txt should include "dependency_chains"'
        )

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_all_seven_dependency_types_mentioned(self, domain):
        prompt = _load_prompt(domain, "dependency_analysis")
        for dep_type in self.VALID_DEPENDENCY_TYPES:
            assert dep_type in prompt.lower(), (
                f'{domain}/dependency_analysis.txt must mention dependency type '
                f'"{dep_type}". agent_06 expects all 7 types.'
            )

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_no_legacy_field_names(self, domain):
        """Ensure old broken field names are NOT present."""
        prompt = _load_prompt(domain, "dependency_analysis")
        for legacy in ["prerequisite_rule_id", "dependent_rule_id"]:
            assert not _prompt_contains_field(prompt, legacy), (
                f'{domain}/dependency_analysis.txt contains legacy field '
                f'"{legacy}" — agent_06 reads source_rule_id/target_rule_id'
            )


# ─────────────────────────────────────────────────────────────────────────────
# 3. rule_matcher_batch  → upstream comparison matcher (not shipped here)
#
#    The upstream comparison matcher reads from each result:
#      result.get("relationship", "UNRELATED")
#      result.get("confidence", 0.5)
#      result.get("similarity_score", 0)
#      result.get("reasoning", "")
#      result.get("key_comparison", {})
#      result.get("conflict_detail", {})
# ─────────────────────────────────────────────────────────────────────────────

class TestRuleMatcherBatchContract:
    """rule_matcher_batch.txt preserves the upstream comparison contract."""

    REQUIRED_FIELDS = [
        "pair_id",
        "relationship",
        "confidence",
        "similarity_score",
        "reasoning",
    ]
    VALID_RELATIONSHIPS = ["IDENTICAL", "EQUIVALENT", "CONTRADICTORY", "UNRELATED"]

    @pytest.mark.parametrize("domain", DOMAINS)
    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_required_field_present(self, domain, field):
        prompt = _load_prompt(domain, "rule_matcher_batch")
        assert _prompt_contains_field(prompt, field), (
            f'{domain}/rule_matcher_batch.txt must include "{field}" '
            f"(the upstream comparison matcher reads it)"
        )

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_relationship_enum_values(self, domain):
        prompt = _load_prompt(domain, "rule_matcher_batch")
        for value in self.VALID_RELATIONSHIPS:
            assert value in prompt, (
                f'{domain}/rule_matcher_batch.txt must mention "{value}" '
                f"as a valid relationship value"
            )

    # NOTE: the source pipeline has test_key_comparison_present_aml /
    # test_conflict_detail_present_aml here, hardcoded to the "aml" domain,
    # which this repo doesn't carry (see README.md "Scope").


# ─────────────────────────────────────────────────────────────────────────────
# 4. entity_extraction  →  agent_02 / agent_05
#
#    agent_02 reads:
#      result.get("entity_types", {})
#      result.get("relationships", {})
#    agent_05 reads:
#      entity_data.get("entity_types") or entity_data.get("entities", {})
#      entity_data.get("relationships", {})
#      entity_info.get("business_rules", [])
# ─────────────────────────────────────────────────────────────────────────────

class TestEntityExtractionContract:
    """entity_extraction.txt must produce fields that agent_02 and agent_05 read."""

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_entity_types_key(self, domain):
        prompt = _load_prompt(domain, "entity_extraction")
        has_entity_types = _prompt_contains_field(prompt, "entity_types")
        has_entities = _prompt_contains_field(prompt, "entities")
        assert has_entity_types or has_entities, (
            f'{domain}/entity_extraction.txt must include "entity_types" or '
            f'"entities" (agent_02 or agent_05 read one or both)'
        )

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_relationships_key(self, domain):
        prompt = _load_prompt(domain, "entity_extraction")
        assert _prompt_contains_field(prompt, "relationships"), (
            f'{domain}/entity_extraction.txt must include "relationships"'
        )

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_business_rules_in_entities(self, domain):
        """Entities must have rule summaries: 'business_rules' (mortgage) or 'business_rule_summaries' (AML)."""
        prompt = _load_prompt(domain, "entity_extraction")
        has_business_rules = _prompt_contains_field(prompt, "business_rules")
        has_summaries = _prompt_contains_field(prompt, "business_rule_summaries")
        assert has_business_rules or has_summaries, (
            f'{domain}/entity_extraction.txt must include "business_rules" or '
            f'"business_rule_summaries" within each entity (used as context for agent_03)'
        )

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_entity_attributes(self, domain):
        """Each entity should have definition/description, attributes/key_attributes."""
        prompt = _load_prompt(domain, "entity_extraction")
        has_definition = _prompt_contains_field(prompt, "definition")
        has_description = _prompt_contains_field(prompt, "description")
        assert has_definition or has_description, (
            f'{domain}/entity_extraction.txt must include "definition" or "description" '
            f"for each entity type"
        )

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_relationship_source_target(self, domain):
        """Relationships must have source/target: mortgage uses source_entity/target_entity,
        AML uses source/target.  agent_05 reads with .get() defaults."""
        prompt = _load_prompt(domain, "entity_extraction")
        has_source_entity = _prompt_contains_field(prompt, "source_entity")
        has_source = _prompt_contains_field(prompt, "source")
        assert has_source_entity or has_source, (
            f'{domain}/entity_extraction.txt must include "source_entity" or "source" '
            f"in relationships"
        )
        has_target_entity = _prompt_contains_field(prompt, "target_entity")
        has_target = _prompt_contains_field(prompt, "target")
        assert has_target_entity or has_target, (
            f'{domain}/entity_extraction.txt must include "target_entity" or "target" '
            f"in relationships"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 5. business_rules_extraction  →  agent_03 / agent_05
#
#    agent_03 reads:
#      result.get("rules", [])      # flat format (AML)
#      result.get("entity_types")   # nested format (mortgage)
#      r.get("relationship")
#      r.get("entity", "UNKNOWN_ENTITY")
#    agent_04 reads:
#      rule.get("rule_id")
#      rule.get("rule_type")
#      rule.get("description")
#      rule.get("conditions")
#      rule.get("consequences")
#      rule.get("confidence_score")
#      rule.get("mandatory")
#      rule.get("source_reference")
# ─────────────────────────────────────────────────────────────────────────────

class TestBusinessRulesExtractionContract:
    """business_rules_extraction.txt must contain fields read by agent_03, agent_04, and agent_05."""

    CORE_RULE_FIELDS = [
        "rule_id",
        "rule_type",
        "description",
        "conditions",
        "consequences",
    ]

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_has_output_container(self, domain):
        """Must instruct LLM to output either 'rules' array or 'entity_types' dict."""
        prompt = _load_prompt(domain, "business_rules_extraction")
        has_rules = _prompt_contains_field(prompt, "rules")
        has_entity_types = _prompt_contains_field(prompt, "entity_types")
        assert has_rules or has_entity_types, (
            f'{domain}/business_rules_extraction.txt must output "rules" or "entity_types"'
        )

    @pytest.mark.parametrize("domain", DOMAINS)
    @pytest.mark.parametrize("field", CORE_RULE_FIELDS)
    def test_core_rule_field(self, domain, field):
        prompt = _load_prompt(domain, "business_rules_extraction")
        assert _prompt_contains_field(prompt, field), (
            f'{domain}/business_rules_extraction.txt must include "{field}" '
            f"in each rule (agent_04 validates it)"
        )

    def test_confidence_score_field_mortgage(self):
        """Mortgage prompt must include confidence_score (agent_04 validates confidence ranges)."""
        prompt = _load_prompt("mortgage", "business_rules_extraction")
        assert _prompt_contains_field(prompt, "confidence_score"), (
            'mortgage/business_rules_extraction.txt must include "confidence_score"'
        )

    def test_source_reference_field_mortgage(self):
        """Mortgage prompt must include source_reference (agent_04 validates it)."""
        prompt = _load_prompt("mortgage", "business_rules_extraction")
        assert _prompt_contains_field(prompt, "source_reference"), (
            'mortgage/business_rules_extraction.txt must include "source_reference"'
        )

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_regulatory_or_source_reference(self, domain):
        """Each domain must have provenance: source_reference (mortgage) or regulatory_source (AML)."""
        prompt = _load_prompt(domain, "business_rules_extraction")
        has_src_ref = _prompt_contains_field(prompt, "source_reference")
        has_reg_src = _prompt_contains_field(prompt, "regulatory_source")
        assert has_src_ref or has_reg_src, (
            f'{domain}/business_rules_extraction.txt must include "source_reference" '
            f'or "regulatory_source" for rule provenance'
        )

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_mandatory_field(self, domain):
        prompt = _load_prompt(domain, "business_rules_extraction")
        assert _prompt_contains_field(prompt, "mandatory"), (
            f'{domain}/business_rules_extraction.txt must include "mandatory" '
            f"(agent_04 and agent_05 read it)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. document_structure_analysis  →  agent_01
#
#    agent_01 reads:
#      result.get("sections", [])
#      section.get("start_marker")
#      section.get("end_marker")
# ─────────────────────────────────────────────────────────────────────────────

class TestDocumentStructureContract:
    """document_structure_analysis.txt must produce fields agent_01 reads."""

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_sections_key(self, domain):
        prompt = _load_prompt(domain, "document_structure_analysis")
        assert _prompt_contains_field(prompt, "sections"), (
            f'{domain}/document_structure_analysis.txt must include "sections"'
        )


# ─────────────────────────────────────────────────────────────────────────────
# 7. Cross-domain structural consistency
#
#    These tests verify that the AML and mortgage prompt schemas are
#    structurally consistent (same top-level keys, same required fields).
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossDomainConsistency:
    """AML and mortgage prompts must share the same structural contract."""

    CRITICAL_PAIRS = [
        ("rule_deduplication", ["duplicate_groups"]),
        ("dependency_analysis", ["dependencies", "circular_dependencies", "dependency_chains"]),
        ("rule_matcher_batch", ["pair_id", "relationship", "confidence", "similarity_score", "reasoning"]),
        ("entity_extraction", ["relationships"]),
    ]

    @pytest.mark.parametrize("prompt_name,fields", CRITICAL_PAIRS)
    def test_both_domains_have_same_critical_fields(self, prompt_name, fields):
        aml = _load_prompt("aml", prompt_name)
        mortgage = _load_prompt("mortgage", prompt_name)
        for field in fields:
            aml_has = _prompt_contains_field(aml, field) or field in aml
            mort_has = _prompt_contains_field(mortgage, field) or field in mortgage
            assert aml_has == mort_has, (
                f'Field "{field}" in {prompt_name}.txt: '
                f"AML={'present' if aml_has else 'MISSING'}, "
                f"mortgage={'present' if mort_has else 'MISSING'} — "
                f"both must match for pipeline compatibility"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 8. agent_06 output → agent_10 input contract
#
#    agent_10 reads from the optimized graph:
#      data.get("business_rules", [])
#      rule.get("rule_id")
#      rule.get("rule_type")
#      rule.get("rule_name")
#      rule.get("mandatory")
#      rule.get("dependencies", [])
#        dep.get("depends_on_rule")
#        dep.get("dependency_type")
#      rule.get("source_reference") or rule.get("legacy_source_reference")
# ─────────────────────────────────────────────────────────────────────────────

class TestAgent06ToAgent10Contract:
    """Verify agent_06 output structure matches what agent_10 reads.

    We test this by verifying agent_06 code writes the correct keys that
    agent_10 accesses, using import-level introspection of the code.
    """

    def test_agent_06_writes_depends_on_rule(self):
        """agent_06 must write 'depends_on_rule' (not 'source_rule_id') into rule deps."""
        agent_06_code = (PROJECT_ROOT / "agents" / "agent_06_knowledge_graph_optimizer.py").read_text()
        assert '"depends_on_rule"' in agent_06_code or "'depends_on_rule'" in agent_06_code, (
            "agent_06 must write 'depends_on_rule' key into rule dependencies "
            "(agent_10 reads dep.get('depends_on_rule'))"
        )

    def test_agent_06_writes_dependency_type(self):
        agent_06_code = (PROJECT_ROOT / "agents" / "agent_06_knowledge_graph_optimizer.py").read_text()
        assert '"dependency_type"' in agent_06_code or "'dependency_type'" in agent_06_code

    def test_agent_06_writes_deduplication_info(self):
        agent_06_code = (PROJECT_ROOT / "agents" / "agent_06_knowledge_graph_optimizer.py").read_text()
        assert '"deduplication_info"' in agent_06_code or "'deduplication_info'" in agent_06_code

    def test_agent_10_reads_depends_on_rule(self):
        """agent_10 (dependency-DAG generator, via utils/dag_builder.py's
        dependency_edges()) must read 'depends_on_rule' for dependency edges.

        The source pipeline's version of this test points at
        the upstream HTML visualizer module; this repo
        has no visualizer (see README.md "Scope") and agent_10 here is the
        dependency-DAG generator instead.
        """
        dag_builder_code = (PROJECT_ROOT / "utils" / "dag_builder.py").read_text()
        kg_readiness_code = (PROJECT_ROOT / "utils" / "kg_readiness.py").read_text()
        assert "depends_on_rule" in dag_builder_code + kg_readiness_code

    def test_agent_10_reads_dependency_type(self):
        dag_builder_code = (PROJECT_ROOT / "utils" / "dag_builder.py").read_text()
        assert "dependency_type" in dag_builder_code


# NOTE: the upstream source pipeline has additional contracts for its
# cross-graph comparison modules. This repository ships only the ten canonical
# extraction/readiness/grounding/DAG agents; comparing two already-extracted
# graphs is a different task, out of scope (see README.md "Scope").


# ─────────────────────────────────────────────────────────────────────────────
# 11. agent_03 normalization shim
#
#    agent_03 must handle BOTH:
#      - Nested format: {"entity_types": {...}, "relationships": {...}}
#      - Flat format:   {"rules": [...]}  (AML)
#    And normalize flat → nested so agent_05 always gets entity_types.
# ─────────────────────────────────────────────────────────────────────────────

class TestAgent03NormalizationContract:
    """agent_03 must handle both flat and nested rule formats."""

    def test_agent_03_handles_flat_rules(self):
        agent_03_code = (PROJECT_ROOT / "agents" / "agent_03_rules_extractor.py").read_text()
        assert "'rules'" in agent_03_code or '"rules"' in agent_03_code, (
            "agent_03 must check for flat 'rules' array format"
        )

    def test_agent_03_handles_entity_types(self):
        agent_03_code = (PROJECT_ROOT / "agents" / "agent_03_rules_extractor.py").read_text()
        assert "'entity_types'" in agent_03_code or '"entity_types"' in agent_03_code, (
            "agent_03 must handle nested 'entity_types' format"
        )

    def test_agent_03_normalizes_flat_to_nested(self):
        """agent_03 must convert flat rules → entity_types/relationships."""
        agent_03_code = (PROJECT_ROOT / "agents" / "agent_03_rules_extractor.py").read_text()
        # Must have normalization: if 'rules' in result and 'entity_types' not in result
        assert "entity_types" in agent_03_code and "rules" in agent_03_code, (
            "agent_03 must normalize flat rules to entity_types structure"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 12. agent_05 entity format flexibility
#
#    agent_05 must handle both:
#      entity_data.get("entity_types") — dict keyed by entity name
#      entity_data.get("entities")     — list of entity objects
# ─────────────────────────────────────────────────────────────────────────────

class TestAgent05EntityFormatContract:
    """agent_05 must accept both dict and list entity formats."""

    def test_agent_05_handles_entity_types_dict(self):
        agent_05_code = (PROJECT_ROOT / "agents" / "agent_05_rules_with_entities_merger.py").read_text()
        assert "entity_types" in agent_05_code

    def test_agent_05_handles_entities_list(self):
        agent_05_code = (PROJECT_ROOT / "agents" / "agent_05_rules_with_entities_merger.py").read_text()
        # agent_05 must have fallback: entity_data.get('entity_types') or entity_data.get('entities', {})
        assert "entities" in agent_05_code, (
            "agent_05 must support 'entities' list format as fallback"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 13. entity_resolution / rule_resolution cross-domain parity
# ─────────────────────────────────────────────────────────────────────────────

class TestResolutionPromptContracts:
    """entity_resolution and rule_resolution must have consistent schemas."""

    ENTITY_RESOLUTION_FIELDS = [
        "entity_clusters",
        "resolution_summary",
    ]
    RULE_RESOLUTION_FIELDS = [
        "rule_clusters",
        "resolution_summary",
    ]

    @pytest.mark.parametrize("domain", DOMAINS)
    @pytest.mark.parametrize("field", ENTITY_RESOLUTION_FIELDS)
    def test_entity_resolution_fields(self, domain, field):
        prompt = _load_prompt(domain, "entity_resolution")
        assert _prompt_contains_field(prompt, field), (
            f'{domain}/entity_resolution.txt must include "{field}"'
        )

    @pytest.mark.parametrize("domain", DOMAINS)
    @pytest.mark.parametrize("field", RULE_RESOLUTION_FIELDS)
    def test_rule_resolution_fields(self, domain, field):
        prompt = _load_prompt(domain, "rule_resolution")
        assert _prompt_contains_field(prompt, field), (
            f'{domain}/rule_resolution.txt must include "{field}"'
        )

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_rule_resolution_has_conflicts_detected(self, domain):
        prompt = _load_prompt(domain, "rule_resolution")
        assert _prompt_contains_field(prompt, "conflicts_detected"), (
            f'{domain}/rule_resolution.txt must include "conflicts_detected"'
        )


# ─────────────────────────────────────────────────────────────────────────────
# 14. rule_matcher (single-pair) consistency with batch
# ─────────────────────────────────────────────────────────────────────────────

class TestRuleMatcherSingleVsBatch:
    """rule_matcher.txt and rule_matcher_batch.txt must share core output fields."""

    SHARED_FIELDS = ["relationship", "confidence", "similarity_score", "reasoning"]

    @pytest.mark.parametrize("domain", DOMAINS)
    @pytest.mark.parametrize("field", SHARED_FIELDS)
    def test_single_matcher_has_field(self, domain, field):
        prompt = _load_prompt(domain, "rule_matcher")
        assert _prompt_contains_field(prompt, field), (
            f'{domain}/rule_matcher.txt must include "{field}" (shared with batch)'
        )

    @pytest.mark.parametrize("domain", DOMAINS)
    @pytest.mark.parametrize("field", SHARED_FIELDS)
    def test_batch_matcher_has_field(self, domain, field):
        prompt = _load_prompt(domain, "rule_matcher_batch")
        assert _prompt_contains_field(prompt, field), (
            f'{domain}/rule_matcher_batch.txt must include "{field}" (shared with single)'
        )


# ─────────────────────────────────────────────────────────────────────────────
# 15. validation_report does NOT need cross-domain parity
#     (domain-specific scoring is intentional)
#     but it must contain the core output structure.
# ─────────────────────────────────────────────────────────────────────────────

class TestValidationReportContract:
    """validation_report.txt must produce a structured report."""

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_has_scoring_section(self, domain):
        prompt = _load_prompt(domain, "validation_report")
        has_score = _prompt_contains_any(prompt, "score", "rating", "assessment")
        assert has_score, (
            f"{domain}/validation_report.txt must include scoring criteria"
        )
