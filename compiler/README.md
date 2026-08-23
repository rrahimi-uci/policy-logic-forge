# compiler/

Scaffold for compiling a grounding-certified knowledge graph into executable
DMN 1.3 and BPMN 2.0. **Not implemented yet** — see [`../k-to-code.md`](../k-to-code.md)
for the full feasibility study and phased plan (phases C0-C4) before writing
code here.

Planned modules (Phase C1):

- `feel.py` — a bounded FEEL renderer + matching evaluator (8 operators, 7
  variable types measured in the real certified graph the plan's spike used;
  fails loudly on anything outside that subset rather than guessing).
- `dmn_builder.py` — `condition_logic` -> DNF -> DMN decision-table rows, hit-policy
  reconciliation, provenance extension elements.
- `bpmn_builder.py` (Phase C3) — one process per multi-rule dependency DAG
  (`agents/agent_6_dag_generator.py` output), sequence flow from
  `prerequisite`/`sequential` edges only.
- `conformance.py` (Phase C4) — replay every rule's `test_vectors` through the
  emitted artifact; refuse to publish a decision that fails its own vectors.

Before starting Phase C1, resolve the plan's open questions (Q1-Q5) — most
consequentially Q2 (exception-list boolean semantics) and Q1 (which corpora to
run under the v2 contract first).
