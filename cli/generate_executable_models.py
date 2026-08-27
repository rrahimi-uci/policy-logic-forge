#!/usr/bin/env python3
"""Generate review-aware DMN/BPMN from an existing pipeline graph and DAGs."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from utils.executable_models import build_graph_dmn, build_dags_bpmn, validate_executable_models

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--dags", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    graph = json.loads(args.graph.read_text(encoding="utf-8")); dags = json.loads(args.dags.read_text(encoding="utf-8"))
    dmn, bpmn = build_graph_dmn(graph), build_dags_bpmn(graph, dags)
    errors = validate_executable_models(dmn, bpmn, [r.get("rule_id") for r in graph.get("business_rules", [])])
    if errors:
        for error in errors: print(f"ERROR: {error}")
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "mortgage_compliance.dmn").write_bytes(dmn)
    (args.output_dir / "mortgage_workflow.bpmn").write_bytes(bpmn)
    report = {"graph": str(args.graph), "dags": str(args.dags), "rules": len(graph.get("business_rules", [])), "dmn": "mortgage_compliance.dmn", "bpmn": "mortgage_workflow.bpmn", "requires_review": sum(bool(r.get("requires_review", True)) for r in graph.get("business_rules", [])), "validation": "pass"}
    (args.output_dir / "executable_model_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
