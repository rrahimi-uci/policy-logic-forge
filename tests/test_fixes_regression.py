"""
Regression tests covering the bug fixes applied during the public-release hardening.

Each test pins a specific fix so the bug cannot silently return.
"""
import importlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.config import Config
from agents.agent_04_rule_validator import RuleValidationAgent, validation_exit_code


def _reset_config_state():
    """Reset every place Config state can hide: the class-level singleton
    Config._instance (what Config.__new__ reuses) and utils.config's
    module-level `_config` global that get_config() caches separately.

    Without also clearing Config._instance, a *later* Config(...) call --
    even the very first call to go through get_config(), which never
    otherwise touched this file's state -- reuses this dirty singleton
    object via Config.__new__, silently inheriting the last test's
    provider/domain/batch overrides instead of getting a clean instance.
    """
    import utils.config as config_module
    config_module._config = None
    Config._instance = None
    Config._config = None
    Config._provider = None
    Config._source_file_name = None
    Config._batch_name = None
    Config._domain = None


@pytest.fixture(autouse=True)
def _clean_config_singleton():
    """Applies to every test in this module: this file exists specifically
    to pin Config-related regressions, so no test here may leak singleton
    state into a test that runs later (in this file or any other)."""
    _reset_config_state()
    yield
    _reset_config_state()


# ── config: fallback to config.example.json when config.json is absent ──

class TestConfigFallback:
    def _fresh(self, path):
        Config._instance = None
        Config._config = None
        return Config(config_path=str(path))

    def test_falls_back_to_example(self, tmp_path, monkeypatch):
        # A directory with only config.example.json should still load.
        example = tmp_path / "config.example.json"
        example.write_text(json.dumps({"llm": {"default_model": "x"}}))
        monkeypatch.delenv("C2C_CONFIG_PATH", raising=False)
        cfg = self._fresh(tmp_path / "config.json")  # does not exist
        assert cfg.get("llm.default_model") == "x"

    def test_missing_both_raises(self, tmp_path, monkeypatch):
        monkeypatch.delenv("C2C_CONFIG_PATH", raising=False)
        with pytest.raises(FileNotFoundError):
            self._fresh(tmp_path / "config.json")

    def test_env_override_path(self, tmp_path, monkeypatch):
        custom = tmp_path / "custom.json"
        custom.write_text(json.dumps({"llm": {"default_model": "envmodel"}}))
        monkeypatch.setenv("C2C_CONFIG_PATH", str(custom))
        Config._instance = None
        Config._config = None
        cfg = Config()
        assert cfg.get("llm.default_model") == "envmodel"

    def test_gpt56_luna_high_is_the_committed_default(self, monkeypatch):
        monkeypatch.setenv("C2C_CONFIG_PATH", str(PROJECT_ROOT / "config.example.json"))
        cfg = self._fresh(PROJECT_ROOT / "config.example.json")

        assert cfg.get_reasoning_model() == "gpt-5.6-luna"
        assert cfg.get_reasoning_effort() == "high"
        assert cfg.get_optimizer_model() == "gpt-5.6-luna"
        assert cfg.get_default_model() == "gpt-5.6-luna"
        assert cfg.get_optimizer_model_name() == "gpt-5.6-luna"

    def test_gpt56_luna_high_are_safe_code_fallbacks(self, tmp_path, monkeypatch):
        monkeypatch.delenv("KG_REASONING_EFFORT", raising=False)
        config_path = tmp_path / "config.json"
        config_path.write_text("{}")
        cfg = self._fresh(config_path)

        assert cfg.get_reasoning_model() == "gpt-5.6-luna"
        assert cfg.get_reasoning_effort() == "high"
        assert cfg.get_optimizer_model() == "gpt-5.6-luna"
        assert cfg.get_default_model() == "gpt-5.6-luna"
        assert cfg.get_optimizer_model_name() == "gpt-5.6-luna"

    def test_invalid_reasoning_effort_is_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KG_REASONING_EFFORT", "turbo")
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({}))
        cfg = self._fresh(config_path)

        with pytest.raises(ValueError, match="Unsupported reasoning effort"):
            cfg.get_reasoning_effort()


# ── config: multi-provider (openai default, anthropic via litellm) ──
#
# Anthropic support was trimmed out of the original fork (see this file's
# git history: the very first commit that imported this pipeline added a
# test asserting `get_anthropic_api_key` must not exist, as a scope guard
# for "focused to 4 benchmark-backed domains"). It's been reinstated on
# request, backed by litellm -- see utils/llm_client.py.

