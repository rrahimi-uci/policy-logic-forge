---
title: "AI Can Write the Rule. Where's the Proof?"
subtitle: "Turning policy into business logic, models, and code — deterministic where it can be, formally proved where that is possible, and judged only where it must be."
author: "Reza Rahimi"
status: "Publication-ready"
note: "No stage count and no performance figures, by choice — see publishing-kit.md. LinkedIn cannot render Markdown tables, so every comparison is a headed list."
---

# AI Can Write the Rule. Where's the Proof?

![Policy Logic Forge carries evidence through four phases: policy, structured knowledge, reasoning and verification, and code-ready artifacts](images/01-policy-logic-forge-hero.png)

For most of the history of enterprise software, the expensive part was **producing** things. Writing the rule. Drawing the decision model. Designing the schema. Scarce experts, long timelines, and a queue.

That constraint is dissolving. Hand a regulation to a model today and it will return all three in seconds — clean, structured, confident.

Which makes the interesting question no longer *can it write the rule?*

It is: **where's the proof?**

That is a different problem, and most organisations have not planned for it. When anything can be generated, the artifact stops being the valuable thing. What becomes scarce is the ability to say where a claim came from, what independently checked it, and what the system refused to assume.

In regulated industries that is not a philosophical observation. It is the difference between a system you can deploy and one you cannot.

Here is the mechanism, and it is worth being precise about it. The dangerous failure in this work has never been output that is obviously wrong — you catch that in review. It is output that is **plausible**. A rule with the right action and the wrong trigger. A condition that reads perfectly and cites a passage that does not actually support it. On the page, fluency and correctness look identical.

Underneath that sits an older problem the same shift now exposes. Most business systems do not implement a policy.

They implement **someone's interpretation** of a policy.

Between a paragraph written by a regulator and a decision made by software, a chain of people must identify the governed concepts, separate obligations from exceptions, resolve dependencies, translate prose into logic, and decide what is safe to automate. Every handoff is a chance to lose meaning — quietly, and without anyone noticing until an audit.

I built a system to close that gap. The most interesting thing I learned was not how well it extracts. It was how easily a pipeline like this can look like it is working while producing confident nonsense — and what it takes to catch that.

This article is about the architecture, the refusals, and the failure that changed how I think about the whole problem.

## The problem: meaning is lost in translation

Take a clause of the kind that appears in almost every regulated domain:

> When a customer submits a complete request, the institution must respond within 30 days unless identity verification remains unresolved.

A person reads that in seconds. A system has to make eight things explicit before it can act on it:

- **Who** is responsible — the institution, or a specific role inside it?
- **What starts the clock** — submission, receipt, or confirmation of completeness?
- **What counts** as a "complete request"?
- **Which days** — 30 calendar or 30 business?
- **What does the exception do** — pause the clock, or remove the obligation entirely?
- **What response** is actually required?
- **What scope** applies — which products, customers, regions, effective dates?
- **Which exact passage** supports each of those answers?

Drop any one and the rule still reads correctly to a human. A rule with the right action and the wrong trigger is not "mostly correct" once software executes it.

![A policy clause passes through expert, analyst, architect, developer, tester, and auditor handoffs where actor, trigger, timing, exception, scope, and evidence can be lost](images/02-policy-translation-gap.png)

### Why the manual approach does not scale

Traditional policy implementation is a relay race:

**Policy author → subject-matter expert → analyst → architect → developer → tester → auditor**

Each runner produces a new representation — notes, spreadsheets, requirements, diagrams, tickets, code, test cases. Each is useful. Each is one more step away from the sentence that started it.

The consequences are familiar to anyone who has worked in a regulated organisation. A revised clause triggers another full round of analysis. Scarce experts re-explain the same policy in different formats. Two teams encode the same rule differently. Reconstructing why a system behaved a certain way becomes forensic work. And when a rule changes, teams know *that* it changed but not which decisions, processes, data fields, or tests depend on it.

These are not documentation inconveniences. In regulated domains they are operational and governance risk.

## Why "just use an LLM" is not the answer

An LLM that emits a list of plausible rules solves the first ten minutes of this problem and none of the rest.

