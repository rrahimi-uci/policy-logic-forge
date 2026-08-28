"""RegDelta "Compare versions" service: discovers fixtures/regdelta/<pair_id>/
old/new-graph pairs and runs the real differential-execution engine
(utils.regdelta_engine) over them, for the review workbench's regdelta view.

This is a read-only, best-effort layer over the same fixtures the pytest
suite validates (see tests/test_mortgage_tier1_fixture.py): a pair missing
optional inputs (dag_edges.json, review_status.json, scenarios.json)
degrades gracefully (no propagation/scenarios) rather than failing closed,
since the UI's job here is to show whatever a pair actually has, not to
gate on completeness the way the fixture's own acceptance tests do.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.regdelta_engine import diff_graphs


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _rule_ids(graph: dict[str, Any]) -> list[str]:
    return [str(rule.get("rule_id")) for rule in graph.get("business_rules", []) if rule.get("rule_id")]


class RegDeltaPairs:
    """Discovers and diffs fixtures/regdelta/<pair_id>/ old/new-graph pairs."""

    def __init__(self, fixtures_root: str | Path) -> None:
        self.fixtures_root = Path(fixtures_root).expanduser().resolve()
        self._cache: dict[str, dict[str, Any]] = {}

    def _pair_dirs(self) -> list[Path]:
        if not self.fixtures_root.is_dir():
            return []
        return sorted(
            path for path in self.fixtures_root.iterdir()
            if path.is_dir() and (path / "old_graph.json").is_file() and (path / "new_graph.json").is_file()
        )

    def list_pairs(self) -> list[dict[str, Any]]:
        items = []
        for path in self._pair_dirs():
            try:
                old_graph = _read_json(path / "old_graph.json")
                new_graph = _read_json(path / "new_graph.json")
            except (OSError, json.JSONDecodeError) as exc:
                items.append({"pair_id": path.name, "status": "load_error", "error": str(exc)})
                continue
            items.append({
                "pair_id": path.name,
                "status": "ready",
                "old_rule_count": len(old_graph.get("business_rules", [])),
                "new_rule_count": len(new_graph.get("business_rules", [])),
                "has_scenarios": (path / "scenarios.json").is_file(),
                "has_dag_edges": (path / "dag_edges.json").is_file(),
            })
        return items

    def diff(self, pair_id: str) -> dict[str, Any]:
        path = self.fixtures_root / pair_id
        if not (path / "old_graph.json").is_file() or not (path / "new_graph.json").is_file():
            raise KeyError(f"unknown RegDelta pair: {pair_id}")
        if pair_id in self._cache:
            return self._cache[pair_id]

        old_graph = _read_json(path / "old_graph.json")
        new_graph = _read_json(path / "new_graph.json")
        universe = sorted(set(_rule_ids(old_graph)) | set(_rule_ids(new_graph)))

        dag_edges: list[tuple[str, str]] = []
        edges_path = path / "dag_edges.json"
        if edges_path.is_file():
            dag_edges = [tuple(edge) for edge in _read_json(edges_path).get("edges", [])]

        review_status: dict[str, bool] = {}
        review_status_path = path / "review_status.json"
        if review_status_path.is_file():
            review_status = _read_json(review_status_path)

        scenarios: list[dict[str, Any]] = []
        scenarios_path = path / "scenarios.json"
        if scenarios_path.is_file():
            scenarios = [
                {"case_id": s["case_id"], "inputs": s["inputs"], "targets": s.get("targets", [])}
                for s in _read_json(scenarios_path).get("scenarios", [])
            ]

        report = diff_graphs(
            old_graph, new_graph,
            universe_rule_ids=universe, dag_edges=dag_edges, review_status=review_status,
            scenarios=scenarios, pair_id=pair_id,
        )
        self._cache[pair_id] = report
        return report


def _dag_edges_from_run(run_dir: Path) -> list[tuple[str, str]]:
    path = run_dir / "agent_10-dag-generation" / "dependency_dags.json"
    if not path.is_file():
        return []
    edges: list[tuple[str, str]] = []
    for dag in _read_json(path).get("dags", []):
        for edge in dag.get("edges", []):
            source, target = edge.get("source_rule_id"), edge.get("target_rule_id")
            if source and target:
                edges.append((source, target))
    return edges


class RegDeltaRuns:
    """Diffs two real pipeline-output/<run_id>/ directories directly -- the
    whole-population comparison plan/regdelta-product-plan.md Section 7.2
    describes (every rule in the union resolves to an explicit status), not
    a curated fixture. No scenarios: there is no hand-authored gold case for
    an arbitrary real document pair, so this reports alignment,
    classification, and propagation/coverage-risk only -- no witnesses.
    """

    def __init__(self, pipeline_root: str | Path) -> None:
        self.pipeline_root = Path(pipeline_root).expanduser().resolve()
        self._cache: dict[tuple[str, str], dict[str, Any]] = {}

    def _graph(self, run_id: str) -> dict[str, Any]:
        path = self.pipeline_root / run_id / "agent_06-optimized" / "optimized_compliance_knowledge_graph.json"
        if not path.is_file():
            raise KeyError(f"run {run_id!r} has no agent_06 output at {path}")
        return _read_json(path)

    def list_runs(self) -> list[dict[str, Any]]:
        """Runs with at least agent_06 output -- candidates for a run-pair diff."""
        if not self.pipeline_root.is_dir():
            return []
        items = []
        for path in sorted(self.pipeline_root.iterdir()):
            if not path.is_dir() or path.name.startswith("."):
                continue
            graph_path = path / "agent_06-optimized" / "optimized_compliance_knowledge_graph.json"
            if graph_path.is_file():
                items.append({"run_id": path.name, "has_dag": (path / "agent_10-dag-generation" / "dependency_dags.json").is_file()})
        return items

    def diff(self, old_run_id: str, new_run_id: str) -> dict[str, Any]:
        cache_key = (old_run_id, new_run_id)
        if cache_key in self._cache:
            return self._cache[cache_key]
        old_graph, new_graph = self._graph(old_run_id), self._graph(new_run_id)
        old_rules = {rule["rule_id"]: rule for rule in old_graph.get("business_rules", []) if rule.get("rule_id")}
        new_rules = {rule["rule_id"]: rule for rule in new_graph.get("business_rules", []) if rule.get("rule_id")}
        universe = sorted(set(old_rules) | set(new_rules))
        review_status = {rule_id: bool((old_rules.get(rule_id) or new_rules[rule_id]).get("requires_review")) for rule_id in universe}
        # Prefer the old side's DAG (the "before" dependency structure);
        # fall back to the new side's if the old run has none.
        dag_edges = _dag_edges_from_run(self.pipeline_root / old_run_id) or _dag_edges_from_run(self.pipeline_root / new_run_id)
        report = diff_graphs(
            old_graph, new_graph,
            universe_rule_ids=universe, dag_edges=dag_edges, review_status=review_status,
            scenarios=(), pair_id=f"{old_run_id}::{new_run_id}",
        )
        self._cache[cache_key] = report
        return report
