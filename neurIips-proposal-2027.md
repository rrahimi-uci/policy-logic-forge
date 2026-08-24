# NeurIPS 2027 Research Proposal — v2 (literature-grounded)

**Working title:** *Verified Compilation of Normative Text: Instrument Validation,
Assumption-Explicit Semantics, and Solver Rewards for Document-to-Logic Extraction*

**Umbrella project name:** **LEXEC** — compile normative documents into executable
decision logic, and use the compiler as the measuring instrument.

| | |
| --- | --- |
| Target venue | NeurIPS 2027 main track (primary); Datasets & Benchmarks track (secondary/spin-off) |
| Target deadline | **NeurIPS 2027 is December 2027, in Europe. Deadline not yet announced; recent years were May 6 (2026), May 16 (2025), May 22 (2024) — plan for ~May 1, 2027 and verify on the CFP.** |
| Time available | ~8.5 months from 2026-08-24 |
| Substrate | This repository: 10-stage extraction pipeline, v2 rule contract, four-invariant readiness gate, claim-level grounding verifier, 100%-coverage dependency DAGs, 4 benchmark-backed domains, `pytest` 770 passed (verified 2026-08-24) |
| Status | Proposal for discussion. `(measured)` = a real run. `(target)` = pre-registered success criterion. `(published)` = a number from cited prior work, verified this session. |

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
   UNIQUE-safety. Nobody runs these over LLM-extracted rule sets at corpus
   scale. → §7
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

**Why it is worth doing now.** The closest published work sits at **42.6%**
outcome equivalence *(published)* — the task is wide open. Extraction is already
built and tested in this repo; the measurement half is the research. And every
fallback is still a paper: if compilation does not generalize, the compiler
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
(§1.6). Saying so is the honest framing, and the contribution is that nobody has
checked whether a *gold-free* extensional metric agrees with a *gold-based* one.

**(B) Assumption-explicit semantics.** If the gold answer needs an unstated
assumption, the artifact should *name* it rather than silently absorb it (§10).

**(C) Relational evaluation, narrowly.** Annotate an edit and its intended
semantic effect; check with a solver (§11), positioned against LGMT.

---

## 4. Contributions, with explicit novelty deltas

| # | Contribution | Closest prior work | What is actually new |
| --- | --- | --- | --- |
| **C1** | **LEXEC-Verify** — LLM-free compiler (v2 rule contract → DMN 1.3/FEEL, SMT-LIB, reference interpreter) + solver layer deciding row disjointness, subsumption, equivalence, co-firing conflict, coverage gaps, vacuity, entailment | ContractCheck (manual blocks, one SPA); PolicyGuard (Z3, contract-vs-policy review); Graus (executor, **no solver checking**) | Solver-decided *internal* consistency of **LLM-extracted** rule sets at corpus scale; witness extraction for repair; UNIQUE-safety proofs |
| **C2** | **Instrument validation** — does gold-free decision agreement predict gold-artifact outcome equivalence? | Nobody | Calibrates the metric that the whole no-gold methodology rests on (§9). **The most defensible contribution in the proposal.** |
| **C3** | **Assumption-explicit compilation** — the artifact emits the minimal assumption set needed to reach the pragmatic answer; measure necessity/minimality | *Know Your Limits* documents the gap and names "assumption-surfacing tools" as future work | Turns a measured negative result into a compilation requirement and a metric |
| **C4** | **LEXEC-Bench** — decision-level benchmark over 6 existing resources, 4 query modes, no new gold artifacts | LegalBench (162 tasks, label-level); PrivacyGLUE (7 tasks); ObliQA (27,869 questions); ContractEval; RuleArena | First *extensional, artifact-level* benchmark spanning contracts, NDAs, privacy policies, regulation, and a gold-DMN anchor |
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

**Fragment.** 8 operators, 1 output operator, 7 value types → linear arithmetic
over integers/rationals + finite enums + equality. Decidable; quantifier-free
cases go straight to an SMT solver. We implement a bounded FEEL renderer and
evaluator and **fail loudly** outside it (notably `duration` and `range`, which
the schema permits and the observed corpus never exercised). Silent coercion
would contaminate the measurement.

---

## 6. Propositions

**P1 (Compilation soundness).** Under §5's defeater semantics, DNF expansion of
*C* ∧ ¬(⋁*X*) into rows, with the hit policy assigned per P2, denotes exactly
⟦*r*⟧ on the declared domain.

