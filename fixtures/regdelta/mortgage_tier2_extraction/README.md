# Mortgage Tier 2 extraction (real, retained)

`optimized_compliance_knowledge_graph.json` in this directory is a copy of
`agent_06`'s real output from running the full agents 01-06 pipeline against
`compliance-files/mortgage-tier2-errata/selling_guide_update.txt` -- a short,
hand-authored "errata" excerpt that restates the same three passages Tier 1
hand-edited (see `fixtures/regdelta/mortgage_tier1/edit_manifest.json`), with
the edited values already applied in prose.

It is copied here because `pipeline-output/` is gitignored (local-only, one
run at a time); this is the retained evidence that the real extraction
independently recovers Tier 1's edits, per
`plan/regdelta-product-plan.md` Phase 4.

To regenerate from scratch:

```bash
PYTHONPATH=. .venv/bin/python cli/extract.py \
  --dir mortgage-tier2-errata --domain mortgage \
  --batch-name mortgage-tier2-revised --agent agent_01
# ...repeat with --agent agent_02 through agent_06...

.venv/bin/python scripts/compare_tier2_extraction.py
```

The real extraction assigns its own rule IDs and its own variable names
(`ltv_ratio`, not `ltv_ratio_percent`; `B1-R001-HIGH-LTV-MI-REQUIREMENT`, not
`R-120-004`) -- alignment against Tier 1's edits is therefore by regulatory
citation code (e.g. `B7-1-01`) extracted from each side's
`source_reference.section_id`, not by rule ID; see
`scripts/compare_tier2_extraction.py`.
