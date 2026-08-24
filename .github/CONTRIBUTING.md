# Contributing to compliance-to-code

Thanks for your interest in improving **compliance-to-code**. This document
covers how to set up a local environment and run the test suite before
opening a pull request.

This is a single-package CLI-and-library repo — see `README.md` "Structure"
for the full layout (`agents/`, `utils/`, `cli/extract.py`, `prompts/`,
`domain-prompts/`, `benchmarks/`).

## Local setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp config.example.json config.json
cp .env.example .env   # add your OPENAI_API_KEY
```

## Running the pipeline

No sample documents are committed — build a benchmark corpus first (see
`README.md` "Quickstart" and "Data and licensing"), then:

```bash
python3 cli/extract.py --dir <domain> --domain <domain> --target-rules 20
```

## Running tests

```bash
pytest
```

No API key is needed — the suite tests contract validation,
readiness/grounding logic, dependency-DAG partitioning, and prompt-pack
consistency against fixed graphs and prompt files, not live extraction runs.

## Pull requests

1. Branch from `main`.
2. Keep changes focused and reasonably small.
3. Update or add tests when behavior changes.
4. Describe what changed and how you tested it, following
   `.github/pull_request_template.md`.

## Ground rules

- Never commit secrets or real data. `.env` and `config.json` are gitignored
  and local-only.
- Local/generated data paths are not committed: `compliance-files/<domain>/`
  (full benchmark corpora), `pipeline-output/`, and `benchmarks/data/` /
  `benchmarks/raw/` / `benchmarks/*-source-docs/`. See `.gitignore` for the
  exact list and why.
- If you edit a domain's extraction prompt, regenerate it from
  `scripts/generate_benchmark_domain_prompts.py` rather than hand-editing the
  committed `.txt` files — see that script's module docstring.
- See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for collaboration expectations.
- See [SECURITY.md](SECURITY.md) for private vulnerability reporting.
