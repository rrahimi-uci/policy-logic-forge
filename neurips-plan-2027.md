# NeurIPS 2027 — Development Plan

**Companion to** [`neurIips-proposal-2027.md`](neurIips-proposal-2027.md) (v3).
The proposal argues *what to claim*; this plan specifies *what to build, in what
order, and what proves each step done*.

| | |
| --- | --- |
| Scope | The minimum paper: G0 (measurement unit) → G1 (external reproduction) → G2 (compiler correctness) → G3 (instrument validation) → G4 (one non-Dutch domain + CEGIR). G5 (solver-reward RL) is conditional and specified but not scheduled as committed work. |
| Horizon | 2026-09-01 → 2027-04-15 (freeze), submit ~2027-05-01 |
| Task IDs | Match §26 of the proposal: `PIPE-*`, `IR-*`, `BE-*`, `BENCH-*`, `ASM-*`, `STAT-*`, `RL-*`. New IDs here: `REPRO-*`, `CEGIR-*`, `OPS-*`. |
| Effort unit | **pd** = person-day for one engineer already fluent in this codebase. Estimates are for building *and* testing, not for research iteration. |
| Definition of done | Every task lists an acceptance test that is a named `pytest` test or a recorded artifact. A task with no acceptance test is not in this plan. |
| Non-negotiable | **No task that consumes a measurement may start before its G0 prerequisite is green.** The two confirmed pipeline defects (proposal §12.4) make every corpus-level denominator wrong until fixed. |

---

## 0. Critical path at a glance

```
                    ┌─────────────────────────────────────────────┐
   G0  PIPE-1..4 ───┤ measurement unit is real (bug fixes)        │  Sep–Oct 2026
       IR-1..3      │ compiler IR v1 + supported subset declared  │
       BENCH-1..3   │ adapters, manifests, gold-hidden queries    │
                    └───────────────────┬─────────────────────────┘
                                        │
   G1  REPRO-1..3  ──── reproduce Graus on HIS harness ───────────   Nov 2026
                        58 models · 4 conditions · 5 runs · 13,080 inputs
                                        │
   G2  BE-1..4     ──── 4 backends agree on a conformance suite ──   Nov–Dec 2026
                        interpreter · DMN/FEEL · SMT-LIB · 3rd-party engine
                                        │
   G3  STAT-1..3   ──── ρ(gold-free DA, gold-based OE) + CI ───────   Dec 2026–Jan 2027
                        protocol frozen BEFORE any result is seen
                                        │
                            ┌───────────┴───────────┐
                    ρ ≥ 0.6 │                       │ ρ fails
                            ▼                       ▼
   G4  ContractNLI + ASM-1..4 + CEGIR-1..3     PLAN B: diagnostic paper
       (Feb–Mar 2027)                          (§20 of the proposal)
                            │
   G5  RL-1..4  ── only if the degenerate-policy gate passes ──────   Mar 2027, conditional
```

**The one-sentence version:** two bug fixes and a compiler IR must land before any
number is quoted; then reproduce someone else's result before producing our own;
then validate the instrument before using it at scale.

---

## 1. Dependencies to declare (and the history that makes this sensitive)

PR #6 removed a `compiler/` scaffold and its `lxml` dependency precisely because
they were declared before any code existed. **This plan re-introduces both only
with working code in the same commit**, and each addition carries a one-line
justification in `requirements.txt`, matching the file's existing comment style.

| Package | Used by | Justification | Added at |
| --- | --- | --- | --- |
| `z3-solver` | `utils/smt.py`, all seven solver queries | The proposal's entire verification layer is SMT. Pure-Python wheel, no system deps. | IR-3 |
| `lxml` | `utils/dmn_emit.py` | DMN 1.3 XML emission with namespace + schema validation. `xml.etree` cannot validate against XSD. | BE-2 |
| `scipy` | `bench/stats.py` | Spearman ρ, bootstrap CIs, Holm–Bonferroni. | STAT-2 |
| `statsmodels` | `bench/stats.py` | Mixed-effects model with a random intercept per document (STAT-2). | STAT-2 |
| *(dev only)* `hypothesis` | `tests/test_feel_properties.py` | Property-based differential testing of the FEEL evaluator vs. the SMT encoding (BE-1/BE-3). | BE-1 |
| *(dev only, optional)* a JVM + a DMN engine | `bench/dmn_engine_harness.py` | BE-4's third-party cross-check. **Kept out of `requirements.txt`** — gated behind an env var and skipped by default so `pytest` stays provider-free and JVM-free. | BE-4 |

**Constraint preserved:** `pytest` must continue to run with no API key, no
network, and no JVM. Everything above is either pure Python or skipped by default.

---

## 2. Module layout

New code only; nothing existing is moved. Follows the repo's conventions:
dependency-light `utils/`, one module per concern, no third-party graph library,
docstrings that explain *why* rather than *what*.

```
utils/
  lexec_ir.py         # IR-1  compiler IR v1: dataclasses + validation + refusal codes
  feel.py             # BE-1  bounded FEEL renderer + reference evaluator
  dmn_builder.py      # BE-2  IR -> decision tables (DNF, hit-policy proofs)
  dmn_emit.py         # BE-2  decision tables -> DMN 1.3 XML (lxml, XSD-validated)
  smt.py              # BE-3  IR -> SMT-LIB; the seven queries; witness extraction
  assumptions.py      # ASM-1..2  typed assumption language + admissibility
compiler/
  __init__.py         # re-exports the public compile() entry point
  pipeline.py         # IR -> {tables, dmn, smt} with a single refusal ledger
bench/
  __init__.py
  manifest.py         # BENCH-1  run manifest schema + writer + hash
  adapters/
    dutch_dmn.py      # BENCH-1  Graus corpus: gold models, legal text, 58-model split
    contract_nli.py   # BENCH-1  ContractNLI: docs, 17 hypotheses, evidence spans
  queries.py          # BENCH-2  gold-hidden query generation + leakage guard
  harness.py          # REPRO-2  run our artifacts through the Dutch executor
  metrics.py          # DA, OE, EY, PP, VR, CQI, defect density
  stats.py            # STAT-1..3  power, hierarchical bootstrap, mixed effects
cli/
  compile.py          # C1..C4 orchestrator (compile / verify / replay / report)
  evaluate.py         # run a benchmark adapter end to end, emit a manifest
tests/
  test_lexec_ir.py  test_feel.py  test_feel_properties.py  test_dmn_builder.py
  test_dmn_emit.py  test_smt_queries.py  test_hit_policy_proofs.py
  test_assumptions.py  test_chunk_coverage.py  test_optimizer_v2_handoff.py
  test_manifest.py  test_query_leakage.py  test_metrics.py  test_stats.py
```

**Hard architectural constraint, verified in code:**
`tests/test_inter_agent_contract_alignment.py:216-248` pins
`_project_execution`'s key set to exactly what `final_rule_issues` reads. The
compiler therefore sits **strictly downstream** and treats `rule["execution"]`
as read-only input. Nothing in `compiler/` or `utils/{feel,dmn_*,smt}.py` may
import from `agents/`.

