#!/usr/bin/env python3
"""Compile-rate ladder: how much formalizability comes from where?

Lowering a rule to the checkable IR is the precondition for every downstream
proof, so "what fraction lowers?" decides whether a risk-coverage study has
room to work. But a single number hides the more interesting result: on
privacy policies the rate moves 2.5% -> 28.3% -> 63.6% across three stages,
which says most formalizability is produced by *repair*, not by the model.

  raw          rules exactly as the extractor emitted them
  normalised   + the deterministic contract normalisation stage 07 applies
               (operator/value-type aliases), with no LLM involved
  repaired     + evidence-grounded repair and merge (stages 05-09), only
               available when the run actually reached those stages

Usage:
  measure_coverage.py --batch <name> [--json-out results/x.json]
"""
import argparse, collections, copy, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from utils.lexec_ir import lower_graph                                   # noqa: E402
from agents.agent_07_executable_readiness import _normalise_rule_contract  # noqa: E402


def _rules_of(data: dict) -> list:
    rules = data.get("business_rules")
    if isinstance(rules, list) and rules:
        return rules
    out = []
    for bucket in ("entity_types", "relationships"):
        for entry in (data.get(bucket) or {}).values():
            if isinstance(entry, dict):
                out += entry.get("business_rules") or []
    return out


def _load(base: pathlib.Path, rel: str):
    p = base / rel
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return {"entity_types": data.get("entity_types") or {},
            "relationships": data.get("relationships") or {},
            "business_rules": _rules_of(data)}


def _rate(graph: dict, tag: str):
    rules = graph["business_rules"]
    if not rules:
        return None
    ir = lower_graph(graph, document_id=f"ladder-{tag}")
    compiled = len(ir.get("rules") or [])
    return {"rules": len(rules), "compiled": compiled,
            "pct": round(100.0 * compiled / len(rules), 1),
            "refusals": dict(collections.Counter(
                r.get("code") for r in (ir.get("refusals") or [])).most_common()),
            "symbol_theories": dict(collections.Counter(
                s.get("theory") for s in (ir.get("symbols") or [])))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    ap.add_argument("--json-out", type=pathlib.Path)
    a = ap.parse_args()
    base = ROOT / "pipeline-output" / a.batch

    raw = _load(base, "agent_03-rules/compliance_rules_with_entities.json")
    if raw is None:
        raise SystemExit(f"no agent_03 output under {base}")

    raw_measured = _rate(copy.deepcopy(raw), "raw")

    normalised = {**raw, "business_rules": []}
    for r in raw["business_rules"]:
        try:
            out = _normalise_rule_contract(copy.deepcopy(r))
            normalised["business_rules"].append(out if isinstance(out, dict) else r)
        except Exception:
            normalised["business_rules"].append(r)

    repaired = (_load(base, "agent_06-07-08-09-optimized/optimized_compliance_knowledge_graph.json")
                or _load(base, "agent_05-rules-with-entities/compliance_knowledge_graph.json"))

    ladder = {"raw": raw_measured, "normalised": _rate(normalised, "norm")}
    if repaired:
        ladder["repaired"] = _rate(repaired, "repaired")

    print(f"\n{'='*62}\nCOMPILE-RATE LADDER — {a.batch}\n{'='*62}")
    for stage in ("raw", "normalised", "repaired"):
        v = ladder.get(stage)
        if not v:
            print(f"  {stage:11s}  (stage not run)")
            continue
        print(f"  {stage:11s}  {v['compiled']:5d}/{v['rules']:<5d} = {v['pct']:5.1f}%")
    print(f"\n  privacy-policy reference: 2.5% -> 28.3% -> 63.6%")

    final = ladder.get("repaired") or ladder["normalised"]
    print("\ntop refusal codes at the best available stage:")
    for code, n in list(final["refusals"].items())[:6]:
        print(f"   {n:5d}  {code}")
    print("symbol theories:", final["symbol_theories"])

    if a.json_out:
        a.json_out.parent.mkdir(parents=True, exist_ok=True)
        a.json_out.write_text(json.dumps({"batch": a.batch, "ladder": ladder}, indent=2) + "\n")
        print(f"\nwrote {a.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
