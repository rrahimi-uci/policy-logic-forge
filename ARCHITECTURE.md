# Architecture

This document describes how Policy Logic Forge is put together: the
eleven-agent extraction pipeline, the shared services and compiler layer
underneath it, the RegDelta differential-execution engine layered on top,
and how configuration and prompts flow through all of it. For setup and CLI
usage, see [`README.md`](README.md).

## 1. System overview

Policy Logic Forge turns compliance policy text into a typed,
source-grounded knowledge graph, then optionally compares two versions of
that graph to report what actually changed. There are three moving parts:

- **The extraction pipeline** (`agents/`, orchestrated by `cli/extract.py`)
  — eleven agents run in a fixed sequence, each consuming the previous
  stage's output and writing its own artifacts under
  `pipeline-output/<batch>/`.
- **Shared services and the compiler layer** (`utils/`) — configuration,
  the LLM client, prompt resolution, and (for rules the compiler can
  represent) a fail-closed lowering to an intermediate representation with
  bounded proof search.
- **RegDelta** (`utils/regdelta_engine.py` and friends) — a
  differential-execution engine that compiles two graphs, aligns their
  rules, classifies what changed, and propagates impact through the
  dependency graph.

```mermaid
flowchart LR
    classDef input fill:#e0f2fe,stroke:#0369a1,color:#0c4a6e,stroke-width:1px
    classDef orchestration fill:#ede9fe,stroke:#6d28d9,color:#4c1d95,stroke-width:1px
    classDef agent fill:#fae8ff,stroke:#a21caf,color:#701a75,stroke-width:1px
    classDef shared fill:#dcfce7,stroke:#15803d,color:#14532d,stroke-width:1px
    classDef compiler fill:#fef3c7,stroke:#b45309,color:#78350f,stroke-width:1px
    classDef regdelta fill:#ffe4e6,stroke:#be123c,color:#881337,stroke-width:1px
    classDef output fill:#e2e8f0,stroke:#334155,color:#1e293b,stroke-width:1px

    DOCS[("Source docs<br/>compliance-files/")]
    CFG[("config.json + .env")]

    subgraph ORCH["Orchestration — cli/extract.py"]
        EXTRACT["ExtractionPipeline"]
    end

    subgraph PIPELINE["11-Agent Pipeline (agents/)"]
        direction LR
        A1["01<br/>Organize"] --> A2["02<br/>Entities"] --> A3["03<br/>Rules"]
        A3 --> A4["04<br/>Validate"] --> A5["05<br/>Merge"] --> A6["06<br/>Optimize"]
        A6 --> A7["07<br/>Readiness"]
        A7 -.->|"review"| A8["08<br/>Remediate"]
        A8 -.->|"re-check"| A7
        A7 --> A9["09<br/>Ground"] --> A10["10<br/>DAG"] --> A11["11<br/>Models"]
    end

    subgraph OUTPUTS["Outputs (pipeline-output/&lt;batch&gt;/)"]
        GRAPH["optimized graph"]
        DAGS["dependency DAGs"]
        MODELS["DMN·BPMN·CMMN·SBVR"]
    end

    DOCS --> EXTRACT
    CFG --> EXTRACT
    EXTRACT ==> A1
    A6 -.-> GRAPH
    A10 -.-> DAGS
    A11 -.-> MODELS

    subgraph SUPPORT["Support layers, used throughout the pipeline"]
        direction TB
        SHARED["Shared services<br/>utils/config · llm_client<br/>adaptive_limiter · prompt_manager"]
        PROMPTS["Prompts<br/>domain-prompts/&lt;domain&gt; + prompts/"]
        COMPILER["Compiler + proof layer<br/>lexec_ir · lexec_compile · smt · feel<br/>executable_models · semantic_artifacts"]
    end

    PIPELINE -.->|"config, LLM calls,<br/>rate limiting"| SHARED
    SHARED -.-> PROMPTS
    A11 -.->|"compiles + proves"| COMPILER

    subgraph REGDELTA["RegDelta engine"]
        direction LR
        RE["regdelta_engine.py<br/>align → classify<br/>→ propagate"]
    end

    GRAPH ==>|"old vs new run"| REGDELTA
    COMPILER -.->|"lower_graph / evaluate_formula"| REGDELTA

    class DOCS,CFG input
    class EXTRACT orchestration
    class A1,A2,A3,A4,A5,A6,A7,A8,A9,A10,A11 agent
    class SHARED,PROMPTS shared
    class COMPILER compiler
    class RE regdelta
    class GRAPH,DAGS,MODELS output
```