---

## 3. Phase G0 — make the measurement unit real (Sep–Oct 2026, ~28 pd)

Nothing here is research. All of it is prerequisite, and it is the highest-value
work in the plan because every later number depends on it.

### 3.1 PIPE-1 — per-document extraction unit with enforced chunk coverage — 4 pd

**Problem** (proposal §12.4 D-1, verified in code): a "full corpus" run reads at
most `target_rules // rules_per_batch + 10` batches — 16 with the CLI defaults —
of length-sorted, character-truncated chunks.

**Change.**
1. Add `--unit {document,corpus}` to `cli/extract.py`, default `document`.
2. In `agents/agent_03_rules_extractor.py`, replace the batch cap with an
   explicit coverage contract:
   ```python
   # A capped run is a pilot, never a coverage claim. `target_rules` may bound
   # how many rules we ask for; it must not bound how much source we read.
   if self.config.require_full_coverage:
       batches_to_process = len(batches)      # every chunk, always
   ```
3. Emit `chunk_coverage.json` per unit: `{unit_id, chunks_total,
   chunks_processed, chunks_truncated, bytes_dropped, sha256_per_chunk}`.
4. Exit non-zero when `chunks_processed != chunks_total` or
   `chunks_truncated > 0` under `require_full_coverage`.

**Acceptance.** `tests/test_chunk_coverage.py::test_forty_chunk_unit_processes_forty_chunks_at_any_target_rules`
— parametrized over `target_rules ∈ {5, 30, 300}`, asserting 40/40 each time; and
`::test_run_fails_closed_when_a_chunk_is_truncated`.

### 3.2 PIPE-2 — reconcile word-based chunking with character-based clipping — 2 pd

Agent 1 targets ~2,000-word chunks; Agent 3 clips at 8,000 characters. Long
chunks silently lose their tails.

**Change.** Make the limit token-aware and *reported*: clip only at a chunk
boundary the organizer produced, and when clipping is unavoidable, record
`bytes_dropped` and the dropped span's hash rather than dropping silently.

**Acceptance.** `tests/test_chunk_coverage.py::test_no_silent_tail_loss` — a
12,000-character chunk either round-trips whole or appears in
`chunk_coverage.json` with a non-zero `bytes_dropped` and its span hash.

### 3.3 PIPE-3 — full v2 fields into the optimizer — 3 pd

**Problem** (D-2, verified in code): `agent_06_knowledge_graph_optimizer.py`
builds dedup and dependency summaries from the legacy `conditions` /
`consequences` fields the v2 prompts forbid (lines 349–350, 536–537, 706–707,
768–769), so for v2-only rules it sees a truncated description and nothing else.

**Change.** One shared `_rule_summary_v2(rule)` helper emitting
`condition_predicates`, `condition_logic`, `outcomes`, `variables` (name/type/
role only), `applicability_scope`, `exceptions`, `recommended_hit_policy`, and
`responsible_party`, with the legacy fields retained only when present (v1
graphs still exist). Update the four call sites and the two prompts that consume
them.

**Acceptance.** `tests/test_optimizer_v2_handoff.py::test_v2_only_rule_yields_predicate_context`
— a rule with no `conditions`/`consequences` produces a summary containing its
predicates and outcomes; and `::test_v1_rule_still_summarised` for the
back-compat path.

### 3.4 PIPE-4 — deterministic, recall-auditable dependency discovery — 6 pd

**Problem.** Cross-batch analysis samples `min(20, batch_size // 4)` (~25%) of
each batch and caps batch pairs at 20 (lines 737–751), so edge **recall** is
unknown. `utils/dag_builder.py` guarantees node coverage of whatever edges it
receives — nothing more.

**Change.**
1. Make pair selection deterministic and *declared*: either all pairs, or a
   seeded sample whose size and seed are written to the manifest.
2. Add `--dependency-recall-audit` producing `dependency_audit.json` with
   candidate pairs considered, pairs skipped, and the sampling rate.
3. Build `tests/fixtures/dependency_gold/` — **60 hand-reviewed rule pairs** from
   two domains, labeled `{prerequisite, sequential, conditional, complementary,
   override, contradictory, none}`.
4. Report precision/recall/F1 against that fixture in the run report.
5. Rename the reported metric so the two claims can never be conflated again:
   `dag_node_coverage` and `dependency_discovery_recall`.

**Acceptance.** `tests/test_dependency_audit.py::test_recall_reported_against_gold_fixture`
(asserts the number is *computed and present*, not that it is high) and
`::test_pair_selection_is_deterministic_under_seed`.

### 3.5 IR-1 — compiler IR v1 — 8 pd

The proposal's §5 describes a formal language the v2 contract does not implement
(§24 R4). The IR is where the gap closes. **The v2 contract is not changed** —
the IR is a separate, downstream, typed lowering target, which keeps every
existing test valid.

`utils/lexec_ir.py`, frozen dataclasses, no I/O, no LLM:

```python
SUPPORTED_THEORIES = {"bool", "int", "real", "enum"}   # v1 subset. Everything else refuses.

@dataclass(frozen=True)
class Var:
    name: str            # globally resolved, canonical
    theory: str          # SUPPORTED_THEORIES
    role: str            # input | derived | output
    domain: Domain       # EnumDomain | IntervalDomain | BoolDomain
    unit: str | None
    norm_kind: str | None   # obligation | permission | prohibition | definition | None
    #  ^ IR-1 adds the deontic axis v2 lacks; §11's shall->may relation needs it.

@dataclass(frozen=True)
class Atom:      var: str; op: str; value: Literal | VarRef
@dataclass(frozen=True)
class Formula:   # And | Or | Not | Atom  -- Not is IR-only, never extracted
@dataclass(frozen=True)
class Rule:
    rule_id: str
    condition: Formula
    defeaters: tuple[Formula, ...]      # combined as OR, negated  (proposal §5)
    outcomes: tuple[Assign, ...]
    scope: Formula | None               # typed, NOT the mortgage-shaped dict
    provenance: tuple[SpanRef, ...]
@dataclass(frozen=True)
class Table:     # IR-3: rules grouped by output signature -> one table
    table_id: str; rules: tuple[str, ...]; hit_policy: str; policy_proof: PolicyProof
@dataclass(frozen=True)
class Refusal:
    rule_id: str; code: str; detail: str; construct: str
```

**Refusal codes are the deliverable, not an afterthought** — every one is
counted and reported: `UNSUPPORTED_THEORY_DATE`, `UNSUPPORTED_THEORY_DURATION`,
`UNSUPPORTED_THEORY_STRING`, `UNSUPPORTED_THEORY_LIST`, `UNSUPPORTED_RANGE`,
`UNRESOLVED_SYMBOL`, `CYCLIC_DERIVED_VAR`, `OPERATOR_TYPE_MISMATCH`,
`UNTYPED_SCOPE`, `NO_OUTPUT_VARIABLE`, `HIT_POLICY_UNPROVABLE`.

