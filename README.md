# compliance-to-code

Turns compliance policy text into a typed, source-grounded knowledge graph:
every rule is extracted with structured conditions and outcomes,
independently verified against the source document, and partitioned into
dependency DAGs with a 100%-coverage guarantee.

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
  research question, which stops at a grounding-certified,
  dependency-partitioned knowledge graph, not a picture of it.
- **Only 4 of the source repo's 8 compliance domains**: `nda_confidentiality`,
  `privacy_policy`, `mobile_app_privacy`, `commercial_contracts`. The other
  four (`mortgage`, `healthcare`, `aml`, `commercial_lending`) have no paired
  public benchmark corpus and use proprietary/product source text whose
  redistribution terms were never checked — inappropriate for a repo meant to
  produce checkable, citable results.

**Fixed during the fork** (all three are pre-existing defects found while
auditing the extraction/readiness pipeline, that would otherwise have been
silently inherited):

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

# The committed template defaults to gpt-5.6-luna with high reasoning.
# If config.json already exists, update its model/effort fields or recreate it
# from config.example.json; config.json is intentionally ignored.

# No sample documents are committed (see "Data and licensing" below) — build
# one corpus first, e.g. ContractNLI's NDAs:
cd benchmarks
python3 scripts/download_benchmarks.py contract-nli
python3 scripts/build_source_docs.py contract-nli
cd ..
mkdir -p compliance-files/nda_confidentiality
cp benchmarks/contract-nli-source-docs/*.txt compliance-files/nda_confidentiality/

python3 cli/extract.py --dir nda_confidentiality --domain nda_confidentiality --target-rules 20
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

| Domain | Corpus | License | Local folder (after building) |
| --- | --- | --- | --- |
| `nda_confidentiality` | ContractNLI (607 NDAs) | CC BY 4.0 | `compliance-files/nda_confidentiality/` |
| `commercial_contracts` | CUAD (510 contracts) | CC BY 4.0 | `compliance-files/commercial_contracts/` |
| `privacy_policy` | OPP-115 (115 policies) | Free for research use; no redistribution grant | `compliance-files/privacy_policy/` |
| `mobile_app_privacy` | MAPP | Free for research use; no redistribution grant | `compliance-files/mobile_app_privacy/` |

None of the four are committed to this repo, regardless of license — build
whichever domain you need (`benchmarks/scripts/download_benchmarks.py` then
`build_source_docs.py`, see `benchmarks/README.md`), then copy that
corpus's `benchmarks/<id>-source-docs/*.txt` into
`compliance-files/<domain>/` as shown in the Quickstart above. `--dir`
then points at whichever domain folder you built.

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
tests/                      pytest suite
```

## Testing

```bash
.venv/bin/python scripts/validate_config.py
.venv/bin/python scripts/validate_neurips_plan.py --check
pytest
```

No API key needed — the suite tests contract validation, readiness/grounding
logic, dependency-DAG partitioning, and prompt-pack consistency against fixed
graphs and prompt files, not live extraction runs.

For a provider-backed one-document configuration smoke run, follow
[`docs/pipeline_smoke.md`](docs/pipeline_smoke.md). It is explicitly a pilot,
not corpus coverage or a benchmark result.
