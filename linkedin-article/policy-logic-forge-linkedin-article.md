---
title: "AI Can Write the Rule. Where's the Proof?"
subtitle: "Turning policy into business logic, models, and code — deterministic where it can be, formally proved where that is possible, and judged only where it must be."
author: "Reza Rahimi"
status: "Publication-ready"
note: "Approximately 2,250 words, six visuals. No stage count and no performance figures, by choice — see publishing-kit.md. LinkedIn cannot render Markdown tables, so every comparison is a headed list."
---

# AI Can Write the Rule. Where's the Proof?

![Policy Logic Forge carries evidence through four phases: policy, structured knowledge, reasoning and verification, and code-ready artifacts](images/01-policy-logic-forge-hero.png)

For most of the history of enterprise software, the expensive part was **producing** things. Writing the rule. Drawing the decision model. Designing the schema. Scarce experts, long timelines, a queue.

That constraint is dissolving. Hand a regulation to a model today and it returns all three in seconds — clean, structured, confident. So the interesting question is no longer *can it write the rule?* It is: **where's the proof?**

When anything can be generated, the artifact stops being the valuable thing. What becomes scarce is the ability to say where a claim came from, what independently checked it, and what the system refused to assume. In regulated industries, that is the difference between a system you can deploy and one you cannot.

The danger has never been output that is obviously wrong — review catches that. It is output that is **plausible**: a rule with the right action and the wrong trigger, a condition that reads perfectly and cites a passage that does not support it. On the page, fluency and correctness look identical.

I built an open-source system to close that gap. The most useful thing I learned was not how well it extracts, but how easily a pipeline like this can look like it is working while producing confident nonsense.

## Most systems implement an interpretation, not a policy

Between a regulator's paragraph and a decision made by software sits a chain of people who must identify the governed concepts, separate obligations from exceptions, translate prose into logic, and decide what is safe to automate. Every handoff can lose meaning quietly, without anyone noticing until an audit.

Take a clause of the kind that appears in every regulated domain:

> When a customer submits a complete request, the institution must respond within 30 days unless identity verification remains unresolved.

A person reads that in seconds. A system has to make six things explicit before it can act on it:

- **Who** is responsible — the institution, or a role inside it?
- **What starts the clock** — submission, receipt, or confirmed completeness?
- **What counts** as a "complete request"?
- **Which days** — 30 calendar or 30 business?
- **What the exception does** — pause the clock, or remove the obligation?
- **Which exact passage** supports each answer?

Drop any one and the rule still reads correctly to a human. But once software executes it, a rule with the right action and the wrong trigger is not "mostly correct."

![A policy clause passes through expert, analyst, architect, developer, tester, and auditor handoffs where actor, trigger, timing, exception, scope, and evidence can be lost](images/02-policy-translation-gap.png)

Traditional implementation is a relay race, and each runner produces a new representation. So a revised clause triggers another full round of analysis, two teams encode the same rule differently, and when a rule changes, teams know *that* it changed but not which decisions, data fields, or tests depend on it. In regulated domains, that is operational and governance risk, not a documentation inconvenience.

## Why "just use an LLM" is not the answer

An LLM that emits a list of plausible rules solves the first ten minutes of this problem and none of the rest.

If a model produces the same clean output whether or not the source supports it, then **no amount of prompting makes the output self-certifying.** You cannot ask the thing that wrote the rule whether the rule is true; you will get another fluent answer. The check has to come from somewhere the generation cannot reach — somewhere **deterministic**, returning the same verdict every time for reasons you can inspect, or better, somewhere **formal**, where a property is stated precisely enough to be proved rather than assessed.

It also needs an **evidence spine** running both ways: forward from source passage to concept, rule, model and artifact, and backward from any generated element to the exact passage behind it. Without that reverse path, a polished decision table is just a more convincing place for unsupported meaning to hide.

## The operating rule: decide, prove, judge, escalate

![The stages of Policy Logic Forge grouped into source, knowledge, verification, model, and exploration responsibilities](images/04-policy-logic-forge-architecture.png)