Also in IR-1: an **operator × theory compatibility matrix** (v2 validates neither
— `>` on a boolean passes today), a **global symbol table** with acyclicity
checking for `variable_reference`, and **explicit null/missing semantics** (a
missing input makes an atom *unknown*, not false; three-valued evaluation with a
declared collapse rule at the table boundary).

**Acceptance.** `tests/test_lexec_ir.py` — one test per refusal code asserting it
fires; `::test_operator_theory_matrix_rejects_gt_on_bool`;
`::test_variable_reference_cycle_refused`;
`::test_lowering_is_total` (every v2 rule either lowers or produces ≥1 refusal —
never silently drops).

### 3.6 IR-2 — theory coverage decision — 2 pd

For each of `date`, `date_time`, `duration`, `string`, `list`, `range`,
`variable_reference`: measure frequency on the Dutch 58 and one non-Dutch corpus,
then either implement the theory or refuse it. **v1 refuses all seven and
reports the refusal rate** — that rate is a headline number, because it bounds
achievable coverage.

**Acceptance.** `tests/test_lexec_ir.py::test_theory_refusal_rate_is_reported`
plus a committed `docs/theory_coverage.md` table.

### 3.7 IR-3 — hit-policy proof obligations — 3 pd

Implements the revised P2 (proposal §6). Group rules by output signature into
tables; for each table discharge one of four obligations:

| Obligation | Method | Emitted |
| --- | --- | --- |
| rows pairwise disjoint | `UNSAT(rᵢ ∧ rⱼ)` ∀ i<j | `UNIQUE` + proof |
| overlap, outputs equal on overlap | `UNSAT(rᵢ ∧ rⱼ ∧ oᵢ ≠ oⱼ)` | `ANY` + proof |
| source-backed precedence exists | precedence relation with a `SpanRef` | `PRIORITY` + citation |
| otherwise | — | `Refusal(HIT_POLICY_UNPROVABLE)` + the witness binding |

**No unproven `FIRST`, ever.**

**Acceptance.** `tests/test_hit_policy_proofs.py` — four tests, one per branch;
`::test_no_unproven_first_is_ever_emitted` over a generated table corpus.

### 3.8 BENCH-1..3 — adapters, manifests, gold-hidden queries — 7 pd

- **BENCH-1** `bench/adapters/dutch_dmn.py`: load `source_models/` (DMN XML),
  `gold_models/` (JSON), `legal_text/`; expose the **58-model testable split**
  and the 37 excluded with reasons. `bench/manifest.py` writes an immutable
  manifest: `{run_id, git_sha, config_sha, model_id, adapter, split, seed,
  n_runs, corpus_sha256, task_ids, cost_usd, wall_clock}`.
- **BENCH-2** `bench/queries.py`: gold-hidden query generation. Enforcement is
  structural, not a promise — the generator runs in a subprocess whose working
  directory cannot reach `gold_models/`, and the harness asserts it:
  ```python
  def _assert_gold_unreachable(gold_dir: Path) -> None:
      """Fail the run, not the review, if the query generator can see gold."""
  ```
  Gold artifacts supply the **label** (execute the gold model on the binding);
  they never supply the **query**.
- **BENCH-3** retain all 5 runs per condition; any best-of-*k* number is tagged
  `estimator="best_of_5"` in the manifest so it can never be compared to a mean
  by accident.

**Acceptance.** `tests/test_query_leakage.py::test_generator_cannot_read_gold_dir`;
`tests/test_manifest.py::test_manifest_is_content_addressed_and_immutable`;
`::test_best_of_k_is_tagged`.

**G0 exit criteria (all four must hold).** ① chunk coverage 100% on a frozen unit
or the run fails; ② dependency precision/recall reported against the 60-pair
fixture; ③ every unsupported construct produces a counted refusal; ④ a manifest
exists for every run and is content-addressed.

---

## 4. Phase G1 — reproduce before extending (Nov 2026, ~9 pd)

### 4.1 REPRO-1 — stand up the anchor harness — 2 pd

Clone `github.com/opengov-lab/legal-text-to-decision-model` at a pinned commit.
Run `evaluation/run_evaluation` unmodified. Record their numbers as *we* obtain
them.

**Target protocol, matched exactly** (all `(published)`, verified against
arXiv:2604.17153): **58** testable models (24 Outcome + 34 Requirements),
**13,080** exhaustive input variations, **4** conditions (`text`, `+srl`, `+io`,
`+srl+io`), **5** runs per condition, **1,900** generations.

**Acceptance.** A committed `results/repro_g1/` with their macro-averaged
outcome-equivalence figures within our bootstrap CI of the published
**42.6% / 60.4%**, and their best-run figures within CI of **19/58 (33%)** and
**29/58 (50%)**. *Any* mismatch is investigated before proceeding.

### 4.2 REPRO-2 — run our artifacts through their executor — 4 pd

`bench/harness.py` adapts our compiled artifacts to their input format. **Matched
information conditions only:**

| Our condition | Compared against | Note |
| --- | --- | --- |
| raw legal text | their `text` | the honest headline comparison |
| our own derived interface | their `text` | our interface derivation is part of the system |
| gold I/O supplied | their `+io` | **labeled gold-leaking**; never our headline |

**Acceptance.** `results/g1_ours/` with per-model OE, all 5 runs retained, and a
manifest. **No claim of beating 42.6%/60.4% from a raw-text run** appears in any
artifact of this phase.

### 4.3 REPRO-3 — license and reuse posture — 1 pd

Resolved during review (proposal §22): the repo is CC BY 4.0 with no separate
data license, and the **upstream Dutch government models carry no explicit
license** — reuse rests on the repo's own assumption about the *Wet hergebruik
van overheidsinformatie*. Actions: reference source models by commit hash, never
re-host; email the Dutch DSO for written confirmation; raise the CC BY vs.
CC BY-SA inconsistency with the author.

**Acceptance.** `docs/data_licensing.md` recording the position, the email sent,
and any reply.

### 4.4 REPRO-4 — defeater semantics decided empirically — 2 pd

Compile the Dutch 58 under all three readings of `exceptions` — defeaters
(`C ∧ ¬⋁X`), conjunctive (`C ∧ ⋀X`), and ignored — and compare OE. The Dutch
corpus has *gold behavior*, which our self-generated vectors do not, so this is
the right testbed.

**Acceptance.** `docs/defeater_semantics.md` with three OE numbers, CIs, and the
decision. If the readings are statistically indistinguishable, that is the
finding and the defeater reading stands on the *a priori* argument alone —
stated as such.

**G1 exit criterion.** Their published numbers reproduce within CI. Nothing
downstream is trusted until this holds.

---

## 5. Phase G2 — validate the compiler (Nov–Dec 2026, ~22 pd)

Four independent implementations of the same semantics, cross-checked. This is
what licenses every later "the artifact decides X" claim.

### 5.1 BE-1 — bounded FEEL renderer + reference evaluator — 6 pd

