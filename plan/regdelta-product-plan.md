# RegDelta product plan: regulatory change impact, grounded in this repository

## 0. What this is

RegDelta is a differential-execution engine layered on top of the eleven-agent
extraction pipeline: given old and new versions of a policy document, it
compiles both to LExec IR, aligns rules, classifies semantic changes, and
propagates impact through the dependency graph — entirely from data and code
this repository already has, with no external benchmark acquisition on the
critical path.

## 1. Goal

Ship a "compare regulation versions" capability in Policy Logic Forge: given
an old and a revised version of a compliance document in a domain this
pipeline already extracts, compile both, detect which rules and cases behave
differently, generate concrete examples, quantify how many cases are
affected, and surface all of it in the existing review UI — proven first
against a domain we have already fully extracted, not an external benchmark.

This plan has two distinct endpoints, and they should not be conflated:
Phases 1-6 produce an **engine-validated capability** — the compiler,
differential engine, and alignment logic proven correct against controlled,
partly hand-authored mortgage data, rendered in the UI. Phase 7 is what turns
that into an actual **product**: a real second full document, run through the
real pipeline, reached through a real entry point, with defined behavior
across every rule (not just the clean subset used to validate the engine).
Section 8 states the acceptance bar for each separately.

## 2. What already exists today

This is a direct inventory of the JSON actually on disk under
`pipeline-output/`, re-read for this revision rather than taken from
`docs/full_e2e_validation_2026-08-27.md`'s prose — that doc's NDA row is a
stale mid-run snapshot ("Agent 03 ... in progress") that predates agent_06
completing, and its own text elsewhere cites a pre-dedup, agent_05-stage
count (2,741) rather than agent_06's final optimized count (2,631) used
below.

| Domain | Agent 06 (optimized rules) | Agent 10 (DAG) | Agent 11 (DMN/BPMN) | Prior review-UI smoke status (historical; that UI has since been removed) |
| --- | --- | --- | --- | --- |
| `mortgage` | 631 rules, 481 dependencies | 235 DAGs, 631/631 covered, 1 cycle group | generated (`compliance_decisions.dmn`, `compliance_workflows.bpmn`); 590/631 rules still `requires_review`, 41 clean | previously smoke-tested |
| `privacy_policy` | 802 rules | 757 DAGs, **802/802 covered, complete** | **not yet run** | previously validated against a retained privacy-policy run |
| `mobile_app_privacy` | 1,904 rules | not yet run | not yet run | not yet exercised |
| `nda_confidentiality` | 2,631 rules | not yet run | not yet run | not yet exercised |
| `commercial_contracts` | not yet run in this checkout | — | — | — |
| `deonticbench` | fully vendored (6,483 rows, reference Prolog, gold labels); pipeline extraction over it is a separate track | — | — | no old/new version pairs, so not directly usable for change-impact regardless of pipeline progress |

Two facts drive everything below:

1. **`mortgage` is the only domain with the full agent_01→agent_11 chain
   already materialized.** It is the only domain ready today for the diff
   engine to consume without spending any pipeline runtime first.
2. **`agent_11` depends only on agent_06's optimized graph and agent_10's
   DAG** (`agents/agent_11_executable_model_generator.py` reads
   `get_optimized_dir()` and `get_dag_dir()` only — no agent_07/08/09
   output). `privacy_policy` already has both, at full 802/802 DAG coverage,
   so it is one command away from matching mortgage's depth, using the
   existing exporter CLI documented in `docs/executable-models.md`:

   ```bash
   PYTHONPATH=. .venv/bin/python cli/generate_executable_models.py \
     --graph pipeline-output/e2e-privacy-20260826/agent_06-07-08-09-optimized/optimized_compliance_knowledge_graph.json \
     --dags pipeline-output/e2e-privacy-20260826/agent_10-dag-generation/dependency_dags.json \
     --output-dir pipeline-output/e2e-privacy-20260826/agent_10-dag-generation/executable-models
   ```

   That makes `privacy_policy` the natural second domain (Phase 5). It is
   also independently well-suited to it: 65 of its 802 rules are already
   `requires_review: false`, comparable to mortgage's 41, including 5 with
   numeric predicates — so the same Tier 1 approach applies without
   modification.

## 3. The anchor example: `R-120-004` / `R-120-003`

