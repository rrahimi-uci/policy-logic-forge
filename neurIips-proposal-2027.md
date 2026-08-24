# NeurIPS 2027 Research Proposal — v3 (literature-grounded, review-applied)

> **v3 changes.** A repository-grounded review (preserved verbatim in §24) raised
> 13 blocking concerns. All 13 were verified against this repo's code and the
> cited papers, and all 13 are applied. Two are applied with an added
> consequence the review did not state — see the disposition table in §25. The
> net effect is a **scope cut**: the primary deliverable is now Dutch-corpus
> reproduction + compiler correctness + instrument validation + one non-Dutch
> domain, which **moves the primary target track from main to Datasets &
> Benchmarks** (§25, D2).

**Working title:** *Verified Compilation of Normative Text: Instrument Validation,
Assumption-Explicit Semantics, and Solver Rewards for Document-to-Logic Extraction*

**Umbrella project name:** **LEXEC** — compile normative documents into executable
decision logic, and use the compiler as the measuring instrument.

| | |
| --- | --- |
| Target venue | **Datasets & Benchmarks track (primary, post-scope-cut); main track only if CEGIR and solver-reward RL both land (§25, D2). Verify the 2027 track names — do not assume "Datasets & Benchmarks" persists.** |
| Target deadline | **Confirmed: NeurIPS lists 2027 — Europe. Not confirmed: the month, the dates, the CFP, or the track list. "December 2027" is a historical expectation, not an announced date.** Recent deadlines were May 6 (2026), May 16 (2025), May 22 (2024); plan for ~May 1, 2027 and re-verify. |
| Time available | ~8.5 months from 2026-08-24 |
| Substrate | This repository: 10-stage extraction pipeline, v2 *candidate* rule contract, four-invariant readiness gate, claim-level grounding verifier, deterministic DAG **node**-coverage partition, and **four corpus input adapters + prompt packs — not four benchmark results** (no label loaders, query builders, splits, scoring code, or run manifests exist; `pytest` 770 passed makes no model calls and tests fixed graphs/prompts). See §24 R1. |
| Status | Proposal for discussion. `(measured)` = a real run. `(target)` = pre-registered success criterion. `(published)` = a number from cited prior work, verified against the source. `(verified-in-code)` = checked against this repo at commit time. |
| Filename | `neurIips-proposal-2027.md` preserves a typo from the original request and is **deliberately retained as a compatibility path** so existing links do not break; the companion plan uses the correct `neurips-plan-2027.md`. Rename before this becomes a cited artifact. |

---

## TL;DR

**The claim.** Compile a normative document into an executable decision artifact
and extraction quality becomes *decidable* — so you can measure it, verify it
with a solver, and train on the solver's verdict instead of a judge's opinion.

**The problem it solves.** There is no gold DMN for real contracts, and even
where one exists, correctness is invariant under renaming, reordering, and table
splitting — so form-matching metrics measure style, not meaning. Judge behavior
instead: what does the artifact *decide*?

**Four pieces**, in dependency order:

1. **LEXEC-Verify** — an LLM-free compiler (v2 rule contract → DMN 1.3/FEEL,
   SMT-LIB, reference interpreter) plus a solver layer deciding co-firing
   conflict, subsumption, vacuity, coverage gaps, equivalence, and
   UNIQUE-safety. We found no prior work applying these over LLM-extracted
   rule sets at corpus scale (§21 states the search protocol). → §7
2. **Instrument validation** (the spine) — does a *gold-free* decision metric
   predict *gold-artifact* outcome equivalence? The 95-model Dutch DMN corpus
   makes it checkable. If yes, every gold-free result inherits credibility; if
   no, that finding should change how this subfield evaluates itself. It is also
   the one contribution that does not depend on publishing first. → §9
3. **Assumption-explicit compilation** — gold legal labels smuggle in unstated
   assumptions (**71** ContractNLI entailments flip to neutral under strict
   logic *(published)*). So the artifact emits a verdict *plus* the minimal
   assumption set it needed, and the solver checks each assumption is
   necessary. → §10
4. **Solver-reward RL + counterexample-guided repair** — the verifier becomes a
   programmatic reward; solver witnesses drive repair. Target: an 8–14B open
   model beating a frontier prompted model on decision agreement at equal
   coverage. → §12

**Scope, after review (§24 R13, §25 D2).** Pieces 1–2 plus one non-Dutch domain
are the **minimum paper**; pieces 3–4 are earned, not planned. That cut moves the
primary target to **Datasets & Benchmarks**, with main track available only if
the RL result lands. Also cut to follow-on work: LEXEC-Perturb, three of four
compilation backends, cross-lingual and cross-jurisdiction transfer, and four of
six corpora as *evaluated* resources.

