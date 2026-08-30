"""Terminal rendering for ``cli/extract.py``.

Two reporters implement the same small interface
(``run_start``/``stage_start``/``log_line``/``stage_end``/``run_end``/``error``):

- ``TextReporter`` -- a polished, human-readable ``rich`` display: a run
  configuration panel, a live stage-plan table (reprinted after every stage
  transition so "what's done/running/left" is always visible), highlighted
  log passthrough, per-stage summary lines, and a final metrics table.
  ``rich`` auto-detects non-tty output and ``NO_COLOR``/``TERM=dumb`` and
  degrades to plain, uncolored text on its own -- no special-casing needed
  here.
- ``JsonReporter`` -- one JSON object per line (NDJSON) on stdout for
  automation/scripting. Raw subprocess log passthrough goes to *stderr*
  instead (so a machine reading stdout never has to skip non-JSON lines);
  a human can still `2>&1` or watch stderr for a live tail.

Both reporters are presentation only -- they read ``utils.pipeline_metrics``
dataclasses and render them. No pipeline/orchestration logic lives here.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Protocol, TextIO

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from utils.pipeline_metrics import (
    FAIL,
    PASS,
    PENDING,
    REVIEW,
    RUNNING,
    SKIPPED,
    RunMetrics,
    StageMetrics,
    format_cost,
    format_duration,
    format_tokens,
)

# (style, icon) per stage status, used by the plan/summary tables.
_STATUS_STYLE: dict[str, tuple[str, str]] = {
    PENDING: ("dim", "·"),       # ·
    RUNNING: ("bold yellow", "▶"),  # ▶
    PASS: ("bold green", "✔"),      # ✔
    REVIEW: ("bold cyan", "◆"),     # ◆
    FAIL: ("bold red", "✘"),        # ✘
    SKIPPED: ("dim", "–"),          # –
}

# Log-line highlight style per utils.pipeline_metrics.classify_log_line() kind.
_LOG_STYLE = {"error": "bold red", "warning": "yellow", "success": "green", "plain": None}


class Reporter(Protocol):
    """The interface ``cli/extract.py`` drives; either concrete class satisfies it."""

    def run_start(self, run: RunMetrics) -> None: ...
    def stage_start(self, stage: StageMetrics, index: int, total: int) -> None: ...
    def log_line(self, line: str, kind: str = "plain") -> None: ...
    def stage_end(self, stage: StageMetrics, run: RunMetrics) -> None: ...
    def run_end(self, run: RunMetrics) -> None: ...
    def error(self, message: str) -> None: ...


def _status_cell(status: str) -> Text:
    style, icon = _STATUS_STYLE.get(status, ("dim", "?"))
    return Text(f"{icon} {status}", style=style)


def _plan_table(run: RunMetrics, *, title: str) -> Table:
    table = Table(title=title, title_justify="left", expand=True, show_lines=False)
    table.add_column("#", justify="right", width=3)
    table.add_column("Stage", ratio=3, no_wrap=True, overflow="ellipsis")
    table.add_column("Status", width=12)
    table.add_column("Duration", justify="right", width=9)
    table.add_column("Tokens", justify="right", width=8)
    table.add_column("Cost", justify="right", width=8)
    table.add_column("Cache%", justify="right", width=7)
    for i, stage_id in enumerate(run.stages, start=1):
        stage = run.stages[stage_id]
        cache = stage.cache_hit_rate_percent
        table.add_row(
            str(i),
            stage.label,
            _status_cell(stage.status),
            format_duration(stage.duration_seconds),
            format_tokens(stage.total_tokens) if stage.total_tokens else "--",
            format_cost(stage.cost_usd) if stage.cost_usd else "--",
            f"{cache:.0f}%" if cache is not None else "--",
        )
    return table


class TextReporter:
    """Human-readable ``rich`` rendering with automatic non-tty/NO_COLOR degradation."""

    def __init__(self, *, stream: TextIO | None = None) -> None:
        self.console = Console(file=stream or sys.stdout, highlight=False, soft_wrap=True)

    def run_start(self, run: RunMetrics) -> None:
        cfg = run.config
        lines = [
            f"[bold]domain[/bold]        {run.domain}",
            f"[bold]source[/bold]        {run.source_dir}",
            f"[bold]batch name[/bold]    {run.batch_name}",
        ]
        for key in ("target_rules", "pilot_batch_limit", "model", "reasoning_effort", "provider",
                    "workers", "skip_optimize", "stages_selected"):
            if key in cfg and cfg[key] not in (None, ""):
                label = key.replace("_", " ")
                lines.append(f"[bold]{label:<12}[/bold] {cfg[key]}")
        # Full performance profile has ~24 KG_* env vars (see cli/extract.py's
        # _PERFORMANCE_ENV) -- too long for a config panel line. Show only the
        # handful an operator actually skims for; the rest still lands in
        # run_metrics.json's config.performance for anyone who needs it.
        perf = cfg.get("performance") or {}
        curated = [
            ("KG_LLM_CONCURRENCY", "llm concurrency"), ("KG_ORGANIZER_WORKERS", "document workers"),
            ("KG_READINESS_WORKERS", "readiness workers"), ("KG_REMEDIATION_WORKERS", "remediation workers"),
            ("KG_GROUNDING_WORKERS", "grounding workers"),
        ]
        shown = [f"{label}={perf[env_name]}" for env_name, label in curated if env_name in perf]
        if shown:
            lines.append(f"[bold]performance[/bold]   {', '.join(shown)}")
        if "output_path" in cfg:
            lines.append(f"[bold]output[/bold]        {cfg['output_path']}")
        self.console.print(Panel(
            "\n".join(lines),
            title="[bold]policy-logic-forge[/bold] — extraction pipeline",
            border_style="blue",
            expand=True,
        ))
        self.console.print(_plan_table(run, title="Stage plan"))

    def stage_start(self, stage: StageMetrics, index: int, total: int) -> None:
        self.console.rule(f"[bold yellow]▶ Stage {index}/{total} — {stage.label}[/bold yellow]", style="yellow")

    def log_line(self, line: str, kind: str = "plain") -> None:
        style = _LOG_STYLE.get(kind)
        if style:
            self.console.print(line.rstrip("\n"), style=style, markup=False, highlight=False)
        else:
            self.console.print(line.rstrip("\n"), markup=False, highlight=False)

    def stage_end(self, stage: StageMetrics, run: RunMetrics) -> None:
        style, icon = _STATUS_STYLE.get(stage.status, ("dim", "?"))
        bits = [f"{icon} {stage.label}: {stage.status.upper()}"]
        if stage.exit_code is not None:
            bits.append(f"(exit {stage.exit_code})")
        bits.append(f"in {format_duration(stage.duration_seconds)}")
        if stage.llm_call_count:
            bits.append(
                f"— {stage.llm_call_count} LLM calls, "
                f"{format_tokens(stage.total_tokens)} tokens, "
                f"{format_cost(stage.cost_usd)}"
            )
            cache = stage.cache_hit_rate_percent
            if cache is not None:
                bits.append(f"({cache:.0f}% cached)")
        if stage.warning_count:
            bits.append(f"— {stage.warning_count} warning(s)")
        if stage.error_count:
            bits.append(f"— {stage.error_count} error line(s)")
        if stage.note:
            bits.append(f"— {stage.note}")
        self.console.print(Text(" ".join(bits), style=style))
        self.console.print(_plan_table(run, title="Progress"))

    def run_end(self, run: RunMetrics) -> None:
        style, icon = _STATUS_STYLE.get(run.overall_status or PASS, ("bold", "?"))
        self.console.print()
        self.console.print(_plan_table(run, title="Final stage summary"))
        totals = run.to_dict()["totals"]
        cache_rate = totals["cache_hit_rate_percent"]
        cache_str = f"{cache_rate:.0f}%" if cache_rate is not None else "n/a"
        summary_lines = [
            f"[bold]status[/bold]          {icon} {(run.overall_status or '').upper()}",
            f"[bold]total time[/bold]      {format_duration(run.duration_seconds)}",
            f"[bold]LLM calls[/bold]       {totals['llm_calls']}",
            f"[bold]tokens[/bold]          {format_tokens(totals['total_tokens'])} "
            f"({format_tokens(totals['prompt_tokens'])} prompt, {format_tokens(totals['completion_tokens'])} completion)",
            f"[bold]cache hit rate[/bold]  {cache_str}",
            f"[bold]estimated cost[/bold]  {format_cost(totals['cost_usd'])}",
        ]
        if totals["warnings"] or totals["errors"]:
            summary_lines.append(f"[bold]log flags[/bold]       {totals['warnings']} warning(s), {totals['errors']} error line(s)")
        self.console.print(Panel(
            "\n".join(summary_lines),
            title="Run summary",
            border_style=style,
            expand=True,
        ))

    def error(self, message: str) -> None:
        self.console.print(Panel(message, title="[bold red]Error[/bold red]", border_style="red", expand=True))


class JsonReporter:
    """NDJSON event stream on stdout for automation; raw log passthrough on stderr."""

    def __init__(self, *, stream: TextIO | None = None, log_stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout
        self.log_stream = log_stream or sys.stderr

    def _emit(self, event: str, **payload: Any) -> None:
        print(json.dumps({"event": event, **payload}, ensure_ascii=False), file=self.stream, flush=True)

    def run_start(self, run: RunMetrics) -> None:
        self._emit(
            "run_start",
            batch_name=run.batch_name,
            domain=run.domain,
            source_dir=run.source_dir,
            config=run.config,
            stages=[{"stage_id": sid, "label": run.stages[sid].label} for sid in run.stages],
        )

    def stage_start(self, stage: StageMetrics, index: int, total: int) -> None:
        self._emit("stage_start", stage_id=stage.stage_id, label=stage.label, index=index, total=total)

    def log_line(self, line: str, kind: str = "plain") -> None:
        print(line, end="" if line.endswith("\n") else "\n", file=self.log_stream, flush=True)

    def stage_end(self, stage: StageMetrics, run: RunMetrics) -> None:
        self._emit("stage_end", **stage.to_dict())

    def run_end(self, run: RunMetrics) -> None:
        self._emit("run_end", **run.to_dict())

    def error(self, message: str) -> None:
        self._emit("error", message=message)


def make_reporter(output_mode: str, *, stream: TextIO | None = None) -> Reporter:
    if output_mode == "json":
        return JsonReporter(stream=stream)
    return TextReporter(stream=stream)
