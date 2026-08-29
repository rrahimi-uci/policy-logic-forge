# Behavioral Simulation and Impact Analysis

## Executive summary

The ask: a simulator over the extracted DMN/BPMN/CMMN models that first
generates scenarios to show how rules behave, then analyses the impact of a
rule and of a rule change.

The honest answer, after measuring the current runs rather than reasoning from
the design docs:

1. **The behavioral question is the right one.** The pipeline can today prove a
   rule is *grounded* (traceable to source) and *ready* (structurally
   executable). It cannot say what the rule set **does**. A rule can be
   perfectly grounded, structurally valid, and still be behaviorally dead,
   vacuous, or in silent contradiction with another rule. Nothing in the
   repository would notice.

2. **It is blocked at step one, and not for the reason anyone would guess.**
   `utils/feel.evaluate_ir` — the repository's only IR executor — returns
   `unknown` for **0 of 350** mortgage and **0 of 371** privacy executable
   rules. Not most. All. See §2.

3. **Once unblocked, scenario generation is far easier than the docs imply.**
   89–99% of condition symbols are `bool`/`enum`, exactly the theories the
   existing bounded enumerator can exhaust. No SMT solver is needed for v1.

4. **Cross-rule simulation is not possible yet, and now we can say so with a
   number.** Of 210 dependency-DAG edges between executable rules, **0** have
   a shared-symbol basis. Rules are symbol-isolated islands.

The proposal therefore delivers **single-rule behavioral simulation and
what-if impact** now, and treats symbol canonicalization as the named
prerequisite for the rule-*network* simulation the ask implies. It
deliberately does **not** propose operational process simulation, which
`plan/proposal.md` §5.2 and §13 exclude for good reasons that still hold.

---

## 1. Position relative to the existing plans

This matters because `plan/proposal.md` line 5 opens by *narrowing away* from
exactly the word in this document's title:

> "This proposal narrows the research objective **from a general business
> simulator** to a problem that the current Policy Logic Forge system can
> support and that open benchmarks can evaluate."

That narrowing was correct and this document does not reverse it. But
"simulator" covers two very different things, and the proposal excludes only
one of them:

| | Excluded by `proposal.md` | Proposed here |
| --- | --- | --- |
| **Operational simulation** — resources, queues, arrival rates, durations, cycle time, cost | §5.2, §13, §14: needs event-log calibration that does not exist; would emit authoritative-looking uncalibrated numbers | **No.** Stays excluded. |
| **Behavioral simulation** — given this case, what does the rule set decide, and why? | Not excluded. §6.1 *requires* "a scenario cohort X"; §11 Phase 2 step 4 calls for `utils/witness_generation.py` | **Yes.** This is the missing front half of RegDelta. |

So this is not a competing track. `plan/regdelta-product-plan.md` §5 already
reserves the space, and RegDelta cannot complete without it: its scenario
cohorts are hand-authored today (9 cases for mortgage Tier 1, 7 for mobile),
and `utils/smt.py`'s witness machinery — built, tested, documented — is
**wired to nothing**.

### What RegDelta already answers, and what it cannot

RegDelta answers *"what differs between two document versions?"* It cannot
answer *"what happens if I feed this case through the model?"* as a standalone
question — there is no evaluation endpoint, CLI, or UI action anywhere that
takes a case and returns an outcome. The only execution path is
`diff_graphs()`, which requires two graphs and reports only differences.

Two entry points are therefore genuinely absent, and both are in the ask:

- **"What does this rule do?"** — no version pair involved.
- **"What breaks if I change this rule?"** — a *proposed edit*, not a second
  real document.

The second is strategically significant: RegDelta's product blocker is data
acquisition (Phase 7.1 needs a real second edition of the Selling Guide, which
does not exist in `compliance-files/`). What-if analysis has no such blocker.
It delivers change-impact value from a hypothetical edit **today**, using the
same engine.

---

## 2. What was measured

All figures from the checked-in runs, measured directly rather than taken from
documentation. Reproduction commands in §10.