`utils/feel.py`. Renders and evaluates exactly the IR-1 subset; raises
`UnsupportedFeelConstruct` outside it. Three-valued (`true/false/unknown`) to
match IR-1's null semantics.

**Acceptance.** `tests/test_feel.py` unit coverage per operator × theory;
`tests/test_feel_properties.py` — `hypothesis` property tests asserting the
evaluator agrees with the SMT encoding on 10⁴ random bindings per generated rule.

### 5.2 BE-2 — decision tables and DMN 1.3 XML — 5 pd

`utils/dmn_builder.py`: `Rule → DNF → rows`, defeater negation applied,
hit policy from IR-3's proof, provenance carried into
`extensionElements` (`rule_id`, `section_id`, grounding status).
`utils/dmn_emit.py`: lxml emission validated against the DMN 1.3 XSD.

**Acceptance.** `tests/test_dmn_builder.py::test_dnf_row_count_matches_reference`;
`tests/test_dmn_emit.py::test_every_emitted_file_validates_against_dmn_xsd`;
`::test_provenance_survives_round_trip`.

### 5.3 BE-3 — SMT-LIB backend and the seven queries — 6 pd

`utils/smt.py`. Each query from proposal §7, each returning a **witness** when
satisfiable (CEGIR depends on the witness, not the boolean):
disjointness, subsumption, equivalence, co-firing conflict, coverage gap,
vacuity, entailment. Plus `solve_with_budget(timeout_ms)` recording a timeout
rate — a timeout is a *reported outcome*, never a silent pass.

**Acceptance.** `tests/test_smt_queries.py` — one test per query with a
hand-built positive and negative case; `::test_conflict_returns_a_concrete_binding`;
`::test_timeouts_are_counted_not_swallowed`.

### 5.4 BE-4 — third-party DMN engine cross-check — 3 pd

`bench/dmn_engine_harness.py`, gated behind `LEXEC_DMN_ENGINE=1` and skipped by
default so `pytest` stays provider-free and JVM-free. Runs a real engine on the
emitted XML and diffs against BE-1's evaluator.

**Acceptance.** `tests/test_dmn_engine_crosscheck.py` (skipped unless the env var
is set) — three-way agreement (interpreter / SMT / engine) on **100%** of a
generated conformance suite of ≥ 500 tables; every disagreement root-caused in
`docs/backend_disagreements.md`.

### 5.5 P3′ regression suite — 2 pd

P3 is withdrawn (proposal §6). P3′ is a *comparison* theorem, so it is
implemented and tested as one — for regression and differential testing between
two known tables, never as a certificate against an unknown reference.
**Exhaustive enumeration stays** in every G1/G3 measurement.

**Acceptance.** `tests/test_p3_prime.py` — ties, open vs. closed endpoints,
multi-dimensional cells, missing/default outputs, non-interval predicates; plus
`::test_p3_prime_does_not_certify_against_unknown_thresholds`, which asserts the
known counterexample (a threshold inserted between interior point and endpoint)
*escapes* the certificate. That test exists to stop the withdrawn claim from
creeping back.

**G2 exit criterion.** Three backends (four with the engine) agree on 100% of the
conformance suite; every disagreement root-caused.

---

## 6. Phase G3 — validate the instrument (Dec 2026–Jan 2027, ~14 pd)

**The primary contribution. The protocol is frozen and committed before any
result is looked at.**

### 6.1 STAT-1 — power analysis, before data collection — 2 pd

`bench/stats.py`. Simulate the hierarchical design (58 models × 5 runs, unequal
scenario counts) and compute power to detect ρ ≥ 0.6 at α = 0.05.

**Acceptance.** `docs/analysis_plan.md`, committed and tagged
`analysis-plan-frozen`, containing the estimand, sampling unit (the **decision
model**), null (ρ = 0), minimum useful effect (ρ ≥ 0.6, CI lower bound > 0.3),
and the power result. **If 58 models cannot reach 80% power, that is reported and
the design changes** — not the threshold.

### 6.2 STAT-2 — hierarchical estimation — 4 pd

Spearman ρ with a hierarchical bootstrap resampling **models** (not queries, not
runs); a mixed-effects cross-check with a random intercept per model; 95% CIs on
everything.

**Acceptance.** `tests/test_stats.py::test_bootstrap_resamples_models_not_queries`
— a synthetic dataset where query-level resampling gives a spuriously tight CI
and model-level resampling does not.

### 6.3 STAT-3 — CQI and metric definitions — 3 pd

Per the corrected P4 (proposal §6): CQI requires query equivalence classes,
abstention handling, and multi-valued (`COLLECT`) handling. Implement all three,
and report CQI **only** alongside DA and EY, always labeled a
*reliability property conditional on successful compilation*.

**Acceptance.** `tests/test_metrics.py::test_cqi_is_undefined_for_partial_artifacts`;
`::test_cqi_never_reported_without_da_and_ey`.

### 6.4 The instrument-validation run — 5 pd

Compute per-model gold-free DA and gold-based OE on the 58; estimate ρ with CIs;
run the structured disagreement review (false-positive: DA high / OE low;
false-negative: DA low / OE high) and build a failure taxonomy.

**Acceptance.** `results/g3_instrument/` with the primary estimate, its CI, the
disagreement taxonomy, and the leakage-audit result.

**G3 exit criterion.** The primary endpoint is estimated with a CI. **Both
outcomes proceed:** ρ ≥ 0.6 → G4; ρ below the threshold → Plan B, which is a
real paper and not a consolation.

---

## 7. Phase G4 — one non-Dutch domain + CEGIR (Feb–Mar 2027, ~26 pd)

### 7.1 BENCH-1b — ContractNLI adapter — 4 pd

607 NDAs × 17 hypotheses, three-way labels, evidence spans (free provenance
gold). Frozen splits; manifest per run.

### 7.2 ASM-1..4 — assumption-explicit compilation — 10 pd

Per proposal §10, narrowed after verifying that arXiv:2606.16118 §5.6 already
proposes MCS surfacing.

- **ASM-1** typed assumption language, closed forms only: `TermSubsumption`,
  `ParameterDefault`, `TemporalDefault`, `PartyRoleIdentification`.
- **ASM-2** the **admissibility check that actually matters** — reject any
  assumption *A* with `⊨ A → h`. This is the solver-checkable version of "don't
  assume the conclusion," and it closes the hole deletion-minimality leaves open.
- **ASM-3** every assumption carries a `SpanRef`, or is flagged `background_law`
  and routed to review.
- **ASM-4** stratified human review (~150 assumptions) reporting the rate at
  which legal reviewers judge them admissible — permissibility is not
  solver-decidable and must not be presented as if it were.

**Acceptance.** `tests/test_assumptions.py::test_assumption_entailing_hypothesis_is_rejected`
(the anti-conclusion-assuming test); `::test_untyped_assumption_is_refused`;
`::test_deletion_minimality_and_admissibility_are_reported_separately`.