**Two defects gate everything** (§12.4, both confirmed in code). A "full corpus"
run reads at most 16 batches of character-truncated, length-sorted chunks; and
the optimizer still feeds itself the legacy prose fields the v2 prompts forbid,
so dependency-edge recall is unmeasured. Until those are fixed, every
corpus-level denominator is wrong. **G0 is a bug fix, not research, and it comes
first.**

**Why it is worth doing now.** The closest published work sits at **42.6%**
macro-averaged outcome equivalence *(published)* — the task is wide open. And
every fallback is still a paper: if compilation does not generalize, the compiler
becomes a *diagnostic* and the paper is a decidable taxonomy of why
document-to-logic extraction fails (§20).

**Three things this proposal explicitly does *not* claim**, after checking the
literature: that gold artifacts never exist (§1.1), that ContractNLI-as-SMT-entailment
is new (§1.2), or that metamorphic evaluation by formal equivalence is new
(§1.3). What is left after those cuts is narrower and better defended.

---

## 0. The one-sentence claim (revised)

> Compiling a normative document into an executable decision artifact makes
> extraction quality *decidable* — and once you can decide it, you can
> **calibrate** the metric against real gold artifacts, **name** the unstated
> assumptions the gold labels smuggle in, and **train** on a solver's verdict
> instead of a judge's opinion.

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
| **C1** | **LEXEC-Verify** — LLM-free compiler (v2 rule contract → DMN 1.3/FEEL, SMT-LIB, reference interpreter) + solver layer deciding row disjointness, subsumption, equivalence, co-firing conflict, coverage gaps, vacuity, entailment | ContractCheck (manual blocks, one SPA); PolicyGuard (Z3, contract-vs-policy review); Graus (executor, **no solver checking**) | Solver-decided *internal* consistency of **LLM-extracted** rule sets at corpus scale; witness extraction for repair; UNIQUE-safety proofs |
| **C2** | **Instrument validation** — does gold-free decision agreement predict gold-artifact outcome equivalence? | None found (§21 search protocol) | Calibrates the metric the whole no-gold methodology rests on (§9). **The primary contribution, and the one that does not depend on publishing first.** |
| **C3** | **Assumption-explicit compilation** — the artifact emits the minimal assumption set needed to reach the pragmatic answer; measure necessity/minimality | *Know Your Limits* documents the gap and names "assumption-surfacing tools" as future work | Turns a measured negative result into a compilation requirement and a metric |
| **C4** | **LEXEC-Bench** — decision-level benchmark; **scope-cut to 2 corpora for the minimum paper** (§25 D2) | LegalBench (162 tasks, label-level); PrivacyGLUE (7 tasks); ObliQA (27,869 questions); ContractEval; RuleArena | We found no *extensional, artifact-level* benchmark for normative documents; scale and breadth are the delta, stated as a bounded absence claim |
| **C5** | **CEGIR + solver-reward RL** | LLM-CEGIS repair (AAAI 2025, arXiv:2502.07786); Logic-LM self-refinement; RLVR for SQL/IE/structured output | Counterexamples from *cross-rule* consistency inside one extracted artifact (no external spec, no gold artifact); reward is a solver verdict on the artifact's *denotation* |
| **C6** | **Two findings**: (a) LLM grounding-verification is miscalibrated on this task; (b) surface metrics are weakly predictive of decision agreement across four domains | *Know Your Limits* (scope laundering, faithfulness); Graus (structure vs. outcome) | (a) is unclaimed and we have striking `(measured)` n=1 evidence; (b) becomes a *replication at corpus scale across domains*, honestly framed |

---

## 5. Formal setup

**Objects.** Document *d*; extraction *R* = *f*(*d*); compiler *γ*; artifact
*A* = *γ*(*R*) with semantics ⟦*A*⟧.

**Rules.** Each *r* ∈ *R* is ( *V*, *C*, *X*, *O*, *σ*, *π* ): typed variables
*V* (number/boolean/enum/date/date_time/duration/string/list; role ∈
{input, derived, output}); condition *C* over predicates with operators
`== != < <= > >= in not_in`; defeaters *X*; output assignments *O* (`=` only);
scope *σ*; hit policy *π* ∈ {UNIQUE, FIRST, PRIORITY, COLLECT, ANY}. This is the
repository's existing v2 contract (`utils/rule_contract.py`), not a new one.

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

**Fragment — corrected (§24 R4).** v2 defines **8 operators**, **1 output
operator**, **8 variable types** (`number`, `boolean`, `enum`, `date`,
`date_time`, `duration`, `string`, `list`) and **10 value types** — the variable
types plus `range` and `variable_reference` *(verified-in-code:
`utils/rule_contract.py`)*. v2 of this proposal said "7 value types" and then
called the fragment linear arithmetic. Both were wrong.

