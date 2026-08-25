# Anchor data licensing and reuse posture (A3)

**Status:** characterization complete; legal clearance and permission to
redistribute upstream artifacts are **not** established.

**Audit basis:** pinned upstream commit
[`6a4844fb235d4f958d0810bba7089a2e9078099e`](https://github.com/opengov-lab/legal-text-to-decision-model/tree/6a4844fb235d4f958d0810bba7089a2e9078099e)
and its repository `LICENSE` and `README.md`, inspected on 2026-08-24. The
release inventory and evaluator replay are documented in
[`anchor_release_audit.md`](anchor_release_audit.md) and
[`anchor_aggregation_recipe.md`](anchor_aggregation_recipe.md).

## What is and is not licensed

| Asset | Evidence at the pinned revision | Repository posture |
| --- | --- | --- |
| Upstream evaluator and supporting code | Upstream `LICENSE` states CC BY 4.0 | Not copied or vendored; replay from a temporary checkout only |
| Upstream paper and generated-model release | Upstream `README.md` identifies David Graus's ICAIL 2026 paper and the released `generated_models/`, `gold_models/`, `source_models/`, `legal_text/`, and `raw_legal_data/` trees | Not redistributed; cite the paper and upstream repository when discussing the release |
| Dutch government legal/source data | Upstream `README.md` says no explicit license is provided and describes reuse under the Dutch Wet hergebruik van overheidsinformatie as an assumption | Treat as unresolved; this is not permission to re-host or publish the data |
| This repository's code and derived metadata | This repository's root `LICENSE` is MIT; A1B retains hashes, counts, aggregate values, and mismatch examples | Redistribute only these code/docs/manifest/hash/aggregate artifacts, subject to checking that they contain no upstream source or model content |

The upstream CC BY notice covers the upstream work under its terms; it does
not by itself prove that every embedded Dutch government or derived artifact
has the same license. Attribution is required for any permitted upstream-code
use, and the paper should be cited for claims about the benchmark protocol.

## Release boundary

The following are intentionally absent from this repository and must remain
absent from future release bundles until a named owner records documented
authority:

- raw Dutch legal XML or legal-text files;
- upstream source DMN, gold-model, or generated-model files;
- copied upstream result CSVs or evaluator caches; and
- any pipeline output that embeds or can reconstruct those artifacts.

The committed Dutch split contains model identifiers, condition names, run
counts, path templates, and selection rules only. The A1B report contains
SHA-256 digests and descriptive replay aggregates, not the upstream files.
This is a provenance record, not a license grant or a statement that the
historical results have been reproduced.

## Required action before any broader release

1. The repository owner must review the exact release allowlist and the
   attribution text.
2. Re-check the upstream license and the Dutch source-data terms at the pinned
   revision; record any written permission or an explicit exclusion.
3. Run the bundle release validator and inspect the archive for source, gold,
   generated, raw, restricted, and local-only roles.
4. Do not contact upstream authors or maintainers without owner approval of
   the exact recipients and message.

No author or maintainer contact was made for A3. Until the open data-rights
question is resolved, publication may include the evaluator recipe, scripts,
manifests, hashes, and clearly labeled derived diagnostics only.
