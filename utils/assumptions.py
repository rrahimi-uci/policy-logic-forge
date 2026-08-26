"""Typed, provenance-bound assumption analysis.

An assumption is only admissible when its source support is explicit.  Solver
validity is reported separately from human/source acceptability, and a set of
assumptions is rejected when it is inconsistent or vacuous.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from utils.smt import query_satisfiable


class AssumptionValidationError(ValueError):
    """Raised for malformed or unproven assumption records."""


def validate_assumption(assumption: Mapping[str, Any]) -> None:
    if not isinstance(assumption, Mapping):
        raise AssumptionValidationError("assumption must be an object")
    if not isinstance(assumption.get("id"), str) or not assumption["id"].strip():
        raise AssumptionValidationError("assumption.id must be non-empty")
    if not isinstance(assumption.get("formula"), Mapping):
        raise AssumptionValidationError("assumption.formula must be an object")
    provenance = assumption.get("provenance")
    if not isinstance(provenance, Sequence) or isinstance(provenance, (str, bytes)) or not provenance:
        raise AssumptionValidationError("assumption.provenance must be a non-empty array")
    for span in provenance:
        if not isinstance(span, Mapping) or not isinstance(span.get("source_sha256"), str) or not span["source_sha256"]:
            raise AssumptionValidationError("each assumption provenance span requires source_sha256")


def analyze_assumption(assumption: Mapping[str, Any], symbols: Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    validate_assumption(assumption)
    result = query_satisfiable(assumption["formula"], symbols)
    valid = result["status"] == "sat"
    return {"id": assumption["id"], "solver_status": result["status"],
            "solver_valid": valid, "witness": result.get("witness"),
            "source_supported": True, "human_acceptability": "unreviewed",
            "claimable": False if result["status"] in {"unknown", "timeout"} else valid}


def analyze_set(assumptions: Sequence[Mapping[str, Any]], symbols: Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if not assumptions:
        raise AssumptionValidationError("assumptions must be non-empty")
    analyses = [analyze_assumption(item, symbols) for item in assumptions]
    formulas = [item["formula"] for item in assumptions]
    conjunction = {"op": "and", "args": formulas}
    consistency = query_satisfiable(conjunction, symbols)
    return {"schema_version": "assumptions/1.0", "assumptions": analyses,
            "set_solver_status": consistency["status"], "set_witness": consistency.get("witness"),
            "consistent": consistency["status"] == "sat", "vacuous": consistency["status"] == "unsat",
            "claimable": consistency["status"] == "sat" and all(item["claimable"] for item in analyses)}