Only a strict subset is linear arithmetic over integers/rationals + finite enums
+ equality. `date`, `date_time`, and `duration` need an explicit temporal theory
(or a total order plus a unit-normalisation rule); `string` needs equality-only
treatment with a declared collation; `list` and `range` need container and
interval theories; `variable_reference` needs global symbol resolution and an
acyclicity check. **The supported subset is a deliverable, not an assumption**
(§26 IR-1), and every construct outside it must produce a *measured refusal*
rather than a silent projection. The bounded FEEL renderer **fails loudly**
outside the subset; silent coercion would contaminate the measurement.

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
compilation**, always paired with DA and EY, never alone. Reporting it requires
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

## 8. LEXEC-Bench: six resources, four modes, no new gold artifacts

| Resource | Scale (verified) | Mode | Gold |
| --- | --- | --- | --- |
| **Dutch DMN corpus** (Graus, ICAIL 2026, CC BY 4.0) | 95 production DMN models + legal text; 58 executable; harness included | **Gold-artifact anchor** | Real DMN + outcome equivalence |
| **ContractNLI** (Koreeda & Manning, Findings EMNLP 2021) | 607 NDAs × 17 hypotheses, 3-way labels + evidence spans | Entailment (assumption-explicit, §10) | Expert labels; **plus 400/610 strict-entailment re-annotations from arXiv:2606.16118 if obtainable** |
| **CUAD** (Hendrycks et al., NeurIPS D&B 2021) | 510 contracts, 41 categories, 13k+ spans, 20,910 QA pairs | Presence/value | `master_clauses.csv` normalized answers |
| **OPP-115** (Wilson et al., ACL 2016) | 115 policies, 3,792 segments, ~23k practices | Practice decision | Consolidated majority-vote annotations |
| **MAPP** (Arora et al., LREC 2022) | 64 EN (292k words) + 91 DE (478k words); 8k + 19k practices; GDPR/CCPA-aware scheme | Practice decision, **cross-lingual** | Bilingual annotations |
| **ObliQA / RegNLP** (arXiv:2409.05677) | 27,869 obligation-centric questions over ADGM financial regulation (40 docs, ~640k words) | Obligation entailment | Question–passage pairs; RePASs contradiction metric |

**Scenario mode** (fact bindings) draws on, in decreasing order of trust: the
rules' own `source_attested` test vectors; solver-generated boundary bindings
per P3; and ~500 human-authored scenarios on a stratified sample, with reported
agreement.

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

*Rewritten per §24 R8, which was correct on every factual point and understated
two of them.*

**The question.** Every gold-free extensional metric assumes that agreeing with
query answers means having built the right artifact. We found no prior work that
tests this assumption (§21 states the search protocol; this is a bounded
absence claim, not a "nobody has"). The Dutch DMN corpus makes it testable
because it has both the artifact and the behavior.

### 9.1 The anchor study's actual protocol, which we must match

Verified against arXiv:2604.17153 directly *(published)*:

| Fact | Value | Why it changes our design |
| --- | --- | --- |
| Models released | 95 | but not all are usable |
| Models used for outcome equivalence | **58** (24 Outcome + 34 Requirements) | the other 37 lack alignable interfaces — **we evaluate on 58, not 95** |
| Testable input variations | **13,080**, exhaustive per model | exhaustive enumeration is the protocol; P3′ cannot replace it (§6) |
| Runs per condition | **5 independent runs** (varying only the sampled example) | 1,900 generations total (95 × 4 × 5) |
| 42.6% / 60.4% | **macro-averaged across all 5 runs** | this is the number to compare against |
| 33% full equivalence, 50% ≥90% | **best-run per model** (19/58 and 29/58) | a *different estimator* — never compare our mean to their best-of-5 |
| `+io` condition | I/O specs **derived from the gold models** | a gold-leaking condition; a raw-text pipeline is not comparable to it |

Two consequences v2 of this proposal got wrong: it said "run the pipeline on the
95 documents," and it proposed beating 42.6%/60.4% without matching either the
information condition or the run-selection rule. Both are corrected below.

### 9.2 Preregistered analysis plan

- **Estimand.** The association between per-model gold-free DA and per-model
  gold-based OE, on the 58 testable models, pooling all runs.
- **Sampling unit.** The **decision model** (equivalently, the document), not the
  query and not the run. Queries are nested in models; runs are repeated
  measures on a model.
- **Model.** A mixed-effects / hierarchical bootstrap with a random intercept per
  model, so unequal scenario counts and 5 repeated runs are not treated as
  independent observations.
- **Primary estimate.** Spearman ρ(DA, OE) with a hierarchical bootstrap CI.
  **Null:** ρ = 0. **Minimum useful effect:** ρ ≥ 0.6 with the CI lower bound
  above 0.3 — declared before looking.
- **Run retention.** *All* stochastic runs are retained and reported. Any
  best-of-*k* figure is labeled as such and compared only against the anchor's
  own best-of-5 figure.
