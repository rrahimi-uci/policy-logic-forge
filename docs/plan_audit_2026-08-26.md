# Plan audit — 2026-08-26

This historical report records the August 26, 2026 review of the now-removed
NeurIPS execution plan and its companion documents against the repository's
code, tests, validators, and retained artifacts at that time. The canonical
current direction is [`plan/proposal.md`](../plan/proposal.md); the task IDs
below remain preserved in `plan/tasks.json` as historical implementation
evidence.

## Findings applied

- The main drift was status accounting: 21 tasks were still marked `partial`
  even though their registered acceptance commands and artifacts already
  passed locally.
- The plan contract now distinguishes `implemented` from `done`.
  `implemented` means the code, tests, docs, and retained non-claiming
  artifacts are complete, while the scientific gate still depends on licensed
  annotations, human adjudication, an approved third-party engine run, or
  GPU/provider authorization.
- The generated summary now reports both `Done pd` and `Executable pd`, which
  makes the implementation boundary visible without overstating scientific
  completion.
- `A2` now has the previously missing preregistration, retained placeholder
  artifact, and artifact validation coverage, so its optional branch is
  implemented even though no fresh generation run has been executed.

## Current implementation boundary

- Minimum paper scope: 125 / 125 person-days executable locally.
- Second-domain extension: 151 / 151 person-days executable locally.
- Full programme: 171 / 171 person-days executable locally.
- Remaining executable gaps: 0 person-days.

## Remaining scientific gaps

- `PIPE-2B` and `PIPE-4` need licensed stratified samples, two independent
  human annotations, adjudication, and agreement statistics before they can
  support extraction-quality claims.
- `IR-2` and `BE-4` need approved real-engine or real-corpus evidence beyond
  the retained exploratory and protocol artifacts.
- `J1`, `J1B`, `STAT-1..3`, `PERTURB-1`, `INST-1`, `BENCH-1B`, `ASM-1`, and
  `CEGIR-1` have provider-free implementations and retained non-claiming
  artifacts, but not the external evidence needed for publishable claims.
- `A2` is implemented as a blocked retained-run contract pending explicit
  paid-provider approval for any fresh generation.
- `RL-1..4` are implemented provider-gated contracts; actual training or
  reward-frontier claims still require explicit GPU/provider authorization.

## Verification run in this audit

- `.venv/bin/python scripts/validate_neurips_plan.py --check`
- `.venv/bin/python scripts/validate_neurips_plan.py --ready`
- `.venv/bin/python scripts/validate_g0_evidence.py`
- `.venv/bin/python scripts/validate_research_artifacts.py`
- `.venv/bin/python scripts/validate_config.py`
- `.venv/bin/python scripts/validate_neurips_plan.py --run-complete`
- `.venv/bin/python -m pytest -q`
- `.venv/bin/python -m coverage run -m pytest -q`
- `.venv/bin/python -m coverage report`
- `.venv/bin/python -m compileall -q agents bench compiler training utils cli scripts tests`
- `git diff --check`

All listed commands passed in this audit PR.
