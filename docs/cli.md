# CLI reference: `cli/extract.py`

`cli/extract.py` is the extraction pipeline's orchestrator: it runs the
eleven canonical agents (`agent_01`–`agent_11`) against a source-document
directory and writes a grounding-certified, DMN/BPMN-ready knowledge graph
under `pipeline-output/<batch-name>/`. This document is the complete,
stand-alone reference for running it — commands, options, configuration,
output, troubleshooting, and common workflows. You should not need to read
`cli/extract.py`'s source to use it.

For what the pipeline does at each stage (responsibilities, algorithms,
inputs/outputs, failure semantics), see
[`ARCHITECTURE.md`'s stage reference](../ARCHITECTURE.md#23-detailed-stage-reference).
This document covers running and monitoring it, not what each stage
computes internally.

- [Quick start](#quick-start)
- [Command reference](#command-reference)
- [Selecting stages](#selecting-stages)
- [Output modes](#output-modes)
- [What the terminal display shows](#what-the-terminal-display-shows)
- [The `run_metrics.json` artifact](#the-run_metricsjson-artifact)
- [Configuration](#configuration)
- [Agent 12 business knowledge report](#agent-12-business-knowledge-report)
- [Common workflows](#common-workflows)
- [Troubleshooting](#troubleshooting)

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp config.example.json config.json
cp .env.example .env   # add your OPENAI_API_KEY

mkdir -p compliance-files/nda_confidentiality
cp /path/to/your/*.txt compliance-files/nda_confidentiality/

python3 cli/extract.py --dir nda_confidentiality --domain nda_confidentiality --target-rules 20
```

This runs all eleven stages in order against
`compliance-files/nda_confidentiality/`, writing to
`pipeline-output/nda_confidentiality/` (the batch name defaults to `--dir`'s
basename). You'll see a configuration panel, a live stage-by-stage progress
table, highlighted log output, and a final summary with total time, tokens,
cost, and cache utilization — see
[What the terminal display shows](#what-the-terminal-display-shows) for a
full walkthrough of a real run's output.

## Command reference

```text
cli/extract.py --dir DIR --domain DOMAIN [options] [selector]
```

| Option | Required | Description |
| --- | --- | --- |
| `--dir DIR` | yes | Source document directory. Absolute, or a name under `compliance-files/` (e.g. `--dir nda_confidentiality` resolves to `compliance-files/nda_confidentiality/`). |
| `--domain {nda_confidentiality,privacy_policy,mobile_app_privacy,commercial_contracts,deonticbench,mortgage}` | yes | Which domain-prompt pack to use. See [README.md's Quickstart](../README.md#quickstart) for the supported-domains list and what each domain-prompt pack covers. |
| `--batch-name NAME` | no | Output folder name under `pipeline-output/`. Default: `--dir`'s basename. Reuse a batch name to overwrite/continue that run's output directory. |
| `--target-rules N` | no | Business rules `agent_03` tries to extract **per batch** (default `30`). Does **not** bound chunk/batch coverage — every organized chunk is still read and processed. Use `--pilot-batch-limit` to bound coverage for a cheap smoke run. |
| `--pilot-batch-limit N` | no | Cap the number of word-balanced batches `agent_03` processes. Omit for full corpus coverage (the default). A capped run is never a coverage claim — see [`docs/pipeline_smoke.md`](pipeline_smoke.md) for an example smoke run. |
| `--workers N` | no | Local scheduling workers. Default: `config.json`'s `pipeline.max_workers`. |
| `--skip-optimize` | no | Skip `agent_06`–`agent_08` (KG optimization, readiness, remediation). Independent `agent_09` grounding still runs before `agent_10` DAG generation. |
| `--keep-going` | no | With `--stages`, run every selected stage even after an earlier one fails, instead of stopping at the first failure. No effect on a single-stage selector or a full run — see [Selecting stages](#selecting-stages). |
| `--output {text,json}` | no | `text` (default): the polished interactive display below. `json`: line-delimited JSON events on stdout for automation — see [Output modes](#output-modes). |
| `--agent AGENT_ID` | no* | Run exactly one agent by canonical id (`agent_01`–`agent_11`). |
| `--stage N` | no* | Run exactly one stage by number (`1`–`11`; accepts `7` or `07`). Same agent as `--agent agent_07`. |
| `--stages RANGE` | no* | Run **multiple** stages in order — a range, a list, or a mix: `3-6`, `3,5,7`, `3-6,9,11`. See [Selecting stages](#selecting-stages). |
| `--step ALIAS` | no* | Deprecated legacy selector (`1`, `3.5`, `5.7`, ...) from a prior ten-stage numbering. Prints the canonical stage it maps to. Prefer `--stage`/`--agent`. |

\* `--agent`, `--stage`, `--stages`, and `--step` are mutually exclusive. Omit
all four to run the full 11-stage pipeline (`run_all`).

Run `python3 cli/extract.py --help` for the same reference from the tool
itself, including the full per-stage summary table baked into its
description.

## Agent 12 business knowledge report

Agent 12 is a post-pipeline presentation stage. It reads the optimized graph,
the DAG artifact, Agent 11's DMN/BPMN/CMMN bundle, and the organized source
chunks, then writes a single self-contained HTML report. It does not call an
LLM or alter upstream artifacts.

```bash
KG_BATCH_NAME=nda-2026 KG_DOMAIN=nda_confidentiality \
  .venv/bin/python agents/agent_12_business_knowledge_report.py
```

The default output is
`pipeline-output/<batch-name>/agent_12-business-knowledge-report/business_knowledge_report.html`.
Use `--graph`, `--dags`, `--models-dir`, `--organized-dir`, and `--output-dir`
when reading from an explicitly selected bundle. The report embeds source
chunks and its CSS, JavaScript, and SVG visualizations, so it can be opened
directly from disk without a web server or network access.

## Selecting stages

Four ways to choose what runs, from broadest to narrowest:

| You want to... | Use | Example |
| --- | --- | --- |
| Run the whole pipeline | (no selector) | `cli/extract.py --dir nda --domain nda_confidentiality` |
| Run a contiguous or mixed set of stages | `--stages` | `cli/extract.py --dir nda --domain nda_confidentiality --batch-name nda-2026 --stages 7-9` |
| Run exactly one stage by number | `--stage` | `cli/extract.py --dir nda --domain nda_confidentiality --batch-name nda-2026 --stage 9` |
| Run exactly one stage by agent id | `--agent` | `cli/extract.py --dir nda --domain nda_confidentiality --batch-name nda-2026 --agent agent_09` |

`--stages` is the answer to "run one or more selected stages independently":

```bash
# Re-run readiness through grounding (stages 7, 8, 9) after fixing a source doc,
# without redoing extraction (stages 1-5) or optimization (stage 6):
python3 cli/extract.py --dir nda_confidentiality --domain nda_confidentiality \
  --batch-name nda-2026 --stages 7-9

# Re-run just DAG generation and model generation (10, 11):
python3 cli/extract.py --dir nda_confidentiality --domain nda_confidentiality \
  --batch-name nda-2026 --stages 10,11

# Non-contiguous: re-validate (4) and re-certify grounding (9) only:
python3 cli/extract.py --dir nda_confidentiality --domain nda_confidentiality \
  --batch-name nda-2026 --stages 4,9
```

Stages always run **in ascending canonical order** regardless of how you
wrote the range (`--stages 9,3` and `--stages 3,9` are identical). By
default, a `--stages` run stops at the first stage that fails or is
review-gated — matching `run_all`'s own fail-closed behavior. Pass
`--keep-going` to run every selected stage regardless, useful when you want
one full report of which of several stages succeed or fail (for example,
re-running every optional stage after a config change) rather than stopping
at the first problem:

```bash
python3 cli/extract.py --dir nda_confidentiality --domain nda_confidentiality \
  --batch-name nda-2026 --stages 7-11 --keep-going
```

**Reuse an existing batch's output**: `--stages`/`--stage`/`--agent` all
write into the *same* `pipeline-output/<batch-name>/` directory as the
original run (via `--batch-name`) and read whatever intermediate files that
run already produced (e.g. `--stages 7-9` reads `agent_06`'s optimized
graph). This is the pipeline's targeted-rerun mechanism — there is no
separate `--resume` flag; re-running only the stage(s) you need, with the
same `--batch-name`, *is* the resume workflow. See
[Common workflows](#common-workflows) for a full example after a mid-run
failure.

**Numbering contract**: the stage number and agent identifier are always the
same value — `--stage 9` and `--agent agent_09` run the identical thing
(`agent_09`, independent grounding verification). See
[README.md's numbering contract](../README.md#numbering-contract) for the
full stage table.

## Output modes

### `--output text` (default)

The polished interactive display described in the next section: a
configuration panel, a live stage table, highlighted log passthrough, and a
final summary panel. Built on [`rich`](https://github.com/Textualize/rich),
which auto-detects a non-interactive terminal (a CI log, a redirected file,
`NO_COLOR=1`, `TERM=dumb`) and degrades to plain, uncolored text on its own —
no separate flag needed for CI logs.

### `--output json`

One JSON object per line (NDJSON) on **stdout**, for automation and
scripting. Raw subprocess log lines (an agent's own prints, `[LLM_COST]`
markers already excluded) go to **stderr** instead, so a script reading
stdout never has to skip non-JSON lines — every line on stdout is guaranteed
to parse.

Event types, in emission order for a run: `run_start` (once, config +
planned stage list), `stage_start` / `stage_end` (once per stage — a
`stage_end` object has the same shape as one entry of `run_metrics.json`'s
`stages` array, see below), `run_end` (once, the full run summary — same
shape as `run_metrics.json` itself), and `error` (only on a fatal error,
e.g. a missing source directory).

```bash
python3 cli/extract.py --dir nda_confidentiality --domain nda_confidentiality \
  --batch-name nda-2026 --stages 7-9 --output json > run.ndjson 2> run.log

# Pull the final pass/fail and total cost out of the stream:
tail -1 run.ndjson | python3 -c "import json,sys; d=json.load(sys.stdin); \
  print(d['overall_status'], d['totals']['cost_usd'])"

# Watch stage completions live:
tail -f run.ndjson | jq -r 'select(.event==\"stage_end\") | \"\(.stage_id) \(.status)\"'
```

Exit code is unchanged in either mode: `0` on success, `1` on failure/stop
(a mid-pipeline review-gate that is later resolved still counts as pass —
see the readiness/grounding review-signal note in
[README.md](../README.md#numbering-contract)).

## What the terminal display shows

A real (locally captured, `NO_COLOR=1` for readability here — the actual
terminal is in color) run of `--stages 3,4` against a two-agent stub, with a
plain-text terminal:

```text
╭──────────────────────────── policy-logic-forge — extraction pipeline ────────────────────────────╮
│ domain        nda_confidentiality                                                                │
│ source        /path/to/compliance-files/nda_confidentiality                                      │
│ batch name    acme-nda-2026                                                                      │
│ target rules  20                                                                                 │
│ model         gpt-5.6-luna                                                                       │
│ reasoning effort high                                                                             │
│ provider      openai                                                                              │
│ workers       32                                                                                  │
│ skip optimize False                                                                               │
│ stages selected 2 selected stages (agent_{03, 04})                                                │
│ performance   llm concurrency=32, document workers=32, readiness workers=80, remediation workers…  │
│ output        pipeline-output/acme-nda-2026                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
Stage plan
┏━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┓
┃   # ┃ Stage                           ┃ Status       ┃  Duration ┃   Tokens ┃     Cost ┃  Cache% ┃
┡━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━┩
│   1 │ Stage 03/11 · agent_03 · Rules… │ · pending    │        -- │       -- │       -- │      -- │
│   2 │ Stage 04/11 · agent_04 · Rule … │ · pending    │        -- │       -- │       -- │      -- │
└─────┴─────────────────────────────────┴──────────────┴───────────┴──────────┴──────────┴─────────┘
────────────────────── ▶ Stage 1/2 — Stage 03/11 · agent_03 · Rules Extractor ──────────────────────
$ .venv/bin/python3 agents/agent_03_rules_extractor.py
Extracting business rules...
  extracted 24 rules
✔ Stage 03/11 · agent_03 · Rules Extractor: PASS (exit 0) in 0.0s — 1 LLM calls, 21.6k tokens, $0.05 (53% cached)
Progress
┏━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┓
┃   # ┃ Stage                           ┃ Status       ┃  Duration ┃   Tokens ┃     Cost ┃  Cache% ┃
┡━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━┩
│   1 │ Stage 03/11 · agent_03 · Rules… │ ✔ pass       │      0.0s │    21.6k │    $0.05 │     53% │
│   2 │ Stage 04/11 · agent_04 · Rule … │ · pending    │        -- │       -- │       -- │      -- │
└─────┴─────────────────────────────────┴──────────────┴───────────┴──────────┴──────────┴─────────┘
────────────────────── ▶ Stage 2/2 — Stage 04/11 · agent_04 · Rule Validator ───────────────────────
$ .venv/bin/python3 agents/agent_04_rule_validator.py --rules-file ... --source-dir ... --output-dir ...
Validating rule contracts...
  2 rules flagged for advisory review
✔ Stage 04/11 · agent_04 · Rule Validator: PASS (exit 0) in 0.0s

Final stage summary
┏━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┓
┃   # ┃ Stage                           ┃ Status       ┃  Duration ┃   Tokens ┃     Cost ┃  Cache% ┃
┡━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━┩
│   1 │ Stage 03/11 · agent_03 · Rules… │ ✔ pass       │      0.0s │    21.6k │    $0.05 │     53% │
│   2 │ Stage 04/11 · agent_04 · Rule … │ ✔ pass       │      0.0s │       -- │       -- │      -- │
└─────┴─────────────────────────────────┴──────────────┴───────────┴──────────┴──────────┴─────────┘
╭────────────────────────────────────────── Run summary ───────────────────────────────────────────╮
│ status          ✔ PASS                                                                           │
│ total time      0.0s                                                                             │
│ LLM calls       1                                                                                │
│ tokens          21.6k (18.4k prompt, 3.2k completion)                                            │
│ cache hit rate  53%                                                                              │
│ estimated cost  $0.05                                                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

What each part answers, mapped to the goal this display was built for:

| Display element | Answers |
| --- | --- |
| Config panel (top) | "What is running and why" — domain, source, batch, model/effort/provider, worker/concurrency profile, resolved output path |
| Stage plan table (before any stage runs) | "Which stages will run, in what order" |
| `▶ Stage i/N` rule before each stage | "What's running right now" |
| Streamed log lines, color-classified | "Important operations and results" — a line starting with `❌`/`ERROR:`/`Traceback` prints in red, `⚠️`/`WARNING:` in yellow, `✅`/`PASS`/`COMPLETE` in green; `[LLM_COST]` marker lines are parsed into the metrics below and never shown raw |
| One-line stage summary after each stage | Pass/fail/review-gated status, exit code, duration, LLM call count, tokens, cost, cache-hit % for that stage alone, and any warning/error line counts |
| "Progress" table after each stage | "Which stages have completed, failed, or remain" at a glance, updated live |
| Final "Run summary" panel | Total wall-clock time, total LLM calls/tokens (prompt vs. completion), overall cache-hit rate, total estimated cost, and aggregate warning/error counts for the whole run |

A stage can land in one of five terminal states, shown with a distinct
icon/color: `✔ pass` (green), `◆ review` (cyan — an agent 07/08/09
data-quality review signal, not a crash; see
[README.md](../README.md#numbering-contract)), `✘ fail` (red, a hard
stop), `– skipped` (dim, e.g. `agent_06` under `--skip-optimize`), and
`· pending` (dim, not yet reached).

## The `run_metrics.json` artifact

Every run — full, single-stage, or multi-stage, in either output mode —
writes `pipeline-output/<batch-name>/run_metrics.json` when it finishes,
independent of the terminal display. This is the durable, machine-readable
record of the run: reuse it in a script even if you only captured the
`text` terminal output, or diff it across runs.

```json
{
  "schema_version": "pipeline-run-metrics/1.0",
  "batch_name": "acme-nda-2026",
  "domain": "nda_confidentiality",
  "source_dir": "/path/to/compliance-files/nda_confidentiality",
  "started_at": 1788104906.118,
  "finished_at": 1788104906.994,
  "duration_seconds": 0.876,
  "overall_status": "pass",
  "config": {
    "target_rules": 20,
    "model": "gpt-5.6-luna",
    "reasoning_effort": "high",
    "provider": "openai",
    "workers": 32,
    "skip_optimize": false,
    "performance": { "KG_LLM_CONCURRENCY": "32", "...": "the full ~24-key resolved KG_* profile" },
    "output_path": "pipeline-output/acme-nda-2026",
    "stages_selected": "2 selected stages (agent_{03, 04})"
  },
  "stages": [
    {
      "stage_id": "agent_03", "label": "Stage 03/11 · agent_03 · Rules Extractor",
      "status": "pass", "exit_code": 0, "note": null,
      "duration_seconds": 0.052, "llm_call_count": 1,
      "prompt_tokens": 18400, "completion_tokens": 3200, "cached_tokens": 9800, "total_tokens": 21600,
      "cost_usd": 0.0491, "cache_hit_rate_percent": 53.3,
      "warning_count": 0, "error_count": 0
    }
  ],
  "totals": {
    "llm_calls": 1, "prompt_tokens": 18400, "completion_tokens": 3200,
    "cached_tokens": 9800, "total_tokens": 21600, "cost_usd": 0.0491,
    "cache_hit_rate_percent": 53.3, "warnings": 0, "errors": 0
  }
}
```

`overall_status` is one of `"pass"` or `"fail"` (a run that stops on a
review-gated stage without recovering counts as `"fail"`, matching the
process exit code). Each stage's `status` is one of `"pass"`, `"fail"`,
`"review"`, or `"skipped"`. `cache_hit_rate_percent` is `null` when a stage
made no LLM calls with prompt tokens to report (nothing to cache-hit
against), not `0`.

## Configuration

Model, reasoning effort, provider, and the performance profile all come from
`config.json` (see [README.md's Quickstart](../README.md#quickstart) for
initial setup from `config.example.json`) and are echoed in both the config
panel and `run_metrics.json`'s `config` object every run, so you can always
see exactly what a given run used without cross-referencing the config file
separately.

The performance profile (worker/concurrency counts) can be overridden per
run via `KG_*` environment variables without editing `config.json` — see
[README.md](../README.md#quickstart) for the full list and defaults, e.g.:

```bash
KG_GROUNDING_LLM_CONCURRENCY=16 python3 cli/extract.py \
  --dir nda_confidentiality --domain nda_confidentiality --stage 9
```

Overridden values show up in the config panel/`run_metrics.json` exactly as
resolved (env override applied), not the `config.json` default.

## Common workflows

### Full run from a fresh corpus

```bash
python3 cli/extract.py --dir nda_confidentiality --domain nda_confidentiality \
  --batch-name nda-2026-q1 --target-rules 30
```

### Cheap smoke test before a full run

Bound both cost and time with `--pilot-batch-limit` and `--skip-optimize`
(see [`docs/pipeline_smoke.md`](pipeline_smoke.md) for a fully worked
example and its actual observed result):

```bash
python3 cli/extract.py --dir nda_confidentiality --domain nda_confidentiality \
  --batch-name nda-smoke --target-rules 1 --pilot-batch-limit 1 --workers 1 --skip-optimize
```

### Recovering from a mid-run failure (no separate `--resume` flag)

If a full run fails partway — say `agent_06` fails after `agent_01`–`05`
already wrote their output — re-run only the remaining stages against the
**same batch name**. Earlier stages' output is untouched and reused as-is:

```bash
# Original run failed at stage 6:
python3 cli/extract.py --dir nda_confidentiality --domain nda_confidentiality \
  --batch-name nda-2026-q1 --target-rules 30
# ... fails at Stage 06/11 ...

# Fix whatever caused the failure, then continue from stage 6 onward,
# same batch name so it reuses stages 1-5's already-written output:
python3 cli/extract.py --dir nda_confidentiality --domain nda_confidentiality \
  --batch-name nda-2026-q1 --stages 6-11
```

The stage plan/final summary only ever reflect the stages you actually
selected for that invocation — `run_metrics.json` from a `--stages 6-11`
rerun will not contain entries for stages 1–5; consult the earlier full
run's own `run_metrics.json` (or diff both) if you need the whole run's
combined picture.

### Re-checking readiness/grounding after fixing a source document

```bash
python3 cli/extract.py --dir nda_confidentiality --domain nda_confidentiality \
  --batch-name nda-2026-q1 --stages 7-9
```

### Scripted/CI usage

```bash
if ! python3 cli/extract.py --dir nda_confidentiality --domain nda_confidentiality \
     --batch-name "nightly-$(date +%Y%m%d)" --output json > run.ndjson 2> run.log; then
  echo "Pipeline failed; see run.log" >&2
  tail -1 run.ndjson | jq .
  exit 1
fi
cost=$(tail -1 run.ndjson | jq -r '.totals.cost_usd')
echo "Run succeeded, total cost: \$${cost}"
```

### Validating configuration without spending any tokens

```bash
.venv/bin/python scripts/validate_config.py
```

## Troubleshooting

| Symptom | What it means | What to do |
| --- | --- | --- |
| `Source directory not found: ...` | `--dir` didn't resolve to an existing path (checked as absolute, then under `compliance-files/`) | Check the path; for a relative `--dir`, confirm the directory exists under `compliance-files/<name>/` |
| `argument --agent/--stage/--step/--stages: not allowed with argument ...` | Two mutually exclusive selectors were passed together | Pick exactly one of `--agent`, `--stage`, `--step`, `--stages` (or none, for a full run) |
| A stage shows `◆ review` (cyan), not `✘ fail` (red) | Agent 07/08/09 exited 3: a **data-quality review signal**, not a crash — affected rules are flagged `requires_review: true` and the run can still continue to later stages | Not necessarily an error to fix before proceeding; consult `kg_readiness_report.md`/`kg_grounding_report.md` in the batch's `agent_06-07-08-09-optimized/` directory. See the review-signal note in [README.md](../README.md#numbering-contract) |
| `STOPPED: agent_07 invariant failure (not remediable by agent_08).` | A structural readiness invariant failed in a way agent_08's focused remediation cannot fix | Inspect `kg_readiness_report.json` in `agent_06-07-08-09-optimized/`; this needs a source-document or upstream-extraction fix, then a fresh run from an earlier stage |
| `STOPPED: agent_09 grounding certification failed.` | Grounding claims were contradicted or missing evidence, and the run's response coverage was incomplete (so it's not safely treated as a review signal) | Inspect `kg_grounding_report.json`; often means the LLM provider dropped/duplicated a response — re-run `--stages 9-11` |
| Every stage shows `$0.00` cost / `n/a` cache% even though the run clearly called an LLM | The model isn't in `utils/llm_client.py`'s pricing table, or the provider response has no `usage` field | Token counts are still accurate; cost is a best-effort estimate only for known model names (see that module's `_PRICING_PER_1M`) |
| Colors/box-drawing characters look wrong or garbled | Terminal doesn't support UTF-8/ANSI (or output is piped somewhere that mangles it) | `rich` degrades automatically for non-tty output; if you're intentionally scripting, use `--output json` instead of parsing the text display |
| Want machine-readable output but still see a rich panel | `--output` defaults to `text` | Pass `--output json` explicitly |
| A `--stages` run stopped after the first failing stage, but you wanted a full report | Default `--stages` behavior is fail-fast, matching a full run | Add `--keep-going` |
| `run_metrics.json` is missing after a run | The batch's `pipeline-output/<batch-name>/` directory couldn't be created/written (permissions, disk full) | The reporter surfaces this as a red "Could not write run_metrics.json" error panel (or a JSON `error` event) rather than silently dropping it — check the message for the underlying `OSError` |
