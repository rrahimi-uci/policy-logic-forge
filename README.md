# compliance-to-code

Turns compliance policy text into a typed, source-grounded, **executable**
knowledge graph: every rule is extracted with structured conditions and
outcomes, independently verified against the source document, partitioned
into dependency DAGs with a 100%-coverage guarantee, and — per the plan in
[`k-to-code.md`](k-to-code.md) — compilable into DMN 1.3 decision models and
BPMN 2.0 process models that a third-party engine can actually execute.

This is a focused research fork of the `policy-to-knowledge` monorepo's
extraction pipeline. See **Scope** below for exactly what was kept, what was
cut, and why.

## Why this exists

`policy-to-knowledge` is a product monorepo (FastAPI backend, React UI, a
graph explorer, a cross-graph comparison pipeline, 8 compliance domains). This
repo pulls out only the part relevant to a "compliance text → executable
logic" research question — the extraction/readiness/grounding/DAG pipeline —
re-scoped to the 4 domains that have a paired, cleanly-licensed public
benchmark corpus, so every claim this repo can make is checkable against a
real, citable dataset.

## Scope

**Kept**: Agents 1 through 5.7 (document organization → entity/relationship
extraction → business-rule extraction → validation → merge → deduplication +
dependency analysis → four-invariant executable-readiness gate → focused
remediation → independent grounding certification), plus Agent 6 (dependency
DAG generation, 100%-coverage guarantee). A lean CLI orchestrator
(`cli/extract.py`) runs them in order.

**Cut, deliberately**:

- **No UI, no backend.** No FastAPI, no React, no WebSocket streaming, no run
  history database. This is a CLI-and-library research repo.
- **No cross-graph comparison pipeline** (the source repo's agents 7-10: rule
  clustering, semantic matching, set operations, comparison visualization).
  Comparing two already-extracted graphs is a different task from extracting
  one.
- **No HTML visualizer** (the source repo's Agent 6). Its job — an
  interactive network graph and rules table — doesn't serve this repo's
  research question; the actual deliverable here is the DMN/BPMN compiler
  described in `k-to-code.md`, not a picture of the graph.
- **Only 4 of the source repo's 8 compliance domains**: `nda_confidentiality`,
  `privacy_policy`, `mobile_app_privacy`, `commercial_contracts`. The other
  four (`mortgage`, `healthcare`, `aml`, `commercial_lending`) have no paired
  public benchmark corpus and use proprietary/product source text whose
  redistribution terms were never checked — inappropriate for a repo meant to
  produce checkable, citable results.

**Fixed during the fork** (all three are pre-existing defects identified while
studying feasibility — see `k-to-code.md`'s "Blockers and preconditions" P2,
P3, P6 — that would otherwise have been silently inherited):

- **P2** — the extraction prompt used to instruct the model to emit both v1
  prose (`conditions`/`consequences`) and the v2 structured contract
  (`condition_predicates`/`outcomes`/...) in the same request. Fixed at the
  source (`scripts/generate_benchmark_domain_prompts.py`) for all 4 domains.
- **P3** — `contract_issues`/`requires_review` were stamped once at
  extraction time and never recomputed after Agent 5.5 normalizes legacy
  operator/value-type aliases, so a structurally clean rule could still carry
  stale "invalid operator" errors. Agent 5.5 now re-validates after
  normalization.
- **P6** — BPMN eligibility was gated on a hardcoded, mortgage-shaped
  `rule_type` set (`process`/`validation`/`compliance`/`exception`). None of
  this repo's 4 domains use that vocabulary (see each domain's
  `business_rules_extraction_compact.txt`), so every rule would have silently
  gotten zero BPMN targets. Now gated on a domain-agnostic signal
  (`responsible_party` set + at least one output variable).

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp config.example.json config.json
cp .env.example .env   # add your OPENAI_API_KEY

# Try it on the committed NDA pilot (3 real NDAs, CC BY 4.0 via ContractNLI):
python3 cli/extract.py --dir nda_confidentiality_pilot --domain nda_confidentiality --target-rules 20