The reason follows directly from the failure mode above. If a model produces the same clean output whether or not the source supports it, then **no amount of prompting makes the output self-certifying.** You cannot ask the thing that wrote the rule whether the rule is true; you will get another fluent answer. The check has to come from somewhere the generation cannot reach.

In practice that means somewhere **deterministic** — a check that returns the same verdict every time, for reasons you can inspect, whoever runs it. Or, better still, somewhere **formal**: a property stated precisely enough that it can be proved rather than assessed.

So the question is not "can a model read a policy?" It is:

> Can a system transform policy into operational knowledge without breaking the chain of evidence — and can it show exactly where it is uncertain?

That requires a set of connected capabilities, not one clever prompt:

- **Source integrity** — did we ingest and preserve the complete corpus? *Prevents: missing pages, tables, attachments.*
- **Shared business vocabulary** — what do the governed concepts mean? *Prevents: duplicate terms, inconsistent interpretation.*
- **Structured rule contracts** — what is the actor, trigger, condition, action, exception, scope, outcome? *Prevents: attractive prose that cannot be tested.*
- **Dependency semantics** — which rules use, produce, constrain, or conflict over the same facts? *Prevents: hidden downstream impact and invented sequence.*
- **Independent verification** — does the cited evidence actually support the claim? *Prevents: treating a nearby citation as proof.*
- **Selective model generation** — is this a decision, an ordered process, a case, or only a rule? *Prevents: forcing every requirement into the wrong notation.*
- **Human review and explainability** — what is uncertain, why, and where is the evidence? *Prevents: review queues with no actionable context.*
- **Change awareness** — what could a revision affect? *Prevents: revalidating everything, or missing impact entirely.*

Those capabilities need a shared backbone: an **evidence spine** that survives every transformation.

![Eight policy-transformation capabilities connect to a central bidirectional evidence spine](images/03-capabilities-evidence-spine.png)

It has to run both ways:

**Source passage → concept → rule → dependency → model → artifact**

and

**Artifact element → model → rule claim → the exact supporting passage**

Without that reverse path, a polished decision table is just a more convincing place for unsupported meaning to hide.

## The approach: determinism first, proof where possible, judgment last

Policy Logic Forge is an open-source CLI and Python library. The important design decision is not that it is a pipeline rather than one large prompt. It is the rule that pipeline follows:

> **Decide as much as possible with code. Prove what can be proved. Ask a model only what genuinely requires judgment. Send a human only what survives all three.**

That ordering is not a performance optimisation. It is the difference between a system whose output you can **re-derive** and one whose output you can only **re-read**.

It also inverts the usual instinct. The reflex in this space is to reach for the model first and add guardrails afterwards. Here the model is the *last* resort before a human, and every stage is an attempt to make its job smaller — because every claim moved from judgment into a decidable check is a claim that stops depending on anyone's confidence, including the model's.

Structurally that means narrow stages with defined contracts, grouped into five responsibilities, each boundary another chance to catch an error before it becomes an artifact.

![The stages of Policy Logic Forge grouped into source, knowledge, verification, model, and exploration responsibilities](images/04-policy-logic-forge-architecture.png)

**Preserve the source before interpreting it.** Inventory and chunk the corpus with stable document identity. Extract a source-linked concept catalog. Convert policy statements into structured rule candidates carrying conditions, outcomes, exceptions, scope, typed variables, and field-level source references. The design choice that matters: extraction produces *candidates with provenance*, never declarations of truth.

**Normalise the knowledge without hiding uncertainty.** Rules and concepts merge into a knowledge graph, normalised and conservatively deduplicated. Relationships are derived deterministically, and only where the semantics justify them. Graph proximity is never treated as business order — two rules can be connected without one happening before the other.

**Repair contracts, then verify claims independently.** Deterministic invariants gate readiness: corpus integrity, naming consistency, schema consistency, referential integrity. A targeted remediator repairs only what failed, then readiness runs again.

Then the part that matters most. The system builds *fresh* evidence packets from the raw corpus and re-checks every claim — description, condition, outcome, party, scope, exception — without trusting the citation the rule already carries.

