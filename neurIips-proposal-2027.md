# NeurIPS 2027 Research Proposal

**Working title:** *No Gold Program: Extensional and Relational Evaluation of
Document-to-Logic Extraction, and the Verifiable Reward It Buys*

**Umbrella project name:** **LEXEC** — compile normative documents into
executable decision logic, and use the compiler as the measuring instrument.

| | |
| --- | --- |
| Target venue | NeurIPS 2027 main track (primary); Datasets & Benchmarks track (secondary/spin-off) |
| Target deadline | Abstract/full paper historically mid-to-late May — **verify against the 2027 CFP** |
| Time available | ~9 months from 2026-08-24 |
| Substrate | This repository (`compliance-to-code`): 10-stage extraction pipeline, v2 rule contract, four-invariant readiness gate, claim-level grounding verifier, 100%-coverage dependency DAGs, 4 benchmark-backed domains |
| Status of this document | Proposal for discussion. Every number marked *(measured)* comes from a real run; every number marked *(target)* is a pre-registered success criterion, not a result. |

---

## 0. The one-sentence claim

> Compiling a normative document into an executable decision artifact converts
> an unmeasurable NLP task into a decidable one — which yields (i) a benchmark
> that needs no gold formalization, (ii) a verifiable reward that trains
> models, and (iii) an inference regime that is self-consistent by
> construction and ~10²–10³× cheaper per query than long-context QA.

Everything below is in service of making that sentence true, measured, and
defensible against a hostile reviewer.

---

## 1. Read this first: why the obvious version of this project gets rejected

The obvious paper is *"we built an LLM pipeline that turns compliance documents
into a knowledge graph and then into DMN/BPMN."* At NeurIPS that is desk-reject
territory, and it is worth being blunt about why, because every design choice
downstream is a response to one of these:

1. **"This is engineering, not research."** A pipeline is an artifact, not a
   claim. There must be a falsifiable hypothesis and an experiment that could
   have come out the other way.
2. **"No ground truth, so no evaluation."** There is no gold DMN for any real
   contract, and there never will be — two competent lawyers formalize the same
   clause into non-isomorphic but equally correct logic. Any metric based on
   matching a reference artifact is dead on arrival.
3. **"Why not just prompt a frontier model per query?"** With 1M-token context,
   "extract a KG first" needs an argument, not an assumption. If direct
   long-context QA matches the pipeline's accuracy, the pipeline needs a
   different justification (and it has one — see §11.3 — but it must be
   *measured*, not asserted).
4. **"DMN/BPMN is a niche industrial standard."** The choice of target language
   must be ablated, not assumed. It is entirely possible that Python, SMT-LIB,
   or ASP is an easier target for an LLM, and that would be an interesting
   result rather than a problem.
5. **"Where is the learning?"** NeurIPS rewards a training signal, a
   generalization claim, or a theoretical result. A prompt chain is none of
   those.
6. **"Legal-NLP already does this."** PolicyLint/PoliCheck, Catala, LegalRuleML,
   Logic-LM/SatLM, and text-to-SQL all overlap. Positioning must be explicit
   and generous (see §17).

The proposal below answers all six. Objection 2 is the one that becomes the
paper's intellectual core, so it is treated first.

---

## 2. The core intellectual problem: there is no gold program

For document-to-logic extraction, the standard supervised setup is unavailable:

- **No gold artifact.** Nobody has hand-written DMN for CUAD's 510 contracts.
- **No canonical form.** Even given a gold artifact, correctness is invariant
  under renaming, reordering, DNF/CNF choice, table splitting, predicate
  factoring, and defeater placement. Form-matching metrics measure style.
- **Surface metrics measure the wrong thing.** ROUGE, span-F1, and LLM-judge
  scores are computed over *text*. Two extractions that quote the same clause
  can encode opposite thresholds; two that quote different clauses can encode
  the same decision function.

There are exactly two escapes, and the paper's contribution is to take both
seriously and combine them:

**(A) Extensional evaluation — judge behavior, not form.**
Compile the extraction to an artifact with a semantics, then evaluate the
*function* it denotes: given a fact binding, what does it decide? Given a
hypothesis, does it entail it? This is the move that made text-to-SQL tractable
(execution accuracy on Spider) and it is *stated as inherited* rather than
claimed as novel. The novelty is the setting: long normative documents, no gold
programs at all, defeasible/open-world semantics, and thousands of gold labels
already sitting in existing legal-NLP corpora that nobody has yet used
extensionally.

**(B) Relational evaluation — judge how behavior changes, not what it is.**
Annotate a *perturbation and its intended semantic effect*, never a target
artifact. For a meaning-preserving edit π, require the compiled function to be
logically equivalent before and after — and check that equivalence *exactly*
with an SMT solver, not with string similarity. For a meaning-changing edit with
a known direction (tighten scope, add a defeater, flip a modality), require a
specific refinement relation to hold.

Relational gold is dramatically cheaper to produce than absolute gold (annotate
an edit, not a formalization) and is *immune to the canonical-form problem* —
which is precisely why it is the right instrument for this task. This is the
single most transferable idea in the proposal: it applies to any text →
formal-artifact task (clinical guidelines, tax code, benefits eligibility, API
contracts, spec-to-test).

---

## 3. Contributions

**C1 — LEXEC-Verify: a compiler-and-solver as a measuring instrument.**
A deterministic, LLM-free compiler from the repository's v2 rule contract to
(a) DMN 1.3 decision tables over a bounded FEEL subset, (b) SMT-LIB, and
(c) a reference interpreter. Plus a solver layer that decides row disjointness,
rule subsumption, pairwise co-firing conflict, coverage gaps, vacuity, and
logical equivalence. Everything the extraction claims becomes a decidable
question. *This is the instrument, and it is also the reward machine in C3.*

**C2 — LEXEC-Bench: a decision-level benchmark with no new gold artifacts.**
Three query modes, all with gold derived from existing expert annotations:

