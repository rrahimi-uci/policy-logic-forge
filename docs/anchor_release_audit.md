# Anchor release-contents audit (A1a)

**Historical task:** `A1a` in `plan/tasks.json`. **Status: done — resolves the
open release-content question from the superseded research plan.** Repository audited via
the GitHub API tree endpoint and raw file fetches on 2026-08-24, commit
`6a4844fb235d4f958d0810bba7089a2e9078099e` of
`github.com/opengov-lab/legal-text-to-decision-model` (branch `main`).

## The question this resolves

The third-pass review of the superseded proposal and plan both flagged the
same open uncertainty: *"I could not confirm that the
generated models or expected result files are released — only source models,
gold models, legal text, and the harness."* That uncertainty gated whether
the `A1b` task (deterministic evaluator replay) is executable at all, or
whether A2 (fresh generation) was the only route.

## Finding: the generated models and results ARE released, in full

Verified directly against the repository tree (`git/trees/main?recursive=1`),
not inferred from the README:

| Directory | Files | Total size | Contents |
| --- | ---: | ---: | --- |
| `generated_models/` | **1,900** | 26.5 MB | LLM-generated decision models, one JSON per (model × condition × run) |
| `results/` | 2 | 428 KB | `metrics.csv` (1,900 data rows + header) + `.gitkeep` |
| `gold_models/` | 99 | 2.9 MB | Gold standard models, simplified JSON |
| `source_models/` | 98 | 7.8 MB | Original DMN 1.3 XML |
| `legal_text/` | 2 | 604 KB | `activity_index.json`, `dmn_index.json` |
| `metrics/` | 4 | 14 KB | `dmn_executor.py`, `graph_similarity.py`, `utils.py` — the code that *produces* the metrics, not just reads them |
| `evaluation/` | 2 | 7.5 KB | `run_evaluation.py` — the harness itself |
| `experiments/`, `preprocessing/`, `raw_legal_data/` | — | — | generation pipeline, prompts, and the raw Dutch legal XML the whole corpus derives from |

**`generated_models/` breaks down exactly as the paper describes**, confirmed
by file count, not assumed from the text:

| Model type | Condition | Files | = models × runs |
| --- | --- | ---: | --- |
| Outcome (N=50) | each of 4 conditions | 250 | 50 × 5 runs |
| Requirements (N=45) | each of 4 conditions | 225 | 45 × 5 runs |
| **Total** | | **1,900** | **95 × 4 × 5** |

This is an exact match to the paper's stated "1,900 generations (95 models ×
4 conditions × 5 runs)" — strong evidence the release is complete, not a
partial or placeholder upload.

**`results/metrics.csv` is a real, populated result file** — 428 KB, 1,900
data rows plus a header, one row per generation, with per-row columns:
`activity_id, condition, run_id, dmn_type, dmn_subtype, generation_success,
gold_path, gen_path, gold_nodes, gold_edges, gold_ext_vars, gold_rules,
gen_nodes, gen_edges, gen_ext_vars, gen_rules, sp_kernel, outcome_testable,
outcome_num_tests, outcome_agree_count, outcome_disagree_count,
outcome_agreement`. This is row-level provenance for both the structural
(`sp_kernel`) and outcome-equivalence (`outcome_*`) metrics the paper reports
in aggregate — not just the aggregate numbers themselves.

**The condition-name mapping** (confirmed from the README, not guessed from
the CSV's terse column values):

| README name | `condition` column value |
| --- | --- |
| Text | `baseline` |
| Text+SRL | `srl` |
| Text+IO | `conditions` |
| Text+SRL+IO | `srl_conditions` |

## Consequence for the plan

**A1a's conditional gate is resolved in the favorable direction.** Plan §4.1's
A1b (deterministic evaluator replay) is executable exactly as scoped — pin the
commit, checksum the released files, run `evaluation/run_evaluation.py` (or
recompute independently from `generated_models/` + `gold_models/` using their
own `metrics/dmn_executor.py`), and compare against the committed
`results/metrics.csv`. This is a real 2-3 pd task, not a blocked one, and A2
(fresh generation) is now optional follow-on work rather than the only route.

## An honest caveat this audit surfaced, and left for A1b to resolve properly

A quick, exploratory attempt to reproduce the paper's headline 42.6% /
60.4% outcome-equivalence figures directly from `results/metrics.csv` — by
macro-averaging the `outcome_agreement` column over rows with
`outcome_testable == "True"`, grouped by `dmn_type` and `condition` — **did
not reproduce those numbers**, and also did not recover the paper's stated
count of 24 testable Outcome models via distinct `activity_id`s under that
same filter (it did recover 24 for Outcome, but only 1 distinct testable
`activity_id` for Requirements, against a stated 34).

**This is reported as a finding, not a conclusion.** It most likely means
either (a) "testability" for the headline figures is a property of the *gold*
model — computed once per activity, independent of whether a given generation
happened to expose a comparable structure — rather than the per-row
`outcome_testable` flag in this CSV, which may instead describe whether *that
specific generation* produced a testable structure; or (b) the aggregation
weights by `outcome_num_tests` rather than treating each row's
`outcome_agreement` equally; or (c) some other detail in
`evaluation/run_evaluation.py` / `metrics/dmn_executor.py` this quick pass did
not read closely enough to find. **A1b's actual task is to read that code and
get this right before quoting any reproduced number** — not to guess a
plausible-looking aggregation from column names, which is exactly the mistake
this audit is flagging rather than repeating.

## Raw evidence retained

`/tmp/anchor_tree.json` (full repository tree) and `/tmp/anchor_metrics.csv`
(the committed results file) were fetched for this audit but are not checked
into this repository — they are upstream artifacts, not ours to redistribute,
consistent with proposal §22's "never re-host the Dutch source models"
posture. Re-fetch from the pinned commit above to reproduce this audit.