**Also attempted here:** email the arXiv:2606.16118 authors for their 400/610
strict-entailment re-annotation. If obtained, the entailment mode gets a correct
oracle for free; if not, budget ~200 re-annotations.

### 7.3 CEGIR-1..3 — counterexample-guided repair — 12 pd

- **CEGIR-1** the loop: `compile → solve → repair`, fixed point or *k* = 3.
- **CEGIR-2** witness rendering — the repair prompt carries the **concrete
  binding** and both cited clauses, not "there is a conflict."
- **CEGIR-3** the required ablation: witness vs. no-witness repair prompts,
  paired by document, with per-round token cost.

**Acceptance.** `tests/test_cegir.py::test_loop_terminates_at_fixed_point_or_k`;
`::test_repair_prompt_contains_a_concrete_binding`; and
`results/g4_cegir/` reporting DA and EY per round *k* ∈ {0,1,2,3} with CIs.

**Confirmatory endpoint (STAT):** DA of CEGIR vs. no-CEGIR, paired by document.

---

## 8. Phase G5 — solver-reward RL (conditional, Mar 2027, ~20 pd)

**Gate: this phase does not start unless the degenerate-policy suite passes
first.** Building the reward before the gate is how reward hacking gets shipped.

### 8.1 RL-3 first — the adversarial gate — 5 pd

Implement four degenerate policies and require each to score **worse** than an
honest baseline on the composite reward: `EmptyArtifact`, `ConstantOutput`,
`DisjointSymbols` (rules that can never co-fire), `OneRulePerDocument`.

**Acceptance.** `tests/test_reward_hacking.py` — four tests, each asserting
`reward(degenerate) < reward(honest_baseline)`. **Run as a CI gate on every
reward change.** If any degenerate policy wins, the reward is wrong and RL does
not start.

### 8.2 RL-1 — coverage reward the policy cannot fake — 5 pd

The hole in v2's reward: "compiles" and "no conflict" both improve by emitting
*less*. Fix: score coverage against a **clause inventory the policy did not
produce** — derived from the corpus's own annotations (CUAD categories,
ContractNLI hypotheses, Dutch gold model I/O) — and report **omission rate**
explicitly.

### 8.3 RL-2 — held-out grounding signal — 4 pd

Vector replay against self-generated vectors is **circular** (nothing in the repo
executes a vector today). Replace with independently-authored held-out vectors
and evidence spans; report self-vector replay separately and **never as a
reward**.

### 8.4 RL-4 — training and reporting — 6 pd

GRPO on an 8–14B model (or LoRA on ~32B). Report **every** reward component, the
Pareto front, output size, symbol-reuse rate, and omission rate — never the
scalar. Never train and evaluate on the same solver-derived witnesses.

**Confirmatory endpoint:** AURC of solver-signal selective compilation vs. the
ported grammar-entropy baseline (a *ported baseline on our task* — not a
comparison to the published AUROC > 0.93, which is a different task and base
rate).

---

## 9. Effort summary and staffing reality

| Phase | pd | Calendar | Can it slip? |
| --- | --- | --- | --- |
| G0 | 28 | Sep–Oct 2026 | **No.** Everything depends on it. |
| G1 | 9 | Nov 2026 | No — external reproduction is the trust anchor. |
| G2 | 22 | Nov–Dec 2026 | Partly: BE-4 (engine cross-check) can slip 2 weeks. |
| G3 | 14 | Dec–Jan | **No.** This is the paper. |
| G4 | 26 | Feb–Mar | Yes: CEGIR can drop, leaving benchmark + instrument. |
| G5 | 20 | Mar (conditional) | Yes: designed to be droppable. |
| Writing | 15 | Apr | Freeze **Apr 15**. |
| **Total (G0–G4 + writing)** | **114 pd** | | |
| **Total with G5** | **134 pd** | | |

**The honest read:** 114 pd across ~7.5 months is ~0.75 FTE of pure engineering
with **no allowance for research iteration, failed experiments, or debugging
someone else's harness**. Realistically this needs **1.5 engineers, or a scope
cut to G0–G3 plus writing (73 pd)**. G0–G3 alone — a validated compiler and a
validated instrument on the Dutch corpus — is a defensible Datasets & Benchmarks
submission. That is the version I would commit to.

---

## 10. What each phase publishes if everything after it fails

Designed so no phase is wasted work.

| Fails after | Still publishable |
| --- | --- |
| **G0** | An engineering note nobody cites — but the pipeline is correct, which was needed regardless. |
| **G1** | A reproduction report on arXiv:2604.17153, including whichever numbers did not reproduce. Reproductions of recent legal-NLP results are genuinely useful. |
| **G2** | A compiler-correctness paper: differential testing of a normative-text→DMN compiler across four backends, plus the theory-refusal rates that bound achievable coverage. Workshop-scale. |
| **G3** | **The core paper, either way.** ρ ≥ 0.6 validates gold-free extensional evaluation for the field. ρ low is the more interesting result and redirects to Plan B. |
| **G4** | Adds a second domain and a method delta → a fuller D&B submission. |
| **G5** | Adds the learning result → main-track candidate. |

---

## 11. Risk register with triggers

| Risk | Trigger to watch | Action |
| --- | --- | --- |
| G1 does not reproduce | any published figure outside our CI | stop; diagnose their harness before writing our own numbers; if irreconcilable, report it as a reproduction failure — that is a finding |
| Theory refusal rate is high (say > 40% of rules touch `date`/`duration`/`list`) | IR-2's measurement | implement the temporal theory (adds ~8 pd) or narrow the corpus, and report the coverage bound honestly either way |
| Solver timeouts dominate | timeout rate > 5% on any corpus | bound row counts; cache by rule-set hash; report the rate as a limitation |
| **Scooped on solver-reward RL** — arXiv:2606.16118 §5.6 names it as future work | a preprint appears | G3 is the spine precisely because it does not depend on being first; also, we emailed them (REPRO/ASM), so we may know early |
| ρ estimate is uninformative (wide CI) | STAT-1 power analysis | discovered *before* data collection; expand to the 37 excluded models via interface adaptation, or add a second gold-artifact source |
| Dutch data reuse challenged | any reply from DSO | we never re-host; reference by commit hash; fall back to reporting on their harness only |
| Engineering capacity (§9) | G0 not green by Oct 31 | cut to G0–G3 + writing (73 pd) and target D&B |

---

## 12. Decision log (append-only)

| Date | Decision | Rationale |
| --- | --- | --- |
| 2026-08-24 | Compiler IR is **separate** from v2 contract v3 | Changing the contract would invalidate 770 passing tests and the agents' prompt packs; a downstream typed lowering achieves the same and keeps the extraction half stable. |
| 2026-08-24 | P3 withdrawn; exhaustive enumeration retained | The counterexample is valid, and P3′ needs the candidate's thresholds, which are unavailable at test-generation time (proposal §25 D1). |
| 2026-08-24 | Unproven `FIRST` is never emitted | Row order carries no legal meaning in this setup; recording a downgrade does not make it sound (proposal §24 R5). |
| 2026-08-24 | Primary track = Datasets & Benchmarks | The scope cut removes both learning contributions; a main-track submission with no method is a hard sell (proposal §25 D2). **Revisit if G5 lands.** |
| 2026-08-24 | Vector replay is not a reward | The vectors come from the same extraction, and nothing in the repo executes them — it measures compiler fidelity to a self-generated pair (proposal §24 R9). |
| 2026-08-24 | Never re-host the Dutch source models | Upstream carries no explicit license; reuse rests on a third party's assumption about Dutch open-data law (proposal §22). |

