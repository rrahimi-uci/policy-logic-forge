from compiler.cegir import CEGIRError, ablation_matrix, apply_repair, evaluate_repair
import pytest


def _ir():
    return {"rules": [{"id": "r1", "condition": {"op": "eq"}, "provenance": [{"source": "s"}]}]}


def test_repair_preserves_provenance_and_logs_edit():
    result = apply_repair(_ir(), {"rule_id": "r1", "field": "condition", "value": {"op": "ne"}})
    assert result["rules"][0]["provenance"]
    assert result["repair_log"][0]["source_preserved"] is True


def test_repair_acceptance_requires_all_guards_and_improvement():
    result = evaluate_repair(_ir(), _ir(), regression_check=lambda _: True, counterexample_check=lambda _: True, objective=lambda _: 1)
    assert result["accepted"] is False
    assert result["guards"]["objective_improved"] is False


def test_repair_without_provenance_refuses():
    with pytest.raises(CEGIRError):
        apply_repair({"rules": [{"id": "r1"}]}, {"rule_id": "r1", "field": "condition", "value": {}})


def test_ablation_requires_source_preservation():
    baseline, candidate = _ir(), _ir()
    report = ablation_matrix(baseline, candidate, evaluate=lambda value: {"accepted": bool(value.get("rules"))})
    assert report["claimable"] is False
