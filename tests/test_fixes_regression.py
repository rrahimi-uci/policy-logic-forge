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


# ── config: OpenAI-only provider ──

class TestProvider:
    def test_provider_is_openai(self, monkeypatch):
        monkeypatch.setenv("C2C_CONFIG_PATH", str(PROJECT_ROOT / "config.example.json"))
        Config._instance = None
        Config._config = None
        assert Config().get_model_provider() == "openai"

    def test_no_anthropic_key_getter(self):
        # Anthropic support was removed; the getter must be gone.
        assert not hasattr(Config, "get_anthropic_api_key")


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
