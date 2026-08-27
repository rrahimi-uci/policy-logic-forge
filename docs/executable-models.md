# Mortgage DMN/BPMN export

`cli/generate_executable_models.py` creates review-aware DMN 1.3 and BPMN 2.0
artifacts from Agent 06's optimized graph and Agent 10's dependency DAGs:

```bash
PYTHONPATH=. .venv/bin/python cli/generate_executable_models.py \
  --graph pipeline-output/e2e-mortgage-20260827/agent_06-optimized/optimized_compliance_knowledge_graph.json \
  --dags pipeline-output/e2e-mortgage-20260827/agent_10-dag-generation/dependency_dags.json \
  --output-dir pipeline-output/e2e-mortgage-20260827/agent_10-dag-generation/executable-models
```

The exporter is deliberately fail-closed. Every graph rule receives a DMN
decision and every DAG rule receives a BPMN `businessRuleTask`, but each model
retains `ctc:requiresReview`, `ctc:groundingStatus`, and `ctc:sourceRef`. An
unsupported predicate becomes a never-match `false` input entry; it is not
silently approximated. The generated report is structural validation only and
does not certify source correctness or replace an independent DMN engine.
