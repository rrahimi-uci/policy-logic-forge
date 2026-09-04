# LinkedIn publishing kit

Companion material for [`policy-logic-forge-linkedin-article.md`](policy-logic-forge-linkedin-article.md).

## Pasting into LinkedIn

LinkedIn has no public API for creating draft articles — that surface is
partner-gated — so publishing is a manual paste. Pasting the Markdown source
loses all formatting: this draft carries 81 bold spans, 67 bullets, 5 block
quotes and 10 inline-code spans, well over 150 operations to reapply by hand.

Pasting *rendered* HTML keeps them. Generate the paste-ready file:

```bash
python linkedin-article/make_paste_ready.py
```

Then open `linkedin-article/paste-ready.html` in a browser, select all, copy,
and paste into the LinkedIn article editor. Headings, bold, italics, lists,
quotes and links all survive.

Two things are deliberately not rendered:

- **Images become labelled placeholders.** LinkedIn images must be uploaded
  through the editor, so an `<img>` would paste broken. Each placeholder names
  the file to upload and its alt text — delete the block, upload the image
  there. The seven are listed under *Image sequence and alt text* below.
- **The title and subtitle are shown separately**, because they belong in
  LinkedIn's own title field rather than in the body.

Regenerate the file after any edit to the article; it is committed so it can
be opened without running anything.

## Format constraint, read this first

**LinkedIn's article editor does not render Markdown tables.** Pasting one produces a run-on paragraph or drops the content entirely. The article previously carried four tables; all four are written as headed bullet lists that survive paste-in unchanged. Do not reintroduce tables when editing.

The editor supports: headings (H1–H3), bold, italic, bulleted and numbered lists, block quotes, links, images, and code blocks. Everything in the draft stays inside that set.

## Editorial position

Two deliberate choices shape this draft:

- **No stage count.** The pipeline is described by its five responsibilities, not by how many stages it has. A reader does not need to hold a number in their head to follow the argument, and a count invites the wrong question ("why that many?") instead of the right one ("what does each boundary catch?").
- **No performance figures.** The article makes its case through architecture and one concrete failure, not through metrics. This keeps the piece durable — figures age, get quoted out of context, and invite benchmark arguments the project is not trying to have. The qualitative claims stand on their own.

If a reader asks for numbers in the comments, that is a good outcome. Answer there, with the run context attached.

## Headline

**AI Can Write the Rule. Where's the Proof?**

*Turning policy into business logic, models, and code — deterministic where it can be, formally proved where that is possible, and judged only where it must be.*

Why it works:

- **It concedes, then pivots.** "AI Can Write the Rule" grants what the reader already believes, which disarms them; the second half turns on what they have not resolved. Arguing with a reader in the first four words rarely survives the scroll.
- **It is the skeptic's own question.** "Where's the proof?" is what an auditor, a risk officer, or a hostile commenter would ask anyway. Putting their objection in the headline defuses it instead of inviting it.
- **It is answerable, so it earns comments.** Question headlines outperform declarative ones here, but only when the question is one a reader can actually engage with.
- **It cashes a cheque the repository can honour.** The word *proof* is now literal: six machine-checked properties and a runnable script. Earlier drafts used it rhetorically.
- **It brackets the article.** The opening reaches it in the fourth line — *"It is: where's the proof?"* — and the close returns to it by name, answering with a directory you can clone rather than a number you have to trust.

### Why the earlier headline was retired

*"AI Can Write the Rule. Can You Prove It's Right?"* had the same structure and was very close. It was changed for one reason: **"prove it's right" points at legal correctness**, which the article explicitly and repeatedly declines to claim. A sharp reader could fairly call that a bait. *"Where's the proof?"* asks for evidence rather than rightness — which is exactly what the piece delivers, and it is the harder question to attack.

### Further back

- *"A Policy Is Not an Algorithm: What It Takes to Turn Regulation Into Executable Systems"* — opened on a negation; *"What It Takes To…"* promises a category rather than a payoff; every noun an abstraction. Read as a conference talk.
- *"AI Doesn't Get Policy Wrong. It Gets It Plausible."* — sharp, but **diagnostic**. It names a problem, and diagnosis looks backward. The line survives in the body.
- *"When AI Can Write Anything, Provenance Becomes the Product"* — visionary but abstract; asks the reader to accept a term before they have felt the problem.

## Variants for a different audience

