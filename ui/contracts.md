# Review workbench contracts

The backend exposes a read model with a deliberately small, stable contract.
All IDs are deterministic within a run and every normalized record retains its
canonical `artifact_path` (or source chunk path). The UI can therefore render a
review result without reading the raw bundle itself.

## Read model records

- `run_summary.json`: run status, stage counts, rule/readiness/grounding counts,
  queue counts, corpus and graph hashes, model metadata.
- `stage_index.json` / `stage_status.json`: one record per agent 01–10 with
  status, embedded checkpoint count, artifact inventory, timestamps, input/output
  counts, and scoped warning/failure counts.
- `rule_index.jsonl`: canonical rule fields plus machine status, structural and
  evidence hashes, source reference, field evidence, execution projections,
  contract issues, and test vectors.
- `relationship_index.jsonl`: entity-type definitions, dependencies, conflicts,
  and DAG edges. Each relationship has a stable ID and provenance path.
- `document_index.jsonl` and `evidence_index.jsonl`: source chunks and field
  support records with hashes, quotes, verdicts, and rule linkage.
- `diagnostics.json`: explicit error/warning findings; missing or malformed
  artifacts become findings instead of successful empty states.

## API rules

- Canonical artifacts are read-only. `GET /api/runs/{run_id}/artifacts` is a
  secondary viewer and caps inline content at 2 MB, returning `truncated: true`
  when necessary.
- Review writes are limited to the overlay routes: comments, decisions, labels,
  saved views, and history. A write must reference an existing run.
- Overlay records carry the artifact hash when applicable. Rule responses mark
  comments and decisions stale when a rerun changes the structural/evidence hash.
- Unknown runs, artifacts, rules, queues, and evidence return 404; malformed
  review payloads return 400. This keeps review failures visible and fail closed.

## Comparison semantics

Comparison matches exact rule/relationship IDs first. Structural and evidence
hashes then identify changes; uncertain semantic matches are not guessed. The
response reports added, removed, and changed rules and relationships plus the
run summaries used for the comparison.
