# NeurIPS 2027 — Development Plan (v2, post-second-and-third review)

> **v2 changes.** The second-pass review (§14) raised 12 blocking findings; the
> proposal's §27 (in `neurIips-proposal-2027.md`) adds 17 more from a third pass. All are applied here. The four
> that change this plan most: the **effort arithmetic was wrong** (G0 is 35 pd,
> not 28; totals 121/141, not 114/134); the **phase graph could not execute in
> its stated order**; **backend agreement is not compiler correctness**; and the
> **string theory is a G0 blocker**, because refusing it drops the primary
> endpoint to n = 24, where it fails its own success criterion (proposal §9.4).

> **Implementation status (2026-08-24).** PIPE-1, PIPE-2, and PIPE-3 are
> **done** — full corpus coverage and the v2-aware optimizer handoff both
> landed with tests (826/826 passing) on
> [PR #10](https://github.com/rrahimi-uci/compliance-to-code/pull/10). IR-2's
> census **tool** is built and unit-tested on the same PR, but has **not yet
> run against real pipeline output** — none exists in this repo yet, so
> `docs/theory_coverage.md` / `docs/expressiveness_census.md` are not
> populated. **A1a is done**: `docs/anchor_release_audit.md` (same PR)
> resolves the open question in §4.1 and §15.3 below — the anchor's generated
> models and result files **are** released, so **A1b is executable, not
> conditional**, contrary to what §4.1 says further down. That section is
> left as originally written (rather than silently rewritten) with a pointer
> to this correction, matching this plan's own convention of recording what
> changed and why rather than editing history quietly.

**Companion to** [`neurIips-proposal-2027.md`](neurIips-proposal-2027.md) (v3).
The proposal argues *what to claim*; this plan specifies *what to build, in what
order, and what proves each step done*.

| | |
| --- | --- |
| Scope | The minimum paper: G0 (measurement unit) → G1 (external reproduction) → G2 (compiler correctness) → G3 (instrument validation) → G4 (one non-Dutch domain + CEGIR). G5 (solver-reward RL) is conditional and specified but not scheduled as committed work. |
| Horizon | 2026-09-01 → 2027-04-15 (freeze), submit ~2027-05-01 |
| Task IDs | `PIPE-*`, `IR-*`, `BE-*`, `BENCH-*`, `ASM-*`, `STAT-*`, `RL-*`, `A*` (anchor track), `J*` (join points), `CEGIR-*`. **`OPS-*` and `REPRO-*` are removed** — `OPS-*` was declared and never used, and `REPRO-*` is superseded by the A/J split (§14 P12). `C1..C4` survives only as a `cli/compile.py` sub-command grouping, not as task IDs. |
| Effort unit | **pd** = person-day for one engineer already fluent in this codebase. Estimates are for building *and* testing, not for research iteration. |
| Definition of done | Every task lists an acceptance test that is a named `pytest` test or a recorded artifact. A task with no acceptance test is not in this plan. |
| Non-negotiable | **No task that consumes a measurement may start before its G0 prerequisite is green.** The two confirmed pipeline defects (proposal §12.4) make every corpus-level denominator wrong until fixed. |

---

## 0. Critical path — two tracks, joining only when prerequisites are real

**Restructured per §14 P2**, which correctly showed v1's single chain could not
execute: it ran our compiled artifacts and compiled 58 models under three
exception readings in G1, while the compiler and solver were scheduled in G2.

```
TRACK A — external anchor (consumes only upstream artifacts; runs in parallel)
  A1a  audit what the anchor actually released      <- do this FIRST, 0.5 pd
  A1b  evaluator replay (only if A1a says possible)   exact / declared tolerance
  A2   fresh-generation replication (separately preregistered)
  A3   license + reuse posture (open until a reply arrives)

TRACK B — this repository (blocks everything measured)
  B0  PIPE-1/2   document identity, zero dropped bytes, rule_recall measured
  B1  PIPE-3/4   v2 optimizer handoff + audited dependency sampling
  B2  IR-2       corpus feature census + expressiveness census  <- BEFORE freezing
  B3  IR-1/IR-3  IR semantics doc, string theory, solver core, lowering oracle
                                              |
                     A ─────────────┬──────────┘
                                    v
  J1   our artifacts through their executor (needs B3)
  J1b  defeater reading decided empirically (needs B3)
                                    v
  J2   G2: lowering correctness  AND  backend agreement   (two claims, not one)
                                    v
  J3   G3: instrument study — AFS vs OE, after the metric is redefined (§9.2 of
           the proposal) and the statistics are frozen
                                    v
  J4   G4: one second domain, with its transfer boundary stated
                                    v
  J5   G5: CEGIR, then RL only after independent anti-omission gates pass
```

**Two non-negotiables.** ① No task that consumes a *measurement from this
pipeline* starts before its Track-B prerequisite is green. ② Track A may start
immediately, because it measures someone else's released artifacts — that is the
whole reason to split it out.

**A machine-readable task DAG** (`plan/tasks.yaml`, §14 P12) is validated in CI
and fails on a missing or cyclic dependency, so this diagram cannot drift from
the schedule again.

---

## 1. Dependencies to declare (and the history that makes this sensitive)

PR #6 removed a `compiler/` scaffold and its `lxml` dependency precisely because
they were declared before any code existed. **This plan re-introduces both only
with working code in the same commit**, and each addition carries a one-line
justification in `requirements.txt`, matching the file's existing comment style.

| Package | Used by | Justification | Added at |
| --- | --- | --- | --- |
| `z3-solver` | `utils/smt.py`, all seven solver queries | The verification layer is SMT. **Correction (§14 P9): not pure Python** — ships `py3-none-<platform>` wheels carrying native libz3. Verified on PyPI. | **G0** (IR-3 needs it; see §15 P2) |
| `lxml` | `utils/dmn_emit.py` | DMN 1.3 XML emission with XSD validation; `xml.etree` cannot validate. **Native (cp3XX platform wheels).** | BE-2 |
| `scipy` | `bench/stats.py` | Spearman ρ, bootstrap CIs, Holm–Bonferroni. | STAT-2 |
| `statsmodels` | `bench/stats.py` | Mixed-effects model with a random intercept per document (STAT-2). | STAT-2 |
| *(dev only)* `hypothesis` | `tests/test_feel_properties.py` | Property-based differential testing of the FEEL evaluator vs. the SMT encoding (BE-1/BE-3). | BE-1 |
| *(dev only, optional)* a JVM + a DMN engine | `bench/dmn_engine_harness.py` | BE-4's third-party cross-check. **Kept out of `requirements.txt`** — gated behind an env var and skipped by default so `pytest` stays provider-free and JVM-free. | BE-4 |

**Correction to v1's claim.** v1 said "everything above is either pure Python or
skipped by default." **None of the four runtime additions is pure Python** —
verified against PyPI: `z3-solver`, `lxml`, `scipy`, and `statsmodels` all ship
platform-specific wheels with native components; none publishes a
`py3-none-any` wheel. What is true and what matters:

- **No compiler is needed** on supported platforms — all four publish prebuilt
  binary wheels.
- **Python 3.14 (this repo's version) is supported:** `lxml`, `scipy`,
  `statsmodels`, and `hypothesis` publish `cp314` wheels; `z3-solver` uses
  platform-tagged `py3` wheels. Recorded so it is not re-litigated.
- **A lock/constraints file is therefore required**, not optional, because native
  wheels pin to platform and ABI. `requirements-lock.txt` with hashes lands in
  the same commit as the first dependency.
- **`pytest` still runs with no API key, no network, and no JVM** — that
  constraint is preserved, and the third-party DMN engine job stays env-gated.

---

## 2. Module layout

**Corrected (§14 P12).** v1 said "new code only; nothing existing is moved" —
false, and it sat directly above four tasks that edit existing files. Accurately:
**new modules below, plus in-place edits to four existing files** —
`agents/agent_03_rules_extractor.py` (PIPE-1/2),
`agents/agent_06_knowledge_graph_optimizer.py` (PIPE-3/4), `cli/extract.py`
(PIPE-1), and the domain prompt packs (PIPE-3). Nothing is *moved*; four things
are *modified*, and each modification has a regression test.

Follows the repo's conventions: dependency-light `utils/`, one module per
concern, no third-party graph library, docstrings that explain *why*.

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

## 3. Phase G0 — make the measurement unit real (Sep–Oct 2026, **43 pd**)

*v1 said 28 pd. Its own items summed to 35 (§14 P3, confirmed by recomputation);
the string theory (+4), the census reordering (+1), and rule-recall measurement
(+3) bring it to **43**. §9's table is now generated from the items, not typed.*

Nothing here is research. All of it is prerequisite, and it is the highest-value
work in the plan because every later number depends on it.

### 3.1 PIPE-1 — per-document extraction unit with enforced chunk coverage — 4 pd

**✅ Done — [PR #10](https://github.com/rrahimi-uci/compliance-to-code/pull/10).**
Implemented as a `--pilot-batch-limit` opt-**out** rather than the
`--unit document` opt-**in** sketched below: full coverage is now the
*default*, with `chunk_coverage.json` and a standalone `full_coverage_violation()`
providing the fail-closed check (extracted as a pure function specifically so
it's testable without a live API key). See the PR description for the exact
design deltas from what follows.

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

### 3.2 PIPE-2 — re-split oversized chunks; zero dropped bytes in full mode — 2 pd

**✅ Done — [PR #10](https://github.com/rrahimi-uci/compliance-to-code/pull/10),**
alongside PIPE-1: `split_oversized_content()` re-splits at word boundaries
with a configurable overlap (default 150 words) instead of truncating.
Property-tested for zero-gap coverage across 5 size/overlap combinations plus
two pathological cases (a single token wider than the window; an overlap
larger than the window itself) — both still terminate and drop zero bytes.

Agent 1 targets ~2,000-word chunks; Agent 3 clips at 8,000 characters. Long
chunks silently lose their tails.

**Corrected (§14 P7).** v1 said PIPE-1 fails on any truncation *and* that PIPE-2
may clip if `bytes_dropped` is recorded. Those contradict. Also "clip only at a
chunk boundary the organizer produced" does not say what happens to an
**oversized** chunk, which is exactly the failing case.

**Change.** In full mode there is **no clipping at all**: an oversized chunk is
**re-split** before prompting, with stable source offsets, a declared overlap,
and a deduplication rule for facts appearing in two windows. `bytes_dropped` must
be **0** in full mode; the field remains only so pilot mode can report it.

**And three coverage notions are separated, because v1 conflated them
(§14 P7):**

| Metric | Means | Does *not* mean |
| --- | --- | --- |
| `source_chunk_coverage` | every chunk was read | that rules were extracted from it |
| `successful_batch_coverage` | every batch returned parseable output | that it returned all the rules present |
| `rule_recall` | **measured** against a complete-rule gold set | — |

The extraction prompts request **up to `rules_per_batch` (5) rules per batch**, so
reading a 4,500-word batch containing nine obligations can succeed while omitting
four. **Reading coverage is not rule coverage, and only `rule_recall` may be
called completeness.** `target_rules` is renamed `--pilot-batch-limit` and is
**rejected in full mode**, since it never bounded the rule count — it bounded
batch selection.

**Acceptance.** `tests/test_chunk_coverage.py::test_full_mode_drops_zero_bytes`;
`::test_oversized_chunk_is_resplit_with_stable_offsets`;
`::test_pilot_batch_limit_rejected_in_full_mode`; and
`tests/test_rule_recall.py::test_rule_recall_reported_against_gold_set` (a
20-document hand-annotated complete-rule set, or a preregistered saturation
audit — **new work, +3 pd**).

### 3.3 PIPE-3 — full v2 fields into the optimizer — 3 pd

**✅ Done — [PR #10](https://github.com/rrahimi-uci/compliance-to-code/pull/10).**
`_rule_summary_v2()` matches the design below exactly, including the
`include_related_entities` parameter for the one call site that never
included that field. 9 tests, including integration tests asserting the
actual JSON handed to `prompt_manager.format_prompt` carries v2 structure.

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
(proposal §24 R4). The IR is where the gap closes. **The v2 contract is not changed** —
the IR is a separate, downstream, typed lowering target, which keeps every
existing test valid.

**Three corrections to v1's IR before any code (§14 P6, proposal §9.4):**

1. **`norm_kind` moves off `Var`.** A variable is not obligatory or permitted —
   a *norm* is. The same variable can be obligatory in one rule, permitted in
   another, prohibited in a third. It belongs on `Rule` (or per-`Assign`).
2. **`scope` is not one `Formula`.** Jurisdiction, parties, authority, effective
   dates, document version, and applicability metadata are not all executable
   predicates. Split `scope_predicates: Formula` (executable) from
   `scope_metadata: Mapping` (recorded, not evaluated).
3. **Exception semantics is a *parameter*, not a constant.** v1 hard-coded
   `C ∧ ¬⋁X` in IR-1 while REPRO-4 claimed to decide it empirically. The IR now
   carries `exception_reading: {"defeater", "conjunctive", "ignored"}` and the
   compiler is run under each; the decision is *recorded* after the study, not
   assumed before it.

**And the supported subset must include strings.** v1's
`{bool, int, real, enum}` refuses `string`, which refuses **34 of the 58 anchor
models (59%)** — the Requirements half, which needs `contains()` substring
predicates, binned-numeric strings, and null-checks. That drops the primary
endpoint to n = 24, where its declared success criterion fails even at the true
target effect (proposal §9.4). A naive string→enum normalisation is **not sound**
for `contains()`. **+4 pd** for a string theory with those three predicate forms.

`utils/lexec_ir.py`, frozen dataclasses, no I/O, no LLM:

```python
# Corrected v1 subset. `string` is REQUIRED, not optional -- see above.
SUPPORTED_THEORIES = {"bool", "int", "real", "enum", "string"}
STRING_PREDICATES  = {"eq", "contains", "is_null", "in_binned_range"}

@dataclass(frozen=True)
class Var:
    name: str            # globally resolved, canonical
    theory: str          # SUPPORTED_THEORIES
    role: str            # input | derived | output
    domain: Domain       # EnumDomain | IntervalDomain | BoolDomain
    unit: str | None
    # norm_kind REMOVED from Var (§14 P6): modality is a property of a norm,
    # not of a variable. It now lives on Rule.

@dataclass(frozen=True)
class Atom:      var: str; op: str; value: Literal | VarRef
@dataclass(frozen=True)
class Formula:   # And | Or | Not | Atom  -- Not is IR-only, never extracted
@dataclass(frozen=True)
class Rule:
    rule_id: str
    condition: Formula
    exceptions: tuple[Formula, ...]       # structure only -- reading is a parameter
    exception_reading: str                # defeater | conjunctive | ignored (REPRO-4 decides)
    outcomes: tuple[Assign, ...]
    norm_kind: str | None                 # obligation | permission | prohibition | definition
    scope_predicates: Formula | None      # executable
    scope_metadata: dict                  # jurisdiction, parties, dates, version -- recorded only
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
missing input makes an atom *unknown*, not false; three-valued Kleene evaluation,
with the collapse rule stated per hit policy rather than "declared" in the
abstract: `UNIQUE`/`ANY` collapse *unknown* to no-match; `COLLECT` records it as a
distinct outcome).

**Where the missing semantics come from (§14 P6).** v2 does not extract modality,
typed scope, derived expressions, or source-backed precedence. A downstream
dataclass cannot invent them. So IR-1 ships with a **versioned enrichment step**:
each such field is either (a) derived deterministically from v2 with a recorded
derivation rule, (b) obtained by a *separate, logged* enrichment pass whose output
carries provenance and is independently checkable, or (c) **refused and counted**.
There is no fourth option, and "preserving 770 tests" is not a reason to pretend
the field exists.

**Acceptance.** `tests/test_lexec_ir.py` — one test per refusal code asserting it
fires; `::test_operator_theory_matrix_rejects_gt_on_bool`;
`::test_variable_reference_cycle_refused`;
`::test_lowering_is_total` (every v2 rule either lowers or produces ≥1 refusal —
never silently drops).

### 3.6 IR-2 — corpus feature census **before** freezing the subset — 3 pd

**⏳ Tool done, not yet run — [PR #10](https://github.com/rrahimi-uci/compliance-to-code/pull/10).**
`utils/corpus_census.py` implements `variable_type_census`, `value_type_census`,
`operator_census`, `coverage_at_subset` (the general form of "how many rules
lower without a refusal under candidate subset S"), and `expressiveness_signal`,
plus a `scripts/corpus_census.py` CLI, all with 19 unit tests against synthetic
v2 fixtures. **What remains:** no real pipeline output exists in this repo yet,
so the tool has not been run against a real graph and `docs/theory_coverage.md`
/ `docs/expressiveness_census.md` are not populated — that run is still this
task's actual acceptance criterion, and it is not yet met.

**Order corrected (§14 P6).** v1 froze `SUPPORTED_THEORIES` and *then* measured
frequency. That is backwards, and it is how the string blocker was missed. The
census runs **first**, it is provider-free (pure parsing of v2 graphs and the
anchor's gold models), and the subset is frozen from its output.

Census over the anchor's 58 models and one non-Dutch corpus: frequency of `date`,
`date_time`, `duration`, `string` (broken out by `eq` / `contains` /
`is_null` / binned-numeric), `list`, `range`, `variable_reference`; plus the
**§14.6 expressiveness census** from the proposal (how much source content a
decision-table semantics can express at all).

**Acceptance.** committed `docs/theory_coverage.md` and
`docs/expressiveness_census.md`;
`tests/test_lexec_ir.py::test_supported_theories_matches_census` — the frozen
subset must cover ≥ 55 of the 58 anchor models, and the test fails if it does not.

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

**BENCH-4 — run bundle and release boundary (new, +3 pd; §14 P9, N13).** A
content-addressed metadata object does not make its referenced inputs immutable.
The run bundle records: schema and metric versions; `requirements-lock.txt`
hashes; OS/arch/Python version; prompt hashes; provider and model snapshot;
upstream anchor commit; **per-stage input/output hashes**; retry and failure
records; refusal counts; and artifact lineage. A validator **fails on a missing
reference**.

And the release boundary is specified, because it currently is not: `.gitignore`
covers `pipeline-output/` but **not `results/`**, which this plan commits. Fix:
`results/raw/` (restricted inputs, generated artifacts) is gitignored;
`results/aggregates/` (publishable tables, manifests, hashes) is committed. No
restricted input may appear in a published bundle.

**Acceptance.** `tests/test_query_leakage.py::test_gold_absent_from_generator_mount`
(and adversarial denial: absolute, `../`, symlink, env-var, manifest-declared
paths); `tests/test_manifest.py::test_validator_fails_on_missing_reference`;
`::test_best_of_k_is_tagged`;
`::test_no_restricted_input_in_publishable_bundle`.

**G0 exit criteria (all four must hold).** ① chunk coverage 100% on a frozen unit
or the run fails; ② dependency precision/recall reported against the 60-pair
fixture; ③ every unsupported construct produces a counted refusal; ④ a manifest
exists for every run and is content-addressed.

---

## 4. Phase A/G1 — anchor work, split into two different claims (~13 pd)

**Restructured (§14 P2, P4).** v1's G1 was incoherent in two ways: it ran "our
compiled artifacts" (REPRO-2) and compiled 58 models under three exception
readings (REPRO-4) **before the compiler existed in G2**; and it conflated a
deterministic evaluator replay with a stochastic experimental replication. Split:

### 4.1 A1 — release-contents audit, then evaluator replay — 3 pd

**Runs in parallel with G0**, because it consumes only upstream artifacts and
none of this pipeline's measurements. That resolves the v1 contradiction where
day 6–7 measured something before G0 was green.

**✅ A1a done, and resolved in the favorable direction —
[PR #10](https://github.com/rrahimi-uci/compliance-to-code/pull/10),
`docs/anchor_release_audit.md`.** The paragraph below (kept as originally
written, per this plan's convention of not editing history quietly) asked the
right question and got it wrong. The actual repository tree was audited via
the GitHub API (pinned commit `6a4844f`), not inferred from the README:
`generated_models/` contains **exactly 1,900 files** (95 models × 4
conditions × 5 runs — an exact match to the paper's own stated count), and
`results/metrics.csv` is a real 428 KB, 1,900-row file with per-generation
outcome-equivalence columns. `metrics/dmn_executor.py` and
`graph_similarity.py` — the code that *produces* those metrics — are released
too, so independent recomputation is possible, not just a replay of committed
numbers. **A1b below is executable as scoped, not conditional; A2 is now
genuinely optional follow-on work rather than the only route.**

One caveat the audit surfaced and did not resolve, left as A1b's actual first
task: a quick attempt to reproduce the paper's headline 42.6%/60.4% by
macro-averaging `results/metrics.csv`'s `outcome_agreement` column directly
did **not** reproduce those numbers (and recovered only 1 distinct testable
Requirements `activity_id` against the paper's stated 34) — the exact
aggregation the paper uses is not obvious from column names alone and needs
to be read from `evaluation/run_evaluation.py` / `metrics/dmn_executor.py`,
not guessed. See `docs/anchor_release_audit.md` for the full finding.

**A1a — audit what is actually released (superseded by the above; kept for
the historical record).** §14 P4 asserts the repo "contains generated models,
evaluation code, and results." I could **not confirm** that the *generated*
models or expected result files are published — only `source_models/`,
`gold_models/`, `legal_text/`, and the harness. **If the generated artifacts
are absent, a deterministic replay is impossible and A1b does not exist**;
the only route is A2. Audit before scheduling.

**A1b — evaluator replay (no longer conditional — see the resolution
above).** Pin the upstream commit and environment; checksum released inputs,
generated artifacts, and expected result files; run `evaluation/run_evaluation`;
require **exact agreement, or a tolerance declared in advance**. v1's "within
our bootstrap CI" was the wrong standard — a deterministic replay of released
files has no sampling error. **Concretely, given the audit's caveat above:**
before comparing anything against `metrics.csv`, first read
`evaluation/run_evaluation.py` and `metrics/dmn_executor.py` closely enough to
state the exact filter/aggregation that produces 42.6%/60.4%/33%/50%, and
verify it against the raw 1,900 rows *before* trusting any further replay.

**Acceptance.** `docs/anchor_release_audit.md` recording exactly what is
published — **done**; and `results/a1_replay/` with a byte- or
tolerance-level match statement — not yet done.

### 4.2 A2 — fresh-generation replication (separately preregistered) — 4 pd

A different claim with different costs and failure modes: new generations at the
anchor's stated temperature, its example-selection schedule, its prompts, and 5
runs — subject to provider drift we cannot control. **Preregister whether this is
in scope at all.** Record model snapshot, prompts, examples, run mapping, API
parameters, failures, and cost; compare distributions with a **declared
equivalence margin**, not a significance test.

### 4.3 J1 — our artifacts through their executor — 4 pd

**Moved after the compiler and solver core** (was REPRO-2 in G1, which was
impossible). Depends on: IR-1, IR-2, IR-3, BE-1, BE-3.

**The comparison table is corrected (§14 P4, proposal §9.3).** The anchor
publishes OE for **`Text+io` and `Text+srl+io` only** — verbatim: *"We limit
ourselves to the io and srl+io conditions, as these have consistent inputs and
outputs, enabling direct comparison."* So:

| Our condition | Compared against | Status |
| --- | --- | --- |
| raw legal text | **nothing** — no published `text` OE exists | reported **standalone, no comparison claim** |
| self-derived interface | `+io`, *with* interface-derivation accuracy reported | the interesting result; new sub-metric |
| gold I/O supplied | `+io` | **labeled gold-leaking**; reproduction check only |

**Acceptance.** `results/j1/` with per-model OE, all 5 runs retained, a manifest,
and a measured **interface-derivation accuracy** (how often our source-derived
I/O signature matches the gold signature).

### 4.4 J1b — defeater semantics decided empirically — 2 pd

**Moved after the compiler** (was REPRO-4). Compile the anchor's 58 under all
three `exception_reading` values and compare OE. The anchor has gold *behavior*,
which our self-generated vectors do not.

**Acceptance.** `docs/defeater_semantics.md` with three OE numbers, CIs, and the
decision — **and the IR's `exception_reading` default is set only after this**,
not before (§3.5).

### 4.5 A3 — license and reuse posture — 1 pd

Characterized in proposal §22: repo says CC BY 4.0, arXiv page says CC BY-SA 4.0,
and the **upstream government models carry no explicit license** — reuse rests on
the repo's own assumption about the Dutch *Wet hergebruik van
overheidsinformatie*. §14 is right that this is **characterized, not resolved**:
resolution is receipt of permission or a documented legal basis. Reference source
models by commit hash; never re-host; email the DSO and the author.

**Acceptance.** `docs/data_licensing.md` with the position, the emails sent, and
any reply. **Status stays `unresolved` until a reply arrives.**

## 5. Phase G2 — two separate claims, because agreement is not correctness (~30 pd)

**Corrected (§14 P5).** v1 called four-way backend agreement "validate the
compiler." It is not: all four backends can agree while sharing **one wrong
v2→IR lowering** or one wrong reading of the source. XSD validation proves XML
shape, not FEEL meaning. And a conformance suite generated *from* the
implementation can omit exactly the cases the implementation mishandles. Two
claims, tested separately:

**Claim 1 — lowering correctness (new, +8 pd).** Hand-authored v2→IR fixtures
with **independently specified denotations** (written by someone who did not
write the lowering), mutation testing of the lowering, refusal-oracle tests, and
anchor source/gold cases. Plus **loss accounting**: every v2 field is consumed,
deliberately ignored with a recorded reason, or causes a counted refusal — no
field may be silently dropped.
*Acceptance:* `tests/test_lowering_oracle.py::test_every_fixture_matches_independent_denotation`;
`::test_every_v2_field_is_consumed_ignored_or_refused`; mutation score ≥ 80%.

**Claim 2 — backend semantic agreement (below).** Independently generated IR
programs covering **every operator × theory × null × hit-policy branch**, plus
metamorphic tests, plus a pinned third-party engine. Coverage of that branch
matrix is itself reported.

**The release gate may say "four-way agreement" only when the engine job actually
ran.** A test that is normally skipped cannot support the claim (§14 P5).

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

**G2 exit criteria (both required).** ① Lowering correctness: every
independent-denotation fixture matches, loss accounting is complete, mutation
score ≥ 80%. ② Backend agreement: three backends (four when the engine job ran)
agree on 100% of a **branch-coverage-audited** suite, with every disagreement
root-caused. **Neither alone may be reported as "compiler correctness."**

---

## 6. Phase G3 — validate the instrument (Dec 2026–Jan 2027, **24 pd**)

*+10 pd: **LEXEC-Perturb is restored to committed scope.** Once the metric is
corrected (proposal §9.2), metamorphic relations are one of only three
artifact-free signals available, and the only one needing no new expert labels.
Cutting it leaves C2 with nothing to validate. Also ~90 annotator hours.*

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

**Acceptance** (missing in v1 — §14 P12).
`tests/test_contractnli_adapter.py::test_split_is_frozen_and_content_addressed`;
`::test_all_607_documents_load_with_17_hypotheses_each`;
`::test_evidence_spans_align_to_document_offsets`. Plus a committed
`docs/contractnli_transfer_boundary.md` stating exactly what transferring from
the Dutch anchor to ContractNLI does and does not license — different language,
legal system, document genre, and **no gold artifact**, so ContractNLI supplies
an AFS and can never supply an OE.

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

**Acceptance for RL-1/2/4** (missing in v1 — §14 P12).
`tests/test_reward_components.py::test_coverage_reward_uses_an_inventory_the_policy_did_not_produce`;
`::test_held_out_vectors_are_not_policy_generated`;
`::test_self_vector_replay_is_reported_but_never_rewarded`;
`::test_every_reward_component_is_logged_separately`. And a release gate: no RL
result is reported without the Pareto front, output size, symbol-reuse rate, and
omission rate alongside the scalar.

GRPO on an 8–14B model (or LoRA on ~32B). Report **every** reward component, the
Pareto front, output size, symbol-reuse rate, and omission rate — never the
scalar. Never train and evaluate on the same solver-derived witnesses.

**Confirmatory endpoint:** AURC of solver-signal selective compilation vs. the
ported grammar-entropy baseline (a *ported baseline on our task* — not a
comparison to the published AUROC > 0.93, which is a different task and base
rate).

---

## 9. Effort, generated from the task items (§14 P3)

v1 hand-entered these totals and got G0 wrong by 7 pd, which propagated into
every downstream figure and into a scope-cut recommendation that omitted writing
entirely. The table below is **computed from the per-task estimates above**; if a
task estimate changes, this table is regenerated, never edited.

| Phase | Items | pd | Calendar | Slippable? |
| --- | --- | ---: | --- | --- |
| **G0** | 4+5+3+6+12+3+3+7 | **43** | Sep–Oct 2026 | **No.** Everything depends on it |
| **A** (anchor, parallel with G0) | 3+4+1 | **8** | Sep–Oct 2026 | A2 is optional and preregistered separately |
| **J** (after the compiler core) | 4+2 | **6** | Dec 2026 | No |
| **G2** | 8+6+5+6+3+2 | **30** | Nov–Dec 2026 | BE-4 may slip 2 weeks |
| **G3** | 2+4+3+5+10 | **24** | Dec–Jan | **No.** This is the paper |
| **G4** | 4+10+12 | **26** | Feb–Mar | Yes — CEGIR can drop |
| **G5** | 5+5+4+6 | **20** | Mar (conditional) | Yes — designed droppable |
| **Writing** | 15 | **15** | Apr (freeze Apr 15) | No |

| Scope | pd | FTE over ~157 working days (Sep 1 → Apr 15) |
| --- | ---: | --- |
| **Minimum paper** (G0 + A + J + G2 + G3 + writing) | **126** | **0.80** |
| + G4 (second domain + CEGIR) | **152** | **0.97** |
| + G5 (RL) | **172** | **1.10** |

**Corrections to v1's numbers:** v1 claimed 114 / 134 / "73 for G0–G3 + writing."
All three were wrong. The 73 figure omitted writing *and* used the understated
G0; the correct minimum-paper figure is **126 pd**, and the itemized-G0 version of
v1's own scope cut was 95 pd even before this pass's additions.

**What is still not in any pd figure** (§14 P3, and it matters): research and
analysis time as distinct from engineering; ~90 annotator hours for Perturb plus
~60–90 for scenarios and assumption review; legal-reviewer hours for ASM-4;
paid API and GPU spend; external waiting time on the DSO and the anchor authors;
environment repair; and **contingency**. Those are budgeted in proposal §18 by
line, not converted into pd, because converting them would hide them again.

**The honest read.** 0.80 FTE of *pure engineering with zero research allowance*
for the minimum paper, and 0.97 for the version with a second domain. A single
engineer who also has to think, debug someone else's harness, and iterate on
failed experiments will not deliver 126 pd of scheduled work in 157 working days.
**This needs two engineers, or the minimum paper needs to shrink further** — the
next thing to cut is G4 entirely, leaving a single-corpus instrument-validation
paper, which §10 already says is publishable.

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
| Theory refusal rate is high | **IR-2's census, which now runs before the subset is frozen** | implement the temporal theory (+8 pd) or narrow the corpus, reporting the coverage bound either way. **The string case is already known and already in G0** (34/58 models, proposal §9.4) |
| Solver timeouts dominate | timeout rate > 5% on any corpus | bound row counts; cache by rule-set hash; report the rate as a limitation |
| **Scooped on solver-reward RL** — arXiv:2606.16118 §5.6 names it as future work | a preprint appears | G3 is the spine precisely because it does not depend on being first; also, we emailed them (REPRO/ASM), so we may know early |
| ρ estimate is uninformative (wide CI) | STAT-1 power analysis | discovered *before* data collection. **Not a fix: expanding to the 37 excluded models after seeing low power** — that changes the population and cannot be automatic (§14 P10). Legitimate responses: implement the string theory (already G0), obtain a second gold-artifact corpus, or report the study as underpowered and stop |
| Dutch data reuse challenged | any reply from DSO | we never re-host; reference by commit hash; fall back to reporting on their harness only |
| Engineering capacity (§9) | G0 not green by Oct 31 | **cut G4 entirely**, leaving the single-corpus instrument paper: G0+A+J+G2+G3+writing = **126 pd**. v1's "73 pd" figure was wrong twice over (§9) |

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
| 2026-08-24 | **DA retired; AFS / sOE / OE separated** | DA was defined with `gold(q)` and obtained by executing the gold DMN, so it was never gold-free (§14 P1). The property that matters is artifact-freedom, not label-freedom (proposal §9.2). |
| 2026-08-24 | **`string` is in the supported subset, not deferred** | Refusing it refuses 34/58 anchor models and drops the primary endpoint to n = 24, where its own success criterion fails at the true target effect (proposal §9.4). |
| 2026-08-24 | **Exception reading is an IR parameter, not a constant** | v1 hard-coded `C ∧ ¬⋁X` in IR-1 while J1b claimed to decide it empirically (§14 P6). |
| 2026-08-24 | **LEXEC-Perturb restored to committed scope** | It is one of only three artifact-free signals and the only one needing no new expert labels; without it C2 has nothing to validate (proposal §9.2). |
| 2026-08-24 | **Effort table is generated, never typed** | v1's hand-entered G0 was wrong by 7 pd and the error propagated into a scope-cut recommendation (§14 P3). |
| 2026-08-24 | **`norm_kind` on `Rule`, not `Var`; scope split into predicates + metadata** | Modality is a property of a norm; jurisdiction/dates/parties are not executable predicates (§14 P6). |

---

## 13. First two weeks, concretely (corrected)

v1's day 6–7 ran the anchor harness before G0 was green, contradicting its own
non-negotiable (§14 P2). Under the two-track split that contradiction disappears:
Track A consumes only upstream artifacts, so it runs in parallel by design.

**Status (2026-08-24): days 1, 1–2, 3, and 4–5(B) are done — see
[PR #10](https://github.com/rrahimi-uci/compliance-to-code/pull/10).** Day
1's A1a came back favorable rather than blocking, which changes day 4–5(A):
it is no longer "replay if possible, else preregister A2" — replay is
possible, so that slot becomes A1b's real work (find the exact aggregation
recipe in the evaluation code; see §4.1).

| Day | Track | Task | Deliverable |
| --- | --- | --- | --- |
| 1 | A | ✅ **A1a release audit** | `docs/anchor_release_audit.md` — **done: generated models and results ARE published**, resolving the day-1 open question in the favorable direction |
| 1–2 | B | ✅ PIPE-1 | full coverage by default, `chunk_coverage.json`, `full_coverage_violation()`; `test_chunk_coverage.py` green (28 tests) |
| 3 | B | ✅ PIPE-2 | `split_oversized_content()` re-splits with zero dropped bytes; `--pilot-batch-limit` opts into the old lossy/capped behavior explicitly |
| 4–5 | B | ✅ PIPE-3 | `_rule_summary_v2()` at all four call sites; `test_optimizer_v2_handoff.py` green (9 tests) |
| 4–5 | A | A1b (re-scoped, not A2) | replay **is** possible per day 1's finding — this slot is now "read `evaluation/run_evaluation.py` / `metrics/dmn_executor.py` and state the exact aggregation," not a go/no-go decision |
| 6–8 | B | ⏳ **IR-2 census** | tool built and unit-tested (`utils/corpus_census.py`, 19 tests); **not yet run** — needs a real optimized graph or the anchor's own gold models, neither yet in hand |
| 9–11 | B | IR-1 (part 1) | not started — IR semantics document + JSON schema **before** dataclasses; then `utils/lexec_ir.py` with refusal codes |
| 12–13 | B | PIPE-4 fixture | not started — dependency sampling frame declared (universe, negatives, class balance, guidance, independent review, adjudication) — **not a 60-pair convenience sample** |
| 14 | B | BENCH-1 | not started — `bench/adapters/dutch_dmn.py` exposing the 58/37 split; `bench/manifest.py` |

**Two weeks in, the honest status should read:** *the extraction unit is
document-complete with zero dropped bytes, the optimizer sees v2 fields, we know
exactly what the anchor released — favorably — and the corpus feature census
tool exists but has not yet run on real data.* Still no research claim — and
running that census (once a real graph exists) remains the single most
decision-relevant artifact in the list, because if the expressiveness fraction
is small the paper changes shape before any money is spent.

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

---

## 15. Final review (third pass) — disposition and corrections applied

*2026-08-24. §14 is the second-pass review (P1–P12). This section records what
was done about each, plus what the third pass found in this plan specifically.
**Proposal §27** carries the same disposition for the proposal, including the
seventeen findings neither prior review made.*

**Verdict on §14: correct, and it caught two arithmetic errors and one
architectural impossibility that a reader would have hit on day 6.** Eleven of
twelve findings confirmed outright; one (P4's premise about released artifacts)
needs a factual check that is now day 1 of the schedule.

### 15.1 What changed in this plan

| §14 finding | Applied |
| --- | --- |
| **P1** DA is not gold-free | Proposal §9.2 retires DA and separates **AFS / sOE / OE**. G3 now validates *artifact-free signals against artifact-based OE*, with sOE as positive control and random/stratified/biased samples as negative controls. **LEXEC-Perturb is restored to committed scope (+10 pd, ~90 annotator hours)** because it is the only AFS needing no new expert labels |
| **P2** phase graph cannot execute | **§0 rebuilt as two tracks.** Track A (anchor) consumes only upstream artifacts and runs in parallel; J1 (our artifacts through their executor) and J1b (defeater reading) move after the compiler core; the solver core moves into G0 so IR-3 can use it; a machine-readable `plan/tasks.yaml` is CI-validated against cycles and missing deps |
| **P3** effort arithmetic wrong | **§9 is now generated from the task items.** G0 = **43 pd** (v1 said 28; its own items summed to 35, and this pass adds the string theory, the census reordering, and rule-recall measurement). Minimum paper = **126 pd / 0.80 FTE**; +G4 = 152 / 0.97; +G5 = 172 / 1.10. v1's "73 pd" omitted writing *and* used the wrong G0 |
| **P4** replay ≠ replication; OE for two conditions only | **G1 split into A1a/A1b/A2 and J1/J1b.** Replay requires exact or declared-tolerance agreement, not "within our bootstrap CI." The comparison table is corrected: **no published raw-`text` OE exists**, both published conditions are gold-leaking, and **interface-derivation accuracy** becomes a new measured sub-result |
| **P4b** *(third-pass qualification — now resolved, 2026-08-24)* | §14 states the repo "contains generated models, evaluation code, and results." **This was checked, not just claimed**: [PR #10](https://github.com/rrahimi-uci/compliance-to-code/pull/10)'s `docs/anchor_release_audit.md` audited the actual repository tree via the GitHub API and confirmed `generated_models/` (1,900 files, matching 95×4×5 exactly) and `results/metrics.csv` (1,900 rows) are both released. **A1a is done; A1b is executable, not conditional** — see §4.1 above for the one honest caveat the audit surfaced (the exact headline-figure aggregation is not obvious from column names and still needs to be read from the evaluation code) |
| **P5** agreement ≠ correctness | **G2 split into two claims:** *lowering correctness* (independent-denotation fixtures, mutation testing, refusal oracle, loss accounting — +8 pd) and *backend agreement* (branch-coverage-audited suite over operator × theory × null × hit-policy). "Four-way agreement" may only be claimed when the engine job actually ran |
| **P6** IR semantics mislocated/unsettled | `norm_kind` moves from `Var` to `Rule`; `scope` splits into `scope_predicates` (executable) and `scope_metadata` (recorded); **`exception_reading` becomes a parameter** decided by J1b rather than hard-coded before it; a **versioned enrichment step** with provenance is specified for every field v2 does not extract; **IR-2's census runs before the subset is frozen**, and the subset must cover ≥ 55 of 58 anchor models |
| **P7** chunk coverage ≠ rule coverage | Three metrics separated (`source_chunk_coverage`, `successful_batch_coverage`, measured `rule_recall`); **zero dropped bytes in full mode** with oversized chunks re-split at stable offsets; the PIPE-1/PIPE-2 contradiction resolved; `target_rules` renamed `--pilot-batch-limit` and rejected in full mode; a 20-document complete-rule gold set added (+3 pd) |
| **P8** the guard is not a boundary | Proposal §9.6 rewritten: gold **absent from the mount**, one-way artifact hand-off to a separate labeler, adversarial denial tests (absolute, `../`, symlink, env-var, manifest paths). The threshold-coincidence audit is **dropped as confounded** — legal text and gold DMN *should* share numbers — and replaced with source-span provenance on every query |
| **P9** manifest insufficient; "pure Python" false | **Verified against PyPI: none of the four ships a `py3-none-any` wheel.** §1 corrected; a hashed `requirements-lock.txt` is now required, not optional; **BENCH-4 run bundle** added (+3 pd) with per-stage hashes, environment, lineage, refusal counts, and a validator that fails on a missing reference; and the release boundary is specified — `results/raw/` gitignored, `results/aggregates/` committed |
| **P10** statistics mix levels; wrong null | Proposal §9.5 rewritten: run-level observation table with a **model-clustered bootstrap**; mixed-effects demoted to a sensitivity check; **null corrected to H₀: ρ ≤ 0.3**; ties, bounds, missingness, and attenuation specified. **Post-hoc expansion to the 37 excluded models is explicitly rejected** as a remedy for low power |
| **P11** audits too easy to pass | Dependency fixture gains a declared sampling universe with negatives, class balance, guidance, independent review, and adjudication; assumption checking adds **set-level entailment** (`A₁ ∧ A₂ ⊨ h`) and blinded expert admissibility; CEGIR gains a **deletion/no-op repair baseline** so deleting rules cannot look like a fix; coverage rewards use inventories the policy did not produce, with held-out adversarial search rather than four fixed attacks |
| **P12** plan violates its own definition of done | Acceptance blocks added for **BENCH-1b** and **RL-1/2/4**; **`OPS-*` and `REPRO-*` removed**; `C1..C4` demoted to a CLI sub-command grouping; the false "new code only" claim replaced by an explicit list of the **four existing files** that get modified, each with a regression test |

### 15.2 Third-pass findings specific to this plan

Beyond the proposal-side findings in **proposal §27.2**:

- **The string theory is the schedule's real critical path**, not the compiler.
  Refusing it drops the primary endpoint to n = 24, where a true ρ = 0.6 yields a
  95% CI of [0.26, 0.74] — **below the study's own declared 0.3 lower bound** —
  and 54% power. At n = 58 it is [0.40, 0.74] and 88%. That single type theory is
  the difference between a viable and an unviable primary result.
- **IR-2 was scheduled after the subset was frozen**, which is how the string
  blocker went unnoticed for two review passes. Census-before-freeze is now a
  structural rule, not a preference.
- **The plan's own "definition of done" was its most-violated rule.** Three task
  families lacked acceptance criteria and one was never used at all. A plan that
  states a rule and breaks it is worse than one that states no rule, because the
  reader stops checking.

### 15.3 What is still unresolved

1. ~~Whether A1b exists (P4b)~~ — **resolved 2026-08-24, favorably.**
   [PR #10](https://github.com/rrahimi-uci/compliance-to-code/pull/10) audited
   the anchor's actual repository tree: the generated models and result files
   are released. See §4.1's update and the P4b disposition row above. What
   remains open from that audit is narrower: **the exact aggregation recipe**
   that reproduces the paper's headline 42.6%/60.4%/33%/50% from
   `results/metrics.csv` is not yet known — a naive per-row macro-average did
   not reproduce them — and needs to be read from
   `evaluation/run_evaluation.py` / `metrics/dmn_executor.py` before any
   number is quoted.
2. **Whether the string theory actually covers the 34 Requirements models.** The
   anchor describes `contains()`, binned-numeric, and null-check strings; whether
   three predicate forms suffice is confirmed by the IR-2 census, not assumed.
   **The census tool exists** ([PR #10](https://github.com/rrahimi-uci/compliance-to-code/pull/10),
   `utils/corpus_census.py`) but has not yet been run against the anchor's own
   models to check this directly — running it against our own extracted
   graphs answers a related but different question (what our corpora need,
   not what the anchor's 34 Requirements models need).
3. **Whether the expressiveness census leaves enough content to evaluate**
   (proposal §14.6). If not, the paper is narrower than any version so far.
   The tool that computes this (`expressiveness_signal`) is built and tested;
   it has not been run against real data for the same reason as item 2.
4. **Staffing.** 126 pd of scheduled engineering in 157 working days, with no
   research allowance, is not a one-person plan. Either add an engineer or cut G4.
5. **The anchor is one corpus.** Proposal §16 now states the bound and declares
   the abandonment condition; neither makes the bound go away.

### 15.4 Bottom line

The engineering is now sequenced so it can actually run, the arithmetic is
generated rather than typed, and the two claims that were conflated (replay vs.
replication; agreement vs. correctness) are separated. What remains is that
**three cheap, model-call-free measurements — the release audit, the feature
census, and the expressiveness census — can each change the shape of the paper,
and all three land inside the first two weeks.** That is the right place for the
risk to be, and it is where this plan now puts it.

The status line from the first review still holds and should survive into the
paper's limitations section:

> This repository contains a promising, well-tested extraction contract and a
> proposal for an executable measurement instrument. It does not yet contain or
> validate that instrument.
