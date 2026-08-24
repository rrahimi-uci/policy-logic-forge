"""Regression tests for verified agent-pipeline correctness fixes.

  Agent 5 (KnowledgeGraphOptimizer):
    The Step-3 dependency-merge loop read dep["source_rule_id"],
    dep["dependency_type"], dep["rationale"] via raw subscript OUTSIDE the
    per-batch try/except. A single LLM-returned dependency object missing one
    of those keys raised KeyError and aborted the whole optimization run.

  Agent 8 (SemanticRuleMatcher):
    Batch verdicts were attached to rule pairs by array position and any
    short/truncated array (len(results) < len(batch)) discarded ALL verdicts,
    falling back to UNRELATED for the entire batch. Verdicts must align by
    pair_id and partial results must be preserved.
"""
import sys
from pathlib import Path

import allure
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── Agent 5: malformed dependency must not crash the merge ─────────────────
@allure.feature("Pipeline agent robustness")
@allure.story("Agent 5 dependency merge tolerates missing keys")
class TestAgent5DependencyMissingKeys:
    @allure.title("A dependency missing keys is skipped, not fatal")
    def test_missing_keys_does_not_crash(self, monkeypatch):
        from agents import agent_06_knowledge_graph_optimizer as a5

        # Build the optimizer without touching real config/LLM construction.
        opt = a5.KnowledgeGraphOptimizer.__new__(a5.KnowledgeGraphOptimizer)
        opt.max_workers = 1
        opt.model = "test-model"

        rules = [
            {"rule_id": "R1", "rule_type": "x"},
            {"rule_id": "R2", "rule_type": "y"},
        ]

        # One well-formed dependency and one missing dependency_type/rationale,
        # plus a junk entry — all of which previously raised KeyError downstream.
        deps = [
            {"source_rule_id": "R1", "target_rule_id": "R2",
             "dependency_type": "prerequisite", "rationale": "R2 needs R1"},
            {"source_rule_id": "R1", "target_rule_id": "R2"},  # missing keys
            {"source_rule_id": "R1"},                          # missing target
            "not-a-dict",                                       # junk
        ]

        # Replace the LLM-driven within-batch step with our crafted deps, and
        # force a single batch (no cross-batch pairs) by patching ThreadPoolExecutor map.
        # Simplest: monkeypatch the within-batch closure indirectly by stubbing
        # the client call. Instead, drive _analyze_dependencies_batched with a
        # batch_size that yields exactly one batch and stub the parse path.
        class _FakeMsg:
            content = '{"dependencies": []}'

        class _FakeChoice:
            message = _FakeMsg()

        class _FakeResp:
            choices = [_FakeChoice()]

        class _FakeClient:
            def chat_completion(self, **kwargs):
                return _FakeResp()

        opt.client = _FakeClient()
        opt.config = _DummyConfig()
        opt.reasoning_effort = "medium"

        class _PM:
            def format_prompt(self, *a, **k):
                return "prompt"

        opt.prompt_manager = _PM()

        # Make _parse_json_response return our crafted deps so they flow into
        # the Step-3 merge that previously crashed.
        monkeypatch.setattr(opt, "_parse_json_response", lambda _c: {"dependencies": deps})

        # batch_size >= len(rules) → exactly one batch, zero cross-batch pairs.
        result_rules, metadata = opt._analyze_dependencies_batched(rules, batch_size=10)

        # The well-formed dependency must be applied to R2.
        r2 = next(r for r in result_rules if r["rule_id"] == "R2")
        assert "dependencies" in r2
        assert r2["dependencies"][0]["depends_on_rule"] == "R1"
        assert r2["dependencies"][0]["dependency_type"] == "prerequisite"
        # The malformed/junk entries were skipped, not fatal.
        assert metadata["rules_with_dependencies"] == 1


class _DummyConfig:
    def get_optimizer_description_truncation_length(self):
        return 500

    def get_optimizer_batched_temperature(self):
        return 0.2

    def get_optimizer_batched_max_tokens(self):
        return 1000

    def get_optimizer_cross_batch_temperature(self):
        return 0.2

    def get_optimizer_cross_batch_max_tokens(self):
        return 1000


# NOTE: the source pipeline has TestAgent8BatchAlignment here, covering
# agent_8_semantic_rule_matcher.py's batch-verdict alignment by pair_id. Agent
# 8 is part of the cross-graph comparison pipeline (agents 7-10), which this
# repo doesn't ship — see README.md "Scope".