---

## 13. First two weeks, concretely

Ordered so the first commit is a bug fix, not a new subsystem.

| Day | Task | Deliverable |
| --- | --- | --- |
| 1–2 | PIPE-1 | `--unit document`, coverage contract, `chunk_coverage.json`, `test_chunk_coverage.py` green |
| 3 | PIPE-2 | no silent tail loss; `bytes_dropped` reported |
| 4–5 | PIPE-3 | `_rule_summary_v2()` at all four call sites; `test_optimizer_v2_handoff.py` green |
| 6–7 | REPRO-1 | anchor harness cloned at a pinned commit and running unmodified; their numbers recorded |
| 8–10 | IR-1 (part 1) | `utils/lexec_ir.py` dataclasses + refusal codes + `test_lexec_ir.py` skeleton |
| 11–12 | PIPE-4 (part 1) | 60-pair dependency fixture built and hand-reviewed |
| 13–14 | BENCH-1 | `bench/adapters/dutch_dmn.py` exposing the 58/37 split; `bench/manifest.py` |

**Two weeks in, the honest status should read:** *the extraction unit is
document-complete and audited, the optimizer sees v2 fields, the anchor harness
reproduces, and the IR's supported subset is declared with counted refusals.* No
research claim yet — and that is the point.

---

## 14. Review — second-pass comments and required corrections (2026-08-24)

### Overall assessment

This is substantially stronger than the proposal reviewed in §24. It correctly
withdraws P3, refuses unproved `FIRST`, separates adapters from results, makes
failure/refusal visible, narrows the novelty claims, and turns most of the first
review into named work. The plan is useful as an architectural backlog.

It is **not yet an executable research protocol**. The remaining problems are
not editorial: the central metric is mislabeled, several phases require code
scheduled in later phases, the compiler-correctness gate has no independent
semantic oracle, the leakage guard is not a guard, and the effort totals do not
add up. The statement in proposal §25 that all 13 blocking concerns are
“applied” should therefore be read as **acknowledged and translated into work**,
not as closed.

**Verdict: revise before execution.** PIPE-1..3 can begin as scoped bug fixes,
and the released Dutch evaluator can be replayed independently. Do not freeze a
preregistration, quote a corpus metric, or start paid generation from the present
plan.

### Disposition of the first review after reading the applied changes

| Prior item | Second-pass status | Reason |
| --- | --- | --- |
| R1 adapters ≠ evaluated domains | **Applied as a limitation; implementation remains future work** | The proposal and plan now say this correctly. |
| R2 corpus completeness | **Partially applied** | Reading every chunk does not imply extracting every rule: each batch prompt still requests only up to `rules_per_batch`, and the proposed unit does not yet preserve original-document identity end to end. |
| R3 optimizer handoff / edge recall | **Partially applied** | `_rule_summary_v2()` is a good repair, but the 60-pair convenience fixture and deterministic pair selection do not establish end-to-end edge recall. |
| R4 formal language mismatch | **Partially applied** | A separate IR is appropriate, but the proposed IR places modality on variables, reduces scope to a formula, hard-codes exception semantics before REPRO-4, and does not say how missing v2 semantics are obtained. |
| R5 `UNIQUE→FIRST` | **Applied** | The proof-obligation table is the right fail-closed policy. |
| R6 P3 | **Applied** | Withdrawal, P3′ restriction, and retention of enumeration are correct. |
| R7 CQI | **Applied conceptually** | CQI is now described as conditional reliability, although the concrete estimand still needs preregistration. |
| R8 instrument validation | **Not yet closed** | DA is defined using `gold(q)`, so it is not gold-free; the anchor reproduction and statistical model also remain under-specified. |
| R9 reward circularity | **Partially applied** | The degenerate-policy gate helps, but the proposed “independent” inventories are not complete clause inventories and four hard-coded attacks are easy to overfit. |
| R10 assumption legitimacy | **Partially applied** | Per-assumption `A → h` rejection misses conclusion laundering by a set of assumptions and does not establish legal admissibility. |
| R11 statistics | **Partially applied** | The plan names clustering and multiplicity, but mixes a per-model Spearman estimand with run-level mixed effects and powers the wrong null for its stated success threshold. |
| R12 matched baselines | **Partially applied** | The Dutch paper reports OE only for the two I/O-enriched conditions, so a raw-`text` OE headline is not available without defining a new interface-alignment intervention. |
| R13 scope / schedule / budget | **Not yet closed** | Phase dependencies conflict and the person-day totals omit BENCH work and misstate the G0–G3 subtotal. |

The non-blocking license item is **characterized, not resolved**. The released
repository says CC BY 4.0, the arXiv page says CC BY-SA 4.0, and the upstream
government models have no explicit license. “Do not re-host; seek written
confirmation” is a sound interim posture, but receipt of permission or a
documented legal basis is the resolution.

### Blocking findings

#### P1. “Gold-free DA” is not gold-free, and the proposed correlation does not validate the claimed instrument

Proposal §13 defines DA as
`E_q[1(⟦A⟧(q) = gold(q))]`; §9.3 says the answer is obtained by executing the
gold DMN. That is a **gold-labeled sparse outcome-equivalence estimate**, not a
gold-free metric. OE is the same candidate-versus-gold comparison over the
anchor's exhaustive input set. Their correlation primarily tests whether one
gold-labeled query sample approximates another gold-labeled query set. It does
not validate a metric usable on corpora without gold artifacts, and it cannot
license the sentence “every gold-free result inherits credibility.”

**Required correction — choose one construct before STAT-1:**

1. Rename DA to **sampled OE (sOE)**, define the independently source-generated
   query distribution, and narrow C2 to *whether source-generated sparse tests
   estimate exhaustive OE*. This is defensible, but not gold-free evaluation.
2. Or define a genuinely gold-free signal whose expected answer comes from an
   independent source: human-authored source-grounded scenarios, expert labels,
   legally valid metamorphic relations, or held-out corpus annotations. Then
   validate that signal against OE without using gold to construct either its
   queries or labels.

Whichever option is chosen, include negative controls: random query samples of
equal size, stratified random samples over the gold interface, and deliberately
biased samples. Otherwise a high correlation cannot be attributed to the
proposed source-driven instrument.

#### P2. The phase graph cannot execute in its stated order

- REPRO-2 runs “our compiled artifacts” in G1, but the reference evaluator,
  DMN builder, emitter, and solver are scheduled in G2.