**The component that wrote a rule is never the only component judging whether the source supports it.** That single separation is what turns the pipeline from a generator into something closer to an instrument.

### "Isn't this just LLM-as-a-judge?"

It is the first question anyone technical asks, and it deserves a direct answer, because the two familiar options both have real problems.

**LLM-as-a-judge** puts a second model in front of the first one's output. It scales, but the judge inherits the same blind spots as the generator, has no ground truth to check against, and is grading the same quality the generator optimised for: plausibility. Two models from the same family agreeing tells you less than it appears to.

**SME review** is the actual gold standard for correctness — and it does not scale. Nobody is reading several hundred extracted rules by hand, repeatedly, every time a policy changes.

This architecture takes a third position, and it rests on one observation: **most verification questions are not matters of opinion at all.**

![Four kinds of verification in order of strength: deterministic checks with no model, a solver, a model used only where judgment is irreducible, and the human expert reserved for legal correctness](images/07-verification-ladder.png)

- *Does this quoted sentence literally occur in the cited chunk?* That is string resolution against the raw corpus. Exact offsets, independently reproducible, no model.
- *Does every rule reference point at a rule that exists?* Set membership.
- *Does this rule's schema, naming, and corpus coverage hold?* Deterministic invariants.
- *Does rule B actually read a symbol that rule A assigns?* A mechanical dataflow test, not an impression of relatedness.
- *Can this rule's condition be satisfied at all, or does it contradict itself?* A solver question, answered by proof search.

And one that is genuinely a proof rather than a check. Every decision table this system emits declares a **hit policy** — `UNIQUE` means no two rules may ever match the same input. That is not a style preference; overlapping rules in a table declared `UNIQUE` is a live production bug, and it is exactly the kind of thing that survives human review because you cannot see it by reading.

So the table carries a **proof obligation**. `UNIQUE` becomes *pairwise disjointness*, discharged by exhaustive enumeration over the finite domain, and the result is recorded with its method, its solver, and a hash of the exact query — so anyone can re-run it and get the same answer. On a real corpus the overwhelming majority of tables came back **proved**; a handful were refused, and one returned *unknown*.

That last outcome is the important one. The prover returns "proved" **only when the search was exhaustive**. Where the domain is unbounded — open intervals, free text — it returns `unknown` rather than a comfortable green tick. It is sound and deliberately incomplete, which is the opposite of the usual trade in this space.

On a real corpus, **the overwhelming majority of relationship claims were settled by these checks alone** — the model was needed for only a small minority. That is the actual claim: not a better judge, but *far fewer questions that need judging.*

Where a model genuinely is required — does this prose faithfully describe that obligation? — two things change its character:

1. **It never sees the prior answer.** Evidence packets are rebuilt from the raw corpus, so the verifier is not reviewing the generator's reasoning. Its mistakes are not correlated with the generator's mistakes, which is precisely the failure mode that makes naive LLM-as-a-judge weak.
2. **Its verdict is labelled as a model verdict**, distinct from a deterministic one. You can always ask *what kind of check produced this answer* and get a straight response.

**And the SME does not disappear — they get routed.** The point is not to replace expert review. It is to stop spending expert attention on claims a string comparison could have settled, and to deliver the remaining ones with the evidence already attached. Reviewing everything and reviewing what actually needs judgment are very different jobs.

To be explicit about the limit: none of this establishes *legal* correctness. A deterministic check can prove a quote exists in the source. It cannot tell you the rule is a correct reading of the regulation. That judgment is still human, and always will be — which is exactly why it should not be squandered on questions that were mechanically decidable.

**Generate the right representation, when justified.** Decision tables, process models only where the source shows explicit multi-step semantics, case models for case-oriented work, a governed vocabulary profile, and a validated business information model.

**Make the knowledge explorable.** One self-contained HTML report: vocabulary, rule explorer, dependency graph, inline models, information model, review signals, and the source text itself. A subject-matter expert can move through all of it without ever opening the system's internal files.

### Proved, not tested

There is a fair follow-up to all of this: *how do I know your verifier is any good?*

A test checks that one example behaved. A **proof** checks that no example can misbehave. Six properties of this system are proved rather than tested — discharged by exhaustive enumeration over their finite domains, which means checked for every case, not a sample.

