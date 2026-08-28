"""Generic Phase 3/5 acceptance test: every fixtures/regdelta/*_tier1/
directory's hand-labeled scenarios.json must agree exactly with what the
real engine (utils.regdelta_engine.diff_graphs) computes.

tests/test_mortgage_tier1_fixture.py additionally asserts mortgage-specific
structure (exact rule IDs, the R-120-004/R-120-003 propagation shape); this
file is the domain-agnostic check every *_tier1 fixture must pass, so
adding a new domain's fixture (Phase 5) does not require a new bespoke test
file to get that base guarantee.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from utils.regdelta_engine import diff_graphs


ROOT = Path(__file__).resolve().parents[1]
REGDELTA_DIR = ROOT / "fixtures" / "regdelta"


def _tier1_fixture_dirs() -> list[Path]:
    if not REGDELTA_DIR.is_dir():
        return []
    return sorted(path for path in REGDELTA_DIR.iterdir() if path.is_dir() and (path / "scenarios.json").is_file())


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("fixture_dir", _tier1_fixture_dirs(), ids=lambda path: path.name)
def test_fixture_scenarios_match_the_real_engine_exactly(fixture_dir: Path):
    old_graph = _load(fixture_dir / "old_graph.json")
    new_graph = _load(fixture_dir / "new_graph.json")
    review_status = _load(fixture_dir / "review_status.json") if (fixture_dir / "review_status.json").is_file() else {}
    dag_edges = [tuple(edge) for edge in _load(fixture_dir / "dag_edges.json")["edges"]] if (fixture_dir / "dag_edges.json").is_file() else []
    scenarios_doc = _load(fixture_dir / "scenarios.json")
    scenarios = [{"case_id": s["case_id"], "inputs": s["inputs"], "targets": s["targets"]} for s in scenarios_doc["scenarios"]]

    report = diff_graphs(
        old_graph, new_graph,
        universe_rule_ids=sorted(review_status) if review_status else sorted({r["rule_id"] for r in old_graph["business_rules"]} | {r["rule_id"] for r in new_graph["business_rules"]}),
        dag_edges=dag_edges, review_status=review_status, scenarios=scenarios, pair_id=fixture_dir.name,
    )
    cases_by_id = {case["case_id"]: case for case in report["affected_cases"]}
    mismatches: list[str] = []
    for scenario in scenarios_doc["scenarios"]:
        case_id = scenario["case_id"]
        actual_case = cases_by_id[case_id]
        for rule_id, expected in scenario["expected"].items():
            if "differs" in expected:
                actual = actual_case["rule_results"].get(rule_id)
                if actual is None:
                    mismatches.append(f"{case_id}/{rule_id}: rule did not compile on both sides")
                    continue
                if actual["old"]["status"] != expected["old_status"]:
                    mismatches.append(f"{case_id}/{rule_id}: old status {actual['old']['status']!r} != expected {expected['old_status']!r}")
                if actual["new"]["status"] != expected["new_status"]:
                    mismatches.append(f"{case_id}/{rule_id}: new status {actual['new']['status']!r} != expected {expected['new_status']!r}")
                if actual["differs"] != expected["differs"]:
                    mismatches.append(f"{case_id}/{rule_id}: differs={actual['differs']} != expected {expected['differs']}")
            else:
                actual_status = report["downstream_impacts"]["statuses"][rule_id]["status"]
                if actual_status != expected["status"]:
                    mismatches.append(f"{case_id}/{rule_id}: status {actual_status!r} != expected {expected['status']!r}")
    assert not mismatches, "\n".join(mismatches)


def test_at_least_mortgage_and_mobile_fixtures_are_discovered():
    names = {path.name for path in _tier1_fixture_dirs()}
    assert {"mortgage_tier1", "mobile_tier1"} <= names