| Measurement | Mortgage v2 | Privacy |
| --- | ---: | ---: |
| Rules compiled to executable IR | 350 / 624 (56%) | 371 / 802 (46%) |
| Tables with `proved` policy | 340 / 345 | 344 / 363 |
| **Rules evaluable by `utils.feel` today** | **0 / 350 (0%)** | **0 / 371 (0%)** |
| Condition symbols that are `bool`/`enum` | 714 / 804 (89%) | 454 / 460 (99%) |
| Condition symbols that are `real` | 90 | 5 |
| Distinct numeric literals in all conditions | 92 | 18 |
| Enum domain size (mean / max) | 1.5 / 14 | 1.4 / 10 |
| Dependency-DAG edges, both endpoints executable | 210 | — |
| Def-use edges (rule defines a symbol another reads) | 4 | — |
| **DAG ∩ def-use** | **0** | — |
| Rules in ≥1 def-use edge | 5 / 350 (1%) | — |

### Finding A — the evaluator refuses every real rule

`utils/feel._scope_available` (`utils/feel.py:109`) returns `False` whenever
`jurisdictions`, `parties`, `effective_from`, `effective_to`, or
`document_version` is non-empty, because the bounded evaluator has no runtime
context. `docs/ir-semantics-v1.md` documents this as a deliberate, tested
safety property, and it is the right default.

But `parties` is populated on **100%** of executable rules in both runs
(mortgage: `{FANNIE_MAE, LENDER}`, `{BORROWER, LENDER}`, …; privacy:
`{FIRST_PARTY}`, `{FIRST_PARTY, THIRD_PARTY}`, …), as is `document_version`.
So the safety property is not a rare abstention — it is total.

This is precisely why `utils/regdelta_engine.py` built its own
`evaluate_rule_for_diff` that bypasses the block. That bypass is correct *for
version diffing* (which asks whether a rule's own logic changed) and wrong for
simulation (which must ask whether the rule is in force for this case).

**The fix is not to bypass it. It is to supply the missing context.** A
scenario should carry an as-of date, a party set, and a jurisdiction — those
are properties of a real case, not evaluator plumbing. Resolving contextual
scope against a scenario context turns a blocking limitation into a *feature*:
the system gains the ability to answer "is this rule in force for this
transaction on this date," which RegDelta explicitly declines to answer.

This is Phase 0. Without it there is no simulator.

A secondary data-quality finding falls out: `document_version` is free prose,
not a controlled vocabulary. Privacy alone has 41 distinct values including
`"unresolved_final_state: the supplied excerpt does not state whether this
cookie choice practice has been superseded."` That field can never be
machine-resolved as-is and should become a controlled enum plus a free-text
note. Filed as a separate extraction-contract issue, not solved here.

### Finding B — scenario generation needs no solver

The bounded enumerator's documented weakness is that it never discretizes real
intervals. That sounded fatal for a mortgage domain full of LTV and DTI
thresholds. Measured, it is not: **89% (mortgage) and 99% (privacy) of
condition symbols are `bool` or `enum`** — exactly what `utils/smt.py` can
exhaust completely. Only 90 and 5 symbols respectively are `real`, and they
carry just 92 and 18 distinct literals between them.

That is small enough to enumerate boundaries exhaustively by hand-rolled
partition analysis, with no solver at all. **A real SMT backend (Z3 behind the
existing `utils/smt.py` interface, as `docs/smt-query-protocol.md` already
anticipates) is a later optimization, not a prerequisite.** This materially
de-risks the whole capability.

The mean enum domain size of ~1.5 is itself a finding: a condition
`x == "Full Review"` where `x`'s domain is exactly `{"Full Review"}` is
vacuously true whenever `x` is bound. That is a behavioral defect the
simulator can detect and the current pipeline cannot (§5, *vacuous rule*).

### Finding C — the rule network is not connected

`plan/regdelta-product-plan.md` §6.5 flags symbol fragmentation as "a genuine
open design question," illustrated with one example: `R-120-003` references
`fannie_mae_required_insurance_or_loan_guaranty` while `R-120-004` changes
`primary_mortgage_insurance_policy_required` — the same fact, two names,
because the rules were extracted independently.

Measured across the whole run, it is not one example. It is the norm:

- 784 symbols are defined as an effect target; 1,006 are used in a condition.
- **22** are both. Yielding **4** def-use edges across 350 rules.
- **1%** of executable rules participate in any def-use edge.
- Of the 210 narrative DAG edges whose endpoints are both executable,
  **0** have a shared-symbol basis.

The narrative DAG (agent_10) and the data-flow graph are describing disjoint
things, and the DAG's own accuracy is unmeasured
(`utils/dependency_audit.py` is `fixture_only`).

Three consequences, all of which the proposal must respect rather than paper
over:

1. **Cross-rule simulation is impossible today.** Rule outputs cannot feed
   other rules' inputs. Every rule is an island. (Within a single rule,
   effects *do* chain — `utils/feel.py:161`.)
