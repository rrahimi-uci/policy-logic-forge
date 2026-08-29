# Semantic DMN/BPMN/CMMN export

`cli/generate_executable_models.py` creates review-aware DMN 1.3, BPMN 2.0,
CMMN 1.1, and an SBVR-aligned vocabulary profile from Agent 06's optimized
graph and Agent 10's dependency artifact:

```bash
PYTHONPATH=. .venv/bin/python cli/generate_executable_models.py \
  --graph pipeline-output/e2e-mortgage-20260827/agent_06-07-08-09-optimized/optimized_compliance_knowledge_graph.json \
  --dags pipeline-output/e2e-mortgage-20260827/agent_10-dag-generation/dependency_dags.json \
  --output-dir pipeline-output/e2e-mortgage-20260827/agent_10-dag-generation/executable-models
```

The exporter is deliberately fail-closed:

- Every graph rule receives a DMN decision retaining review, grounding, and
  source metadata. An unsupported predicate becomes a never-match `false`
  input entry; it is not silently approximated.
- BPMN is emitted only for a review-free, grounding-certified rule with
  `workflow_semantics` that directly evidences a trigger, actor role, and two
  or more ordered source steps. Dependency-DAG order is never treated as
  process order. Omitted rules and reasons are listed in the report.
- CMMN cases represent evidence-resolution and human-review routes. Purely
  mechanical repair findings do not enter the human queue. The exported report
  deliberately separates the fail-closed `review_required_rules` quality-hold
  count from `human_review_required_rules`: evidence gaps remain visible and
  prevent executable promotion, while only positive contradictions or explicit
  judgment findings enter the human queue. This avoids treating a summary such
  as `0 contradicted and 3 insufficient claims` as a contradiction. The two
  rates are emitted as `review_required_rate` and `human_review_rate`.
- `semantic_vocabulary_profile.json` preserves explicit concept kinds and
  flags unresolved typing. It is an SBVR-aligned pipeline profile, not a claim
  of full SBVR interchange conformance.

`executable_model_report.json` includes hashes of both source artifacts so a
consumer can detect stale generated models. Structural validation does not
certify source correctness or replace an independent DMN engine.
