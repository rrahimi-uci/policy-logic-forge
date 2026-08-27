# Full compliance-pipeline E2E validation (2026-08-27)

This report records end-to-end runs for every dataset under `compliance-files/`.
Generated pipeline outputs are intentionally not committed; the commands and
checks below are the reproducible evidence for each run.

## Dataset inventory

| Dataset | Source inventory | Run | Status |
|---|---:|---|---|
| `privacy_policy` | 115 files | `e2e-privacy-20260826` | Agents 01–10 complete; readiness/grounding review gates retained |
| `mobile_app_privacy` | 155 files | `e2e-mobile-20260826` | Agents 01–08 complete; review-gated readiness remains |
| `mortgage` | 1 PDF (Fannie Mae, 1,191 pages) | `e2e-mortgage-20260827` | Agents 01–10 complete; review-gated readiness/grounding retained |
| `nda_confidentiality` | 607 files | `e2e-nda-20260827` | Agent 01 complete; Agent 03 full-coverage extraction in progress |
| `commercial_contracts` | 510 files | `e2e-commercial-20260827` | Agent 01 in progress |
| `deonticbench` | 6,483 official `.txt` cases (smoke fixture excluded) | `e2e-deonticbench-20260827` | Agent 01 in progress |

## Reproducibility

Runs use the repository virtual environment, `--workers 40`, the configured
`gpt-5.6-luna` model, and isolated limiter state files. Source PDFs and all
generated `pipeline-output/` artifacts are local-only and ignored by Git.

## Validation policy

Exit code 0 means the stage completed; readiness and grounding exit codes 2/3
are expected review gates and must remain visible. A dataset is not reported as
fully certified unless corpus coverage, schema, referential integrity,
grounding coverage, and Agent 10 DAG coverage all pass. Any transient API or
worker failure is recorded with its root cause and rerun result.

## Completed evidence

### Mortgage

- Agent 01: 506 chunks from the source PDF, no failures.
- Agent 02: 26 entity types, 30 relationships, 60 business rules, quality 85.
- Agent 03: 640 extracted rules, 0 dropped bytes, full source coverage.
- Agent 04: completed (3 checks passed, 2 failures, 138 warnings; advisory).
- Agent 05: complete knowledge graph with 640 rules.
- Agent 06: 631 optimized rules, 481 dependencies, no failures/throttling.
- Agent 07: 69 ready / 562 review; corpus, naming, and referential invariants pass;
  schema violations remain review-gated.
- Agent 08: three remediation passes; 462 ready / 169 review; no failures/throttling.
- Agent 09: completed with review-gated findings; no unreported failures.
- Agent 10: 235 DAGs cover 631/631 rules, 0 dropped edges, 1 cycle group.

### Privacy and mobile

The previously completed runs retain their fail-closed readiness and grounding
findings. They are included in the final reconciliation with the same invariant
checks; review-gated outputs are not converted into certification claims.

### NDA extraction and downstream validation (active)

Agent 03 completed all 622/622 batches (0 failed) with a bounded, isolated
limiter state and reusable checkpoints. It
published 2,741 rules after merging and uniqueness enforcement. Empty/length-
truncated responses were recovered by the compact retry path and malformed JSON
was repaired strictly; the final coverage artifact passed without dropped
source batches.

One batch returned a valid empty rule set. It remains visible for later
coverage/data-quality review rather than being silently converted into a
failure.

Agent 04 completed successfully (2,049 loaded rules, 4,467 source documents,
10/10 sampled source checks verified, 29 completeness failures retained for
review). Agent 05 completed successfully and produced the unified graph with
2,741 rules, 17 entity types, and 21 relationships. Agent 06 completed
successfully: deduplication reduced the graph to 2,631 rules (110 removed),
and optimization added 1,136 dependencies with unique rule identifiers.
Agent 07 is being rerun from its preserved checkpoint after a concurrent
commercial extraction saturated the provider connection pool. The degraded
attempt was stopped before publishing; 1,104 successful rule results remain
checkpointed, and the clean rerun uses a fresh isolated limiter while commercial
Agent 03 is paused. The clean rerun currently has 1,400 total checkpointed
results (296 added in the clean pass), with 131 successful calls and no failures
or throttles. The final readiness artifact is not yet published.

During continued concurrent execution, a later provider connection burst caused
additional transient API connection/time-out failures and adaptive limiter
backoff. No checkpointed results were lost. Both model jobs were stopped
gracefully, and Agent 07 was restarted alone with a fresh limiter for recovery;
the preserved checkpoint currently contains 1,599 unique rules.

The isolated recovery completed 385 calls before a second provider outage caused
eight consecutive API connection failures and limiter backoff to one request.
It was stopped safely before publishing an incomplete readiness graph; the
checkpoint remains preserved at 2,161 lines. This is recorded as an external
provider availability issue, not a data or schema failure.

A third isolated retry reproduced the same external failure: 22 successful calls
followed by eight API connection failures and limiter backoff. It was stopped
without publishing partial output; the durable checkpoint now contains 2,167
lines. Local tests remain green, but completion of model-dependent stages is
blocked on provider recovery.

The earlier partial attempt did encounter repeated HTTP 500/API connection
errors after 122 batches. It was stopped without publishing an incomplete
artifact; those checkpoints remain reusable and motivated the isolated limiter
and resume validation.

### Commercial contracts (active downstream)

Agent 01 completed all 510/510 source files successfully and materialized 13,822
chunks. Agent 02 completed successfully (13 entity types, 22 relationships,
58 initial rules). Agent 03 was paused after 8 successful batches when its
concurrent API load caused NDA readiness connection failures; those 8 batches
are checkpointed for a stable resume after NDA readiness completes.

### DeonticBench (active)

The initial launch was stopped before writing outputs after inventory checks
showed a repository smoke fixture alongside the official benchmark. The
corrected run targets `compliance-files/deonticbench` and excludes underscore
metadata/smoke directories during recursive discovery, covering exactly 6,483
official cases. The orchestrator also ignores unsupported top-level metadata
when selecting files, with regression tests for both layouts.
The corrected run was safely paused at 349/6,483 official cases in the live log
after the shared provider connection burst; its resumable output is preserved
and no organizer failures were reported.

## Known shared fixes under validation

- Organizer resume/checkpoint matching and duplicate-title collision handling.
- Rule checkpoint corpus fingerprints and malformed-candidate normalization.
- Bounded grounding request sizes and single-wrong-claim review fallback.
- Remediation worker exception fallback that preserves unresolved review items.
- Hidden-file filtering and fail-closed continuation from review-only grounding.

The final section will be updated after NDA, commercial, and DeonticBench runs
complete with exact counts, commands, failures, reruns, and validation results.