2. **Impact propagation over the DAG is suggestive, not sound.** It has zero
   data-flow grounding. It should be labeled as narrative reachability, not
   dependency.
3. **Symbol canonicalization is the prerequisite** for any rule-network claim.
   `semantic_vocabulary_profile.json` — already emitted by agent_11 — is the
   natural vehicle. That is a named, scoped follow-on, not something to
   attempt inside this capability.

Reporting this fragmentation as a first-class extraction-quality metric is
cheap and high-value: it converts a known open question into a tracked number.

---

## 3. Product proposition

**Today the pipeline produces a knowledge graph you can read. This makes it a
policy model you can interrogate.**

The current review surface asks a reviewer to judge a rule from its text,
evidence, and a confidence score. That is the hardest possible way to spot the
defects that actually matter. Compare:

| Current review prompt | Behavioral review prompt |
| --- | --- |
| "Rule R-120-004, confidence 0.72 — approve?" | "R-120-004 never fires for any of 4,100 generated cases. Its condition requires `project_review_basis == 'Full Review'`, but that enum's only allowed value makes the test vacuous. Here is the case." |
| "Rules R-120-004 and R-120-003 are related (DAG edge, confidence 90.2)." | "No case exists in which both fire — they cannot be related through data. The edge is narrative only." |
| "Threshold changed 80 → 78." | "Of 4,100 cases, 61 flip outcome. All 61 sit in LTV ∈ (78, 80]. Here are three." |

The right-hand column is what a business reviewer can actually adjudicate, and
it is generated, not authored.

Three surfaces, deliberately **not** called a "simulator" in user-facing copy —
that word invites confusion with the operational process simulation this
project excludes:

- **Scenario Lab** — generate and curate case cohorts.
- **Behavior Explorer** — run a cohort; see what each rule does; triage
  behavioral defects.
- **Impact Analyzer** — "what depends on this?" and "what breaks if I change
  it?"

The value ladder, in order of how quickly it lands:

1. **Behavioral defect detection** (dead/vacuous/unknown-dominant rules).
   Immediate, needs no human input, feeds the existing review queue.
2. **Concrete conflict witnesses.** "Rules A and B both fire on this case with
   contradictory effects" is worth more than a conflict flag.
3. **What-if change impact.** Unblocks change-impact value without a second
   real document.
4. **Coverage as a run-level metric.** Comparable across runs; a regression
   signal for prompt and pipeline changes.

---

## 4. Layer 0 — the scenario contract (the unblocker)

```jsonc
{
  "schema_version": "scenario-cohort/1.0",
  "cohort_id": "mortgage-v2-boundary-001",
  "provenance": { "ir_sha256": "...", "generator": "boundary|enum|witness|persona", "seed": 1234 },
  "context": {                       // resolves scope metadata; REQUIRED
    "as_of_date": "2026-08-29",
    "parties": ["BORROWER", "LENDER"],
    "jurisdiction": "US-CA"
  },
  "cases": [
    { "case_id": "bv-0001",
      "inputs": { "ltv_ratio_percent": 80, "project_review_basis": "Full Review" },
      "unbound": ["special_assessment_delinquency_percent"],   // explicit, not missing
      "derivation": { "kind": "boundary", "symbol": "ltv_ratio_percent", "literal": 80, "offset": "at" } }
  ]
}
```

Two design points carry real weight:

- **`unbound` is explicit.** A symbol deliberately left null is a first-class
  test of the fail-closed property, not an oversight. Kleene `unknown` is the
  expected result and must be recorded as such, never as `no_match`.
