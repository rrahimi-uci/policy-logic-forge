# NeurIPS 2027 — executable development plan

**Companion to:** [`neurIips-proposal-2027.md`](neurIips-proposal-2027.md)

**Plan contract:** [`tasks.json`](tasks.json)

**Compiler IR contract:** [`lexec-ir-v1.schema.json`](lexec-ir-v1.schema.json)

This document is the human-readable operating plan for the NeurIPS 2027 work.
The task registry is authoritative for task IDs, dependencies, status, effort,
acceptance commands, artifacts, and scope membership. This document is
authoritative for research definitions, claim boundaries, and stop/go rules.

“Executable” means that every registered task has machine-readable
prerequisites, an argv-form acceptance command, an artifact target, and a
claim boundary, and that the graph can be validated and queried locally. It
does **not** mean that the planned research has already been implemented or
that a publishable result is guaranteed. At this revision, 20 person-days of
work are evidenced as complete; the compiler, benchmark, instrument study,
transfer study, and optional RL work remain future work.

## Status — 2026-08-24

<!-- GENERATED_TASK_SUMMARY_START -->
| Phase | Tasks | Total pd | Done pd | Status |
| --- | ---: | ---: | ---: | --- |
| G0 | 13 | 46 | 19 | done=8, partial=2, planned=3 |
| A | 4 | 8 | 1 | done=1, planned=2, conditional=1 |
| J | 2 | 6 | 0 | planned=2 |
| G2 | 6 | 30 | 0 | planned=6 |
| G3 | 5 | 24 | 0 | planned=5 |
| G4 | 3 | 26 | 0 | planned=3 |
| G5 | 4 | 20 | 0 | conditional=4 |
| Writing | 1 | 15 | 0 | planned=1 |

| Scope | Included pd | Done pd | Remaining pd |
| --- | ---: | ---: | ---: |
| `minimum_paper` | 125 | 20 | 105 |
| `second_domain` | 151 | 20 | 131 |
| `full_programme` | 171 | 20 | 151 |
| `minimum_plus_optional_replication` | 129 | 20 | 109 |

**Ready now:** `PIPE-2B`, `PIPE-4`, `IR-2`, `A1B`, `A3`.

Generated from [`plan/tasks.json`](tasks.json) by `scripts/validate_neurips_plan.py`; manual edits to this block fail CI.
<!-- GENERATED_TASK_SUMMARY_END -->

Status words have literal meanings:

- `done`: every registered acceptance command passes and every registered
  artifact and evidence path exists.
- `partial`: useful implementation exists, but the registered acceptance gate
  is not yet satisfied.
- `planned`: dependencies and acceptance contract are specified; work is not
  evidenced complete.
- `conditional`: out of the committed scope unless its written entry gate is
  met and the task is explicitly activated.
- `blocked`: cannot proceed without a named external decision or resource.

The registry and this summary never turn `partial`, exploratory, refused,
invalid, or unrun output into a completed result.

---

## 0. How to execute this plan

Run all commands from the repository root with the checked-in virtual
environment:

```bash
.venv/bin/python scripts/validate_neurips_plan.py --check
.venv/bin/python scripts/validate_neurips_plan.py --ready
.venv/bin/python scripts/validate_neurips_plan.py --show IR-2
.venv/bin/python scripts/validate_neurips_plan.py --run IR-2
.venv/bin/python scripts/validate_neurips_plan.py --run-done
```

`--check` validates IDs, dependency existence and acyclicity, scope closure,
status/evidence rules, acceptance command shape, completed artifacts, and the
generated summary above. `--run TASK` executes only that task's explicit argv
commands without a shell. It does not infer work, call a paid provider, send
email, or change task status. `--run-done` replays the acceptance commands of
all tasks currently marked `done`.

To complete a task:

1. Confirm all dependencies are `done` with `--show` or `--ready`.
2. Implement the task and its tests on a dedicated branch.
3. Produce the registered artifacts and preserve run provenance.
4. Run the task's registered acceptance commands.
5. Change the status and evidence fields in `plan/tasks.json` in the same PR.
6. Replace the generated summary with exact `--summary` output.
7. Run `--check`, the focused tests, and the full test suite.

The critical path has two initially independent tracks:

