# Policy Logic Forge

Turns compliance policy text into a typed, source-grounded knowledge graph:
every rule is extracted with structured conditions and outcomes,
independently verified against the source document, and partitioned into
dependency DAGs with a 100%-coverage guarantee. A differential-execution
engine (RegDelta) can then compare two versions of a policy and report which
rules and downstream cases actually changed.

For a detailed technical reference — per-stage responsibilities and
algorithms, module dependency graphs, configuration/prompt resolution, and
real DMN/BPMN/CMMN/SBVR examples — see [`ARCHITECTURE.md`](ARCHITECTURE.md).

## What's here

**The extraction pipeline** — twelve canonical agents, `agent_01` through
`agent_12` (document organization → entity/relationship extraction →
business-rule extraction → validation → merge → deduplication + dependency
analysis → four-invariant executable-readiness gate → focused remediation →
independent grounding certification → dependency DAG generation → DMN/BPMN/
CMMN model generation → self-contained business knowledge report). A lean CLI
orchestrator (`cli/extract.py`) runs them in order.

**RegDelta** — a rule-change/version differential-execution engine layered on
top: compile old and new versions of a policy to LExec IR, align rules,
classify semantic changes, and propagate impact through the dependency
graph. See [`plan/regdelta-product-plan.md`](plan/regdelta-product-plan.md).

**No UI.** This is a CLI-and-library tool; there is currently no web
frontend or backend service.

**Agent 12 report layer** — after Agent 11 has produced its model bundle,
`agents/agent_12_business_knowledge_report.py` creates one self-contained
`business_knowledge_report.html`. The report provides tabbed SBVR vocabulary,
rule exploration, review management, DMN/BPMN/CMMN coverage, dependency views,
embedded source chunks, search/filter controls, and inline SVG visualizations.
It uses only graph-derived facts; missing evidence remains explicitly
unresolved.

### Engineering fixes made along the way

Three pre-existing defects were found and fixed while building this out,
worth knowing about if you're comparing behavior against an earlier version:

- **P2** — the extraction prompt used to instruct the model to emit both v1
  prose (`conditions`/`consequences`) and the v2 structured contract
  (`condition_predicates`/`outcomes`/...) in the same request. Fixed at the
  source (`scripts/generate_benchmark_domain_prompts.py`) for every domain
  pack.
- **P3** — `contract_issues`/`requires_review` were stamped once at
  extraction time and never recomputed after `agent_07` normalizes legacy
  operator/value-type aliases, so a structurally clean rule could still carry
  stale "invalid operator" errors. `agent_07` now re-validates after
  normalization.
- **P6** — BPMN eligibility was first gated on a hardcoded, mortgage-shaped
  `rule_type` set and later over-corrected to `responsible_party` plus an
  output variable. Neither establishes process order. BPMN now requires a
  grounded, source-explicit trigger, actor role, direct evidence, and at
  least two ordered workflow steps. Rules without those semantics remain in
  DMN and record their BPMN omission reasons instead of becoming invented
  linear workflows.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp config.example.json config.json
cp .env.example .env   # add your OPENAI_API_KEY

# The committed template defaults to gpt-5.6-luna with high reasoning.
# If config.json already exists, update its model/effort fields or recreate it
# from config.example.json; config.json is intentionally ignored.

