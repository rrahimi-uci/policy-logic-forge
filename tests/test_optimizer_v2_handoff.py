"""PIPE-3 (plan/neurips-plan-2027.md §3.3): the optimizer's dedup/dependency
prompts must see a v2 rule's structured contract, not just its truncated
description.

Before this fix, `_deduplicate_rules_single`, `analyze_dependencies`, and
both batched dependency paths in `agent_06_knowledge_graph_optimizer.py`
built their LLM-facing rule summaries from the legacy `conditions` /
`consequences` string fields alone. agent_03's compact prompts explicitly
forbid those fields for every domain this repo carries (see
domain-prompts/*/business_rules_extraction_compact.txt), so a v2-only rule's
summary carried nothing but `rule_id`, `rule_type`, `title`, and a truncated
`description` — none of its `condition_predicates`, `condition_logic`,
`outcomes`, `variables`, `applicability_scope`, or `exceptions` ever reached
the model doing deduplication or dependency analysis.

`_rule_summary_v2()` is the shared fix: it reads whichever contract a rule
actually carries. These tests exercise the helper directly (unit) and then
confirm all four call sites actually use it by inspecting the JSON each one
hands to `prompt_manager.format_prompt` (integration, no live LLM call —
same `object.__new__(KnowledgeGraphOptimizer)` construction pattern as
tests/test_agent_06_dependency_support.py).
"""

import json
from unittest.mock import MagicMock

from agents.agent_06_knowledge_graph_optimizer import KnowledgeGraphOptimizer


def _v1_rule(rule_id="R1"):
    return {
        "rule_id": rule_id,
        "rule_type": "eligibility",
        "title": "Legacy rule",
        "description": "A prose rule extracted under the v1 contract.",
        "conditions": ["credit_score >= 620"],
        "consequences": ["loan_approved = true"],
    }


def _v2_rule(rule_id="R2"):
    return {
        "rule_id": rule_id,
        "rule_type": "confidentiality_scope",
        "title": "Structured rule",
        "description": "A structured rule extracted under the v2 contract.",
        "condition_predicates": [
            {"predicate_id": "p1", "variable": "disclosure_to_third_party", "operator": "==", "value": True, "value_type": "boolean"}
        ],
        "condition_logic": {"predicate_ref": "p1"},
        "outcomes": [
            {"variable": "breach_of_confidentiality", "operator": "=", "value": True, "value_type": "boolean"}
        ],
        "variables": [
            {"name": "disclosure_to_third_party", "type": "boolean", "role": "input", "unit": None},
            {"name": "breach_of_confidentiality", "type": "boolean", "role": "output"},
        ],
        "applicability_scope": {"loan_types": [], "occupancy_types": [], "transaction_types": []},
        "exceptions": [
            {"predicate_id": "e1", "variable": "compelled_by_judicial_order", "operator": "==", "value": True, "value_type": "boolean"}
        ],
        "recommended_hit_policy": "UNIQUE",
        "responsible_party": "RECIPIENT",
        "related_entities": ["RECIPIENT", "DISCLOSING_PARTY"],
        # A v2-only rule never carries these — asserted absent below to
        # confirm the summary isn't reading them by accident.
    }


def _optimizer():
    """Bare optimizer with just enough mocked config to call the summary
    helper and drive the four prompt-building call sites without a real
    LLM client, matching tests/test_agent_06_dependency_support.py."""
    optimizer = object.__new__(KnowledgeGraphOptimizer)
    optimizer.config = MagicMock()
    optimizer.config.get_optimizer_description_truncation_length.return_value = 500
    optimizer.config.get_optimizer_batch_size.return_value = 100
    optimizer.config.get_optimizer_dedup_temperature.return_value = 0.1
    optimizer.config.get_optimizer_dedup_max_tokens.return_value = 4000
    optimizer.config.get_optimizer_dependency_temperature.return_value = 0.1
    optimizer.config.get_optimizer_dependency_max_tokens.return_value = 4000
    optimizer.config.get_optimizer_batched_temperature.return_value = 0.1
    optimizer.config.get_optimizer_batched_max_tokens.return_value = 4000
    optimizer.config.get_optimizer_max_cross_batch_pairs = MagicMock(return_value=20)
    optimizer.model = "test-model"
    optimizer.reasoning_effort = "medium"
    optimizer.max_workers = 4
    optimizer.prompt_manager = MagicMock()
    optimizer.prompt_manager.format_prompt.return_value = "irrelevant prompt text"

    empty_dedup = json.dumps({"duplicate_groups": []})
    dedup_response = MagicMock()
    dedup_response.choices = [MagicMock(message=MagicMock(content=empty_dedup))]

    empty_deps = json.dumps({"dependencies": []})
    deps_response = MagicMock()
    deps_response.choices = [MagicMock(message=MagicMock(content=empty_deps))]

    optimizer.client = MagicMock()
    optimizer.client.chat_completion.return_value = deps_response
    return optimizer


# ─────────────────────────────────────────────────────────────────────────
# _rule_summary_v2 — unit tests
# ─────────────────────────────────────────────────────────────────────────