- **`context` is required.** A cohort without one cannot evaluate anything, per
  Finding A. Making it mandatory in the schema prevents silently reintroducing
  the universal-scope bug the current block exists to prevent.

Evaluator change (`utils/feel.py`), surgical:

```python
def _scope_available(scope, context=None) -> tuple[bool, str | None]:
    #  effective_from/to  -> compare against context.as_of_date
    #  jurisdictions      -> membership against context.jurisdiction
    #  parties            -> membership against context.parties
    #  document_version   -> controlled values resolve; free prose stays unknown
    #  no context supplied -> current behavior exactly (unknown)
```

Default with no context is byte-identical to today, so
`tests/test_feel.py::test_contextual_scope_and_collect_are_not_silently_executed`
keeps passing unchanged. An unresolvable dimension stays `unknown` — context
resolves scope, it never overrides it.

---

## 5. Layer 1 — scenario generation

**Core idea: the rule set's own literals define its equivalence partitions.**
Every comparison in the compiled IR contributes a boundary. This is classical
boundary-value analysis and equivalence partitioning, and it needs no solver.

Generators, cheapest first:

| # | Generator | Mechanism | Needs |
| --- | --- | --- | --- |
| 1 | **Enum/bool exhaustion** | full cross product over small domains (89–99% of symbols) | nothing |
| 2 | **Boundary probes** | for each `real` literal *v*: {*v*−ε, *v*, *v*+ε} | nothing |
| 3 | **Kleene/null sweep** | omit each condition symbol in turn | nothing |
| 4 | **Rule-targeted witness** | `utils.smt.query_witness` — synthesize an input that fires rule *R* | existing, unused |
| 5 | **Gap witness** | `utils.smt.query_coverage` counterexample — inputs no rule covers | existing, unused |
| 6 | **Conflict witness** | `utils.smt.query_overlap` / `query_conflicts` — both fire, effects differ | existing, unused |
| 7 | **n-wise combinatorial** | pairwise over partition representatives, to bound explosion | nothing |
| 8 | **Persona / LLM-authored** | realistic narrative cases | provider |

Generators 4–6 give **rule coverage by construction** and are already built and
tested — wiring them is the single highest-value/lowest-cost item in this plan.

> **Claim boundary — the one that is easiest to violate.** A generated cohort
> is **not a population sample**. Results are *scenario exposure* (`N of M
> generated cases`), never "N% of your customers." This is exactly
> `proposal.md` §5.3's existing three-tier vocabulary (structural concern /
> scenario exposure / expected risk), and only the first two are supported.
> Generator 8 output must be labeled illustrative and **must never feed an
> exposure statistic** — an LLM-authored cohort has no sampling frame at all.

---

## 6. Layer 2 — behavioral execution and the defect taxonomy

Execute the cohort; record per rule × case: `matched` / `no_match` /
`unknown` / `defeated` / `conflict` / `refused`. Aggregate into a **behavioral
defect taxonomy** that complements the existing grounding and readiness
taxonomies:

| Finding | Definition | Likely extraction defect |
| --- | --- | --- |
| **Dead rule** | never `matched` across the cohort | over-constrained condition; contradictory conjunction |
| **Vacuous rule** | `matched` on every bound case | condition lost or degenerate (e.g. single-value enum) |
| **Unknown-dominant** | mostly `unknown` | under-specified; unresolvable scope; missing bindings |
| **Silent conflict** | two rules match one case, incompatible effects on one target | genuine contradiction, now concrete |
| **Boundary drift** | behavior flips at a value not matching any source-cited threshold | threshold mis-extracted |
| **Defeater dominance** | exceptions defeat most matches | exception scoped too broadly |

Every finding carries a **concrete witness case** and routes into the existing
review queue. "This rule never fires, here is proof" is a far better review
prompt than a confidence score.

Coverage metrics per run, comparable across runs: rule coverage, condition
coverage, boundary coverage, unknown rate, refused rate.

> A dead-rule finding is only as good as the cohort. Every behavioral finding
> must be reported **jointly with cohort coverage**, so "never fires" is never
> confused with "we never tried." This mirrors the repo's existing
> accuracy-with-coverage discipline.

---

## 7. Layer 3 — impact analysis

