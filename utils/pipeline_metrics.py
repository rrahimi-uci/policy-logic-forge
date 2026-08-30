"""Run/stage metrics collection for the CLI's live progress display and
``run_metrics.json`` artifact.

``utils/llm_client.py`` already emits one ``[LLM_COST]{...}`` JSON line to
stdout per LLM call (originally "emitted for the UI runner" -- see that
module's comment; the UI it fed was removed, this module is the new
consumer). This module parses those lines, aggregates them per pipeline
stage and for the whole run, and classifies plain log lines as
warning/error/success/plain for terminal highlighting. It has no
dependency on ``rich`` or any terminal library -- ``cli/console.py``
consumes this module's plain dataclasses to render output.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# The exact prefix utils/llm_client.py writes before the JSON payload.
LLM_COST_PREFIX = "[LLM_COST]"

# Terminal stage statuses. "review" is a first-class outcome, not an error --
# see agent_07/08/09's documented exit-code-3 "review signal" semantics
# (ARCHITECTURE.md Section 2.3): a rule needing human review is not a
# pipeline failure.
PENDING, RUNNING, PASS, FAIL, REVIEW, SKIPPED = (
    "pending", "running", "pass", "fail", "review", "skipped",
)


def parse_llm_cost_line(line: str) -> "LLMCallRecord | None":
    """Return an ``LLMCallRecord`` if ``line`` is a ``[LLM_COST]`` marker, else ``None``."""

    stripped = line.strip()
    if not stripped.startswith(LLM_COST_PREFIX):
        return None
    payload = stripped[len(LLM_COST_PREFIX):]
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return LLMCallRecord(
            model=str(data.get("model") or ""),
            prompt_tokens=int(data.get("prompt_tokens") or 0),
            completion_tokens=int(data.get("completion_tokens") or 0),
            total_tokens=int(data.get("total_tokens") or 0),
            cached_tokens=int(data.get("cached_tokens") or 0),
            cost_usd=float(data.get("cost") or 0.0),
        )
    except (TypeError, ValueError):
        return None


# Best-effort classification of a subprocess log line for terminal
# highlighting. Deliberately conservative -- it only matches well-known
# markers this codebase's own agents/utils already print (see
# utils/llm_client.py's "⚠️" truncation warning and cli/extract.py's own
# "PASS"/"FAIL"/"STOPPED" lines), plus a narrow regex for an unambiguous
# ERROR/WARNING/Traceback token. It is pattern matching over stdout text,
# not semantic understanding -- a rule whose *content* happens to contain
# the word "warning" will not be misclassified, because the checks below
# only match line-start markers or a capitalized, colon-terminated token.
_ERROR_LINE = re.compile(r"^\s*(❌|✗|ERROR[:\s]|Traceback \(most recent call last\)|FAIL[ :])")
_WARNING_LINE = re.compile(r"^\s*(⚠️?|WARNING[:\s]|STOPPED:)")
_SUCCESS_LINE = re.compile(r"^\s*(✅|✓|PASS[ :]|COMPLETE)")


def classify_log_line(line: str) -> str:
    """Return ``"error"``, ``"warning"``, ``"success"``, or ``"plain"``."""

    if _ERROR_LINE.match(line):
        return "error"
    if _WARNING_LINE.match(line):
        return "warning"
    if _SUCCESS_LINE.match(line):
        return "success"
    return "plain"


@dataclass
class LLMCallRecord:
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int
    cost_usd: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cached_tokens": self.cached_tokens,
            "cost_usd": round(self.cost_usd, 6),
        }


@dataclass
class StageMetrics:
    stage_id: str
    label: str
    status: str = PENDING
    exit_code: int | None = None
    started_at: float | None = None
    finished_at: float | None = None
    llm_calls: list[LLMCallRecord] = field(default_factory=list)
    warning_count: int = 0
    error_count: int = 0
    note: str | None = None
    """Short human note attached on skip/review, e.g. "--skip-optimize"."""

    def start(self) -> None:
        self.status = RUNNING
        self.started_at = time.time()

    def finish(self, *, status: str, exit_code: int | None, note: str | None = None) -> None:
        self.status = status
        self.exit_code = exit_code
        self.finished_at = time.time()
        if note:
            self.note = note

    def record_llm_call(self, call: LLMCallRecord) -> None:
        self.llm_calls.append(call)

    def observe_log_line(self, line: str) -> None:
        kind = classify_log_line(line)
        if kind == "error":
            self.error_count += 1
        elif kind == "warning":
            self.warning_count += 1

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at is None:
            return None
        end = self.finished_at if self.finished_at is not None else time.time()
        return max(0.0, end - self.started_at)

    @property
    def prompt_tokens(self) -> int:
        return sum(call.prompt_tokens for call in self.llm_calls)

    @property
    def completion_tokens(self) -> int:
        return sum(call.completion_tokens for call in self.llm_calls)

    @property
    def cached_tokens(self) -> int:
        return sum(call.cached_tokens for call in self.llm_calls)

    @property
    def total_tokens(self) -> int:
        return sum(call.total_tokens for call in self.llm_calls)

    @property
    def cost_usd(self) -> float:
        return sum(call.cost_usd for call in self.llm_calls)

    @property
    def llm_call_count(self) -> int:
        return len(self.llm_calls)

    @property
    def cache_hit_rate_percent(self) -> float | None:
        """``None`` when no prompt tokens were sent (nothing to cache-hit against)."""

        prompt = self.prompt_tokens
        if prompt <= 0:
            return None
        return round(self.cached_tokens / prompt * 100, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "label": self.label,
            "status": self.status,
            "exit_code": self.exit_code,
            "note": self.note,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": round(self.duration_seconds, 3) if self.duration_seconds is not None else None,
            "llm_call_count": self.llm_call_count,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cached_tokens": self.cached_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "cache_hit_rate_percent": self.cache_hit_rate_percent,
            "warning_count": self.warning_count,
            "error_count": self.error_count,
        }


@dataclass
class RunMetrics:
    schema_version: str = "pipeline-run-metrics/1.0"
    batch_name: str = ""
    domain: str = ""
    source_dir: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    config: dict[str, Any] = field(default_factory=dict)
    stages: dict[str, StageMetrics] = field(default_factory=dict)
    overall_status: str | None = None
    """Set once at the very end: "pass" | "fail" | "review"."""

    def stage(self, stage_id: str, label: str) -> StageMetrics:
        """Get-or-create the ``StageMetrics`` for ``stage_id``, preserving insertion order."""

        if stage_id not in self.stages:
            self.stages[stage_id] = StageMetrics(stage_id=stage_id, label=label)
        return self.stages[stage_id]

    def finish(self, *, overall_status: str) -> None:
        self.finished_at = time.time()
        self.overall_status = overall_status

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at is None:
            return None
        end = self.finished_at if self.finished_at is not None else time.time()
        return max(0.0, end - self.started_at)

    def _totals(self, attr: str) -> float:
        return sum(getattr(s, attr) for s in self.stages.values())

    @property
    def total_llm_calls(self) -> int:
        return int(self._totals("llm_call_count"))

    @property
    def total_prompt_tokens(self) -> int:
        return int(self._totals("prompt_tokens"))

    @property
    def total_completion_tokens(self) -> int:
        return int(self._totals("completion_tokens"))

    @property
    def total_cached_tokens(self) -> int:
        return int(self._totals("cached_tokens"))

    @property
    def total_tokens(self) -> int:
        return int(self._totals("total_tokens"))

    @property
    def total_cost_usd(self) -> float:
        return self._totals("cost_usd")

    @property
    def overall_cache_hit_rate_percent(self) -> float | None:
        prompt = self.total_prompt_tokens
        if prompt <= 0:
            return None
        return round(self.total_cached_tokens / prompt * 100, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "batch_name": self.batch_name,
            "domain": self.domain,
            "source_dir": self.source_dir,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": round(self.duration_seconds, 3) if self.duration_seconds is not None else None,
            "overall_status": self.overall_status,
            "config": self.config,
            "stages": [self.stages[k].to_dict() for k in self.stages],
            "totals": {
                "llm_calls": self.total_llm_calls,
                "prompt_tokens": self.total_prompt_tokens,
                "completion_tokens": self.total_completion_tokens,
                "cached_tokens": self.total_cached_tokens,
                "total_tokens": self.total_tokens,
                "cost_usd": round(self.total_cost_usd, 6),
                "cache_hit_rate_percent": self.overall_cache_hit_rate_percent,
                "warnings": int(self._totals("warning_count")),
                "errors": int(self._totals("error_count")),
            },
        }

    def write_json(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def format_duration(seconds: float | None) -> str:
    """Human-readable duration: ``"3.2s"``, ``"1m 04s"``, ``"1h 02m"``."""

    if seconds is None:
        return "--"
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(round(seconds)), 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def format_cost(cost_usd: float) -> str:
    if cost_usd <= 0:
        return "$0.00"
    if cost_usd < 0.01:
        return f"${cost_usd:.4f}"
    return f"${cost_usd:.2f}"


def format_tokens(count: int) -> str:
    if count < 1000:
        return str(count)
    if count < 1_000_000:
        return f"{count / 1000:.1f}k"
    return f"{count / 1_000_000:.2f}M"