```text
Track A: A1A -> A1B -> J1
                    \-> A2 (optional fresh replication)
         A1A -> A3 -> PAPER-1

Track B: PIPE repairs/audits ------\
         IR-2 -> IR-1 -> backends -> J1 -> J1B -> statistics -> INST-1
         BENCH-1 -> retention -----/                              |
         BENCH-2 -> signals/statistics ---------------------------/
                                                               |
                        minimum paper: PAPER-1 <----------------/
                        extension: BENCH-1B -> ASM-1 -> CEGIR-1
                        conditional: RL-1 + RL-2 -> RL-3 -> RL-4
```

No downstream task may consume a measurement whose prerequisite is not done.

---

## 1. Operating boundaries and reproducibility

### 1.1 Evidence classes

Every result and manuscript statement must be tagged internally as one of:

| Class | Meaning | May support a paper claim? |
| --- | --- | --- |
| Implemented | Code exists and focused tests pass | Only an implementation claim |
| Run | A retained bundle records inputs, versions, and outputs | Descriptive claim only |
| Valid | The preregistered estimator and validity gates pass | Yes, within the frozen boundary |
| Exploratory | Analysis was not preregistered or was changed after inspection | Clearly labeled only |
| Refused | The system declined because evidence or semantics were insufficient | Supports coverage/refusal analysis, not correctness |
| Unrun | Specified but not executed | No |
| Invalid | A protocol, leakage, power, or provenance gate failed | No positive/negative scientific claim |

### 1.2 Authority boundaries

- Local deterministic work is the default first step.
- Paid model calls require an explicit approved run configuration and budget.
- Human annotation requires a frozen protocol, consent/ethics determination,
  adjudication rule, and approved budget before recruitment.
- Emailing upstream authors or maintainers requires the repository owner's
  approval of the exact message and recipients.
- Network downloads must be pinned by source URL, revision, license posture,
  and content hash in the retained bundle.
- `--run` is intentionally incapable of silently crossing these boundaries;
  restricted tasks use acceptance commands that verify an already approved
  artifact rather than initiating the external action.

### 1.3 Reproducibility contract

Every empirical bundle must record at least:

- repository commit and dirty-tree state;
- task registry schema version and task ID;
- source artifact IDs and SHA-256 hashes;
- dataset revision, split manifest, and license/reuse note;
- model/provider/version, decoding parameters, seed, and retry policy;
- environment and dependency lock hashes;
- per-observation outputs, failures, refusals, and exclusion reasons;
- estimator version, aggregation unit, confidence interval method, and result;
- validation status: `valid`, `exploratory`, `refused`, `unrun`, or `invalid`.

When new runtime dependencies are introduced, they must be pinned in the
repository's lock mechanism in the same PR. Anticipated dependencies include
Z3, `lxml`, Hypothesis, SciPy/statsmodels, and a pinned third-party DMN engine;
their presence is not assumed until the implementing task adds and validates
them.

---

## 2. Compiler IR contract

The canonical interchange format is **LExec IR v1**, defined structurally by
[`plan/lexec-ir-v1.schema.json`](lexec-ir-v1.schema.json). It replaces the
ambiguous idea of treating an existing `rule["execution"]` object as the
compiler IR. Existing extracted-rule JSON is an input that must be lowered;
it is not itself the executable semantics.

LExec IR v1 requires:

- a versioned document unit with source path and content hash;
- typed symbols (`bool`, `int`, `real`, `enum`, or `string`) with provenance;
- recursive, typed formulas rather than unchecked expression strings;
- an explicit applicability `scope` separate from the rule condition;
- modality attached to each effect (`obligation`, `permission`,
  `prohibition`, `definition`, or `none`), not only to the rule container;
- explicit exception structure and an exception reading of `unset`,
  `defeater`, `conjunctive`, or `ignored`;
- explicit null/missing-field and boundary-unknown semantics;
- decision tables with hit policy and proof records;
- fail-closed refusals with provenance and `requires_review: true`.

The JSON Schema guarantees shape, not meaning. `IR-1` must also create
`docs/ir-semantics-v1.md`, defining type checking, evaluation, null behavior,
boundary behavior, exception composition, conflict ordering, table overlap,
and backend equivalence. A lowering is total only when every input field is
classified as one of:

