# Technical report

A LaTeX report on the architecture of Policy Logic Forge: the thirteen-stage
pipeline, the evidence spine, the exit-code contract, the readiness gate, the
compiler layer and its proof obligations, the generated model formats,
RegDelta, and what the evaluation actually found — including a pre-registered
hypothesis that failed.

```bash
make          # build _build/report.pdf
make data     # regenerate every plot coordinate from the result files
make check    # fail if the committed figure data is stale
make clean
```

## Why `tectonic`

The report needs `pgfplots`, `tcolorbox`, Libertinus and IBM Plex. A minimal
TeX Live install — the common case on macOS — has none of them, and
`arrows.meta` is missing too. `tectonic` carries its own package bundle,
fetches what it needs once, and caches it, so every build after the first is
offline and reproducible. `pdflatex` will work only on a full TeX Live.

## Figures are generated, never transcribed

`make_data.py` reads the committed result artifacts and writes every
coordinate the plots use:

| Output | Source |
| --- | --- |
| `data/rc_confidence.csv`, `data/rc_refusal_point.csv`, `data/rc_macros.tex` | `research/refusal_signal/results/baseline.jsonl` |
| `data/compile_ladder.tex` | `research/pilot/results/sara_binary.json` |
| `data/bucket_accuracy.tex` | both refusal-signal result files |
| `data/code_size.tex` | the repository tree |

So a number in the PDF cannot drift from the run that produced it. `make
check` fails if regenerating changes anything, which makes staleness a build
error rather than a proofreading miss.

The prose figures — the pipeline, the evidence spine, the verification
ladder, the exit-code contract, the module graph, RegDelta — are TikZ, drawn
in `figures/`.

## Editing notes

Three things cost real time when this was built, all worth knowing before
touching the figures:

- **Never put an expression inside a TikZ coordinate.** `at (\i*(\w+2), 0)`
  makes TikZ read `(\w+2)` as a node name and fail with *No shape named …*.
  Place nodes on an integer grid and let the `x=`/`y=` unit vectors do the
  arithmetic.
- **Fit the bands, do not compute them.** Group boxes with
  `fit=(a)(b)(c)` on a background layer. Hand-computed band heights drift
  from their contents the moment a label changes.
- **Never `\input` a coordinate list inside pgfplots `coordinates{}`.** It
  sends the coordinate parser into a loop that does not terminate — the
  build hangs rather than failing. Use `\addplot table[col sep=comma]` with
  a CSV, which is what the risk–coverage figure does.

Two font settings in `preamble.tex` are load-bearing: `Ligatures=TeX`
(without it `---` renders as three literal hyphens in Plex, since the dash
ligature is a font feature the serif has and Plex does not get by default) and
`Scale=MatchLowercase` (without it `\code{}` renders oversized inside
`\scriptsize` figure text).
