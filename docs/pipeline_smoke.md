# Pipeline configuration smoke run

This is a provider-backed, one-document smoke test of the extraction pipeline,
not a benchmark result or corpus-coverage claim. The source file and all
pipeline outputs remain local-only and are ignored by Git; this repository
retains only the metadata/hash manifest at
[`results/aggregates/config_high_smoke/run_manifest.json`](../results/aggregates/config_high_smoke/run_manifest.json).

## Configuration verified

- model: `gpt-5.6-luna`
- reasoning effort: `high`
- reasoning completion budget: `32768` (the normal runtime minimum; do not use
  an 8k cap for this pipeline)
- optimizer skipped for the smoke run; no optimizer/grounding quality claim
- one deterministic NDA source file, one pilot extraction batch, one worker

## Reproduction command

From the repository root, with the local `.env` key configured:

```bash
KG_ENTITY_EARLY_STOP=true \
KG_ENTITY_MIN_ITERATIONS=1 \
KG_ENTITY_SAMPLE_DOCUMENTS=1 \
KG_ENTITY_SAMPLE_CHARS=800 \
.venv/bin/python cli/extract.py \
  --dir /path/to/one-file-nda-directory \
  --domain nda_confidentiality \
  --batch-name config-high-smoke-20260825-r2 \
  --target-rules 1 \
  --pilot-batch-limit 1 \
  --workers 1 \
  --skip-optimize
```

## Observed result

The run completed canonical stages `01/11`, `02/11`, `03/11`, `04/11`,
`05/11`, and `10/11` successfully (Agent 06–09 were intentionally skipped):
12 chunks, 17 entity types, 23 relationships, 5 source-verified rules, zero
validation failures, and 5/5 DAG coverage with zero cycles. The retained
manifest records the input/output hashes and explicitly labels the run as a
smoke test.