- **The 37 excluded models** are reported as an explicit exclusion with the
  reason, not dropped silently, and we report whether our pipeline can produce
  artifacts for any of them (an interface-adequacy finding in its own right).
- **Disagreement review.** Structured false-positive (DA high, OE low) and
  false-negative (DA low, OE high) analysis, with a taxonomy — this is the part
  most likely to be the paper's most useful figure.

### 9.3 Gold-hidden query generation (frozen before any result is looked at)

The instrument is worthless if the queries leak the gold artifact. Frozen
protocol:

1. Queries are generated **only** from the source legal text and our own
   extracted rule set — never from `gold_models/`, never from the gold I/O
   specification, never from gold threshold values.
2. Generation runs in a process with no filesystem access to the gold directory;
   the harness asserts this.
3. **The gold answer for a gold-free query comes from executing the gold model on
   that query's binding** — the gold artifact supplies the *label*, but never the
   *query*. This is the distinction v2 failed to make, and it is what makes the
   comparison meaningful rather than circular.
4. A leakage audit: for a held-out sample, check that no generated query's
   threshold values coincide with gold thresholds more often than chance.

### 9.4 Matched-information comparison

We report our system under **matched conditions only**: raw-text vs. Graus's
`text`; our-own-derived interface vs. Graus's `text`; and, separately and
labeled as gold-leaking, gold-I/O-supplied vs. Graus's `+io`. **We do not claim
a win over 42.6%/60.4% from a raw-text run.** If solver-checked compilation only
beats the `text` condition, that is what gets claimed.

### 9.5 Why this is the paper's spine

If gold-free DA tracks gold-based OE, every result on the corpora *without* gold
artifacts inherits warranted credibility. If it does not, that finding should
change how this subfield evaluates itself. Both outcomes are publishable — but
"metric failure is publishable" is a *possible* outcome to plan for, **not a
guaranteed acceptance argument**, and §20 treats it that way.

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

| Needed | Status |
| --- | --- |
| v2 typed rule contract + validator, closed enums | ✅ `utils/rule_contract.py` |
| Four-invariant hard gate | ✅ `agents/agent_07_executable_readiness.py` |
| Claim-level grounding certification | ✅ `agents/agent_09_grounding_verifier.py` (6 of 12 claim types LLM-verified; rest structural) |
| DAG partition, 100% coverage, SCC condensation | ✅ `utils/dag_builder.py` |
| Selective-prediction machinery (`readiness`, `unresolved`) | ✅ `utils/readiness.py`, `utils/kg_readiness.py` |
| DMN/BPMN *projection* | ⚠️ 12-line column manifest (`_project_execution`) — a hint, not a model |
| DMN 1.3 XML / FEEL renderer + evaluator | ❌ |
| SMT-LIB backend + the seven queries | ❌ |
| Vector-replay conformance gate | ❌ |
| Metamorphic harness | ❌ |
| Assumption extraction/minimization | ❌ |
| RL environment wrapping the verifier | ❌ |
| Corpus **input adapters** (download + normalise), checksummed | ✅ `benchmarks/` (4; +2 to add) |
| Corpus **label loaders, query builders, fixed splits, scoring code, run manifests** | ❌ **none exist** *(verified-in-code: `benchmarks/` holds only `README.md`, `datasets.json`, `.gitignore`, and two download/normalise scripts)* |
| Document/chunk-complete extraction | ❌ **broken** — see §12.4 |
| v2-aware deduplication and dependency analysis | ❌ **broken** — see §12.4 |

**Corrected summary (§24 R1).** The extraction half is *implemented and covered
by 770 provider-free tests that make no model calls and exercise fixed graphs
and prompt files* — which establishes engineering invariants, **not scientific
readiness, and not a single completed end-to-end benchmark run**. "Four
benchmark-backed domains" means four input adapters and four prompt packs. Live
pipeline runs will be reported separately from the test suite, and every corpus
needs a deterministic evaluation contract — document IDs, gold-query
construction, frozen train/dev/test boundaries, metrics, and immutable run
manifests — before any DA, EY, defect-density, or cost number is quoted (§26
BENCH-1..3).

### 12.4 Two pipeline defects that invalidate corpus-level claims

Both were raised in §24 (R2, R3) and both are confirmed in code. Neither is a
research risk — they are bugs that make the *denominators* wrong, so they gate
everything.

**D-1 — a "full corpus" run does not read the full corpus.**
`agents/agent_03_rules_extractor.py::read_text_files_batch()` truncates every
organized chunk to `max_content_length` (**8,000 characters** by default, line
195), sorts chunks by word count **descending** (line 205), and then returns only
`min(len(batches), target_rules_count // rules_per_batch + 10)` batches (line
240). With the CLI default `--target-rules 30` and `rules_per_batch_openai: 5`,
that is **at most 16 batches regardless of how many documents were organized**
*(verified-in-code)*. The sample is biased toward the longest chunks, and because
Agent 1 chunks by ~2,000 *words* while Agent 3 clips by *characters*, long chunks
lose trailing content before extraction.

