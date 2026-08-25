#!/usr/bin/env python3
"""Validate and operate the machine-readable NeurIPS 2027 execution plan.

Examples:

    .venv/bin/python scripts/validate_neurips_plan.py --check
    .venv/bin/python scripts/validate_neurips_plan.py --ready
    .venv/bin/python scripts/validate_neurips_plan.py --show IR-1
    .venv/bin/python scripts/validate_neurips_plan.py --run-done

The validator is deliberately standard-library only. It validates structure,
dependency closure, cycles, status/evidence contracts, acceptance commands,
scope totals, and the generated summary embedded in neurips-plan-2027.md.
It never runs planned paid/network tasks automatically.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "plan" / "tasks.json"
PLAN = ROOT / "neurips-plan-2027.md"
IR_SCHEMA = ROOT / "plan" / "lexec-ir-v1.schema.json"
SUMMARY_START = "<!-- GENERATED_TASK_SUMMARY_START -->"
SUMMARY_END = "<!-- GENERATED_TASK_SUMMARY_END -->"
PHASE_ORDER = ("G0", "A", "J", "G2", "G3", "G4", "G5", "Writing")


class PlanValidationError(ValueError):
    """Raised when the execution plan violates its own contract."""


def load_registry(path: Path = REGISTRY) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def task_index(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {task["id"]: task for task in registry["tasks"]}


def _require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _cycle_errors(tasks: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visited:
            return
        if task_id in visiting:
            start = visiting.index(task_id)
            errors.append("dependency cycle: " + " -> ".join(visiting[start:] + [task_id]))
            return
        visiting.append(task_id)
        for dependency in tasks[task_id]["depends_on"]:
            if dependency in tasks:
                visit(dependency)
        visiting.pop()
        visited.add(task_id)

    for task_id in tasks:
        visit(task_id)
    return errors


def _scope_sets(registry: dict[str, Any]) -> dict[str, set[str]]:
    scopes = registry["scopes"]
    minimum = set(scopes["minimum_paper"])
    second = minimum | set(scopes["second_domain"])
    full = second | set(scopes["full_programme"])
    optional = minimum | set(scopes["optional_fresh_replication"])
    return {
        "minimum_paper": minimum,
        "second_domain": second,
        "full_programme": full,
        "minimum_plus_optional_replication": optional,
    }


def validate_registry(registry: dict[str, Any], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    _require(registry.get("schema_version") == "1.0", "schema_version must be 1.0", errors)
    _require(isinstance(registry.get("tasks"), list) and registry["tasks"], "tasks must be a non-empty list", errors)
    _require(isinstance(registry.get("scopes"), dict), "scopes must be an object", errors)
    if errors:
        return errors

    tasks_list = registry["tasks"]
    ids = [task.get("id") for task in tasks_list]
    duplicates = sorted(task_id for task_id, count in Counter(ids).items() if count > 1)
    _require(not duplicates, f"duplicate task ids: {duplicates}", errors)
    tasks = task_index(registry)
    allowed_statuses = set(registry.get("status_values", []))

    for task in tasks_list:
        task_id = task.get("id", "<missing>")
        for field in (
            "id", "title", "phase", "track", "status", "effort_pd",
            "depends_on", "acceptance", "evidence", "claim_boundary",
        ):
            _require(field in task, f"{task_id}: missing {field}", errors)
        if any(field not in task for field in ("status", "effort_pd", "depends_on", "acceptance")):
            continue
        _require(task["status"] in allowed_statuses, f"{task_id}: invalid status {task['status']!r}", errors)
        _require(isinstance(task["effort_pd"], (int, float)) and task["effort_pd"] >= 0,
                 f"{task_id}: effort_pd must be non-negative", errors)
        _require(isinstance(task["depends_on"], list), f"{task_id}: depends_on must be a list", errors)
        for dependency in task["depends_on"]:
            _require(dependency in tasks, f"{task_id}: missing dependency {dependency}", errors)
            _require(dependency != task_id, f"{task_id}: self dependency", errors)

        acceptance = task["acceptance"]
        commands = acceptance.get("commands", []) if isinstance(acceptance, dict) else []
        artifacts = acceptance.get("artifacts", []) if isinstance(acceptance, dict) else []
        _require(bool(commands), f"{task_id}: at least one executable acceptance command is required", errors)
        _require(bool(artifacts), f"{task_id}: at least one acceptance artifact is required", errors)
        for command in commands:
            _require(
                isinstance(command, list) and bool(command) and all(isinstance(part, str) and part for part in command),
                f"{task_id}: acceptance commands must be non-empty argv arrays",
                errors,
            )
        for artifact in artifacts:
            _require(isinstance(artifact, str) and bool(artifact), f"{task_id}: invalid artifact path", errors)

        if task["status"] in {"done", "partial"}:
            _require(bool(task.get("evidence")), f"{task_id}: {task['status']} task requires evidence", errors)
            for evidence in task.get("evidence", []):
                _require((root / evidence).exists(), f"{task_id}: evidence does not exist: {evidence}", errors)
        if task["status"] == "done":
            for artifact in artifacts:
                _require((root / artifact).exists(), f"{task_id}: completed artifact does not exist: {artifact}", errors)
            for dependency in task["depends_on"]:
                if dependency in tasks:
                    _require(tasks[dependency]["status"] == "done",
                             f"{task_id}: done task depends on non-done {dependency}", errors)

    errors.extend(_cycle_errors(tasks))

    listed_in_scopes: set[str] = set()
    for scope_name, task_ids in registry["scopes"].items():
        _require(isinstance(task_ids, list), f"scope {scope_name}: must be a list", errors)
        for task_id in task_ids:
            _require(task_id in tasks, f"scope {scope_name}: unknown task {task_id}", errors)
            _require(task_id not in listed_in_scopes, f"task {task_id} appears in multiple base scopes", errors)
            listed_in_scopes.add(task_id)
    _require(listed_in_scopes == set(tasks),
             f"scope coverage mismatch: missing={sorted(set(tasks)-listed_in_scopes)}, extra={sorted(listed_in_scopes-set(tasks))}",
             errors)

    for scope_name, task_ids in _scope_sets(registry).items():
        for task_id in task_ids:
            missing = set(tasks[task_id]["depends_on"]) - task_ids
            _require(not missing, f"scope {scope_name}: {task_id} misses dependencies {sorted(missing)}", errors)

    return errors


def validate_ir_schema(path: Path = IR_SCHEMA) -> list[str]:
    """Check the IR schema's internal references and fail-closed invariants."""
    errors: list[str] = []
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"IR schema cannot be loaded: {exc}"]

    definitions = schema.get("$defs", {})
    _require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
             "IR schema must use JSON Schema draft 2020-12", errors)
    _require(schema.get("properties", {}).get("schema_version") == {"const": "lexec-ir/1.0"},
             "IR schema must pin schema_version to lexec-ir/1.0", errors)

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            reference = node.get("$ref")
            if reference is not None:
                prefix = "#/$defs/"
                _require(isinstance(reference, str) and reference.startswith(prefix),
                         f"IR schema has unsupported reference: {reference!r}", errors)
                if isinstance(reference, str) and reference.startswith(prefix):
                    _require(reference[len(prefix):] in definitions,
                             f"IR schema reference does not resolve: {reference}", errors)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    effect = definitions.get("effect", {})
    refusal = definitions.get("refusal", {})
    semantics = definitions.get("semantics", {})
    _require("modality" in effect.get("required", []),
             "IR effects must require modality", errors)
    _require(refusal.get("properties", {}).get("requires_review") == {"const": True},
             "IR refusals must require requires_review=true", errors)
    exception_values = semantics.get("properties", {}).get("exception_reading", {}).get("enum", [])
    _require("unset" in exception_values,
             "IR exception semantics must support an unset fail-closed state", errors)
    return errors