- REPRO-4 compiles all 58 models under three exception readings before the same
  compiler exists.
- IR-3 requires solver `UNSAT` proofs in G0, while `utils/smt.py` and BE-3 are
  scheduled in G2.
- The day 6–7 REPRO-1 measurement occurs before G0 is green, contradicting both
  the non-negotiable and the critical-path diagram.

**Required correction:** split reproduction into **A1 evaluator replay** and
**A2 fresh generation replication**. A1 may run in parallel with PIPE work
because it evaluates released upstream artifacts and does not consume this
pipeline's measurements. Move REPRO-2 and REPRO-4 after the minimal compiler and
solver core. Either move the solver core needed by IR-3 into G0 or move IR-3 to
the backend phase. Publish a machine-readable task DAG and fail plan validation
on missing or cyclic dependencies.

#### P3. The effort arithmetic is internally inconsistent

G0's listed tasks total **35 pd**, not 28:

`PIPE (4+2+3+6) + IR (8+2+3) + BENCH (7) = 35`.

Therefore G0–G4 plus writing totals **121 pd**, not 114. Even using the stated
28 pd for G0, G0–G3 plus writing is **88 pd**, not 73; using the itemized G0 it
is **95 pd**. The 73-pd scope-cut claim omits material work. Annotation,
external-author correspondence, paid model runs, environment repair, and
research iteration are also not represented in pd.

**Required correction:** generate the summary table from a task registry rather
than hand-entering totals. Separate engineering pd, research/analysis pd, legal
reviewer hours, annotation hours, paid API/GPU cost, and external waiting time.
Add contingency explicitly; do not infer staffing from the current totals.

#### P4. REPRO-1 conflates deterministic evaluator replay with stochastic experimental replication

