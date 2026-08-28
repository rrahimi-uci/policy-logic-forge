# RegDelta plans and task contracts

RegDelta has two parallel planning documents, sharing one engine design but
diverging on what proves it works:

- [`proposal.md`](proposal.md) is the research/benchmark track. It targets
  academic venues and depends on acquiring external evaluation resources
  (OpenExempt-CF, RegelRecht-Real) not yet present in this repository. It
  replaces the superseded NeurIPS proposal and plan.
- [`regdelta-product-plan.md`](regdelta-product-plan.md) is the
  product-engineering track. It validates the same engine entirely against
  data and code this repository already has (starting with the `mortgage`
  domain's already-complete agent_01-11 pipeline output), with no external
  acquisition on the critical path.

Section 6 of `proposal.md` and Section 6 of `regdelta-product-plan.md`
describe the same compiler/alignment/differential-execution engine, and
Phases 1-2 of each document's implementation plan are identical for the same
reason — that part of the design does not depend on which validation data
proves it, so keep those in sync if either changes. Everything else
(validation data, domain rollout order, success criteria, and `proposal.md`'s
Section 7 benchmark design specifically) is intentionally track-specific.

This directory also retains the machine-readable contracts produced by the
earlier compiler programme:

- `tasks.json` is the historical registry for task IDs, dependency edges, statuses,
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
.venv/bin/python scripts/validate_neurips_plan.py --run-complete
```

Do not mark a task `done` until all its acceptance commands pass and all its
artifact/evidence paths exist and the named scientific or prerequisite gate is
actually satisfied. Use `implemented` when code, tests, docs, and retained
non-claiming artifacts are complete but the scientific gate still depends on
licensed data, approved external engines, human adjudication, or
GPU/provider-approved runs. Use `conditional` for work outside the committed
scope and `blocked` only when a named external dependency prevents execution.
`--summary` renders the historical registry summary; it is not embedded in or
authoritative for the new RegDelta proposal. Future RegDelta implementation
tasks should update or replace the registry explicitly rather than inheriting
legacy completion statuses.
