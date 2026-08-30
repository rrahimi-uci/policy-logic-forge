# RegDelta plan

RegDelta is a rule-change/version differential-execution engine layered on
top of the eleven-agent extraction pipeline: given two versions of a policy
document, it compiles both to LExec IR, aligns rules, classifies semantic
changes, and propagates impact through the dependency graph.

- [`regdelta-product-plan.md`](regdelta-product-plan.md) is the current plan.
  It validates the engine entirely against data and code this repository
  already has (starting with the `mortgage` domain's already-complete
  agent_01-11 pipeline output), with no external acquisition on the critical
  path.
- `lexec-ir-v1.schema.json` is the structural contract for the compiler
  intermediate representation. `docs/ir-semantics-v1.md` and
  `utils/lexec_ir.py` implement the current fail-closed G0 subset;
  corpus-wide freezing, solver proofs, and backend equivalence remain later
  work.
