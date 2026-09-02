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

    assert config["pipeline"]["max_workers"] == 80
    assert config["pipeline"]["document_workers"] == 32
    assert performance["llm_concurrency"] == 16
    assert performance["reasoning_max_completion_tokens"] == 32768
    assert performance["readiness_rules_per_request"] == 8
    assert performance["readiness_max_evidence_chars"] == 12000
    assert performance["remediation_rules_per_request"] == 8
    assert performance["remediation_max_conflict_pairs"] == 5000
    assert performance["global_llm_concurrency_initial"] == 8
    assert performance["global_llm_concurrency_max"] == 16
    assert performance["global_llm_success_window"] == 3
    assert performance["readiness_llm_concurrency"] == 16
    assert performance["remediation_llm_concurrency"] == 16
    assert performance["grounding_llm_concurrency"] == 16
    assert performance["readiness_workers"] == 80
    assert performance["remediation_workers"] == 80
    assert performance["grounding_workers"] == 80
    assert performance["grounding_relationships_per_request"] == 12
    assert config["openai"]["rate_limiting"]["timeout"] == 300
    assert performance["global_llm_lease_seconds"] == 900
    assert performance["llm_watchdog_margin"] == 30
    assert performance["batch_connection_backoff_seconds"] == 10
    # A live request must not expire from the shared lease table before its
    # watchdog deadline, or it can be counted twice and recreate overload.
    watchdog_deadline = config["openai"]["rate_limiting"]["timeout"] * (
        config["openai"]["rate_limiting"]["max_retries"] + 1
    ) + performance["llm_watchdog_margin"]
    assert performance["global_llm_lease_seconds"] >= watchdog_deadline
