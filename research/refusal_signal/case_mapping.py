#!/usr/bin/env python3
"""Join DeonticBench cases to the pipeline's own coverage decision.

The experiment asks whether the pipeline's *refusal* is a useful difficulty
signal.  That only means anything if the join from a benchmark case to a
refusal is mechanical and auditable, so it is isolated here rather than
buried in the runner.

Two facts make the join clean:

1.  Every ``sara_binary`` case id begins with the statutory section it tests
    (``s1_a_1_i_pos`` tests section 1(a)(1)(i)).  No parsing of question
    prose is required.
2.  Every extracted rule id names the section it *governs*
    (``batch2_sec1_a_graduated_tax_schedule`` governs section 1(a)).

Rule *citations* are deliberately not used for this.  They record the
sections a rule cross-references, not the one it decides: the section 1(a)
tax schedule cites sections 2 and 7703 because it refers to surviving
spouses and marital status, while governing neither.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
BENCH = ROOT / "compliance-files" / "deonticbench" / "data"
GRAPH = (
    ROOT
    / "pipeline-output"
    / "pilot-sara-binary"
    / "agent_06-07-08-09-optimized"
    / "optimized_compliance_knowledge_graph.json"
)

# Which section each extracted rule decides, read off its rule id and name.
# Written out rather than inferred so a reviewer can check all nine at once.
RULE_GOVERNS: dict[str, str] = {
    "batch1_surviving_spouse_eligibility": "2",
    "batch1_surviving_spouse_limitations": "2",
    "batch1_head_of_household_child_or_dependent_eligibility": "2",
    "batch1_nonitemizer_taxable_income_calculation": "63",
    "batch1_employer_excise_tax_rate": "3301",
    "batch2_sec1_a_graduated_tax_schedule": "1",
    "batch2_sec1_b_head_of_household_tax_schedule": "1",
    "batch2_sec1_c_unmarried_tax_schedule": "1",
    "batch2_sec1_d_married_separate_tax_schedule": "1",
}

COVERED = "covered"      # a compiled rule governs this section
REFUSED = "refused"      # a rule was extracted for it and refused to lower
NO_RULE = "no_rule"      # extraction produced nothing for this section


def load_cases(config: str = "sara_binary") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((BENCH / config).glob("*.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def case_section(case: dict[str, Any]) -> str:
    match = re.match(r"s(\d+)", str(case.get("id", "")))
    if not match:
        raise ValueError(f"case id does not name a section: {case.get('id')!r}")
    return match.group(1)


def load_rules() -> list[dict[str, Any]]:
    graph = json.loads(GRAPH.read_text())
    rules = graph.get("business_rules") or []
    if rules:
        return rules
    for bucket in ("entity_types", "relationships"):
        for entry in (graph.get(bucket) or {}).values():
            rules += (entry or {}).get("business_rules") or []
    return rules


def compile_status(*, extend_scope_allowlist: bool = True) -> dict[str, Any]:
    """Lower each rule alone so a refusal attributes to exactly one rule.

    ``extend_scope_allowlist`` adds the two scope dimensions this statute
    uses to the IR's hardcoded five-name allowlist.  Without it every rule
    refuses on ``UNREPRESENTABLE_SCOPE`` and the arithmetic signal is
    masked by a defect that has nothing to do with difficulty -- see
    ``research/pilot/README.md``.
    """
    import copy

    import utils.lexec_ir as ir

    if extend_scope_allowlist:
        ir._SCOPE_DIMENSION_SYMBOLS = {
            **ir._SCOPE_DIMENSION_SYMBOLS,
            "case_types": "case_type",
            "configurations": "configuration",
        }

    per_rule: dict[str, dict[str, Any]] = {}
    for rule in load_rules():
        rule_id = rule.get("rule_id")
        lowered = ir.lower_graph({"business_rules": [copy.deepcopy(rule)]})
        refusals = lowered.get("refusals") or []
        per_rule[rule_id] = {
            "compiled": bool(lowered.get("rules")),
            "codes": sorted({r.get("code") for r in refusals}),
            "governs": RULE_GOVERNS.get(rule_id),
        }
    return per_rule


def section_buckets(per_rule: dict[str, Any]) -> dict[str, str]:
    """Section -> COVERED / REFUSED.  Sections absent from the result got no rule."""
    compiled_sections, refused_sections = set(), set()
    for info in per_rule.values():
        section = info["governs"]
        if section is None:
            continue
        (compiled_sections if info["compiled"] else refused_sections).add(section)
    buckets = {s: REFUSED for s in refused_sections}
    buckets.update({s: COVERED for s in compiled_sections})  # compiled wins
    return buckets


def build(config: str = "sara_binary", **kwargs: Any) -> list[dict[str, Any]]:
    """Attach a bucket and the section's refusal codes to every case."""
    per_rule = compile_status(**kwargs)
    buckets = section_buckets(per_rule)

    codes_by_section: dict[str, set[str]] = {}
    for info in per_rule.values():
        if info["governs"] and not info["compiled"]:
            codes_by_section.setdefault(info["governs"], set()).update(info["codes"])

    out = []
    for case in load_cases(config):
        section = case_section(case)
        out.append(
            {
                "id": case["id"],
                "section": section,
                "text": case["text"],
                "question": case["question"],
                "label": int(case["label"]),
                "bucket": buckets.get(section, NO_RULE),
                "refusal_codes": sorted(codes_by_section.get(section, ())),
                # cheap surface heuristic, used as an ablation baseline
                "asserts_amount": "$" in case["question"],
            }
        )
    return out


def main() -> int:
    import collections

    cases = build()
    counts = collections.Counter(c["bucket"] for c in cases)
    print(f"cases: {len(cases)}")
    print("\nbucket totals")
    for bucket in (COVERED, REFUSED, NO_RULE):
        print(f"  {bucket:<9} {counts[bucket]:>4}")

    print("\nsection -> bucket")
    by_section = collections.Counter((c["section"], c["bucket"]) for c in cases)
    for (section, bucket), n in sorted(by_section.items(), key=lambda kv: -kv[1]):
        print(f"  §{section:<6} {bucket:<9} {n:>4}")

    print("\nsanity")
    assert sum(counts.values()) == len(cases)
    print(f"  buckets partition the cases: {sum(counts.values())} == {len(cases)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