Two things worth noticing immediately:

1. **The compiler layer is additive, not required.** Agents 01–10 and most
   of agent_11 (the review-projection DMN/BPMN/CMMN/SBVR) never touch
   `lexec_ir.py`/`lexec_compile.py`/`smt.py`. Only the proof-checked side
   output (`lexec_ir.json`, `compilation_report.json`, `proof_records.json`)
   goes through the compiler, and a failure there never blocks or replaces
   the review-projection output.
2. **RegDelta consumes the pipeline's output, it doesn't run inside it.**
   It reads two already-completed runs' optimized graphs; nothing in
   `agents/` or `cli/extract.py` imports from `utils/regdelta_engine.py` or
   its dependencies.

## 2. The eleven-agent pipeline

### 2.1 Stage responsibilities

| Stage | Agent | Responsibility | Primary output |
| --- | --- | --- | --- |
| 01/11 | `agent_01` | Document organization | `agent_01-organized-documents/` |
| 02/11 | `agent_02` | Entity and relationship extraction | `agent_02-entities/` |
| 03/11 | `agent_03` | Business-rule extraction | `agent_03-rules/` |
| 04/11 | `agent_04` | Advisory rule validation | `agent_04-validation/` |
| 05/11 | `agent_05` | Rules/entities merge | `agent_05-rules-with-entities/` |
| 06/11 | `agent_06` | Knowledge-graph optimization (dedup + dependency analysis) | `agent_06-07-08-09-optimized/optimized_compliance_knowledge_graph.json` |
| 07/11 | `agent_07` | Executable-readiness gate (four invariants) | readiness report, embedded in the shared optimized directory |
| 08/11 | `agent_08` | Readiness remediation (only if agent_07 requests it) | focused rule fix-ups |
| 09/11 | `agent_09` | Independent grounding verification | claim-level certification |
| 10/11 | `agent_10` | Dependency-DAG generation, 100%-coverage guarantee | `agent_10-dag-generation/dependency_dags.json` |
| 11/11 | `agent_11` | DMN/BPMN/CMMN/SBVR generation + LExec compile | `agent_11-executable-models/` |

Stages 07–09 share one directory (`agent_06-07-08-09-optimized/`) because
they all read and write the same optimized graph; their stage IDs and
checkpoints stay distinct. The stage number and agent identifier are always
the same value — `--stage 9` and `--agent agent_09` select the same stage.

### 2.2 Execution flow, including the readiness/remediation loop

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant CLI as cli/extract.py
    participant A as agents 01–06
    participant A7 as agent_07<br/>Readiness
    participant A8 as agent_08<br/>Remediator
    participant A9 as agent_09<br/>Grounding
    participant A10 as agent_10/11<br/>DAG + Models
    participant FS as pipeline output

    Op->>CLI: extract.py --dir --domain --resume
    CLI->>FS: read pipeline_run_state.json
    alt resume requested
        FS-->>CLI: last completed stage
    end
    CLI->>A: run_agent_01 … run_agent_06
    A->>FS: write per-stage artifacts + checkpoints
    CLI->>FS: record_stage_result() after each stage

    CLI->>A7: run_agent_07()
    A7->>FS: read optimized graph
    A7-->>CLI: exit 0 (ready) or exit 3 (review signal)

    alt rules need remediation
        CLI->>A8: run_agent_08()
        A8->>FS: focused rule fix-ups
        CLI->>A7: run_agent_07(reuse_conflicts=true)
        A7-->>CLI: re-verified readiness
    end

    CLI->>A9: run_agent_09() — independent grounding
    A9-->>CLI: claim-level certification

    CLI->>A10: run_agent_10() DAG, run_agent_11() models
    A10->>FS: dependency_dags.json + DMN/BPMN/CMMN/SBVR + lexec_ir.json

    CLI-->>Op: COMPLETE — optimized graph, DAGs, executable models