1. **Your AI Passed Every Test. Would It Survive a Proof?** — carries the tested-versus-proved axis, the most differentiated idea in the piece, and challenges the reader's own system. Drops the policy anchor and the payoff arrives late, so **use it as the headline for the standalone proofs post**, not the article.
2. **AI Can Write the Rule. It Can't Vouch for It.** — the sharpest logic of the set, compressing *"you cannot ask the thing that wrote the rule whether the rule is true."* Loses the word *proof*, which is the asset worth spending.
3. **Verifying AI Shouldn't Need Another Opinion** — kills the LLM-as-a-judge frame in the headline itself. Best paired with the verification-ladder image as a standalone post.
4. **Generation Is Cheap. Proof Is the Product.** — the quotable aphorism, now backed by a real `proofs/` directory. Least domain-anchored of the set.

**Pairing note:** the cover image says *"A policy is not an algorithm."* That is deliberate. The title asks the question; the cover states the principle behind it. Keep them different — a headline and a thesis card doing the same job wastes one of them.

## Suggested article feed post

Most business systems do not implement a policy.

They implement someone's interpretation of a policy.

A subject-matter expert identifies the obligation. An analyst rewrites it as a requirement. An architect turns it into a model. A developer writes the code. A tester builds scenarios. An auditor later tries to reconstruct why the system behaved as it did.

At every handoff, a trigger, exception, or scope qualifier can quietly disappear.

I built a pipeline to close that gap, around one rule:

Decide as much as possible with code. Prove what can be proved. Ask a model only what genuinely requires judgment. Send a human only what survives all three.

That ordering is the whole point. It inverts the usual instinct of reaching for the model first and adding guardrails afterwards — here the model is the last resort before a human, and every stage exists to make its job smaller.

Concretely: literal quote resolution against the raw corpus, deterministic readiness invariants, mechanical dataflow tests for rule dependencies, and a frozen formal semantics where obligations like decision-table disjointness are proved rather than assessed — returning "unknown" rather than a green tick when the domain is unbounded.

The most useful thing it does is refuse.

It will not draw a process diagram unless the source actually shows an ordered process with a trigger, an actor, and multiple evidenced steps. On privacy policies, that means it declines for the overwhelming majority of rules — which is the correct answer, not a shortfall.

It also caught its own extraction model inventing rule identifiers that had never existed anywhere, while every artifact still rendered perfectly.

That is the real risk in AI-assisted policy work: not output that looks wrong, but output that looks right.

Where does policy meaning most often get lost in your organisation — interpretation, implementation, testing, or change management?

## Standalone infographic post

Use `images/06-policy-to-code-infographic.png` as the media.

> Turning policy into code is not one transformation. It is a chain of semantic commitments.
>
> Policy must become governed vocabulary and atomic rule contracts. Those rules must be normalised, connected, and independently checked against source evidence. Only then should a system generate the representation the source actually supports — a decision, an ordered process, a case, a data model, or nothing at all.
>
> Traceability runs forward into the artifacts and backward to the exact source passage. Where semantics are absent, the pipeline refuses to invent them.
>
> The objective is not automation at any cost. It is selective automation with explicit evidence and clear boundaries.

## Standalone refusal post

Use `images/05-standards-by-question.png`. The refusal idea is the most shareable single point in the whole piece.

> We built a system that turns policy documents into decision models, process models, and data schemas.
>
> Its most useful behaviour is declining to produce them.
>
> It will not emit a process diagram because two rules happen to share a dependency. It requires an evidenced trigger, a responsible actor, and at least two explicitly ordered steps in the source text. On privacy policies, that test declines for the overwhelming majority of rules — because a privacy policy states obligations, it does not describe workflows.
>
> Generating a diagram for every rule would have looked like far more progress and meant considerably less.
>
> Sometimes the most accurate diagram is no diagram.

## Standalone verification post

**Headline: Verifying AI Shouldn't Need Another Opinion**

Use `images/07-verification-ladder.png`. This is the argument most likely to be challenged, so it is worth making on its own.

> "Isn't that just LLM-as-a-judge?"
>
> It is the first question anyone asks about AI verification, and both familiar answers have problems. A second model inherits the first one's blind spots and grades the same quality the generator optimised for: plausibility. A subject-matter expert is the real gold standard — and cannot read several hundred rules by hand every time a policy changes.
>
> There is a third position, and it starts with an observation: most verification questions are not matters of opinion.
>
> Does this quoted sentence literally occur in the cited source? String resolution. Does this reference point at something that exists? Set membership. Does rule B actually read a value that rule A assigns? A mechanical dataflow test. Can this condition be satisfied at all? A solver.
>
> On a real corpus, the overwhelming majority of relationship claims were settled by checks like these, with no model involved.
>
> The difference is not a better judge. It is far fewer questions that need judging — and an expert who spends their attention on the ones that genuinely do.