### 7.1 "What depends on this rule?"

Report **two graphs side by side and their disagreement**, rather than one
graph presented as truth:

- **Narrative reachability** — agent_10's DAG. Label it as extraction
  judgement, and surface `strength`/`confidence`, which `potential_set`
  currently ignores entirely.
- **Data-flow** — def-use over IR symbols. Today: 4 edges.

The disagreement set *is* the deliverable. With 210 narrative edges and 0
data-flow corroboration, the honest headline is: **"no dependency in this run
has a data-flow basis; propagation is narrative reachability only."** That is a
decision-forcing measurement, and it is a tracked metric that will improve as
symbol canonicalization lands.

### 7.2 "What breaks if I change this rule?"

An analyst edits a threshold, condition, or effect in the UI:

```
edit → recompile that rule (utils.lexec_compile)
     → classify (utils.semantic_diff.classify_change)        [exists]
     → replay cohort, old vs new                             [Layer 2]
     → diff outcomes → witnesses                             [exists in regdelta_engine]
     → narrative reachability, labeled as such                [utils.impact_propagation]
```

Every component exists. This is orchestration plus a UI, not new science. The
only genuinely new piece is the cohort — which is Layers 1–2.

Note the edit vocabulary limit: `regdelta_fixture_lib.apply_edit` supports
exactly one scalar predicate value. Richer edits (add/remove rule, change
effect, change exception) need a real edit model.

---

## 8. DMN, BPMN, and CMMN — the honest answer

The ask names all three. They are not in the same state, and treating them
alike would manufacture false confidence.

| Notation | Reality today | Proposed |
| --- | --- | --- |
| **DMN / decisions** | `compliance_decisions.dmn` is a **review projection**, not executable: `utils/dmn_builder` raises `UNSUPPORTED_SCOPE` for any non-null `scope.predicate`, now most mortgage rules, so `executable_decisions.dmn` is deliberately not produced (`agent_11:34-41`) | **Simulate for real — over LExec IR, not the emitted DMN.** IR is the semantic boundary; the DMN is a picture of it. Later, cross-check against a pinned third-party engine via the existing `bench/dmn_engine_harness.py` (BE-4), which is built and `unrun`. |
| **BPMN / processes** | Generated by ordering business-rule tasks along the *narrative DAG* (`proposal.md` §4.2). Given Finding C, that ordering has no data-flow basis | **Do not token-simulate.** Replaying it would produce authoritative-looking output about a process never observed. Instead: (i) static soundness checks — unreachable task, improper termination — which catch real projection defects; (ii) **annotate** the diagram with real decision results ("for this case, these rule-tasks fired"), giving the visual without the fabricated process claim. |
| **CMMN / cases** | `build_review_cmmn` emits one case per non-machine review route with a `humanTask` + `milestone`. No executor anywhere | **Reduce to guard evaluation.** A sentry / entry criterion *is* decision logic, so evaluating criteria against a scenario reuses Layers 1–2 entirely and shows which stages become available. Do not build a case lifecycle engine. |