def _format_pd(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


def render_summary(registry: dict[str, Any]) -> str:
    tasks = task_index(registry)
    by_phase: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in registry["tasks"]:
        by_phase[task["phase"]].append(task)

    lines = [
        SUMMARY_START,
        "| Phase | Tasks | Total pd | Done pd | Status |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for phase in PHASE_ORDER:
        phase_tasks = by_phase.get(phase, [])
        total = sum(float(task["effort_pd"]) for task in phase_tasks)
        done = sum(float(task["effort_pd"]) for task in phase_tasks if task["status"] == "done")
        counts = Counter(task["status"] for task in phase_tasks)
        status_text = ", ".join(f"{name}={counts[name]}" for name in registry["status_values"] if counts[name])
        lines.append(f"| {phase} | {len(phase_tasks)} | {_format_pd(total)} | {_format_pd(done)} | {status_text} |")

    lines.extend([
        "",
        "| Scope | Included pd | Done pd | Remaining pd |",
        "| --- | ---: | ---: | ---: |",
    ])
    for scope_name, ids in _scope_sets(registry).items():
        total = sum(float(tasks[task_id]["effort_pd"]) for task_id in ids)
        done = sum(float(tasks[task_id]["effort_pd"]) for task_id in ids if tasks[task_id]["status"] == "done")
        lines.append(f"| `{scope_name}` | {_format_pd(total)} | {_format_pd(done)} | {_format_pd(total-done)} |")

    ready = [
        task["id"] for task in registry["tasks"]
        if task["status"] in {"planned", "partial"}
        and all(tasks[dependency]["status"] == "done" for dependency in task["depends_on"])
    ]
    lines.extend([
        "",
        f"**Ready now:** {', '.join(f'`{task_id}`' for task_id in ready) if ready else 'none'}.",
        "",
        f"Generated from [`plan/tasks.json`](plan/tasks.json) by "
        "`scripts/validate_neurips_plan.py`; manual edits to this block fail CI.",
        SUMMARY_END,
    ])
    return "\n".join(lines)


def validate_embedded_summary(registry: dict[str, Any], plan_path: Path = PLAN) -> list[str]:
    text = plan_path.read_text(encoding="utf-8")
    if SUMMARY_START not in text or SUMMARY_END not in text:
        return ["plan is missing generated summary markers"]
    start = text.index(SUMMARY_START)
    end = text.index(SUMMARY_END, start) + len(SUMMARY_END)
    actual = text[start:end]
    expected = render_summary(registry)
    return [] if actual == expected else ["embedded generated summary is stale; render it with --summary and update via reviewable patch"]


def run_commands(task: dict[str, Any]) -> int:
    for command in task["acceptance"]["commands"]:
        print(f"[{task['id']}] $ {' '.join(command)}", flush=True)
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode:
            print(f"[{task['id']}] failed with exit {completed.returncode}", file=sys.stderr)
            return completed.returncode
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Validate registry and embedded plan summary")
    mode.add_argument("--summary", action="store_true", help="Render the authoritative Markdown summary")
    mode.add_argument("--ready", action="store_true", help="List non-complete tasks whose dependencies are done")
    mode.add_argument("--show", metavar="TASK_ID", help="Show one task as JSON")
    mode.add_argument("--run", metavar="TASK_ID", help="Run one task's acceptance commands")
    mode.add_argument("--run-done", action="store_true", help="Run acceptance commands for every completed task")
    args = parser.parse_args()

    registry = load_registry()
    errors = validate_registry(registry)
    if args.check:
        errors.extend(validate_ir_schema())
        errors.extend(validate_embedded_summary(registry))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    tasks = task_index(registry)
    if args.check:
        print(f"Plan valid: {len(tasks)} tasks, no missing dependencies, no cycles, summary current.")
        return 0
    if args.summary:
        print(render_summary(registry))
        return 0
    if args.ready:
        for task in registry["tasks"]:
            if task["status"] in {"planned", "partial"} and all(
                tasks[dependency]["status"] == "done" for dependency in task["depends_on"]
            ):
                print(f"{task['id']}\t{task['status']}\t{task['title']}")
        return 0
    if args.show:
        if args.show not in tasks:
            print(f"Unknown task: {args.show}", file=sys.stderr)
            return 2
        print(json.dumps(tasks[args.show], indent=2))
        return 0
    if args.run:
        if args.run not in tasks:
            print(f"Unknown task: {args.run}", file=sys.stderr)
            return 2
        return run_commands(tasks[args.run])
    if args.run_done:
        for task in registry["tasks"]:
            if task["status"] == "done":
                result = run_commands(task)
                if result:
                    return result
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
