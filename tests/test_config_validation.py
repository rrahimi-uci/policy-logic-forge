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