**P2 (UNIQUE-safety is decidable).** UNIQUE is admissible iff rows are pairwise
disjoint — an unsatisfiability check per pair in this fragment. NP-complete
propositionally; practical at observed sizes (**87.5% of rules expand to a
single row; worst case 7** *(measured)*). Where disjointness is not provable the
compiler **downgrades to FIRST and records the reason** (**42 rules**
*(measured)*), never emitting a false UNIQUE.

**P3 (Boundary vectors are a complete certificate for interval tables).** For a
table whose rows are conjunctions of interval constraints over independent
numeric inputs and finite enums, a suite containing each interval endpoint plus
one interior point per cell is *complete*: it distinguishes the table from any
other in the class. Two payoffs: the contract's existing
`boundary_condition` test vectors become a verification certificate rather than
a smoke test; and it **obviates exhaustive enumeration** — Graus brute-forced
**2,712 + 10,368 test cases** across 58 models by enumerating 2^n input
combinations *(published)*, which P3 replaces with a suite linear in the number
of thresholds. This is the cleanest theoretical result available here and it has
an immediate practical consequence.

**P4 (Consistency by construction).** A compiled artifact's answers are
consistent with one function by construction; per-query LLM answering is not.
Report *cross-query inconsistency* (CQI): 0 for compiled, measured for the
baseline.

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
external policies; Graus has an executor but **no solver layer at all**. Nobody
runs these seven checks over LLM-extracted rule sets at corpus scale, and the
per-100-rule defect densities they yield are themselves a new measurement of
extraction quality that needs no human and no gold.

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

## 9. Instrument validation — the contribution I did not have in v1

**The question.** Every gold-free extensional metric assumes that agreeing with
query answers means having built the right artifact. *Nobody has checked that.*
The Dutch DMN corpus makes it checkable, because it has both the artifact and
the behavior.

**The experiment.**

1. Run the pipeline on the 95 documents' legal text → compiled artifacts.
2. Compute **gold-based** outcome equivalence against the 95 gold DMN models
   using their released harness (reproducing Graus's protocol so numbers are
   comparable).
3. Compute **gold-free** decision agreement, using only queries and scenarios
   derived without touching the gold artifacts.
4. Report the correlation, the rank agreement, and — most importantly — the
   **disagreement cases**: where does the gold-free metric say "good" and the
   gold artifact say "wrong," and why?

**Why this matters more than another accuracy number.** If gold-free DA tracks
gold-based equivalence, every result on the five corpora *without* gold
artifacts inherits credibility. If it does not, that is a finding that should
change how this entire subfield evaluates itself — and either way the paper has
something a reviewer cannot dismiss as an application.

**Bonus, free from the same data:** re-run Graus's four input conditions (text;
+semantic roles; +I/O specs; +both) with our compiler and solver in the loop, and
report whether solver-checked compilation beats their best condition
(**42.6% / 60.4%** *(published)*). A published number to beat, on a published
harness, is the cheapest credibility available.

---

## 10. Assumption-explicit compilation

**The problem, measured by others.** ContractNLI's gold labels reflect pragmatic
legal interpretation; **71 entailment cases become neutral** under strict formal
entailment *(published, arXiv:2606.16118)*. Graded naively, the entailment mode
punishes an artifact for being *more* rigorous than the annotator.

**The fix.** The artifact answers with a pair — a verdict *and* the minimal
assumption set it needed:

```
query   : "Receiving Party may share some Confidential Information with third parties"
verdict : ENTAILED under assumptions { third_party ⊑ permitted_recipient,
                                       written_consent_obtainable = true }
strict  : NOT ENTAILED
```

**Three metrics fall out**, and each is solver-computable:

- **Assumption-free accuracy** — strict entailment vs. re-annotated strict labels.
- **Assumption-augmented accuracy** — accuracy against original pragmatic labels
  when the artifact is allowed to declare assumptions.
- **Assumption minimality** — is each declared assumption *necessary*? Drop it
  and re-check: if the verdict survives, the assumption was padding. Minimality
  is exactly what stops a model from "assuming" its way to any answer, and it is
  decided by the solver, not by a judge.

This converts someone else's negative result into a design requirement, a
metric, and a defense of the benchmark's oracle. It also answers the sharpest
reviewer question about the entailment mode before it is asked.

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