1. consumed with a provenance link;
2. intentionally ignored with a stable reason code; or
3. refused with `requires_review: true`.

Silent field loss is a correctness failure. A refusal is a measured coverage
outcome, never an incorrect successful compilation.

---

## 3. G0 — repair and freeze the measurement unit

G0 must finish before any corpus-level compiler or instrument claim.

### 3.1 Completed work

- `CFG-1`: exposes full-coverage configuration in `config.example.json`.
- `PIPE-1`: processes all source chunks. This proves read coverage, not rule
  recall.
- `PIPE-2`: re-splits oversized chunks without dropped source bytes. Duplicate
  semantic extraction from overlap remains a measured risk.
- `PIPE-3`: passes complete v2 fields into the optimizer prompt. This repairs
  context availability, not dependency accuracy.
- `A1A`: audits the upstream anchor release at a pinned revision.

### 3.2 Remaining pipeline and IR gates

- `PIPE-2B`: construct a stratified, independently annotated source-rule
  sample and report semantic rule recall with uncertainty. Source-byte
  coverage is not a substitute.
- `PIPE-4`: audit dependency precision/recall and missing-link categories on a
  frozen sample; do not infer success merely from optimizer input coverage.
- `IR-2`: run the census tool on retained real pipeline output and publish
  counts for types, operators, scopes, modalities, tables, dependencies,
  exceptions, missing fields, and unsupported constructs. A bounded NDA pilot
  now exists at `docs/theory_coverage.md` and
  `docs/expressiveness_census.md`, with provenance in
  `results/aggregates/ir2_nda_pilot/run_manifest.json`; it is explicitly
  exploratory (two documents, one pre-optimization rules batch) and is not a
  corpus estimate. The pilot exposed six rules requiring review, including
  invalid predicate operators, so IR-1 remains blocked from freezing a subset.
- `IR-1`: freeze semantics after the census, implement schema validation and
  total lowering, and refuse unsupported semantics.
- `IR-3`: implement the reference solver core plus table hit-policy proof
  obligations.

### 3.3 Benchmark gates

- `BENCH-1`: pin the Dutch adapter, source artifacts, and frozen 58/37 split.
  This is now implemented as `bench/adapters/dutch_dmn.py` plus the
  content-free, commit-pinned `bench/splits/dutch_58.json`; it freezes 24
  Outcome and 34 Requirements models without redistributing upstream files.
- `BENCH-2`: enforce gold isolation at the filesystem/container boundary.
  `bench/queries.py` stages copied source inputs and an output directory,
  rejects traversal and symlink escapes, scrubs provider credentials, and
  runs the query program with Python-level file, network, and child-process
  guards. Adversarial tests demonstrate that a known absolute gold path is
  denied. This local guard is not a kernel boundary: release jobs must also
  record a container/VM mount with gold absent and network disabled.
- `BENCH-3`: retain individual runs and label the estimator used for each
  reported aggregation. This is now implemented by `bench/manifest.py`: every
  expected model/condition/run key must have exactly one retained record,
  completed outputs are content-addressed, failures/refusals retain reasons,
  and comparisons reject mixing best-of-k with mean estimators. The contract
  does not claim that benchmark runs have been executed.
- `BENCH-4`: validate content-addressed bundles and separate redistributable
  files, scripts/manifests, and non-redistributable derived artifacts. This is
  now implemented by `bench/run_bundle.py` with path-safety, size/hash,
  required-lock/manifest, and explicit-release-allowlist checks. It rejects
  source, gold, raw, restricted, and local-only artifacts from release and
  does not claim that a benchmark bundle has been executed.

### 3.4 G0 exit gate

G0 is green only when all 13 G0 registry tasks are `done`; `--check` and all
their acceptance commands pass; the real census exists; rule and dependency
recall are reported with uncertainty; unsupported semantics refuse closed;
and gold-isolation tests pass. Until then, corpus-wide denominators are
diagnostic only.

---

## 4. Track A and join points

### 4.1 Anchor reproduction

- `A1A` is complete: it establishes what was released, not reproduced scores.
- `A1B` replays the released evaluator using released artifacts. Before any
  comparison, it must recover the exact observation unit, inclusion rules,
  aggregation, and confidence interval procedure. A mismatch is reported, not
  tuned away.
