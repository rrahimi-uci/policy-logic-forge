from __future__ import annotations

import json
from pathlib import Path

import pytest

from ui.backend.regdelta import RegDeltaPairs


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
