"""Contract tests for the machine-readable NeurIPS execution plan."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.validate_neurips_plan import (
    PLAN,
    REGISTRY,
    load_registry,
    render_summary,
    validate_embedded_summary,
    validate_ir_schema,
    validate_registry,
)


ROOT = Path(__file__).resolve().parent.parent


def test_repository_registry_and_embedded_summary_are_valid() -> None:
    registry = load_registry()

    assert validate_registry(registry) == []
    assert validate_ir_schema() == []
    assert validate_embedded_summary(registry) == []
    assert REGISTRY == ROOT / "plan" / "tasks.json"
    assert PLAN == ROOT / "plan" / "neurips-plan-2027.md"
    assert (ROOT / "plan" / "neurIips-proposal-2027.md").is_file()
    assert not (ROOT / "neurips-plan-2027.md").exists()
    assert not (ROOT / "neurIips-proposal-2027.md").exists()


def test_generated_summary_has_frozen_scope_totals_and_ready_queue() -> None:
    summary = render_summary(load_registry())

    assert "| `minimum_paper` | 125 | 10 | 115 |" in summary
    assert "| `second_domain` | 151 | 10 | 141 |" in summary
    assert "| `full_programme` | 171 | 10 | 161 |" in summary
    assert "| `minimum_plus_optional_replication` | 129 | 10 | 119 |" in summary
    assert "`PIPE-2B`, `PIPE-4`, `IR-2`, `BENCH-1`, `A1B`, `A3`" in summary


def test_cycle_is_rejected() -> None:
    registry = copy.deepcopy(load_registry())
    tasks = {task["id"]: task for task in registry["tasks"]}
    tasks["PIPE-1"]["depends_on"] = ["PIPE-2"]

    errors = validate_registry(registry)

    assert any("dependency cycle: PIPE-1 -> PIPE-2 -> PIPE-1" in error for error in errors)


def test_missing_dependency_is_rejected() -> None:
    registry = copy.deepcopy(load_registry())
    registry["tasks"][0]["depends_on"] = ["DOES-NOT-EXIST"]

    errors = validate_registry(registry)

    assert any("missing dependency DOES-NOT-EXIST" in error for error in errors)


def test_task_cannot_appear_in_two_base_scopes() -> None:
    registry = copy.deepcopy(load_registry())
    registry["scopes"]["optional_fresh_replication"].append("PIPE-1")

    errors = validate_registry(registry)

    assert "task PIPE-1 appears in multiple base scopes" in errors


def test_completed_task_requires_existing_evidence() -> None:
    registry = copy.deepcopy(load_registry())
    tasks = {task["id"]: task for task in registry["tasks"]}
    tasks["PIPE-1"]["evidence"] = ["does/not/exist"]

    errors = validate_registry(registry)

    assert "PIPE-1: evidence does not exist: does/not/exist" in errors


def test_ir_schema_preserves_core_semantic_boundaries() -> None:
    schema = json.loads((ROOT / "plan" / "lexec-ir-v1.schema.json").read_text())
    definitions = schema["$defs"]

    assert schema["properties"]["schema_version"] == {"const": "lexec-ir/1.0"}
    assert {
        "schema_version",
        "document_unit",
        "semantics",
        "symbols",
        "rules",
        "tables",
        "refusals",
    } <= set(schema["required"])
    assert "modality" in definitions["effect"]["required"]
    assert definitions["rule"]["properties"]["exceptions"]["items"] == {
        "$ref": "#/$defs/exception"
    }
    assert definitions["exception"]["properties"]["provenance"]["minItems"] == 1
    assert definitions["refusal"]["properties"]["requires_review"] == {"const": True}
    assert definitions["semantics"]["properties"]["exception_reading"]["enum"][0] == "unset"
    assert definitions["scope"]["properties"]["predicate"] != definitions["rule"]["properties"]["condition"]