Three properties worth stating: the reward is computed by a compiler and a
solver, so there is no judge to persuade; the signal is dense in a domain that
had none; and abstention is priced, which makes selective prediction a trade-off
the model must navigate — then measured with risk–coverage curves against the
grammar-entropy UQ baseline from **Grammars of Formal Uncertainty** (NeurIPS
2025), which reaches **AUROC > 0.93** on logic tasks *(published)* and is the
number to beat.

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
| Benchmark corpora, checksummed, license-clean | ✅ `benchmarks/` (4 corpora; +2 to add) |

Extraction half: built and tested. Measurement half: the research build.

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
| Grounding-verifier over-rejection | ours, n=1: **98% flagged vs. 6% vector-replay failure** | **≥ 5×**, replicated across 4 domains and ≥ 3 verifier models |
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
| Dependency-edge types | prerequisite 138, complementary 46, conditional 45, sequential 37, validation 18, override 16, contradictory 5 |

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

## 17. Timeline (2026-08 → 2027-05), tightened

NeurIPS deadlines have moved earlier three years running (May 22 → May 16 →
May 6). Plan for **~May 1, 2027**, results frozen **April 15**.

| Month | Work | Gate |
| --- | --- | --- |
| **Sep 2026** | **Start with the Dutch corpus, not our own.** Clone Graus's repo, run its harness, reproduce its baseline. Then run our pipeline on the same 95 documents and get a first OE number. In parallel: `utils/feel.py` (renderer + evaluator), `utils/dmn_builder.py` (DNF → rows, hit-policy reconciliation). | **G1:** we reproduce Graus's reported baseline on his harness, and our pipeline produces a measurable OE on the same data. *This is a far better month-1 gate than v1's self-replication, because it is externally checkable.* |
| **Oct 2026** | SMT-LIB backend + the seven queries. Semantic dedup. Conformance gate (`cli/compile.py`, C1–C4). Provenance into artifacts. Replicate §16's table on one non-mortgage benchmark domain. | **G2:** seven queries running; defect densities on ≥ 2 domains; §16 replication done or its failure characterized. |
| **Nov 2026** | **§9 instrument validation** — gold-free DA vs. gold-based OE on the Dutch corpus, with disagreement analysis. §10 assumption extraction + minimality. ContractNLI and CUAD query builders. Write up for a legal-NLP workshop (NLLP-style) to get external review early. | **G3:** the correlation exists (or provably doesn't) and the disagreement cases are characterized. **Make-or-break: without §9, the benchmark has no warrant.** |
| **Dec 2026** | C6: span-F1 / LLM-judge vs. DA across 4 domains; grounding-verifier over-rejection replication across domains and verifier models. Contamination probes. RuleArena head-to-head (§14.3). | **G4:** both findings replicate, or are honestly reported as absent. |
| **Jan 2027** | LEXEC-Perturb: closed relation list, guidelines, tooling, annotator hiring, 200-item pilot with IAA; full annotation runs in parallel with Feb. | **G5:** IAA ≥ 0.7 on relation labels. |
| **Feb 2027** | CEGIR: repair loop, witness ablation, rounds-vs-accuracy. Target-language ablation (DMN / SMT-LIB / Python / ASP). | **G6:** ≥ 5-point DA gain from CEGIR. |
| **Mar 2027** | Solver-reward RL: environment, GRPO on 8–14B, reward shaping, abstention pricing, risk–coverage vs. the grammar-entropy baseline. | **G7:** beats SFT on the same data by ≥ 3 DA points. |
| **Apr 2027** | Cross-domain / cross-lingual / cross-jurisdiction / cross-task transfer. Amortization + CQI. Human validation of the scenario subset. **Freeze April 15.** | **G8:** headline table filled. |
| **May 2027** | Writing, figures, artifact release, reproducibility checklist, broader impact. Submit ~May 1. | — |

Two scheduling principles: the *instrument* is validated before it is used at
scale, and annotation starts early because it is the only irreducibly slow item.

---

## 18. Compute and cost budget

**LLM extraction.** 1,387 documents across four corpora (plus 95 Dutch, plus
ObliQA passages) through a 10-stage reasoning pipeline. Order-of-magnitude: a
few dollars per document per full run → **~$3k–$11k per complete four-corpus
sweep**. Therefore: main results on a stratified subsample (~150 docs/corpus);
one full-corpus ContractNLI run for the flagship; the full 95-document Dutch set
every time (it is small and it is the anchor); cheap models for ablation sweeps;
frontier models only for headline rows. **Budget $15k–$30k with a hard cap and
per-experiment cost logging from day one.** The repo's adaptive global rate
limiter already makes concurrent batch runs safe.

**RL training.** GRPO on 8–14B: ~8×H100 for 1–2 weeks per serious run, plus
false starts; LoRA on ~32B as the cheaper path. Budget 2–4 runs. The verifier is
CPU-bound, so **solver throughput, not GPU, is likely the RL bottleneck** — cache
by rule-set hash, bound row counts, time-box solver calls and record the timeout
rate.

**Annotation.** ~1.5–2k perturbation items at 2–4 min, 20% double-annotated →
~120–160 hours; plus ~500 scenario validations. 2–3 qualified annotators (law
students / privacy-compliance practitioners), fair disclosed rates.

---

## 19. Risks and mitigations

| Risk | Severity | Mitigation |
| --- | --- | --- |
| **Someone publishes the solver-reward RL first.** Wang et al. named it as future work in June 2026. | **High** | Move C5 earlier if G3 lands early; and make C2 (instrument validation) the paper's spine, since it does not depend on the method being first |
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

Every item below was located and checked in this session; Appendix C lists the
identifiers. Organized by what each line of work leaves open.

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
- **Licensing.** CUAD and ContractNLI: CC BY 4.0. Dutch DMN corpus: CC BY 4.0 per
  the repository (the paper page indicated CC BY-SA — **verify before
  redistribution**). OPP-115 and MAPP: research use, no redistribution grant →
  ship edit scripts and offsets, never derived text. ObliQA: check ADGM terms.
  Cite every corpus paper. `benchmarks/datasets.json` (checksummed upstream URLs)
  is the template.
- **Annotators:** fair disclosed pay, published guidelines, reported IAA.
- **Dual use:** the same machinery finds gaps in a policy, which can serve
  exploitation as well as audit. One honest sentence in broader impact; the
  counterpoint is that this capability is what makes compliance auditable at all.
- **Release:** compiler, solver layer, benchmark harness, assumption extractor,
  perturbation edit scripts, RL environment, adapter weights; reproducibility
  checklist including the true cost of a full reproduction.

---

## 23. Immediate next four weeks

Reordered by the literature review. The first action is now *someone else's
repository*.

1. **Clone and run `github.com/opengov-lab/legal-text-to-decision-model`.**
   Reproduce Graus's reported outcome-equivalence baseline on his harness. Until
   that reproduces, nothing else is trustworthy. Cheap, external, and decisive.
2. **Run our pipeline on the same 95 documents** and produce a first OE number
   through his harness. This is a real, externally comparable month-1 result
   rather than a self-report.
3. **Read arXiv:2606.16118 in full and email the authors** about the 400/610
   strict-entailment re-annotation. If it is available, §8's entailment mode gets
   a correct oracle for free; if not, budget the re-annotation.
4. **Build `utils/feel.py` + `utils/dmn_builder.py`** in the repo's
   dependency-free, unit-tested style. Constraint verified in code: the two tests
   in `tests/test_inter_agent_contract_alignment.py` pin `_project_execution`'s
   key set to exactly what `final_rule_issues` reads, so the compiler must sit
   strictly downstream and treat `execution` as read-only.
5. **Resolve the defeater semantics empirically** on the Dutch corpus (which has
   gold behavior to check against — a strictly better testbed than our own
   vectors) by compiling under all three readings and comparing OE.
6. **Replicate §16's table on one non-mortgage benchmark domain** (ContractNLI or
   OPP-115 — vocabularies furthest from mortgage).
7. **Start annotation logistics** (guidelines, closed relation list, sourcing) —
   the long-lead item.
8. **Set up a citation-verification pass.** Everything in §21 was located this
   session, but venues/years for a few items (MAUD, SatLM, LINC, CheckList,
   Spider) still need a primary-source check before submission.

---

## Review — repository-grounded comments and concerns (2026-08-24)

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
compute estimates in §18; every `(target)` in §15; the Dutch corpus's exact
license (CC BY 4.0 in the repo vs. CC BY-SA 4.0 on the paper page); whether the
arXiv:2606.16118 re-annotation is obtainable; NeurIPS 2027's actual deadline.

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
