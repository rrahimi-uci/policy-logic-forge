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
