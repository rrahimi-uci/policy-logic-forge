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
| Graph and executable review | Rule-only layered SVG dependency DAG (deterministic Layer 0+ topology, arrow direction, direct-neighborhood highlighting) with selected-rule evidence, relationships, interactive DMN decision table, and BPMN workflow drill-down. Complete rule/relationship pagination keeps large runs intact. | Layering/entity-exclusion component tests, API pagination tests, backend offset route test, mortgage API smoke checks, frontend build and coverage. |
| Human overlay | SQLite comments, decisions, labels, saved views, audit history, artifact-hash stale detection. | Store/API tests and rule-workbench interaction tests. |
| Search and comparison | Rules, source chunks, evidence, relationships, diagnostics search; exact-ID/hash-bound rule and relationship comparison. | API/index tests and UI comparison/search tests. |
| Delivery boundary | Stdlib HTTP API with safe artifact traversal and static SPA serving; no pipeline imports or canonical writes. | HTTP integration tests, full repository pytest, TypeScript/lint/build. |
| Professional UX pass | Responsive desktop rail and mobile drawer, SVG navigation, semantic stage stepper, command-style search dialog, explicit refresh/error feedback, adaptive tables and evidence layouts, focus and reduced-motion support. | Component coverage, production build, and retained-run rendering at 1440×1000 and 390×844. |

## Explicit limitations and next increments

- The UI renders the normalized rule execution contract and Agent 11's DMN/BPMN
  metadata as a review projection. It is not a DMN/BPMN execution engine and
  does not replace a standards-compliant modeler or third-party engine
  discrepancy view.
- Comparison is conservative: exact IDs are compared first, then structural
  and evidence hashes. Semantic matching, review-delta export, and multi-user
  assignment are intentionally follow-on work.
- Local mode uses SQLite and in-memory API filtering over a normalized index.
  PostgreSQL/OpenSearch and server-side pagination are appropriate only when a
  multi-user deployment requires them.
- The professional UX pass was rendered against the retained privacy-policy run
  in local Chrome at desktop and mobile viewport sizes. Automated browser
  screenshots are still not a CI gate; jsdom integration coverage and the
  production build remain the deterministic repository checks.

The limitations above are visible in the UI as review/health state rather than
being represented as successful empty results.
