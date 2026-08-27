# Paper review and publication gate

## Verdict at the 27 August 2026 freeze

The manuscript is now professionally structured and technically honest, but it
is not yet a claim-complete NeurIPS empirical paper. The strongest defensible
contribution in this snapshot is an evidence-gated evaluation instrument plus a
reproducibility audit that rejects an unresolved benchmark anchor. A stronger
claim about semantic fidelity or outcome quality would be unsupported until the
gates below are completed.

The current draft targets the next NeurIPS cycle using the latest verified 2026
format as a proxy. NeurIPS 2026 submission dates have passed, and the official
2027 call/template must replace the local archive when published.

## Review findings addressed

- Reframed the manuscript from a pipeline/readiness memo into a paper with a
  single argument: executable validity is not source fidelity, so evaluation
  must preserve coverage, provenance, refusal, and evidence state.
- Defined attributable source fidelity (AFS), operational evidence (OPS), and
  outcome equivalence (OE), including executable yield and conditional quality
  equations.
- Promoted the retained Dutch replay disagreement to the central audit result:
  1,108 of 1,900 rows are exact and 792 differ. The mismatch is quarantined and
  is not used as an OE score.
- Kept the 1,012-document privacy run as an exploratory operational stress
  observation, not a precision, recall, or legal-correctness result.
- Replaced schematic box diagrams with vector-native TikZ architecture and
  data-driven audit plots. Plot percentages are generated from retained JSON
  artifacts, not hand-entered in TeX.
- Added an evaluation matrix, compact implementation table, claim ledger,
  publication gates, and explicit source/engine/human-study limitations.
- Corrected primary-source bibliography metadata, including Catala authors,
  RuleArena authors, DMN 1.3, and direct paper URLs.
- Removed the stale 1,051-test claim; current checkout test collection is
  volatile and is not presented as scientific evidence.

## Remaining P0 gates before a scientific headline claim

1. Root-cause the 792/1,900 replay mismatches from pinned inputs and schema
   semantics. Retain the corrected release/replay comparison and update the
   anchor status only after the validator passes.
2. Run the licensed, stratified AFS frame with two independent annotations,
   adjudication, exception/threshold/span labels, and uncertainty intervals.
3. Run OE with gold and generated artifacts in a pinned independent DMN engine;
   retain paired traces, refusal/timeout/unknown counts, and a disagreement
   taxonomy.
4. Run the preregistered human-review instrument with leakage, permutation,
   positive, and negative controls before making any reviewer-efficiency claim.

If any gate remains unavailable, the paper should remain framed as a transparent
instrument and negative reproducibility audit, or be submitted to a venue that
accepts methodological audits. It should not convert operational throughput,
fixture recall, mutation score, or implementation coverage into semantic quality.

## Local verification

The paper build regenerates evidence macros and the checklist, compiles with
Tectonic, validates source/bibliography/template hashes, checks the nine-page
content boundary, and renders successfully. The repository paper tests cover
source contracts, checklist rendering, and evidence projection. The full
repository suite and the repository-level research validators remain the final
checks after this paper change is transferred to the original checkout.
