# LEXEC NeurIPS paper

This directory is a self-contained LaTeX project for the NeurIPS 2027
submission planned by the repository.  It uses the official NeurIPS 2026
formatting archive, the newest official archive available when this project
was created (26 August 2026), with the `eandd` track option.  The 2027 call
and template are not yet published; refresh the files in
`template/official/` and the manifest when they become available.  The
official style file is not modified.

The manuscript is deliberately evidence-gated.  Engineering capabilities are
reported as implemented, while exploratory, fixture-only, unrun, and blocked
experiments remain visibly distinct.  No legal-correctness or benchmark-quality
claim is made from the current repository snapshot.

## Layout

- `main.tex` — anonymous submission entry point.
- `sections/` — manuscript sections, included in order by `main.tex`.
- `figures/` and `tables/` — source files for paper figures and tables.
- `references/` — BibTeX database.
- `template/official/` — unchanged official style, checklist, source, and hash manifest.
- `scripts/` — reproducible build and source/artifact validator.
- `tests/` — Python tests for the paper contract.
- `build/` — ignored generated files (PDF, auxiliary files, logs).

## Build and validate

From the repository root:

```bash
paper/scripts/build_paper.sh
.venv/bin/python paper/scripts/validate_paper.py --source paper/main.tex --build-dir paper/build
```

The build script uses `TECTONIC_BIN` when supplied, otherwise the first
`tectonic` on `PATH`.  On the author's machine the preinstalled binary is
`/opt/homebrew/bin/tectonic`; no TeX distribution or package is downloaded by
this repository.  `validate_paper.py --check-source` performs the deterministic
checks without a local TeX installation.  The full repository test command is
`.venv/bin/python -m pytest -q`.

The latest NeurIPS instructions allow up to nine pages of content for the
Evaluations & Datasets track; references, checklist, and appendices are kept
outside that content budget according to the official style.  Always re-check
the current call before submission.
