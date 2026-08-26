# NeurIPS 2027 Research Proposal — v4 (implementation-audited, evidence-gated)

> **v4 changes (2026-08-26).** The earlier reviews correctly identified missing
> compiler, pipeline, benchmark, statistics, and reward contracts. Those local
> implementation gaps are now closed: the machine-readable plan contains 38
> validated tasks, and every task in the 171 person-day programme has a locally
> executable implementation contract. That does **not** mean the scientific
> programme is complete. Only 23 person-days are classified `done`; the
> remaining task implementations are deliberately `implemented` because their
> publishable claims still need licensed data, independent human annotation,
> a pinned external DMN engine, approved provider/GPU runs, or real experimental
> observations. Sections 12.3–12.4, 16–17, 19, 23, and 28 now state that boundary
> explicitly. Sections 24–27 remain a dated review record and are not the active
> status source.

**Working title:** *Executable Evaluation of Normative Text-to-Logic Systems:
A Bounded Compiler and Instrument Validation*

**Umbrella project name:** **LEXEC** — compile normative documents into executable
decision logic, and use the compiler as the measuring instrument.

| | |
| --- | --- |
| Target venue | **Working assumption: NeurIPS Evaluations & Datasets track.** The 2027 CFP and track list are not published; the [2026 official call](https://neurips.cc/Conferences/2026/CallForEvaluationsDatasets) renamed “Datasets & Benchmarks” to “Evaluations & Datasets” and explicitly welcomes evaluation methods, audits, tools, and negative results. Main track is credible only if a method result such as CEGIR or solver-reward training lands in addition to the evaluation contribution. |
| Target deadline | **Confirmed only: [NeurIPS lists 2027 — Europe](https://neurips.cc/Conferences/FutureMeetings).** The month, submission dates, CFP, paper format, and track list remain unannounced. Use **2027-04-15 internal freeze / ~2027-05-01 planning deadline** until the official CFP appears, then replace both dates. |
| Time available | About eight months to the internal freeze from 2026-08-26 |
| Substrate | Current checkout: complete 10-stage extraction pipeline; full source-chunk coverage; v2 extraction contract; canonical LExec IR v1 and total fail-closed lowering; bounded reference/FEEL evaluation; DMN 1.3 emission; bounded solver queries and proof records; Dutch and ContractNLI adapters; run retention, statistics, perturbation, CEGIR, reward-audit, and publication-artifact contracts; and an interactive review workbench. `pytest` currently collects **1,051 core Python tests**. These are engineering assets, not benchmark results. |
| Status | **Implementation-complete, evidence-incomplete.** `(measured)` = a retained real run with a declared observation unit. `(exploratory)` = a real but non-claiming run. `(fixture-only)` = contract validation only. `(unrun)` / `(blocked)` remain visible. `(target)` and `(published)` are never presented as repository results. |
| Development plan | [`neurips-plan-2027.md`](neurips-plan-2027.md) — the buildable form of §26: task IDs, module layout, acceptance tests, effort in person-days, and the G0→G5 sequence |
| Filename | `plan/neurIips-proposal-2027.md` preserves the original filename typo; both proposal and companion plan now live under `plan/`. Rename only with a repository-wide link migration. |

---

## TL;DR

**The claim.** Compiling a normative document into an executable decision
artifact makes a **bounded set of semantic properties and behaviors decidable**:
type validity, table overlap, hit-policy safety, satisfiability, selected
conflicts, and outcome behavior inside the supported IR. It does **not** make
source fidelity or legal correctness decidable. The paper's central empirical
question is whether source-grounded, artifact-free signals predict gold-artifact
outcome equivalence well enough to serve as a measurement instrument.

**The problem it solves.** There is no gold DMN for real contracts, and even
where one exists, correctness is invariant under renaming, reordering, and table
splitting — so form-matching metrics measure style, not meaning. Judge behavior
instead: what does the artifact *decide*? The thing no corpus has is a gold
**formalization**, not a gold **label** — an equivocation that cost v3 its
central metric (§9.2).

**What this cannot claim.** A decision-table target cannot express deontic
modality, temporal validity, defeasibility beyond a fixed negation, or vagueness
("reasonable efforts"). The IR refuses most of that (§5). So the honest framing
is not "we evaluate document understanding" but **"we evaluate the fraction of
normative content a decision-table semantics can carry, and we measure that
fraction"** (§14.6).

**Four pieces**, in dependency order:

1. **LEXEC-Verify** — an LLM-free, fail-closed compiler (v2 rule contract →
   LExec IR v1 → bounded reference/FEEL execution and DMN 1.3) plus bounded
   solver-shaped queries and proof records. The implementation and conformance
   tests exist; a pinned third-party DMN-engine result and corpus-scale
   correctness result do not. → §§7, 12.3, 28
2. **Instrument validation** (the spine) — do **artifact-free signals** predict
   **artifact-based** outcome equivalence? The Dutch DMN corpus makes it testable
   on **58** models. If yes, results on corpora with no gold formalization
   inherit **bounded** credibility — bounded by one jurisdiction, one language,
   one statute; if no, that finding should change how the subfield evaluates
   itself. It is also the contribution that does not depend on publishing first.
   The adapter, isolation boundary, estimator, controls, and retained artifact
   schema exist; the observation bundle is still `unrun`. → §§9, 28
3. **Assumption-explicit compilation** — gold legal labels smuggle in unstated
   assumptions (**71** ContractNLI entailments flip to neutral under strict
   logic *(published)*). So the artifact emits a verdict *plus* the minimal
   assumption set it needed, and the solver checks typed consistency and
   selected necessity obligations. The analyzer exists; the human source-support
   and legal-admissibility study is `unrun`. → §§10, 28
4. **Solver-reward RL + counterexample-guided repair** — the verifier becomes a
   programmatic reward; solver witnesses drive repair. The source-preserving
   CEGIR and adversarial reward-audit contracts exist. No training frontier has
   been run, and no RL claim belongs in the minimum paper. → §§12, 28

**Scope after implementation audit.** The minimum paper is now narrower and more
executable: (1) bounded compiler correctness, (2) Dutch-anchor replay and our
compiled-artifact evaluation, (3) instrument validation with frozen controls,
and (4) one carefully bounded non-Dutch transfer result only if its evidence
gate passes. Assumption analysis and CEGIR are extensions. Solver-reward RL is
optional and cannot delay the minimum paper. This points to **Evaluations &
Datasets** as the working track; a main-track submission needs a genuine method
result, not merely implemented scaffolding.

**The old engineering blockers are fixed; evidence blockers replace them.** The
extractor now processes every source chunk and records zero dropped bytes, and
the optimizer receives full v2 fields. What remains is scientific: real
PIPE-2B/PIPE-4 annotation frames, a corpus-scale IR census, a pinned external
engine run, resolution of the anchor replay mismatch, a real J1 observation
bundle, and the G3 instrument study. Fixture scores and exploratory local runs
must not be promoted into conference results.

**Why it is worth doing now.** The closest published work sits at **42.6%**
macro-averaged outcome equivalence *(published)* — the task is wide open. If
compilation does not generalize, a valid, adequately powered diagnostic study
may still support a paper about where document-to-logic extraction fails. An
invalid or underpowered study is not automatically publishable (§20).

**Three things this proposal explicitly does *not* claim**, after checking the
literature: that gold artifacts never exist (§1.1), that ContractNLI-as-SMT-entailment
is new (§1.2), or that metamorphic evaluation by formal equivalence is new
(§1.3). What is left after those cuts is narrower and better defended.

---

## 0. The one-sentence claim (revised)

> Compiling a normative document into a bounded, executable IR makes selected
> semantic properties and outcome behavior decidable; validating source fidelity
> still requires independent evidence, gold-artifact calibration, and explicit
> accounting for assumptions and refusals.

Version 1 of this proposal claimed something broader ("no gold program exists,
so extensional evaluation is the only escape"). The literature review below
forced three corrections, and the claim above is what survives them — narrower,
and considerably better defended.

---

## 1. What the literature review changed (read this section first)

I searched the legal-NLP, law-as-code, neurosymbolic, BPM, autoformalization,
and RLVR literatures. Seven findings changed the proposal; three of them
invalidate specific v1 claims outright.

### 1.1 The premise "there is no gold program" is false in one important case

**Graus, *From Legal Text to Executable Decision Models*, ICAIL 2026**
(arXiv:2604.17153) released **95 production-grade DMN decision models paired
with their source legal text** — the Dutch Environment and Planning Act
(*Omgevingswet*), powering the government's *Omgevingsloket* permit portal —
under CC BY 4.0, **with an execution-based evaluation harness**
(`github.com/opengov-lab/legal-text-to-decision-model`).

Worse for v1: their primary metric, *outcome equivalence* — run gold and
generated models on exhaustive input combinations and compare decisions — **is
exactly my "Decision Agreement."** Someone published the core evaluation idea
four months ago.

Better for v2: their results are the strongest possible empirical support for
the *canonical-form* argument v1 could only assert. Best condition reaches
**42.6% outcome equivalence** on Outcome models and **60.4%** on Requirements
models; only **33% of models achieve full equivalence**; and generated models
contain just **26–35% of the gold models' nodes**, while **45–55% of gold nodes
are identity/pass-through** *(all published)*. Behavior and form come apart, at
scale, measured. And a task at 42.6% is nowhere near saturated.

**So: adopt their dataset, don't compete with it.** §9 turns it into the single
most valuable thing in this proposal — a way to *validate the measuring
instrument itself*.

### 1.2 ContractNLI-as-SMT-entailment is done, and it found a problem with the oracle

**Wang et al., *Know Your Limits: On the Faithfulness of LLMs as Solvers and
Autoformalizers in Legal Reasoning*** (arXiv:2606.16118, June 2026) re-annotated
**400 ContractNLI examples** (expanded to 610 with minimal pairs) under *strict
formal entailment*, and ran pure-LLM classification vs. LLM-based formal
reasoning vs. Z3 solver-based formal reasoning across five LLMs.

Their findings hit v1's flagship benchmark design directly:

- **71 entailment cases had to be reclassified as neutral** — ContractNLI's gold
  labels encode *pragmatic legal interpretation*, and a substantial share of
  legally sound inferences are not formally grounded without unstated
  assumptions *(published)*.
- **"Scope laundering":** LLMs report solver-inconsistent classifications
  without actually executing the formal reasoning — **15.3% (GPT) to 52.5%
  (Qwen)** *(published)*.
- **Z3 program-synthesis failure rates: 25.5% (Claude) to 63.2% (Llama)**
  *(published)*.
- Best accuracy: LLM-based formal reasoning, **Claude 83.0%** *(published)* —
  yet the paper's whole point is that this number does not imply faithfulness.

Consequences for this proposal, all of them design changes rather than
inconveniences:

1. **Strict SMT entailment against ContractNLI's original labels is the wrong
   oracle.** v1's ContractNLI design would have measured the gold set's pragmatics, not the
   artifact's quality. §10 replaces it with **assumption-explicit compilation**.
2. **"Scope laundering" is direct empirical support for this project's core
   architectural decision** — the compiler makes *no LLM calls*, and
   verification is external rather than self-reported. A model asked to
   self-verify will, between 15% and 53% of the time, report a formal-looking
   verdict it never computed.
3. **Their stated future work is my §12.2**: "solver-based feedback training
   objectives for legal-domain LLMs." Someone is likely already building it.
   That is a competitive risk, not a validation — see §19.

### 1.3 Metamorphic evaluation via formal equivalence is already published

**Zhou et al., *LGMT: Logic-Grounded Metamorphic Testing*** (arXiv:2605.23965,
July 2026) is an oracle-free framework that derives metamorphic relations from
first-order-logic equivalences and detects reasoning defects by cross-case
consistency across six LLMs. Also relevant: **METAL** (arXiv:2312.06056), the
**metamorphic-testing-and-LLMs survey** (arXiv:2605.13898), and metamorphic
prompting that validates generated SQL by comparing *execution results* of
transformed queries.

v1 called relational/metamorphic evaluation "the strongest part of the design."
That was overclaiming. What survives is narrow but real, and stated as such in
§11: LGMT perturbs *the reasoning problem* and checks *answer* consistency; we
perturb *the source document* and check *logical equivalence of the compiled
artifact*. And the **meaning-changing, direction-annotated** relations
(scope tightening ⇒ applicability set strictly shrinks) appear genuinely
underexplored — so the emphasis moves from invariance to *refinement*.

### 1.4 Three more things exist that v1 treated as open

- **ContractCheck** (Khoja, Kölbl, Leue & Wilhelmi, *Artificial Intelligence and
  Law*; arXiv:2504.18422) encodes Share Purchase Agreements into decidable
  FOL fragments and uses an SMT solver to find conflicting clauses — via a
  manual, ontology-driven "blocks" encoding, on one realistic-size SPA with
  seeded inconsistencies.
- **PolicyGuard** (Malik, Singh & Azad, arXiv:2606.32004, July 2026) builds
  neuro-symbolic compliance-review engines from organizational policies,
  grounds retrieved contract clauses into atom-level truth values, uses Z3, and
  evaluates on **CUAD and ContractNLI**.
- **Horner, Mateis, Governatori & Ciabattoni** (arXiv:2506.08899) formalize
  legal text into **Defeasible Deontic Logic** with LLMs — atomic-snippet
  segmentation, deontic rule extraction, coherence evaluation — on the
  Australian Telecommunications Consumer Protections Code.

So: LLM → formal legal representation → solver is an established line. The
uncontested space is *corpus-scale, learned, and behaviorally validated*.

### 1.5 "Verifiable rewards beyond math and code" is too broad a claim

RLVR already covers text-to-SQL (**Reasoning-SQL**, arXiv:2503.23157),
information extraction (**LA-RL**, arXiv:2607.23420), structured output
(**RL-Struct**, arXiv:2512.00319), cyber threat intelligence (**Minerva**,
arXiv:2602.00513), knowledge-intensive QA (**K2V**), and autoformalization
(**ReForm**, arXiv:2510.24592; **StepFun-Formalizer**, arXiv:2508.04440;
process-verified Lean RL, arXiv:2606.20068). *RL with Symbolic Feedback* is a
named family. The narrowed claim is in §12.2.

### 1.6 The BPM community already evaluates generated models extensionally

LLM-generated process models are routinely scored by **conformance checking** —
simulate event logs from the ground-truth model, replay them, and/or compare
behavioral-footprint similarity (PM4Py). See **ProMoAI** (arXiv:2403.04327),
BPMN Assistant, Nala2BPMN, "Do LLMs Speak BPMN?", and the SoSyM benchmark study.
The **PET** dataset — the field's standard — has **47 text/BPMN pairs**.

Two consequences: extensional evaluation of generated formal artifacts has prior
art that must be cited (not claimed), and BPMN's evidence base is thin enough
that **de-scoping BPMN from this paper is now well-supported** rather than a
retreat.

### 1.7 Two gifts I did not have in v1

- **RuleArena** (arXiv:2412.08972, ACL 2025): 95 real-world rules, 816 problems,
  three domains (airline baggage, NBA transactions, tax). LLMs "perform poorly,"
  struggle to select the right rule, and improve markedly when given external
  tools for math and logic *(published)*. That is a ready-made, published
  measurement of the failure a compiled artifact is supposed to eliminate — so
  §14.3 adds a direct head-to-head.
- **Grammars of Formal Uncertainty** (Ganguly et al., **NeurIPS 2025**,
  arXiv:2505.20047): SMT autoformalization swings from **+34.8%** on logical
  tasks to **−44.5%** on factual ones; token-entropy UQ fails to catch the
  errors; a PCFG-based grammar-entropy signal reaches **AUROC > 0.93** on logic
  *(published)*. This is both proof NeurIPS takes this subject seriously and a
  strong, concrete baseline for my selective-compilation arm — I no longer have
  to invent one.

---

## 2. Why the obvious version of this project still gets rejected

The obvious paper is *"we built an LLM pipeline that turns compliance documents
into a knowledge graph and then into DMN/BPMN."* Six standing objections, now
with evidence attached:

1. **"This is engineering."** A pipeline is an artifact, not a claim.
2. **"Your KG intermediate isn't novel."** Correct, and now demonstrably so:
   **GraphCompliance** (arXiv:2510.26309) aligns policy and context graphs for
   GDPR compliance (+4.1–7.2pp micro-F1 over LLM-only and RAG on 300 scenarios);
   **Baldwin & Ghanavati** (arXiv:2604.27713) build KGs from AI-policy documents
   and beat baselines on 42 QA tasks; **SOLAR** (CIKM 2025, arXiv:2509.00710)
   uses formalized intermediate representations with symbolic inference for
   statutory reasoning. Drop every KG novelty claim.
3. **"Why not prompt a frontier model per query?"** Needs measurement, not
   assertion (§14.4).
4. **"DMN is niche."** Must be ablated against SMT-LIB, Python, and ASP (§14.2).
5. **"Where's the learning?"** §12.2, narrowed.
6. **"Legal NLP already did this."** Partly true (§1, §21). The paper must say
   exactly what is left.

Venue reality check: the closest paper went to **ICAIL 2026**; the CUAD-based
benchmark went to **NLLP 2025**; **LegalBench** went to NeurIPS D&B 2023;
**Grammars of Formal Uncertainty** went to NeurIPS 2025 main track. NeurIPS is
reachable — but only with the method and theory load-bearing, not the pipeline.

---

## 3. The premise, corrected

Gold formal artifacts for normative text are **rare, jurisdiction-bound, and
non-canonical** — not nonexistent.

- **Rare and bound:** the one substantial public collection is 95 models, one
  country, one language, one statute (§1.1). Nothing comparable exists for
  commercial contracts, NDAs, or privacy policies.
- **Non-canonical, and now measured:** correctness is invariant under renaming,
  reordering, DNF/CNF choice, table splitting, predicate factoring, and defeater
  placement. Graus's numbers show what that does to form-matching metrics —
  generated models with **26–35%** of gold's nodes reach **42.6%** behavioral
  equivalence, and **45–55%** of gold nodes are pass-throughs carrying no logic
  *(published)*. Structural similarity is measuring plumbing.
- **The gold labels themselves carry pragmatics:** ContractNLI's expert labels
  presume unstated assumptions (**71 entailment→neutral** re-annotations,
  §1.2) *(published)*.

Three consequences, and they are the paper:

**(A) Extensional evaluation, calibrated rather than assumed.** Judge behavior,
not form — and then *validate that judgment against the 95 gold artifacts*
(§9). Execution accuracy as a metric is inherited from semantic parsing (Spider;
**BIRD**, arXiv:2305.03111, 12,751 pairs / 95 DBs / ~73% execution accuracy;
Spider 2.0 at ~21.3% under agentic evaluation) and from BPM conformance checking
(§1.6). Saying so is the honest framing, and the contribution is that **we found
no prior work** checking whether a *gold-free* extensional metric agrees with a
*gold-based* one (§21 search protocol).

**(B) Assumption-explicit semantics.** If the gold answer needs an unstated
assumption, the artifact should *name* it rather than silently absorb it (§10).

**(C) Relational evaluation, narrowly.** Annotate an edit and its intended
semantic effect; check with a solver (§11), positioned against LGMT.

---

## 4. Contributions, with explicit novelty deltas

| # | Contribution | Closest prior work | What is actually new |
| --- | --- | --- | --- |
| **C1** | **LEXEC-Verify** — LLM-free, fail-closed lowering from the v2 extraction contract to LExec IR v1, bounded reference/FEEL execution, DMN 1.3 emission, and bounded solver queries/proof records | ContractCheck (manual blocks, one SPA); PolicyGuard (Z3, contract-vs-policy review); Graus (executor, no solver checking) | Potential contribution: provenance-preserving compilation plus explicit refusals and machine-checkable proof obligations for LLM-extracted rules. **Implemented; corpus correctness and independent-engine evidence pending.** |
| **C2** | **Instrument validation** — do artifact-free signals predict gold-artifact OE, with sOE as a positive control and random, biased, permuted, and leakage-canary controls? | None found under the bounded §21 search protocol | The primary empirical contribution if the frozen study is valid. **Harness/statistics implemented; observation bundle unrun.** |
| **C3** | **Assumption-explicit analysis** — typed, provenance-bound assumptions analyzed individually and as sets, with solver witnesses and human source-support review | *Know Your Limits* documents the gap and names assumption-surfacing tools as future work | Potential contribution: connects formal consistency to source support without claiming that solver validity establishes legal admissibility. **Analyzer implemented; human study unrun.** |
| **C4** | **LEXEC-Bench contracts** — Dutch anchor plus bounded ContractNLI transfer, with gold isolation, frozen splits, retained run manifests, and explicit release roles | LegalBench; PrivacyGLUE; ObliQA; ContractEval; RuleArena | Potential contribution: artifact-level, extensional evaluation with a validated instrument. **Infrastructure implemented; no claimable benchmark bundle yet.** |
| **C5** | **Source-preserving CEGIR** *(extension)* | LLM-CEGIS repair; Logic-LM self-refinement | Counterexamples from cross-rule consistency with deletion/no-op/oracle-withheld controls and provenance preservation. **Implemented; real comparison unrun.** |
| **C6** | **Solver-reward training** *(optional, provider-gated)* | RLVR for SQL, IE, and structured output | Solver feedback over an extracted artifact's denotation, guarded by independent coverage, held-out signals, and adversarial degenerate policies. **Reward contracts implemented; training frontier unrun.** |

---

## 5. Formal setup

**Objects.** Document *d*; extraction *R* = *f*(*d*); total lowering
*λ*(*R*) = *I* or an explicit refusal, where *I* is LExec IR v1; backend
*γ*; artifact *A* = *γ*(*I*) with semantics ⟦*A*⟧. The existing v2 rule JSON
is an extraction contract and compiler input, **not** the executable IR.

**Rules.** The v2 input contract permits a wider surface language. LExec IR v1
normalizes supported rules into typed symbols (`bool`, `int`, `real`, `enum`,
`string`), recursive formulas, explicit scope, per-effect modality, explicit
exception readings, typed assignments, and proof-bound decision tables. Date,
duration, list, open-domain, malformed, and other unsupported constructs are
refused with stable reason codes and `requires_review: true`; they are never
silently projected. The structural contract is
`plan/lexec-ir-v1.schema.json`; the semantic contract is
`docs/ir-semantics-v1.md`.

**Defeater semantics.** The contract keeps `exceptions` separate from
`condition_logic` and never specifies the combination. In the one run available,
**155/352 rules carry exceptions and 125 of those introduce variables absent
from the condition** *(measured)* — so the reading changes the compiled input
signature, not just the logic. We fix:

> ⟦*r*⟧ ≡ *C* ∧ ¬( ⋁_{x ∈ X} *x* )

Exceptions are **defeaters**. This is the reading Defeasible Deontic Logic and
LegalRuleML are built around (LegalRuleML Core v1.0, OASIS Standard, 30 Aug 2021,
models defeasibility, deontic operators, and norm classification explicitly),
and it is the weakest commitment consistent with how legal exceptions read. The
alternatives (independent single-predicate exceptions; conjunctive exceptions)
are **pre-registered as the empirical comparison**, decided by vector replay and
by LEXEC-Perturb's defeater-insertion relation — not by assertion.

**Worked example** (NDA, abbreviated):

> *"Recipient shall not disclose Confidential Information to any third party for
> a period of three (3) years from the Effective Date, provided that disclosure
> compelled by judicial order shall not constitute a breach."*

```
variables:  disclosure_to_third_party    : boolean (input)
            years_since_effective_date   : number  (input, years)
            compelled_by_judicial_order  : boolean (input)
            breach_of_confidentiality    : boolean (output)
condition:  all[ disclosure_to_third_party == true,
                 years_since_effective_date <= 3 ]
exceptions: [ compelled_by_judicial_order == true ]      # defeater
outcomes:   breach_of_confidentiality = true
hit policy: UNIQUE
```

One DMN row after defeater negation (`true`, `<= 3`, `false` → `true`); SMT
assertion `(=> (and dttp (<= yse 3) (not cbjo)) breach)`. The ContractNLI
hypothesis *"Receiving Party may share some Confidential Information with third
parties"* becomes an entailment query — **and, per §1.2, one that needs an
explicit assumption record to be gradable against the corpus label.** See §10.

**Input fragment and implemented compiler subset.** v2 defines **8 operators**, **1 output
operator**, **8 variable types** (`number`, `boolean`, `enum`, `date`,
`date_time`, `duration`, `string`, `list`) and **10 value types** — the variable
types plus `range` and `variable_reference` *(verified-in-code:
`utils/rule_contract.py`)*. v2 of this proposal said "7 value types" and then
called the fragment linear arithmetic. Both were wrong.

The implemented v1 subset supports booleans, bounded integer/real values,
finite enums, and bounded string predicates covered by the conformance suite.
It implements total, fail-closed lowering, an ignored-field ledger, global
symbol validation, and explicit proof/unknown/refusal records. It does not
claim complete temporal, duration, list, open-string, open-interval, or general
SMT semantics. The expressiveness census must therefore report both successful
coverage and refusal reasons; backend agreement cannot expand the language.

---

## 6. Propositions

**P1 (Compilation soundness).** Under §5's defeater semantics, DNF expansion of
*C* ∧ ¬(⋁*X*) into rows, with the hit policy assigned per P2, denotes exactly
⟦*r*⟧ on the declared domain.

**P2 (Hit-policy assignment is a proof obligation).** *Revised per §24 R5 —
v2's "downgrade to FIRST" was not semantics-preserving.* UNIQUE is admissible
iff rows are pairwise disjoint (an unsatisfiability check per pair; NP-complete
propositionally, practical at observed sizes — **87.5% of rules expand to a
single row, worst case 7** *(measured)*). When rows provably overlap, `FIRST`
picks an answer **by row order, and row order has no legal meaning** in this
setup; recording the downgrade does not make the choice sound. The corrected
rule:

| Proof obligation discharged | Admissible policy |
| --- | --- |
| rows pairwise disjoint | `UNIQUE` |
| rows overlap **and** outputs provably equal on the overlap | `ANY` |
| a source-backed precedence or defeater relation exists | `PRIORITY` (or `FIRST` **only** where the source itself orders the rules) |
| rows overlap, outputs differ, no source-backed precedence | **refuse, and preserve the conflict as an unresolved finding** |

The **42 rules** that v2 would have silently downgraded *(measured)* become a
measured refusal-or-`ANY` population, and the split between those outcomes is
itself a reportable number.

**P3 — WITHDRAWN AS STATED, restated as a restricted conjecture (§24 R6).**

v2 claimed that endpoints plus one interior point per cell distinguish an
interval table from *any other* in the class. **That is false.** A candidate can
insert a new threshold strictly between a sampled interior point and an endpoint,
agree on every certificate point, and differ everywhere else. The claim is
withdrawn.

**P3′ (restricted, and a comparison theorem — not a test-generation theorem).**
Fix a finite threshold set *T* known to bound both tables. Then a suite covering
every cell induced by *T*, with open/closed endpoints handled explicitly and
ties resolved, distinguishes any two tables in that restricted class.

The refinement the review did not state, and which matters more than the fix:
**P3′ requires knowing the candidate's thresholds, which you do not have at
test-generation time.** So P3′ is useful for *comparing two known tables*
(regression testing, equivalence checking, differential testing of two compiler
backends) and **not** for certifying an artifact against an unknown reference. It
therefore cannot replace exhaustive enumeration for §9's instrument validation.

**Consequences, applied throughout:** exhaustive enumeration is retained (§9
follows Graus's 13,080-input protocol); the contract's `boundary_condition`
vectors are demoted from "verification certificate" to "test-suite reduction
hypothesis," to be measured, not assumed; and P3′ needs tests for ties,
open/closed bounds, multiple dimensions, missing/default outputs, and
non-interval predicates before it is used for anything.

**The existing checks are weaker still** *(verified-in-code)*:
`utils/readiness.py::_test_vector_boundary_reasons` requires only that **at least
one** numeric input appear in **at least one** `boundary_condition: true`
vector; and `agents/agent_09_grounding_verifier.py::_verify_test_vector` is
documented in its own docstring as "a referential-integrity check, not an
arithmetic one: it does not evaluate condition_predicates against the vector's
inputs." Nothing in the repo currently executes a test vector.

**P4 (Determinism, not correctness — scope corrected per §24 R7).** A compiled
artifact's answers are consistent with a single function **by construction, and
only once** (a) compilation succeeded, (b) the artifact denotes a total
deterministic function on the queried domain, and (c) the compared queries are
extensionally equivalent. Partial artifacts, `COLLECT` tables, preserved
conflicts, abstentions, and two differently-encoded spellings of the same query
each make CQI undefined or nonzero.

**And a deterministic-but-wrong program earns the same CQI advantage**, so CQI
is *not* a correctness metric and cannot be an unconditional contribution. It is
reported as a **reliability/cost property conditional on successful
compilation**, always paired with AFS/sOE and EY, never alone. Reporting it requires
first defining query equivalence classes, abstention handling, multi-valued
output handling, and the baseline's consistency protocol (§26 STAT-3).

---

## 7. What the solver must decide

| Check | Query | Role |
| --- | --- | --- |
| Row disjointness | `UNSAT(row_i ∧ row_j)` | UNIQUE-safety (P2) |
| Subsumption | `UNSAT(C_a ∧ ¬C_b)` | **semantic dedup**, replacing the pipeline's text-similarity dedup |
| Equivalence | `UNSAT(⟦A₁⟧ ⊕ ⟦A₂⟧)` | metamorphic invariance (§11); round-trip checks |
| Co-firing conflict | `SAT(C_a ∧ C_b ∧ O_a ≠ O_b)` | contradictory obligations; **returns the witness** CEGIR needs |
| Coverage gap | `SAT(¬⋁_i C_i)` under σ | unhandled scenarios; audit-relevant |
| Vacuity | `UNSAT(C_r)` | a rule that can never fire = extraction error |
| Entailment | `UNSAT(⟦A⟧ ∧ ¬h)` | query modes (§8), with assumptions per §10 |

Contrast with prior art: ContractCheck does conflict detection from a *manual*
encoding of one contract type; PolicyGuard uses Z3 to review contracts *against*
external policies; Graus has an executor but **no solver layer at all**. We found
no prior work running these seven checks over LLM-extracted rule sets at corpus
scale (§21 search protocol), and the per-100-rule defect densities they yield are
a measurement of extraction quality needing no human and no gold — **provided the
denominator is honest**, which §12.4 D-2 shows it currently is not, and provided
the reward-hacking paths in §12.2 are closed before the density is optimised
against.

---

## 8. LEXEC-Bench — two corpora committed, four held in reserve

**Corrected for consistency (this pass).** v3's header said "six resources" while
§4's C4 row, §17's cut list, and the TL;DR all said the benchmark is scope-cut to
two corpora. The table below now marks each resource **COMMITTED** or
**RESERVE**; only committed resources may appear in a headline claim, and reserve
resources return only if their gate passes early (§17).

| Resource | Status | Scale (verified) | Mode | Gold |
| --- | --- | --- | --- |
| **Dutch DMN corpus** (Graus, ICAIL 2026, CC BY 4.0) | **COMMITTED** | 95 production DMN models + legal text; 58 executable; harness included | **Gold-artifact anchor** | Real DMN + outcome equivalence |
| **ContractNLI** (Koreeda & Manning, Findings EMNLP 2021) | **COMMITTED** | 607 NDAs × 17 hypotheses, 3-way labels + evidence spans | Entailment (assumption-explicit, §10) | Expert labels; **plus 400/610 strict-entailment re-annotations from arXiv:2606.16118 if obtainable** |
| **CUAD** (Hendrycks et al., NeurIPS D&B 2021) | RESERVE | 510 contracts, 41 categories, 13k+ spans, 20,910 QA pairs | Presence/value | `master_clauses.csv` normalized answers |
| **OPP-115** (Wilson et al., ACL 2016) | RESERVE | 115 policies, 3,792 segments, ~23k practices | Practice decision | Consolidated majority-vote annotations |
| **MAPP** (Arora et al., LREC 2022) | RESERVE | 64 EN (292k words) + 91 DE (478k words); 8k + 19k practices; GDPR/CCPA-aware scheme | Practice decision, **cross-lingual** | Bilingual annotations |
| **ObliQA / RegNLP** (arXiv:2409.05677) | RESERVE | 27,869 obligation-centric questions over ADGM financial regulation (40 docs, ~640k words) | Obligation entailment | Question–passage pairs; RePASs contradiction metric |

**Scenario mode** (fact bindings). v3 sourced these partly from "solver-generated
boundary bindings **per P3**" — but **P3 is withdrawn** (§6), so that clause is
removed. Corrected sources, in decreasing order of trust: ~500 **human-authored,
source-grounded scenarios** on a stratified sample with reported inter-annotator
agreement; **exhaustive or solver-enumerated bindings** over the declared input
domain (no completeness claim attached — see §6 P3′); and the rules' own
`source_attested` test vectors, used **only** as a diagnostic and never as a
reward or a headline, because they are generated by the same extraction pass they
would be scoring (§12.2).

**Positioning against existing suites, explicitly.** LegalBench (162 expert-built
tasks) and PrivacyGLUE (7 tasks: OPP-115, PI-Extract, Policy-Detection,
PolicyIE-A/B, PolicyQA, PrivacyQA) evaluate *labels and spans*. ContractEval
(NLLP 2025, arXiv:2508.03080) scores clause-level risk on CUAD across 4
proprietary + 15 open models and even measures "laziness" (spurious "no related
clause"), which is an abstention metric precedent worth borrowing. None of them
evaluates an *artifact's behavior*. That is the gap, and it is a narrow, true
claim.

**Contamination.** CUAD, ContractNLI, OPP-115, and the Dutch corpus are public
and pre-cutoff. Mitigations: report LEXEC-Perturb separately (new text); include
a post-cutoff held-out corpus; run a memorization probe. Prior art warns this is
real — "Knowledge-Driven Hallucination in LLMs: Process Modeling"
(arXiv:2509.15336) documents models overriding the given text with prior
knowledge; "Pervasive Annotation Errors Break Text-to-SQL Benchmarks"
(arXiv:2601.08778) is a reminder to audit borrowed gold before trusting it.

---

## 9. Instrument validation — the primary contribution

*Rewritten twice: per §24 R8 (which was right on every fact), and again per the
second-pass §14 P1, which showed the central metric was misnamed. §9.2 explains
the redefinition; it is the most important correction in this document.*

**The question.** Every gold-free extensional metric assumes that agreeing with
query answers means having built the right artifact. We found no prior work that
tests this assumption (§21 states the search protocol; this is a bounded
absence claim, not a "nobody has"). The Dutch DMN corpus makes it testable
because it has both the artifact and the behavior.

### 9.1 The question

Every extensional metric assumes that agreeing with query answers means having
built the right artifact. We found no prior work testing that assumption (§21
states the search protocol and its limits; this is a bounded absence claim). The
Dutch DMN corpus makes it testable because it is the one public resource holding
both the gold artifact and its behavior.

**§9.2 then shows the metric v3 proposed for this test was not the metric it
claimed to be.** Read §9.2 before §9.3.

### 9.2 The metric was misnamed, and that changes the contribution

*Second-pass review §14 P1 is correct, and it is the deepest finding in either
review.* §13 defined DA as `E_q[1(⟦A⟧(q) = gold(q))]`, and §9.3 obtained
`gold(q)` by **executing the gold DMN model**. So the quantity was never
gold-free: it is a *sparse, gold-labeled* estimate of the same thing OE measures
exhaustively. Correlating the two would mostly have tested whether one
gold-labeled sample approximates another gold-labeled sample — a
sample-sufficiency question, not an instrument-validity one — and it could never
have licensed "results on corpora without gold artifacts inherit credibility."

**The fix, and it makes the contribution better rather than smaller.** The
equivocation was on the word *gold*. Separate two things that were conflated:

| Term | Definition | Available where |
| --- | --- | --- |
| **sOE** — sampled outcome equivalence | agreement with the gold **artifact**, measured on a sampled query set instead of the exhaustive one | only where a gold DMN exists (Dutch) |
| **OE** | agreement with the gold **artifact** over the exhaustive input set | only where a gold DMN exists (Dutch) |
| **AFS** — artifact-free signal | any score computed **without ever touching a gold formal artifact**, whether or not it uses labels | everywhere |

"Artifact-free" is the property that actually matters, because the thing no
corpus has is a gold *formalization* — not a gold *label*. Three AFS instruments
qualify, and all three already exist in this proposal:

1. **Expert-label entailment** — ContractNLI's 17 hypotheses per NDA with
   three-way expert labels (§8). Labels, but no artifact.
2. **Metamorphic relations** — LEXEC-Perturb (§11). Needs neither artifact nor
   label, only an annotated *relation*, and it is checked by SMT equivalence.
3. **Human-authored source-grounded scenarios** — a stratified expert-labeled
   scenario set (§8).

**C2 restated.** *Do artifact-free signals predict artifact-based outcome
equivalence?* With **sOE as the positive control** (it should track OE well — if
it does not, the sampling is broken and nothing else is interpretable) and
**random, stratified, and deliberately-biased query samples as negative
controls** (a high correlation must be attributable to the AFS, not to the mere
act of sampling).

**Consequence that partially reverses the scope cut.** LEXEC-Perturb was demoted
to "most expendable" in §20 Plan D on the grounds that LGMT overlaps it. Under
the corrected framing it is the **only AFS that requires no new expert labels**,
so it moves back onto the critical path. That is a real cost — see §17 — and it
is the price of having a coherent primary claim.

### 9.3 The anchor study's actual protocol, and the baseline that does not exist

Verified against arXiv:2604.17153 directly *(published)*:

| Fact | Value | Consequence |
| --- | --- | --- |
| Models released | 95 | 37 lack alignable interfaces |
| Models used for outcome equivalence | **58** = 24 Outcome + 34 Requirements | our n for the primary endpoint |
| Input types | 24 Outcome models are **boolean-only, ≤10 inputs** (2^n enumeration). The **34 Requirements models require string-typed inputs**: categorical strings tested with `contains()`, binned numeric strings, and null-check strings | **see §9.4 — this is a blocker, not a detail** |
| Testable input variations | **13,080**, exhaustive | P3′ cannot replace enumeration (§6) |
| Runs per condition | **5** independent runs; 1,900 generations (95 × 4 × 5) | all runs retained |
| **Conditions with OE reported** | **only `Text+io` and `Text+srl+io`** — verbatim: *"We limit ourselves to the io and srl+io conditions, as these have consistent inputs and outputs, enabling direct comparison."* | **there is no published raw-`text` OE baseline at all** |
| 42.6% / 60.4% | `Text+srl+io`, **macro-averaged over 5 runs** | not a "best condition, 1-shot" figure |
| 33% full / 50% ≥90% | **best-run per model** (19/58, 29/58) | a different estimator; never compared to a mean |
| `+io` interface specs | **derived from the gold models** | a gold-leaking condition |

**The comparison v3 designed does not exist.** §9.4 of v3 promised "raw-text vs.
Graus's `text`" as the honest headline. The anchor reports no OE for `text`,
because that condition produces no alignable interface. So the only conditions
with a published OE number are both gold-leaking, and a raw-text run of ours has
**nothing published to be compared against**.

Three options, and the choice is preregistered before any run:

1. **Report our raw-text OE as a standalone number** with no comparison claim,
   and compare only within our own information conditions. Honest; weaker.
2. **Define an interface-alignment intervention that does not use gold** — derive
   the I/O signature from the source text alone, publish the derivation, and
   report OE for it. Then our `self-derived-interface` number is comparable to
   the anchor's `+io` *only if* we also report how often our derived signature
   matches the gold signature. This is the interesting option and it becomes a
   measured sub-result: **interface-derivation accuracy**.
3. **Reproduce the anchor's `+io` condition exactly** and claim only a
   gold-leaking comparison, clearly labeled.

We will do (1) and (2), and (3) only as a reproduction check (§17 G1).

### 9.4 The string theory is a statistical blocker, not an implementation detail

The plan's proposed IR subset is `{bool, int, real, enum}`, refusing `string`.
Applied to the anchor corpus that **refuses all 34 Requirements models** — 59% of
the testable set, and the half where the anchor scores *higher* (60.4% vs.
42.6%). The primary endpoint would then run at **n = 24**.

That is not survivable, and the arithmetic is elementary (Fisher-z,
se = 1/√(n−3)):

| n | 95% CI for a true ρ = 0.6 | Power vs. H₀: ρ ≤ 0.3 |
| --- | --- | --- |
| 24 | **[0.26, 0.74]** — lower bound **below** the declared 0.3 threshold | **54%** |
| 58 | [0.40, 0.74] | **88%** |
| 95 | [0.45, 0.72] | 98% |

**At n = 24 the study fails its own declared success criterion even when the
true effect is exactly the target.** So a string theory covering `contains()`
substring predicates, binned-numeric strings, and null-checks is a **G0
deliverable**, not an IR-2 measurement — and note that a naive string→enum
normalisation is *not* sound for `contains()`, which is a substring test rather
than equality. Neither prior review reached this; it is the single most
schedule-relevant correction in this pass.

### 9.5 Preregistered analysis plan (corrected)

- **Estimand.** Spearman ρ between a per-model **AFS score** and a per-model
  **OE**, on the 58 testable models. One number per model per run.
- **Sampling unit.** The decision model. Queries are nested in models; runs are
  repeated measures.
- **Aggregation — the incoherence in v3 is fixed.** v3 said "per-model Spearman
  pooling all runs" *and* "mixed-effects with a random intercept per model."
  Those are incompatible: aggregating to one value per model leaves no run-level
  residual for the random intercept. **Resolved:** the primary estimate is
  computed on the **run-level observation table** (58 models × 5 runs = 290 rows,
  minus refusals), with a **cluster bootstrap resampling models** (not rows, not
  runs) for the CI, and a mixed-effects model on Fisher-z-transformed per-run
  correlations as a sensitivity check — reported as sensitivity, never as the
  headline.
- **Null and power — also corrected.** v3 powered against ρ = 0 while declaring
  success as "ρ ≥ 0.6 with CI lower bound > 0.3." The relevant null for that
  decision rule is **H₀: ρ ≤ 0.3**, one-sided. Power at n = 58 against a true
  ρ = 0.6 is **≈88%** (table above). ρ = 0 is not tested; it is not the decision.
- **Ties, bounds, and missingness.** Both AFS and OE are bounded proportions with
  ties and unequal query counts. Spearman handles ties by mid-ranks; we report the
  tie fraction, and pre-declare that if >20% of models tie at 0 or 1 the primary
  estimator switches to a censored-data alternative (declared now, not after
  looking). Refusals are **not** imputed — they are a separate reported stratum.
- **Attenuation.** Both variables are measured with error, which biases ρ toward
  zero. We report a disattenuated estimate using the between-run variance as the
  reliability estimate, **as a secondary number**, and never as the headline.
- **Negative and positive controls.** Positive: sOE. Negative: equal-size random
  samples, stratified random samples over the gold interface, and deliberately
  biased samples. A high ρ that the negative controls also achieve is not
  evidence for the instrument.
- **Run retention.** All runs retained. Best-of-*k* labeled and compared only to
  the anchor's own best-of-5.
- **The 37 excluded models** are an explicit reported exclusion, plus whether our
  pipeline can produce artifacts for any of them (an interface-adequacy result).
- **Disagreement review.** Structured false-positive (AFS high, OE low) and
  false-negative analysis with a taxonomy.

### 9.6 Information isolation, not an assertion

v3's leakage "guard" was a subprocess whose working directory could not reach
`gold_models/`. That is not a boundary: absolute paths, parent traversal,
symlinks, and environment variables all defeat it (second-pass §14 P8, correct).
Replaced with an actual information boundary:

1. Query generation runs in a **separate checkout or container** with only an
   allow-listed, **content-addressed source packet** mounted read-only. The gold
   files are *absent from the mount*, not merely unreachable by convention.
2. The result crosses a **one-way artifact boundary** to a distinct labeler
   process that has gold and no ability to influence generation.
3. Denial is **tested adversarially**: absolute paths, `../` traversal, symlinks,
   env-var indirection, and manifest-declared paths must all fail.
4. v3's "threshold-coincidence audit" is dropped: legal text and gold DMN
   *should* share numbers, so coincidence is not evidence of leakage. Replaced
   with **information-flow provenance** — every query records the source spans it
   was derived from, and any query without a source-span derivation is rejected.

### 9.7 Why this is the paper's spine

If artifact-free signals track artifact-based OE, results on corpora with no gold
formalization inherit *bounded* credibility — bounded by the anchor's single
jurisdiction, language, and statute (§21 states this limit). If they do not, that
is a finding that should change how the subfield evaluates itself. Both outcomes
are publishable, but **"metric failure is publishable" is a contingency, not an
acceptance argument**, and G3 proceeds to a negative finding only after the
leakage, precision, power, and protocol-validity gates pass — an *invalid or
uninformative* estimate is not evidence of low association.

---

## 10. Assumption-explicit compilation

**The problem, measured by others.** ContractNLI's gold labels reflect pragmatic
legal interpretation; **71 entailment cases become neutral** under strict formal
entailment *(published, arXiv:2606.16118)*. Graded naively, the entailment mode
punishes an artifact for being *more* rigorous than the annotator.

**Novelty delta, narrowed per §24 R10 — which was right, and I verified it.**
arXiv:2606.16118 §5.6 (Future Work) already proposes "surfacing Minimal
Correction Subsets (MCS) via SMT solvers and presenting them to legal
practitioners as structured entry points," defining an MCS as "the minimal set of
axioms whose acceptance would shift the classification from Neutral to Entailment
or Contradiction" *(published, quoted verbatim)*. **So assumption surfacing and
minimal correction are not new here.** What is left is narrow and must be stated
that way: a *document-level, provenance-bound implementation and evaluation* —
assumptions typed, tied to cited source spans, admissibility-checked, and scored
at corpus scale — rather than the concept.

**The fix.** The artifact answers with a pair — a verdict *and* the minimal
assumption set it needed:

```
query   : "Receiving Party may share some Confidential Information with third parties"
verdict : ENTAILED under assumptions { third_party ⊑ permitted_recipient,
                                       written_consent_obtainable = true }
strict  : NOT ENTAILED
```

**Metrics — and what each does *not* prove** (§24 R10):

- **Assumption-free accuracy** — strict entailment vs. re-annotated strict labels.
- **Assumption-augmented accuracy** — accuracy against original pragmatic labels
  when the artifact may declare assumptions.
- **Deletion-minimality** — drop each assumption and re-check; if the verdict
  survives, it was padding. **This proves deletion-minimality relative to one
  formalization. It does *not* prove minimum cardinality, uniqueness, legal
  permissibility, consistency with background law, or source grounding** — and a
  model can still add a single decisive assumption that is equivalent to the
  hypothesis it wants. Minimality alone is therefore *not* a sufficient guard.

**What has to be built for the guard to be real** (§26 ASM-1..4):

1. A **typed assumption language** with a closed set of admissible forms
   (subsumption between defined terms, default value for an unstated parameter,
   temporal default, party-role identification) — not free-form propositions.
2. An **admissibility policy**: an assumption must be *entailment-weaker* than the
   hypothesis it supports. Reject any assumption *A* where `⊨ A → h`; this is the
   solver-checkable version of "don't assume the conclusion," and it is the check
   that actually closes the hole minimality leaves open.
3. **Provenance:** every assumption cites the source span that motivated it, or is
   marked as background-law, which requires review.
4. A **human-review protocol** on a stratified sample, reporting the rate at which
   legal reviewers judge declared assumptions admissible — because permissibility
   is not solver-decidable.

---

## 11. LEXEC-Perturb, narrowed

~1.5–2k clause-level perturbation pairs, each labeled with a metamorphic
relation, never a target artifact.

**Meaning-preserving (invariance):** paraphrase; active↔passive;
legalese↔plain; clause reordering; splitting/merging; defined-term substitution;
unit-preserving numeric restatement ("three years" ↔ "36 months"); redundant
(already-implied) defeater insertion. Required: ⟦γ(f(d))⟧ ≡ ⟦γ(f(π(d)))⟧, checked
by SMT equivalence — not string similarity.

**Meaning-changing (directional refinement — the emphasis, post-LGMT):**

| Edit | Required relation |
| --- | --- |
| scope tightening | `SAT(σ_old ∧ ¬σ_new)` ∧ `UNSAT(σ_new ∧ ¬σ_old)` |
| threshold shift | decision boundary moves in the named direction |
| modality flip (shall→may) | obligation becomes permission (output *role* changes) |
| defeater addition | firing set strictly shrinks |
| negation insertion | outcome flips on the affected region |
| cross-reference redirect | the dependency edge moves |

**Position against LGMT explicitly.** LGMT (arXiv:2605.23965) derives MRs from
FOL equivalences and checks *answer* consistency on reasoning problems. Here the
perturbation is applied to a *real normative document*, the object checked is a
*compiled artifact*, and the interesting half is *refinement* rather than
invariance. That is the whole delta, and the paper should say so in one sentence
rather than dressing it up.

**Scoring.** **SDI = SR + SE − 1** (Youden's J): invariance rate plus
correct-change rate minus one. A constant model scores 0; a noisy model scores 0.
One number, gameable in neither direction.

**Annotation cost.** Write an edit, pick a relation from a closed list — no logic
required. ~2–4 min/item → ~120–160 annotator hours with 20% double annotation.

**Licensing.** OPP-115 and MAPP carry no redistribution grant. Ship **edit
scripts and offsets**, never derived text — the posture
`benchmarks/datasets.json` already takes.

---

## 12. Method

### 12.1 CEGIR — counterexample-guided iterative repair

```
R₀ ← f(d)
loop k = 0,1,2,…
    A ← γ(R_k)                          # deterministic compile, no LLM
    W ← Solve(A)                        # conflicts, vacuity, gaps, vector replay,
                                        #   train-split gold-query disagreements
    if W = ∅ → return A
    R_{k+1} ← f_repair(R_k, W, d)         # repair prompt carries the CONCRETE binding
```

The repair prompt carries a witness: *"under `loan_amount = 250000, occupancy =
investment`, rules R-014 and R-031 both fire and assign `max_ltv` to 80 and 75 —
here are both cited clauses."* Report accuracy and yield vs. round *k* and the
token cost per round; expect diminishing returns by *k* = 3 *(target)*.

**Novelty, honestly bounded.** CEGIS-with-LLMs is established: MaxSAT-localized
counterexample-guided program repair (AAAI 2025, arXiv:2502.07786; 1,431 student
programs), Logic-LM's solver-error self-refinement, SCAFFOLD-CEGIS,
property-guided synthesis for planning. The delta here is the *source* of the
counterexample: not an external specification or a test suite, but
**cross-rule inconsistency inside a single extracted artifact** — a signal that
only exists because the extraction target is a rule *set* over shared variables.
The required ablation is witness vs. no-witness repair prompts.

### 12.2 Solver-reward RL, narrowed

GRPO-style RL on an open-weight model (8–14B dense, or LoRA on ~32B) with a
composite programmatic reward:

```
r =  w₁·1[compiles]
   + w₂·(fraction of test vectors replayed)
   + w₃·1[no unresolved SMT conflict]         # solver, not a model
   + w₄·(provenance precision vs. cited spans)
   + w₅·(decision agreement on train-split gold queries)
   + w₆·(assumption minimality, §10)
   − w₇·(abstention rate)                     # abstaining must not be free
```

**The narrowed claim.** Not "RLVR beyond math and code" — that is taken (§1.5).
The claim is: *RL where the reward is a **solver verdict on the denotation of an
artifact extracted from a long document with no gold artifact**.* RLVR for
text-to-SQL rewards execution against a gold query; for IE, agreement with gold
labels; for structured output, schema validity plus label match; for
autoformalization, prover success on a gold theorem statement. Here there is no
gold artifact, no gold label for the artifact, and the reward is *internal
logical consistency plus behavioral agreement*. Wang et al. name exactly this as
future work ("solver-based feedback training objectives for legal-domain LLMs"),
which is both the strongest citation for the gap and the reason to move fast.

**Every component above is hackable, and §24 R9 is right that an abstention
penalty does not close the paths.** Stated explicitly, because a reward this
gameable cannot be presented as "verifiable" without the audit:

| Reward component | How a policy games it | Counter-measure |
| --- | --- | --- |
| `1[compiles]` | emit one trivial rule per document | **coverage reward** (§ below); output-size reporting |
| vector replay | **circular** — the vectors are emitted by the *same* extraction, and nothing in the repo executes them today *(verified-in-code)*. This measures compiler fidelity to a self-generated pair, not fidelity to source | replay only **held-out, independently-authored** vectors; report self-vector replay separately and never as a reward |
| `no SMT conflict` | emit rules over **disjoint symbol sets** so nothing can co-fire | **symbol-reuse rate** as a reported metric and a reward floor |
| low defect density | emit fewer rules | denominator-aware scoring; **omission rate** vs. a reference clause inventory |
| assumption minimality | one decisive assumption ≈ the hypothesis | the entailment-weaker admissibility check (§10) |
| provenance precision | cite the whole document | span-length-penalised precision |

**Required additions before any RL run** (§26 RL-1..4): an explicit **coverage /
completeness reward** measured against a source-clause inventory that the policy
did not produce; **held-out, source-grounded queries and evidence spans**
authored outside the training loop; and a **standing adversarial reward-hacking
test suite** — degenerate policies (empty artifact, constant output, disjoint
symbols, single-rule-per-document) that must score *worse* than an honest
baseline, run as a gate on every reward change. **Never train and evaluate on the
same solver-derived witnesses.** Report every reward component, the Pareto front,
output size, symbol reuse, and omission rate — not the scalar.

Abstention is priced, which makes selective prediction a trade-off the model must
navigate — then measured with risk–coverage curves. Note the comparison is
**not** directly to **Grammars of Formal Uncertainty**'s **AUROC > 0.93** on logic
tasks *(published)*: that is a different task, a different metric family, and a
different base rate. We port their PCFG/grammar-entropy *signal* as a baseline
predictor on our task and compare AURC head-to-head on our data (§24 R11).

**Headline target:** an 8–14B open model, solver-reward-trained, exceeds a
frontier prompted model on decision agreement at equal or better coverage
*(target)*.

### 12.3 Where this repository already sits

| Capability | Implementation evidence | Scientific evidence boundary |
| --- | --- | --- |
| v2 extraction contract, readiness/remediation, grounding, DAG partition | `utils/rule_contract.py`; agents 07–10; provider-free tests | Engineering invariants only; LLM grounding remains model-dependent and failures stay review-visible |
| Full source-chunk extraction | `PIPE-1/2`; `chunk_coverage.json`; regression tests | Proves read/byte coverage, not semantic rule recall |
| v2-aware optimizer handoff | `PIPE-3`; optimizer handoff tests | Restores input context; does not prove dependency accuracy |
| Semantic rule-recall evaluator | `utils/rule_recall.py`; `results/aggregates/rule_recall.json` | `fixture_only`; needs a licensed stratified frame, two independent annotators, adjudication, weights, and agreement |
| Dependency audit | `utils/dependency_audit.py`; `results/aggregates/dependency_audit.json` | `fixture_only`; needs real positive/negative edge labels and human adjudication |
| Canonical compiler IR and total lowering | `plan/lexec-ir-v1.schema.json`; `docs/ir-semantics-v1.md`; `utils/lexec_ir.py` | Implemented bounded subset; full-corpus expressiveness and refusal distribution not established |
| Reference/FEEL evaluator, DMN 1.3 emitter | `utils/feel.py`; `utils/dmn_builder.py`; `utils/dmn_emit.py` | Local conformance passes; a pinned independent engine run is still required |
| Bounded solver queries and hit-policy proof obligations | `utils/smt.py`; solver/query/proof tests | Intentionally not a complete native SMT backend; unknown/timeout/open-domain cases do not pass |
| Dutch anchor audit, split, replay, and harness | `bench/adapters/dutch_dmn.py`; `bench/splits/dutch_58.json`; `bench/anchor_replay.py` | Replay completed but disagrees with released metrics on 792/1,900 rows; no paper claim until root-caused |
| Gold isolation, manifests, bundles, estimators | `bench/queries.py`; `bench/manifest.py`; `bench/run_bundle.py`; `bench/stats.py` | Contracts exist; no claimable J1/G3 run bundle has been collected |
| Perturbation, assumptions, CEGIR | `bench/perturb.py`; `utils/assumptions.py`; `compiler/cegir.py` | Implemented and tested; real annotations/observations remain `unrun` |
| Reward components, held-out signals, frontier reporting | `training/` and reward-hacking tests | Provider/GPU-gated; no training result exists |
| Interactive review workbench | `ui/` with pipeline/stage, rule, evidence, graph, comparison, diagnostics, and review views | Review/observability infrastructure; useful for adjudication and demos, not a scientific result |

The current checkout passes 1,051 core Python tests, the plan validator, the G0
artifact validator, and the research-artifact overclaiming guard. These establish
implementation quality. They do not establish extraction accuracy, compiler
correctness on a real corpus, instrument validity, transfer, or training gains.

### 12.4 Resolved engineering defects and active evidence blockers

The two defects identified in v3 are resolved in code:

- **D-1 resolved (`PIPE-1/2`).** Every source chunk is processed, oversized
  chunks are re-split, coverage is recorded, and silently dropped bytes fail the
  contract. The retained privacy-policy run processed 1,260 chunks in 231/231
  batches with zero dropped bytes. This is an exploratory operational run, not
  a semantic-recall estimate.
- **D-2 implementation resolved (`PIPE-3`).** Optimizer prompts receive complete
  v2 predicates, logic, outcomes, scope, variables, and exceptions. Dependency
  correctness is still unmeasured on a real frame; `PIPE-4` is only
  `fixture_only` until independent annotation is completed.

The active blockers are now evidence gates, not missing code:

1. root-cause the 792-row Dutch anchor replay mismatch before using released
   or replayed aggregates;
2. complete real PIPE-2B and PIPE-4 annotation frames;
3. run and retain a corpus-scale IR/expressiveness census;
4. cross-check supported DMN cases with a pinned third-party engine;
5. collect J1/J1B observations under the frozen isolation boundary; and
6. execute the G3 instrument study with preregistered controls and clustered
   uncertainty.

---

## 13. Metrics

| Metric | Definition |
| --- | --- |
| **AFS** | **Artifact-Free Signal** — any score computed without touching a gold formal artifact: expert-label entailment, metamorphic relations, or human scenarios (§9.2). **This, not DA, is the primary quantity.** |
| **OE** | Outcome Equivalence vs. gold DMN artifacts, exhaustive input set (Graus protocol; §9.3) |
| **sOE** | **sampled** outcome equivalence — same gold-artifact comparison on a sampled query set. v3 called this "gold-free DA"; it is not gold-free (§9.2). Retained only as the **positive control** |
| ~~DA~~ | **Retired.** The name implied artifact-freedom the definition did not have. Every prior use of "DA" in this document means sOE where a gold artifact exists, and AFS otherwise |
| **EA_strict / EA_assumed / AM** | assumption-free accuracy, assumption-augmented accuracy, assumption minimality (§10) |
| **EY** | Executable Yield: fraction of documents producing a compiled, gate-passing artifact |
| **S@c, AURC** | selective score at coverage *c*; risk–coverage summary |
| **SR / SE / SDI** | invariance rate, correct-change rate, `SR + SE − 1` |
| **PP** | Provenance Precision vs. expert evidence spans (free from ContractNLI/CUAD) |
| **CQI** | Cross-Query Inconsistency — **conditional** on successful compilation, a total deterministic denotation, and extensionally equivalent queries (revised P4, §6). Not 0 unconditionally, and never a correctness metric |
| **VR** | Vector Replay on the *emitted* artifact |
| **Defect density** | solver-detected conflicts / gaps / vacuities per 100 rules |
| **Cost** | USD + tokens to *build* an artifact; USD per query to *use* it |

AFS/sOE and EY trade off, so neither is ever reported alone: every table gives
(score, EY) jointly or a selective risk–coverage curve. **`S-DA@c` is renamed
`S@c`** for the same reason DA was retired.

### 13.1 Statistical analysis plan (§24 R11)

v2 listed a dozen metrics across corpora, model families, target languages,
repair rounds, and ablations, and treated "pre-registered targets" as if that
handled inference. It does not: it addresses neither multiplicity, stochastic
model variance, document clustering, nor best-run selection.

**One primary endpoint.** ρ(**AFS**, **OE**) on the 58 Dutch testable models
(§9.2, §9.5). Everything else is confirmatory or exploratory. *v3 wrote this as
ρ(gold-free DA, gold-based OE); the first term was not gold-free (§9.2).*

**Three confirmatory endpoints**, fixed in advance, with family-wise error
controlled at α = 0.05 by Holm–Bonferroni across exactly these three:

1. **OE** of solver-checked compilation vs. the matched raw-`text` condition —
   **reported standalone**, since the anchor publishes no `text` OE (§9.3).
2. **AFS** of CEGIR vs. no-CEGIR, paired by document.
3. AURC of solver-signal selective compilation vs. the ported grammar-entropy
   baseline.

**Everything else — target-language ablation, cross-domain/lingual transfer,
CQI, cost, defect density, the dissociation studies — is exploratory and labeled
as such in every table.** No exploratory result carries a target. **SDI moves out
of "exploratory": it is now one of the artifact-free signals feeding the primary
endpoint (§9.2), so it is reported as an input to C2, not as a standalone
finding.**

**Aggregation and inference.** Macro-average over documents (never micro over
queries, which would let long documents dominate); document as the unit; ≥ 5
seeds/runs per condition with **all** runs retained; paired tests where the design
is paired; hierarchical bootstrap or mixed-effects models with a random intercept
per document; 95% CIs on every headline number; best-of-*k* figures labeled and
compared only to other best-of-*k* figures. A power/sensitivity analysis on the
58-model primary endpoint is run **before** data collection, and if 58 models
cannot detect ρ ≥ 0.6 at 80% power, that is reported and the design changes.

---

## 14. Experiments and baselines

### 14.1 Required baselines

1. **Prompt-only frontier models**, document → v2 rule set, several families.
2. **The existing 10-stage pipeline, unchanged** — the "does the pipeline earn
   its cost" ablation. It must be allowed to lose.
3. **Graus's four input conditions** on the Dutch corpus (text / +SRL / +I/O /
   +both), reproduced on their harness — a published number to beat.
4. **Direct-to-Python.** Code LLMs are strong here; this baseline may win on the
   decision scores,
   and the paper must say so if it does. The defense is then PP, CQI, and
   standards-compatibility — separately measured.
5. **Direct long-context QA** — the strongest accuracy baseline.
6. **RAG QA** — the industrial default.
7. **Fine-tuned span extraction** (CUAD/ContractNLI-style) for the surface-metric
   arm of C6(b). ContractEval's 19-model CUAD results give a published reference
   point.
8. **Ours, ablated:** −CEGIR; −witness; −defeater semantics (conjunctive /
   ignored); −semantic dedup; −SMT (vector replay only); −assumptions.

**Matched-information protocol (§24 R12).** These baselines do not naturally
receive the same interface, retrieval, context, or execution budget, and the
Dutch `+io` condition is **gold-derived** while a raw-text pipeline is not. So:

- Every system gets the **same source slice** and is run in **declared
  information conditions** — `raw-text`, `self-derived-interface`, and
  `gold-interface` — and is only ever compared *within* a condition.
- **Representation failure is separated from executor failure.** A system that
  produced a sound artifact the backend could not run is counted differently from
  one that produced an unsound artifact. Backend capability and test strength are
  reported per target, and **target-language differences are not interpreted as
  model preferences** until both are comparable.
- **Generated Python is sandboxed** (no network, no filesystem, CPU and wall-clock
  limits, hard timeout) and non-termination is recorded as a distinct outcome — a
  failure mode a bounded decision table cannot have, so the comparison is not
  like-for-like and is annotated as such.
- Both **per-generation** and **best-of-*k*** results are reported for every
  stochastic system.

### 14.2 Target-language ablation

Same extraction → **DMN 1.3 + FEEL**, **SMT-LIB**, **Python**, **ASP/Datalog**
(defeasible-native). Report AFS/sOE, EY, and defect density per target. *Which formal
target can an LLM hit most reliably, and does a defeasible-native
representation help?* — interesting whichever way it lands, and it retires the
"why DMN?" objection. Grounding: Horner et al. target Defeasible Deontic Logic,
LegalRuleML models defeasibility natively, DMN does not.

### 14.3 Compile-then-execute vs. in-context rule application (new)

**RuleArena** (ACL 2025) already measured the failure mode: given 95 real rules
in context and 816 problems across airline/NBA/tax, LLMs "perform poorly,"
confuse similar regulations, botch the arithmetic, and improve markedly with
external math/logic tools *(published)*. Head-to-head: LLM applies rules in
context vs. LEXEC compiles the rule text once and executes deterministically.
This is a cheap experiment on an existing benchmark that isolates exactly what
compilation is supposed to buy, and it is the most direct available answer to
"why not just prompt the model?"

### 14.4 Amortization and consistency

Per document, answer *N* queries under each regime. Compiled: one compile, then
~free solver calls, CQI = 0 by construction. Long-context QA: *N* × (document +
query) tokens, CQI measured. **Report with and without prompt caching** —
caching narrows the gap and a reviewer will raise it, so raise it first. Report
break-even *N*. For ContractNLI's 17 hypotheses the gap is modest; for scenario
sweeps (10³–10⁴ bindings — the actual industrial use) it is ~10²–10³×. The
unconditional claim is CQI; the cost claim is conditional on *N* and stated that
way.

### 14.5 Generalization

- **Cross-domain:** train on one corpus, evaluate on the others. Vocabularies
  barely overlap, and this repo already has evidence that domain coupling fails
  silently (a `rule_type`-keyed BPMN gate produced zero targets for five of eight
  domains until fixed).
- **Cross-lingual:** MAPP's 91 German policies, evaluated through the shared
  formal language.
- **Cross-jurisdiction:** the Dutch corpus is a different legal system, language,
  and document genre from the four English corpora — transfer here is a real
  test, not a courtesy experiment.
- **Cross-task:** clinical guidelines or benefits eligibility, to support "recipe,
  not compliance system." Note that **CPGPrompt** (arXiv:2601.03475) already
  translates clinical guidelines into LLM-executable guidance trees, so this
  transfer has prior art to build on rather than virgin territory.

### 14.6 Expressiveness census — the construct-validity experiment neither review demanded

Nothing in v1–v3 argued that a **decision-table semantics is an adequate model of
normative text at all.** §14.2 ablates target *languages* against each other, but
if all four targets are inexpressive in the same way, the ablation is a
comparison among equally wrong choices. And the IR (§5) *refuses* deontic
modality, temporal validity, open-ended defeasibility, and vagueness — which is
honest, but it means the pipeline is silently scoped to whatever survives those
refusals.

**The experiment, and it is cheap because it needs no model calls.** On both
committed corpora, classify every source obligation/clause by whether a
decision-table semantics can express it at all:

| Category | Expressible in DMN + bounded FEEL? |
| --- | --- |
| threshold / eligibility conditions | yes |
| enumerated categorical conditions | yes |
| fixed-set defeaters | yes (as `C ∧ ¬⋁X`) |
| deontic modality (obligation vs. permission vs. prohibition) | **no** — no modality in the target |
| temporal validity / effective dates / supersession | **no** — needs a temporal theory |
| open-textured standards ("reasonable", "material") | **no** |
| cross-document or cross-clause reference resolution | partially |
| discretionary authority ("the Minister may determine") | **no** |

Report the fraction of source content in each bucket. **This number bounds every
other result in the paper**, and publishing it is the difference between "we
evaluate document understanding" (unsupportable) and "we evaluate the
decision-table-expressible fraction of normative content, which is X%"
(supportable, and interesting in its own right). If X turns out small, that is
itself the most useful finding the project could produce — and it should be
measured in G0, not discovered in April.

---

## 15. Pre-registered headline table

Now anchored to *published* numbers rather than invented ones.

| Result | Reference point (published) | Target |
| --- | --- | --- |
| Outcome equivalence, Dutch corpus (Outcome / Requirements) | **42.6% / 60.4%** — Graus `Text+srl+io`, **macro-averaged over 5 runs**, and a **gold-leaking** condition (I/O specs from the gold models). **No raw-`text` OE baseline exists** (§9.3) | **≥ 55% / ≥ 70%** *in the matched `+io` condition only*, macro-averaged over ≥5 runs. Our raw-text and self-derived-interface numbers are reported **without a comparison claim** |
| Models reaching full outcome equivalence | **33%** = 19/58, **best-of-5 per model** | **≥ 45% best-of-5** (estimator named, so it is comparable) |
| **Instrument validation: ρ(AFS, OE)** — the primary endpoint | none exists | **ρ ≥ 0.6 with 95% CI lower bound > 0.3**, at n = 58. The bounded string implementation exists, but eligibility across all 58 models is not established; recompute power from the actual eligible cluster count before preregistration (§9.4) |
| ContractNLI, strict-entailment accuracy | **83.0%** (Claude, LLM-based formal reasoning) | ≥ comparable *from a compiled artifact*, at ≥ 90% EY |
| Assumption minimality | none exists | ≥ 80% of declared assumptions provably necessary |
| Scope-laundering analogue | **15.3–52.5%** in LLM self-reported formal reasoning | **Reworded — v3's "0 by construction, verified by audit" was incoherent** (either it needs no audit or it is not by construction). Correct claim: the compiler cannot launder a *verdict*, because it makes no LLM calls — but the failure **relocates** to extraction, where the model may assert a predicate it did not derive from the text. That relocated rate is **measured, not assumed to be zero**, via provenance precision against evidence spans |
| Selective prediction: AURC vs. a **ported** grammar-entropy predictor | the published **AUROC > 0.93** is on *logic tasks*, a different task, metric family, and base rate — **not a threshold for us** (consistent with §12.2, which v3's table contradicted) | beat the ported baseline **on our data**, reported as AURC with CIs |
| ρ(span-F1, AFS) — the dissociation | **no published reference point.** v3 cited "structural similarity ≈ 0.43 alongside outcome equivalence ≈ 0.43" — two unrelated quantities that happen to be numerically close, which is not a correlation and cannot anchor a target | **< 0.4** on **committed** corpora only (2, not 3 — §8), reported as exploratory (§13.1) |
| Grounding-verifier / vector-replay **dissociation** (not a calibration result — §24 non-blocking) | ours, n=1: **98% flagged vs. 6% self-vector-replay failure** | dissociation **≥ 5×**, replicated across ≥ 3 domains and ≥ 3 verifier models, **and** an independently-labeled grounding-truth set built before it is called miscalibration |
| RuleArena head-to-head | LLMs "perform poorly"; tools help | compile-then-execute **≥ +15 points** over in-context application |
| CEGIR gain | — | **+6–12** points on **AFS**, paired by document |
| Solver-reward RL over SFT | — | **+5–10** points on **AFS**; 8–14B ≥ frontier prompted *(conditional phase — §17 G5)* |
| SDI, best system | — | **< 0.7** (benchmark not saturated) |
| CQI, compiled vs. long-context QA | — | **0 vs. > 5%** |
| Conflict density, before vs. after CEGIR | — | **≥ 60%** reduction |
| Amortized cost at N = 10³ | — | **≥ 100×** cheaper, with caching enabled for the baseline |

---

## 16. Preliminary evidence in hand, and its limits

### 16.1 Current repository evidence (2026-08-26)

| Evidence | Current result | What it supports | What it does not support |
| --- | --- | --- | --- |
| Core Python test suite | 1,051 collected tests pass | Local engineering and contract regression coverage | Scientific validity, benchmark quality, or real-world generalization |
| Plan/research validators | 38-task plan valid; G0 retained artifacts internally consistent; 9 research artifacts pass the overclaiming guard | Evidence taxonomy, dependency graph, artifact contracts, and visible non-results | Completion of tasks marked `implemented` |
| Full privacy-policy pipeline run | 1,012 source files; 1,260 chunks; 231/231 extraction batches; zero dropped bytes; 879 final rules | End-to-end operability and repaired source-read coverage | Semantic rule recall, dependency accuracy, or corpus-level legal correctness |
| Readiness and grounding on that run | readiness: 537 ready / 342 review before grounding; grounding: 108 certified / 771 failed, 100% claim-response coverage | The pipeline preserves review failures and produces useful audit queues | Model calibration or accuracy; the run is exploratory and locally retained |
| PIPE-2B semantic recall | 2/3 fixture matches; precision/recall 0.667 with descriptive Wilson intervals | Evaluator and uncertainty-reporting contract | Population semantic recall; fixture is synthetic |
| PIPE-4 dependency audit | 1/2 fixture matches; precision/recall 0.5 with descriptive Wilson intervals | Positive/negative edge accounting and evaluator contract | Population dependency quality; fixture is synthetic |
| IR-2 pilots | bounded NDA and privacy-policy manifests retained; unsupported constructs remain explicit refusals | Census tooling, provenance, and refusal accounting | Full-corpus construct prevalence or an IR completeness claim |
| Dutch A1 replay | 1,900 rows compared; 1,108 exact and 792 mismatched | Reproducible detection of a material upstream/replay disagreement | Any headline OE number until the mismatch is root-caused |
| J1, G3, G4, G5 retained artifacts | explicit `unrun` / `blocked` records | Honest release boundary and executable schemas | Compiler performance, instrument validity, CEGIR gain, or RL gain |

The interactive UI makes these run, artifact, evidence, diagnostic, and review
states inspectable. It is valuable for annotation and artifact demonstration,
but it must appear in the paper as research infrastructure or supplementary
material, not as an empirical contribution.

### 16.2 Historical predecessor feasibility spike

From a throwaway spike against this pipeline's predecessor monorepo on a
352-rule certified graph. **One run, one domain (mortgage), n = 1**; the
artifacts are not in this repository.

| Measurement | Result *(measured, n=1)* |
| --- | --- |
| Rules with complete DMN-critical structure | 352/352 (100%) |
| Rules emitting well-formed DMN 1.3 XML | 352/352 (100%) |
| Literals not renderable as FEEL | 0 of 1,385 |
| Distinct operators (all FEEL-expressible) | 8 |
| DNF expansion | 429 rows from 352 rules; 87.5% single-row; worst case 7 |
| Rules needing negation nodes | 0 |
| **Test vectors reproduced by generated row logic** | **361/384 (94.0%)** |
| Vectors where a rule fired with a *wrong* value | **0** |
| Grounding verifier flagged as requiring review | **345/352 (98%)** ← the dissociation |
| Rules with exceptions | 155/352; **125 introduce variables absent from the condition** |
| Hit-policy mix | 324 UNIQUE / 24 COLLECT / 4 ANY |
| UNIQUE→FIRST downgrades required | 42 |
| Output-signature groups | 336 for 352 rules; 323 singletons |
| Dependency-edge types | prerequisite 138, complementary 46, conditional 45, sequential 37, validation 18, override 16, contradictory 5 — **but see the caveat below** |

**These edge counts are not trustworthy (§12.4 D-2).** They were produced by an
optimizer that summarised each rule from the legacy `conditions`/`consequences`
fields the v2 prompts forbid, sampled ~25% of each batch for cross-batch checks,
and capped batch pairs at 20 *(verified-in-code)*. So the counts measure what a
partially-blind, partially-sampled pass happened to find — **not** the dependency
structure of the graph. Every downstream use of them (BPMN ordering shares, the
`prerequisite`/`sequential` 175-of-305 split, CEGIR's witness supply) inherits
that. They stay in the table as the historical record and are not used as
evidence until PIPE-3/PIPE-4 land.

**Should generalize** (schema-level properties of the v2 contract, not of
mortgage data): operator/type/hit-policy inventories, FEEL mappability, DNF
tractability, DMN column derivation.

**And the same criticism applies to the anchor, which no review has said out
loud.** This section rightly discounts its own evidence as n = 1 (one run, one
domain). The instrument-validation result in §9 rests on **n = 1 corpus**: one
jurisdiction (Netherlands), one language (Dutch), one statute (*Omgevingswet*),
one document genre (statutory permit rules), one generating model (GPT-5.1), one
research group's formalization conventions. It is the only public gold-artifact
corpus we found, so there is no alternative — but the paper must state the limit
in the same words it uses for its own preliminary evidence, and the claim must be
"artifact-free signals track OE **on this corpus**," never "in general."

**Two mitigations, both cheap enough to commit to.** (a) Search for a second
gold-artifact source — candidate leads: OpenFisca / PolicyEngine rule bases with
paired legislation, Catala's formalized statutes, and government "rules as code"
pilots; even 10–20 paired artifacts would turn n = 1 into n = 2 jurisdictions.
(b) **Declare the abandonment condition now**, which v1–v3 never did: *if
artifact-free signals do not predict OE on the anchor, and no second
gold-artifact corpus can be obtained to check whether that is corpus-specific,
the extensional-evaluation thesis is not supportable and the project reverts to
the diagnostic paper (§20 Plan B) rather than arguing the anchor was unusual.*

**Probably will not:** the 94% replay rate, the 87.5% single-row share, the
conflict count, and anything keyed to `rule_type`.

**Cross-check against the literature.** Graus's 42.6% outcome equivalence
against *gold artifacts* and our 94% *self*-vector replay are not in conflict —
they measure different things (fidelity to the extracted rule vs. fidelity to
the correct rule), and the gap between them is roughly the size of the
extraction problem. Stating that plainly is important: it is exactly why §9's
instrument validation, not another replay number, is the load-bearing
experiment.

Also inherited: the grounding verifier LLM-checks only 6 of 12 claim types
against corpus quotes (`description`, `condition`, `outcome`, `party`, `scope`,
`exception`); `test_vector`, `condition_logic`, `variable`, `classification`,
`entity_attachment`, and `execution` are structural-only. "Certified" does **not**
mean the DMN projection was verified against source text. The correctness
argument is a *chain* — the verifier checks conditions/outcomes against source;
vector replay checks the artifact against conditions/outcomes — and the paper
claims only the composition.

---

## 17. Timeline — evidence acquisition and paper freeze

Local implementation is no longer the critical path. The schedule is now driven
by external evidence, adjudication, mismatch diagnosis, and preregistered runs.
Dates below are internal commitments and must be replaced when the official 2027
CFP is published.

| Phase | Internal window | Work | Exit gate |
| --- | --- | --- | --- |
| **E0 — freeze evidence frames** | Sep 2026 | Freeze licensed PIPE-2B and PIPE-4 sampling frames; recruit two independent annotators; freeze the corpus census population; pin the third-party DMN engine; archive the Dutch replay inputs and environment. | Licenses/release roles recorded; annotator instructions and adjudication protocol frozen; all hashes retained |
| **E1 — resolve reproducibility blockers** | Sep–Oct 2026 | Root-cause the 792/1,900-row Dutch replay mismatch; run the external DMN engine; execute the real IR census; complete rule/dependency annotations. | A1 replay either matches or has a documented root cause; BE-4 evidence retained; PIPE-2B/PIPE-4/IR-2 can move from `implemented` to `done` or stop the claim |
| **E2 — compiler and anchor observations** | Oct–Nov 2026 | Run J1 on the frozen Dutch units, record refusals and eligible clusters, select exception readings outcome-blind, and retain every run/failure. | Valid J1/J1B bundle; actual eligible cluster count and power recomputed; compiler claim bounded to observed coverage |
| **E3 — instrument study** | Nov–Dec 2026 | Freeze preregistration, collect source-only AFS observations, run sOE positive control and permutation/bias/leakage controls, then estimate clustered uncertainty. | `g3_instrument.json` is `useful`, `weak`, `underpowered`, or `invalid` under the frozen rule; no retrospective relabeling |
| **E4 — choose submission shape** | Jan 2027 | If G3 is valid/useful, add bounded ContractNLI transfer and optionally CEGIR. If weak but valid, write a limitations/diagnostic paper. If invalid, stop the instrument claim and decide whether C1 alone is sufficient. | Written go/no-go memo naming the exact paper claim, tables, and excluded claims |
| **E5 — optional method branch** | Jan–Feb 2027 | Run CEGIR first. Activate solver-reward training only with separate provider/GPU approval and only after the held-out reward audit passes. | Method result is included only if fully retained and statistically interpretable; otherwise omitted without delaying the paper |
| **Artifact + manuscript freeze** | Mar–Apr 2027 | Re-run the accepted configuration; generate tables/figures from retained bundles; complete limitations, ethics, data cards, reproducibility checklist, and anonymized artifact. | **Internal artifact freeze 2027-04-01; manuscript freeze 2027-04-15**; no new headline result afterward without reopening validation |

Cross-lingual/cross-jurisdiction expansion, additional target languages, broad
multi-corpus sweeps, and RL are follow-on work unless E1–E4 finish early. The UI
review workbench supports adjudication and supplementary demonstrations but is
not on the scientific critical path.

## 18. Budget, separated by line (§24 R13)

v2 gave one `$15k–$30k` figure "presented mainly as extraction spend" and did not
reconcile GPU weeks, annotation, or engineering time. Separated, with the
scope-cut scope:

| Line | **Minimum paper** (registered implementation scope = **125 pd**) | Full programme (registered implementation scope = **171 pd**) |
| --- | --- | --- |
| **API / inference** | Anchor: 58 testable models × 5 runs × the conditions we can match (§9.3), plus the A2 replication if in scope → **$3k–$7k**. **No CEGIR in the minimum paper** | four-corpus sweeps, multi-model, ablations → **$15k–$30k** |
| **GPU** | none (no RL in the minimum paper) | 8×H100 × 1–2 weeks × 2–4 runs ≈ **600–1,300 GPU-hours**, plus false starts → **$8k–$25k** at commodity rates, or a cluster allocation |
| **Solver / CPU** | modest, but the RL bottleneck later — cache by rule-set hash, bound row counts, time-box calls and report the timeout rate | a solver farm; budget separately from GPU |
| **Annotation** | **now includes LEXEC-Perturb**, restored to committed scope by §9.2: ~1.5–2k items at 2–4 min with 20% double annotation → **~120–160 hours**, plus ~500 scenario validations and a stratified assumption-admissibility review → **~60–90 hours**. **Total ~180–250 hours** | + the reserve corpora's scenario sets |
| **Storage / artifacts** | run manifests, all 5 runs retained per condition, generated artifacts → tens of GB | hundreds of GB with RL rollouts |
| **Engineering time** | The 125 pd implementation contract is complete locally. Remaining calendar effort is experiment operation, annotation, adjudication, mismatch diagnosis, artifact generation, and scientific iteration; it must not be reported as zero remaining work. | The 171 pd implementation contract is complete locally, but real G4/G5 evidence still consumes reviewer, provider, GPU, and analysis time. |

Hard cap plus per-experiment cost logging from day one. The repo's adaptive
global rate limiter already makes concurrent batch runs safe.

---

## 19. Risks and mitigations

| Risk | Severity | Mitigation |
| --- | --- | --- |
| **Source-read coverage is fixed, but semantic recall is unknown** | **Blocking for extraction claims** | Retain PIPE-1/2 coverage; complete the licensed PIPE-2B frame with two annotators, adjudication, weights, and agreement |
| **Optimizer context is fixed, but dependency precision/recall is unknown** | **Blocking for graph/CEGIR claims** | Complete PIPE-4 on a declared frame with explicit negatives; keep DAG node coverage separate from discovery accuracy |
| **Actual anchor eligibility may be below 58 despite bounded string support** | **Blocking for the powered primary endpoint** | Run the corpus census and J1 lowering first; recompute power from the observed eligible cluster count; do not assume implementation implies 58/58 coverage |
| **D-4: the anchor reports no raw-`text` OE**, so v3's headline comparison does not exist | **Blocking for the claim, not the work** | Report raw-text OE standalone; add *interface-derivation accuracy* as a measured sub-result; treat `+io` comparisons as gold-leaking and label them (§9.3) |
| **D-5: the anchor is n = 1 corpus** — one jurisdiction, language, statute, genre, generating model | **High** | State the bound in the same words §16 uses for our own n = 1; hunt a second gold-artifact source; **abandonment condition declared** (§16) |
| **No claimable J1/G3 benchmark bundle yet** | **High** | E1–E3 are the critical path; all failures/refusals are retained and the paper claim is chosen only after the frozen outcome |
| **Dutch replay disagrees with released metrics on 792/1,900 rows** | **Blocking** | Root-cause representation, evaluator-version, inclusion, and environment differences before quoting either aggregate |
| **No pinned third-party DMN-engine result** | **Blocking for independent backend claims** | Execute BE-4 against a content-addressed engine/runtime and retain every disagreement |
| **Someone publishes the solver-reward RL first.** Wang et al. named it as future work in June 2026 (and separately proposed the MCS idea §10 builds on). | **High** | Move C5 earlier if G3 lands early; and make C2 (instrument validation) the paper's spine, since it does not depend on the method being first |
| **Extraction quality, not compilation, is the bottleneck** — garbage rules compile perfectly | **High** | The benchmark is the primary contribution; a rigorous "nobody can do this yet" is publishable. Graus at 42.6% already establishes headroom |
| §16's numbers don't replicate off-mortgage | High | G2; Plan B ready (§20) |
| **AFS does not track gold-based OE** (§9 fails) | **High** | Report a bounded negative result only if the instrument study is valid and adequately powered; an invalid or underpowered study supports no correlation conclusion |
| Direct long-context QA simply wins on the decision scores | High | Pre-committed: report it; pivot to PP/CQI/amortization, all pre-registered. Do not hide it |
| Dutch corpus is one jurisdiction/language/genre | Medium | It is the *anchor*, not the benchmark; five other corpora carry breadth. Graus lists this limitation himself |
| Defeater semantics wrong | Medium | Compare all three readings empirically; report which the vectors and Perturb support |
| Contamination inflates results | Medium | Perturbed + post-cutoff splits; memorization probe; cite arXiv:2509.15336 and arXiv:2601.08778 as prior warnings |
| Borrowed gold has annotation errors | Medium | Audit a sample of every borrowed gold set before trusting it (arXiv:2601.08778) |
| ContractNLI entailment mode ungradable | Medium→**mitigated** | §10 assumption-explicit compilation; and try to obtain the 400/610 strict re-annotation from arXiv:2606.16118 |
| SMT throughput limits the RL loop | Medium | Cache by rule-set hash; bound rows; recorded timeouts |
| Annotation IAA too low on "meaning-preserving" | Medium | Closed relation list, pilot, adjudication, per-relation IAA |
| Reviewers see an application paper | Medium | Lead with §9 (instrument validation) and §10 (semantics), not with the pipeline; include cross-task transfer |
| BPMN over-interpretation | Low (de-scoped) | **BPMN is out of the paper.** Only `prerequisite`/`sequential` are ordering (175 of 305 edges *(measured)*). PET's 47 pairs show how thin that evidence base is. Spin-off, not contribution |
| Scope creep across six contributions | **High** | Staged so each is independently publishable (§20) |

---

## 20. Fallbacks

- **Plan A (target).** Main track: instrument validation + assumption-explicit
  semantics + solver layer + CEGIR + solver-reward RL + the two findings.
- **Plan B (if §9 or G2 fails).** *"Why document-to-logic extraction fails: a
  decidable diagnosis."* Use the compiler as a diagnostic and characterize which
  semantic phenomena defeat extraction — defeasibility, cross-references,
  temporal scope, deontic modality, vagueness ("reasonable efforts," "material
  adverse change"). Graus's finding that generated models keep 26–35% of gold
  nodes yet match behavior 42.6% of the time is the perfect opening figure for
  this paper. No RL needed.
- **Plan C (if RL doesn't beat SFT).** Evaluations & Datasets track: LEXEC-Bench +
  instrument validation + assumption-explicit metrics + CEGIR + the
  miscalibration finding. LegalBench set the precedent for legal benchmarks at
  NeurIPS D&B.
- **Plan D (if annotation slips).** Ship without LEXEC-Perturb; the extensional
  half plus §9 stands alone. Given LGMT, this is the most expendable piece.
- **Spin-offs (keep out of the main paper):** BPMN orchestration from dependency
  DAGs; semantic dedup by logical equivalence vs. embedding similarity; the RL
  environment as a standalone released artifact.

---

## 21. Related work, grounded

Every item below was located and checked against a primary source; Appendix C
lists the identifiers. Organized by what each line of work leaves open.

**Search protocol** (stated so the paper's bounded absence claims — "we found no
prior work that…" — are auditable rather than categorical, per §24's non-blocking
note). Engines: web search plus direct arXiv/ACL/Springer/IEEE/USENIX/OpenReview
retrieval, 2026-08-24. Query families: legal/contract/privacy NLP benchmarks;
"rules as code" / "regulation as code"; LLM → DMN / BPMN / decision model /
decision table; defeasible deontic logic + LLM; LLM + SMT/solver/autoformalization;
metamorphic testing of LLMs and of structured generation; RLVR / RL-with-symbolic-feedback
across domains; text-to-SQL execution accuracy; regulatory QA and compliance
checking; policy-as-code for agents. Forward/backward citation chasing on the
five closest hits (arXiv:2604.17153, 2606.16118, 2605.23965, 2504.18422,
2606.32004). **Known limits:** English-language sources only; no systematic sweep
of ICAIL/JURIX/BPM proceedings by table of contents; no patent search; and the
2026 literature is still arriving. Absence claims are therefore scoped to "this
protocol did not surface it," never to "it does not exist."

**A. Manual formalization of law ("rules as code").** Catala (Merigoux,
Chataing & Protzenko, ICFP 2021 / arXiv:2103.03198) — a DSL for statutory
computation that found a bug in the official French benefits implementation.
LegalRuleML (OASIS Standard v1.0, 30 Aug 2021; Athan, Governatori et al., ICAIL
2013) — defeasibility, deontic operators, norm classification, rule/text
isomorphism. Symboleo (IEEE RE 2020; SoSyM 2022) with Symboleo2SC (SoSyM 2024) —
obligations/powers with statechart semantics, LTL/CTL model checking, smart-contract
generation. Hublet, Kvamme & Krstić (arXiv:2402.17350) — enforceable GDPR
specifications for runtime enforcement. OECD *Cracking the Code* — the policy
framing. **Left open:** all hand-authored. This project's target representation
is theirs; the extraction and the validation are not.

**B. LLM → formal legal representation.** Horner, Mateis, Governatori &
Ciabattoni (arXiv:2506.08899) — legal text → Defeasible Deontic Logic with
atomic-snippet segmentation and coherence metrics. SOLAR (Sadowski & Chudziak,
CIKM 2025 / arXiv:2509.00710) — multi-agent statutory reasoning with formalized
intermediate representations and symbolic inference. ContractCheck (Khoja et al.,
*AI and Law* / arXiv:2504.18422) — SPAs → decidable FOL → SMT conflict detection,
from a manual ontology-driven encoding. PolicyGuard (arXiv:2606.32004) —
neuro-symbolic NDA compliance review with Z3, evaluated on CUAD and ContractNLI.
PropertyGPT (NDSS 2025) — retrieval-augmented formal property generation for
smart contracts. **Left open:** corpus-scale behavioral validation, no learning
from the verifier, and no calibration of the evaluation itself.

**C. Document → executable decision model.** **Graus, ICAIL 2026
(arXiv:2604.17153)** — the closest work: 95 production DMN models + Dutch
statutory text, four input representations, structural (graph-kernel) *and*
outcome-equivalence evaluation, released under CC BY 4.0 with a harness. Earlier,
pre-LLM: Text2Dec (Springer 2020) and DMN extraction via dependency parsing /
deep learning; the field's own literature notes that *"a paucity of
gold-standard, scalable annotated datasets currently hinders objective
evaluations."* **Left open, per his own limitations:** one jurisdiction/language/
domain, one LLM, 1-shot, no solver-based consistency checking, exhaustive-enumeration
testing, and I/O specs supplied by experts. Each is a line item in §4.

**D. LLM → process models (BPMN).** ProMoAI (arXiv:2403.04327), BPMN Assistant,
Nala2BPMN, "Do LLMs Speak BPMN?", the SoSyM benchmark study; PET (47 text/BPMN
pairs) as the standard dataset; evaluation via conformance checking and
behavioral-footprint similarity (PM4Py); knowledge-driven hallucination in
process modeling (arXiv:2509.15336). **This is prior art for extensional
evaluation of generated formal artifacts and must be cited as such.** It is also
why BPMN is out of scope here.

**E. Legal / privacy / regulatory benchmarks.** LegalBench (Guha et al., NeurIPS
D&B 2023 / arXiv:2308.11462; 162 expert-built tasks). CUAD (NeurIPS D&B 2021).
ContractNLI (Findings EMNLP 2021 / arXiv:2110.01799). MAUD; ACORD
(arXiv:2501.06582; 114 queries, 126k query–clause pairs); ContractEval (NLLP
2025 / arXiv:2508.03080; CUAD, 4 proprietary + 15 open models, plus a "laziness"
metric). SARA (arXiv:2005.05257; 9 IRC sections, 96 hand-crafted cases).
RuleArena (ACL 2025 / arXiv:2412.08972; 95 rules, 816 problems). ObliQA/RIRAG
(arXiv:2409.05677; 27,869 obligation-centric questions). OPP-115 (ACL 2016);
MAPP (LREC 2022); PolicyQA (arXiv:2010.02557); PrivacyGLUE (*Applied Sciences*
2023, 7 tasks); PLUE (arXiv:2212.10011). PolicyLint (USENIX Security 2019;
11,430 apps, 14.2% with contradictions), PoliCheck (USENIX Security 2020),
Polisis (USENIX Security 2018). Survey: *AI/NLP's Role in Regulatory Compliance*
(Findings of ACL 2025). **Left open:** every one of these scores labels, spans,
retrieval, or free text. None scores an artifact's behavior.

**F. Compliance with KG / graph intermediates.** GraphCompliance
(arXiv:2510.26309; policy + context graphs, 300 GDPR scenarios, +4.1–7.2pp
micro-F1). Baldwin & Ghanavati (arXiv:2604.27713; KGs from AI-policy documents,
42 QA tasks, 5 LLMs, LLM-discovered schema ≥ formal ontology). Automated privacy
policy analysis with KGs (USENIX Security 2023). **Consequence: the KG
intermediate is not a contribution of this project.**

**G. Neurosymbolic LLM + solver.** Logic-LM (Findings EMNLP 2023 /
arXiv:2305.12295; +39.2% over standard prompting, with solver-error
self-refinement), SatLM, LINC. *Know Your Limits* (arXiv:2606.16118) — the
faithfulness study that reshapes §8 and §10. *Grammars of Formal Uncertainty*
(NeurIPS 2025 / arXiv:2505.20047) — autoformalization swings +34.8% to −44.5%;
grammar-entropy UQ at AUROC > 0.93. nl2spec; Verus-SpecGym (arXiv:2605.26457);
neurosymbolic auditing of NL requirements (arXiv:2605.13817). **Left open:**
these operate on short problems or single utterances with gold formal targets,
not long normative documents with none.

**H. Execution-based evaluation and semantic parsing.** Spider; BIRD
(arXiv:2305.03111); Spider 2.0; Reasoning-SQL (arXiv:2503.23157). Also the
annotation-error caution (arXiv:2601.08778). **Acknowledged ancestor:** execution
accuracy is theirs. The delta is documents instead of utterances, no gold
programs, defeasible semantics, and audit-traceability.

**I. Metamorphic / behavioral testing.** LGMT (arXiv:2605.23965), METAL
(arXiv:2312.06056), the MT-and-LLMs survey (arXiv:2605.13898), metamorphic
prompting for SQL, search-based MR selection (arXiv:2507.05565), CheckList.
**Left open (narrowly):** perturbing the *source document* and checking
*compiled-artifact* equivalence, with directional refinement relations.

**J. RLVR and symbolic feedback.** Tulu 3 (arXiv:2411.15124); RLVR for
text-to-SQL (arXiv:2503.23157), information extraction (arXiv:2607.23420),
structured output (arXiv:2512.00319), cyber threat intelligence
(arXiv:2602.00513), knowledge-intensive domains (K2V); autoformalization RL
(ReForm arXiv:2510.24592; StepFun-Formalizer arXiv:2508.04440; process-verified
Lean RL arXiv:2606.20068); LLM-CEGIS program repair (AAAI 2025 /
arXiv:2502.07786). **Left open:** a reward that is a solver verdict on the
*denotation* of an artifact extracted from a long document with no gold artifact
— named as future work by arXiv:2606.16118 and, as of this search, unpublished.

**K. Policy-as-code in agent systems.** ToolGuard (NL policy → executable guard
code at the tool boundary); PolicyBank (arXiv:2604.15505); PolicyGuard
dialogue-grounded verifier (arXiv:2606.29225); Near-Miss (arXiv:2603.29665);
implicit regulatory compliance in tool invocation (arXiv:2601.08196). **Left
open:** per-policy imperative guards with no semantics, no cross-policy
consistency checking, and no decision-level benchmark.

**One-line positioning:** *prior work either formalizes law by hand, scores legal
NLP by string overlap, or — in one recent case — compares generated decision
models against 95 gold artifacts in one jurisdiction. We validate the gold-free
metric against those gold artifacts, make the assumptions the gold labels hide
explicit, decide consistency with a solver, and train on the solver's verdict.*

---

## 22. Ethics, licensing, release

- **Not legal advice.** Decision *support*. State it in the paper and ship it in
  the artifact.
- **Automation bias is the real harm.** A confidently wrong compiled artifact is
  more dangerous than a confidently wrong sentence because it looks authoritative
  and it executes. Measured mitigations: mandatory provenance per emitted row;
  `unresolved` as a first-class output; risk–coverage instead of a single accuracy
  number; refusal to emit from uncertified input by default. Note that §10's
  assumption records are also a safety feature — an artifact that must name what
  it assumed is auditable in a way a bare verdict is not.
- **Licensing — the Dutch discrepancy is resolved, and the answer is more
  delicate than either option** (§24 non-blocking). Checked the repository
  directly: it states "This repository is licensed under CC BY 4.0," with **no
  separate data license**, and — the part that actually matters — **the upstream
  Dutch government DMN models carry no explicit license at all**. The repo's own
  words: "No explicit license is provided in the repository, but the data is
  assumed to be freely reusable under the Dutch *Wet hergebruik van
  overheidsinformatie* (Act on the Re-use of Government Information), which
  implements the EU Open Data Directive." So redistribution rests on an
  **assumption about Dutch open-government law made by a third party**, not on a
  grant. Consequences: cite the repo's CC BY 4.0 for their derived artifacts;
  **do not re-host the source models** in our release — reference them by
  commit hash and let the harness fetch; and seek written confirmation from the
  Dutch DSO before any redistribution. The paper page's CC BY-SA indication is
  inconsistent with the repository and should be raised with the author.
- Other corpora: CUAD and ContractNLI CC BY 4.0. OPP-115 and MAPP research use,
  no redistribution grant → ship edit scripts and offsets, never derived text.
  ObliQA: check ADGM terms. Cite every corpus paper.
  `benchmarks/datasets.json` (checksummed upstream URLs) is the template.
- **Annotators:** fair disclosed pay, published guidelines, reported IAA.
- **Dual use:** the same machinery finds gaps in a policy, which can serve
  exploitation as well as audit. One honest sentence in broader impact; the
  counterpoint is that this capability is what makes compliance auditable at all.
- **Release:** compiler, solver layer, benchmark harness, assumption extractor,
  perturbation edit scripts, RL environment, adapter weights; reproducibility
  checklist including the true cost of a full reproduction.

---

## 23. Immediate next four weeks — produce claimable material

The implementation queue is empty; the evidence queue is not. The next four
weeks should create the minimum set of retained observations needed to decide
whether a NeurIPS paper exists.

1. **Root-cause the Dutch A1 mismatch.** Re-run from the pinned upstream commit
   and compare evaluator version, input enumeration, inclusion rules, parsing,
   and aggregation. Preserve the current mismatch artifact; do not overwrite it
   with a normalized result that hides the disagreement.
2. **Freeze and launch PIPE-2B/PIPE-4 annotation.** Record corpus/license,
   sampling strata and weights, inclusion/exclusion, explicit dependency
   negatives, two independent annotations, adjudication, and agreement. The
   synthetic fixtures remain test data only.
3. **Run the real IR-2 census.** Produce type/operator/exception/table/dependency
   and refusal distributions over the frozen population. Use it to define the
   actual compiler eligibility denominator and update the primary-study power
   calculation.
4. **Execute BE-4.** Pin an independent DMN engine and runtime, run the generated
   conformance suite plus eligible corpus cases, retain hashes and disagreements,
   and refuse the independent-backend claim if the engine job is unavailable.
5. **Build the J1 pilot bundle.** Run a small, frozen Dutch subset end to end to
   validate isolation, manifests, estimator labels, and failure retention. The
   pilot is operational until the full preregistered frame runs.
6. **Freeze G3 before inspecting G3 outcomes.** Commit the estimand, controls,
   eligible clusters, power curve, seeds, bootstrap replicates, missingness,
   multiplicity, and invalidation rules. Then collect the full observation
   bundle.
7. **Prepare conference artifacts in parallel.** Create the claim/evidence
   ledger, table/figure generation scripts, data/release cards, anonymized setup,
   and UI demonstration dataset described in §28.

**Deliberately excluded from this four-week window:** provider/GPU training,
broad multi-corpus expansion, and cosmetic paper writing that depends on an
unknown G3 outcome.

---

## 24. Review — repository-grounded comments and concerns (2026-08-24)

*Historical record, preserved verbatim. Disposition of every item is in §25;
the original work checklist is in §26. Some implementation-status statements
below are intentionally stale and are superseded by §§12.3–12.4 and §28.*

### Overall assessment

The proposal has a credible paper inside it, but the current version is not yet
an executable research protocol. Its strongest idea is **C2, instrument
validation**, supported by a deliberately small compiler/interpreter that makes
the comparison possible. The present six-contribution program is too broad for
the evidence and infrastructure in this repository, and several formal claims
are stronger than the v2 contract can support.

My recommendation is **conditional go, with a scope cut**: make the paper's first
decision point a per-document, reproducible experiment on the executable subset
of the Dutch corpus; treat CEGIR, RL, LEXEC-Perturb, cross-lingual transfer, and
four target languages as follow-ons that earn their place only after that result.
Passing the current test suite establishes useful engineering invariants, not
scientific readiness.

### What is genuinely strong

- The proposal correctly separates extraction, deterministic compilation, and
  external verification. That is the right safety and measurement boundary.
- It is unusually explicit about prior art, negative outcomes, inherited
  evidence, and fallbacks. Keeping the `(measured)` / `(target)` / `(published)`
  distinctions will materially improve reviewer trust.
- The Dutch gold-DMN corpus is the right first external anchor, and the proposal
  is right to reproduce another team's harness before building a large internal
  benchmark.
- The repository already provides useful substrate: a typed candidate contract,
  fail-closed readiness/grounding states, evidence pointers, and deterministic
  graph partitioning. Those are meaningful implementation assets even though
  they are not yet an executable semantic instrument.

### Blocking concerns

#### R1. The repository has source-corpus adapters, not four evaluated benchmark domains

`benchmarks/datasets.json` and `benchmarks/scripts/build_source_docs.py` download
and normalize source text, but there are no committed label loaders, query
builders, fixed splits, scoring code, run manifests, or result artifacts for
CUAD, ContractNLI, OPP-115, or MAPP. The README also states that `pytest` makes no
model calls and tests fixed graphs/prompts rather than live extraction. Therefore
“4 benchmark-backed domains” currently means **four input adapters and prompt
packs**, not four benchmark results. §12.3 should not summarize the extraction
half as “built and tested” without this qualification.

**Required before claims:** add a deterministic evaluation contract per corpus,
with document IDs, gold-query construction, train/dev/test boundaries, metrics,
and immutable run manifests. Report live pipeline runs separately from the 770
provider-free tests.

#### R2. A full-corpus CLI invocation does not currently process the full corpus for rules

`BusinessRulesExtractor.read_text_files_batch()` sorts organized chunks by word
count, truncates every chunk to `max_content_length` (8,000 characters by
default), then returns only
`target_rules // rules_per_batch + 10` batches. With the CLI default of 30 target
rules and five rules per OpenAI batch, that is at most 16 batches even if hundreds
of documents were organized. The result is biased toward the longest chunks and
is not a document-complete extraction. In addition, agent_01 targets roughly
2,000-word chunks while agent_03 clips by characters, so long organized chunks can
lose substantial trailing content before extraction.

This invalidates the current reading of “run one full corpus as one batch,” and
would make cross-domain DA, EY, defect density, and cost denominators ambiguous.

**Required before G1:** execute one model/artifact per gold document (or define an
explicit, frozen multi-document unit), process every chunk for that unit, record
chunk coverage, and fail the run if any required chunk is skipped or truncated.
`target_rules` may cap a pilot, but a capped run must not be scored as corpus
coverage.

#### R3. The optimizer's v2 handoff is broken for both deduplication and dependency analysis

agent_03's compact prompts explicitly forbid the legacy prose fields
`conditions` and `consequences`. However,
`KnowledgeGraphOptimizer._deduplicate_rules_single()`,
`analyze_dependencies()`, and both batched dependency paths still construct
their LLM summaries from exactly those legacy fields. For v2-only rules, the
optimizer mainly sees a truncated description, type, and entity attachments—not
the structured predicates, Boolean logic, outcomes, scope, or exceptions that
the proposed solver semantics depend on.

The batched dependency pass is also intentionally incomplete: it samples only a
small prefix of each batch for cross-batch checks and caps the number of batch
pairs (20 by default). `utils/dag_builder.py` guarantees 100% **node coverage** of
whatever edges it receives; it does not guarantee dependency-edge recall or
semantic correctness. Condensing a cycle preserves nodes but does not produce a
valid execution order within the cycle.

This directly undermines CEGIR's “cross-rule inconsistency,” the cross-reference
perturbation, semantic deduplication baselines, and the proposal's inherited DAG
counts.

**Required before using any graph result:** pass the full v2 fields to the
optimizer, make candidate-pair generation deterministic and recall-auditable,
and evaluate dependency precision/recall on a human-reviewed fixture. Keep “DAG
partition coverage” distinct from “dependency discovery coverage.”

#### R4. The v2 contract is not yet the formal language described in §5

The contract currently leaves several semantics open:

- `applicability_scope` is only checked as a mapping. Final readiness inserts
  mortgage-shaped keys (`loan_types`, `occupancy_types`, `transaction_types`)
  even for the four non-mortgage domains; no typed predicate semantics for
  scope exist.
- There is no deontic modality field. Variable roles are only `input`,
  `derived`, and `output`, so §11's `shall→may` relation cannot be represented as
  an output-role change.
- The eight variable types are `number`, `boolean`, `enum`, `date`, `date_time`,
  `duration`, `string`, and `list`; predicate/outcome values additionally admit
  `range` and `variable_reference`. §5 calls this seven value types and then
  describes the fragment as linear arithmetic. Dates, durations, strings,
  lists, ranges, and cross-variable references need explicit theories and type
  rules or must be rejected.
- Validation does not establish operator/type compatibility, globally canonical
  variable identity, total definitions for derived variables, or a Boolean
  combination for multiple exception predicates.
- A recommended hit policy is stored per extracted rule, while DMN hit policy is
  a table-level property. The rule-to-table grouping and shared output signature
  are not part of the formal setup.

**Required before P1/P2 or solver implementation:** publish a contract v3 (or a
separate compiler IR) with typed scope, modality/norm kind, exception logic,
derived expressions, global symbol resolution, table grouping, null/missing
semantics, and an explicit supported subset. Every unsupported construct should
produce a measured refusal, not be silently projected.

#### R5. P2's `UNIQUE→FIRST` fallback is not semantics-preserving

Proving that rows overlap can show `UNIQUE` is unsafe, but switching to `FIRST`
chooses an answer according to row order. The current formal setup does not give
that order legal meaning. If overlapping rows produce the same output, `ANY` may
be appropriate; if they differ, the artifact is unresolved unless a source-backed
priority or defeater relation exists. Recording the downgrade does not make the
arbitrary choice sound.

**Required change:** make hit-policy reconciliation a proof obligation. Use
`ANY` only with output-equivalence proof, `PRIORITY`/`FIRST` only with explicit
precedence semantics, and otherwise refuse or preserve the conflict.

#### R6. P3 is false as stated

Endpoints plus one interior point per observed cell do not distinguish a table
from **any other** interval table. A candidate can insert a new threshold between
the sampled interior point and an endpoint and agree on every certificate point
while differing elsewhere. Completeness holds only under additional restrictions,
for example when both tables are limited to a known finite threshold set and the
certificate covers every induced cell with correctly handled open/closed bounds.

The current readiness check is much weaker still: it requires only that at least
one numeric input appear in one `boundary_condition: true` vector, and agent_09
checks only that vector keys name declared variables/outcomes; it explicitly does
not execute the predicates or validate the expected value.

**Required change:** either prove a correctly restricted theorem and test ties,
open/closed endpoints, multiple dimensions, missing/default outputs, and
non-interval predicates, or demote P3 to a hypothesis about test-suite reduction.
Do not use it to replace exhaustive enumeration until the restrictions are met.

#### R7. P4/CQI is a determinism property, not evidence of legal consistency

“CQI = 0 by construction” is true only after defining a total deterministic
function and asking extensionally identical queries. A partial artifact, a
`COLLECT` table, an unresolved conflict, or two differently encoded queries can
still make the metric undefined or nonzero. More importantly, any deterministic
but wrong program obtains the same headline advantage. CQI therefore cannot be
an unconditional scientific contribution.

**Required change:** define query equivalence classes, handling of abstentions and
multi-valued outputs, and the baseline consistency protocol. Present CQI as a
reliability/cost property conditional on successful compilation, never as a
correctness metric.

#### R8. Instrument validation is not operationalized and currently mismatches the anchor study

Graus reports outcome equivalence on **58 testable models**, not all 95: 24
Outcome models and 34 Requirements models with alignable interfaces. The
published best condition uses I/O specifications derived from the gold model and
five generations per condition. §9 currently says to run all 95, derive queries
without the gold artifact, and correlate “gold-free DA” with OE, but it does not
define:

- who supplies the gold answer for each gold-free query;
- how queries are sampled without leaking gold I/O, rules, or threshold values;
- whether correlation is across documents, systems, random generations, or all
  three;
- how repeated runs and unequal scenario counts are modeled;
- how the 37 non-executable/interface-incompatible models are handled;
- what confidence interval, null, and minimum useful effect make the instrument
  valid.

It is also not fair to claim a win over 42.6%/60.4% unless both systems receive
the same interface information and are evaluated with the same run-selection
rule; the paper's 33% full-equivalence result is a **best-of-five per model**
analysis, not a single-run rate.

**Required before G1/G3:** preregister the estimand and sampling unit; reproduce
the exact 58-model protocol first; freeze a gold-hidden query-generation process;
compare matched information conditions; retain all stochastic runs; and report
hierarchical uncertainty plus false-positive/false-negative disagreement cases.
Treat “metric failure is publishable” as a possible outcome, not a guaranteed
acceptance argument.

#### R9. Several proposed rewards and metrics are circular or reward trivial artifacts

The repository's vectors are emitted by the same extraction process and are not
currently executed by the grounding verifier. Rewarding vector replay therefore
measures compiler fidelity to a self-generated rule/vector pair, not fidelity to
the source. “Compiles,” “no SMT conflict,” low defect density, and assumption
minimality can all be improved by emitting fewer rules, constant outputs, disjoint
symbols, or no useful coverage. A simple abstention penalty does not close these
paths.

**Required before C5:** define adversarial reward-hacking tests and independent
coverage/completeness rewards. Use held-out source-grounded queries and evidence
spans that are not generated by the policy being trained. Report every reward
component, Pareto front, output size, symbol reuse, and omission rate; never train
and evaluate on the same solver-derived witnesses.

#### R10. Assumption minimality does not make arbitrary assumptions legitimate

Dropping each assumption one at a time proves deletion-minimality relative to a
particular formalization; it does not prove minimum cardinality, uniqueness,
legal permissibility, consistency with background law, or source grounding. A
model can still add one decisive assumption equivalent to the desired hypothesis.
The proposal needs a typed assumption language, admissibility policy, provenance,
and a human-review protocol.

The novelty delta must also be narrower. *Know Your Limits* already proposes
surfacing Minimal Correction Subsets with SMT and presenting them to legal
practitioners, in addition to calling for solver feedback. The new claim can be a
document-level, provenance-bound implementation and evaluation—not assumption
surfacing or minimal correction in the abstract.

#### R11. The statistical plan is not sufficient for the number of comparisons

The headline table mixes accuracy, coverage, correlation, AUROC, AURC, cost,
defect density, and many target effect sizes across corpora, model families,
target languages, repair rounds, and ablations. “Pre-registered targets” alone do
not address multiplicity, stochastic model variance, document clustering, or
selection of the best prompt/run. AUROC > 0.93 on another task is not a directly
comparable threshold for AURC on this task.

**Required change:** identify one primary endpoint and a small number of
confirmatory endpoints; specify macro vs. micro aggregation, seeds/runs, paired
tests, hierarchical bootstrap or mixed-effects analysis, confidence intervals,
multiple-comparison control, and power/sensitivity analysis. Everything else
should be exploratory and labeled that way.

#### R12. Baselines need matched information and execution safety

Direct Python, DMN, SMT-LIB, ASP/Datalog, RAG, and long-context QA do not naturally
receive the same interface, retrieval, context, or execution budget. In
particular, the Dutch `+io` condition receives gold-derived interface information;
a raw-text pipeline does not. Direct-to-Python also introduces sandboxing and
nontermination concerns that are absent from a bounded decision table.

**Required change:** define matched-input baseline families, give every system the
same source slice and interface condition, separate representation failure from
executor failure, sandbox generated code, and report both per-generation and
best-of-*k* results. Do not interpret target-language differences as model
preferences until backend capability and test strength are comparable.

#### R13. The schedule and budget do not match the proposed scope

Within roughly eight months the plan asks for: external reproduction; a compiler,
interpreter, DMN backend, SMT backend, Python backend, ASP/Datalog backend; six
resource adapters; a new annotated perturbation suite; 500 human scenarios;
CEGIR; multi-model studies; cross-domain/language/jurisdiction/task transfer; and
2–4 RL runs. The stated $15k–$30k cap is presented mainly as extraction spend and
does not reconcile 8×H100 weeks, qualified annotation, repeated frontier-model
runs, or engineering time. The repository has not yet completed one committed
end-to-end benchmark run.

**Required change:** budget compute, API, annotation, storage, and labor separately.
Commit now to a minimum paper: Dutch reproduction + compiler correctness +
instrument validation + one non-Dutch external-validation domain. Add CEGIR only
after the instrument passes; add RL only after CEGIR yields a stable, non-gameable
reward. Move the remaining target languages and LEXEC-Perturb to explicit
follow-on work.

### Important non-blocking corrections

- The deadline row should say only what is confirmed: NeurIPS lists **2027 —
  Europe**; the 2027 dates and CFP are not announced. “December 2027” is a
  historical expectation, not a confirmed date. Also re-check the 2027 track
  name rather than assuming “Datasets & Benchmarks.”
- Resolve the Dutch artifact's CC BY 4.0 vs. paper-page CC BY-SA 4.0 discrepancy
  before cloning data into a release or deriving redistribution permissions.
- Fix the filename's `neurIips` spelling before it becomes a cited artifact, or
  explicitly preserve it as a compatibility path.
- Replace categorical novelty statements such as “Nobody” / “first” with a
  documented search protocol and bounded phrasing (“we found no prior work that
  combines ...”). The related-work map is strong, but absence claims remain
  difficult to prove.
- “98% grounding-verifier over-rejection vs. 6% vector-replay failure” is not yet
  a calibration result because the two mechanisms check different targets, the
  artifacts are absent, and the denominator is one mortgage run. Call it a
  motivating dissociation until independently labeled grounding truth exists.

### Recommended go/no-go sequence

1. **G0 — make the measurement unit real.** Fix document/chunk coverage, the v2
   optimizer handoff, and compiler-IR semantics; add deterministic label/query
   adapters and run manifests.
2. **G1 — reproduce before extending.** Reproduce the published Dutch harness on
   its 58 testable models, including all five runs and matched I/O conditions.
3. **G2 — validate the compiler.** Differentially test the reference interpreter,
   SMT encoding, and one real DMN engine; retain exhaustive enumeration until a
   restricted P3 is proved.
4. **G3 — validate the instrument.** Freeze gold-hidden queries and a statistical
   analysis plan, then estimate DA↔OE association with uncertainty and structured
   disagreement review.
5. **G4 — choose the paper after the result.** If G3 succeeds, add one
   non-Dutch domain and CEGIR. If it fails, write the diagnostic paper. Attempt
   solver-reward RL only if a non-trivial, held-out, omission-resistant reward has
   already survived adversarial tests.

Until G0–G3 pass, the defensible claim is: **this repository contains a promising,
well-tested extraction contract and a proposal for an executable measurement
instrument. It does not yet contain or validate that instrument.**

---

## 25. Disposition of the §24 review

**All 13 blocking concerns and all 5 non-blocking corrections are applied.**
Every claim §24 made about this repository or about the cited papers was verified
before applying it — and in three places (R2's exact batch arithmetic, R8's run
protocol, R10's MCS claim) the sources are *more* specific than the review stated.

| Item | Verdict | Where applied | Verification |
| --- | --- | --- | --- |
| **R1** adapters ≠ benchmark domains | **Applied** | metadata table; §12.3 rewritten; §26 BENCH-1..3 | `benchmarks/` holds only `README.md`, `datasets.json`, `.gitignore`, 2 download/normalise scripts — no loaders, splits, scoring, or manifests *(verified-in-code)* |
| **R2** full-corpus run isn't corpus-complete | **Applied** | §12.4 D-1; §23 item 1; G0 | `agent_03:195` truncates at 8,000 chars; `:205` sorts desc; `:240` caps at `target//rules_per_batch + 10`. CLI default 30, `rules_per_batch_openai: 5` → **max 16 batches** *(verified-in-code; the review's arithmetic is exactly right)* |
| **R3** v2 optimizer handoff broken | **Applied** | §12.4 D-2; §7 caveat; §23 item 2 | legacy fields at `agent_06:349,536,706,768`; cross-batch sample `min(20, batch_size//4)`; pair cap 20 at `:737-751` *(verified-in-code)* |
| **R4** contract ≠ the §5 formal language | **Applied** | §5 fragment rewritten; §26 IR-1 | `VALUE_TYPES` = **10**, `VARIABLE_TYPES` = **8**, `VARIABLE_ROLES` = {input, derived, output}, scope checked only as a Mapping *(verified-in-code)*. **v2 said "7 value types" — a factual error, now fixed** |
| **R5** UNIQUE→FIRST not semantics-preserving | **Applied** | P2 replaced with a proof-obligation table | Correct on the semantics: row order carries no legal meaning in this setup |
| **R6** P3 is false | **Applied — claim withdrawn** | P3 → P3′, restricted; exhaustive enumeration retained | The counterexample is valid (insert a threshold between interior point and endpoint). **I added a refinement §24 did not state:** P3′ needs the candidate's thresholds, so it is a *comparison* theorem, not a test-generation theorem — which is why it cannot replace enumeration in §9 |
| **R7** CQI is determinism, not correctness | **Applied** | P4 rewritten; §13.1 STAT-3 | Correct — and a deterministic-but-wrong artifact earns the same headline |
| **R8** §9 not operationalized, mismatches the anchor | **Applied — §9 fully rewritten** | §9.1–9.5 | Verified in the paper: **58** of 95 testable (24+34), **13,080** input variations, **5 runs/condition**, 1,900 generations, 42.6/60.4 are **macro-averaged**, 33%/50% are **best-run (19/58, 29/58)**, `+io` specs **derived from gold models** |
| **R9** rewards are circular / reward trivial artifacts | **Applied** | §12.2 hacking table + §26 RL-1..4 | Correct, including that vector replay is circular: nothing in the repo executes a test vector today *(verified-in-code)* |
| **R10** minimality ≠ legitimacy; novelty narrower | **Applied** | §10 metrics + admissibility policy | Verified verbatim: arXiv:2606.16118 §5.6 proposes "surfacing Minimal Correction Subsets (MCS) via SMT solvers and presenting them to legal practitioners." **The concept is theirs; only a provenance-bound implementation is ours** |
| **R11** statistical plan insufficient | **Applied** | new §13.1: one primary + 3 confirmatory endpoints, Holm–Bonferroni, everything else exploratory | Correct; also correct that AUROC>0.93 on another task is not a comparable threshold |
| **R12** baselines need matched information + sandboxing | **Applied** | §14.1 matched-information protocol | Correct; the `+io` gold leak is real |
| **R13** schedule/budget don't match scope | **Applied — with an added consequence (D2)** | §17 rebuilt on G0–G5; §18 split by line | Correct: zero completed end-to-end runs behind a 9-workstream plan |
| **NB1** deadline overclaimed | Applied | metadata table: only "2027 — Europe" is confirmed; track names to re-verify | |
| **NB2** Dutch license discrepancy | **Applied — and resolved** | §22 | Repo says CC BY 4.0, **no separate data license**, and the upstream government models have **no explicit license** — reuse rests on an *assumption* about the Dutch *Wet hergebruik van overheidsinformatie*. Do not re-host; reference by commit hash |
| **NB3** filename | **Applied via the review's second option** | metadata table documents it as a deliberate compatibility path | The user named this file explicitly twice; renaming unasked would break their links. §24 permits "explicitly preserve it as a compatibility path," which is what is done. **Recommend renaming before submission** |
| **NB4** categorical novelty claims | Applied | five "Nobody"/"first" claims → bounded phrasing; §21 search protocol added with stated limits | |
| **NB5** 98% vs 6% isn't calibration | Applied | §15 relabels it a *dissociation*; requires independently-labeled grounding truth before "miscalibration" | |

### Two places I extended rather than simply accepted

**D1 — P3′ is weaker than the review's own fix implies (§6).** §24 says
completeness holds "when both tables are limited to a known finite threshold set."
True — but at test-generation time you do not know the *candidate's* thresholds.
So the restricted theorem is only usable for comparing two *known* tables
(regression, equivalence checking, differential backend testing) and cannot
certify an artifact against an unknown reference. That is a strictly stronger
restriction than stated, and it is why §9 keeps exhaustive enumeration rather
than merely "until the restrictions are met."

**D2 — the scope cut changes the target venue, and that is a decision to make
consciously.** §24's minimum paper (Dutch reproduction + compiler correctness +
instrument validation + one non-Dutch domain) is the right call on the evidence.
But it removes both learning contributions, and a NeurIPS **main-track**
submission with no method and no training result is a hard sell. So the scope cut
implies **Datasets & Benchmarks as the primary target**, with main track
available only if G5 lands. I have made that switch explicit in the metadata
table rather than leaving the venue row inconsistent with the plan — but it is a
trade-off the review did not name, and it is worth an explicit decision: *a
narrower, safer D&B paper, or hold main-track ambition and accept the schedule
risk?*

### One framing I want to keep from §24 verbatim

> Until G0–G3 pass, the defensible claim is: **this repository contains a
> promising, well-tested extraction contract and a proposal for an executable
> measurement instrument. It does not yet contain or validate that instrument.**

That sentence should survive into the paper's limitations section.

---

## 26. Required work, itemized (the G0 checklist)

*Historical implementation checklist from 2026-08-24. The code contracts below
have since been implemented and are tracked authoritatively in `tasks.json`.
They are not all scientifically `done`; §28 maps each remaining evidence gate.*

Each item was a prerequisite named by §24, with an owner-sized unit of work and
an acceptance test. This was the bridge to `neurips-plan-2027.md`.

**Pipeline correctness (blocks everything)**

- **PIPE-1** — per-document extraction unit; every chunk processed; coverage
  recorded; fail on skip/truncation. *Accept:* a 40-chunk document yields 40
  processed chunks at any `--target-rules`.
- **PIPE-2** — reconcile agent_01's word-based chunking with agent_03's
  character-based clipping. *Accept:* no chunk loses trailing content silently;
  any clip is logged and counted.
- **PIPE-3** — full v2 fields into dedup and dependency summaries. *Accept:* a
  v2-only rule set produces non-empty predicate/outcome context in the prompt.
- **PIPE-4** — deterministic, recall-auditable pair generation; human-reviewed
  dependency fixture. *Accept:* reported dependency precision/recall, and
  "dependency discovery coverage" reported separately from "DAG node coverage."

**Compiler IR and semantics**

- **IR-1** — compiler IR v1: supported subset declared; typed scope; norm
  kind/modality; exception Boolean structure; derived-variable expressions;
  global symbol resolution + acyclicity; table grouping by output signature;
  null/missing semantics; operator×type compatibility matrix. *Accept:* every
  unsupported construct yields a counted refusal, never a silent projection.
- **IR-2** — theories for `date`/`date_time`/`duration`/`string`/`list`/`range`/
  `variable_reference`, or explicit rejection. *Accept:* a conformance suite per
  type.
- **IR-3** — hit-policy proof obligations per revised P2. *Accept:* the 42
  previously-downgraded rules resolve to `ANY`-with-proof, `PRIORITY`-with-source,
  or a counted refusal — never an unproven `FIRST`.

**Backends and differential testing**

- **BE-1** — reference interpreter. **BE-2** — DMN 1.3/FEEL emitter.
  **BE-3** — SMT-LIB emitter. **BE-4** — third-party DMN engine harness.
  *Accept:* all four agree on 100% of a generated conformance suite; every
  disagreement root-caused.

**Benchmark infrastructure**

- **BENCH-1** — per-corpus evaluation contract: document IDs, gold-query
  construction, frozen splits, metrics, immutable run manifests.
- **BENCH-2** — gold-hidden query generation with a filesystem-level guard and a
  leakage audit (§9.3). *Accept:* the guard fails the run if `gold_models/` is
  reachable from the generator.
- **BENCH-3** — all 5 runs per condition retained; best-of-*k* labeled
  everywhere.

**Assumptions**

- **ASM-1** typed assumption language (closed forms). **ASM-2** entailment-weaker
  admissibility check (reject any *A* with `⊨ A → h`). **ASM-3** span provenance
  per assumption. **ASM-4** stratified human admissibility review.

**RL (only after G4)**

- **RL-1** coverage/completeness reward against an inventory the policy did not
  produce. **RL-2** held-out, independently-authored vectors and evidence spans.
  **RL-3** adversarial degenerate-policy gate (empty, constant, disjoint-symbol,
  one-rule-per-doc must all score worse than the honest baseline). **RL-4** report
  every component, Pareto front, output size, symbol reuse, omission rate.

**Statistics**

- **STAT-1** power/sensitivity analysis on the 58-model primary endpoint, before
  data collection. **STAT-2** hierarchical bootstrap / mixed-effects
  implementation with a random intercept per document. **STAT-3** query
  equivalence classes, abstention and multi-valued handling for CQI.

**Every item above is scheduled, sized, and given an acceptance test in
[`neurips-plan-2027.md`](neurips-plan-2027.md)** — which also adds the task
families this list did not name (`REPRO-*` for the external reproduction,
`BE-*` for the four backends, `CEGIR-*`), the module layout, the dependency
additions and their justifications, a corrected effort total of **126 pd for the
minimum paper** (v3 said 114 pd for a larger scope, and its arithmetic was
wrong — see the plan's §9), and the staffing conclusion that follows.

---

## 27. Final review (third pass) — findings and corrections applied

*Historical third review pass, 2026-08-24; superseded for current implementation
status by §28. §24 is the first review (R1–R13,
applied in §25). The development plan's §14 is the second review (P1–P12). This
section records the third pass: my disposition of P1–P12, plus **seventeen
findings neither prior review made**, and the corrections applied for each.*

**Verdict on the second-pass review: substantially correct.** I verified every
checkable claim. Eleven of twelve findings confirmed outright, one needs a
factual check before its remedy is schedulable (P4b below). P1 is the most
important criticism made of this proposal in any pass, and it changed the primary
contribution rather than merely refining it.

### 27.1 Disposition of the second-pass findings P1–P12

| # | Verdict | Applied where |
| --- | --- | --- |
| **P1** DA is not gold-free | **Confirmed — the deepest finding in three passes.** §13 defined DA with `gold(q)`; §9.3 obtained it by executing the gold DMN. Correlating a sparse gold-labeled score with an exhaustive gold-labeled score tests sampling, not instrument validity | **§9.2 rewritten.** DA retired; **sOE** (sampled, gold-artifact) separated from **AFS** (artifact-free signal); C2 restated as *do AFS predict OE*, with sOE as positive control and random/stratified/biased samples as negative controls. §13 metrics table, §4 C2, TL;DR all updated |
| **P2** the phase graph cannot execute | Confirmed | Plan §15 + the two-track replan (plan §16) |
| **P3** effort arithmetic is wrong | **Confirmed by recomputation.** G0 = 4+2+3+6+8+2+3+7 = **35**, not 28; totals **121** / **141**, not 114 / 134; "G0–G3 + writing" = **95** itemized, not 73 (that figure omitted writing *and* used the wrong G0) | Plan §9 regenerated |
| **P4** replay ≠ replication; OE only for two conditions | **Confirmed verbatim:** *"We limit ourselves to the io and srl+io conditions, as these have consistent inputs and outputs, enabling direct comparison."* | §9.3 rewritten; §15 rows relabeled; plan REPRO split |
| **P4b** — *my qualification* | **Partial.** P4 asserts the released repo "contains generated models, evaluation code, and results," making a deterministic evaluator replay the cheap first step. I could not confirm the **generated** models or expected result files are released — only gold models, source models, legal text, and the harness. If they are not, **A1 as specified is not executable** and the only route is A2 (fresh generation), which is a different cost and a different claim | Plan A1 now begins with a *release-contents audit* and treats replay as conditional |
| **P5** backend agreement ≠ compiler correctness | Confirmed — four backends can share one wrong lowering | Plan G2 split into *lowering correctness* (independent oracle) and *backend agreement* |
| **P6** the IR encodes unsettled/mislocated semantics | **Confirmed, and worse than stated** — see 27.2 N2 | §5, §17 G0, plan IR-1 |
| **P7** chunk coverage ≠ rule coverage | Confirmed; and PIPE-1 ("fail on truncation") contradicted PIPE-2 ("record `bytes_dropped`") | Plan PIPE-1/2 reconciled; three coverage metrics separated |
| **P8** the leakage guard is not a boundary | Confirmed | **§9.6 rewritten** as an information boundary (absent-from-mount, one-way artifact hand-off, adversarial denial tests); the threshold-coincidence audit is dropped as confounded and replaced with source-span provenance |
| **P9** the manifest is insufficient; "pure Python" is false | **Confirmed by checking PyPI.** None of `z3-solver`, `lxml`, `scipy`, `statsmodels` ships a `py3-none-any` wheel; z3 ships `py3-none-<platform>` wheels carrying native libz3 | Plan §1 corrected; run-bundle spec added |
| **P10** statistics mix levels and power the wrong null | Confirmed | **§9.5 rewritten:** run-level observation table with a model-clustered bootstrap; mixed-effects demoted to sensitivity; null corrected to **H₀: ρ ≤ 0.3**; ties/bounds/missingness/attenuation specified |
| **P11** the audits are too easy to pass | Confirmed | Plan §15; sampling frames, set-level assumption entailment, deletion/no-op repair baseline, held-out adversarial search |
| **P12** the plan violates its own definition of done | Confirmed — `OPS-*` declared and never used; BENCH-1b and RL-1/2/4 have no acceptance blocks; `C1..C4` survives only in a code comment; "new code only" sits above tasks editing four existing files | Plan task registry (§15) |

**One framing from the second review is adopted verbatim**, because it is the
correct status line for this document:

> Do not freeze a preregistration, quote a corpus metric, or start paid
> generation from the present plan.

### 27.2 Seventeen findings neither prior review made

Grouped by whether they change the science, the schedule, or only the text.

**Changes the science**

- **N1 — the headline comparison does not exist.** v3's §9.4 promised "raw-text
  vs. Graus's `text`" as the honest headline. The anchor publishes **no OE for
  `text`**, because that condition yields no alignable interface. Both published
  OE conditions are gold-leaking. *Applied:* §9.3 offers three preregistered
  options and commits to two, adding **interface-derivation accuracy** as a new
  measured sub-result.
- **N2 — refusing the `string` theory refuses 34 of 58 anchor models (59%)**, and
  specifically the Requirements half where the anchor scores *higher* (60.4% vs.
  42.6%). The anchor's Requirements models need `contains()` substring
  predicates, binned-numeric strings, and null-checks; a naive string→enum
  normalisation is **not sound** for `contains()`. *Applied:* string theory
  promoted from an IR-2 measurement to a **G0 deliverable**.
- **N3 — N2 is a statistical blocker, and this is the finding I would lead with
  after P1.** Fisher-z, se = 1/√(n−3): at **n = 58** a true ρ = 0.6 gives 95% CI
  **[0.40, 0.74]** and **88%** power against H₀: ρ ≤ 0.3. At **n = 24** it gives
  **[0.26, 0.74]** and **54%** power — the CI lower bound falls **below the
  study's own declared 0.3 threshold even when the true effect is exactly the
  target.** So the string theory is not a coverage nicety; without it the primary
  endpoint cannot succeed. *Applied:* §9.4, §15, §17 G0, §19 D-3.
- **N16 — the anchor is n = 1 corpus, which is the criticism this proposal makes
  of itself.** §16 rightly discounts its own preliminary evidence as one run, one
  domain. The instrument result rests on one jurisdiction, one language, one
  statute, one genre, one generating model, one group's formalization
  conventions. *Applied:* §16 states the bound in the same words, names candidate
  second sources (OpenFisca/PolicyEngine rule bases, Catala's statutes,
  government "rules as code" pilots), and — new in this pass — **declares the
  abandonment condition**, which v1–v3 never did.
- **N17 — construct validity of the target language was never argued.** §14.2
  ablates target *languages* against each other; if all four are inexpressive in
  the same way, that compares equally wrong choices. And the IR *refuses* deontic
  modality, temporal validity, open defeasibility, and vagueness — so the
  pipeline is silently scoped to whatever survives refusal. *Applied:* **new
  §14.6 expressiveness census**, a model-call-free experiment that reports the
  fraction of source content a decision-table semantics can carry at all. That
  number bounds every other result in the paper, and it is the difference between
  "we evaluate document understanding" and "we evaluate the X% that is
  expressible."

**Changes the text, materially**

- **N4** — §13 still said CQI is "**0 by construction**", contradicting the
  corrected P4 in §6 that makes it conditional. *Fixed.*
- **N5** — §8's header said "six resources" while §4 C4, §17, and the TL;DR said
  two. *Fixed:* every resource is now marked **COMMITTED** or **RESERVE**, and
  only committed resources may appear in a headline claim.
- **N6** — §8's scenario mode still sourced bindings "**per P3**". **P3 is
  withdrawn.** A retracted proposition was still load-bearing in the benchmark
  design. *Fixed.*
- **N7** — §15 labeled the anchor numbers "best condition, GPT-5.1, **1-shot**".
  They are `Text+srl+io` **macro-averages over 5 runs**; and 33% is **best-of-5**,
  so the "≥ 45%" target named no estimator and was uncomparable. *Fixed.*
- **N8** — §15 said "AUROC > 0.93 … beat it" while §12.2 said explicitly that the
  comparison is not direct. Same document, opposite instructions. *Fixed.*
- **N9** — §15's dissociation row cited "structural similarity ≈ 0.43 alongside
  outcome equivalence ≈ 0.43" as a reference point. Those are two unrelated
  quantities that happen to be numerically close; it is not a correlation and
  cannot anchor a target. *Fixed.*
- **N10** — §15's scope-laundering row said "**0 by construction** … verified by
  audit," which is self-contradictory, and it also missed that the failure
  **relocates**: the compiler cannot launder a verdict, but the extractor can
  still assert a predicate it never derived from the text. *Fixed:* the relocated
  rate is measured via provenance precision, not assumed zero.
- **N11** — plan §1 called `z3-solver` a "Pure-Python wheel, no system deps."
  False. *Fixed*, with the useful corollary verified: **cp314 wheels exist** for
  lxml/scipy/statsmodels/hypothesis and z3 ships platform-tagged `py3` wheels, so
  this repo's Python 3.14 is fine — worth recording so it is not re-litigated.
- **N12** — the pd arithmetic (confirming P3 with the numbers). *Fixed.*
- **N13** — `results/` is **not** gitignored (only `pipeline-output/` is), yet the
  plan commits `results/`. *Fixed* in the plan's release-boundary spec.
- **N14** — plan §2's "New code only; nothing existing is moved" sits directly
  above tasks that edit `agent_03`, `agent_06`, `cli/extract.py`, and prompts.
  *Fixed.*
- **N15** — `OPS-*` declared and never used; BENCH-1b and RL-1/2/4 without
  acceptance blocks; `C1..C4` only in a code comment. *Fixed* by the task
  registry.

### 27.3 What is still not resolved, stated plainly

1. **Whether the anchor's generated artifacts are released** (N/P4b). Until
   checked, the cheap "evaluator replay" step may not exist.
2. **Whether a second gold-artifact corpus is obtainable.** Without one, the
   central result is bounded to a single jurisdiction and the abandonment
   condition in §16 becomes live.
3. **Whether the expressiveness census (§14.6) leaves enough content to be worth
   evaluating.** If the decision-table-expressible fraction is small, the honest
   paper is a much narrower one than any of v1–v3 describes.
4. **Legal admissibility of assumptions** is not solver-decidable (§10 ASM-4) and
   depends on recruiting qualified reviewers who have not been secured.
5. **Whether the primary claim survives at all.** After three review passes the
   defensible status line remains the one §25 preserved from the first review:
   *this repository contains a promising, well-tested extraction contract and a
   proposal for an executable measurement instrument; it does not yet contain or
   validate that instrument.*

### 27.4 The honest bottom line after three passes

The direction is sound and the corpus opportunity is real. But the proposal has
now had its **primary metric renamed once (P1), its headline comparison deleted
(N1), its statistical power shown to depend on an unimplemented type theory
(N2/N3), and its construct validity left unargued until this pass (N17).** None
of that is fatal; all of it was found by reading rather than by running, which is
the cheapest possible place to find it.

What follows from that is a scheduling conclusion, not a scientific one: **the
first month should produce measurements, not prose.** Specifically the
expressiveness census (§14.6), the string-theory coverage check on the 58 anchor
models (§9.4), and the anchor release-contents audit (§27.3 item 1). All three
are model-call-free, all three can be done in days, and **any one of them coming
back badly would change the paper more than another review pass would.**

---

## 28. NeurIPS material plan from the current implementation

This section is the active bridge from “implemented repository” to “submission
with defensible evidence.” It supersedes implementation-status statements in
§§24–27. `plan/tasks.json` remains authoritative for task status and acceptance
commands; this section is authoritative for the conference package.

### 28.1 Claim freeze

The minimum claim should be written as:

> For a declared, bounded subset of normative decision logic, LExec compiles
> source-grounded extracted rules into fail-closed executable artifacts and
> exposes machine-checkable semantic defects. On a frozen Dutch gold-artifact
> benchmark, we test whether independently constructed artifact-free signals
> predict outcome equivalence, reporting executable yield and refusals beside
> conditional quality.

The submission must **not** claim that compilation decides legal correctness,
that source coverage implies rule recall, that fixture audits estimate
population accuracy, that local backend agreement proves independent
correctness, that a review UI is a research result, or that implemented RL
contracts are training evidence.

### 28.2 Required scientific evidence

| Package | Data required | Current state | Completion criterion | Material produced |
| --- | --- | --- | --- | --- |
| **M1 — extraction denominator** | Licensed, frozen rule and dependency frames; strata/weights; explicit negatives; two annotators | PIPE-2B/PIPE-4 evaluators complete; fixtures only | Adjudicated precision/recall, uncertainty, agreement, and error taxonomy retained | Main coverage table; annotation appendix; data card |
| **M2 — IR construct validity** | Frozen real corpus population and all lowering/refusal records | Census tooling and bounded pilots complete | Full population manifest; type/operator/exception/table distributions; refusal denominator; eligible Dutch cluster count | Expressiveness figure; compiler-coverage table; refusal taxonomy |
| **M3 — compiler correctness** | Independent lowering oracle, generated conformance cases, eligible corpus cases, pinned external DMN engine | Local oracle/reference/DMN/bounded-query tests complete; BE-4 real run absent | All supported cases agree or every disagreement is root-caused; unsupported cases refuse | Backend agreement table; mutation score; counterexample examples |
| **M4 — Dutch anchor reproducibility** | Pinned upstream checkout, released metrics, replayed metrics, environment lock | Audit and replay complete; 792/1,900 rows mismatch | Mismatch explained and corrected or reported as an upstream/reproduction limitation with no borrowed headline number | Reproduction table; discrepancy appendix; exact aggregation recipe |
| **M5 — compiled-artifact benchmark** | Frozen Dutch units, isolated query artifacts, all systems/runs/failures | J1/J1B schemas and harnesses implemented; observations unrun | Content-addressed bundle with estimator labels, OE/sOE/EY, refusal reasons, cost/tokens, and exception-reading result | Primary system table; risk/coverage plot; qualitative failures |
| **M6 — instrument validation** | Independent AFS labels/relations/scenarios, positive and negative controls, J1 OE | Estimator, power, controls, and artifact schema implemented; study unrun | Preregistered clustered estimate with validity checks and a frozen `useful`/`weak`/`underpowered`/`invalid` outcome | Primary correlation figure; control table; disagreement analysis |
| **M7 — bounded transfer** | ContractNLI within the adapter's supported boundary; source-supported assumption review | Adapter and assumption analyzer implemented; human review unrun | Transfer result reported separately, with unsupported modes excluded and assumption agreement/admissibility measured | Transfer table and boundary statement |
| **M8 — CEGIR extension** | Frozen baseline, source-preserving edits, witnesses, deletion/no-op/oracle-withheld ablations | Implementation and retained `unrun` artifact complete | Paired real comparison with no provenance regressions | Repair-gain/ablation table; witness case study |
| **M9 — RL extension** | Approved provider/GPU budget; disjoint training/reward/audit/test sets | Components and adversarial audit code implemented; no training | Held-out reward audit passes, then full frontier with failed runs and exploit checks | Optional main-track method figure/table; otherwise omit completely |

M1–M6 are the minimum evidence path. M7 is useful breadth. M8 can strengthen a
main-track story. M9 is optional and must never consume the artifact-free time
needed by M1–M6.

### 28.3 Paper tables and figures

Every number must be generated from a retained, content-addressed bundle; no
manual spreadsheet should be the source of a paper result.

1. **Figure 1 — measurement chain and trust boundary.** Source document → v2
   extraction → total lowering/refusal → LExec IR → reference/DMN/bounded-query
   backends → AFS/sOE/OE. Visually separate source-grounding evidence from
   internal solver evidence and gold-artifact evidence.
2. **Figure 2 — expressiveness and refusals.** Stacked distribution of supported,
   ignored-with-reason, and refused constructs by type/operator/exception
   family, with the eligible denominator used by later tables.
3. **Figure 3 — instrument validation.** AFS vs. OE at the
   `model × system × run` level, model-clustered interval, positive control, and
   negative/permuted/leakage controls. Plot EY/risk–coverage beside conditional
   quality.
4. **Figure 4 — failure flow.** Source coverage → extracted rules → lowered →
   emitted → independently executed → outcome-equivalent, with explicit counts
   and refusal reasons. This prevents denominator drift.
5. **Table 1 — corpus and evidence card.** Documents, units, language,
   jurisdiction, license/reuse posture, splits, annotations, IAA, and release
   role.
6. **Table 2 — compiler correctness.** Oracle mutation score, local backend
   agreement, independent-engine agreement, unsupported cases, timeouts, and
   unknowns.
7. **Table 3 — anchor and system results.** Matched conditions and estimators,
   OE/sOE/EY, cost, and all failed/refused runs. Keep released and replayed Dutch
   results separate until M4 closes.
8. **Table 4 — instruments and controls.** AFS definition, information source,
   artifact/gold access, correlation, uncertainty, and validity outcome.
9. **Table 5 — ablations.** No solver, no grounding, no CEGIR, no assumptions,
   alternative exception reading, deletion/no-op repair, and direct
   long-context application under matched information.
10. **Table 6 — scoped transfer.** Only if M7 passes; never pool incompatible
    endpoints into the Dutch primary result.

The appendix should include IR semantics, operator/type matrix, refusal codes,
query and isolation protocols, power curves, estimator details, annotation
instructions, disagreement taxonomy, prompt/config hashes, model parameters,
cost accounting, and the full limitations/claim ledger.

### 28.4 Reproducibility and release package

The artifact must contain or point to:

- an anonymized source snapshot and immutable release tag;
- `tasks.json`, LExec IR schema/semantics, exact acceptance commands, and the
  generated plan summary;
- locked dependencies, OS/Python metadata, provider/model identifiers,
  reasoning effort, seeds, rate/concurrency settings, prompts, and configs;
- content-addressed run manifests containing successes, failures, refusals,
  timeouts, unknowns, and costs;
- corpus/data cards, licenses, restricted/local-only roles, and an explicit
  redistribution allowlist;
- one command per table/figure plus a validator that fails on stale or manually
  edited outputs;
- a claim/evidence ledger mapping every abstract, table, and conclusion claim to
  a retained artifact and evidence class;
- an anonymized, sanitized review-workbench demo bundle for traceability and
  qualitative inspection; and
- exported adjudication records in immutable JSON/CSV with reviewer IDs
  pseudonymized, timestamps, artifact hashes, and stale-review detection.

The UI currently supports comments, decisions, labels, saved views, audit
history, stale-hash detection, and selected-rule CSV export. A canonical
**review-delta/adjudication export** is still a conference-material gap; the
SQLite overlay itself must not be the only copy of study labels.

### 28.5 Submission gates and stop rules

The paper is ready for internal submission review only when all are true:

- M1–M6 have retained artifacts and their validators pass;
- the Dutch replay mismatch is closed or explicitly prevents borrowed-result
  claims;
- the eligible denominator and power analysis use observed, not assumed,
  compiler coverage;
- at least one independent backend has executed the supported subset;
- every table reports EY/refusals beside conditional quality;
- the primary analysis was frozen before outcome inspection;
- no `fixture_only`, `exploratory`, `unrun`, `blocked`, `invalid`, or
  `underpowered` artifact appears as positive evidence;
- all paper numbers regenerate from the release bundle; and
- the official 2027 CFP, track name, dates, format, anonymity, and checklist have
  been re-verified.

Stop or narrow the paper when any of these occur:

- **M2 low expressiveness:** narrow the claim to the supported construct family;
- **M3 backend disagreement:** report a compiler limitation and remove the
  independent-correctness claim;
- **M4 unresolved mismatch:** do not use the released anchor aggregate as a
  reproduction baseline;
- **M6 invalid/underpowered:** make no instrument-correlation conclusion;
- **M6 valid but weak:** consider a bounded diagnostic result, not an automatic
  positive paper; or
- **M7/M8/M9 fail:** remove the extension without moving the minimum-paper
  deadline.

### 28.6 Verification commands

Before each evidence freeze and the final artifact tag, run:

```bash
.venv/bin/python scripts/validate_neurips_plan.py --check
.venv/bin/python scripts/validate_neurips_plan.py --run-complete
.venv/bin/python scripts/validate_g0_evidence.py
.venv/bin/python scripts/validate_research_artifacts.py
.venv/bin/python scripts/validate_config.py
.venv/bin/python -m pytest -q
```

For the UI supplement, additionally run its Python tests/coverage, frontend
lint, frontend coverage, type-aware production build, and browser smoke flow.
Record the exact commands and reports in the release manifest rather than
copying a historical test count into the paper.

---

## Appendix A — Naming

| Name | What it is |
| --- | --- |
| **LEXEC** | umbrella project |
| **LEXEC-Verify** | compiler + solver layer; measuring instrument and reward machine |
| **LEXEC-Bench** | extensional benchmark (gold-anchor / entailment / presence-value / practice-decision / scenario modes) |
| **LEXEC-Perturb** | relational (metamorphic) suite |
| **CEGIR** | Counterexample-Guided Iterative Repair |
| **SDI** | Semantic Discrimination Index, `SR + SE − 1` |
| **AFS / sOE / OE** | artifact-free signal / sampled gold-labeled outcome equivalence / oracle outcome equivalence; non-interchangeable measures in §9 |

## Appendix B — Provenance of every claim

**Verified in the current implementation audit (2026-08-26):**
`scripts/validate_neurips_plan.py --check` reports 38 valid tasks with no
missing dependencies or cycles; `scripts/validate_g0_evidence.py` verifies all
five retained G0 artifacts as internally consistent and non-claiming;
`scripts/validate_research_artifacts.py` validates nine research artifacts with
no overclaiming status; and the core test suite collects 1,051 tests and passes.
The canonical compiler assets are `plan/lexec-ir-v1.schema.json`,
`docs/ir-semantics-v1.md`, `utils/lexec_ir.py`, `utils/feel.py`,
`utils/dmn_builder.py`, `utils/dmn_emit.py`, and `utils/smt.py`. Benchmark,
statistics, transfer, CEGIR, reward, and publication contracts are present in
`bench/`, `compiler/`, `training/`, and `scripts/`. The retained research
artifacts explicitly preserve `fixture_only`, `exploratory`, `unrun`, and
`blocked` states.

The local full privacy-policy run records 1,012 source files, 1,260 chunks,
231/231 extraction batches, zero dropped bytes, and 879 final rules. Its
grounding report records 108 certified and 771 failed rules with 100% response
coverage. These values are operational diagnostics from a locally retained run,
not a population-quality estimate or a release artifact. The Dutch anchor replay
compares 1,900 rows and records 792 mismatches; this is a reproducibility blocker,
not a headline result.

**Historical verification while applying the §24 review (2026-08-24):**
`agent_03_rules_extractor.py:195` (8,000-char truncation), `:205` (descending
word-count sort), `:240` (`target_rules // rules_per_batch + 10` batch cap);
`cli/extract.py:264` (`--target-rules` default 30); `config.example.json:69-70`
(`rules_per_batch_openai: 5`) → **≤16 batches**;
`agent_06_knowledge_graph_optimizer.py:349,536,706,768` (legacy
`conditions`/`consequences` in dedup and both dependency paths), `:737-751`
(cross-batch sample `min(20, batch_size//4)`, pair cap 20);
`utils/rule_contract.py` (`VALUE_TYPES` = 10, `VARIABLE_TYPES` = 8,
`VARIABLE_ROLES` = 3, `applicability_scope` checked only as a Mapping);
`utils/readiness.py::_test_vector_boundary_reasons` (one numeric input in one
boundary vector suffices); `agent_09_grounding_verifier.py::_verify_test_vector`
(docstring: "a referential-integrity check, not an arithmetic one"); `benchmarks/`
contains no label loaders, query builders, splits, scoring code, or run
manifests.

**Verified against primary sources while applying the review:**
arXiv:2604.17153 — 58 of 95 testable (24 Outcome + 34 Requirements), 13,080 input
variations, 5 runs per condition, 1,900 generations, 42.6%/60.4% macro-averaged,
33%/50% best-run (19/58, 29/58), `+io` specs derived from the gold models;
arXiv:2606.16118 §5.6 — "surfacing Minimal Correction Subsets (MCS) via SMT
solvers and presenting them to legal practitioners," and solver-based feedback
training named as future work; `opengov-lab/legal-text-to-decision-model` README
— "This repository is licensed under CC BY 4.0," no separate data license, and
the upstream government models carry no explicit license (reuse assumed under the
Dutch *Wet hergebruik van overheidsinformatie*).

**Historical repository state verified on 2026-08-24:** the v2 contract's
closed enums (`utils/rule_contract.py`); the four invariants and
`_project_execution` (`agents/agent_07_executable_readiness.py`); which grounding
claim types reach the LLM verifier vs. are structural
(`agents/agent_09_grounding_verifier.py`, `MODEL_CLAIM_TYPES`); the DAG partition
and SCC condensation (`utils/dag_builder.py`); readiness/selective-prediction
(`utils/readiness.py`, `utils/kg_readiness.py`); the then-absence of FEEL/DMN/BPMN
XML or SMT code in the repo; the `_project_execution` key-set pinning in
`tests/test_inter_agent_contract_alignment.py`; corpus sizes/licenses/checksums
(`benchmarks/datasets.json`, `benchmarks/README.md`); `pytest` → 770 passed at
that historical revision. These absence and test-count statements are
superseded by the current implementation audit above.

**Verified against primary sources this session (web search + fetch):** every
`(published)` number and every citation in §21 and Appendix C — titles, authors, venues,
arXiv IDs, dataset scales, and the specific figures quoted (Graus's 42.6%/60.4%/33%
and node ratios; Wang et al.'s 400/610, 15.3–52.5%, 25.5–63.2%, 71 label
transitions, 83.0%; Ganguly et al.'s +34.8%/−44.5%/AUROC>0.93; RuleArena's 95
rules / 816 problems; ObliQA's 27,869 questions; MAPP's 64/91 policies and
292k/478k words; PET's 47 pairs; BIRD's 12,751 pairs; PolicyLint's 11,430 apps
and 14.2%); and the contents/license/harness of
`github.com/opengov-lab/legal-text-to-decision-model`.

**Inherited from a prior feasibility study** (a 520-line analysis written against
this pipeline's predecessor monorepo, removed in commit `1dea9c8` and recovered
from git history): every `(measured)` number in §16. **One run, one domain,
n = 1**; those artifacts are not in this repository.

**Still unverified, and flagged as such:** venues/years for MAUD, SatLM, LINC,
CheckList, and Spider (located but not primary-source-checked); all cost and
compute estimates in §18; every `(target)` in §15; whether the arXiv:2606.16118
re-annotation is obtainable; NeurIPS 2027's month, dates, CFP, and track list
(only "2027 — Europe" is confirmed); and whether the Dutch DSO will confirm reuse
terms in writing. **Resolved since v2:** the Dutch license question (§22) — the
answer is that the upstream data has no explicit license at all.

## Appendix C — Key references (verified this session)

| Work | Identifier |
| --- | --- |
| NeurIPS official future-meetings page / 2026 Evaluations & Datasets call | `neurips.cc/Conferences/FutureMeetings` · `neurips.cc/Conferences/2026/CallForEvaluationsDatasets` |
| Graus, *From Legal Text to Executable Decision Models*, ICAIL 2026 | arXiv:2604.17153 · `github.com/opengov-lab/legal-text-to-decision-model` |
| Wang et al., *Know Your Limits* (LLM faithfulness, ContractNLI + Z3) | arXiv:2606.16118 |
| Zhou et al., *LGMT* (logic-grounded metamorphic testing) | arXiv:2605.23965 |
| Ganguly et al., *Grammars of Formal Uncertainty*, NeurIPS 2025 | arXiv:2505.20047 |
| Khoja et al., *Automated Consistency Analysis for Legal Contracts* (ContractCheck), *AI and Law* | arXiv:2504.18422 |
| Malik et al., *PolicyGuard* (neuro-symbolic compliance review) | arXiv:2606.32004 |
| Horner, Mateis, Governatori & Ciabattoni, *Legal Text → Defeasible Deontic Logic* | arXiv:2506.08899 |
| Sadowski & Chudziak, *SOLAR*, CIKM 2025 | arXiv:2509.00710 |
| Guha et al., *LegalBench*, NeurIPS D&B 2023 | arXiv:2308.11462 |
| Hendrycks et al., *CUAD*, NeurIPS D&B 2021 | DOI 10.5281/zenodo.4595826 |
| Koreeda & Manning, *ContractNLI*, Findings EMNLP 2021 | arXiv:2110.01799 |
| Wilson et al., *OPP-115*, ACL 2016 | — |
| Arora et al., *MAPP*, LREC 2022 | ACL 2022.lrec-1.585 |
| *RuleArena*, ACL 2025 | arXiv:2412.08972 |
| *RIRAG / ObliQA* | arXiv:2409.05677 |
| *ContractEval*, NLLP 2025 | arXiv:2508.03080 |
| *ACORD* | arXiv:2501.06582 |
| Holzenberger et al., *SARA* | arXiv:2005.05257 |
| *PrivacyGLUE*, Applied Sciences 2023 | DOI 10.3390/app13063701 |
| *PolicyQA* / *PLUE* | arXiv:2010.02557 / arXiv:2212.10011 |
| Andow et al., *PolicyLint*, USENIX Security 2019 | — |
| Merigoux, Chataing & Protzenko, *Catala*, ICFP 2021 | arXiv:2103.03198 |
| LegalRuleML Core v1.0, OASIS Standard (30 Aug 2021) | — |
| Symboleo (IEEE RE 2020; SoSyM 2022) / Symboleo2SC (SoSyM 2024) | — |
| Hublet, Kvamme & Krstić, *Enforceable GDPR Specification* | arXiv:2402.17350 |
| *GraphCompliance* | arXiv:2510.26309 |
| Baldwin & Ghanavati, *KG for LLM Policy Compliance Reasoning* | arXiv:2604.27713 |
| Pan et al., *Logic-LM*, Findings EMNLP 2023 | arXiv:2305.12295 |
| *ProMoAI* | arXiv:2403.04327 |
| *BIRD* (text-to-SQL) | arXiv:2305.03111 |
| *Reasoning-SQL* (RL for text-to-SQL) | arXiv:2503.23157 |
| LLM-CEGIS program repair, AAAI 2025 | arXiv:2502.07786 |
| *Tulu 3* (RLVR) | arXiv:2411.15124 |
| *CPGPrompt* (clinical guidelines → executable) | arXiv:2601.03475 |
| MT + LLM survey / *METAL* | arXiv:2605.13898 / arXiv:2312.06056 |
| Annotation errors in text-to-SQL benchmarks | arXiv:2601.08778 |
| Knowledge-driven hallucination in process modeling | arXiv:2509.15336 |
| OECD, *Cracking the Code* (Rules as Code) | OECD Working Papers on Public Governance No. 42 |