| Mode | Question form | Gold source | Approx. scale |
| --- | --- | --- | --- |
| **Entailment** | Does the document's rule set entail hypothesis *h*? | ContractNLI: 607 NDAs × 17 expert-labeled hypotheses | ~10.3k labeled queries |
| **Presence/value** | Does clause category *c* exist, and with what value? | CUAD: 510 contracts × 41 categories, 13k+ spans | ~20.9k QA pairs |
| **Practice decision** | Is data practice *p* permitted/disclosed for actor *a*, purpose *u*? | OPP-115 (~23k practices) + MAPP (bilingual EN/DE, GDPR legal-basis axis) | ~23k practices, 270 policies |

Plus **LEXEC-Perturb** (the one genuinely new dataset): ~1.5–2k expert-verified
perturbation pairs across the four corpora, each labeled with a *metamorphic
relation* rather than a target artifact.

**C3 — CEGIR: counterexample-guided iterative repair, and RLVR beyond math and
code.** Two coupled methods that only exist because C1 exists:
- *CEGIR* (inference time): compile → solve → the solver returns a concrete
  counterexample (a fact binding where two rules co-fire contradictorily, or
  where the artifact disagrees with a gold hypothesis) → feed the counterexample
  back as a repair instruction → iterate to a fixed point. CEGIS, applied to
  information extraction.
- *RLVR* (training time): the verifier's composite pass/fail becomes a
  programmatic reward for GRPO-style RL on an open-weight model. The headline
  claim is deliberately broad: **verifiable rewards are not limited to math,
  code, and theorem proving; a compiler can manufacture a verifier for any
  domain whose output has a semantics.**

**C4 — Two empirical findings we expect to be the most-cited part of the paper.**
- **The surface–semantics dissociation.** Span-F1 / LLM-judge scores are weakly
  predictive of decision agreement. Pre-registered prediction: Spearman ρ < 0.4
  between per-document span-F1 and per-document decision agreement *(target)*.
- **LLM self-verification is badly miscalibrated on this task.** In the one
  certified run we have, the claim-level grounding verifier flagged **345/352
  rules (98%)** as requiring review while **94.0% of the same rules'
  source-attested test vectors replayed correctly** through generated DMN
  *(measured, n=1 — see §13)*. If that dissociation survives replication across
  four domains and several verifier models, it is a substantive result about
  LLM self-verification, independent of compliance.

---

## 4. Formal setup

**Objects.** A document *d* (a normative text: contract, policy, regulation).
An extraction function *f* (the LLM system) producing a *rule set*
*R* = *f*(*d*). A compiler *γ* producing an artifact *A* = *γ*(*R*) with a
denotational semantics ⟦*A*⟧.

