"""Compile a v2 rule graph to a proved LExec IR document, plus the two
audit artifacts proposal.md Phase 1 calls for: a compilation report and a
standalone proof-records export.

This is the "integrate LExec into the live pipeline" half of Phase 1 that
does not depend on DMN emission (``utils.dmn_builder`` cannot yet represent
a rule with a non-null ``scope.predicate`` -- see ``docs/executable-models.md``
and the caller in ``agents/agent_11_executable_model_generator.py`` for why
``executable_decisions.dmn`` is deliberately not produced here yet).
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from utils.lexec_ir import lower_graph
from utils.smt import prove_table


def compile_and_prove(graph: Mapping[str, Any], *, document_id: str) -> dict[str, Any]:
    """Lower ``graph`` and replace each table's proof with a real one.

    ``lower_graph`` always returns tables with ``policy_proof.status ==
    "unknown"`` (lowering does not itself claim disjointness or equal
    outputs on overlap -- see docs/ir-semantics-v1.md). This attaches the
    ``utils.smt.prove_table`` result for each table in place, so the
    returned IR is ready for ``utils.feel.evaluate_ir`` without a separate
    proving step.
    """

    ir = lower_graph(graph, document_id=document_id)
    rules_by_id = {rule["id"]: rule for rule in ir["rules"]}
    symbols_by_id = {symbol["id"]: symbol for symbol in ir["symbols"]}
    for table in ir["tables"]:
        table["policy_proof"] = prove_table(table, rules_by_id, symbols_by_id)
    return ir


def build_compilation_report(ir: Mapping[str, Any]) -> dict[str, Any]:
    """Summarize one compiled IR document: what compiled, what didn't, and why."""

    refusal_codes = Counter(str(refusal.get("code")) for refusal in ir.get("refusals", []))
    proof_statuses = Counter(str(table.get("policy_proof", {}).get("status")) for table in ir.get("tables", []))
    return {
        "schema_version": "regdelta-compilation-report/1.0",
        "document_id": ir["document_unit"]["document_id"],
        "source_sha256": ir["document_unit"]["source_sha256"],
        "rules_compiled": len(ir.get("rules", [])),
        "rules_refused": len(ir.get("refusals", [])),
        "refusal_codes": dict(sorted(refusal_codes.items())),
        "tables": len(ir.get("tables", [])),
        "table_proof_statuses": dict(sorted(proof_statuses.items())),
        "ignored_fields": len(ir.get("ignored_fields", [])),
    }


def build_proof_records(ir: Mapping[str, Any]) -> dict[str, Any]:
    """Export every table's proof record as a standalone audit artifact."""

    return {
        "schema_version": "regdelta-proof-records/1.0",
        "document_id": ir["document_unit"]["document_id"],
        "proofs": [
            {"table_id": table["id"], "hit_policy": table["hit_policy"], "rule_ids": table["rule_ids"], "policy_proof": table["policy_proof"]}
            for table in ir.get("tables", [])
        ],
    }