The most legible one: **`Money` and `Percentage` are incomparable.**

Both are decimal numbers. A system that quietly reconciles them will eventually read a 3% rate as $3. That cannot happen here — and *cannot* is the operative word. It is not a test that passed on the inputs someone thought of. It is a property that holds for every pair of types in the system: the type relation is proved to be a strict partial order, and neither of those two is a special case of the other — so there is no narrowest reading to pick, and the system refuses rather than choosing one.

The others are of the same kind. Type reconciliation always returns the unique narrowest reading or explicitly refuses, never a coercion. The prover reports a proof only when its search was exhaustive — it never converts *"I could not find a counterexample"* into *"there is none."* On fully bounded inputs it is a genuine decision procedure — it does not fall back on `unknown` to avoid committing. And the dependency graphs form a **partition** of the rule set: every rule in exactly one, none lost, none counted twice.

The proofs live in the repository and run in a couple of seconds:

```
$ python proofs/check_properties.py
ALL PROPERTIES HOLD
```

I mention this less as a feature than as a standard. If a system's whole argument is *"you can check my work,"* that has to include checking the checker.

## One quality score hides several different questions

Running this on a real corpus of public privacy policies taught me something I did not expect about measurement itself.

Ask *"is the extraction good?"* and there is no single honest answer, because that question is really three:

- **Does every rule point at a source?** Nearly always. Pointers are easy.
- **Is each individual claim supported by the source it points at?** Usually — but this is a much stricter test, and it is where independent verification starts earning its place.
- **Does the whole rule pass every check, end to end?** Far less often. A rule fails this if *any* of its claims falls short.

Same corpus. Same run. Three very different pictures of quality.

Lead with the first and the system looks finished. Lead with the third and it looks broken. Both are true, which is exactly why the system reports each of them separately instead of averaging them into one reassuring score.

If you take one thing from this article, make it that: **"accuracy" is close to meaningless for evidence-critical AI unless you say which question you are answering.**

### The failure that changed my mind

While auditing the system against its own output, I found something I was not looking for.

The knowledge graph carried per-rule "related rules" lists — dependency references written by the extraction model. Nothing validated them. Some pointed at rules that deduplication had removed and never cleaned up after. Others pointed at rules that had **never existed in any version of the graph at all.** The model had invented rule identifiers, and every stage downstream passed them along unexamined.

The dependency builder quietly discarded them and reported nothing dropped. The loss was invisible.

It is worth being precise about why this matters: nothing crashed, no output looked wrong, and every artifact still rendered beautifully. A pipeline like this can be *confidently, quietly incorrect* — and unless something is built specifically to look for that, you will ship it.

There is now an integrity check that validates those references and records every drop with a reason. But the lesson generalises well past this project: **in evidence-critical systems, the checks you do not write are the failures you do not see.**

## Why SBVR, DMN, BPMN, CMMN, LinkML, and a compiler — together?

Because no single notation answers every business question.

![SBVR, DMN, BPMN, CMMN, LinkML, and a compiled representation each answer a different business question, behind a source-support gate](images/05-standards-by-question.png)

- **SBVR-aligned profile** — *What do the business terms mean, and how do they relate?* A vocabulary derived deterministically from the graph, linked to concepts and rules.
- **DMN 1.3** — *What decision follows from these inputs?* Decision-table review projections with traceability metadata.
- **BPMN 2.0** — *What explicitly ordered work must occur?* Generated only for grounded, prescriptive, multi-step processes.
- **CMMN 1.1** — *What work unfolds as a case rather than a fixed sequence?* Review and case projections.
- **LinkML** — *What business data do the rules depend on?* A validated schema, with JSON Schema and diagrams generated from it.
- **Compiled intermediate representation** — *Which properties can be proved rather than assessed?* A frozen formal semantics the rules lower into, so obligations like decision-table disjointness become machine-checkable — and unprovable ones come back as `unknown`.

**The refusal boundary matters as much as the export format.** The pipeline does not emit a process model because two rules share a dependency. It requires an evidenced trigger, a responsible actor, and at least two explicitly ordered steps in the source.

