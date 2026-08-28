# RegDelta: Source-Grounded Differential Execution for Regulatory Change Impact

## Executive summary

This proposal narrows the research objective from a general business simulator
to a problem that the current compliance-to-code system can support and that
open benchmarks can evaluate:

> Given old and revised policy text plus a cohort of cases, compile both policy
> versions, determine which cases and executable effects change, generate
> concrete witnesses, quantify the affected population, and trace every result
> to the changed source provisions.

The proposed system, **RegDelta**, is a source-grounded regulatory
change-impact engine. Its scientific contribution is behavioral differential
execution rather than textual change detection alone. It compares the behavior
of executable old and new policy programs, reports uncertainty and refusals,
and distinguishes observed scenario exposure from uncalibrated business risk.

The evaluation uses two complementary open resources:

1. **OpenExempt-CF** (Counterfactual), a scalable controlled-change benchmark
   derived from the CC BY 4.0 OpenExempt statutes, scenario generator, and
   deterministic solver.
2. **RegelRecht-Real**, a smaller real-change evaluation using versioned,
   executable Dutch laws and legal scenarios from the EUPL-licensed RegelRecht
   project.

DeonticBench and the Dutch legal-text-to-DMN corpus remain supporting transfer
and compiler evaluations. Public process-mining logs are deferred because they
do not include aligned regulation versions, gold rule mappings, or gold
change-impact labels.

## 1. Problem statement

Organizations need to understand more than whether regulatory wording changed.
They need to know:

- which executable conditions, effects, exceptions, and scopes changed;
- which existing or prospective cases receive different outcomes;
- which obligations or other executable effects activate or deactivate;
- which downstream rules may need reevaluation;
- how many cases are exposed to the change and by how much; and
- which source provisions justify each reported impact.

For an old policy document $D_0$, a revised document $D_1$, their compiled
programs $P_0$ and $P_1$, and a scenario cohort $X$, the primary object of
study is the behavioral change set:

$$
X_\Delta = \{x \in X \mid P_0(x) \neq P_1(x)\}.
$$

For each $x \in X_\Delta$, the system should report the old result, new
result, semantic reason for the difference, affected rule path, and supporting
source evidence. Aggregate analysis should report affected-case prevalence,
decision-flip matrices, monetary deltas where available, activated or
deactivated effects, and exact incremental-recomputation savings.

## 2. Research question and hypothesis

### Primary research question

> Can source-grounded differential execution identify the behavioral impact of
> a regulatory revision more accurately than textual, LLM-only, or structural
> rule-diff approaches, while explicitly abstaining when the revision cannot be
> executed safely?

### Secondary questions

1. How much error comes from policy extraction, rule-version alignment,
   execution, and impact propagation respectively?
2. Do solver-generated and boundary-focused witnesses improve the
   completeness and reviewability of change-impact reports?
3. Can incremental impact propagation reproduce full replay exactly while
   reevaluating fewer rules and cases?
4. How well do results from controlled policy changes transfer to genuine
   regulatory version changes?

### Hypothesis

Behavioral comparison of source-grounded executable programs will identify
affected cases and output changes more accurately than text diff, artifact
hashing, or direct LLM prediction. Fail-closed compilation will reduce coverage
but improve precision by preventing unsupported constructs from being silently
approximated.

## 3. Relationship to prior work

RegDelta must not claim to be the first regulatory change-impact system.
Barrientos, Winter, and Rinderle-Ma's 2026 RC4PC approach formalizes regulatory
requirements with deontic logic, extracts atomic changes, and assesses their
effect on business-process compliance. RegDelta differs by making differential
execution and automatically labeled affected-case sets the primary object of
evaluation, rather than only identifying atomic requirement changes and
compliance deviations.

Relevant foundations include:

