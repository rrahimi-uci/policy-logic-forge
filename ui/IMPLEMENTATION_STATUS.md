# Implementation status

This folder is the first production-oriented slice of the `ui-c2c.md` review
workbench. It is deliberately self-contained: the pipeline remains the owner
of canonical artifacts, while this layer builds disposable indexes and a
separate human-review overlay.

## Delivered in this PR

| Plan area | Implementation | Verification |
| --- | --- | --- |
| Read-model boundary | `backend/review_index.py` normalizes stages, rules, relationships, source chunks, evidence, diagnostics, hashes, queues, and FTS5 search. | Fixture and retained privacy-policy index tests; real retained run indexed with 879 rules, 1,012 source chunks, 7,636 evidence links, 3,365 relationships, and 4,244 diagnostics. |
| Run catalog and overview | Runs view, run selector, KPI/triage/provenance overview, stage flow. | React integration tests and live API smoke checks. |
| Stage observability | Stage status snapshots, checkpoint counts, artifact inventory, timestamps, scoped warning/failure counts, raw read-only artifact viewer, five-second checkpoint polling. | API and component tests; live artifact retrieval smoke check. |
| Rule review | Filterable, sortable, groupable, selectable/exportable rule table and review queues. | Component tests plus API queue/filter tests. |
| Traceability | Rule workbench, source split view, field evidence, evidence register, stable evidence IDs, source hashes. | Fixture/retained-run tests and component tests. |
| Graph and executable review | Cytoscape relationship/conflict/dependency/DAG modes and DMN/BPMN projection cards. | Graph component tests and retained relationship assertions. |
| Human overlay | SQLite comments, decisions, labels, saved views, audit history, artifact-hash stale detection. | Store/API tests and rule-workbench interaction tests. |
| Search and comparison | Rules, source chunks, evidence, relationships, diagnostics search; exact-ID/hash-bound rule and relationship comparison. | API/index tests and UI comparison/search tests. |
| Delivery boundary | Stdlib HTTP API with safe artifact traversal and static SPA serving; no pipeline imports or canonical writes. | HTTP integration tests, full repository pytest, TypeScript/lint/build. |

## Explicit limitations and next increments

- The current retained pipeline emits rule-level DMN/BPMN projections, not
  compiler-produced DMN XML or BPMN XML. The UI shows those projections and
  clearly preserves the missing-asset state; a full document viewer and
  third-party engine discrepancy view belong when those artifacts are emitted.
- Comparison is conservative: exact IDs are compared first, then structural
  and evidence hashes. Semantic matching, review-delta export, and multi-user
  assignment are intentionally follow-on work.
- Local mode uses SQLite and in-memory API filtering over a normalized index.
  PostgreSQL/OpenSearch and server-side pagination are appropriate only when a
  multi-user deployment requires them.
- Browser automation was not available in the execution environment. The
  browser-facing flows are covered by jsdom integration tests, a production
  Vite build, and a live HTTP smoke test; a real-browser screenshot pass should
  be added in CI or a workstation with the browser connector enabled.

The limitations above are visible in the UI as review/health state rather than
being represented as successful empty results.
