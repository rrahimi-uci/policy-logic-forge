# DeonticBench feasibility pilot

Purpose: decide whether **verification-grounded selective prediction on
statutory reasoning** is a viable research direction, before investing in it.

The direction only works if statute-derived rules actually lower to the
checkable IR. On privacy policies that rate is **63.6%**. This pilot measures
the same number on DeonticBench statutes and reports *why* anything fails.

```bash
# 1. build a corpus from the benchmark (sara_binary shares one statute)
.venv/bin/python research/pilot/build_corpus.py --config sara_binary --max-statutes 1

# 2. extract
.venv/bin/python cli/extract.py --dir pilot_sara --domain deonticbench \
    --batch-name pilot-sara-binary --stages 1-3 --target-rules 60

# 3. the number that decides the direction
.venv/bin/python research/pilot/measure_coverage.py --batch pilot-sara-binary \
    --json-out research/pilot/results/sara_binary.json
```

## What the pilot established before running

These come from reading the benchmark, and they reshape the experiment design.

### The arithmetic gap is ~11%, not the bulk

The LExec IR has no arithmetic — its operators are
`and · or · not · is_null · eq · ne · lt · le · gt · ge · contains · in_binned_range`
and outcomes are assignment-only. That was the main feasibility worry.

Measured against the benchmark, it costs less than expected:

| Split | Rows | Arithmetic-free | Note |
| --- | --- | --- | --- |
| `uscis-aao` | 270 | **270 (100%)** | accept/dismiss adjudication |
| `housing` | 5,392 | **5,329 (99%)** | statute yes/no |
| `sara_binary` | 306 | **195 (64%)** | the rest assert a `$` amount |
| `airline`, `sara_numeric` | 515 | 0 | numeric by construction |

**5,794 of 5,968 classification rows (97%) need no arithmetic.** The excluded
~11% of the benchmark includes the hard numeric subsets where published
performance is weakest (44.4% on SARA-Numeric), so adding bounded arithmetic to
the IR remains the highest-value upgrade — but it is an *enhancement*, not a
prerequisite.

### The splits are three different tasks, not one

This is the finding that most affects design. Each needs different plumbing:

| Split | `text` field | Task shape | What it needs |
| --- | --- | --- | --- |
| `sara_binary` | 176 chars, structured facts | apply rules to clean facts | closest to what the pipeline already does |
| `uscis-aao` | ~1.8k chars, appeal narrative | adjudicate from prose | fact extraction from narrative |
| `housing` | **empty** | statute QA — no case at all | a query mechanism over the rule set, not rule application |

Treating DeonticBench as one task would be a design error. The cleanest
starting point is **the 195 arithmetic-free `sara_binary` applicability rows**
("Section 2(b)(1)(A)(ii) applies to Charlie as the dependent in 2017"), which
are scope-and-exception reasoning over structured facts — exactly what the rule
contract models.

### Why `sara_binary` is the right pilot

All 306 cases share **one** 27KB statute, so a single extraction run supports
the whole split. `uscis-aao` is near 1:1 (221 statutes / 270 cases) and would
need one extraction per case.

## Decision rule

Pre-registered before the run, kept here verbatim.

- **Compile rate ≳ 60%** — comparable to privacy policies. The risk-coverage
  experiment is viable; proceed.
- **Compile rate 30–60%** — viable but the coverage axis is truncated. Read the
  refusal codes: if they concentrate in a few fixable causes, fix those first.
- **Compile rate < 30%** — the risk-coverage frontier has too little room. Fall
  back to the faithfulness-at-scale study, which needs no execution and can use
  `reference_prolog` as gold directly.

## Result

Stages 1–9, 7m 20s, $0.16, 9 rules extracted from the 27KB statute.

```text
raw            0/9 =  0.0%     8x UNSUPPORTED_OPERATOR ('=' not 'eq'), 1x TYPE_MISMATCH
normalised     0/9 =  0.0%     operator wall cleared; scope + arithmetic wall behind it
repaired       0/9 =  0.0%     3x UNREPRESENTABLE_SCOPE, 2x UNSUPPORTED_VALUE_TYPE,
                               4x UNSUPPORTED_VARIABLE_TYPE
```

**The headline 0% is not the finding.** Decomposed, it is two unrelated causes,
one of them a bug:

### Cause 1 — the scope vocabulary is hardcoded per domain (a real defect)

`_SCOPE_DIMENSION_SYMBOLS` in `utils/lexec_ir.py` is a five-name allowlist:
`loan_types`, `transaction_types`, `occupancy_types` (mortgage) and
`user_categories`, `information_types` (privacy). Its own comment says as much.
A tax statute scopes rules by `case_types` and `configurations`, so lowering
refuses them — not because the semantics cannot express the scope, but because
the field name is not on a list tuned to the two domains already run.

Adding those two names to the allowlist, changing nothing else:

```text
repaired       3/9 = 33.3%     remaining: 2x feel_expression, 4x list
```

This matters beyond the pilot. **The 63.6% privacy compile rate is partly a
product of having tuned this allowlist to privacy.** Any cross-domain claim has
to fix this first; it should be a declared scope ontology per domain pack, or
an open string-symbol dimension, not a literal in the IR.

### Cause 2 — arithmetic, exactly as predicted

Of the 9 rules, 6 are tax computation. Every one of the 6 fails on the
arithmetic gap and nothing else — 2 on `feel_expression`
(`adjusted_gross_income - standard_deduction_amount - ...`), 4 on `list`
(the §1(a)–(d) graduated bracket tables).

The split is total and clean:

| Rule class | Count | Compiled |
| --- | --- | --- |
| Arithmetic-free (2 eligibility, 1 exception) | 3 | **3 (100%)** |
| Arithmetic-bearing (6 calculation) | 6 | 0 (0%) |

**Not one arithmetic-free statutory rule failed for a semantic reason.** The
33% is entirely the arithmetic mix of this particular statute.

### Reading the result against the decision rule

The rule was written expecting one number and got a bimodal one, so applying it
literally would mislead. `sara_binary`'s statute is IRC §1/§2/§63/§68/§151/§152/
§3301/§3306/§7703 — the most arithmetic-dense text in the benchmark. It was the
worst case for an IR with no arithmetic, and it still compiled everything that
did not need it.

The pre-registered `< 30% → fall back` branch does **not** fire, because the
denominator it assumed (rules the IR is meant to cover) is 3, not 9.

### Two remaining constraints, both real

- **Extraction yield.** 9 rules from a 27KB, 9-section statute against
  `--target-rules 60`. The 9 touch §1, §2, §151, §152, §3306, §7703 — missing
  §63 (44 questions), §68 (16), §3301 (2). Coverage is now bounded by
  extraction, not by the IR.
- **Question reach.** The 3 compiled rules cover §2 / §152 / §7703, the
  applicability chain, which is roughly 96 of the 306 questions.

### Recommendation

Scope the study to the arithmetic-free applicability subset the benchmark
already isolates (195 `sara_binary` + 270 `uscis-aao` + 5,329 `housing` =
5,794 rows, 97% of classification rows), fix the scope allowlist first, and
treat bounded IR arithmetic as the headline ablation rather than a prerequisite.

The sharper hypothesis this pilot surfaced, which is testable with data already
in hand: **the refusal code is a deterministic, pre-execution difficulty signal
obtained with no model call and no judge.** If baseline LLM accuracy on
arithmetic-refused questions is materially worse than on representable ones,
selective prediction here is *sound by construction* rather than *calibrated by
fitting* — which is a different claim from anything in the risk-coverage
literature.
