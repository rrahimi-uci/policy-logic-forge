# PIPE-4 dependency-audit protocol

PIPE-4 measures dependency discovery precision and recall on a frozen edge
universe. A DAG coverage count is not dependency accuracy: every candidate
edge needs a positive or explicit negative disposition.

## Required real-evidence frame

A real audit must include:

- a declared rule universe and candidate directed edge/type universe;
- explicit negative edges, including plausible non-dependencies;
- two independent annotator edge sets;
- an adjudication record retaining disagreements and decisions;
- agreement statistics over positive and negative edge labels; and
- predictions from a pinned optimizer configuration and code revision.

The evaluator validates that no edge escapes the universe, self-loops are not
silently accepted, and a prediction cannot be counted outside the candidate
edge set. Precision and recall match typed `(source_rule_id, target_rule_id,
dependency_type)` edges.

## Checked-in fixture boundary

`tests/fixtures/dependency_gold/` is synthetic and marked
`evidence_status: fixture_only`. It exists to test the audit contract without
an API call. Its 0.5 precision, 0.5 recall, and 1.0 Jaccard agreement values
must not be presented as corpus dependency quality or human IAA.

Run it with:

```bash
.venv/bin/python scripts/dependency_audit.py \
  --fixture tests/fixtures/dependency_gold \
  --output results/aggregates/dependency_audit.json
```

The real PIPE-4 result remains blocked until the licensed, independently
annotated rule/dependency frame is available.
