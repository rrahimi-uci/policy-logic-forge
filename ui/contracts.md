# Review workbench contracts

The backend exposes a read model with a deliberately small, stable contract.
All IDs are deterministic within a run and every normalized record retains its
canonical `artifact_path` (or source chunk path). The UI can therefore render a
review result without reading the raw bundle itself.

## Read model records

- `run_summary.json`: run status, stage counts, rule/readiness/grounding counts,
  queue counts, corpus and graph hashes, model metadata.
- `stage_index.json` / `stage_status.json`: one record per agent 01–11 with
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

## Upload and job write surface (a deliberate, scoped exception)

The API rules above ("canonical artifacts are read-only," "review writes are
limited to the overlay routes") describe the review workbench's original
scope: a read model over already-completed runs. `POST /api/uploads` and
`POST /api/jobs` (plus `POST /api/runs/{run_id}/resume`) are a deliberate,
narrowly scoped exception to that boundary, added so the UI can accept a
document upload and drive `cli/extract.py` end to end instead of only
watching for runs that already exist:

- `POST /api/uploads` streams a multipart upload to
  `compliance-files/uploads/<upload_id>/<relative-path>` (see
  `ui/backend/multipart.py`) and records an `uploads` row in `review.db`.
  This is new pipeline *input*, not a canonical artifact -- it lives outside
  `pipeline_root` and is never read by the review index.
- `POST /api/jobs` and `POST /api/runs/{run_id}/resume` start
  `cli/extract.py` as an OS subprocess (`ui/backend/jobs.py`'s `JobRunner`)
  and record a `jobs` row. The pipeline itself never imports from
  `ui/backend` and never reads or writes `review.db` -- it only writes its
  normal canonical output under `pipeline-output/<batch_name>/`, exactly as
  it does when launched directly from the CLI. The `jobs` table is
  UI-side bookkeeping (status, pid, log path, exit code) about a subprocess
  the UI started, not a change to what the pipeline itself produces or how
  it produces it.
- Resume-stage bookkeeping (`pipeline_run_state.json`, written by
  `utils/pipeline_state.py`) stays inside the run bundle itself, not in
  `review.db` -- it's bundle metadata the CLI depends on to resume without
  the UI, not review-overlay metadata.

Every other route remains exactly as scoped above: rules, relationships,
stages, evidence, diagnostics, and comparisons are still read-only over
`pipeline_root`, and review writes (comments, decisions, labels, saved
views) are still limited to the overlay routes.

## Comparison semantics

Comparison matches exact rule/relationship IDs first. Structural and evidence
hashes then identify changes; uncertain semantic matches are not guessed. The
response reports added, removed, and changed rules and relationships plus the
run summaries used for the comparison.
