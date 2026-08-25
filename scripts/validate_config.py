#!/usr/bin/env python3
"""Validate the model and pipeline settings used by the extraction CLI.

The checked-in example is the portable source of truth.  When a local
``config.json`` exists, it is checked too so a stale ignored copy cannot make a
developer run a different model or reasoning level than CI and documentation
advertise.  API keys are never printed or required for this structural check.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent.parent
EXPECTED_MODEL = "gpt-5.6-luna"
EXPECTED_REASONING_EFFORT = "high"
ALLOWED_REASONING_EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}


def _get(config: Mapping[str, Any], path: str) -> Any:
    value: Any = config
    for key in path.split("."):
        if not isinstance(value, Mapping) or key not in value:
            return None
        value = value[key]
    return value


def _positive_number(config: Mapping[str, Any], path: str, errors: list[str]) -> None:
    value = _get(config, path)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        errors.append(f"{path} must be a positive number (got {value!r})")


def validate_config(config: Mapping[str, Any], *, source: str = "config") -> list[str]:
    """Return structural and default-policy errors for one config object."""

    errors: list[str] = []
    for path in (
        "openai.models.reasoning",
        "openai.models.optimizer",
        "llm.default_model",
        "optimizer.model",
    ):
        value = _get(config, path)
        if value != EXPECTED_MODEL:
            errors.append(f"{source}: {path} must be {EXPECTED_MODEL!r} (got {value!r})")

    effort = _get(config, "openai.models.reasoning_effort")
    if effort not in ALLOWED_REASONING_EFFORTS:
        errors.append(f"{source}: openai.models.reasoning_effort is invalid: {effort!r}")
    elif effort != EXPECTED_REASONING_EFFORT:
        errors.append(
            f"{source}: openai.models.reasoning_effort must be {EXPECTED_REASONING_EFFORT!r} (got {effort!r})"
        )

    for path in (
        "pipeline.max_workers",
        "pipeline.document_workers",
        "pipeline.performance.llm_concurrency",
        "pipeline.performance.reasoning_max_completion_tokens",
        "rules_extractor.rules_per_batch_openai",
        "rules_extractor.batch_size",
        "rules_extractor.target_words_per_batch",
        "openai.rate_limiting.timeout",
    ):
        _positive_number(config, path, errors)

    initial = _get(config, "pipeline.performance.global_llm_concurrency_initial")
    maximum = _get(config, "pipeline.performance.global_llm_concurrency_max")
    minimum = _get(config, "pipeline.performance.global_llm_concurrency_min")
    if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in (minimum, initial, maximum)):
        if not minimum <= initial <= maximum:
            errors.append(
                "pipeline.performance.global_llm_concurrency_min <= "
                "global_llm_concurrency_initial <= global_llm_concurrency_max is required"
            )

    return errors


def validate_file(path: Path) -> list[str]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"{path}: file does not exist"]
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path}: cannot parse JSON: {exc}"]
    if not isinstance(config, Mapping):
        return [f"{path}: top-level JSON value must be an object"]
    return validate_config(config, source=str(path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, action="append", help="Additional config file to validate")
    args = parser.parse_args()

    paths = [ROOT / "config.example.json"]
    local = ROOT / "config.json"
    if local.exists():
        paths.append(local)
    paths.extend(args.config or [])

    errors = [error for path in paths for error in validate_file(path)]
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"Configuration valid: {len(paths)} file(s), model={EXPECTED_MODEL}, reasoning_effort={EXPECTED_REASONING_EFFORT}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
