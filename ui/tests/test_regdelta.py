from __future__ import annotations

import json
from pathlib import Path

import pytest

from ui.backend.regdelta import RegDeltaPairs, RegDeltaRuns


ROOT = Path(__file__).resolve().parents[2]


def _write_rule(rule_id: str, threshold: int) -> dict:
    return {
        "schema_version": "2.0", "rule_id": rule_id, "rule_type": "constraint",
        "condition_predicates": [{"predicate_id": "p1", "variable": "amount", "operator": ">", "value": threshold, "value_type": "number"}],
        "condition_logic": {"predicate_ref": "p1"},
        "outcomes": [{"variable": "flag", "operator": "=", "value": True, "value_type": "boolean"}],
        "variables": [{"name": "amount", "type": "number", "role": "input"}, {"name": "flag", "type": "boolean", "role": "output"}],
        "recommended_hit_policy": "UNIQUE", "applicability_scope": {}, "scope_basis": "genuinely_unscoped", "exceptions": [], "mandatory": True,
        "source_reference": {"chunk_path": "fixture.txt", "section_id": "s1", "source_text": "amount over 10", "start_offset": 0, "end_offset": 15},
    }


@pytest.fixture()
def pairs_root(tmp_path: Path) -> Path:
    root = tmp_path / "regdelta"
    pair_dir = root / "toy_pair"
    pair_dir.mkdir(parents=True)
    (pair_dir / "old_graph.json").write_text(json.dumps({"business_rules": [_write_rule("R-1", 10)]}), encoding="utf-8")
    (pair_dir / "new_graph.json").write_text(json.dumps({"business_rules": [_write_rule("R-1", 8)]}), encoding="utf-8")
    (pair_dir / "review_status.json").write_text(json.dumps({"R-1": False}), encoding="utf-8")
    return root


def test_list_pairs_reports_only_directories_with_both_graphs(pairs_root: Path):
    (pairs_root / "not_a_pair").mkdir()
    pairs = RegDeltaPairs(pairs_root)
    items = pairs.list_pairs()
    assert [item["pair_id"] for item in items] == ["toy_pair"]
    assert items[0]["old_rule_count"] == 1
    assert items[0]["has_scenarios"] is False


def test_diff_runs_the_real_engine_and_is_cached(pairs_root: Path):
    pairs = RegDeltaPairs(pairs_root)
    report = pairs.diff("toy_pair")
    assert report["pair_id"] == "toy_pair"
    assert report["downstream_impacts"]["statuses"]["R-1"]["status"] == "threshold_or_constant_change"
    assert pairs.diff("toy_pair") is report  # cached, not recomputed


def test_diff_raises_for_unknown_pair(pairs_root: Path):
    with pytest.raises(KeyError):
        RegDeltaPairs(pairs_root).diff("missing_pair")


def test_diff_against_the_real_checked_in_mortgage_tier1_fixture():
    pairs = RegDeltaPairs(ROOT / "fixtures" / "regdelta")
    pair_ids = {item["pair_id"] for item in pairs.list_pairs()}
    assert "mortgage_tier1" in pair_ids
    report = pairs.diff("mortgage_tier1")
    assert report["metrics"]["universe_size"] == 65
    assert set(report["downstream_impacts"]["direct"]) == {"R-120-004", "batch5_mortgage_pool_fixed_rate_submission_minimum"}


# --- RegDeltaRuns: whole-population run-vs-run comparison (Phase 7.2) --------

def _write_run(root: Path, run_id: str, rules: list[dict], edges: list[tuple[str, str]] | None = None) -> None:
    run_dir = root / run_id
    (run_dir / "agent_06-optimized").mkdir(parents=True)
    (run_dir / "agent_06-optimized" / "optimized_compliance_knowledge_graph.json").write_text(json.dumps({"business_rules": rules}), encoding="utf-8")
    if edges is not None:
        (run_dir / "agent_10-dag-generation").mkdir(parents=True)
        dag = {"dags": [{"dag_id": "d1", "edges": [{"source_rule_id": s, "target_rule_id": t} for s, t in edges]}]}
        (run_dir / "agent_10-dag-generation" / "dependency_dags.json").write_text(json.dumps(dag), encoding="utf-8")


@pytest.fixture()
def runs_root(tmp_path: Path) -> Path:
    root = tmp_path / "pipeline-output"
    old_rule = _write_rule("R-1", 10)
    new_rule = _write_rule("R-1", 8)
    downstream_old = {**_write_rule("R-2", 5), "requires_review": True}
    downstream_new = {**_write_rule("R-2", 5), "requires_review": True}
    _write_run(root, "run-old", [old_rule, downstream_old], edges=[("R-1", "R-2")])
    _write_run(root, "run-new", [new_rule, downstream_new])
    return root


def test_list_runs_reports_only_directories_with_agent_06_output(runs_root: Path):
    (runs_root / "not-a-run").mkdir()
    runs = RegDeltaRuns(runs_root)
    items = {item["run_id"]: item for item in runs.list_runs()}
    assert set(items) == {"run-old", "run-new"}
    assert items["run-old"]["has_dag"] is True
    assert items["run-new"]["has_dag"] is False


def test_diff_covers_the_whole_population_and_uses_the_old_sides_dag(runs_root: Path):
    runs = RegDeltaRuns(runs_root)
    report = runs.diff("run-old", "run-new")
    assert report["pair_id"] == "run-old::run-new"
    assert report["metrics"]["universe_size"] == 2
    assert report["downstream_impacts"]["direct"] == ["R-1"]
    # R-2 only has a DAG edge because run-old's agent_10 output supplies it
    # (run-new has none) -- confirms the "prefer old, fall back to new" rule.
    assert report["downstream_impacts"]["statuses"]["R-2"]["status"] == "unresolved-review"
    assert runs.diff("run-old", "run-new") is report  # cached


def test_diff_raises_for_an_unknown_run(runs_root: Path):
    with pytest.raises(KeyError):
        RegDeltaRuns(runs_root).diff("run-old", "no-such-run")