- `A2` is optional and separately preregistered. It uses fresh model
  generations only after `A1B`, with a distinct budget and no substitution of
  current-model output for the historical release.
- `A3` records license and reuse posture. Contacting authors is external
  communication and requires owner approval.

### 4.2 Join points

`J1` evaluates this repository's compiled artifacts in the pinned anchor
executor only after lowering, reference evaluation, SMT, benchmark retention,
and release-boundary gates pass. It cannot claim compiler correctness by
itself.

`J1B` chooses the exception interpretation empirically from frozen alternatives
(`defeater_or`, `conjunctive`, or explicit refusal). The selection dataset and
criterion must be frozen before inspecting downstream instrument outcomes.

---

## 5. G2 — compiler correctness

The compiler claim has two independently tested parts:

1. **Lowering correctness:** did the source/extracted representation become
   the intended LExec IR without silent loss?
2. **Backend correctness:** do evaluators and emitted artifacts implement that
   IR consistently?

Tasks:

- `LOWER-1`: compare lowering against an independent oracle with mutation,
  boundary, missing-field, modality, exception, and unsupported-construct
  cases.
- `BE-1`: implement a bounded, simple reference evaluator.
- `BE-2`: emit DMN 1.3 and validate schema, hit policy, and behavior.
- `BE-3`: implement complete SMT encoding plus satisfiability, overlap,
  coverage, conflict, counterexample, and witness queries.
- `BE-4`: cross-check selected artifacts in a pinned independent DMN engine.
- `P3P`: preserve a restricted P3-prime comparator without allowing its
  narrower language to define the main IR.

G2 succeeds only if the lowering oracle passes its frozen cases, all supported
IR programs agree across the reference and SMT backends, DMN-compatible cases
also agree with both DMN engines, and every unsupported case is an explicit
refusal. Agreement among backends derived from the same faulty lowering is not
evidence of lowering correctness.

---

## 6. G3 — validate artifact-free signals as instruments

### 6.1 Non-interchangeable measures

- **AFS — artifact-free signal:** both query generation and signal labels are
  independent of the candidate artifact and any gold executable artifact.
- **sOE — source-originated execution:** a query is generated from source, but
  its expected answer comes from gold DMN. It is a gold-labeled positive
  control, not artifact-free.
- **OE — oracle execution:** exhaustive or benchmark-defined execution against
  the gold artifact. It is the reference anchor.
- **EY — executable yield:** fraction of eligible source units that compile
  successfully under the frozen IR boundary.
- **CQI — conditional quality index:** quality among successfully compiled
  units, always reported alongside EY and refusal reasons.

No table, code comment, or paper claim may rename sOE as AFS or describe AFS as
gold-free while its labels are derived from gold DMN.

### 6.2 Frozen estimand and statistics

The observation row is `model × system × run`; observations are never reduced
to one row per system before inference. The primary estimand is Spearman
correlation between AFS and OE across runs. Confidence intervals use a
model-clustered bootstrap that resamples models and retains all associated
system/run rows.

Preregister before `INST-1`:

- primary null: **H0: population Spearman rho <= 0.30**;
- useful-signal target: point estimate `rho >= 0.60` and lower 95% clustered
  confidence bound `> 0.30`;
- alpha, bootstrap replicates, seed, missingness, exclusion, tie handling,
  multiplicity, and minimum effective cluster count;
- power curves over plausible cluster counts/effect sizes, not an unsupported
  closed-form iid calculation.

Negative controls must include leakage canaries, source/label permutations,
constant or trivial candidates, and deliberately damaged artifacts. sOE is a
positive control. If canaries are accessible or permuted controls remain
predictive, the run is invalid.

Outcomes are reported as `useful`, `weak`, `underpowered`, or `invalid` under
the frozen rule. Failure to reject H0 is not proof that rho is zero. A weak or
invalid instrument removes instrument-dependent claims from the paper; it does
not automatically create a publishable negative result.

---

## 7. G4 — transfer, assumptions, and repair

G4 is a 26 pd extension and is not included in the 125 pd minimum paper scope.

- `BENCH-1B`: adapt ContractNLI only within its supported entailment/contradiction
  boundary. It is not evidence for general policy execution semantics.