```

**Readiness exit code 3 is a review signal, not a crash.** The full
orchestrator runs remediation, then continues to independent grounding and
DAG generation once all four readiness invariants pass; affected rules
remain `requires_review: true` in the final artifacts rather than blocking
the run. A structural invariant failure (not remediable) still stops it.

### 2.3 Resume and checkpointing

Two independent mechanisms cooperate:

- **Stage-level resume.** After every stage, `ExtractionPipeline` writes
  `pipeline_run_state.json` at the batch root recording which of the nine
  resumable units (agents 01–06 individually, the 07→08→09 loop as one
  unit, then 10 and 11) completed successfully. `--resume` reads this file
  and restarts at the first incomplete unit; `--resume-from <stage>`
  overrides that explicitly. The 07→08→09 loop is always resumed from its
  start, never mid-loop.
- **Item-level resume, inside a single stage.** Agents 01, 03, 07, 08, and
  09 each maintain their own append-only JSONL checkpoint
  (`agent_07_rule_checkpoint.jsonl` and similar) keyed by a content
  fingerprint, so an interrupted stage skips already-processed items on its
  next invocation instead of redoing them — independent of whether the
  outer orchestrator is resuming or running that stage fresh.

A shared adaptive concurrency limiter (`utils/adaptive_limiter.py`) governs
API request pacing across every agent subprocess in a run, backed by a
SQLite file so concurrently running batches share one budget.

## 3. Module architecture (`utils/`)

Most of `utils/` is used directly by one or more agents with no interesting
inter-module structure. The part worth diagramming is the compiler layer,
because it is a genuine hub: `lexec_ir.py` is imported both by agent_11's
proof-checked compile path and by every RegDelta module that needs to read
or evaluate that IR.

```mermaid
flowchart TB
    classDef pipeline fill:#fae8ff,stroke:#a21caf,color:#701a75,stroke-width:1px
    classDef core fill:#dcfce7,stroke:#15803d,color:#14532d,stroke-width:1px
    classDef hub fill:#fef3c7,stroke:#b45309,color:#78350f,stroke-width:2px
    classDef regdelta fill:#ffe4e6,stroke:#be123c,color:#881337,stroke-width:1px

    A11["agent_11_executable_model_generator.py"]:::pipeline

    EM["executable_models.py<br/>(real DMN + BPMN emitter)"]:::core
    SA["semantic_artifacts.py<br/>(real CMMN + SBVR emitter)"]:::core
    LC["lexec_compile.py"]:::core
    IR["lexec_ir.py"]:::hub
    SMT["smt.py<br/>(bounded proof search)"]:::core

    OTHER["14 other utils/ modules<br/>config · llm_client · adaptive_limiter · agent_names<br/>prompt_manager · rule_contract · rule_uniqueness · dag_builder<br/>readiness · kg_readiness · citations · semantic_routing …<br/><i>used directly by agents/, no internal utils/ dependencies</i>"]:::core

    A11 --> EM
    A11 --> SA
    A11 -->|"proof-checked path"| LC
    LC --> IR
    LC --> SMT

    subgraph RD["RegDelta-only — layered on utils/regdelta_engine.py"]
        RE["regdelta_engine.py"]:::regdelta
        RA["rule_alignment.py"]:::regdelta
        SD["semantic_diff.py"]:::regdelta
        IP["impact_propagation.py"]:::regdelta
        FEEL["feel.py<br/>(bounded evaluator)"]:::regdelta
    end

    RE --> RA
    RE --> SD
    RE --> IP
    RE --> FEEL
    RE -->|"lower_graph"| IR
    FEEL -->|"validate_ir"| IR
