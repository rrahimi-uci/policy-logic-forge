# PIPE-2B rule-recall protocol

PIPE-2B measures semantic rule recall against a frozen, independently
annotated sampling frame. Source-byte coverage and model saturation are not
semantic recall.

## Required real-evidence frame

Before a corpus claim, the frame must contain:

- a licensed, stratified source sample with immutable lowercase hexadecimal
  SHA-256 hashes;
- two independent annotator files using the same semantic rule schema;
- an adjudication file retaining disagreements and decisions;
- source quotes that occur verbatim in the hashed source files;
- extractor predictions from a pinned configuration and code revision; and
- an agreement statistic (for example, exact semantic-key agreement and an
  appropriate chance-corrected measure where the sample supports it).

The evaluator requires every semantic field and source quote to be a
non-empty string, validates source hashes as lowercase hexadecimal SHA-256,
and rejects frames without an explicit claim boundary. It matches semantic
keys, not model-generated rule IDs. A match is
the normalized tuple `(source_id, rule_type, subject, action, object)`. It
reports matched, missing, and false-positive rules, plus per-source precision
and recall. It also reports descriptive 95% Wilson intervals for the frozen
frame and semantic-key agreement between the two annotators. These intervals
and agreement values are frame diagnostics only; they are not population
uncertainty or chance-corrected human IAA without the real stratified sampling
weights, licensed source frame, and approved annotation protocol.

## Checked-in fixture boundary

`tests/fixtures/rule_recall_gold/` is synthetic and marked
`evidence_status: fixture_only`. It exists to test provenance validation,
adjudication wiring, semantic-key matching, and deterministic metrics without
an API call. Its result must not be called a corpus recall estimate or human
inter-annotator agreement.

Run it with:

```bash
.venv/bin/python scripts/rule_recall.py \
  --fixture tests/fixtures/rule_recall_gold \
  --output results/aggregates/rule_recall.json
```

The real PIPE-2B result remains blocked until the independent human annotation
frame and adjudication are available.
