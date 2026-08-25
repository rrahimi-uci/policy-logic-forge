# Benchmarks

Legal- and privacy-domain NLP corpora used to evaluate the compliance-to-code
extraction pipeline: clause extraction, data-practice classification, and
document-level inference against expert gold annotations.

Nothing here is committed except the manifest, the two scripts, and this file —
`data/`, `raw/`, and `*-source-docs/` are git-ignored (~637 MB in total, and two
of the four corpora are redistribution-restricted). [`datasets.json`](datasets.json)
is the source of truth: it pins every upstream URL, SHA-256, license, and the
verified contents, so a fresh clone reproduces byte-identical corpora.

## Fetch the datasets

```bash
cd apps/benchmarks
python3 scripts/download_benchmarks.py            # all four
python3 scripts/download_benchmarks.py cuad mapp  # a subset
python3 scripts/download_benchmarks.py --verify   # status + checksums, no download
python3 scripts/download_benchmarks.py --force    # re-download existing archives
```

Archives land in `raw/`, extracted trees in `data/<id>/`. Only `curl` and the
Python standard library are required.

## Build the pipeline-ready source docs

Each corpus ships its documents in a different shape — plaintext, `|||`-segmented
HTML, or embedded in the annotation JSON. `build_source_docs.py` normalizes all
four into flat folders of `.txt`, one per benchmark, ready to feed the extraction
pipeline:

```bash
python3 scripts/build_source_docs.py                 # all four
python3 scripts/build_source_docs.py cuad --limit 20 # cheap pilot subset
```

| Folder | Documents | Size | Derived from |
|---|---|---|---|
| `cuad-source-docs/` | 510 | 27 MB | `full_contract_txt/` — copied verbatim |
| `opp-115-source-docs/` | 115 | 1.9 MB | `sanitized_policies/` — `\|\|\|` segments unwrapped to text blocks |
| `contract-nli-source-docs/` | 607 | 7.9 MB | `text` field of `train`/`dev`/`test.json` |
| `mapp-source-docs/` | 155 | 5.8 MB | EN + DE sanitized policies, `en_`/`de_` prefixed |

In every case the emitted text is **the same text the gold annotations index
into**, so extracted rules stay alignable with the gold labels:

- CUAD documents are byte-identical to the corpus originals (510/510 verified).
- ContractNLI text matches the gold `text` exactly with all spans in range (607/607).
- OPP-115 segment counts match the max segment ID in each policy's annotation CSV (115/115).
- MAPP documents each resolve to their consolidation annotation file (155/155).

Each folder also carries a `_manifest.json` mapping every emitted filename back to
its annotation key and gold-annotation path. The pipeline ignores it — it only
globs `.pdf`/`.txt`/`.md`/`.docx`. Stems are sanitized and capped at 120 characters
so the pipeline's output directories stay under the filesystem limit; two truncated
CUAD names collide and get a `__2` suffix, with the full original name preserved in
the manifest.

## Run the pipeline per benchmark

`cli/extract.py --dir` reads a subdirectory of `compliance-files/` (repo
root). Point it at each `*-source-docs/` folder this script just built, or —
more likely — copy a subset into a `compliance-files/<name>/` folder of your
own first (see "Cost" below):

```bash
cd ..   # repo root
mkdir -p compliance-files/cuad_full compliance-files/contract_nli_full \
         compliance-files/opp_115_full compliance-files/mapp_full
cp benchmarks/cuad-source-docs/*.txt         compliance-files/cuad_full/
cp benchmarks/contract-nli-source-docs/*.txt compliance-files/contract_nli_full/
cp benchmarks/opp-115-source-docs/*.txt      compliance-files/opp_115_full/
cp benchmarks/mapp-source-docs/*.txt         compliance-files/mapp_full/

python3 cli/extract.py --dir cuad_full         --domain commercial_contracts
python3 cli/extract.py --dir contract_nli_full --domain nda_confidentiality
python3 cli/extract.py --dir opp_115_full      --domain privacy_policy
python3 cli/extract.py --dir mapp_full         --domain mobile_app_privacy
```

| Benchmark | Domain pack | Rule-type vocabulary aligned to |
|---|---|---|
| CUAD | `commercial_contracts` | the 41 clause categories — obligation, restriction, license_grant, ip_assignment, liability, … |
| ContractNLI | `nda_confidentiality` | the 17 NDA propositions — confidentiality_scope, permitted_use, permitted_disclosure, return_destruction, survival, … |
| OPP-115 | `privacy_policy` | the 10 data-practice categories — collection, sharing, user_choice, access_rights, retention, … |
| MAPP | `mobile_app_privacy` | the practice attributes including the GDPR **legal_basis** axis; reads German source text and normalises rules to English |

