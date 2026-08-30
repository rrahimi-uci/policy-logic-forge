# Retained run evidence

This directory holds metadata-only evidence from real pipeline runs — run
manifests recording configuration, stage status, and content hashes, never
source documents or full pipeline output.

- `config_high_smoke/`, `full_smallest_privacy/` — retained manifests from
  real extraction runs, pinning status, model/reasoning configuration, and
  DAG coverage as a regression check (`tests/test_pipeline_smoke_manifest.py`,
  `tests/test_full_smallest_run_manifest.py`).
- `regdelta/` — retained results from the RegDelta differential-execution
  engine's fixture-based acceptance tests (`tests/test_mortgage_tier1_fixture.py`,
  `tests/test_regdelta_tier1_fixtures.py`, `tests/test_mortgage_tier2_extraction.py`).

Nothing here authorizes redistribution of any source document or full
pipeline output; only aggregate, hash-verifiable metadata is retained.