*Consequence:* `benchmarks/README.md`'s "each command above is one full corpus as
one batch" is not what happens, and DA / EY / defect-density / cost denominators
are ambiguous until fixed.

*Required before G1:* **one artifact per gold document** (or an explicitly frozen
multi-document unit), every chunk of that unit processed, chunk coverage
recorded, and the run **failed** if any required chunk is skipped or truncated.
`target_rules` may cap a pilot; a capped run must never be scored as corpus
coverage.

**D-2 — the optimizer's v2 handoff is broken.** The domain prompts explicitly
forbid the legacy prose fields `conditions` / `consequences`, yet
`agents/agent_06_knowledge_graph_optimizer.py` builds its LLM summaries from
exactly those fields in `_deduplicate_rules_single()` (lines 349–350),
`analyze_dependencies()` (536–537), and both batched dependency paths (706–707,
768–769) *(verified-in-code)*. For v2-only rules the optimizer sees a **truncated
description, type, and entity attachments** — not the predicates, Boolean logic,
outcomes, scope, or exceptions the proposed solver semantics depend on. The
cross-batch pass is also deliberately partial: it samples
`min(20, batch_size // 4)` (~25%) of each batch and caps batch pairs at **20** by
default (lines 737–751).

*Consequence:* dependency-edge **recall** is unmeasured and probably poor. This
undermines CEGIR's cross-rule witnesses, the cross-reference perturbation
relation, the semantic-dedup baseline, and §16's inherited edge-type counts.
`utils/dag_builder.py` guarantees 100% **node** coverage of whatever edges it is
handed — it guarantees nothing about edge recall or semantic correctness, and
condensing a cycle preserves nodes without producing a valid order inside the
cycle. **"DAG partition coverage" and "dependency discovery coverage" are
different claims and are kept separate from here on.**

*Required before using any graph result:* pass full v2 fields to the optimizer,
make candidate-pair generation deterministic and recall-auditable, and measure
dependency precision/recall against a human-reviewed fixture.

---

## 13. Metrics

| Metric | Definition |
| --- | --- |
| **DA** | Decision Agreement: `E_q[1(⟦A⟧(q) = gold(q))]` — primary |
| **OE** | Outcome Equivalence vs. gold DMN artifacts (Graus protocol; §9) |
| **EA_strict / EA_assumed / AM** | assumption-free accuracy, assumption-augmented accuracy, assumption minimality (§10) |
| **EY** | Executable Yield: fraction of documents producing a compiled, gate-passing artifact |
| **S-DA@c, AURC** | selective decision agreement at coverage *c*; risk–coverage summary |
| **SR / SE / SDI** | invariance rate, correct-change rate, `SR + SE − 1` |
| **PP** | Provenance Precision vs. expert evidence spans (free from ContractNLI/CUAD) |
| **CQI** | Cross-Query Inconsistency; **0 by construction** for compiled artifacts (P4) |
| **VR** | Vector Replay on the *emitted* artifact |
| **Defect density** | solver-detected conflicts / gaps / vacuities per 100 rules |
| **Cost** | USD + tokens to *build* an artifact; USD per query to *use* it |

DA and EY trade off, so neither is ever reported alone: every table gives
(DA, EY) jointly or an S-DA@c curve.

### 13.1 Statistical analysis plan (§24 R11)

v2 listed a dozen metrics across corpora, model families, target languages,
repair rounds, and ablations, and treated "pre-registered targets" as if that
handled inference. It does not: it addresses neither multiplicity, stochastic
model variance, document clustering, nor best-run selection.

**One primary endpoint.** ρ(gold-free DA, gold-based OE) on the 58 Dutch testable
models (§9.2). Everything else is confirmatory or exploratory.

**Three confirmatory endpoints**, fixed in advance, with family-wise error
controlled at α = 0.05 by Holm–Bonferroni across exactly these three:

1. DA of solver-checked compilation vs. the matched raw-`text` condition.
2. DA of CEGIR vs. no-CEGIR, paired by document.
3. AURC of solver-signal selective compilation vs. the ported grammar-entropy
   baseline.

**Everything else — target-language ablation, cross-domain/lingual transfer,
SDI, CQI, cost, defect density, the dissociation studies — is exploratory and
labeled as such in every table.** No exploratory result carries a target.

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
4. **Direct-to-Python.** Code LLMs are strong here; this baseline may win on DA,
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
(defeasible-native). Report DA, EY, defect density per target. *Which formal
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

---

## 15. Pre-registered headline table

Now anchored to *published* numbers rather than invented ones.