On a corpus of privacy policies, that test withholds the process diagram for the overwhelming majority of rules — and that is the correct outcome, not a shortfall. A privacy policy states obligations; it rarely describes ordered workflows. Generating a diagram for every rule would have looked like far more progress and meant considerably less.

Sometimes the most accurate diagram is no diagram.

The same discipline applies to vocabulary: a low-level decision variable is not automatically a governed business concept. Keeping those layers separate is what stops an SBVR view from degenerating into a dump of every symbol in every rule.

## Traceability is the product, not a footnote

Evidence is not attached at the end for the auditor. It is carried through the rule contract and re-checked before any artifact is promoted.

For any generated element, a reviewer can ask:

1. Which rule produced this decision row, process task, case item, or schema field?
2. Which structured claim does it represent?
3. Which document and chunk were cited?
4. Does the quoted text literally occur in the source packet?
5. Did an independent verifier support it, contradict it, or find the evidence insufficient?
6. What is still a projection that needs validation in its target engine?

That last question guards against the most expensive category error in this whole space:

> **Machine-readable is not the same as production-ready.**

## What exists today — and what does not

Credibility here depends on drawing the line clearly. So:

**Implemented and running in the repository:**

- A staged CLI pipeline with checkpointed output at every step
- Structured rule contracts with field-level source references
- Deterministic readiness invariants and targeted remediation
- Independent, claim-level grounding verification, with literal quote resolution against the raw corpus
- A frozen IR semantics and a bounded proof layer that discharges decision-table obligations, or returns `unknown`
- Deterministic relationship derivation with stated acceptance conditions, and complete DAG partitioning
- DMN, selective BPMN, CMMN, and SBVR-aligned outputs
- A validated LinkML information model, with JSON Schema and diagrams generated from it
- A self-contained traceability and review report
- Version-to-version change analysis with impact propagation and scenario replay

**Honest limitations:**

- It is a pipeline and a library, **not a hosted governance platform**.
- Extraction quality still depends on source quality and model behaviour.
- Readiness invariants check structure. **They do not prove legal correctness.**
- Literal quote support is stricter than pointer presence, but it is not full legal entailment.
- The proof layer is **bounded formal verification, not general theorem proving**. It enumerates finite domains exhaustively rather than calling an industrial SMT backend, so it is sound but deliberately incomplete — and it verifies *internal logical properties* such as hit-policy disjointness, never that a rule is a correct reading of the regulation.
- The mechanically checkable path does not cover every rule. Those it cannot lower are reported as refusals with stated reasons rather than quietly dropped.
- The SBVR artifact is a project-aligned profile, not full OMG interchange conformance. CMMN output is intentionally simple.
- Generated schemas still require environment-specific ownership decisions.
- Change analysis aligns rules by exact identifier today, so a renamed rule reads as a removal plus an addition.

The repository does **not** establish a universal accuracy rate, complete concept recall, legal correctness, or automatic deployability. Those claims need curated expert benchmarks and target-environment validation. I am not making them here.

## What this changes for the people doing the work

The goal was never "remove the human." It was to give humans and systems a more reliable object to work with.

- **Policy experts** review a structured claim beside its evidence, instead of searching a corpus.
- **Analysts** see definitions, conditions, exceptions, and dependencies in one connected model.
- **Developers** receive typed, code-ready schemas and decision projections instead of prose.
- **Testers** connect scenarios and predicates back to the rule that motivated them.
- **Auditors** follow an operational artifact back to a document and a source chunk.
- **Change teams** inspect graph impact before deciding what to revalidate.

There is a quieter benefit that matters most in regulated work: **a deterministic check gives the same answer next quarter that it gave today.** Re-run the pipeline on the same corpus and the same claims resolve the same way, for the same stated reasons. That is not true of a model verdict, and it is the property an audit actually depends on.

Selective automation with explicit boundaries: automate what is sufficiently supported for a specific environment, route genuine ambiguity to people, and keep the evidence for both decisions.

![A portrait infographic showing the complete Policy to Knowledge to Reasoning and Verification to Code-ready Artifacts journey, with bidirectional traceability and business outcomes](images/06-policy-to-code-infographic.png)

