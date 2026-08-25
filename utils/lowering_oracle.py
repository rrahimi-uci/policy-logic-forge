"""Independent fixture/oracle harness for the v2-to-LExec lowering gate.

The expected projections live in a checked-in JSON fixture and are authored
without importing lowering helpers.  This module only invokes the public
``lower_graph`` API, projects observable IR semantics, and applies declared
input mutations.  A mutation score therefore measures whether changes that
should alter semantics are detected by the oracle suite.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from utils.lexec_ir import lower_graph


FIXTURE_VERSION = "lowering-oracle/1"


def load_fixture(path: str | Path) -> dict[str, Any]:
    root = Path(path)
    fixture_path = root / "cases.json" if root.is_dir() else root
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    if fixture.get("fixture_version") != FIXTURE_VERSION:
        raise ValueError(f"unsupported lowering oracle fixture version: {fixture.get('fixture_version')!r}")
    if not isinstance(fixture.get("cases"), list) or not isinstance(fixture.get("mutations"), list):
        raise ValueError("lowering oracle fixture requires cases and mutations arrays")
    return fixture


def _projection(ir: Mapping[str, Any]) -> dict[str, Any]:
    rules = ir.get("rules") if isinstance(ir.get("rules"), list) else []
    refusals = ir.get("refusals") if isinstance(ir.get("refusals"), list) else []
    if rules and refusals:
        return {"status": "invalid_mixed_result"}
    if len(rules) == 1:
        rule = _without_provenance(rules[0])
        return {
            "status": "compiled",
            "rule": {
                "id": rule["id"],
                "scope": rule["scope"],
                "condition": rule["condition"],
                "exceptions": rule["exceptions"],
                "effects": rule["effects"],
            },
        }
    if len(refusals) == 1:
        refusal = refusals[0]
        return {
            "status": "refused",
            "refusal": {
                "rule_id": refusal["rule_id"],
                "code": refusal["code"],
                "construct": refusal["construct"],
                "detail": refusal["detail"],
                "requires_review": refusal["requires_review"],
            },
        }
    return {"status": "invalid_result", "rule_count": len(rules), "refusal_count": len(refusals)}


def _without_provenance(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _without_provenance(item) for key, item in value.items() if key != "provenance"}
    if isinstance(value, list):
        return [_without_provenance(item) for item in value]
    return value


def _set_path(value: Any, path: str, replacement: Any, *, remove: bool = False) -> None:
    parts = path.split(".")
    current = value
    for part in parts[:-1]:
        current = current[int(part)] if isinstance(current, list) else current[part]
    leaf = parts[-1]
    if isinstance(current, list):
        index = int(leaf)
        if remove:
            current.pop(index)
        else:
            current[index] = replacement
    elif remove:
        current.pop(leaf, None)
    else:
        current[leaf] = replacement


def _case_input(case: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    raw = case.get("input")
    if not isinstance(raw, Mapping):
        raise ValueError(f"case {case.get('id')!r} has no input object")
    source_sha256 = str(case.get("source_sha256") or "d" * 64)
    return copy.deepcopy(dict(raw)), source_sha256


def run_oracle(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Run all frozen cases and mutations and return a deterministic report."""

    case_results: list[dict[str, Any]] = []
    by_id: dict[str, Mapping[str, Any]] = {}
    for case in fixture["cases"]:
        case_id = str(case["id"])
        if case_id in by_id:
            raise ValueError(f"duplicate oracle case id: {case_id}")
        by_id[case_id] = case
        raw, source_sha256 = _case_input(case)
        actual = _projection(lower_graph([raw], source_sha256=source_sha256))
        expected = case.get("expected")
        passed = actual == expected
        case_results.append({"id": case_id, "passed": passed, "actual": actual if not passed else None})

    mutation_results: list[dict[str, Any]] = []
    for mutation in fixture["mutations"]:
        mutation_id = str(mutation["id"])
        base_id = str(mutation["base_case"])
        if base_id not in by_id:
            raise ValueError(f"mutation {mutation_id!r} references unknown case {base_id!r}")
        raw, source_sha256 = _case_input(by_id[base_id])
        baseline = _projection(lower_graph([copy.deepcopy(raw)], source_sha256=source_sha256))
        _set_path(raw, str(mutation["path"]), mutation.get("value"), remove=bool(mutation.get("remove")))
        mutated = _projection(lower_graph([raw], source_sha256=source_sha256))
        killed = mutated != baseline
        mutation_results.append({"id": mutation_id, "killed": killed, "baseline": baseline if not killed else None, "mutated": mutated if not killed else None})

    passed_cases = sum(1 for result in case_results if result["passed"])
    killed_mutations = sum(1 for result in mutation_results if result["killed"])
    return {
        "fixture_version": FIXTURE_VERSION,
        "status": "fixture_only",
        "claim_boundary": "Frozen provider-free expected projections and mutations only; this is not a corpus-level lowering accuracy estimate.",
        "case_count": len(case_results),
        "cases_passed": passed_cases,
        "mutation_count": len(mutation_results),
        "mutations_killed": killed_mutations,
        "mutation_score": killed_mutations / len(mutation_results) if mutation_results else 0.0,
        "failed_cases": [result["id"] for result in case_results if not result["passed"]],
        "survived_mutations": [result["id"] for result in mutation_results if not result["killed"]],
    }
