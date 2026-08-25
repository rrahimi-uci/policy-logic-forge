# NeurIPS plan contracts

This directory contains the machine-readable contracts behind
[`neurips-plan-2027.md`](neurips-plan-2027.md):

- `tasks.json` is authoritative for task IDs, dependency edges, statuses,
  person-day estimates, scope membership, acceptance commands, artifacts, and
  evidence paths.
- `lexec-ir-v1.schema.json` is the structural contract for the proposed
  compiler intermediate representation. `docs/ir-semantics-v1.md` and
  `utils/lexec_ir.py` provide the current fail-closed G0 subset; corpus-wide
  freezing, solver proofs, and backend equivalence remain later gates.

From the repository root:

```bash
.venv/bin/python scripts/validate_neurips_plan.py --check
.venv/bin/python scripts/validate_neurips_plan.py --ready
.venv/bin/python scripts/validate_neurips_plan.py --show TASK_ID
.venv/bin/python scripts/validate_neurips_plan.py --run TASK_ID
.venv/bin/python scripts/validate_neurips_plan.py --run-done
```

Do not mark a task `done` until all its acceptance commands pass and all its
artifact/evidence paths exist. Use `conditional` for work outside the committed
scope and `blocked` only when a named external dependency prevents execution.
Update the generated summary in the Markdown plan with exact `--summary`
output in the same PR as any registry change.
