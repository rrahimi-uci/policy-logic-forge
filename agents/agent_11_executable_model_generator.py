#!/usr/bin/env python3
"""Generate review-aware executable DMN and BPMN models from pipeline outputs."""

from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.config import get_config  # noqa: E402
from utils.executable_models import (  # noqa: E402
    build_dags_bpmn,
    build_graph_dmn,
    validate_executable_models,
)
from utils.lexec_compile import build_compilation_report, build_proof_records, compile_and_prove  # noqa: E402
from utils.semantic_artifacts import build_review_cmmn, build_sbvr_profile, validate_review_cmmn  # noqa: E402
from utils.semantic_routing import bpmn_eligibility, bpmn_rule_ids  # noqa: E402


def _lower_and_prove(graph: dict, output_dir: Path, *, document_id: str) -> dict | None:
    """Emit lexec_ir.json/compilation_report.json/proof_records.json.

    Additive and best-effort: a failure here must never block or replace
    the review-projection DMN/BPMN this agent already produces. Returns
    the compilation report on success, or None (with a printed warning) on
    an unexpected failure.

    A proof-verified ``executable_decisions.dmn`` is deliberately not
    produced yet: no emitter here can represent a rule with a non-null
    ``scope.predicate``, which is now most compiled mortgage rules since
    utils.lexec_ir started representing loan/transaction/occupancy-type
    scope as a checkable predicate. Extending DMN emission to fold
    scope.predicate into the table's condition columns is separate,
    scoped follow-on work, not silently done here.
    """

    try:
        ir = compile_and_prove(graph, document_id=document_id)
    except Exception as exc:  # noqa: BLE001 - never let this block DMN/BPMN output
        print(f"WARNING: LExec compilation skipped ({type(exc).__name__}: {exc})", flush=True)
        return None
    compilation_report = build_compilation_report(ir)
    proof_records = build_proof_records(ir)
    (output_dir / "lexec_ir.json").write_text(json.dumps(ir, indent=2) + "\n", encoding="utf-8")
    (output_dir / "compilation_report.json").write_text(json.dumps(compilation_report, indent=2) + "\n", encoding="utf-8")
    (output_dir / "proof_records.json").write_text(json.dumps(proof_records, indent=2) + "\n", encoding="utf-8")
    return compilation_report


def generate(input_graph: Path, dags_file: Path, output_dir: Path) -> dict:
    """Generate and validate both artifacts, returning the persisted report."""
    graph = json.loads(input_graph.read_text(encoding="utf-8"))
    dags = json.loads(dags_file.read_text(encoding="utf-8"))
    dmn = build_graph_dmn(graph, model_name="Policy Logic Forge executable decisions")
    bpmn = build_dags_bpmn(graph, dags, model_name="Policy Logic Forge executable workflows")
    cmmn = build_review_cmmn(graph)
    sbvr_profile = build_sbvr_profile(graph)
    rule_ids = [str(rule.get("rule_id")) for rule in graph.get("business_rules", [])]
    eligible_bpmn_ids = bpmn_rule_ids(graph)
    cmmn_rule_ids = {
        str(rule.get("rule_id"))
        for rule in graph.get("business_rules", [])
        if isinstance(rule, dict)
        and isinstance(rule.get("review_route"), dict)
        and rule["review_route"].get("route") in {"case_management", "human_review"}
    }
    errors = validate_executable_models(dmn, bpmn, rule_ids, sorted(eligible_bpmn_ids))
    errors.extend(validate_review_cmmn(cmmn, cmmn_rule_ids))
    if errors:
        raise ValueError("; ".join(errors))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "compliance_decisions.dmn").write_bytes(dmn)
    (output_dir / "compliance_workflows.bpmn").write_bytes(bpmn)
    (output_dir / "compliance_reviews.cmmn").write_bytes(cmmn)
    (output_dir / "semantic_vocabulary_profile.json").write_text(json.dumps(sbvr_profile, indent=2) + "\n", encoding="utf-8")
    # input_graph is .../<batch>/agent_06-07-08-09-optimized/optimized_compliance_knowledge_graph.json;
    # its batch directory is a more meaningful IR document_id than the
    # (often batch-agnostic) output directory name.
    document_id = input_graph.resolve().parents[1].name or "lexec-ir"
    compilation_report = _lower_and_prove(graph, output_dir, document_id=document_id)
    report = {
        "generator": "agent_11_executable_model_generator",
        "source_graph": str(input_graph),
        "source_dags": str(dags_file),
        "rule_count": len(rule_ids),
        "review_required_rules": sum(bool(rule.get("requires_review", True)) for rule in graph.get("business_rules", [])),
        "review_required_rate": round(
            sum(bool(rule.get("requires_review", True)) for rule in graph.get("business_rules", []))
            / max(1, len(rule_ids)) * 100,
            2,
        ),
        "human_review_required_rules": sum(
            bool(route.get("human_review_required"))
            for rule in graph.get("business_rules", [])
            if isinstance(rule, dict)
            for route in [rule.get("review_route")]
            if isinstance(route, dict)
        ),
        "human_review_rate": round(
            sum(
                bool(route.get("human_review_required"))
                for rule in graph.get("business_rules", [])
                if isinstance(rule, dict)
                for route in [rule.get("review_route")]
                if isinstance(route, dict)
            )
            / max(1, len(rule_ids)) * 100,
            2,
        ),
        "review_route_counts": {
            route: sum(
                ((rule.get("review_route") or {}).get("route") or "none") == route
                for rule in graph.get("business_rules", [])
            )
            for route in ("none", "machine_repair", "case_management", "human_review")
        },
        "bpmn_rule_count": len(eligible_bpmn_ids),
        "bpmn_omitted_rule_count": len(rule_ids) - len(eligible_bpmn_ids),
        "bpmn_omissions": {
            str(rule.get("rule_id")): bpmn_eligibility(rule)[1]
            for rule in graph.get("business_rules", [])
            if isinstance(rule, dict) and not bpmn_eligibility(rule)[0]
        },
        "cmmn_case_count": len(cmmn_rule_ids),
        "sbvr_profile_unresolved_concepts": len(sbvr_profile["unresolved_concept_ids"]),
        "source_graph_sha256": hashlib.sha256(input_graph.read_bytes()).hexdigest(),
        "source_dags_sha256": hashlib.sha256(dags_file.read_bytes()).hexdigest(),
        "dmn_file": "compliance_decisions.dmn",
        "bpmn_file": "compliance_workflows.bpmn",
        "cmmn_file": "compliance_reviews.cmmn",
        "sbvr_profile_file": "semantic_vocabulary_profile.json",
        "validation": "pass",
        "lexec_compilation": compilation_report,
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
    print(
        f"Generated DMN for {report['rule_count']} rules, BPMN for "
        f"{report['bpmn_rule_count']} explicit workflows, and "
        f"{report['cmmn_case_count']} review cases in {output}",
        flush=True,
    )
    print(
        f"Quality-hold rules retained: {report['review_required_rules']} "
        f"({report['review_required_rate']}%); human-review queue: "
        f"{report['human_review_required_rules']} ({report['human_review_rate']}%)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