# Or the CUAD commercial-contracts pilot (CC BY 4.0):
python3 cli/extract.py --dir commercial_contracts_pilot --domain commercial_contracts --target-rules 20
```

Output lands under `pipeline-output/<batch-name>/`:

- `agent-5-optimized/optimized_compliance_knowledge_graph.json` — the final,
  grounding-certified knowledge graph.
- `agent-5-optimized/kg_readiness_report.{json,md}` and
  `kg_grounding_report.{json,md}` — the four-invariant self-report and the
  independent claim-level certification.
- `agent-6-dag-generation/dependency_dags.json` — every rule partitioned into
  one or more dependency DAGs, with an explicit, checked coverage guarantee.

Run a single stage with `--step` (e.g. `--step 5.7` to re-run only grounding
certification), or `--skip-optimize` to skip deduplication/readiness/grounding
entirely and go straight from the merged graph to DAG generation.

## Data and licensing

Benchmark corpora are downloaded, not vendored (`benchmarks/README.md` has
the full reproduction story — checksummed URLs in `benchmarks/datasets.json`):

```bash
cd benchmarks
python3 scripts/download_benchmarks.py           # all 4, ~640 MB
python3 scripts/build_source_docs.py             # normalize into flat .txt per corpus
```

| Domain | Corpus | License | Committed pilot sample? |
| --- | --- | --- | --- |
| `nda_confidentiality` | ContractNLI (607 NDAs) | CC BY 4.0 | Yes — `compliance-files/nda_confidentiality_pilot/` |
| `commercial_contracts` | CUAD (510 contracts) | CC BY 4.0 | Yes — `compliance-files/commercial_contracts_pilot/` |
| `privacy_policy` | OPP-115 (115 policies) | Free for research use; no redistribution grant | **No** — build locally after downloading |
| `mobile_app_privacy` | MAPP | Free for research use; no redistribution grant | **No** — build locally after downloading |

CC BY 4.0 explicitly permits redistribution with attribution, so this repo
commits a small (2-3 document) pilot sample for those two domains directly
under `compliance-files/`, letting you run the quickstart above with zero
setup. OPP-115 and MAPP's license permits research use but does not grant a
redistribution right, so no sample from either is committed — run
`benchmarks/scripts/build_source_docs.py` after downloading, then point
`--dir` at a folder you create under `compliance-files/` yourself.

## Structure

```
cli/extract.py              10-stage orchestrator (1, 2, 3, 3.5, 4, 5, 5.5, 5.6, 5.7, 6)
agents/                     one module per stage
utils/                      config, LLM client, adaptive rate limiter,
                            rule contract + validator, readiness/grounding
                            helpers, dependency-DAG partitioning
prompts/                    shared prompts (the v2 rule contract, readiness/
                            grounding/remediation prompts) — apply to every domain
domain-prompts/<domain>/    per-domain extraction prompts, one dir per kept domain
scripts/generate_benchmark_domain_prompts.py
                            source of truth for the 4 domain-prompt packs —
                            regenerate after editing a template, don't hand-edit
                            the committed .txt files
benchmarks/                 dataset registry + download/build scripts
compiler/                   scaffold for the k-to-code.md DMN/BPMN compiler
                            (not implemented yet — read the plan first)
k-to-code.md                feasibility study + phased plan for compiling the
                            graph into executable DMN/BPMN
tests/                      pytest suite (766 tests as of this writing)
```

## Testing

```bash
pytest
```

No API key needed — the suite tests contract validation, readiness/grounding
logic, dependency-DAG partitioning, and prompt-pack consistency against fixed
graphs and prompt files, not live extraction runs.

## Roadmap

Read [`k-to-code.md`](k-to-code.md) before writing any code in `compiler/`. It
measures DMN feasibility against a real certified graph (352/352 rules emit
well-formed DMN; 0 wrong-value test-vector replays) and BPMN's materially
weaker story, names the open design questions (exception-list semantics,
which corpora to run under v2 first, single-vs-consolidated decision tables),
and is explicit about what's measured evidence versus code-reading versus
still genuinely unverified.