- `ASM-1`: analyze typed, provenance-bound assumptions individually **and as
  sets**. Solver tests must cover each `A_i -> h`, conjunctions and minimally
  sufficient subsets, mutual inconsistency, vacuity, and countermodels. Human
  review measures source support and acceptability; SMT validity alone does
  not make an assumption source-grounded.
- `CEGIR-1`: compare a frozen baseline with counterexample-guided repair. Every
  accepted edit must preserve source provenance, pass regression and
  counterexample suites, and improve the preregistered objective. Required
  ablations include deletion, no-op, oracle-withheld, and source-preservation
  gates. Report AFS, sOE, and OE under their correct names.

If the adapter or annotator agreement fails its frozen gate, report the
boundary and stop; do not pool an incompatible second domain into the main
claim.

---

## 8. G5 — conditional solver-reward RL

G5 is outside both the minimum paper and second-domain extension. It may be
activated only if G4 is valid, the reward components show independent signal,
the adversarial audit finds no disqualifying exploit, and a separate compute
budget is approved.

The only valid order is:

1. `RL-1`: build an independent coverage inventory.
2. `RL-2`: build held-out grounding and behavioral signals.
3. `RL-3`: adversarially audit the complete proposed reward using held-out
   cases, including reward hacking and provenance substitution.
4. `RL-4`: train only after `RL-3` passes; report the full reward/quality/
   coverage frontier and all failed runs.

Training data, reward-development data, adversarial audit data, and final test
data must be content-hash disjoint. Solver reward never substitutes for source
grounding or human acceptability.

---

## 9. Effort and scheduling

The generated status table is the sole source of numeric totals. The scopes
are cumulative:

- minimum paper: 125 pd total, 20 done, 105 remaining;
- minimum plus optional fresh-generation replication: 129 pd;
- second-domain extension: 151 pd cumulative;
- full programme including conditional RL: 171 pd cumulative.

These are engineering person-days for a contributor already fluent in the
repository. They exclude queue time, model-provider latency, author replies,
recruitment, ethics review, and scientific iteration after a failed gate.
Therefore the calendar cannot be obtained by dividing totals by headcount.

With one contributor, the minimum scope is not credible by simply serializing
105 remaining pd into the submission window. The recommended execution is:

- immediately parallelize provider-free G0 work (`IR-2`, `BENCH-3`, pipeline
  audits) with anchor replay/licensing (`A1B`, `A3`);
- freeze IR semantics only after the census;
- build reference and SMT backends in parallel after `IR-1`;
- freeze statistics before instrument outcomes are inspected;
- begin `PAPER-1` artifact plumbing early, while scientific conclusions remain
  gated on `INST-1`.

Any date commitment must add named owners, availability, external budgets, and
calendar slack. The registry deliberately stores effort and dependencies, not
fictional certainty about dates.

---

## 10. Publication outcomes

The plan enables, but does not guarantee, these defensible outcomes:

- If G2 passes: a bounded, provenance-preserving compiler and cross-backend
  correctness result for the frozen LExec IR subset.
- If G3 is valid and useful: evidence that truly artifact-free signals track
  oracle execution within the evaluated systems/models.
- If G3 is valid but weak: a bounded negative/limitations result only if power
  and measurement validity are adequate.
- If G3 is underpowered or invalid: no correlation conclusion; publishability
  must rest on other completed contributions.
- If G4 passes: a scoped transfer and counterexample-repair result.
- If G5 activates and passes: a separate solver-reward result, not an assumed
  consequence of the compiler.

The manuscript must report executable yield and refusals beside conditional
quality, distinguish current evidence from proposals, and avoid extrapolating
from one domain or fixed benchmark to policy compilation generally.

---

## 11. Risk register and automatic actions