## Standalone "proved, not tested" post

**Headline: Your AI Passed Every Test. Would It Survive a Proof?**

The single most differentiating claim in the piece, and the one least likely to be matched by anyone else posting about AI tooling. Worth its own slot.

> Most AI projects ship tests. A test checks that one example behaved.
>
> We proved six properties instead. A proof checks that no example can misbehave.
>
> The most legible one: in our type system, Money and Percentage are incomparable.
>
> Both are decimal numbers. A system that quietly reconciles them will eventually read a 3% rate as $3. That cannot happen in ours — and "cannot" is the operative word. It is not a test that passed on the inputs someone happened to think of. It is a property that holds for every pair of types in the system, proved by exhaustive enumeration.
>
> The others are the same shape. Type reconciliation returns the unique narrowest reading or refuses outright, never a coercion. The prover never reports "proved" for something satisfiable. The dependency graphs form a partition of the rule set — every rule in exactly one, none lost, none double-counted.
>
> They run in a couple of seconds:
>
> $ python proofs/check_properties.py
> ALL PROPERTIES HOLD
>
> If a system's whole argument is "you can check my work," that has to include checking the checker.
>
> What would it take for you to trust a verification claim about an AI system?

No image needed — the terminal output is the visual. If you want one, screenshot the run.

## Suggested hashtags

Five to seven, not a block:

`#ResponsibleAI` `#EnterpriseAI` `#PolicyAutomation` `#KnowledgeGraphs` `#Compliance` `#DecisionIntelligence` `#BusinessRules`

## Image sequence and alt text

Seven images, all rendered from the SVG masters beside them. Edit the SVG, never the PNG, and re-render with:

```bash
rsvg-convert -w 3200 -h 1800 <name>.svg -o <name>.png          # landscape
rsvg-convert -w 2160 -h 2700 06-policy-to-code-infographic.svg -o 06-policy-to-code-infographic.png
```

1. `images/01-policy-logic-forge-hero.png` — **article cover.**
   Alt: "Policy Logic Forge carries evidence through four phases: policy, structured knowledge, reasoning and verification, and code-ready artifacts."
2. `images/02-policy-translation-gap.png` — after the eight-questions list.
   Alt: "A policy clause passes through expert, analyst, architect, developer, tester, and auditor handoffs where actor, trigger, timing, exception, scope, and evidence can be lost."
3. `images/03-capabilities-evidence-spine.png` — after the capabilities list.
   Alt: "Eight policy-transformation capabilities connect to a central bidirectional evidence spine."
4. `images/04-policy-logic-forge-architecture.png` — opening the architecture section.
   Alt: "The stages of Policy Logic Forge grouped into source, knowledge, verification, model, and exploration responsibilities."
5. `images/07-verification-ladder.png` — in the *"Isn't this just LLM-as-a-judge?"* section. **The single most important visual in the piece:** it answers the objection every technical reader will raise, and it is the clearest statement of what is actually different here.
   Alt: "Four kinds of verification in order of strength: deterministic checks with no model; a bounded prover that discharges obligations such as pairwise disjointness and returns unknown rather than guessing; a model used only where judgment is irreducible; and the human expert reserved for legal correctness."
6. `images/05-standards-by-question.png` — in the standards section. **Also a strong standalone post.**
   Alt: "SBVR, DMN, BPMN, CMMN, LinkML, and a compiled representation each answer a different business question, behind a source-support gate."
7. `images/06-policy-to-code-infographic.png` — near the close, and reused as an independent feed post.
   Alt: "A portrait infographic showing the complete Policy to Knowledge to Reasoning and Verification to Code-ready Artifacts journey, with bidirectional traceability and business outcomes."

## Publishing checklist

- Upload `01-...-hero.png` as the cover, then insert the rest at the marked positions.
- **Do not convert any list back into a table.** See the format constraint above.
- **Do not add performance figures.** See the editorial position above; if you want them, they belong in a follow-up post with the run context attached.
- Keep short paragraphs and descriptive headings for mobile.
- Preserve the "What exists today — and what does not" section and the scope note. They are the article's credibility, not boilerplate.
- Put the repository link in the article *and* the first comment.
- Reply to early comments within the first hour; it materially affects distribution.
- Use image 05 or 06 as a follow-up post rather than repeating the cover.
- Preview on desktop and mobile before publishing.
- Do not add accuracy, legal-correctness, or production-readiness claims without new expert-labelled evidence.