What matters is not that the system is a pipeline rather than one large prompt. It is the rule that pipeline follows:

> **Decide as much as possible with code. Prove what can be proved. Ask a model only what genuinely requires judgment. Send a person only what survives all three.**

That ordering is the difference between output you can **re-derive** and output you can only **re-read**. It also inverts the usual instinct: instead of reaching for the model first and adding guardrails afterwards, the model is the *last* resort before a human, and every stage exists to make its job smaller.

Structurally, that means narrow stages with defined contracts, grouped into five responsibilities:

- **Preserve the source before interpreting it.** Extraction produces rule *candidates with provenance* — conditions, exceptions, scope, and field-level source references — never declarations of truth.
- **Normalise knowledge without hiding uncertainty.** Rules and concepts merge into a conservatively deduplicated graph, and proximity in that graph is never treated as business order.
- **Repair contracts, then verify claims independently.** Deterministic invariants gate readiness; the system then rebuilds *fresh* evidence from the raw corpus and re-checks every claim, without trusting the citation the rule already carries.
- **Generate only the representation the source supports**, and refuse where it does not.
- **Make the result explorable** in one self-contained report an expert can navigate without opening an internal file.

One separation carries most of the weight: **the component that wrote a rule is never the only component judging whether the source supports it.**

## "Isn't this just LLM-as-a-judge?"

It is the first question anyone technical asks, and both familiar answers have real problems. **LLM-as-a-judge** puts a second model in front of the first one's output; it scales, but the judge inherits the generator's blind spots, has no ground truth, and grades the quality the generator optimised for: plausibility. **Expert review** is the gold standard for correctness and does not scale, because nobody reads several hundred extracted rules by hand every time a policy changes.

There is a third position, resting on one observation: **most verification questions are not matters of opinion.**

![Four kinds of verification in order of strength: deterministic checks with no model, a solver, a model used only where judgment is irreducible, and the human expert reserved for legal correctness](images/07-verification-ladder.png)

- *Does this quoted sentence literally occur in the cited chunk?* String resolution against the raw corpus — exact offsets, reproducible, no model.
- *Does every rule reference point at a rule that exists?* Set membership.
- *Does rule B actually read a symbol that rule A assigns?* A mechanical dataflow test, not an impression of relatedness.
- *Can this condition be satisfied at all, or does it contradict itself?* A solver question.

One obligation is genuinely a proof rather than a check. Every decision table declares a **hit policy**: `UNIQUE` means no two rules may ever match the same input, so an overlap there is a live production bug — exactly the kind that survives human review, because you cannot see it by reading. That becomes a proof obligation of pairwise disjointness, discharged by exhaustive enumeration and recorded with its method, solver, and a hash of the exact query, so anyone can re-run it. Where the domain is unbounded, the prover returns `unknown` rather than a comfortable green tick.

On a real corpus, **the overwhelming majority of relationship claims were settled by these checks alone.** That is the actual claim: not a better judge, but *far fewer questions that need judging.*

Where a model is genuinely required, it never sees the prior answer — evidence is rebuilt from the raw corpus, so its mistakes do not correlate with the generator's — and its verdict is labelled a model verdict. **The expert does not disappear; they get routed**, and no longer spend attention on claims a string comparison could have settled.

One boundary matters more than any other: **none of this proves legal correctness.** The checks establish structure, provenance, and internal logical properties — never that a rule is a correct reading of the regulation. That judgment stays with a person, which is precisely why it should not be squandered on mechanically decidable questions.

### Proved, not tested

The fair follow-up is *how do I know your verifier is any good?* A test checks that one example behaved; a **proof** checks that no example can misbehave. Six properties of this system are proved rather than tested, by exhaustive enumeration over their finite domains.

The most legible one: **`Money` and `Percentage` are incomparable.** Both are decimal numbers, and a system that quietly reconciles them will eventually read a 3% rate as $3. That *cannot* happen here — not a test that passed on the inputs someone thought of, but a property holding for every pair of types: neither is a special case of the other, so there is no narrowest reading to pick, and the system refuses rather than choosing one. If a system's whole argument is *"you can check my work,"* that has to include checking the checker.