- [RC4PC: Impact analysis of regulatory requirement changes on business process compliance](https://www.sciencedirect.com/science/article/pii/S0950584926000686)
- [OpenExempt](https://arxiv.org/abs/2601.13183), which supplies dynamically
  generated legal cases and deterministic executable answers.
- [DeonticBench](https://arxiv.org/abs/2604.04443), which supplies legal and
  regulatory cases with labels and reference Prolog programs.
- [From Legal Text to Executable Decision Models](https://arxiv.org/abs/2604.17153),
  which releases 95 production DMN models paired with Dutch legal text and
  demonstrates that structural similarity and behavioral equivalence are
  complementary.
- [Semantics and Analysis of DMN Decision Tables](https://arxiv.org/abs/1603.07466),
  which provides formal foundations for overlap and completeness analysis.
- [Automated Discovery of Business Process Simulation Models from Event Logs](https://arxiv.org/abs/1910.05404),
  which motivates later operational simulation but does not provide regulatory
  change ground truth.

The intended novelty is the combination of source-grounded compilation,
semantic rule-version alignment, differential execution, concrete witnesses,
case-level exposure measurement, exact incremental recomputation, and explicit
refusal semantics.

## 4. Corrections to the current capability assessment

The proposal depends on an accurate boundary around the repository's current
implementation.

### 4.1 Current strengths

The repository already provides:

- an eleven-agent, source-grounded extraction and validation pipeline;
- a typed v2 rule contract with conditions, effects, variables, evidence, and
  review status;
- LExec IR v1 and fail-closed lowering for a bounded executable subset;
- a reference evaluator and bounded proof/query utilities;
- bounded comparison of known, proved UNIQUE/ANY decision tables;
- dependency DAG generation;
- DMN/BPMN review projections;
- a run comparison and review UI; and
- retained public benchmark adapters and artifacts.

### 4.2 Capabilities that do not yet exist

The repository does **not** yet provide:

- semantic rule matching across independently extracted versions;
- a live pipeline stage that emits and executes canonical LExec IR;
- a general old/new semantic change-impact engine;
- behaviorally certified `agent_11` DMN/BPMN artifacts;
- operational process simulation with resources, durations, probabilities, or
  event-log calibration; or
- a calibrated probability, severity, or expected-loss risk model.

The UI's current comparison is conservative: it compares exact rule IDs and
structural/evidence hashes. `agent_11`'s DMN/BPMN outputs are review projections,
not a standards-engine behavioral oracle. Unsupported DMN predicates may be
rendered as `false`, and the generated BPMN primarily orders business-rule
tasks by the dependency DAG. Those artifacts must not be used as the semantic
foundation of RegDelta.

The canonical LExec compiler, evaluator, and proof records should instead
become the execution boundary. Review projections should remain visibly
separate from executable, proved artifacts.

## 5. Scope and claim boundary

### 5.1 In scope

- old/new policy compilation within the supported LExec subset;
- source- and structure-aware rule alignment;
- semantic classification of rule changes;
- replay of fixed historical or generated scenarios;
- changed-decision and changed-output detection;
- activation/deactivation of executable effects when the benchmark provides a
  valid oracle;
- solver- or boundary-generated witnesses;
- downstream rule-impact propagation;
- quantitative scenario exposure; and
- provenance-complete review artifacts and UI views.

### 5.2 Out of scope for the first paper

- universal business-process simulation;
- real staffing, queueing, or cycle-time forecasts;
- expected financial or reputational loss;
- arbitrary optimization and temporal legal reasoning;
- complete obligation recall across unrestricted legal text;
- production-grade BPMN process discovery;
- legal correctness beyond the benchmark's gold programs; and
- claims that synthetic counterfactual changes fully represent naturally
  occurring amendments.

### 5.3 Risk terminology

The first system must distinguish:

- **structural concern**: a high-importance rule or control is affected;
- **scenario exposure**: the number or share of evaluated cases affected; and
- **expected risk**: calibrated probability multiplied by quantified
  consequence.

Only the first two are supported initially. Expected risk requires independent
probability, severity, and calibration data. The existing extracted
`risk_level` field is metadata, not a quantitative risk estimate.

## 6. Proposed RegDelta system

### 6.1 End-to-end flow

```text
old and new policy text
          |
          v
old and new grounded rule graphs
          |
          v
old and new fail-closed LExec programs
          |
          v
rule alignment and semantic change classification
          |
          v
differential execution over a fixed case cohort
          |
          v
affected cases, witnesses, and changed effects
          |
          v
downstream dependency propagation
          |
          v
source-grounded impact report and review UI
```

### 6.2 Outputs for an affected case

```text
Case:                      OE-AZ-00491
Changed source:            Ariz. Rev. Stat. section 33-1125(8)
Semantic edit:             vehicle exemption cap 15,000 -> 18,000
Old output:                3,000 non-exempt
New output:                0 non-exempt
Monetary delta:            -3,000
Directly changed rule:     AZ-33-1125-8
Potential downstream:      exemption valuation, non-exempt total
Evidence status:           source and gold program aligned
Execution status:          observed by replay
```

### 6.3 Change taxonomy

The semantic differ should recognize:

- rule addition and removal;
- condition strengthening and weakening;
- threshold or constant change;
- output/effect change;
- modality change;
- exception addition and removal;
- scope change;
- priority or hit-policy change;
- dependency change;
- semantically unchanged textual edits; and
- unresolved or ambiguous alignment.

### 6.4 Rule alignment

Alignment should proceed in this order:

1. exact benchmark ID or regulatory citation;
2. stable source section and output signature;
3. normalized predicate/effect structure;
4. constrained semantic similarity; and
5. explicit review when ambiguity remains.

The alignment contract must support one-to-one, one-to-many, split, merge,
added, removed, and unresolved mappings. Embedding similarity alone must never
silently establish identity.

### 6.5 Impact propagation

For document/version delta $D$ and executable layer $L$:

- `Direct(D,L)` contains active consumers whose selected evidence, condition,
  effect, or output changed.
- `Potential(D,L)` is the executable downstream closure of `Direct(D,L)`.
- `Recompute(D,L)` contains potential nodes whose input fingerprint changed.

Full replay is the correctness oracle. Incremental execution may claim savings
only when its observable outputs exactly match full replay.

## 7. Open benchmark design

No mature open resource located during this review combines natural old/new
regulations, executable versions, business cases, process traces, rule-process
mappings, and quantitative risk labels. RegDelta therefore uses a scalable
controlled benchmark plus a small genuine-version evaluation.

### 7.1 OpenExempt-CF: primary scalable benchmark

[OpenExempt](https://github.com/servantez/OpenExempt) is CC BY 4.0 and provides
expert-structured U.S. bankruptcy exemption statutes, natural-language
statutory descriptions, configurable case generation, and a deterministic
branch-and-bound solver. Its released benchmark contains 9,765 samples across
nine evaluation suites.

OpenExempt-CF will create controlled old/new policy pairs while preserving an
executable gold oracle. Each change must modify both the natural-language
statute and its structured executable field.

#### Initial mutation families

Only changes compatible with the initial LExec subset are admitted:

- numeric cap increase or decrease;
- boolean applicability change;
- enumerated-category inclusion or exclusion;
- simple rule addition or removal; and
- simple condition strengthening or weakening.

The first version targets OpenExempt's exemption-valuation stage. Full optimal
allocation and non-exempt-asset optimization remain excluded until a separate
optimizer semantics is implemented.

#### Gold construction

For each fixed case $x$:

```python
old_result = official_solver(old_statutes, x)
new_result = official_solver(new_statutes, x)
gold_changed = observable(old_result) != observable(new_result)
if gold_changed:
    gold_impacts.append({
        "case_id": x.id,
        "old_result": observable(old_result),
        "new_result": observable(new_result),
    })
```

The mutation generator must validate that:

- the edited citation and field exist;
- the old source text expresses the old executable value;
- the new source text expresses the new executable value;
- the edit manifest matches the program delta;
- old and new programs execute successfully; and
- the same case object is used on both sides.

#### Pair contract

```json
{
  "schema_version": "regdelta-pair/1.0",
  "pair_id": "arizona_vehicle_limit_001",
  "source": {
    "benchmark": "openexempt",
    "license": "CC-BY-4.0",
    "upstream_commit": "pinned-sha"
  },
  "old": {
    "text": "...not exceeding $15,000...",
    "gold_program": {},
    "version": "v0"
  },
  "new": {
    "text": "...not exceeding $18,000...",
    "gold_program": {},
    "version": "v1"
  },
  "edit_manifest": [],
  "scenarios": [],
  "gold_impacts": []
}
```

### 7.2 RegelRecht-Real: genuine version changes

The Dutch government's [RegelRecht](https://github.com/MinBZK/regelrecht)
project is EUPL-1.2-licensed and supplies an execution engine, editor, and BDD
legal scenarios. The versioned legal source text and machine-readable law
encodings are published separately in the companion
[regelrecht-corpus](https://github.com/MinBZK/regelrecht-corpus) repository as
dated YAML files (for example a `wet_op_de_zorgtoeslag` law with both a
`2024-01-01.yaml` and a `2025-01-01.yaml` version). The adapter must pin both
repositories by commit SHA so the genuine pairs below are reproducible from a
clean checkout.

The inspected public repositories contain three genuine 2024-to-2025 pairs:

- the standard health-insurance premium regulation;
- the Dutch Income Tax Act; and
- the Dutch Health Care Allowance Act.

The Health Care Allowance versions contain genuine changes to premium values,
income thresholds, percentages, and asset limits. These pairs provide a small
real-revision evaluation rather than a scalable primary benchmark.

Only constructs executable by both RegelRecht and the supported RegDelta
backend should be scored. Nested arithmetic, conditional external calls,
rounding, and unsupported date operations remain explicit refusals until LExec
is extended and independently tested.

### 7.3 Supporting evaluations

| Resource | Role | Limitation for change-impact evaluation |
| --- | --- | --- |
| [DeonticBench](https://github.com/guangyaodou/DeonticBench) | Regression and transfer over 6,483 labeled cases (whole + hard splits, already vendored under `compliance-files/deonticbench/`) and reference Prolog | No natural old/new version pairs |
| [Dutch legal-text-to-DMN corpus](https://github.com/opengov-lab/legal-text-to-decision-model) | Text-to-executable compiler evaluation over 95 production models | One regulatory version per model |
| [IEEE process-mining event logs](https://www.tf-pm.org/resources/logs) | Future process-distribution and timing calibration | No aligned regulation versions or gold rule mappings |
| RC4PC data | Optional external baseline if it can be pinned and licensed reproducibly | Availability must be verified before it enters the committed protocol |

## 8. Experimental design

The evaluation separates errors caused by the impact engine from errors caused
by extracting executable rules from text.

### 8.1 Experiment A: gold-program impact analysis

Inputs are old and new gold programs plus a fixed scenario cohort. This
provider-free experiment measures:

- affected-case detection;
- output-delta correctness;
- witness validity;
- effect activation/deactivation where gold semantics exist; and
- incremental/full-replay equivalence.

The impact engine should achieve exact agreement with the external benchmark
solver for all admitted constructs.

### 8.2 Experiment B: text-to-program compilation

Inputs are old and new natural-language policy versions. Extracted programs are
compared independently with the corresponding gold programs. This measures:

- changed-predicate and changed-effect accuracy;
- preservation of unchanged rules;
- source-edit localization;
- refusal correctness; and
- executable coverage.

### 8.3 Experiment C: end-to-end text-to-impact

Inputs are only old/new text and held-out scenarios. The complete system is
scored on affected-case detection, old/new outcomes, output deltas, and source
attribution.

This decomposition attributes failures to extraction, alignment, execution, or
propagation rather than collapsing them into one number.

### 8.4 Dataset splitting

Splits occur at the **policy-pair level**, not the scenario level. Scenarios
derived from a policy mutation may not cross train/development/test boundaries.
The fixed split manifest must pin upstream commit, mutation configuration,
random seed, case hashes, and solver version. This splitting protocol applies
to OpenExempt-CF, whose mutation generator can produce enough pairs for a
meaningful train/development/test partition.

RegelRecht-Real is held out entirely as an evaluation-only resource. With only
three genuine version pairs, no train/development split of it is meaningful;
none of its pairs, scenarios, or results may be used for prompt tuning,
threshold selection, or model/configuration selection that is later scored
against it.

## 9. Baselines and ablations

### Baselines

1. sentence-level textual diff;
2. the current exact-ID and structural/evidence-hash comparison;
3. LLM-only atomic change extraction in the style of requirement-delta work;
4. structural LExec diff without execution; and
5. direct LLM prediction of affected cases.

RegDelta's full semantic differential-execution system (Sections 6-8) is the
proposed system evaluated against baselines 1-5 under the same scenario
cohort and metrics; it is the point of comparison, not itself a baseline.

### Ablations

- without source provenance;
- without rule normalization;
- without semantic execution;
- without witness generation;
- without dependency propagation;
- without fail-closed refusal; and
- exact-ID alignment versus semantic alignment.

## 10. Metrics

### Primary metrics

- changed-rule precision, recall, and F1;
- affected-case precision, recall, and F1;
- old/new outcome exact accuracy;
- monetary-delta exact accuracy and mean absolute error;
- source-edit localization precision and recall;
- valid-witness rate;
- refusal correctness and executable coverage;
- traceability completeness;
- runtime and provider cost;
- incremental recomputation savings; and
- exact incremental/full-replay agreement.

### Coverage-risk reporting

Accuracy must be reported jointly with executable coverage. Refused cases
remain in the denominator of corpus coverage and may not be discarded from
retained results. Results should include the correctness-versus-coverage
frontier rather than only accuracy on admitted cases.

## 11. Implementation plan

### Phase 1: executable pipeline boundary

Integrate LExec into the live pipeline and clearly separate executable outputs
from review projections.

Proposed `agent_11` output:

```text
agent_11-executable-models/
  lexec_ir.json
  compilation_report.json
  proof_records.json
  executable_decisions.dmn
  review_projection.dmn
  review_projection.bpmn
```

Execution steps:

1. Reconcile the graph shape `utils/lexec_ir.py`'s `lower_graph` expects with
   the shape Agent 06 actually emits
   (`optimized_compliance_knowledge_graph.json`), since `agent_11` currently
   reads that graph through `utils/executable_models.py`, not
   `utils/lexec_ir.py`.
2. Add a compilation step (extend `utils/lexec_ir.py` or add
   `utils/lexec_backend.py`) that lowers a frozen `lexec-ir/1.0` document unit
   into (a) an executable DMN document containing only non-refused rules and
   (b) `proof_records.json` capturing per-rule UNIQUE/ANY completeness and
   overlap results, reusing the bounded proof utilities already referenced in
   Section 4.1.
3. Rewrite `agents/agent_11_executable_model_generator.py` to: call
   `lower_graph` on Agent 06's optimized graph to produce `lexec_ir.json` and
   `compilation_report.json` (the refusal and `ignored_fields` ledger from
   Section 4.1's fail-closed lowering); compile only non-refused IR rules into
   `executable_decisions.dmn` and `proof_records.json`; and keep today's
   `build_graph_dmn`/`build_dags_bpmn` output, renamed to
   `review_projection.dmn`/`review_projection.bpmn`, behaviorally unchanged so
   existing review-UI consumers keep working.
4. Update `utils/config.py`'s executable-models directory contract and
   `docs/executable-models.md` to document the new six-file
   `agent_11-executable-models/` layout shown above.
5. Add `tests/test_agent_11_lexec_boundary.py` asserting: every graph rule
   appears in exactly one of `lexec_ir.json`'s `rules` (executable) or
   `refusals`, never both; `executable_decisions.dmn` contains only
   non-refused rule IDs; and `review_projection.dmn`/`.bpmn` remain
   byte-identical to today's `compliance_decisions.dmn`/`compliance_workflows.bpmn`
   for existing fixtures (a regression guard against silently changing review
   behavior while adding the executable path).
6. Re-run the existing end-to-end fixtures (for example
   `pipeline-output/e2e-mortgage-20260827/`) through the updated `agent_11`
   and diff the new artifacts against the acceptance criteria before merging.
7. Record the above as explicit task entries (ID, dependencies, acceptance
   commands, evidence paths) in a RegDelta task registry, per `plan/README.md`'s
   instruction that RegDelta implementation tasks update or replace
   `plan/tasks.json` rather than inheriting legacy statuses.

Acceptance criteria:

- every rule is executable, refused, or review-only;
- unsupported predicates never silently become executable `false`;
- all executable rules retain source provenance;
- proof and refusal records are schema-valid; and
- reference execution is covered by unit and end-to-end tests.

### Phase 2: gold differential engine

Implement:

- old/new IR comparison;
- rule-version alignment contract;
- semantic change taxonomy;
- scenario replay;
- witness generation;
- downstream impact propagation; and
- full-versus-incremental comparison.

Execution steps:

1. Add `utils/rule_alignment.py` implementing the Section 6.4 alignment order
   (exact ID/citation, then source-section-plus-output-signature, then
   normalized predicate/effect structure, then constrained semantic
   similarity, then explicit review) and returning one-to-one, one-to-many,
   split, merge, added, removed, and unresolved mappings.
2. Add `utils/semantic_diff.py` implementing the Section 6.3 taxonomy as a
   closed classification (`classify_change(old_rule_ir, new_rule_ir,
   alignment) -> ChangeKind`) so every aligned rule pair resolves to exactly
   one taxonomy entry.
3. Add `utils/impact_propagation.py` implementing `Direct(D,L)`,
   `Potential(D,L)`, and `Recompute(D,L)` (Section 6.5) over the existing
   dependency DAG from `agent_10_dag_generator.py`, plus a `replay(old_ir,
   new_ir, cases)` function that is the full-replay correctness oracle.
4. Add `utils/witness_generation.py` for solver- and boundary-focused witness
   search restricted to the LExec-supported subset (numeric boundary probes,
   boolean flips, enum edge cases matching the Section 7.1 mutation
   families).
5. Add `cli/regdelta_diff.py` orchestrating the four modules above over two
   `lexec_ir.json` document units and a scenario cohort, emitting the Section
   12 impact-report contract (`regdelta-impact/1.0`).
6. Add `tests/test_impact_propagation.py` and `tests/test_semantic_diff.py`
   with deterministic fixtures; assert `Recompute` results exactly match full
   `replay` output on every fixture before any incremental-savings claim is
   made.
7. Add `docs/regdelta_impact_contract.md` documenting the schema and worked
   examples, in the style of `docs/ir-semantics-v1.md`.

Acceptance criteria:

- exact agreement with full replay on all deterministic fixtures;
- explicit refusal for unsupported table policies and theories;
- witnesses reproduce every reported difference; and
- convergent graph paths are deduplicated for execution but retained for
  explanation.

### Phase 3: OpenExempt-CF adapter

Implement:

- pinned upstream acquisition and license manifest;
- fixed-seed case generation;
- text/program mutation generation;
- external-solver gold replay;
- change-pair and result schemas; and
- corpus validators.

Execution steps:

1. Add `bench/adapters/openexempt_cf.py` following the not-vendored,
   pinned-commit pattern already used by `bench/adapters/dutch_dmn.py`:
   OpenExempt itself is never vendored, only its upstream commit SHA,
   license, and path conventions are recorded.
2. Add `scripts/fetch_openexempt.sh`, mirroring the clone-and-pin recipe in
   `docs/anchor_aggregation_recipe.md`, that clones `servantez/OpenExempt` at
   a pinned SHA into a scratch directory (never into the repository).
3. Add `bench/openexempt_mutate.py` implementing the five Section 7.1
   mutation families (numeric cap change, boolean applicability change,
   enumerated inclusion/exclusion, simple rule add/remove, condition
   strengthen/weaken) and the five gold-construction validations from that
   section (citation/field existence, old/new text-value agreement,
   edit-manifest/program-delta agreement, successful execution on both
   sides, identical case object).
4. Add `scripts/build_openexempt_cf_split.py` producing a frozen split
   manifest under `bench/splits/` that pins upstream commit, mutation
   configuration, random seed, case hashes, and solver version (Section 8.4).
5. Add a `bench/schemas/regdelta_pair-1.0.schema.json` validating the Section
   7.1 pair-contract JSON, plus `scripts/validate_openexempt_cf_corpus.py`
   checking every pair against the acceptance criteria below.
6. Add `tests/test_openexempt_cf_adapter.py` covering the mutation
   generator's five validations and the corpus validator using small
   synthetic fixtures, so CI never requires network access.
7. Document license and attribution in `benchmarks/README.md` and
   `benchmarks/datasets.json`, matching the existing DeonticBench and Dutch
   DMN entries' format.

Acceptance criteria:

- clean-checkout provider-free reproduction;
- byte- and hash-pinned benchmark manifests;
- validated agreement between source text, edit manifest, and executable
  mutation; and
- retained successful, failed, and refused records for every expected pair.

### Phase 4: end-to-end benchmark

Run both versions through the complete extraction and compilation pipeline,
align the extracted rules, execute supported cases, and compare the resulting
impact set with OpenExempt gold.

Execution steps:

1. Add `scripts/run_openexempt_cf_e2e.py` that pushes each pair's old/new
   statute text through the agent 01-11 pipeline (`cli/extract.py`), aligns
   the two extracted `lexec_ir.json` outputs with `utils/rule_alignment.py`,
   runs `cli/regdelta_diff.py`, and compares the resulting impact set against
   the pair's `gold_impacts`.
2. Wire the Section 9 baselines (sentence-level diff, exact-ID/hash
   comparison, LLM-only atomic-change extraction, structural LExec diff
   without execution, direct LLM prediction) into the same runner as
   alternate `--baseline` modes, so all configurations share one metrics
   path.
3. Implement the Section 9 ablations as `--ablate
   {provenance,normalization,execution,witness,propagation,fail_closed,exact_id_alignment}`
   flags on the same runner.
4. Add metric computation (extend `utils/metric_contract.py` or add
   `utils/regdelta_metrics.py`) covering every Section 10 primary metric plus
   the coverage-risk frontier, writing results under
   `results/aggregates/regdelta/`.
5. Enforce Section 8.4's pair-level, single-estimator split rules with a
   `bench/manifest.py`-style validator before any result is retained.
6. Add `tests/test_openexempt_cf_e2e_contract.py` asserting retained results
   always include successful, failed, and refused records for every expected
   pair, and that no baseline or ablation configuration is silently dropped.

Acceptance criteria:

- predeclared pair-level splits;
- all baseline and ablation configurations retained;
- no best-of-k and mean estimator mixing;
- complete configuration, prompt, model, seed, and artifact hashes; and
- separate gold-program, compilation, and end-to-end results.

### Phase 5: RegelRecht real-change evaluation

Implement a pinned adapter for supported 2024/2025 law pairs and run the
official external engine as the oracle.

Execution steps:

1. Add `bench/adapters/regelrecht.py` (not-vendored) pinning both
   `MinBZK/regelrecht` (engine) and `MinBZK/regelrecht-corpus` (dated law
   YAML) commit SHAs, and enumerating the three 2024/2025 pairs named in
   Section 7.2.
2. Add `scripts/fetch_regelrecht.sh`, mirroring the OpenExempt fetch recipe,
   cloning both repositories into a scratch directory at their pinned SHAs.
3. Add `bench/regelrecht_scope.py` that statically scans each YAML law's
   operations against the LExec-supported construct list and emits an
   explicit refusal record for every unsupported construct (nested
   arithmetic, conditional external calls, rounding, unsupported date
   operations) rather than skipping it silently.
4. Add `bench/regelrecht_oracle.py` wrapping RegelRecht's own execution
   engine as the external oracle via the same JSON-lines harness protocol
   used by `bench/harness.py`/`bench/dmn_engine_harness.py`.
5. Add `tests/test_regelrecht_adapter.py` with small fixture laws (not the
   real corpus) verifying the scope-scan and harness-protocol wiring.
6. Add `docs/regelrecht_real_protocol.md` documenting the pinned commits,
   in-scope provisions, and reproduction commands, in the structure of
   `docs/anchor_aggregation_recipe.md`.

Acceptance criteria:

- each included provision has old/new text and executable artifacts;
- included scenarios execute under both versions;
- unsupported constructs remain visible refusals; and
- every reported impact is reproducible with the external engine.

### Phase 6: review UI and paper

Extend the workbench with:

- source redline;
- rule-alignment status;
- semantic change categories;
- affected-case tables;
- old/new outcome comparison;
- witness exploration;
- impacted-rule DAGs;
- proved, observed, uncertain, and refused states; and
- downloadable impact reports.

Execution steps:

1. Extend `ui/backend` with endpoints/serializers for the Section 12 impact-
   report contract (`rule_alignments`, `semantic_changes`, `affected_cases`,
   `witnesses`, `downstream_impacts`, `refusals`, `provenance`).
2. Extend `ui/frontend` with the views listed above, reusing the existing
   layered rule-graph UI for the impacted-rule DAGs and adding proved/
   observed/uncertain/refused state badges and a downloadable-report action.
3. Add `ui/backend` and `ui/frontend` component tests for the new views,
   following the conventions already recorded in `ui/IMPLEMENTATION_STATUS.md`
   and `ui/contracts.md`.
4. Draft new `paper/sections/` content for RegDelta, using
   `paper/EXPERIMENT_RUNBOOK.md`'s existing experiment-tracking conventions,
   reporting controlled (OpenExempt-CF) and genuine (RegelRecht-Real) results
   in clearly separate tables.
5. Update `paper/tables/` and `paper/figures/` generation scripts to consume
   `results/aggregates/regdelta/` from Phase 4.

The paper must report controlled and genuine changes separately and must not
convert engineering test coverage, fixture mutation score, or structural
similarity into semantic-quality claims.

## 12. Impact report contract

```json
{
  "schema_version": "regdelta-impact/1.0",
  "pair_id": "...",
  "rule_alignments": [],
  "semantic_changes": [],
  "affected_cases": [],
  "witnesses": [],
  "downstream_impacts": [],
  "refusals": [],
  "provenance": [],
  "metrics": {}
}
```

All outputs must retain source digests, upstream versions, configuration,
prompts, model and reasoning settings, solver versions, random seeds, execution
hashes, and result status.

## 13. Defensible claims

If supported by the experiments, the project may claim:

- behavioral impact detection within a declared executable subset;
- automatically generated affected-case sets and counterexamples;
- exact incremental/full-replay agreement;
- improved impact prediction over textual and structural baselines;
- source-grounded impact explanations; and
- calibrated refusal outside supported semantics.

It may not claim:

- complete regulatory obligation capture;
- general business-process simulation;
- real staffing, cycle-time, or cost impact;
- expected compliance risk;
- production-grade BPMN execution;
- unrestricted legal-domain generalization; or
- legal correctness beyond benchmark gold programs.

## 14. Publication position

The strongest first paper is about **behavioral regulatory change impact**, not
a universal business simulator. The most natural venues are ICAIL, BPM, CAiSE,
ICSE, or ASE. A major AI datasets-and-benchmarks track becomes plausible if
OpenExempt-CF is released as a substantial, reproducible benchmark with strong
baselines and a genuine-version evaluation.

Operational business simulation should be a later extension. It would add
rule-to-task mappings, process event logs, resources, durations, branching
probabilities, costs, and calibrated consequences. None of those are required
to establish the first paper's central contribution.

## 15. Final recommendation

Proceed with RegDelta under the following scope:

> Compile old and new regulations, determine their behavioral differences,
> generate concrete affected cases, propagate impacts through executable rule
> dependencies, quantify scenario exposure, and preserve source evidence and
> refusals end to end.

OpenExempt provides scalable automatic gold data. RegelRecht provides genuine
versioned regulations and an external execution oracle. The current repository
provides most of the extraction, IR, proof, DAG, and review substrate, but the
canonical compiler must be integrated into the pipeline and semantic
cross-version comparison must be implemented before impact claims are made.
