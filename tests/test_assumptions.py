import pytest

from utils.assumptions import AssumptionValidationError, analyze_assumption, analyze_set


def _symbols():
    return [{"id": "active", "theory": "bool", "domain": {"kind": "boolean"}}]


def _assumption(identifier, formula):
    return {"id": identifier, "formula": formula, "provenance": [{"source_sha256": "a" * 64}]}


def test_assumption_requires_provenance_and_reports_solver_status():
    assumption = _assumption("a1", {"op": "eq", "left": {"symbol": "active"}, "right": {"literal": True, "type": "bool"}})
    result = analyze_assumption(assumption, _symbols())
    assert result["solver_status"] == "sat"
    assert result["source_supported"] is True


def test_inconsistent_assumption_set_is_not_claimable():
    a = _assumption("a", {"op": "eq", "left": {"symbol": "active"}, "right": {"literal": True, "type": "bool"}})
    b = _assumption("b", {"op": "eq", "left": {"symbol": "active"}, "right": {"literal": False, "type": "bool"}})
    result = analyze_set([a, b], _symbols())
    assert result["set_solver_status"] == "unsat"
    assert result["consistent"] is False


def test_missing_provenance_refuses():
    with pytest.raises(AssumptionValidationError):
        analyze_assumption({"id": "a", "formula": {"op": "and", "args": []}}, _symbols())