**Semantics.** Each rule *r* ∈ *R* is
( *V*, *C*, *X*, *O*, *σ*, *π* ) where *V* is a typed variable set
(number / boolean / enum / date / date_time / duration / list; role ∈
{input, derived, output}), *C* is a boolean combination of atomic predicates
over *V* (operators `== != < <= > >= in not_in`), *X* is a set of *defeaters*
(the contract's `exceptions`), *O* is a set of output assignments (`=` only),
*σ* an applicability scope, and *π* a hit policy ∈ {UNIQUE, FIRST, PRIORITY,
COLLECT, ANY}.

**Defeater semantics (the P4 decision, resolved).** The repository's contract
deliberately keeps `exceptions` separate from `condition_logic` and never
specifies how they combine — and in the one run we have, **155/352 rules carry
exceptions and 125 of those introduce variables absent from the condition**
*(measured)*, so the choice materially changes the compiled input signature.
We fix it, and make the choice a stated, testable part of the paper:

> **effective condition** ⟦*r*⟧ ≡ *C* ∧ ¬( ⋁_{x ∈ X} *x* )

i.e. exceptions are *defeaters*: any one holding means the rule does not apply.
This is the weakest-commitment reading, it matches how legal exceptions read,
and — crucially — it is *empirically checkable* against the vector suite and
against LEXEC-Perturb's defeater-insertion relation. If the data contradicts it,
that is a finding, and the alternative readings (independent single-predicate
exceptions; conjunctive exceptions) are pre-registered as the comparison.

**Worked example** (NDA, abbreviated):

> *"Recipient shall not disclose Confidential Information to any third party
> for a period of three (3) years from the Effective Date, provided that
> disclosure compelled by judicial order shall not constitute a breach."*

```
variables:  disclosure_to_third_party : boolean  (input)
            years_since_effective_date: number   (input, unit=years)
            compelled_by_judicial_order: boolean (input)
            breach_of_confidentiality : boolean  (output)
condition:  all[ disclosure_to_third_party == true,
                 years_since_effective_date <= 3 ]
exceptions: [ compelled_by_judicial_order == true ]     # defeater
outcomes:   breach_of_confidentiality = true
hit policy: UNIQUE
```

Compiles to one DMN row (`true`, `<= 3`, `false` → `true`) after defeater
negation, and to the SMT assertion
`(=> (and dttp (<= yse 3) (not cbjo)) breach)`. The ContractNLI hypothesis
*"Receiving Party may share some Confidential Information with third parties"*
becomes the entailment query
`(check-sat (and rules (exists binding: dttp ∧ ¬breach)))` — decidable, and
gradable against the corpus's expert label.

**Fragment and decidability.** The measured corpus uses 8 operators, one output
operator, and 7 value types. That fragment is linear arithmetic over
integers/rationals plus finite enums plus equality — decidable, and in the
quantifier-free case handled directly by an off-the-shelf SMT solver. We
implement a bounded FEEL renderer/evaluator and **fail loudly** on anything
outside it (notably `duration` and `range`, which the schema permits but the
observed corpus never exercised). "Fail loudly" is a research choice, not
laziness: silent coercion would contaminate the measurement.

---

## 5. Propositions (the paper's theoretical content)

Small, provable, and load-bearing. Not a theory paper — but enough that the
correctness argument is stated rather than gestured at.

**P1 (Compilation soundness).** Under the defeater semantics of §4, the DNF
expansion of *C* ∧ ¬(⋁*X*) into decision-table rows, with the hit policy
assigned by P2's rule, denotes exactly ⟦*r*⟧ on the declared variable domain.
*Sketch:* DNF expansion is semantics-preserving; the only risk is hit-policy
misassignment, which P2 governs.

**P2 (UNIQUE-safety is decidable).** A multi-row table may be declared UNIQUE
iff its rows are pairwise disjoint. In the fragment of §4 this is an
unsatisfiability check per row pair — decidable; NP-complete in the
propositional part; practical at observed table sizes (87.5% of rules expand to
a single row; worst case 7 rows *(measured)*). When disjointness is not
provable, the compiler must **downgrade to FIRST and record the downgrade with
its reason** (42 rules hit this in the measured run) rather than emit a false
UNIQUE.

**P3 (Boundary vectors are a complete certificate for interval tables).** For a
decision table whose rows are conjunctions of interval constraints over
independent numeric inputs and finite enums, a test suite containing each
interval endpoint (and one interior point per cell) is *complete*: it
distinguishes the table from any other table in the same class. Consequence:
the LLM-generated `boundary_condition` test vectors the contract already
requires are not a heuristic smoke test — inside this fragment they are a
verification certificate. This is the proposition that turns an existing
pipeline requirement into a guarantee, and it is the most useful of the four.

**P4 (Consistency by construction).** A compiled artifact's answers to any set
of queries are consistent with a single underlying function by construction. Per-query
LLM answering carries no such guarantee. We therefore report *cross-query
inconsistency rate* as a metric on which the compiled system is 0 by
construction and the long-context baseline is measured — a guaranteed,
non-cherry-picked axis of comparison (§11.3).

---

## 6. What LEXEC-Verify must decide

Each of these is an SMT query, and each is a metric in the paper:

| Check | Query | Why it matters |
| --- | --- | --- |
| Row disjointness | `UNSAT(row_i ∧ row_j)` | UNIQUE-safety (P2) |
| Subsumption | `UNSAT(C_a ∧ ¬C_b)` | semantic dedup, replacing text-similarity dedup |
| Logical equivalence | `UNSAT(⟦A₁⟧ ⊕ ⟦A₂⟧)` | the metamorphic invariance check (§8) |
| Co-firing conflict | `SAT(C_a ∧ C_b ∧ O_a ≠ O_b)` | contradictory obligations; returns a **counterexample binding** for CEGIR |
| Coverage gap | `SAT(¬⋁_i C_i)` under scope | unhandled scenarios; audit-relevant |
| Vacuity | `UNSAT(C_r)` | a rule that can never fire = extraction error |
| Entailment | `UNSAT(⟦A⟧ ∧ ¬h)` | ContractNLI query mode |

Two things to note. First, **semantic dedup by logical equivalence/subsumption
replaces the pipeline's current similarity-based deduplication** — a concrete,
measurable improvement with its own ablation. Second, the conflict check returns
a *witness*, and the witness is what makes CEGIR possible; a boolean verifier
would not be enough.

---

## 7. Benchmark design: where the gold actually comes from

The feasibility of this whole proposal rests on this section. No new artifact
annotation is required for the main results.

**7.1 ContractNLI → entailment mode (the flagship).**
607 NDAs, 17 fixed hypotheses each, three-way expert labels *plus evidence
spans*. Each hypothesis becomes an SMT entailment query against the compiled
artifact; the corpus label is the gold answer; the evidence spans give a *free*
provenance-precision metric (did the artifact's cited sections overlap the
expert's evidence spans?). ~10.3k gold decision-level labels, zero new
annotation. This corpus alone can carry the paper.

**7.2 CUAD → presence/value mode.** 510 contracts, 41 clause categories,
`master_clauses.csv` normalized answers. Queries: "is there a governing-law
clause, and what jurisdiction?", "is there a change-of-control restriction?".
Tests whether the compiled artifact captured the clause *as a decision*, not
just as a span.

**7.3 OPP-115 / MAPP → practice-decision mode.** Data practices as
(actor, data type, purpose, permitted?) tuples — a natural fit for fact-binding
evaluation. MAPP adds the GDPR `legal_basis` axis and a bilingual EN/DE split,
which gives a **cross-lingual generalization** experiment essentially for free
(compile German policies, query in the shared formal language).

**7.4 Scenario mode (the one place we synthesize).** For fact-binding
evaluation we need scenarios. Three sources, in decreasing order of trust:
(i) the rules' own `source_attested` test vectors; (ii) solver-generated
boundary bindings from P3; (iii) human-authored scenarios for a small
gold subset. We will hand-verify a stratified sample (~500 scenarios) with
domain experts to bound the noise in (i) and (ii), and report agreement.

**7.5 Contamination.** CUAD, ContractNLI, OPP-115 are all public and pre-cutoff
for every model we will test. This must be addressed head-on:
- Report performance on **LEXEC-Perturb** separately — perturbed clauses are
  new text and are the contamination-resistant number.
- Include a **held-out fresh corpus** collected after the newest model's
  cutoff (e.g. newly published privacy policies / SEC-filed contracts).
- Run a memorization probe (can the model reproduce the gold labels from
  document ID alone?).

---

## 8. LEXEC-Perturb: relational gold

~1.5–2k clause-level perturbation pairs, each annotated with a metamorphic
relation, not a target artifact. Checked with the SMT layer, so "unchanged"
means *logically equivalent*, not *string-identical*.

**Meaning-preserving (invariance required):**
`⟦γ(f(d))⟧ ≡ ⟦γ(f(π(d)))⟧`
- lexical paraphrase; active↔passive; legalese↔plain language
- clause reordering; splitting one clause into two; merging two into one
- defined-term substitution ("Recipient" ↔ "Receiving Party")
- unit-preserving numeric restatement ("three years" ↔ "36 months")
- redundant-defeater insertion (an exception that is already implied)

**Meaning-changing (a specific relation required):**
- **scope tightening** → applicability set must strictly shrink:
  `SAT(σ_old ∧ ¬σ_new)` and `UNSAT(σ_new ∧ ¬σ_old)`
- **threshold shift** ("3 years" → "5 years") → the decision boundary must move
  in the named direction
- **modality flip** ("shall" → "may") → obligation must become permission
  (output variable changes role, not just value)
- **defeater addition** → the firing set must strictly shrink
- **negation insertion** → outcome must flip on the affected region
- **cross-reference redirect** ("subject to Section 5" → "Section 7") → the
  dependency edge must move

**Why this is the strongest part of the design.** A model that always outputs
the same thing scores perfectly on invariance and zero on sensitivity; a model
that is noisy scores the reverse. Only a model that actually tracks meaning
scores well on both. We therefore report the **Semantic Discrimination Index**
(Youden's J): `SDI = SR + SE − 1`, where SR is invariance rate on
meaning-preserving edits and SE is correct-change rate on meaning-changing
edits. One number, gameable in neither direction.

**Annotation cost.** Annotators write an edit and pick a relation from a closed
list. No logic, no formalization. Estimated ~2–4 minutes/item → ~100–130 hours
→ tractable with 2–3 law-school or privacy-compliance annotators, double-annotated
on a 20% overlap for IAA.

**Licensing constraint (already known in this repo).** OPP-115 and MAPP carry no
redistribution grant. LEXEC-Perturb ships as **edit scripts + offsets against
the upstream corpora**, never as derived text — the same posture
`benchmarks/datasets.json` already takes for the source documents.

---

## 9. Method

### 9.1 CEGIR — counterexample-guided iterative repair (inference time)

```
R₀ ← f(d)                                # LLM extraction
loop k = 0,1,2,…
    A ← γ(R_k)                           # deterministic compile
    if compile fails → witness = the refusal reason
    else W ← Solve(A)                    # conflicts, vacuity, gaps, vector replay,
                                         #   and (train split only) gold-query disagreements
    if W = ∅ → return A                  # fixed point
    R_{k+1} ← f_repair(R_k, W, d)         # repair prompt carries the *concrete binding*
```

The key detail: the repair prompt contains a **concrete counterexample**
("under `loan_amount = 250000, occupancy = investment`, rules R-014 and R-031
both fire and assign `max_ltv` to 80 and 75 respectively — here are both cited
clauses"), not a generic "there is a conflict". This is the difference between
CEGIS and self-critique, and the ablation (witness vs. no-witness repair
prompts) is a required experiment.

Report accuracy and yield vs. repair round *k*, and the token cost of each
round. Expect diminishing returns by *k* = 3 *(target)*.

### 9.2 RLVR — the verifier as reward (training time)

Train an open-weight model (8–14B dense, or LoRA on ~32B) with GRPO-style
policy optimization on a composite programmatic reward:

```
r =  w₁ · 1[compiles]
   + w₂ · (fraction of test vectors replayed)
   + w₃ · 1[no unresolved SMT conflict]         # solver, not a model
   + w₄ · (provenance precision vs. cited spans)
   + w₅ · (decision agreement on train-split gold queries)
   − w₆ · (abstention rate)                     # so abstaining isn't free
```

Three properties worth stating explicitly because they are what make this a
NeurIPS contribution rather than a fine-tuning report:

1. **The reward is not a learned judge.** w₁–w₄ are computed by a compiler and
   a solver. No reward model, no LLM-as-judge in the training loop, hence no
   reward hacking through judge persuasion.
2. **The reward is dense in a domain that had none.** Before compilation, the
   only signal on "did you extract this policy correctly" was a human or an LLM
   judge. Compilation manufactures a dense, cheap, automatic signal.
3. **Abstention is priced.** The pipeline's readiness gate already produces an
   honest "unresolved" state. Left unpriced, RL will learn to abstain on
   everything; w₆ makes selective prediction a trade-off the model must
   navigate, which is exactly what we then measure with risk–coverage curves.

**Headline result to aim for:** an 8–14B open model, RLVR-trained on the
verifier, exceeds a frontier prompted model on decision agreement at equal or
better coverage *(target)*. That is the result that makes this a main-track
paper rather than a benchmark paper.

### 9.3 Where this repository already sits

The repo is the substrate; roughly half the verifier exists as a *self*-report
and needs to become an *external* instrument:

| Needed | Status in this repo |
| --- | --- |
| v2 typed rule contract + validator | ✅ `utils/rule_contract.py`, closed enums, unit-tested |
| Four-invariant hard gate (corpus / naming / schema / referential integrity) | ✅ `agents/agent_07_executable_readiness.py` |
| Claim-level grounding certification | ✅ `agents/agent_09_grounding_verifier.py` (6 of 12 claim types LLM-verified; rest structural) |
| Dependency DAG partition, 100% coverage, SCC condensation | ✅ `utils/dag_builder.py` |
| DMN/BPMN *projection* | ⚠️ 12-line column manifest (`_project_execution`) — a hint, not a model |
| **DMN 1.3 XML / FEEL renderer + evaluator** | ❌ does not exist |
| **SMT-LIB backend + solver queries** | ❌ does not exist |
| **Vector-replay conformance gate** | ❌ does not exist (a throwaway spike existed; see §13) |
| **Metamorphic harness** | ❌ does not exist |
| **RL environment wrapping the verifier** | ❌ does not exist |
| Benchmark corpora, checksummed, license-clean | ✅ `benchmarks/` — CUAD, ContractNLI, OPP-115, MAPP |

So: the extraction half is built and tested (`pytest`: 770 passed, verified
2026-08-24); the *measurement* half is the research build.

---

## 10. Metrics

Defined precisely, because vague metrics are how this kind of paper dies.

| Metric | Definition |
| --- | --- |
| **DA** — Decision Agreement | over a query distribution *Q*, `E_q[ 1(⟦A⟧(q) = gold(q)) ]`; the primary metric |
| **EA** — Entailment Accuracy | 3-way accuracy on ContractNLI queries answered by SMT over ⟦*A*⟧ |
| **EY** — Executable Yield | fraction of documents producing a compiled, gate-passing artifact (coverage) |
| **S-DA@c** | selective decision agreement at coverage *c*; the risk–coverage curve, summarized by **AURC** |
| **SR / SE / SDI** | invariance rate, correct-change rate, and `SR + SE − 1` on LEXEC-Perturb |
| **PP** — Provenance Precision | overlap of artifact-cited sections with expert evidence spans (free from ContractNLI/CUAD) |
| **CQI** — Cross-Query Inconsistency | fraction of query pairs whose answers cannot come from one consistent function; **0 by construction** for compiled artifacts (P4) |
| **VR** — Vector Replay | fraction of source-attested test vectors reproduced by the *emitted* artifact |
| **Conflict / gap / vacuity density** | solver-detected defects per 100 rules — a graph-quality measure with no human in the loop |
| **Cost** | USD and tokens per document to *build* the artifact; USD per query to *use* it |

Note the deliberate pairing: EY and DA trade off, so neither may be reported
alone. Every table reports (DA, EY) jointly or an S-DA@c curve.

---

## 11. Experiments and baselines

### 11.1 Baselines that must be in the paper

1. **Prompt-only frontier models**, one-shot document → v2 rule set (no
   pipeline, no repair). Several model families.
2. **The full existing pipeline, unchanged** — 10 stages, no compiler feedback.
   This is the "does the elaborate pipeline earn its cost" ablation, and it
   must be allowed to lose.
3. **Direct-to-Python.** "Write a Python function that decides *X* from this
   contract." Code LLMs are extremely strong at this. **This baseline may well
   beat DMN on DA, and the paper must say so if it does** — the defense is then
   auditability, provenance, consistency, and standards-compatibility, all of
   which are separately measured (PP, CQI), not asserted.
4. **Direct long-context QA.** Whole document in context, answer each query
   directly. No artifact. This is the strongest accuracy baseline and the most
   important comparison.
5. **RAG QA** over chunked documents — the industrial default.
6. **Fine-tuned span extraction** (a CUAD/ContractNLI-style supervised model)
   for the surface-metric arm of the dissociation study.
7. **Ablations of ours:** −CEGIR; −witness (repair without the concrete
   counterexample); −defeater semantics (exceptions as conjunction / ignored);
   −semantic dedup (text-similarity dedup instead); −SMT (vector replay only).

### 11.2 Target-language ablation (answers objection 4)

Same extraction, four compilation targets: **DMN 1.3 + FEEL**, **SMT-LIB**,
**Python**, **ASP/Datalog (defeasible-friendly)**. Measure DA, EY, and defect
density per target. The scientific question — *which formal target can an LLM
hit most reliably, and does defeasible-native representation help?* — is
interesting whichever way it lands, and it converts "why DMN?" from a weakness
into a section.

### 11.3 The amortization and consistency experiment (answers objection 3)

For each document, answer *N* queries under each regime:

- **Compiled:** one compile (~document-length tokens, once) + *N* free solver
  calls. Marginal query cost ≈ 0. CQI = 0 by construction.
- **Long-context QA:** *N* × (document + query) tokens. **Report with and
  without prompt caching** — caching narrows the gap substantially and a
  reviewer will raise it, so we raise it first. Measure CQI empirically.

Report the break-even *N*. For ContractNLI's 17 hypotheses per NDA the gap is
modest; for scenario sweeps (10³–10⁴ fact bindings, which is the actual
industrial use — "what does this policy decide across our whole book of
business?") it is ~10²–10³×. The honest claim is therefore conditional on *N*,
and stated that way. The unconditional claim is CQI: guaranteed 0 vs. measured.

### 11.4 Generalization experiments

- **Cross-domain:** train RLVR on one corpus, evaluate on the other three.
  Domain vocabularies barely overlap (NDA propositions vs. privacy practice
  categories vs. CUAD clause types), so this is a real transfer test — and the
  repository already has direct evidence that domain-specific coupling breaks
  silently (the `rule_type`-keyed BPMN gate produced zero targets for five of
  eight domains until it was fixed).
- **Cross-lingual:** MAPP's German half, evaluated through the shared formal
  language.
- **Cross-task transfer (the generality claim):** apply the same
  compile-and-verify recipe to one non-compliance domain — clinical practice
  guidelines or benefits eligibility rules — to support "this is a recipe, not
  a compliance system." Even a small-scale version strengthens the paper
  considerably.

---

## 12. Pre-registered headline table (what "strong enough" looks like)

Filling this in with these magnitudes is roughly the accept threshold. These
are **targets**, and the proposal is written so that missing them still yields a
publishable paper (§18).

| Result | Target |
| --- | --- |
| DA, best baseline (long-context QA) on ContractNLI entailment | strong — assume it is the number to beat |
| DA, ours (pipeline + CEGIR + RLVR) | ≥ baseline, at ≥ 90% EY |
| DA gain from CEGIR alone | +6–12 points absolute |
| DA gain from RLVR over SFT on the same data | +5–10 points absolute |
| 8–14B RLVR model vs. frontier prompted model | ours ≥ theirs on DA |
| ρ(span-F1, DA) — the dissociation | < 0.4 |
| LLM grounding-verifier flag rate vs. VR failure rate | ≥ 5× over-rejection, replicated across 4 domains |
| SDI on LEXEC-Perturb, best system | < 0.7 (i.e. the benchmark is *not* saturated — a benchmark everyone solves is worthless) |
| CQI, compiled vs. long-context QA | 0 vs. > 5% |
| Solver-detected conflict density, before vs. after CEGIR | ≥ 60% reduction |
| Amortized cost at N = 10³ scenario queries | ≥ 100× cheaper than per-query QA (with caching enabled for the baseline) |

---

## 13. Preliminary evidence already in hand — and its limits

A throwaway spike (built against this pipeline's predecessor monorepo, on a
352-rule certified graph) produced these numbers. They are the reason to
believe the compiler is feasible at all. **All of them come from one run, one
domain (mortgage), n = 1**, and the artifacts are not in this repository.

| Measurement | Result *(measured, n=1)* |
| --- | --- |
| Rules with complete DMN-critical structure | 352/352 (100%) |
| Rules emitting well-formed DMN 1.3 XML | 352/352 (100%) |
| Predicate/outcome literals not renderable as FEEL | 0 of 1,385 |
| Distinct operators in use (all FEEL-expressible) | 8 |
| DNF expansion | 429 rows from 352 rules; 87.5% single-row; worst case 7 |
| Rules requiring negation nodes | 0 |
| **Test vectors reproduced by generated row logic** | **361/384 (94.0%)** |
| Vectors where a rule fired with a *wrong* value | **0** |
| Grounding verifier flagged as requiring review | 345/352 (98%) ← the dissociation |
| Rules with exceptions | 155/352; **125 introduce variables absent from the condition** |
| Hit-policy mix | 324 UNIQUE / 24 COLLECT / 4 ANY |
| Rules needing UNIQUE→FIRST downgrade | 42 |
| Output-signature groups | 336 groups for 352 rules; 323 singletons |
| Dependency-edge types | prerequisite 138, complementary 46, conditional 45, sequential 37, validation 18, override 16, contradictory 5 |

**What should generalize:** the operator/type/hit-policy inventories and the DMN
column derivation are *schema-level* properties of the v2 contract, not domain
properties. FEEL mappability and DNF tractability should hold for any
contract-conformant domain.

**What almost certainly will not:** the 94% replay rate, the 87.5% single-row
share, the conflict count, and anything keyed to `rule_type` — there is direct
in-repo evidence that `rule_type`-dependent behavior breaks across domains.

**Therefore the first experiment of the project is a replication**, not a build:
re-run one benchmark domain (ContractNLI or OPP-115 — the vocabularies furthest
from mortgage) under the v2 contract and re-measure every row of that table.
If the replay rate collapses on a non-mortgage domain, the project's shape
changes, and it is far better to learn that in month 1 than in month 6.

Also inherited from that analysis, and relevant to the paper's honesty section:
the grounding verifier LLM-checks only 6 of 12 claim types against actual corpus
quotes (`description`, `condition`, `outcome`, `party`, `scope`, `exception`);
`test_vector`, `condition_logic`, `variable`, `classification`,
`entity_attachment`, and `execution` are checked structurally only. So
"certified" does **not** mean "the DMN projection was verified against source
text." The correctness argument is a *chain* — the verifier checks conditions
and outcomes against source; vector replay checks the artifact against
conditions and outcomes — and the paper must claim only the composition.

---

## 14. Timeline (2026-08 → 2027-05) with go/no-go gates

| Month | Work | Gate |
| --- | --- | --- |
| **Sep 2026** | Replicate §13 on one non-mortgage benchmark domain. Build `utils/feel.py` (renderer + evaluator) and `utils/dmn_builder.py` (DNF → rows, hit-policy reconciliation). Decide defeater semantics empirically. | **G1:** ≥ 90% of certified rules emit schema-valid DMN and ≥ 85% of positive vectors replay, on a non-mortgage domain. *If not: pivot to Plan B (§18).* |
| **Oct 2026** | SMT-LIB backend + the seven solver queries (§6). Semantic dedup/subsumption. Conformance gate (`cli/compile.py`, stages C1–C4). Provenance into artifacts. | **G2:** all seven queries running on a real graph; conflict/gap/vacuity densities measured on ≥ 2 domains. |
| **Nov 2026** | LEXEC-Bench harness: ContractNLI entailment mode end-to-end; CUAD and OPP-115/MAPP query builders. First DA numbers. Write up an early version for a legal-NLP workshop (e.g. NLLP) to get external feedback and stake the claim. | **G3:** DA measurable on ≥ 5k gold queries; long-context QA baseline implemented. **This is the make-or-break gate** — if DA can't be computed, there is no paper. |
| **Dec 2026** | The dissociation study (C4): span-F1 / LLM-judge vs. DA correlation; grounding-verifier over-rejection replication across 4 domains. Contamination probes. | **G4:** dissociation replicates on ≥ 3 domains, or is honestly reported as absent. |
| **Jan 2027** | LEXEC-Perturb: annotation guidelines, closed relation list, tooling, annotator hiring, pilot (200 items, IAA). Then full annotation in parallel with Feb work. | **G5:** IAA ≥ 0.7 on relation labels. |
| **Feb 2027** | CEGIR: repair loop, witness-vs-no-witness ablation, rounds-vs-accuracy curves. Target-language ablation (DMN / SMT-LIB / Python / ASP). | **G6:** CEGIR shows ≥ 5-point DA gain. |
| **Mar 2027** | RLVR: RL environment wrapping the verifier, GRPO on an 8–14B model, reward shaping, abstention pricing, risk–coverage curves. | **G7:** RLVR beats SFT on the same data by ≥ 3 points DA. |
| **Apr 2027** | Cross-domain / cross-lingual / cross-task transfer. Amortization + CQI experiment. Human validation of the scenario subset. Full results freeze by **Apr 30**. | **G8:** all headline table rows filled. |
| **May 2027** | Writing, figures, artifact release (code, harness, perturbation edit scripts), reproducibility checklist, broader-impact statement. Submit. | — |

Two deliberate scheduling choices: the benchmark comes **before** the method
(if DA is not measurable, no amount of method work saves the paper), and
annotation starts early because it is the only irreducibly slow item.

---

## 15. Compute and cost budget (rough, for planning)

**LLM extraction.** The four corpora total 1,387 documents through a 10-stage
pipeline with reasoning models. Order-of-magnitude: a few dollars per document
per full pipeline run → **~$3k–$11k for one complete sweep of all four
corpora**. Experiments need many sweeps (model conditions × ablations × CEGIR
rounds), so:
- Main results on a **stratified subsample** (~150 docs/corpus ≈ 600 docs).
- One **full-corpus** run on ContractNLI (607 docs) for the flagship number.
- Cheap models for ablation sweeps; frontier models only for headline rows.
- Budget line: **$15k–$30k** in inference across the project, with a hard cap
  and per-experiment cost logging from day one. (The pipeline already has an
  adaptive global rate limiter, so concurrent batch runs are safe.)

**RL training.** GRPO on an 8–14B dense model: ~8×H100 for 1–2 weeks per
serious run, plus false starts. LoRA on ~32B as the cheaper alternative.
Budget **2–4 such runs**. The verifier itself is CPU-bound (compiler + SMT), so
plan for a solver farm — solver calls, not GPU, may be the throughput
bottleneck in the RL loop. Cache aggressively: identical rule sets recur across
rollouts.

**Annotation.** ~1.5–2k perturbation items at 2–4 min, double-annotated at 20%
→ ~120–160 annotator hours. Plus ~500 scenario validations. Budget for 2–3
qualified annotators (law students / privacy-compliance practitioners).

---

## 16. Risks and mitigations

| Risk | Severity | Mitigation |
| --- | --- | --- |
| **Extraction quality is the bottleneck, not compilation** — garbage rules compile perfectly into garbage DMN | **High** | This is *the* central risk. Mitigated by making the benchmark the primary contribution: even if DA is low across the board, an honest benchmark showing "nobody can do this yet" is publishable and valuable. Also why G3 precedes method work. |
| §13's numbers don't replicate off-mortgage | **High** | G1 in month 1; Plan B ready |
| Direct long-context QA simply wins on DA | **High** | Pre-committed: report it, and pivot the claim to auditability + CQI + amortization, all pre-registered as separate measured axes. Do **not** hide it. |
| Defeater semantics is wrong | Medium | Empirically compare all three readings; report which the vector suite and LEXEC-Perturb support |
| Contamination inflates results | Medium | Perturbed + post-cutoff held-out splits; memorization probe |
| ContractNLI hypotheses aren't answerable from compiled rules (representational mismatch) | Medium | Pilot 50 documents by hand in month 1; if a hypothesis class is systematically unanswerable, exclude it *and report the exclusion rate as a finding* about representational adequacy |
| SMT throughput limits the RL loop | Medium | Cache by rule-set hash; bound row counts; time-box solver calls with a recorded timeout rate |
| Annotation IAA too low on "meaning-preserving" | Medium | Closed relation list, pilot, adjudication pass, report IAA per relation |
| Reviewers see "application paper" | Medium | Lead with the no-gold-program problem (§2) and the cross-task transfer experiment; the compliance corpora are the *testbed*, not the topic |
| BPMN over-interpretation | Medium | Only `prerequisite`/`sequential` edges become sequence flows (of 305 edges, 175); everything else is reported as a modelling note. **De-scope BPMN from the paper** — DMN carries the logic and the guarantees; BPMN is orchestration with a much weaker correctness story. Mention it as future work. |
| Scope creep across three contributions | **High** | Contributions are staged so each is independently publishable; §18 defines what to cut and when |

---

## 17. Related work and positioning

To be filled in with verified citations — **none of the references below have
been checked against a live database in preparing this document, so verify
every one before use.** The map is what matters here:

- **Law as code / manual formalization:** Catala (a DSL for statutory law),
  LegalRuleML, OpenFisca, Blawx, Symboleo. *Difference:* these are hand-written
  formalizations by experts. Ours is extracted and verified automatically. Their
  existence is evidence the target representation is the right one — cite them
  as motivation, not as competition.
- **Legal/privacy NLP corpora:** CUAD (NeurIPS D&B 2021), ContractNLI (Findings
  of EMNLP 2021), OPP-115 (ACL 2016), MAPP (LREC 2022), LexGLUE, SARA
  (statutory reasoning), CLERC, Claudette. *Difference:* all evaluate at the
  span or label level. We evaluate the same corpora **extensionally** — which is
  precisely the novel use of them.
- **Privacy-policy formal analysis:** PolicyLint, PoliCheck, Polisis, PolicyQA.
  *Difference:* hand-built taxonomies and narrow flow logic for privacy only;
  ours is learned, general, and executable. These are the closest prior art in
  spirit and deserve careful, generous treatment.
- **LLM + solver neurosymbolic:** Logic-LM, SatLM, LINC, program-of-thought,
  and FOLIO/ProofWriter-style benchmarks. *Difference:* short synthetic
  problems with gold logical forms; single questions, not documents; no
  training from verifier feedback; no defeasibility; no amortized artifact.
- **Semantic parsing / text-to-SQL:** Spider and execution accuracy. *This is
  our methodological ancestor and we say so.* Difference: gold programs exist
  there; documents (not utterances) are the input here; defeasible open-world
  semantics; artifact must be audit-traceable.
- **RLVR:** verifiable-reward RL in math, code, and theorem proving. *Difference:*
  we manufacture the verifier for a domain that had none. The claim
  "verifiable rewards beyond math and code" is the paper's most portable line.
- **Metamorphic / behavioral testing of NLP:** CheckList and successors.
  *Difference:* their invariance is checked on text-level outputs; ours is
  checked by **exact logical equivalence** on formal outputs — a strictly
  stronger instrument, available only because the output is compiled.
- **Selective prediction / calibration:** risk–coverage, AURC. We frame the
  readiness gate as selective compilation.
- **Business process / decision management:** DMN 1.3, BPMN 2.0, FEEL, decision
  hit policies, and the process-mining literature.

**One-line positioning:** *prior work either formalizes law by hand, or
evaluates legal NLP by string overlap. We do neither: we compile, and then we
measure what the compiled thing decides.*

---

## 18. Fallbacks — what to cut, and when

Staged so that a failure at any gate still yields a paper.

- **Plan A (target).** Main-track paper: benchmark + dissociation + CEGIR +
  RLVR. All four contributions.
- **Plan B (if G1 fails — compilation doesn't generalize off-mortgage).** The
  paper becomes *"Why document-to-logic extraction fails: a decidable
  diagnosis."* Use the compiler as a *diagnostic* instrument: characterize
  exactly which semantic phenomena defeat extraction (defeasibility, cross
  references, temporal scope, deontic modality, vagueness — "reasonable
  efforts", "material adverse change"). A rigorous negative result with a
  decidable taxonomy of failure is a genuinely good NeurIPS paper and needs no
  RL at all.
- **Plan C (if G7 fails — RLVR doesn't beat SFT).** Drop the method; submit
  benchmark + dissociation + CEGIR to the **Datasets & Benchmarks** track. A
  decision-level benchmark over four established corpora, plus the metamorphic
  suite, plus the miscalibration finding, is a solid D&B contribution.
- **Plan D (if annotation slips).** Ship LEXEC-Bench without LEXEC-Perturb;
  hold the perturbation suite for a follow-up. The extensional half stands
  alone.
- **Deliberate spin-offs** (do not put these in the main paper):
  - BPMN orchestration from dependency DAGs — weaker guarantees, separate venue.
  - Semantic deduplication by logical equivalence vs. embedding similarity — a
    tidy short paper on its own.
  - The RL environment as a standalone released artifact ("a verifiable-reward
    environment for document-to-logic extraction").

---

## 19. Ethics, licensing, release

- **Not legal advice.** Everything is decision *support*. The paper must state
  it, and the artifact must carry it.
- **Automation bias is the real harm.** A confidently wrong compiled artifact is
  more dangerous than a confidently wrong sentence, precisely because it looks
  authoritative and executes. Mitigations to state and measure: mandatory
  provenance on every emitted row; the explicit `unresolved` state as a
  first-class output; risk–coverage reporting rather than a single accuracy
  number; refusal to emit from uncertified input by default.
- **Licensing.** OPP-115 and MAPP carry no redistribution grant: release edit
  scripts and offsets, not text. CUAD and ContractNLI are CC BY 4.0. Cite all
  four papers. The repo's `benchmarks/datasets.json` (checksummed upstream URLs)
  is already the right template for reproducibility without redistribution.
- **Annotator treatment.** Fair pay, disclosed rates, disclosed IAA, published
  guidelines.
- **Dual use.** Low, but real: the same machinery could be used to find gaps in
  a policy in order to exploit them. Worth a sentence in broader impact — and
  the honest counterpoint is that the same capability is what makes compliance
  auditable at all.
- **Release plan.** Compiler, solver layer, benchmark harness, perturbation edit
  scripts, RL environment, and trained adapter weights. Reproducibility
  checklist filled honestly, including the cost of a full reproduction.

---

## 20. Immediate next four weeks

Concrete, ordered, and all of it is month-1 gate work:

1. **Pick the flagship corpus.** Recommendation: **ContractNLI** — 607 NDAs,
   17 expert-labeled hypotheses each, evidence spans included. It is the only
   corpus that hands us ~10.3k decision-level gold labels *and* free provenance
   gold, and its `rule_type` vocabulary is far from mortgage's, which makes it
   the right replication target for §13.
2. **Hand-pilot 50 ContractNLI documents.** For each of the 17 hypotheses, ask:
   *is this answerable as an SMT query over a compiled rule set at all?*
   Record the unanswerable classes. This is the cheapest possible test of the
   paper's central assumption, and it costs days, not weeks.
3. **Run the existing pipeline on that 50-doc subset** and re-measure every row
   of §13's table. This is G1.
4. **Build `utils/feel.py` + `utils/dmn_builder.py`** (renderer, evaluator, DNF
   expansion, hit-policy reconciliation with recorded downgrades) with the
   repo's existing dependency-free, unit-tested style. Note: the two tests in
   `tests/test_inter_agent_contract_alignment.py` pin `_project_execution`'s key
   set to what `final_rule_issues` reads — the compiler must sit strictly
   downstream and treat `execution` as read-only input.
5. **Resolve the defeater semantics empirically** on that subset: compile under
   all three readings, replay the vectors, and see which reading the data
   supports. Then write the winner into the contract documentation.
6. **Draft the ContractNLI query builder** (hypothesis → SMT entailment query)
   and get a first DA number on 50 documents, however bad. A bad number in
   month 1 is worth more than a good number in month 6.
7. **Start annotation logistics now** (guidelines, closed relation list,
   annotator sourcing) — it is the long-lead item.

---

## Appendix A — Naming

| Name | What it is |
| --- | --- |
| **LEXEC** | umbrella project name |
| **LEXEC-Verify** | the compiler + solver layer; the measuring instrument and the reward machine |
| **LEXEC-Bench** | the extensional benchmark (entailment / presence-value / practice-decision / scenario modes) |
| **LEXEC-Perturb** | the relational (metamorphic) suite |
| **CEGIR** | Counterexample-Guided Iterative Repair |
| **SDI** | Semantic Discrimination Index, `SR + SE − 1` |

## Appendix B — Provenance of the claims in this document

- **Verified by reading this repository's code:** the v2 contract's closed
  enums (`utils/rule_contract.py`); the four invariants and the DMN/BPMN
  projection (`agents/agent_07_executable_readiness.py`); which grounding claim
  types reach the LLM verifier vs. are checked structurally
  (`agents/agent_09_grounding_verifier.py`); the DAG partition and SCC
  condensation (`utils/dag_builder.py`); the readiness/selective-prediction
  logic (`utils/readiness.py`, `utils/kg_readiness.py`); the absence of any
  FEEL/DMN/BPMN XML or SMT code anywhere in the repo; corpus sizes, licenses,
  and checksums (`benchmarks/datasets.json`, `benchmarks/README.md`).
- **Inherited from a prior feasibility study** (a 520-line analysis written
  against this pipeline's predecessor monorepo, removed from this repo in commit
  `1dea9c8` and recovered from git history for this proposal): every *(measured)*
  number in §13. One run, one domain, n = 1. The artifacts it measured are not
  in this repository.
- **Not verified and requiring work before use:** every citation in §17; all
  cost and compute estimates in §15; every *(target)* number in §12; the
  assumption that ContractNLI hypotheses are answerable as SMT queries over
  compiled rules (item 2 of §20 exists to test exactly this).