| Result | Reference point (published) | Target |
| --- | --- | --- |
| Outcome equivalence, Dutch corpus (Outcome / Requirements models) | **42.6% / 60.4%** (Graus, best condition, GPT-5.1, 1-shot) | **≥ 55% / ≥ 70%** with solver-checked compilation + CEGIR |
| Models reaching full outcome equivalence | **33%** | **≥ 45%** |
| Instrument validation: ρ(gold-free DA, gold-based OE) | none exists | **≥ 0.6**, with the disagreement cases characterized |
| ContractNLI, strict-entailment accuracy | **83.0%** (Claude, LLM-based formal reasoning) | ≥ comparable *from a compiled artifact*, at ≥ 90% EY |
| Assumption minimality | none exists | ≥ 80% of declared assumptions provably necessary |
| Scope-laundering analogue in our loop | **15.3–52.5%** in LLM self-reported formal reasoning | **0 by construction** (compiler makes no LLM calls) — a design claim, verified by audit |
| Selective prediction: AURC vs. grammar-entropy UQ | **AUROC > 0.93** on logic tasks (NeurIPS 2025) | beat it on document-scale extraction |
| ρ(span-F1, DA) — the dissociation | Graus: structural similarity ≈ 0.43 alongside outcome equivalence ≈ 0.43 | **< 0.4**, replicated on ≥ 3 domains |
| Grounding-verifier / vector-replay **dissociation** (not a calibration result — §24 non-blocking) | ours, n=1: **98% flagged vs. 6% self-vector-replay failure** | dissociation **≥ 5×**, replicated across ≥ 3 domains and ≥ 3 verifier models, **and** an independently-labeled grounding-truth set built before it is called miscalibration |
| RuleArena head-to-head | LLMs "perform poorly"; tools help | compile-then-execute **≥ +15 points** over in-context application |
| CEGIR gain | — | **+6–12** DA points |
| Solver-reward RL over SFT | — | **+5–10** DA points; 8–14B ≥ frontier prompted |
| SDI, best system | — | **< 0.7** (benchmark not saturated) |
| CQI, compiled vs. long-context QA | — | **0 vs. > 5%** |
| Conflict density, before vs. after CEGIR | — | **≥ 60%** reduction |
| Amortized cost at N = 10³ | — | **≥ 100×** cheaper, with caching enabled for the baseline |

---

## 16. Preliminary evidence in hand, and its limits

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

## 17. Timeline — rebuilt around the review's go/no-go sequence (§24 R13)

v2 asked, in ~8.5 months, for: external reproduction; a compiler, interpreter,
and four backends; six corpus adapters; a new annotated perturbation suite; 500
human scenarios; CEGIR; multi-model studies; four transfer studies; and 2–4 RL
runs — with **zero completed end-to-end benchmark runs** behind it. That was not
a schedule. The review's sequence is adopted, and **G0 is new**: the measurement
unit has to be real before anything is measured.

| Phase | Months | Work | Gate |
| --- | --- | --- | --- |
| **G0 — make the measurement unit real** | Sep–Oct 2026 | Fix D-1 (per-document unit, full chunk coverage, fail-on-skip) and D-2 (full v2 fields into the optimizer; deterministic, recall-auditable pair generation). Publish **compiler IR v1** with the supported subset, typed scope, modality, exception logic, derived expressions, global symbol resolution, table grouping, and null/missing semantics. Deterministic label/query adapters + immutable run manifests for the Dutch corpus and one non-Dutch corpus. | Chunk coverage = 100% on a frozen unit, or the run fails; dependency precision/recall measured on a human-reviewed fixture; every unsupported construct produces a measured refusal |
| **G1 — reproduce before extending** | Nov 2026 | Reproduce Graus's published protocol on **his** harness: 58 testable models, 4 conditions, **5 runs each**, 13,080 input variations, macro-averaged. | Our reproduction matches his reported numbers within CI. *Nothing downstream is trusted until this passes.* |
| **G2 — validate the compiler** | Nov–Dec 2026 | Differential testing: reference interpreter vs. SMT encoding vs. **one real third-party DMN engine**, on generated and corpus tables. Retain exhaustive enumeration (P3 is withdrawn; P3′ is a comparison theorem only). Hit-policy proof obligations implemented per revised P2. | Three backends agree on 100% of a generated conformance suite; every disagreement is root-caused |
| **G3 — validate the instrument** | Dec 2026–Jan 2027 | Freeze the gold-hidden query protocol (§9.3) and the statistical plan (§13.1) **before** looking at results. Estimate ρ(DA, OE) with hierarchical uncertainty; structured disagreement review. | Primary endpoint estimated with a CI; minimum useful effect declared in advance was ρ ≥ 0.6, CI lower bound > 0.3 |
| **G4 — choose the paper from the result** | Feb 2027 | If G3 succeeds: add **one** non-Dutch domain (ContractNLI, with §10 assumption-explicit compilation) + CEGIR. If G3 fails: write the diagnostic paper (§20 Plan B). | A decision, recorded, with the evidence |
| **G5 — method, only if earned** | Mar 2027 | Solver-reward RL **only if** an omission-resistant, held-out, adversarially-tested reward already survives §12.2's degenerate-policy gate. | Degenerate policies score worse than the honest baseline; then and only then, train |
| **Freeze + write** | Apr 2027 (freeze **Apr 15**) → submit ~May 1 | Writing, figures, artifact release, reproducibility checklist, broader impact. | — |

