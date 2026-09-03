# Is a refusal a difficulty signal?

**Result: no. The hypothesis is not supported, and the selector built on it
is worse than answering everything.** This directory contains the experiment
that established that, kept because a negative result that closes a
direction is worth as much as one that opens it.

## The idea being tested

`research/pilot/` established that the pipeline refuses to lower some
statutory rules to the checkable IR, and says *why* with a typed code. That
suggested something attractive:

> The refusal code is a deterministic, pre-execution difficulty signal —
> obtained with no model call and no judge. If refused questions are the ones
> a model gets wrong, then selective prediction here is *sound by
> construction* rather than *calibrated by fitting*.

That would have been a genuinely different claim from the risk–coverage
literature, and it is the claim a paper would have rested on. So it was worth
testing before building anything on it.

## Hypotheses, fixed before the run

- **H1** — A case whose governing rule the IR *refused* is harder for an LLM
  than one whose rule *compiled*.
- **H2** — The refusal signal selects abstentions at least as well as the
  model's own confidence.

## Method

**Data.** All 306 `sara_binary` cases from DeonticBench. Each gives case
facts, a claim, and a gold binary label.

**Join.** Every case id names the section it tests (`s1_a_1_i_pos` → §1), and
every extracted rule id names the section it *governs*
(`batch2_sec1_a_graduated_tax_schedule` → §1). Rule *citations* are
deliberately not used: they record cross-references, not jurisdiction — the
§1(a) tax schedule cites §2 and §7703 while governing neither. The mapping is
written out explicitly in `case_mapping.py` so all nine rules can be checked
at once.

| Bucket | Meaning | Sections | Cases |
| --- | --- | --- | --- |
| `covered` | a compiled rule governs it | §2 | 36 |
| `refused` | a rule was extracted and refused to lower | §1, §63, §3301 | 110 |
| `no_rule` | extraction produced nothing | §68, §151, §152, §3306, §7703 | 160 |

**Baseline.** The model is given **the same 27KB statute the pipeline read**.
Answering from facts alone would be a strawman, and beating a strawman would
prove nothing. Two independent runs:

1. one sample at temperature 0, with self-reported confidence
2. five samples at temperature 1 — majority vote, with agreement as a
   self-consistency confidence

1,836 model calls total. The statute is a byte-identical prompt prefix, so
provider caching makes the repeat cost small.

```bash
python research/refusal_signal/case_mapping.py                    # audit the join
python research/refusal_signal/run_baseline.py                    # temp 0
python research/refusal_signal/run_baseline.py --samples 5 \
    --out research/refusal_signal/results/selfconsistency.jsonl   # self-consistency
python research/refusal_signal/analyse.py
```

## Results

Baseline accuracy: **87.9%** (temp 0) and **88.6%** (self-consistency).

### H1 — not supported, in both runs

| Bucket | temp 0 | self-consistency | n |
| --- | --- | --- | --- |
| `covered` | 83.3% | 83.3% | 36 |
| `refused` | **90.0%** | **88.2%** | 110 |
| `no_rule` | 87.5% | 90.0% | 160 |

`refused − covered` = **+6.7pp** (Fisher exact p = 0.368) and **+4.8pp**
(p = 0.568). Not significant — and the point estimate has the **wrong sign**
in both runs. Refused cases were, if anything, slightly *easier*.

### H2 — refuted, and not by a close call

| Selector | Risk | Coverage |
| --- | --- | --- |
| answer everything | 12.1% | 100% |
| **abstain unless covered** | **16.7%** | 11.8% |
| self-reported confidence, same coverage | **2.8%** | 11.8% |

Abstaining on refusals **raises** risk from 12.1% to 16.7%. The selector does
not merely fail to help — it picks a worse-than-average subset. At the same
coverage the model's own confidence reaches 2.8%.

AURC (lower is better): self-reported confidence **0.0535**, self-consistency
agreement **0.1028**.

### Two findings that came out sideways

- **The model's own confidence works well here** — AUC 0.774 (temp 0) and
  0.801 (self-consistency), p < 0.0001. Despite clustering at 95–100, the
  tail is informative. This runs against the project's framing that model
  self-assessment cannot be trusted; on this benchmark it can.
- **Self-consistency is the *worse* selector** (AURC 0.1028 vs 0.0385). The
  model is consistent even when wrong, so agreement adds little.

### Ablation — arithmetic is not the hard part

A free surface heuristic, "does the claim assert a `$` amount":

| | Accuracy | n |
| --- | --- | --- |
| asserts `$` | 87.4% | 111 |
| no `$` | 88.2% | 195 |

Flat. Arithmetic — the thing the IR refuses — is not what this model finds
difficult. That is the mechanism behind the null: the IR refuses what is
*arithmetically routine* and accepts what is *semantically intricate*, which
is close to the opposite of what an LLM finds hard.

## What this null result does and does not establish

Reported honestly, because an underpowered null is easy to overread.

```
80% power to detect a true gap of only ~25pp (n_covered = 36)
observed gap 6.7pp -- far inside the region this design cannot resolve
```

- **H1's null means "no large effect", not "no effect".** A real gap of
  10pp would have been detected only 29% of the time. Ruling out a small
  effect would need far more `covered` cases than one statute yields.
- **H2 does not depend on power.** The refusal selector raises risk
  outright. That is a direction, not a significance question, and it
  replicated across two independent runs.
- **This is one benchmark and one model.** SARA is close to saturated at
  ~88%, leaving only ~36 errors — thin ground for any error analysis. A
  harder benchmark could behave differently.

## Recommendation

**Do not build the paper on refusal-as-difficulty-signal.** Two independent
runs put the effect at the wrong sign and the derived selector below the
trivial answer-everything baseline. No amount of framing fixes a selector
that increases risk.

What survives from `research/pilot/` is the honest, smaller claim: the
pipeline's refusals are *sound* — it declines to represent what it cannot
represent, with a machine-checkable reason. That is a **correctness**
property, and `proofs/` already establishes properties of that kind. It is
not a **difficulty** property, and this experiment is why that distinction
now has evidence behind it rather than an assumption.

The two constraints identified in `research/pilot/README.md` remain the real
blockers and are unaffected by this result: the scope allowlist is hardcoded
per domain, and extraction yield (9 rules from a 27KB statute) now binds
before the IR does.