The [released Dutch repository](https://github.com/opengov-lab/legal-text-to-decision-model)
contains generated models, evaluation code, and results. Running
`python -m evaluation.run_evaluation` over those released artifacts should be a
deterministic **evaluator replay**, checked against exact files or a declared
numeric tolerance—not “inside our bootstrap CI.” A fresh replication requires
new GPT-5.1 generations at temperature 0.1, the original example-selection
schedule, prompts, provider behavior, and five runs. These are different
claims, costs, and failure modes.

The [paper's outcome evaluation](https://arxiv.org/html/2604.17153) is also
limited to **Text+io and Text+srl+io**, because only those conditions have fixed
inputs alignable to gold. Four conditions × five runs describes the generation
study (1,900 generations), not four-condition OE on 13,080 inputs.

**Required correction:**

- **A1:** pin upstream commit and environment; checksum released inputs,
  generated artifacts, and expected result files; replay the evaluator; require
  exact/tolerance-defined agreement.
- **A2:** separately preregister whether fresh generation replication is in
  scope; record model snapshot, prompts, examples, run mapping, API parameters,
  failures, and cost; compare distributions with a declared equivalence margin.
- Remove raw `text` versus raw `text` from the OE table unless a non-gold
  interface-alignment protocol is defined. It is not an existing published OE
  baseline.

#### P5. Backend agreement is not compiler correctness

BE-1..4 can all agree while sharing the same wrong v2→IR lowering or the same
wrong interpretation of the source. XSD validation proves XML shape, not FEEL
meaning. A generated conformance suite derived from the implementation can omit
exactly the cases the implementation mishandles. Calling this gate “validate the
compiler” overstates what it proves.

**Required correction:** split G2 into two claims:

1. **Lowering correctness:** hand-authored v2→IR fixtures with independently
   specified denotations, mutation tests, refusal-oracle tests, and Dutch
   source/gold cases. Include loss-accounting: every source field is consumed,
   deliberately ignored with a reason, or causes refusal.
2. **Backend semantic agreement:** independently generated IR programs covering
   every operator×type×null×hit-policy branch, plus metamorphic tests and a
   pinned third-party engine.

The release gate may say four-way agreement only when the required engine job
actually ran. A normally skipped test cannot support that claim.

#### P6. The proposed IR encodes unsettled or incorrectly located semantics

- `norm_kind` belongs to a norm, rule, or outcome—not a variable. The same
  variable may be obligatory in one rule, permitted in another, and prohibited
  in a third.
- `scope: Formula` is insufficient for jurisdiction, parties, authority,
  effective dates, document versions, and applicability metadata. Separate
  executable scope predicates from non-executable scope metadata.
- `defeaters` are hard-coded as `C ∧ ¬⋁X` in IR-1, but REPRO-4 later claims to
  decide exception semantics empirically. The IR must represent exception
  structure without deciding it, or version the selected interpretation after
  the study.
- v2 does not extract the richer modality, typed scope, derived expressions, or
  source-backed precedence the IR requires. A downstream dataclass cannot
  invent them. Define a versioned lowering/enrichment step with provenance and
  refusal behavior; preserving 770 tests is not a reason to freeze an
  insufficient schema.
- Refusing `string` by default conflicts with the Dutch anchor's categorical and
  `contains()`-based string inputs and string outputs. Run a provider-free corpus
  feature census before freezing `SUPPORTED_THEORIES`; define a source-backed
  string→enum normalization if that is the intended subset.

**Required correction:** publish an IR semantics document and JSON/schema
version before implementation, with denotational examples, field lineage,
unknown/null behavior, exception interpretation as an explicit parameter, and a
corpus feature-coverage report. The compiler must consume the complete rule,
not treat `rule["execution"]`—which currently contains only columns, targets,
and hit policy—as the semantic program.

#### P7. Chunk coverage is not rule coverage, and PIPE-2 still permits loss

The current compact extraction prompts request **up to five rules per batch**.
Processing every chunk therefore proves source-read coverage, not semantic rule
recall. A 4,500-word batch containing more than five obligations can be read
successfully while omitting most rules. `target_rules` does not currently bound
the final rule count; it controls how many batches are selected. Retaining that
name after removing the batch cap would be misleading.

PIPE-2 says clipping may remain if `bytes_dropped` is recorded, while PIPE-1/G0
say any truncation fails. A chunk is already the organizer's boundary, so “clip
only at a chunk boundary” does not define how an oversized chunk is subdivided.

**Required correction:**

- distinguish `source_chunk_coverage`, `successful_batch_coverage`, and measured
  `rule_recall`; never call the first two document completeness;
- replace `target_rules` with an explicit pilot batch limit, or remove it from
  full mode;
- re-split oversized chunks before prompting with stable source offsets and
  overlap/deduplication rules; full mode must have zero dropped bytes;
- define the original source document as the unit through Agent 1, extraction,
  optimization, compilation, and scoring, including how cross-document
  dependencies are isolated or intentionally modeled; and
- annotate a small complete-rule gold set to estimate extraction recall or use a
  preregistered saturation audit. Without one, G0 makes the denominator traceable
  but not semantically complete.

#### P8. The proposed filesystem leakage guard is not a security boundary

A subprocess working directory that “cannot reach `gold_models/`” can still
read absolute paths or parent directories. `_assert_gold_unreachable()` is only
an assertion unless the gold files are genuinely absent from its mount or
process sandbox. The proposed threshold-coincidence audit also confuses leakage
with legitimate source thresholds: legal text and gold DMN should often share
numbers.

**Required correction:** generate queries in a separate checkout/container with
only an allow-listed, content-addressed source packet mounted read-only. Pass the
result across a one-way artifact boundary to a distinct labeler that has gold.
Test denial with adversarial absolute, parent-relative, symlink, environment,
and manifest paths. Audit provenance and information flow, not mere threshold
coincidence.

#### P9. The manifest is not sufficient to make a run immutable or reproducible

Content-addressing a small metadata object does not make its referenced inputs
or outputs immutable. The proposed manifest omits schema/metric versions,
Python and dependency locks, OS/architecture, prompt hashes, provider/model
snapshot, upstream commit, per-stage input/output hashes, retry/failure records,
refusal counts, and artifact lineage. The repository currently ignores corpora
and pipeline outputs, while the plan commits `results/`; the release boundary is
not specified.

**Required correction:** define a versioned run bundle and validator. Hash every
referenced artifact, record environment and stage lineage, distinguish local
restricted artifacts from publishable aggregates, and fail validation on a
missing reference. Add a lock/constraints file: `z3-solver`, `lxml`, SciPy, and
statsmodels include native components/wheels, so the statement that the added
runtime is “pure Python” is false. Ordinary CI may stay offline, but the
publication workflow needs required jobs for the pinned DMN engine and artifact
validation.

#### P10. The statistical plan mixes incompatible levels and powers the wrong decision rule

The estimand is described as a **per-model** Spearman correlation, but also as
“pooling all runs,” followed by a mixed model with a random intercept per model.
If DA and OE are first aggregated per model, there are no repeated run-level
observations left for that random intercept. If runs are retained, ordinary
Spearman correlation does not define the stated mixed-effects analysis. Scores
are bounded proportions with ties, refusals, unequal query counts, and likely
missingness.

Power against `H0: ρ = 0` does not establish the success rule “ρ ≥ 0.6 with CI
lower bound > 0.3.” The relevant null for that decision is at least `ρ ≤ 0.3`,
with sensitivity to ties and measurement error. Expanding to the excluded 37
after seeing low power also changes the population and cannot be an automatic
fix.

**Required correction:** after P1 is resolved, specify one observation table,
one aggregation rule, missing/refusal handling, the exact bootstrap nesting,
and the estimand for repeated runs. Simulate power for the actual acceptance
rule and plausible tie/missingness structure. G3 may proceed to a negative
finding only when leakage, precision, power, and protocol-validity gates pass;
an invalid or uninformative estimate is not the same as evidence of low
association.

#### P11. Dependency, assumption, repair, and reward audits remain too easy to pass

- A hand-reviewed set of 60 selected pairs has no interpretable recall unless it
  is sampled from a declared candidate universe with negatives, class balance,
  annotation guidance, independent review, and adjudication. “Metric present”
  is not an adequate G0 gate.
- Rejecting each assumption where `A → h` misses a set where
  `A₁ ∧ A₂ → h` even though neither assumption alone entails the conclusion. It
  also does not establish legal permissibility. Report set-level entailment,
  source/background-law provenance, and blinded expert admissibility separately.
- A CEGIR witness proves an internal formal defect, not which extracted clause
  should change. Repairs need source-evidence preservation, omission checks,
  held-out evaluation, and a deletion/no-op baseline; otherwise deleting rules
  is an attractive “repair.”
- CUAD categories, 17 ContractNLI hypotheses, and Dutch gold I/O are not complete
  clause inventories. They cannot make an omission-proof coverage reward. Four
  hard-coded degenerate policies can be overfit; use held-out adversarial search
  and never use evaluation gold in a training reward.

**Required correction:** give each of these tasks a frozen sampling frame,
independent oracle, quantitative failure threshold, and contamination boundary.
Keep results `requires_review: true` when the oracle or adjudication is absent.

#### P12. The plan's own definition of done is not satisfied

The plan says every task has a named pytest or recorded artifact, but BENCH-1b
has no acceptance block, RL-1/RL-2/RL-4 lack individual acceptance criteria,
and `OPS-*` is announced but never defined. Some recorded-artifact acceptances
check only existence, not schema validity or scientific adequacy. The claim
“new code only; nothing existing is moved” also sits beside PIPE tasks that
explicitly edit existing agents, CLI, and prompts.

**Required correction:** create one task registry with ID, owner, inputs,
dependencies, outputs, acceptance command, evidence tier, estimate, and status.
Validate it in CI against the plan. “File exists” must be paired with a schema
validator and substantive gate. Remove unused task families and resolve `C1..C4`
versus `PIPE/IR/BE` naming.

### Required replan before G0 is called green

Use two tracks that join only after their prerequisites are real:

```text
Track A — external anchor
  A1 evaluator replay on released artifacts
  A2 optional fresh-generation replication
                     ┐
                     ├─> J1 matched adapter + minimal compiler
Track B — this repo  │
  B0 document identity / zero-loss source coverage
  B1 v2 optimizer handoff + audited dependency sampling
  B2 corpus feature census + versioned IR semantics
  B3 lowering oracle + solver core + reference evaluator
                     ┘

J2 backend differential validation + third-party engine
J3 instrument study, only after redefining DA/sOE and freezing statistics
J4 one second-domain claim with its exact transfer boundary
J5 CEGIR, then optional RL only after independent anti-omission gates
```

Minimum gate corrections:

1. **G0:** all task acceptances pass; original-document lineage is complete;
   zero source bytes and zero failed batches are silently dropped; extraction
   recall/saturation and dependency recall have declared sampling frames; every
   unsupported semantic construct is counted.
2. **A1:** released Dutch evaluation replays under a pinned environment with
   exact/tolerance-defined agreement. A2 is reported separately.
3. **Compiler gate:** v2→IR lowering passes an independent semantic oracle, then
   all required backends agree on a coverage-audited suite. Backend agreement
   alone is not labeled compiler correctness.
4. **Instrument gate:** the metric is correctly named and independently defined;
   query generation is isolated by an actual information boundary; negative
   controls, power, aggregation, missingness, and success/failure/invalid
   outcomes are frozen before evaluation.
5. **Publication gate:** result bundles validate, restricted inputs are absent,
   all headline values trace to immutable manifests, and claims distinguish
   implemented, run, valid, exploratory, refused, and unrun work.

### Bottom line

The revised proposal now contains a plausible research direction, and this plan
contains much of the right engineering work. The immediate defensible work is
PIPE-1..3, a provider-free corpus/IR census, and an exact replay of the released
Dutch evaluator. The primary scientific claim should remain **uncommitted**
until P1, P2, P4, P5, and P10 above are resolved. In particular, do not call the
current DA gold-free, do not call four internally agreeing backends compiler
correctness, and do not treat a low or high correlation as interpretable until
the metric and sampling process have independent validity.