Rather than inventing a fixture from scratch, the plan anchors on a rule
cluster that is already sitting in `pipeline-output/e2e-mortgage-20260827/`,
extracted from the real Fannie Mae Selling Guide text already in
`compliance-files/mortgage/Fannie-Mae.pdf`.

**`R-120-004`** ("Primary Mortgage Insurance for High-LTV Conventional First
Mortgages"), from `agent_06-07-08-09-optimized/optimized_compliance_knowledge_graph.json`:

- source citation: *B7-1-01, Provision of Mortgage Insurance (04/02/2025)*
- `requires_review: false` — already clean and executable-eligible today
- condition predicates: `conventional_first_mortgage == true`,
  **`ltv_ratio_percent > 80`**, `another_charter_compliant_credit_enhancement_provided == false`,
  `fannie_mae_purchase_or_securitization == true` (all four `all`-combined)
- outcome: `primary_mortgage_insurance_policy_required = true`
- one declared exception: `another_charter_compliant_credit_enhancement_provided == true`

`agent_10`'s dependency DAG already contains `dag_0203`, a real, already-scored
edge from `R-120-004` to **`R-120-003`** ("the lender must ensure required
mortgage insurance ... is in place and must obtain evidence"): dependency
type `conditional`, strength `5/5`, confidence `90.2`, detection method
`explicit`, with agent_10's own worked examples ("A conventional first
mortgage has an 85% LTV ... the system flags primary mortgage insurance as
required and blocks delivery until the policy and evidence are available.").

This single, already-real cluster gives the plan a clean numeric threshold
(a "numeric cap change" edit family), a real citation, a real known
downstream dependent, and pre-existing worked examples — everything Section
6.5's `Direct`/`Potential`/`Recompute` propagation needs to be demonstrated
without inventing anything beyond the edit itself.

One property of this cluster is deliberate, not incidental: `R-120-003`
itself is `requires_review: true`. It is not an exception — of the 41
mortgage rules currently `requires_review: false`, 27 dependency edges
originate from one of them, landing on 26 unique downstream targets, and 24
of those 26 are themselves `requires_review: true` (only `B80-R05` and
`B26-LENDER-ALTERNATIVE-DELIVERY-003` are already clean). Any realistic
Tier 1 propagation example crosses the review boundary; Section 4.1 treats
that as something to test, not something to avoid.

## 4. Validation data plan

### 4.1 Tier 1 — synthetic graph-level fixture (buildable immediately)

No new pipeline run is required for Tier 1; it operates directly on
artifacts already on disk.

1. Define the fixture universe as two tiers, not one: the **41** mortgage
   rules currently marked `requires_review: false` (the only ones eligible
   to be hand-edited, so "the diff engine has a bug" is never conflated with
   "this rule is still pending review"), **plus** the **24** additional rules
   that are direct DAG dependents of one of those 41 and are themselves
   still `requires_review: true` (found by walking `agent_10`'s DAG edges
   outward from the 41 — `R-120-003` via `dag_0203` is one of them). The
   second group is carried into the fixture at its real, unedited review
   status; it exists so the fixture can test that propagation correctly
   reaches a review-required rule and reports it honestly, which is the
   overwhelmingly common case here: of the 41 clean rules' 27 outgoing
   dependency edges, 24 of 26 unique targets are still `requires_review:
   true`. A fixture that only ever propagates into already-clean rules would
   not be representative.
2. Of the 41, 7 carry a numeric `condition_predicate`
   (`R-120-004`, `batch5_mortgage_pool_fixed_rate_submission_minimum`,
   `B32-A2-2-06-001`, `B58-MORTGAGE_LOAN-MANUFACTURED_HOME-CASH_OUT_ELIGIBILITY`,
   `B16-R004-ADU-RENTAL-INCOME-CAP`, `B96-LOAN_APPLICATION-UNEMPLOYMENT_BENEFITS-QUALIFICATION`,
   `B125-BORROWER-GIFT-COHABITATION-003`). Fork
   `optimized_compliance_knowledge_graph.json` into `old_graph.json` and
   `new_graph.json` (both containing all 65 fixture-universe rules), and
   hand-edit 3-5 of the 7 numeric fields in the "new" copy (for example,
   `R-120-004`'s LTV trigger `80 -> 78`). Each edit gets a one-line
   rationale, written as if it were a real Selling Guide announcement, and
   an updated `effective_date` so provenance stays internally consistent.
   Only the 41 clean rules are ever edited; the 24 review-required
   dependents are copied unchanged into both graphs.
3. Hand-write 10-15 scenario cases exercising the edited rules plus their
   known dependents from `agent_10`'s DAGs (at minimum `R-120-003` via
   `dag_0203`), and hand-label two different things per case: the expected
   old-vs-new **outcome** for each of the 41 editable rules the case
   exercises, and the expected **status** — `unresolved-review`, not an
   outcome — for each of the 24 review-required downstream rules the case's
   propagation should reach. (Phase 3's acceptance criteria fixes this
   four-way status vocabulary — `changed` / `unchanged` /
   `unresolved-review` / `refused-unsupported-construct` — and Phase 7.2
   later extends it to the full rule population; it isn't redefined twice.)
   This hand-labeled set *is* the gold data — authored by us, over rules
   already extracted from the real source text, with no external oracle
   required.
4. This fixture is the acceptance-test data for Phase 1 (compiler) and
   Phase 2 (differential engine) below.

### 4.2 Tier 2 — real text-to-pipeline validation (still in-house)

Tier 1 proves the engine given a hand-edited *graph*. Tier 2 proves the
*whole* text-to-impact path, including extraction.

1. Hand-author a short "errata" excerpt — a few paragraphs, not a new
   1,191-page PDF — rewriting the real `source_text` of the Tier 1 edited
   rules with those edits applied, in the same style as the organized
   chunks already under
   `pipeline-output/e2e-mortgage-20260827/agent_01-organized-documents/`.
2. Run it through agents 01-06 as its own small batch:

   ```bash
   PYTHONPATH=. .venv/bin/python cli/extract.py \
     --dir compliance-files/mortgage-tier2-errata \
     --domain mortgage \
     --batch-name mortgage-tier2-revised
   ```

3. Confirm the real extraction recovers the same field-level changes Tier 1
   hand-edited. Only once this passes does "old text in, impact report out"
   become a supportable claim for the mortgage domain — Tier 1 alone only
   proves the diff/propagation engine, not extraction fidelity.

## 5. Scope and non-goals

In scope: old/new compilation within the supported LExec subset, rule
alignment, semantic change classification, scenario replay, witness
generation, downstream propagation, and quantitative exposure with full
provenance. Out of scope: general business-process simulation, real
staffing/cycle-time/cost forecasts, expected financial or reputational loss,
any claim of legal correctness beyond what a rule's own source evidence
supports, and external benchmark integration.

## 6. System design

The worked example below uses data this repository already has.

### 6.1 End-to-end flow

```text
old and new mortgage document versions
          |
          v
old and new grounded rule graphs (agent_06)
          |
          v
old and new fail-closed LExec programs
          |
          v
rule alignment and semantic change classification
          |
          v
differential execution over hand-authored (Tier 1) or extracted (Tier 2) cases
          |
          v
affected cases, witnesses, and changed effects
          |
          v
downstream dependency propagation (agent_10's DAG)
          |
          v
source-grounded impact report and review UI
```

### 6.2 Worked example (Tier 1)

```text
Case:                      MORT-HIGH-LTV-0001 (hand-authored Tier 1 scenario)
Changed source:            Fannie Mae Selling Guide B7-1-01, Provision of
                           Mortgage Insurance (04/02/2025)
Directly changed rule:     R-120-004
Semantic edit:             LTV trigger for required PMI: 80% -> 78%
                           (hand-authored synthetic edit for Tier 1; Tier 2
                           replaces this with real extracted text)
Scenario:                  conventional first mortgage, LTV 79%, no other
                           credit enhancement, purchased by Fannie Mae
Old output:                primary_mortgage_insurance_policy_required = false
New output:                primary_mortgage_insurance_policy_required = true
Known downstream:          R-120-003 (insurance-in-place obligation; edge
                           already present in agent_10's dag_0203, strength
                           5/5, confidence 90.2, detection_method=explicit)
Downstream status:         unresolved-review (R-120-003 is requires_review:
                           true in the fixture; reported as present and
                           unresolved, not silently changed/unchanged/dropped)
Evidence status:           source and hand-authored gold label aligned
Execution status:          observed by replay (Tier 1); to be confirmed by
                           real extraction (Tier 2)
```

### 6.3 Change taxonomy

The change taxonomy: rule addition/removal, condition strengthening/weakening,
threshold or constant change, output/effect change, modality change,
exception addition/removal, scope change, priority/hit-policy change,
dependency change, semantically unchanged edits, and unresolved alignment.

### 6.4 Rule alignment

For the mortgage domain specifically, Tier 1's alignment is close to trivial
(the "new" graph is a copy of the "old" graph with a handful of fields
edited, so rule IDs match exactly); Tier 2 is where the alignment contract is
actually exercised, because the real extraction over the errata excerpt will
not reuse the original rule IDs and must be aligned by source section and
predicate structure instead.

### 6.5 Impact propagation

`Direct`/`Potential`/`Recompute` over the dependency DAG, full replay as the
correctness oracle. For the anchor example: `Direct` = `{R-120-004}`;
`Potential` = `{R-120-004, R-120-003}` (via `dag_0203`).

`Recompute` is *not* automatically equal to `Potential` here, and this is a
genuine open design question for Phase 2, not a solved fact: `dag_0203`'s
edge is a narrative dependency agent_10's extraction judged from the source
text (`detection_method: explicit`, confidence 90.2), but `R-120-003`'s own
condition predicate references a *different* variable
(`fannie_mae_required_insurance_or_loan_guaranty`) than the one `R-120-004`'s
edit changes (`primary_mortgage_insurance_policy_required`) — the two rules
were extracted independently and never assigned a shared symbol. An
`Recompute` fingerprint that only compares variable-level inputs would miss
this dependency entirely. Phase 2 must resolve this one of two ways: either
canonicalize the two variables as the same fact during alignment (Section
6.4), so a fingerprint comparison is meaningful, or treat every DAG neighbor
in `Potential` as unconditionally requiring re-execution regardless of
fingerprint match whenever no such canonical link exists — accepting fewer
"exact incremental/full-replay agreement" savings claims in exchange for
never silently missing a real dependency. Phase 3's fixture (Section 4.1)
is exactly where this decision gets tested, using `R-120-004`/`R-120-003` as
the concrete case.

## 7. Rollout phases

### Phases 1-2: executable pipeline boundary; gold differential engine — delivered

LExec is integrated into the live pipeline (`agent_11` compiles and proves
each rule via `utils/lexec_compile.py`), and the alignment/diff/propagation/
witness engine is implemented (`utils/rule_alignment.py`,
`utils/semantic_diff.py`, `utils/impact_propagation.py`, orchestrated by
`utils/regdelta_engine.py`).

### Phase 3: mortgage Tier 1 fixture and acceptance tests

A small, hand-labeled, in-house fixture (rather than an external benchmark
adapter) proving the engine against real pipeline output — see Section 4.1
above.

Execution steps:

1. Add `fixtures/regdelta/mortgage_tier1/` containing `old_graph.json` and
   `new_graph.json` (each the full 65-rule fixture universe from Section
   4.1 step 1: the 41 editable rules plus their 24 review-required direct
   DAG dependents, the latter byte-identical across both graphs), and
   `edit_manifest.json` recording each edit's rule ID, field, old/new value,
   and rationale.
2. Add `fixtures/regdelta/mortgage_tier1/scenarios.json` with the 10-15
   hand-labeled cases from Section 4.1 step 3, each carrying the expected
   old/new outcome for the editable rules it exercises and the expected
   `unresolved-review` status for any of the 24 review-required rules its
   propagation should reach.
3. Add `scripts/validate_mortgage_tier1_fixture.py` checking that every
   edited rule ID is one of the 41 editable rules, every one of the 24
   review-required dependent rules is byte-identical across both graphs (so
   the fixture can't silently drift, and can't silently un-flag a rule that
   is supposed to stay `requires_review: true`), and every scenario's
   referenced rule IDs exist in the fixture universe.
4. Add `tests/test_mortgage_tier1_fixture.py` running Phase 1/2's compiler
   and differential engine over this fixture and asserting 100% agreement
   with the hand-labeled outcomes, downstream sets, and `unresolved-review`
   statuses.
5. Record results — including the refusal count for the 566 mortgage rules
   outside the 65-rule fixture universe entirely (590 total
   `requires_review: true` rules, less the 24 carried into the fixture) —
   under `results/aggregates/regdelta/mortgage_tier1.json`.

Acceptance criteria:

- every hand-labeled Tier 1 case is classified changed/unchanged correctly;
- every hand-labeled downstream rule is found by `Potential`/`Recompute`;
  a review-required one is reported as `unresolved-review` (present, not
  silently dropped, and not resolved to changed/unchanged), and nothing
  outside the hand-labeled set is reported;
- incremental recomputation exactly matches full replay on this fixture;
- the 566 mortgage rules outside the 65-rule fixture universe are reported
  as explicit refusals, never silently treated as unchanged or as
  executable `false`.

### Phase 4: mortgage Tier 2 real text-to-pipeline validation

Validates Tier 1's hand-authored edits against a real text-to-pipeline
extraction — see Section 4.2 above.

Execution steps:

1. Author `compliance-files/mortgage-tier2-errata/` with the short revised
   excerpt described in Section 4.2 step 1.
2. Run it through `cli/extract.py` (agents 01-06) as its own batch, per the
   command in Section 4.2 step 2.
3. Add `scripts/compare_tier2_extraction.py` that aligns the newly extracted
   rules against Tier 1's `new_graph.json` for the same rule cluster and
   reports field-by-field agreement (not exact-ID match, since the real
   extraction will assign different rule IDs).
4. Add `tests/test_mortgage_tier2_extraction.py` asserting the real
   extraction recovers the same edited field values Tier 1 hand-authored,
   within an agreed tolerance for free-text description drift.
5. Record the gap, if any, between Tier 1 (engine-only) and Tier 2
   (extraction-included) accuracy under
   `results/aggregates/regdelta/mortgage_tier2.json`, so extraction error is
   never silently absorbed into the engine's reported accuracy.

Acceptance criteria:

- every Tier 1 edit is independently recovered by the real extraction;
- source-edit localization points at the errata excerpt's actual changed
  sentences;
- any extraction miss is retained and attributed to extraction, not silently
  dropped from the result set.

### Phase 5: expand to the remaining domains

Domain breadth: the same Tier 1/Tier 2 approach applied to each of this
repository's other four domains, ordered by actual pipeline distance to
mortgage's depth (Section 2), not by any external priority:

1. **`privacy_policy`** — already has 802/802 DAG coverage; only needs an
   `agent_11` run (no LLM calls, purely structural) to match mortgage's
   depth. Build a Tier 1 fixture for it the same way as Section 4.1, then
   its own Tier 2 pass.
2. **`mobile_app_privacy`** — needs agent_09 (grounding) confirmed, then
   agent_10 and agent_11.
3. **`nda_confidentiality`** — agent_06 already produced 2,631 rules; needs
   agent_07 through agent_11.
4. **`commercial_contracts`** — least progressed; needs the full pipeline
   run in this checkout before any RegDelta fixture work can start.

Acceptance criteria per domain: agent_11 output exists and validates; a
Tier 1 fixture exists with at least 10 hand-labeled cases; Phase 1/2's engine
achieves the same 100%-agreement bar Phase 3 set for mortgage.

### Phase 6: review UI — "Compare versions"

No review UI exists in this repository (the earlier review workbench under
`ui/` was removed). This phase needs a UI built from scratch — source
redline, alignment status, change categories, affected-case tables, old/new
comparison, witness exploration, impacted-rule DAGs, proved/observed/
uncertain/refused states, downloadable reports — built first against
mortgage's Tier 1 fixture so it has real data to render from day one, then
wired to Tier 2 and to each domain as Phase 5 completes them. Scope, stack,
and endpoints are undecided; this is a future planning task, not a
ready-to-execute step.

### Phase 7: real end-to-end product workflow

Phases 1-6 prove the engine is correct against controlled data. Phase 7 is
what actually makes RegDelta a product: two real, full document versions,
through the real pipeline, reached through a real entry point, with defined
behavior for every rule — not just the 65-rule fixture universe Tier 1 used
to validate the engine in isolation.

**7.1 A real second full document.** This is the one deliberate exception to
this plan's "no new external input" posture (Sections 0 and 9): you cannot
validate a two-full-real-document product workflow with only one document.
Fannie Mae publishes dated, full Selling Guide PDFs publicly and for free on
`singlefamily.fanniemae.com` — for example the effective dates already
embedded in our own extracted rules' `source_reference` fields (`2025-04-02`,
`2025-08-06`) confirm this is the same publication `compliance-files/mortgage/Fannie-Mae.pdf`
was drawn from, and later dated editions of the same publication are
published the same way. Acquire the next dated edition after the one already
in `compliance-files/mortgage/`, run it through the full agent_01-11 pipeline
as its own batch (same command shape as the existing `e2e-mortgage-20260827`
run), and record actual runtime/cost — the existing run processed 506 chunks
into 640 extracted rules across many LLM calls, so a second full run is a
comparable real spend, not a free rerun.

**7.2 Defined behavior for the whole rule population, not just the fixture
subset.** Phase 3's fixture already had to introduce the `unresolved-review`
status (Section 4.1), because 24 of its own 65 rules are `requires_review:
true`. Phase 7 extends that same four-way vocabulary (`changed` /
`unchanged` / `unresolved-review` / `refused-unsupported-construct`) from the
fixture's 65 rules to all 631 — of which 590 are currently `requires_review:
true` — and adds a coverage-risk line to the impact report: of all aligned
rule pairs, how many were actually diffable versus held for review versus
refused for unsupported constructs, following the same "never absorb into
the headline accuracy number" principle Section 8 already applies to the
Tier 1/Tier 2 gap. This extends Phase 2's alignment/diff engine to the full
rule population; it does not replace it, and it does not introduce a new
status vocabulary — Phase 3 already did.

**7.3 A real product entry point.** A "Compare versions" action (UI or CLI)
that: accepts two document(-set) references (an existing batch, or a freshly
uploaded file); triggers `cli/extract.py` for whichever side hasn't reached
`agent_11` yet; runs the differential engine once both sides have; and
renders the resulting impact report. Pipeline runs are not instant, so this
needs an async job model exposing per-agent run status (queued / running
agent N of 11 / complete / failed). Reject a cross-domain comparison
outright, and block (with a clear message, not a partial diff) comparing a
side that hasn't reached `agent_10`/`agent_11` yet.

**7.4 Measured cost and latency, not assumed.** Record actual wall-clock time
and LLM spend for both the 7.1 full second-document run and a full round
trip through the 7.3 entry point, using the same reporting conventions as
`docs/full_e2e_validation_2026-08-27.md`. If the full round trip is too slow
or expensive to be a synchronous, interactive UI action, say so plainly and
design the UX around it (an async "notify when ready" pattern, with the
measured cost shown before a user commits to running it) rather than
shipping a misleading "instant compare" experience.

Acceptance criteria:

- two full, independently-published real mortgage document versions are
  compiled end to end through the actual product entry point, not a
  hand-authored excerpt;
- the impact report explicitly distinguishes changed / unchanged /
  unresolved-review / refused-unsupported-construct for every aligned rule
  pair — no rule silently disappears from the report;
- coverage-risk numbers are reported alongside any accuracy claim;
- actual runtime and cost for the full round trip are measured, published,
  and reflected honestly in the product UX; and
- only after this phase does "RegDelta is a product for the mortgage domain"
  become a supportable claim — Phase 6 alone supports only "the engine is
  validated and viewable," not "a customer can use this."

## 8. Success criteria

**Engine-validated (Phases 1-6):**

- 100% of mortgage Tier 1's hand-labeled cases correctly classified by the
  differential engine (Phase 3).
- The Tier 2 real-extraction gap, if any, is measured and reported, never
  absorbed into the engine's own accuracy number (Phase 4).
- Incremental recomputation exactly matches full replay on every retained
  fixture (Phases 3-5).
- A reviewer can open the existing workbench, pick the mortgage domain, and
  see the Tier 1 (then Tier 2) old-vs-new diff end to end (Phase 6).
- At least one additional domain (`privacy_policy`, per Phase 5's ordering)
  reaches the same bar before this plan considers itself validated beyond a
  single domain's idiosyncrasies.

**Product-ready (Phase 7):**

- A user can point the running product at two real, full mortgage document
  versions and get back an impact report, through the actual UI entry point,
  without any hand-authored fixture in the loop.
- Every one of the 631 mortgage rules resolves to an explicit status
  (changed, unchanged, unresolved-review, or refused) — none are silently
  dropped because they were outside Tier 1's 65-rule fixture universe.
- Measured runtime and cost for a full round trip are published and the
  product UX matches what was measured.

Do not describe RegDelta as "a product" based on Phase 6 alone — that phase
proves the engine and gives reviewers something to look at, but Phase 7 is
what a customer could actually use.

## 9. What this plan intentionally defers

No external benchmark acquisition, license negotiation, or academic
baseline/ablation protocol is required by this plan.

Phase 7's single new external input (Section 7.1's second Selling Guide
edition) is the one deliberate exception to this posture, and is scoped as
narrowly as possible: one more edition of a publication this repository
already has one edition of, acquired only when Phase 7 actually starts.