| Risk signal | Automatic action |
| --- | --- |
| Rule/dependency recall below frozen gate | Stop corpus claims; repair extraction before compiler evaluation |
| Census shows unsupported constructs above threshold | Narrow the IR claim or implement support before freezing semantics |
| Gold path or network reachable in AFS generation | Mark run invalid; repair isolation; rerun from clean bundles |
| Lowering and shared backends agree but oracle mutations fail | Treat lowering as incorrect; backend agreement cannot rescue it |
| Independent DMN engine disagrees | Quarantine cases and classify schema, hit-policy, or semantic cause |
| Bootstrap has too few effective model clusters | Report underpowered; do not use iid rows to inflate precision |
| Negative control predicts OE or leakage canary is accessible | Mark instrument run invalid |
| Exception-reading selection changes after outcomes | Mark affected analysis exploratory and rerun on untouched data |
| Assumption set is inconsistent or vacuous | Refuse it; do not report individual implications as set validity |
| Repair improves by deletion/no-op | Reject causal repair claim and report ablation failure |
| Upstream reuse permission unresolved | Release scripts/manifests/hashes only; exclude restricted artifacts |
| RL adversarial audit fails | Do not train; report the exploit and stop G5 |

---

## 12. Decision log

| Decision | Rationale |
| --- | --- |
| `plan/tasks.json` is the task source of truth | Eliminates duplicated totals, status drift, and implicit dependencies |
| LExec IR v1 is distinct from extracted rule JSON | Separates extraction output from executable semantics |
| Modality is attached to effects | A rule can produce semantically distinct effects |
| Exception reading defaults to `unset` | Prevents silently choosing a favorable interpretation |
| Unsupported semantics refuse closed | Preserves visible failure rather than fabricating execution |
| AFS, sOE, and OE are separate measures | Prevents gold-labeled controls from being called artifact-free |
| H0 is rho <= 0.30 | Tests usefulness rather than merely nonzero association |
| Gold isolation is a mount/network boundary | Working-directory conventions do not prevent leakage |
| Assumptions are checked individually and jointly | Individual validity does not imply set consistency or sufficiency |
| CEGIR includes deletion/no-op/source-preservation ablations | Prevents trivial metric improvement from being called repair |
| RL components precede the full reward audit | A reward cannot be audited before it exists |
| A2 is optional and excluded from the 125 pd minimum | Fresh generation is scientifically distinct from released-evaluator replay |

---

## 13. Immediate executable queue

The validator currently identifies five dependency-ready tasks. Recommended
order within the two parallel tracks:

1. `IR-2`: run the existing census on retained real output; it determines the
   IR boundary.
2. `PIPE-2B` and `PIPE-4`: measure the two unresolved extraction claims.
3. `A1B`: recover and replay the released aggregation independently of Track B.
4. `A3`: draft the reuse posture; pause before external communication for owner
   approval.

Use `--show TASK` for the exact artifact and command contract. If a task's
acceptance command cannot pass without unstated setup, update that task's
contract in review before implementation; do not use undocumented operator
knowledge as part of “done.”

---

## 14. Review disposition

This revision incorporates the prior proposal and plan reviews into the
operative plan rather than preserving stale alternative instructions. In
particular, it fixes:

- the missing machine-readable registry and validator;
- the absent canonical IR structure and semantics boundary;
- the false equivalence between gold-free diagnostic agreement and AFS;
- the scientifically weak `rho = 0` null;
- working-directory-only gold isolation;
- individual-only assumption checks;
- CEGIR evaluation without deletion/no-op/source-preservation controls;
- RL ordering that audited a reward before defining its components;
- effort totals that counted optional A2 in the minimum scope;
- status accounting that assigned all A1 effort to the completed audit; and
- language implying that either G3 outcome would automatically be publishable.

Historical comments are recoverable in Git history and the proposal's review
section. They are not duplicated here because an execution document must have
one active instruction for each decision.

---

## 15. Definition of plan completion

The planning artifact is complete when all of the following remain true:

- every research task appears exactly once in a base scope;
- every dependency exists, is acyclic, and is contained in cumulative scope;
- every task has at least one argv-form acceptance command and artifact;
- every `done`/`partial` status points to existing evidence;
- completed artifacts exist and completed tasks depend only on completed tasks;
- the generated status/effort summary exactly matches the registry;
- LExec IR has a versioned schema and `IR-1` requires a prose semantics spec;
- scientific gates define estimands, controls, invalidation, and stop actions;
- external-authority steps are explicit; and
- the validator and its tests pass in CI.

Those conditions make the **plan** mechanically executable and auditable. The
research programme becomes complete only when its tasks progress through their
registered gates with retained evidence. No current text should be read as a
claim that the compiler, validated instrument, transfer result, or RL result
already exists.