**Explicitly moved to follow-on work** (§24 R13): LEXEC-Perturb and its
annotation programme; three of the four target-language backends
(SMT-LIB is retained because G2 needs it; Python/ASP/Datalog are cut);
cross-lingual (MAPP German) and cross-jurisdiction transfer; the cross-task
(clinical/benefits) study; ObliQA, CUAD, OPP-115, and MAPP as *evaluated*
corpora; and the 500 human-authored scenarios. Each returns only if its
prerequisite gate passes early.

## 18. Budget, separated by line (§24 R13)

v2 gave one `$15k–$30k` figure "presented mainly as extraction spend" and did not
reconcile GPU weeks, annotation, or engineering time. Separated, with the
scope-cut scope:

| Line | Minimum paper (G0–G4) | Full programme (adds G5 + follow-ons) |
| --- | --- | --- |
| **API / inference** | Dutch 95 docs × 4 conditions × 5 runs, plus one non-Dutch corpus subsample (~150 docs) and CEGIR rounds → **$4k–$9k** | four-corpus sweeps, multi-model, ablations → **$15k–$30k** |
| **GPU** | none (no RL in the minimum paper) | 8×H100 × 1–2 weeks × 2–4 runs ≈ **600–1,300 GPU-hours**, plus false starts → **$8k–$25k** at commodity rates, or a cluster allocation |
| **Solver / CPU** | modest, but the RL bottleneck later — cache by rule-set hash, bound row counts, time-box calls and report the timeout rate | a solver farm; budget separately from GPU |
| **Annotation** | ~500 scenario validations + a stratified assumption-admissibility review → **~60–90 hours** | + LEXEC-Perturb 1.5–2k items at 2–4 min, 20% double-annotated → **+120–160 hours**, 2–3 qualified annotators at fair disclosed rates |
| **Storage / artifacts** | run manifests, all 5 runs retained per condition, generated artifacts → tens of GB | hundreds of GB with RL rollouts |
| **Engineering time** | **the dominant cost, and previously unbudgeted**: G0 alone is two pipeline fixes, a compiler IR, two backends, adapters, and a manifest system | + RL environment, four backends, perturbation tooling |

Hard cap plus per-experiment cost logging from day one. The repo's adaptive
global rate limiter already makes concurrent batch runs safe.

---

## 19. Risks and mitigations