```

Note the two independent DMN/BPMN emitters, which is easy to conflate:

- `utils/executable_models.py` + `utils/semantic_artifacts.py` produce the
  **real** `compliance_decisions.dmn`, `compliance_workflows.bpmn`,
  `compliance_reviews.cmmn`, and `semantic_vocabulary_profile.json` in
  every run. This path never touches the compiler.
- `lexec_compile.py` → `lexec_ir.py`/`smt.py` produce a **separate**,
  proof-checked `lexec_ir.json` for the subset of rules the compiler can
  represent (no unsupported `scope.predicate`, no unproved hit-policy
  table). It is additive and best-effort: a compiler failure never blocks
  or replaces the review-projection output above.

## 4. Configuration and prompt resolution

```mermaid
flowchart TB
    classDef file fill:#e0f2fe,stroke:#0369a1,color:#0c4a6e
    classDef code fill:#dcfce7,stroke:#15803d,color:#14532d
    classDef decision fill:#fef3c7,stroke:#b45309,color:#78350f

    CFGJSON[("config.json<br/>(gitignored, local)")]:::file
    CFGEX[("config.example.json<br/>(committed template)")]:::file
    ENVF[(".env<br/>OPENAI_API_KEY")]:::file

    CONFIGPY["utils/config.py<br/>Config singleton"]:::code
    CFGJSON --> CONFIGPY
    CFGEX -.->|"fallback if missing"| CONFIGPY
    ENVF --> CONFIGPY

    DOMAIN{{"--domain flag<br/>sets active domain"}}:::decision
    CONFIGPY --> DOMAIN

    PM["utils/prompt_manager.py<br/>PromptManager.load_prompt(name)"]:::code
    DOMAIN --> PM

    CHECK{{"domain-prompts/&lt;domain&gt;/&lt;name&gt;.txt<br/>exists?"}}:::decision
    PM --> CHECK
    DOMPACK[("domain-prompts/&lt;domain&gt;/<br/>per-domain override pack")]:::file
    SHAREDP[("prompts/<br/>shared fallback templates")]:::file
    CHECK -->|"yes"| DOMPACK
    CHECK -->|"no"| SHAREDP

    AGENT["calling agent<br/>(e.g. agent_03, agent_07)"]:::code
    DOMPACK --> AGENT
    SHAREDP --> AGENT
```

`config.json` is gitignored and local-only; `config.example.json` is the
committed, portable source of truth checked by `scripts/validate_config.py`.
`Config` is a process-level singleton (`utils/config.py`), mutated in place
by `set_batch_name`/`domain` — a real constraint for anything that might
want to launch concurrent batches from the same Python process: each batch
must be its own OS process, never an in-process call into
`ExtractionPipeline`. Six domains are registered in
`config.example.json`'s `domain.available` list; five have a dedicated
`domain-prompts/<domain>/` override pack, and `mortgage` falls back entirely
to the shared `prompts/` templates. `scripts/generate_benchmark_domain_prompts.py`
is the source of truth for the generated `.txt` packs — regenerate from it
rather than hand-editing the committed files.

## 5. RegDelta: differential-execution engine

Given two already-completed runs (an "old" and a "new" optimized graph),
RegDelta answers *what changed, for whom, and what else does it affect* —
without re-running the extraction pipeline.

```mermaid
flowchart LR
    classDef input fill:#e0f2fe,stroke:#0369a1,color:#0c4a6e
    classDef step fill:#ffe4e6,stroke:#be123c,color:#881337
    classDef output fill:#e2e8f0,stroke:#334155,color:#1e293b

    OLD[("old run<br/>optimized graph")]:::input
    NEW[("new run<br/>optimized graph")]:::input

    COMPILE["Compile both to<br/>LExec IR"]:::step
    ALIGN["Align rules<br/>rule_alignment.py<br/>(exact-ID today)"]:::step
    CLASSIFY["Classify each pair<br/>semantic_diff.py<br/>added · removed · changed · unchanged"]:::step
    PROPAGATE["Propagate impact<br/>impact_propagation.py<br/>Direct → Potential → Recompute"]:::step
    REPLAY["Replay scenarios<br/>feel.py evaluate_formula<br/>old vs new outcome"]:::step

    REPORT["regdelta-impact/1.0<br/>rule_alignments · semantic_changes ·<br/>affected_cases · witnesses ·<br/>downstream_impacts · refusals"]:::output

    OLD --> COMPILE
    NEW --> COMPILE
    COMPILE --> ALIGN --> CLASSIFY --> PROPAGATE --> REPLAY --> REPORT