## One quality score hides three different questions

Ask *"is the extraction good?"* of a real corpus and there is no single honest answer, because that question is really three:

- **Does every rule point at a source?** Nearly always. Pointers are easy.
- **Is each claim supported by the source it points at?** Usually — a much stricter test, and where independent verification earns its place.
- **Does the whole rule pass every check, end to end?** Far less often, because it fails if *any* of its claims falls short.

Same corpus, same run, three very different pictures. Lead with the first and the system looks finished; lead with the third and it looks broken. Both are true — which is why the system reports each separately instead of averaging them into one reassuring score.

If you take one thing from this article, make it this: **"accuracy" is close to meaningless for evidence-critical AI unless you say which question you are answering.**

### The failure that changed my mind

While auditing the system against its own output, I found something I was not looking for.

The knowledge graph carried per-rule "related rules" lists written by the extraction model, and nothing validated them. Some pointed at rules that deduplication had removed. Others pointed at rules that had **never existed in any version of the graph at all.** The model had invented rule identifiers, every downstream stage passed them along unexamined, and the dependency builder quietly discarded them while reporting nothing dropped.

Nothing crashed. No output looked wrong. Every artifact still rendered beautifully.

An integrity check now validates those references and records every drop with a reason. But the lesson generalises well past this project: **in evidence-critical systems, the checks you do not write are the failures you do not see.**

## The right representation — or none at all

![SBVR, DMN, BPMN, CMMN, LinkML, and a compiled representation each answer a different business question, behind a source-support gate](images/05-standards-by-question.png)

No single notation answers every business question, so the system generates against the question the source can actually support: SBVR-aligned vocabulary for what the terms mean, DMN for what decision follows from a set of inputs, BPMN for explicitly ordered work, CMMN for work that unfolds as a case, LinkML for the data the rules depend on, and a compiled formal representation for what can be proved.

**The refusal boundary matters as much as the export format.** The pipeline does not emit a process model because two rules share a dependency; it requires an evidenced trigger, a responsible actor, and at least two explicitly ordered steps in the source. On privacy policies, that withholds the diagram for the overwhelming majority of rules — the correct outcome, not a shortfall, because a privacy policy states obligations and rarely describes workflows.

Sometimes the most accurate diagram is no diagram.

One more boundary guards the most expensive category error in this space: **machine-readable is not the same as production-ready.** A generated decision table is a reviewable projection, not a deployed artifact, and still has to be validated in its target engine.

## What this changes for the people doing the work

The goal was never to remove the human, but to give people a more reliable object to work with: a structured claim beside its evidence, a typed schema instead of prose, an artifact that leads back to a document and a source chunk, and a graph you can inspect for impact before deciding what to revalidate.

The quieter benefit matters most in regulated work: **a deterministic check gives the same answer next quarter that it gave today.** That is not true of a model verdict, and it is the property an audit actually depends on.

![A portrait infographic showing the complete Policy to Knowledge to Reasoning and Verification to Code-ready Artifacts journey, with bidirectional traceability and business outcomes](images/06-policy-to-code-infographic.png)

## Where this goes

The competitive question in regulated AI is about to invert. For the last few years it has been *how much can we generate?* The next few will be about the question this article opened with — **where's the proof?** — which unpacks into: can every operational claim explain where it came from, how it was transformed, what checked it, and what the system refused to assume?

Organisations that can answer will deploy. Organisations that cannot will keep producing impressive artifacts that never leave the review queue — not because the models were not good enough, but because nobody could defend the output.

**Provenance is not documentation you add at the end. It is the thing you are actually building.** And you build it unglamorously, by moving claims out of judgment and into decision, one at a time, until what is left is the part that genuinely needed a person.

So, the concrete version of the same question, because I would genuinely like to know: where does policy meaning most often get lost in your organisation — interpretation, implementation, testing, or change management?