| Risk | Severity | Mitigation |
| --- | --- | --- |
| **D-1: corpus-level denominators are wrong today** — a "full corpus" run reads ≤16 batches of truncated, length-sorted chunks | **Blocking** | G0 / PIPE-1..2 before any measurement; fail-on-skip; a capped pilot is never scored as coverage (§12.4) |
| **D-2: dependency-edge recall is unmeasured** — the optimizer reads forbidden legacy fields and samples ~25% of each batch | **Blocking** | G0 / PIPE-3..4; report dependency precision/recall on a human-reviewed fixture; keep DAG node coverage separate from discovery coverage (§12.4) |
| **Zero completed end-to-end benchmark runs behind the plan** | **High** | The minimum paper is defined so that one reproduction + one instrument-validation result is publishable (§25 D2) |
| **Someone publishes the solver-reward RL first.** Wang et al. named it as future work in June 2026 (and separately proposed the MCS idea §10 builds on). | **High** | Move C5 earlier if G3 lands early; and make C2 (instrument validation) the paper's spine, since it does not depend on the method being first |
| **Extraction quality, not compilation, is the bottleneck** — garbage rules compile perfectly | **High** | The benchmark is the primary contribution; a rigorous "nobody can do this yet" is publishable. Graus at 42.6% already establishes headroom |
| §16's numbers don't replicate off-mortgage | High | G2; Plan B ready (§20) |
| **The gold-free metric doesn't track gold-based OE** (§9 fails) | **High** | That *is* a publishable finding, and it redirects the paper to Plan B. But it must be discovered in Nov 2026, not April 2027 |
| Direct long-context QA simply wins on DA | High | Pre-committed: report it; pivot to PP/CQI/amortization, all pre-registered. Do not hide it |
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
- **Plan C (if RL doesn't beat SFT).** Datasets & Benchmarks track: LEXEC-Bench +
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

## 23. Immediate next four weeks — reordered to G0 (§24 R13)

v2 put "clone the Dutch repo" first. The review is right that this is second: a
reproduction is only interpretable once our own measurement unit is real. Both
still fit in four weeks because item 1 is a bug fix, not research.

1. **Fix D-1 (chunk/document coverage).** Make the extraction unit one gold
   document; process every chunk; record coverage; fail the run on any skip or
   truncation. Add a regression test that a 40-chunk unit yields 40 processed
   chunks regardless of `--target-rules`. *This is the single highest-value
   change in the list, because every corpus-level number depends on it.*
2. **Fix D-2 (v2 optimizer handoff).** Pass `condition_predicates`,
   `condition_logic`, `outcomes`, `variables`, `applicability_scope`, and
   `exceptions` into the dedup and dependency summaries instead of the forbidden
   `conditions`/`consequences`. Make pair generation deterministic. Add a
   human-reviewed dependency fixture and report precision/recall.
3. **Clone and reproduce `github.com/opengov-lab/legal-text-to-decision-model`** —
   58 models, 4 conditions, 5 runs, 13,080 input variations, macro-averaged.
   External, cheap, decisive. Nothing downstream is trusted until this matches.
4. **Draft compiler IR v1** (§26 IR-1) with an explicit supported subset, and a
   refusal path that is *counted*. Then `utils/feel.py` + `utils/dmn_builder.py`
   in the repo's dependency-free, unit-tested style. Constraint verified in code:
   `tests/test_inter_agent_contract_alignment.py` pins `_project_execution`'s key
   set to what `final_rule_issues` reads, so the compiler sits strictly
   downstream and treats `execution` as read-only.
5. **Run our pipeline on the Dutch 58** through their harness, matched to the
   `text` condition only, and report an honest first OE number.
6. **Resolve the defeater semantics empirically** on the Dutch corpus — it has
   gold behavior to check against, which our own self-generated vectors do not.
7. **Email the arXiv:2606.16118 authors** about the 400/610 strict-entailment
   re-annotation, and ask whether they are pursuing the solver-feedback training
   direction they list in §5.6 (this is the scooping risk in §19, and asking is
   cheaper than guessing).
8. **Citation-verification pass** on the items Appendix B still lists as
   unverified (MAUD, SatLM, LINC, CheckList, Spider).

**Deliberately *not* in the next four weeks**, and previously were: LEXEC-Perturb
annotation logistics, three of four target-language backends, any RL work, and
the four non-Dutch evaluated corpora.

---

## 24. Review — repository-grounded comments and concerns (2026-08-24)

*Preserved verbatim, unedited. Disposition of every item is in §25; the work each
item requires is in §26.*

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
is not a document-complete extraction. In addition, Agent 1 targets roughly
2,000-word chunks while Agent 3 clips by characters, so long organized chunks can
lose substantial trailing content before extraction.

This invalidates the current reading of “run one full corpus as one batch,” and
would make cross-domain DA, EY, defect density, and cost denominators ambiguous.

**Required before G1:** execute one model/artifact per gold document (or define an
explicit, frozen multi-document unit), process every chunk for that unit, record
chunk coverage, and fail the run if any required chunk is skipped or truncated.
`target_rules` may cap a pilot, but a capped run must not be scored as corpus
coverage.

#### R3. The optimizer's v2 handoff is broken for both deduplication and dependency analysis

Agent 3's compact prompts explicitly forbid the legacy prose fields
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
one numeric input appear in one `boundary_condition: true` vector, and Agent 5.7
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

Each item is a prerequisite named by §24, with an owner-sized unit of work and an
acceptance test. This is the bridge to `neurips-plan-2027.md`.

**Pipeline correctness (blocks everything)**

- **PIPE-1** — per-document extraction unit; every chunk processed; coverage
  recorded; fail on skip/truncation. *Accept:* a 40-chunk document yields 40
  processed chunks at any `--target-rules`.
- **PIPE-2** — reconcile Agent 1's word-based chunking with Agent 3's
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
| **OE / DA** | gold-based Outcome Equivalence / gold-free Decision Agreement — the two sides of §9 |

## Appendix B — Provenance of every claim

**Verified in code while applying the §24 review (2026-08-24):**
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

**Verified by reading this repository's code (2026-08-24):** the v2 contract's
closed enums (`utils/rule_contract.py`); the four invariants and
`_project_execution` (`agents/agent_07_executable_readiness.py`); which grounding
claim types reach the LLM verifier vs. are structural
(`agents/agent_09_grounding_verifier.py`, `MODEL_CLAIM_TYPES`); the DAG partition
and SCC condensation (`utils/dag_builder.py`); readiness/selective-prediction
(`utils/readiness.py`, `utils/kg_readiness.py`); the absence of any FEEL/DMN/BPMN
XML or SMT code in the repo (grep); the `_project_execution` key-set pinning in
`tests/test_inter_agent_contract_alignment.py`; corpus sizes/licenses/checksums
(`benchmarks/datasets.json`, `benchmarks/README.md`); `pytest` → 770 passed.

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