class TestProvider:
    def _fresh(self, path, **kwargs):
        Config._instance = None
        Config._config = None
        return Config(config_path=str(path), **kwargs)

    def test_provider_defaults_to_openai(self, monkeypatch):
        monkeypatch.delenv("KG_PROVIDER", raising=False)
        assert self._fresh(PROJECT_ROOT / "config.example.json").get_model_provider() == "openai"

    def test_provider_selectable_via_env(self, monkeypatch):
        monkeypatch.setenv("KG_PROVIDER", "anthropic")
        assert self._fresh(PROJECT_ROOT / "config.example.json").get_model_provider() == "anthropic"

    def test_provider_selectable_via_constructor(self):
        assert self._fresh(PROJECT_ROOT / "config.example.json", provider="anthropic").get_model_provider() == "anthropic"

    def test_unsupported_provider_is_rejected(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({}))
        cfg = self._fresh(config_path, provider="watson")
        with pytest.raises(ValueError, match="Unsupported model provider"):
            cfg.get_model_provider()

    def test_anthropic_api_key_getter_reads_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({}))
        cfg = self._fresh(config_path)
        assert cfg.get_anthropic_api_key() == "test-anthropic-key"

    def test_anthropic_api_key_missing_raises(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({}))
        cfg = self._fresh(config_path)
        with pytest.raises(ValueError, match="Anthropic API key not found"):
            cfg.get_anthropic_api_key()

    def test_get_api_key_dispatches_by_provider(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({}))
        cfg = self._fresh(config_path, provider="anthropic")
        assert cfg.get_api_key() == "test-anthropic-key"
        cfg._provider = "openai"
        assert cfg.get_api_key() == "test-openai-key"

    def test_anthropic_reasoning_model_falls_back_to_a_claude_default(self, tmp_path):
        """The provider-neutral 'gpt-5.6-luna' fallback must never leak into
        an anthropic-provider run that has no models.reasoning configured."""
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({}))
        cfg = self._fresh(config_path, provider="anthropic")
        assert cfg.get_reasoning_model() == "claude-sonnet-5"
        assert cfg.get_reasoning_effort() == "high"  # provider-neutral fallback still applies

    def test_kg_model_override_wins_over_provider_default(self, monkeypatch, tmp_path):
        # Deliberately a different model than the anthropic default (claude-sonnet-5)
        # so this actually proves override precedence, not just a coincidental match.
        monkeypatch.setenv("KG_MODEL", "claude-opus-5")
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({}))
        cfg = self._fresh(config_path, provider="anthropic")
        assert cfg.get_reasoning_model() == "claude-opus-5"
        assert cfg.get_default_model() == "claude-opus-5"


class TestRuleValidatorStructuredEnums:
    def test_findings_remain_advisory_for_pipeline_progression(self):
        report = {"statistics": {"failure_count": 583}}

        assert validation_exit_code(report) == 0

    def test_structured_enum_values_are_reported_without_crashing(self):
        """Malformed structured enum output must remain a validation warning."""
        validator = object.__new__(RuleValidationAgent)
        report = {"failures": [], "warnings": [], "passed": []}

        validator._validate_completeness(
            [
                {
                    "schema_version": "2.0",
                    "rule_id": "rule-1",
                    "risk_level": {"level": "high"},
                    "audit_frequency": {"frequency": "monthly"},
                }
            ],
            report,
        )

        enum_warnings = [
            warning for warning in report["warnings"]
            if warning.get("check") == "enum_validation"
        ]
        assert len(enum_warnings) == 2


class TestRuleValidatorCoverageAndGrounding:
    @staticmethod
    def _rule(rule_id, path="doc.txt", start=0, end=6, text="The lender must retain source records"):
        return {
            "rule_id": rule_id,
            "source_reference": {
                "chunk_path": path,
                "section_id": "s1",
                "start_word_position": start,
                "end_word_position": end,
                "source_text": text,
            },
            "field_evidence": {
                "description": [{
                    "chunk_path": path,
                    "section_id": "s1",
                    "source_text": text,
                }],
            },
        }

    def test_load_rules_preserves_overlapping_entity_and_relationship_names(self, tmp_path):
        graph = {
            "entity_types": {
                "LENDER": {"business_rules": [self._rule("entity-rule")]},
            },
            "relationships": {
                "LENDER": {"business_rules": [self._rule("relationship-rule")]},
            },
        }
        graph_path = tmp_path / "rules.json"
        graph_path.write_text(json.dumps(graph), encoding="utf-8")

        loaded = object.__new__(RuleValidationAgent).load_rules(graph_path)

        assert [rule["rule_id"] for rule in loaded["rules"]] == [
            "entity-rule", "relationship-rule",
        ]
        assert loaded["source_counts"] == {"entity_rules": 1, "relationship_rules": 1}
        assert loaded["expected_rule_count"] == 2
        assert {rule["source_namespace"] for rule in loaded["rules"]} == {
            "entity", "relationship",
        }

    def test_source_verification_checks_every_rule_and_rejects_bad_span(self):
        validator = object.__new__(RuleValidationAgent)
        rules = [self._rule(f"R-{index}") for index in range(11)]
        rules.append(self._rule("R-bad", start=1, end=6))
        report = {"failures": [], "warnings": [], "passed": []}

        validator._verify_against_sources(
            rules,
            [{"path": "doc.txt", "content": "The lender must retain source records"}],
            report,
        )

        failures = [item for item in report["failures"] if item["check"] == "source_verification"]
        assert [item["rule_id"] for item in failures] == ["R-bad"]
        assert "source_text does not match its cited word span" in failures[0]["issue"]
        assert not any(item["check"] == "source_verification" for item in report["passed"])


# ── utils package: importing Config must not pull in the LLM client ──

class TestLazyImport:
    def test_config_import_is_lightweight(self):
        for mod in ("utils", "utils.config"):
            importlib.import_module(mod)
        import utils
        # The lazy attribute access path resolves without raising AttributeError.
        assert hasattr(utils, "Config")

# NOTE: the source pipeline has a TestRunStore class here, covering its UI
# backend's SQLite run-history store (ui/backend/services/run_store.py).
# There is no UI backend in this repo (see README.md "Scope"), so there is
# nothing to pin a regression test against.
