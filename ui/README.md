# Policy Logic Forge review workbench

See [`contracts.md`](contracts.md) for the normalized read-model, API, overlay,
and comparison contracts. [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md)
maps the delivered surfaces to `ui-c2c.md` and records explicit follow-up
limits.

The review workbench turns an existing `pipeline-output/<run>/` bundle into a
provenance-first workspace for triage, source validation, layered rule-graph inspection,
run comparison, and human review decisions. The pipeline remains the source of
truth; generated indexes are disposable and reviewer state is stored separately.

## Local run

From the repository root:

```bash
python3 -m ui.backend.review_index \
  pipeline-output/privacy-policy-full-20260825 \
  --output ui/.cache/review-index/privacy-policy-full-20260825

cd ui/frontend
npm install
npm run build
cd ../..
python3 -m ui.backend.api --pipeline-root pipeline-output --port 8787
```

Open <http://127.0.0.1:8787>. The API lazily indexes discovered runs, so the
explicit index command is useful for validating a bundle or warming a shared
index but is not required for a first local visit.

For frontend-only development, run `npm run dev` in `ui/frontend`. Set
`VITE_C2C_API_BASE` if the API is on another origin.

## Read model

`ui/backend/review_index.py` consumes the current agent 01–11 folder layout,
including embedded agent 07–09 checkpoints and executable DMN/BPMN outputs
from agent 11. It writes `run_summary.json`,
`stage_index.json`, JSONL indexes for rules, relationships, documents and
evidence, comparison hashes, and a SQLite FTS5 search database. Missing or
malformed artifacts become explicit diagnostics.

`ui/backend/api.py` serves normalized records through `/api` endpoints and
static frontend assets. `ui/backend/review_store.py` stores comments and
decisions, labels, saved views, and audit history in an overlay SQLite database
keyed by run, artifact, and hash. No endpoint mutates canonical pipeline files.
The API fingerprints bundle file size/mtime and refreshes its cached index when
checkpoint files change, which makes the frontend's five-second polling useful
during an in-flight run.

The API also exposes an evidence register (`/runs/{run_id}/evidence`),
relationship filters, read-only artifact retrieval, and review overlay routes:
`/review/comments`, `/review/decisions`, `/review/labels`, `/review/views`, and
`/review/history`.

## Quality gates

```bash
.venv/bin/python -m coverage erase
.venv/bin/python -m coverage run --source=ui/backend -m pytest -q ui/tests
.venv/bin/python -m coverage report --include='ui/backend/*.py' --fail-under=85
cd ui/frontend
npm run lint
npm run test:coverage
npm run build
```

The fixture tests exercise a compact bundle and a retained privacy-policy run;
the browser-facing tests cover the overview, queue, workbench, source/evidence,
graph, diagnostics, comparison, search, and review-overlay flows.