## Where this goes

Generative AI has made it trivially easy to produce something that **looks** like business knowledge. That capability is only going to get cheaper and more convincing.

Which is why I think the competitive question in regulated AI is about to invert. For the last few years it has been *how much can we generate?* The next few years will be about the question this article opened with — **where's the proof?** — which unpacks into:

> Can every operational claim explain where it came from, how it was transformed, what checked it, and what the system refused to assume?

Organisations that can answer that will be able to deploy. Organisations that cannot will keep producing impressive artifacts that never leave the review queue — not because the models were not good enough, but because nobody could defend the output.

**Provenance is not documentation you add at the end. It is the thing you are actually building.**

And the way you build it is unglamorous: by moving claims out of judgment and into decision, one at a time. Every question you can turn into a string comparison, a set membership, a dataflow test, or a proof obligation is a question that no longer depends on anyone's confidence — not the model's, not the reviewer's, not yours. What is left after that is the part that genuinely needed a human, which is where the expertise should have been going all along.

And for this project, the most honest answer I can give to my own title is that directory of proofs. Not a benchmark. Not a score. A handful of properties that either hold or do not, and a command that tells you which.

That is a far smaller claim than *"the extraction is accurate."* It is also one I can hand you instead of asking you to believe it.

The invented rule references are the part of this project I think about most. Not because the bug was hard to fix — the check that catches it is a few dozen lines — but because nothing about the system's output suggested anything was wrong. That is the shape of the risk, and it is why I now trust an architecture that reports its own refusals — and publishes properties you can re-derive — far more than one that reports a high score.

**If generation really is becoming free, what becomes the scarce thing in your part of the business — provenance, judgment, or accountability?**

And the concrete version of the same question, because I would genuinely like to know: where does policy meaning most often get lost for you — interpretation, implementation, testing, or change management? That answer is the part I would build next.

[Policy Logic Forge](https://github.com/rrahimi-uci/policy-logic-forge) is open source and still developing. Issues and disagreement both welcome.

---

## Technical grounding

Architectural claims map to implemented components:

- [Canonical stages and names](https://github.com/rrahimi-uci/policy-logic-forge/blob/main/utils/agent_names.py)
- [Structured rule contract](https://github.com/rrahimi-uci/policy-logic-forge/blob/main/utils/rule_contract.py)
- [Dependency semantics and reference integrity](https://github.com/rrahimi-uci/policy-logic-forge/blob/main/utils/rule_dependencies.py)
- [Readiness invariants](https://github.com/rrahimi-uci/policy-logic-forge/blob/main/utils/kg_readiness.py)
- [Independent grounding verifier](https://github.com/rrahimi-uci/policy-logic-forge/blob/main/agents/agent_09_grounding_verifier.py)
- [Complete DAG builder](https://github.com/rrahimi-uci/policy-logic-forge/blob/main/utils/dag_builder.py)
- [DMN and selective BPMN generation](https://github.com/rrahimi-uci/policy-logic-forge/blob/main/utils/executable_models.py)
- [CMMN and SBVR-aligned artifacts](https://github.com/rrahimi-uci/policy-logic-forge/blob/main/utils/semantic_artifacts.py)
- [LinkML business information model](https://github.com/rrahimi-uci/policy-logic-forge/blob/main/utils/linkml_schema.py)
- [Self-contained HTML report](https://github.com/rrahimi-uci/policy-logic-forge/blob/main/agents/agent_13_business_knowledge_report.py)
- [Change analysis engine](https://github.com/rrahimi-uci/policy-logic-forge/blob/main/utils/regdelta_engine.py)
- [Machine-checked properties](https://github.com/rrahimi-uci/policy-logic-forge/tree/main/proofs) — the six theorems above, runnable

*Scope note: This describes the architecture and contracts implemented as of September 2026. All figures come from a single documented run over 109 public privacy policies and are pipeline observations — coverage, support, and refusal counts — not an extraction-accuracy benchmark against expert labels. Generated models are review projections until validated in their target engines. "SBVR" refers to the project's SBVR-aligned vocabulary profile, not complete OMG SBVR interchange conformance.*