`cli/extract.py` runs a single batch/domain per invocation — there is no
`--batch`/`--source` sweep mode in this repo (see `../README.md` "Scope": the
orchestrator is deliberately lean). Each command above is one full corpus as
one batch; `--target-rules` bounds how many rules agent_03 tries to extract,
not how many documents get read.

> **Cost.** These corpora total 1,387 documents through a 7-8-stage LLM
> pipeline. Start with a handful of files copied into your own
> `compliance-files/<name>/` folder before committing to a full-corpus run.

## The corpora

| id | Dataset | Task | Extracted | License |
|----|---------|------|-----------|---------|
| `cuad` | CUAD v1 (Atticus Project) | Clause extraction / span QA | 174 MB | CC BY 4.0 |
| `opp-115` | OPP-115 (Usable Privacy) | Data-practice classification | 339 MB | Research use, cite |
| `contract-nli` | ContractNLI (Stanford NLP) | Document-level NLI + evidence | 84 MB | CC BY 4.0 |
| `mapp` | MAPP Corpus (Usable Privacy) | Bilingual EN/DE practice annotation | 8 MB | Research use, cite |

### CUAD v1 — `data/cuad/CUAD_v1/`

510 commercial contracts with 13,000+ expert labels across 41 clause categories
(governing law, change of control, exclusivity, IP ownership, …).

- `CUAD_v1.json` — SQuAD 2.0 format, 510 documents / 20,910 QA pairs
- `master_clauses.csv` — 83 columns × 510 rows, clause text plus normalized answers
- `full_contract_pdf/` — 510 source PDFs, grouped `Part_I`–`Part_III` by contract type
- `full_contract_txt/` — the same 510 contracts as plaintext
- `label_group_xlsx/` — 28 per-category label reports

> Hendrycks, Burns, Chen & Ball (2021). *CUAD: An Expert-Annotated NLP Dataset for
> Legal Contract Review.* NeurIPS Datasets & Benchmarks. DOI 10.5281/zenodo.4595826

### OPP-115 — `data/opp-115/OPP-115/`

115 website privacy policies, ~23,000 data practices annotated by legal experts
across 10 categories.

- `annotations/` — 115 per-policy annotation CSVs
- `sanitized_policies/` — 115 segmented HTML policies (the annotation targets)
- `original_policies/` — 228 as-crawled captures
- `consolidation/` — majority-vote gold at 0.5 / 0.75 / 1.0 overlap thresholds
- `pretty_print/`, `pretty_print_uniquified/` — human-readable renderings
- `documentation/` — annotation scheme and manual

> Wilson et al. (2016). *The Creation and Analysis of a Website Privacy Policy
> Corpus.* ACL 2016.

### ContractNLI — `data/contract-nli/contract-nli/`

607 NDAs, each evaluated against 17 fixed hypotheses — a three-way entailment
label plus the evidence spans supporting it.

- `train.json` (423 docs) · `dev.json` (61) · `test.json` (123)
- `raw/` — the 607 source documents
- `LICENSE`, `TERMS` — upstream terms, read before redistributing

> Koreeda & Manning (2021). *ContractNLI: A Dataset for Document-level Natural
> Language Inference for Contracts.* Findings of EMNLP 2021.

### MAPP Corpus — `data/mapp/MAPP_Corpus/`

Bilingual mobile-app privacy policies: 64 English and 91 German, annotated with
the same practice taxonomy so GDPR-era EU and US policies can be compared.

- `English_sanitized_policies/` (64) + `English_consolidation/` (64)
- `German_sanitized_policies/` (91) + `German_consolidation/` (91)
- `documentation/` — annotation scheme and manual

> Arora et al. (2022). *A Tale of Two Regulatory Regimes: Creation and Analysis of
> a Bilingual Privacy Policy Corpus.* LREC 2022.

## Licensing

CUAD and ContractNLI are CC BY 4.0. OPP-115 and MAPP are provided by the Usable
Privacy Policy Project for research use and require citing their papers. All four
are downloaded from their original upstream sources — nothing is re-hosted here.
Cite the papers above in any published evaluation, and check each corpus's own
`readme` / `TERMS` before redistributing.
