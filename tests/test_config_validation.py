"""Configuration contract tests for the default pipeline profile."""

import json
from pathlib import Path

from scripts.validate_config import validate_config, validate_file


ROOT = Path(__file__).resolve().parent.parent


def test_checked_in_example_has_the_expected_model_and_pipeline_profile() -> None:
    assert validate_file(ROOT / "config.example.json") == []


def test_validator_rejects_model_or_effort_drift() -> None:
    config = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    config["openai"]["models"]["reasoning"] = "gpt-5.2"
    config["openai"]["models"]["reasoning_effort"] = "xhigh"

    errors = validate_config(config, source="fixture")

    assert any("openai.models.reasoning must be 'gpt-5.6-luna'" in error for error in errors)
    assert any("reasoning_effort must be 'high'" in error for error in errors)


def test_validator_rejects_invalid_concurrency_order() -> None:
    config = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    performance = config["pipeline"]["performance"]
    performance["global_llm_concurrency_min"] = 20
    performance["global_llm_concurrency_initial"] = 12
    performance["global_llm_concurrency_max"] = 16

    errors = validate_config(config, source="fixture")

    assert any("global_llm_concurrency_min" in error for error in errors)


def test_default_profile_is_parallel_but_has_bounded_stall_recovery() -> None:
    config = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    performance = config["pipeline"]["performance"]

    assert config["pipeline"]["max_workers"] == 40
    assert performance["llm_concurrency"] == 16
    assert performance["remediation_llm_concurrency"] == 32
    assert performance["grounding_llm_concurrency"] == 32
    assert config["openai"]["rate_limiting"]["timeout"] == 300
    assert performance["global_llm_lease_seconds"] == 300
    assert performance["llm_watchdog_margin"] == 30
    assert performance["batch_connection_backoff_seconds"] == 10