# Put your own source documents under compliance-files/<domain>/ — no sample
# corpora are bundled. Pick one of the supported domains (see below), e.g.:
mkdir -p compliance-files/nda_confidentiality
cp /path/to/your/*.txt compliance-files/nda_confidentiality/

python3 cli/extract.py --dir nda_confidentiality --domain nda_confidentiality --target-rules 20
```

**Supported domains**: `nda_confidentiality`, `privacy_policy`,
`mobile_app_privacy`, `commercial_contracts`, `deonticbench` (each with its
own `domain-prompts/<domain>/` pack), and `mortgage` (uses the shared
`prompts/` fallback). `--dir` accepts either an absolute path or a name under
`compliance-files/`.

**Model provider**: OpenAI by default. Pass `--provider anthropic` (or set
`KG_PROVIDER=anthropic`) to run against Claude models instead — every agent
subprocess picks it up automatically. Requires `ANTHROPIC_API_KEY` (see
`.env.example`) and the `anthropic.models.*` block in `config.json` (see
`config.example.json`; defaults to `claude-sonnet-5`). Anthropic calls are
routed through [litellm](https://docs.litellm.ai/); OpenAI calls are
unaffected — they still use the OpenAI SDK directly, exactly as before. See
`utils/llm_client.py`'s module docstring for exactly what does and doesn't
translate across providers (`reasoning_effort`, token budgets, cost/cache
tracking).

The default runtime profile is tuned for high-throughput execution: 80
scheduling workers, 32 in-flight API requests (the shared adaptive limiter
starts at 16 and ramps to 32), and 32 document workers. Stage pools can queue
up to 80 tasks while the request gate bounds provider work. Requests have a
300-second timeout, a 900-second shared lease,
a 30-second watchdog margin, and a 10-second connection backoff. Grounding uses
12 relationship packets per request to keep prompts bounded. Operators can
override these values through the `KG_*` environment variables exported by
`cli/extract.py` (for example, `KG_GROUNDING_LLM_CONCURRENCY` or
`KG_OPENAI_TIMEOUT`).

Output lands under `pipeline-output/<batch-name>/`:

- `agent_06-07-08-09-optimized/optimized_compliance_knowledge_graph.json` — the final,
  grounding-certified knowledge graph.
- `agent_06-07-08-09-optimized/kg_readiness_report.{json,md}` and
  `agent_06-07-08-09-optimized/kg_grounding_report.{json,md}` — the
  four-invariant self-report and the
  independent claim-level certification.
- `agent_10-dag-generation/dependency_dags.json` — every rule partitioned into
  one or more dependency DAGs, with an explicit, checked coverage guarantee.
- `agent_11-executable-models/` — DMN/BPMN/CMMN/SBVR review projections, plus
  a compiled, proof-checked LExec IR document for rules the compiler can
  represent (`lexec_ir.json`, `compilation_report.json`, `proof_records.json`).
- `agent_12-business-knowledge-report/business_knowledge_report.html` — the
  self-contained human-review and exploration report generated from the Agent
  11 bundle. Open it directly in a browser; no server or network access is
  required.

### Numbering contract

The pipeline has one canonical sequence of twelve stages. The stage number and
agent identifier are the same value, so `Stage 09/12` always means
`agent_09` (grounding verification). Use `--stage N` when selecting by number
or `--agent agent_NN` when selecting by identifier:

| Stage | Agent | Responsibility |
| --- | --- | --- |
| 01/12 | `agent_01` | Document organization |
| 02/12 | `agent_02` | Entity and relationship extraction |
| 03/12 | `agent_03` | Business-rule extraction |
| 04/12 | `agent_04` | Advisory rule validation |
| 05/12 | `agent_05` | Rules/entities merge |
| 06/12 | `agent_06` | Knowledge-graph optimization |
| 07/12 | `agent_07` | Executable-readiness gate |
| 08/12 | `agent_08` | Readiness remediation |
| 09/12 | `agent_09` | Independent grounding verification |
| 10/12 | `agent_10` | Dependency-DAG generation |
| 11/12 | `agent_11` | DMN/BPMN/CMMN model generation |
| 12/12 | `agent_12` | Self-contained business knowledge report |

Stages 07–09 intentionally write reports into the shared
`agent_06-07-08-09-optimized/` directory because they operate on the same optimized
graph. Their stage IDs and checkpoints remain distinct. The deprecated
`--step` option is retained only for older scripts; its fractional aliases do
not define the current pipeline numbering. Readers also accept the former
`agent_06-optimized/` name for retained historical bundles; new runs always
write the descriptive shared-directory name above.

Agent 12 is the post-pipeline presentation stage and is part of the canonical
extraction numbering contract. Generate it for an existing batch with:

```bash
KG_BATCH_NAME=my-batch KG_DOMAIN=privacy_policy \
  .venv/bin/python agents/agent_12_business_knowledge_report.py
```

Optional `--graph`, `--dags`, `--models-dir`, `--organized-dir`, and
`--output-dir` arguments allow generation from an explicitly selected bundle.

Run a single stage with `--stage 9` or a single agent with `--agent agent_09`
(for example, to re-run grounding certification), or multiple stages in one
invocation with `--stages 7-12` (also accepts a list or a mix, e.g. `3,5,7`).
`--skip-optimize` skips `agent_06`–`agent_08`; independent `agent_09`
grounding still runs before `agent_10` DAG generation. There is no separate
`--resume` flag: re-running only the remaining stage(s) against the same
`--batch-name` reuses the earlier stages' already-written output and *is*
the resume workflow — see [`docs/cli.md`](docs/cli.md#recovering-from-a-mid-run-failure-no-separate---resume-flag)
for a worked example. The deprecated numeric `--step` selector remains
accepted for backwards compatibility and prints the canonical stage it maps
to. Every run also writes a `run_metrics.json` next to its other output with
per-stage/total timing, token, cost, and cache-hit metrics — see
[`docs/cli.md`](docs/cli.md) for the full CLI reference, output modes
(`--output json` for scripting), and troubleshooting guidance.

Readiness exit code 3 is a review signal, not a subprocess crash. The full
orchestrator runs remediation, then continues to independent grounding and DAG
generation when all four readiness invariants pass; affected rules remain
`requires_review: true` in the final artifacts. Structural invariant failures
still stop the run.

## Structure

```text
cli/extract.py              `agent_01`–`agent_12` orchestrator
agents/                     one zero-padded module per extraction agent plus Agent 12 report layer
utils/                      config, LLM client, adaptive rate limiter,
                            rule contract + validator, readiness/grounding
                            helpers, dependency-DAG partitioning, the LExec
                            compiler/evaluator, and the RegDelta engine
prompts/                    shared prompts (the v2 rule contract, readiness/
                            grounding/remediation prompts) — apply to every domain
domain-prompts/<domain>/    per-domain extraction prompts, one dir per domain
                            with an override pack
scripts/generate_benchmark_domain_prompts.py
                            source of truth for the domain-prompt packs —
                            regenerate after editing a template, don't hand-edit
                            the committed .txt files
fixtures/regdelta/          hand-labeled fixtures for RegDelta's acceptance tests
tests/                      pytest suite
```

## Testing

```bash
.venv/bin/python scripts/validate_config.py
pytest
```

No API key needed — the suite tests contract validation, readiness/grounding
logic, dependency-DAG partitioning, and prompt-pack consistency against fixed
graphs and prompt files, not live extraction runs.

For a provider-backed one-document configuration smoke run, follow
[`docs/pipeline_smoke.md`](docs/pipeline_smoke.md).