def test_v2_only_rule_yields_predicate_context():
    optimizer = _optimizer()
    summary = optimizer._rule_summary_v2(_v2_rule())

    assert summary["condition_predicates"] == _v2_rule()["condition_predicates"]
    assert summary["condition_logic"] == {"predicate_ref": "p1"}
    assert summary["outcomes"] == _v2_rule()["outcomes"]
    assert summary["applicability_scope"] == _v2_rule()["applicability_scope"]
    assert summary["exceptions"] == _v2_rule()["exceptions"]
    assert summary["recommended_hit_policy"] == "UNIQUE"
    assert summary["responsible_party"] == "RECIPIENT"
    # No legacy fields leak into a v2 summary.
    assert "conditions" not in summary
    assert "consequences" not in summary


def test_v2_variables_are_trimmed_to_name_type_role():
    """Variables may carry unit/allowed_range/free_text metadata the dedup
    and dependency prompts don't need — only name/type/role travel."""
    optimizer = _optimizer()
    summary = optimizer._rule_summary_v2(_v2_rule())

    assert summary["variables"] == [
        {"name": "disclosure_to_third_party", "type": "boolean", "role": "input"},
        {"name": "breach_of_confidentiality", "type": "boolean", "role": "output"},
    ]


def test_v1_rule_still_summarised():
    """Back-compat: a rule with no v2 fields at all must still summarize
    exactly as every call site did before this change."""
    optimizer = _optimizer()
    summary = optimizer._rule_summary_v2(_v1_rule())

    assert summary["conditions"] == ["credit_score >= 620"]
    assert summary["consequences"] == ["loan_approved = true"]
    # No v2 fields leak into a v1 summary.
    assert "condition_predicates" not in summary
    assert "outcomes" not in summary
    assert "variables" not in summary


def test_related_entities_only_included_when_requested():
    optimizer = _optimizer()
    rule = _v2_rule()

    without = optimizer._rule_summary_v2(rule)
    with_entities = optimizer._rule_summary_v2(rule, include_related_entities=True)

    assert "related_entities" not in without
    assert with_entities["related_entities"] == ["RECIPIENT", "DISCLOSING_PARTY"]


def test_a_rule_with_neither_contract_produces_empty_legacy_fields():
    """A malformed or empty rule must not raise — it falls back to the
    legacy branch with empty lists rather than crashing the batch."""
    optimizer = _optimizer()
    summary = optimizer._rule_summary_v2({"rule_id": "EMPTY"})

    assert summary["conditions"] == []
    assert summary["consequences"] == []


# ─────────────────────────────────────────────────────────────────────────
# Integration: all four call sites must actually use the helper
# ─────────────────────────────────────────────────────────────────────────

def test_deduplication_prompt_carries_v2_structure():
    optimizer = _optimizer()
    optimizer.client.chat_completion.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps({"duplicate_groups": []})))]
    )

    optimizer._deduplicate_rules_single([_v2_rule()])

    kwargs = optimizer.prompt_manager.format_prompt.call_args.kwargs
    sent = json.loads(kwargs["rules_json"])
    assert sent[0]["condition_predicates"], "v2 predicates must reach the dedup prompt"
    assert "related_entities" not in sent[0], "dedup never included related_entities before this change"


def test_single_batch_dependency_prompt_carries_v2_structure():
    optimizer = _optimizer()

    optimizer.analyze_dependencies([_v2_rule()])

    kwargs = optimizer.prompt_manager.format_prompt.call_args.kwargs
    sent = json.loads(kwargs["rules_json"])
    assert sent[0]["outcomes"], "v2 outcomes must reach the single-batch dependency prompt"
    assert sent[0]["related_entities"] == ["RECIPIENT", "DISCLOSING_PARTY"]


def test_batched_within_batch_dependency_prompt_carries_v2_structure():
    optimizer = _optimizer()
    optimizer.config.get_optimizer_batch_size.return_value = 1  # force the batched path

    rules = [_v2_rule("R2"), _v2_rule("R3")]
    optimizer._analyze_dependencies_batched(rules, batch_size=1)

    calls = optimizer.prompt_manager.format_prompt.call_args_list
    assert calls, "batched dependency analysis must still build at least one prompt"
    sent = json.loads(calls[0].kwargs["rules_json"])
    assert sent[0]["condition_predicates"], "v2 predicates must reach the within-batch prompt"


def test_batched_cross_batch_dependency_prompt_carries_v2_structure():
    optimizer = _optimizer()
    optimizer.config.get_optimizer_batch_size.return_value = 1
    optimizer.config.get_optimizer_max_cross_batch_pairs = MagicMock(return_value=20)

    rules = [_v2_rule("R2"), _v2_rule("R3"), _v2_rule("R4")]
    optimizer._analyze_dependencies_batched(rules, batch_size=1)

    # Every format_prompt call in this run — within-batch and cross-batch —
    # must carry v2 structure; none may have silently fallen back to legacy
    # fields the rules don't have.
    for call in optimizer.prompt_manager.format_prompt.call_args_list:
        sent = json.loads(call.kwargs["rules_json"])
        for entry in sent:
            assert "conditions" not in entry
            assert entry.get("condition_predicates") or entry.get("outcomes")
