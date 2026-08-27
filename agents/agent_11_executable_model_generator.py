#!/usr/bin/env python3
"""Generate review-aware executable DMN and BPMN models from pipeline outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.config import get_config  # noqa: E402
from utils.executable_models import (  # noqa: E402
    build_dags_bpmn,
    build_graph_dmn,
    validate_executable_models,
)


def generate(input_graph: Path, dags_file: Path, output_dir: Path) -> dict:
    """Generate and validate both artifacts, returning the persisted report."""
    graph = json.loads(input_graph.read_text(encoding="utf-8"))
    dags = json.loads(dags_file.read_text(encoding="utf-8"))
    dmn = build_graph_dmn(graph, model_name="Compliance-to-Code executable decisions")
    bpmn = build_dags_bpmn(graph, dags, model_name="Compliance-to-Code executable workflows")
    rule_ids = [str(rule.get("rule_id")) for rule in graph.get("business_rules", [])]
    errors = validate_executable_models(dmn, bpmn, rule_ids)
    if errors:
        raise ValueError("; ".join(errors))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "compliance_decisions.dmn").write_bytes(dmn)
    (output_dir / "compliance_workflows.bpmn").write_bytes(bpmn)
    report = {
        "generator": "agent_11_executable_model_generator",
        "source_graph": str(input_graph),
        "source_dags": str(dags_file),
        "rule_count": len(rule_ids),
        "review_required_rules": sum(bool(rule.get("requires_review", True)) for rule in graph.get("business_rules", [])),
        "dmn_file": "compliance_decisions.dmn",
        "bpmn_file": "compliance_workflows.bpmn",
        "validation": "pass",
    }
    (output_dir / "executable_model_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    config = get_config()
    graph = config.get_optimized_dir() / "optimized_compliance_knowledge_graph.json"
    dags = config.get_dag_dir() / "dependency_dags.json"
    output = config.get_executable_models_dir()
    missing = [str(path) for path in (graph, dags) if not path.exists()]
    if missing:
        print("ERROR: required upstream artifact(s) missing: " + ", ".join(missing), flush=True)
        return 2
    try:
        report = generate(graph, dags, output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: executable model generation failed: {exc}", flush=True)
        return 2
    print(f"Generated DMN/BPMN for {report['rule_count']} rules in {output}", flush=True)
    print(f"Review-required rules retained: {report['review_required_rules']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