On CMMN more broadly, the industry signal is unambiguous and argues against
investing there at all. Camunda — which built a CMMN engine *before* OMG even
released the spec, then invested years in symbols, modeling, and admin tools —
published ["How CMMN never lived up to its
potential"](https://camunda.com/blog/2020/08/how-cmmn-never-lived-up-to-its-potential/)
in 2020, reduced CMMN to maintained-but-not-fully-supported in Camunda 7, and
[dropped it entirely from Camunda
8](https://forum.camunda.io/t/support-for-case-management-in-camunda/38860).
Their standing recommendation is to express [CMMN patterns in
BPMN](https://camunda.com/blog/2023/07/cmmn-patterns-bpmn/) instead. Flowable
retains a CMMN engine, but it is now effectively the only major one.

**Recommendation: do not build CMMN execution.** Keep emitting the review
projection, evaluate its sentries as decision logic (above), and treat any
deeper CMMN investment as unjustified.

### A note on BE-4 engine selection

For eventually cross-checking emitted DMN against a real engine
(`bench/dmn_engine_harness.py`), the practical options are worth recording now:
the Python-side candidates are poor fits —
[pyDMNrules](https://github.com/russellmcdonell/pyDMNrules) is DMN 1.3-compliant
but consumes **Excel workbooks**, not DMN XML;
[bkflow-dmn](https://github.com/TencentBlueKing/bkflow-dmn) describes tables as
Python dicts; and [SpiffWorkflow](https://spiff-arena.readthedocs.io/en/latest/reference/bpmn/decision_tables.html)
uses Python expression syntax rather than FEEL, so it cannot validate FEEL
rendering at all. The credible choice is a JVM engine — [Drools/KIE
DMN](https://kiegroup.github.io/dmn-feel-handbook/), which implements the spec's
FEEL — run as a pinned sidecar behind the harness's existing NDJSON adapter
protocol. That matches the harness's design intent exactly and requires no
Python dependency.

**Summary position: simulate the decision layer for real; use it to
*illuminate* the process and case layers rather than pretending to execute
them.**

---

## 9. Claim boundary

Consistent with `docs/ir-semantics-v1.md` and `plan/proposal.md` §13.

**May be claimed**, if the work succeeds:

- behavioral characterization of the **executable subset** of one run;
- generated cohorts with declared coverage over that subset;
- concrete witnesses for dead/vacuous/conflicting rules;
- outcome deltas for a hypothetical rule edit, over a declared cohort;
- a measured symbol-fragmentation rate and narrative-vs-data-flow agreement.

**May not be claimed:**

- population or portfolio exposure ("N% of customers") — cohorts are not samples;
- behavioral coverage of the ~45–55% of rules that do not compile;
- process or case behavior (BPMN/CMMN are annotated, not executed);
- rule-network behavior, until symbol canonicalization lands (Finding C);
- legal correctness, or that a rule set is complete or compliant;
- operational metrics — staffing, cycle time, cost (out of scope, §1);
- that agreement between the reference evaluator and itself validates anything.

Status vocabulary reuses the existing ladder unchanged: **proved** (solver),
**observed** (seen on a declared cohort), **unknown**, **refused**. Nothing
promotes `unknown` to a pass.

---

## 10. Phases

Each phase is independently valuable and independently abandonable.

### Phase 0 — Scenario context (unblocks everything)
`utils/feel.py` context-aware `_scope_available`; `scenario-cohort/1.0` schema;
`utils/scenario.py` load/validate.
**Acceptance:** ≥1 real rule from a real run evaluates to `matched` (today: 0);
no-context behavior byte-identical to current; existing feel tests unchanged.

### Phase 1 — Generators 1–3 (no solver)
Enum/bool exhaustion, boundary probes, Kleene sweep. `utils/scenario_gen.py`.
**Acceptance:** cohort generated for both retained runs; every case traces to
the IR literal that produced it; deterministic under seed.

### Phase 2 — Behavior run + defect taxonomy
`utils/behavior.py`, `behavior-report/1.0`, CLI. The six §6 findings.
**Acceptance:** every executable rule gets a status — none silently dropped;
each finding carries a witness; coverage reported alongside every finding.

### Phase 3 — Solver-directed generation
Wire the existing `utils/smt.py` queries (generators 4–6).
**Acceptance:** rule coverage strictly improves over Phase 1; every witness
reproduces on replay; `unknown`/`timeout` never reported as a gap.

### Phase 4 — Fragmentation + dual-graph report
Def-use extraction; narrative-vs-data-flow agreement metric.
**Acceptance:** metric computed for both runs; DAG `strength`/`confidence`
surfaced; propagation output labeled narrative-only where unsupported.

### Phase 5 — What-if rule edit
`cli/whatif.py` orchestrating existing modules + Layer 2 replay.
**Acceptance:** an edit reproducing a `mortgage_tier1` fixture edit yields the
same witness set as RegDelta does for that edit.

### Phase 6 — UI
Scenario Lab / Behavior Explorer / Impact Analyzer; BPMN/CMMN annotation.

### Phase 7 (optional, gated) — real SMT backend
Z3 behind the existing `utils/smt.py` interface. **Deferred deliberately:**
Finding B shows it is not needed for v1. Justified only if real-interval
domains grow.

**Reproduction of §2:**
```bash
.venv/bin/python3 -m pytest ui/tests/ -q          # existing gates unaffected
# measurement scripts to be added under scripts/ in Phase 0
```

---

## 11. Risks

| Risk | Mitigation |
| --- | --- |
| **Cohort mistaken for a population** — the most damaging failure mode | Schema-level: no cohort carries a weight/frequency field. Copy says "of N generated cases". Persona cohorts flagged and barred from exposure stats. |
| Behavioral findings blamed on rules when the cohort is inadequate | Always report cohort coverage beside every finding. |
| Half the population invisible | Refused rules stay in every denominator, per existing discipline. |
| Context resolution reintroduces the universal-scope bug | Unresolvable dimension stays `unknown`; default-off; existing test retained unchanged. |
| Narrative DAG treated as sound dependency | Dual-graph report; explicit labeling; agreement metric published. |
| Combinatorial explosion | n-wise capping; `MAX_ASSIGNMENTS` respected; cohort size budgeted per run. |
| Scope creep into operational simulation | §1 and §9 are the standing answer. |

---

## 12. Open questions

1. **Context granularity** — one context per cohort, or per case? Per case is
   more expressive (mixed as-of dates) and more complex. Recommendation: per
   cohort in v1, per case override later.
2. **Where does behavior run?** A new agent_12, part of agent_11, or an
   out-of-band CLI over retained runs? Recommendation: out-of-band CLI first —
   it needs no pipeline change and can run against every retained run
   immediately.
3. **Is `document_version` fixable at the extraction contract level?** It is
   free prose today and can never be machine-resolved as-is (§2, Finding A).
4. **Does symbol canonicalization belong to agent_06 or agent_11?** Determines
   whether Finding C is fixable inside the existing pipeline or needs a new
   stage. Out of scope here; blocking for rule-network simulation.
5. **CMMN investment** — needs the industry-status verification noted in §8.

---

## 13. Sources

Cited in `plan/proposal.md` §3 and relied on here:

- [Semantics and Analysis of DMN Decision Tables](https://arxiv.org/abs/1603.07466) — overlap and completeness foundations
- [From Legal Text to Executable Decision Models](https://arxiv.org/abs/2604.17153) — structural similarity vs behavioral equivalence
- [RC4PC: Impact analysis of regulatory requirement changes on business process compliance](https://www.sciencedirect.com/science/article/pii/S0950584926000686)
- [Automated Discovery of Business Process Simulation Models from Event Logs](https://arxiv.org/abs/1910.05404) — why operational simulation needs event logs this project lacks

Verified during this review (§8):

- [How CMMN never lived up to its potential](https://camunda.com/blog/2020/08/how-cmmn-never-lived-up-to-its-potential/) — Camunda, 2020
- [Support for Case management in Camunda](https://forum.camunda.io/t/support-for-case-management-in-camunda/38860) — CMMN absent from Camunda 8
- [CMMN Patterns Made Easily with BPMN](https://camunda.com/blog/2023/07/cmmn-patterns-bpmn/) — the recommended replacement
- [Drools DMN FEEL handbook](https://kiegroup.github.io/dmn-feel-handbook/) — BE-4 engine candidate
- [pyDMNrules](https://github.com/russellmcdonell/pyDMNrules) — DMN 1.3, but Excel-driven
- [bkflow-dmn](https://github.com/TencentBlueKing/bkflow-dmn) — Python + FEEL, dict-driven
- [SpiffWorkflow decision tables](https://spiff-arena.readthedocs.io/en/latest/reference/bpmn/decision_tables.html) — Python expressions, not FEEL

Standard techniques referenced without novel claim: boundary-value analysis and
equivalence partitioning; combinatorial (n-wise) testing; MC/DC-style condition
coverage; program slicing and change impact analysis; regression test
selection; mutation testing (already used at `scripts/lowering_mutation.py`).

**Research caveat:** the repository audit and every §2 measurement are
first-hand, reproducible, and complete. The CMMN status and DMN-engine
findings in §8 were verified against the sources listed above. Broader
literature on decision-table verification, combinatorial test generation, and
change impact analysis was **not** systematically surveyed for this draft
(background research agents were terminated by an API spend limit); the
standard techniques named above are well established but the survey should be
completed before §5's generator design is treated as final.