```

Key design choices, since they're easy to get wrong by assumption:

- **Alignment is exact-ID only, today.** `rule_alignment.py` implements
  only the first stage of a five-stage alignment ladder (exact ID →
  source-section signature → predicate structure → semantic similarity →
  explicit review). It is sufficient when both runs share an ID namespace
  (a hand-edited fork of one graph); two independently re-extracted runs of
  the same document will not align well yet.
- **`Potential` is narrative reachability, not proven dependency.** It
  walks `agent_10`'s dependency-DAG edges, which are extraction judgment
  calls about *narrative* dependency between rules, not a shared data-flow
  symbol. `Recompute` is `Potential` minus anything still
  `requires_review`, so a rule that can't be safely re-evaluated is held
  for review rather than silently resolved.
- **RegDelta deliberately does not use `utils/feel.py`'s `evaluate_ir`.**
  That entry point forces `unknown` whenever a rule's scope carries
  jurisdiction/party/effective-date metadata (a tested safety property —
  the evaluator has no real-world runtime context). RegDelta instead calls
  the same module's side-effect-free `evaluate_formula` directly, because
  it's asking "does this rule's own logic differ between two snapshots,"
  not "is this rule in force for a real transaction."
- **Four-way status vocabulary, nothing silently dropped.** Every rule in
  scope resolves to exactly one of `changed`, `unchanged`,
  `unresolved-review`, or `refused-unsupported-construct` — refused and
  review-held rules stay in the denominator of every reported metric.

See [`plan/regdelta-product-plan.md`](plan/regdelta-product-plan.md) for the
full rollout plan and acceptance criteria.

## 6. Directory reference

```text
cli/                         orchestrators
  extract.py                   agent_01–agent_11 pipeline runner
  generate_executable_models.py  regenerate DMN/BPMN from an existing graph + DAGs
agents/                      one zero-padded module per pipeline agent
utils/                       shared services, compiler/proof layer, RegDelta engine
compliance-files/<domain>/   source documents (gitignored, local)
domain-prompts/<domain>/     per-domain extraction prompt overrides
prompts/                     shared prompts (v2 rule contract, readiness/grounding/remediation)
scripts/                     fixture builders, config/prompt-pack validators
fixtures/regdelta/           hand-labeled fixtures for RegDelta's acceptance tests
results/aggregates/          retained run-evidence manifests (metadata only)
docs/                        compiler/semantics notes + retained validation records
plan/                        RegDelta product plan + LExec IR schema
pipeline-output/<batch>/     run output (gitignored, regenerable)
tests/                       pytest suite
```

### `pipeline-output/<batch>/` layout

Mirrors the stage table in §2.1 exactly:

```text
pipeline-output/<batch>/
├── pipeline_run_state.json                    resume checkpoint
├── agent_01-organized-documents/
├── agent_02-entities/
├── agent_03-rules/
├── agent_04-validation/
├── agent_05-rules-with-entities/
├── agent_06-07-08-09-optimized/
│   ├── optimized_compliance_knowledge_graph.json
│   ├── kg_readiness_report.{json,md}
│   ├── kg_grounding_report.{json,md}
│   └── agent_0{7,8,9}_*_checkpoint.jsonl
├── agent_10-dag-generation/
│   └── dependency_dags.json
└── agent_11-executable-models/
    ├── compliance_decisions.dmn
    ├── compliance_workflows.bpmn
    ├── compliance_reviews.cmmn
    ├── semantic_vocabulary_profile.json
    └── lexec_ir.json, compilation_report.json, proof_records.json
```

## 7. Testing

No API key is required to run the suite — it tests contract validation,
readiness/grounding logic, dependency-DAG partitioning, prompt-pack
consistency, the LExec compiler/evaluator/proof search, and RegDelta's
alignment/diff/propagation engine against fixed graphs and prompt files, not
live extraction runs.

- **Unit/contract tests** (`tests/test_agent_*`, `test_lexec_*`,
  `test_smt_*`, `test_feel*`, `test_readiness*`) — one file per
  agent/module, run against synthetic fixtures.
- **RegDelta acceptance tests** (`test_regdelta_engine.py`,
  `test_mortgage_tier1_fixture.py`, `test_regdelta_tier1_fixtures.py`,
  `test_mortgage_tier2_extraction.py`) — assert 100% agreement with
  hand-labeled outcomes over `fixtures/regdelta/`, including that
  incremental recomputation exactly matches full replay.
- **Retained-run regression tests** (`test_pipeline_smoke_manifest.py`,
  `test_full_smallest_run_manifest.py`) — pin configuration, stage status,
  and content hashes from real provider-backed runs, retained under
  `results/aggregates/`.

```bash
.venv/bin/python scripts/validate_config.py
pytest
```
