#!/usr/bin/env python3
"""
Extraction orchestrator: compliance documents -> a grounding-certified,
DMN/BPMN-ready knowledge graph.

This is a lean, single-batch orchestrator by design (see README.md "Scope").
It runs the twelve canonical stages in order, streaming each subprocess's
output.  The stage number and agent identifier are deliberately identical:
Stage 01/13 is ``agent_01`` through Stage 13/13, ``agent_13``:

  01/12  agent_01  Document Organizer        chunk raw documents
  02/12  agent_02  Entity Extractor          entities & relationships
  03/12  agent_03  Rules Extractor           business rules (v2 contract)
  04/12  agent_04  Rule Validator             advisory quality pass (non-blocking)
  05/12  agent_05  Rules+Entities Merger      first complete knowledge graph
  06/12  agent_06  KG Optimizer               dedup + dependency analysis
  07/12  agent_07  Executable Readiness       four-invariant gate; DMN/BPMN projection
  08/12  agent_08  Readiness Remediator       focused fix-up (only if agent_07 requests it)
  09/12  agent_09  Grounding Verifier         independent claim-level certification
  10/12  agent_10  Dependency DAG Generator   100%-coverage DAG partition of the graph
  11/12  agent_11  Executable Model Generator  DMN 1.3 and BPMN 2.0 projection
  12/13  agent_12  Business Information Model  UML domain model + catalog
  13/13  agent_13  Business Knowledge Report    self-contained HTML report

Each agent subprocess shares an adaptive API-concurrency limiter (see
utils/adaptive_limiter.py) via KG_GLOBAL_LLM_STATE_FILE, so running multiple
batches concurrently (e.g. from a shell loop) is safe.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from utils.agent_names import (  # noqa: E402
    AGENT_IDS,
    CANONICAL_STAGE_NUMBERS,
    LEGACY_STEP_ALIASES,
    agent_id_for_stage,
    agent_spec,
    output_dir_name,
    stage_label,
)
from utils.config import MODEL_PROVIDERS, get_config  # noqa: E402
from utils.pipeline_metrics import (  # noqa: E402
    FAIL,
    PASS,
    REVIEW,
    SKIPPED,
    RunMetrics,
    classify_log_line,
    parse_llm_cost_line,
)
from cli.console import make_reporter  # noqa: E402

DOMAINS = [
    "nda_confidentiality", "privacy_policy", "mobile_app_privacy", "commercial_contracts",
    "deonticbench", "mortgage",
]

PACIFIC_TIME_ZONE = ZoneInfo("America/Los_Angeles")


def default_batch_name(source_dir: Path, *, now: datetime | None = None) -> str:
    """Build the default output-folder name for a fresh pipeline run.

    The timestamp uses the US Pacific civil clock (PST/PDT as applicable), so
    the folder name is easy to correlate with the operator's local terminal:
    ``mortgage-run-2026-09-01-09-05``.  An explicit ``--batch-name`` remains
    the stable choice when resuming a previous run.
    """

    run_time = now or datetime.now(PACIFIC_TIME_ZONE)
    if run_time.tzinfo is None:
        run_time = run_time.replace(tzinfo=PACIFIC_TIME_ZONE)
    else:
        run_time = run_time.astimezone(PACIFIC_TIME_ZONE)
    return f"{Path(source_dir).name}-run-{run_time:%Y-%m-%d-%H-%M}"


def _parse_stage_arg(value: str) -> str:
    """Normalize ``--stage 7`` and ``--stage 07`` to the same value."""

    try:
        normalized = str(int(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"stage must be an integer from 1 to {len(AGENT_IDS)}") from exc
    if normalized not in CANONICAL_STAGE_NUMBERS:
        raise argparse.ArgumentTypeError(f"stage must be an integer from 1 to {len(AGENT_IDS)}")
    return normalized


def _parse_stages_arg(value: str) -> list[str]:
    """Parse ``--stages`` into an ascending, deduplicated list of agent ids.

    Accepts a comma-separated mix of single numbers and inclusive ranges,
    e.g. ``"3-6"``, ``"3,5,7"``, or ``"3-6,9,11"``.
    """

    numbers: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, _, end_s = part.partition("-")
            try:
                start, end = int(start_s), int(end_s)
            except ValueError as exc:
                raise argparse.ArgumentTypeError(f"invalid stage range: {part!r}") from exc
            if start > end:
                raise argparse.ArgumentTypeError(f"invalid stage range (start > end): {part!r}")
            numbers.update(range(start, end + 1))
        else:
            try:
                numbers.add(int(part))
            except ValueError as exc:
                raise argparse.ArgumentTypeError(f"invalid stage number: {part!r}") from exc
    if not numbers:
        raise argparse.ArgumentTypeError("--stages requires at least one stage number or range")
    out_of_range = sorted(n for n in numbers if not 1 <= n <= len(AGENT_IDS))
    if out_of_range:
        raise argparse.ArgumentTypeError(f"stage(s) out of range 1-{len(AGENT_IDS)}: {out_of_range}")
    return [agent_id_for_stage(n) for n in sorted(numbers)]

# Env vars every agent subprocess inherits, mapped from pipeline.performance in
# config.json. Kept as a flat table (name -> (config_key, fallback)) so a new
# knob only needs one line here, matching the source pipeline's convention.
_PERFORMANCE_ENV = {
    # Worker pools can be larger than the request gate. The shared adaptive
    # limiter caps aggregate provider load while allowing enough local work to
    # keep a provider-safe 16-request profile saturated. The shared limiter
    # starts lower and grows only after consecutive healthy calls.
    "KG_LLM_CONCURRENCY": ("llm_concurrency", 16),
    "KG_ORGANIZER_WORKERS": ("document_workers", 32),
    "KG_REASONING_MAX_COMPLETION_TOKENS": ("reasoning_max_completion_tokens", 32768),
    "KG_GLOBAL_LLM_CONCURRENCY_INITIAL": ("global_llm_concurrency_initial", 8),
    "KG_GLOBAL_LLM_CONCURRENCY_MAX": ("global_llm_concurrency_max", 16),
    "KG_GLOBAL_LLM_CONCURRENCY_MIN": ("global_llm_concurrency_min", 1),
    "KG_GLOBAL_LLM_SUCCESS_WINDOW": ("global_llm_success_window", 3),
    # Must cover the LLM watchdog (timeout * SDK attempts + margin), otherwise
    # a slow but still-live request expires and is counted twice by the shared
    # limiter, recreating the overload this limiter is meant to prevent.
    "KG_GLOBAL_LLM_LEASE_SECONDS": ("global_llm_lease_seconds", 900),
    "KG_GLOBAL_LLM_POLL_SECONDS": ("global_llm_poll_seconds", 0.1),
    "KG_LLM_WATCHDOG_MARGIN": ("llm_watchdog_margin", 30),
    "KG_BATCH_CONNECTION_BACKOFF_SECONDS": ("batch_connection_backoff_seconds", 10),
    "KG_READINESS_WORKERS": ("readiness_workers", 80),
    "KG_READINESS_LLM_CONCURRENCY": ("readiness_llm_concurrency", 16),
    "KG_READINESS_RULES_PER_REQUEST": ("readiness_rules_per_request", 8),
    "KG_READINESS_MAX_EVIDENCE_CHARS": ("readiness_max_evidence_chars", 12000),
    "KG_REMEDIATION_WORKERS": ("remediation_workers", 80),
    "KG_REMEDIATION_LLM_CONCURRENCY": ("remediation_llm_concurrency", 16),
    "KG_REMEDIATION_RULES_PER_REQUEST": ("remediation_rules_per_request", 8),
    "KG_REMEDIATION_PAIRS_PER_REQUEST": ("remediation_pairs_per_request", 12),
    "KG_REMEDIATION_MAX_CONFLICT_PAIRS": ("remediation_max_conflict_pairs", 5000),
    "KG_REMEDIATION_MAX_PASSES": ("remediation_max_passes", 3),
    "KG_GROUNDING_WORKERS": ("grounding_workers", 80),
    "KG_GROUNDING_LLM_CONCURRENCY": ("grounding_llm_concurrency", 16),
    "KG_GROUNDING_RULES_PER_REQUEST": ("grounding_rules_per_request", 4),
    "KG_GROUNDING_CLAIMS_PER_REQUEST": ("grounding_claims_per_request", 48),
    "KG_GROUNDING_RELATIONSHIPS_PER_REQUEST": ("grounding_relationships_per_request", 12),
    "KG_ENTITY_EARLY_STOP": ("entity_early_stop", True),
    "KG_ENTITY_MIN_ITERATIONS": ("entity_min_iterations", 2),
}


def _count_business_rules(data: dict) -> int:
    """Count rules in the agent_03 raw or agent_05+ graph shape."""
    if isinstance(data.get("business_rules"), list):
        return len(data["business_rules"])
    total = 0
    for bucket in ("entity_types", "relationships"):
        for entry in (data.get(bucket) or {}).values():
            if isinstance(entry, dict):
                total += len(entry.get("business_rules") or [])
    return total


class ExtractionPipeline:
    def __init__(self, source_dir: Path, domain: str, target_rules: int, max_workers: int | None,
                 skip_optimize: bool, batch_name: str | None, pilot_batch_limit: int | None = None,
                 output: str = "text", provider: str | None = None):
        self.config = get_config(domain=domain, provider=provider)
        self.source_dir = source_dir
        self.domain = domain
        self.target_rules = target_rules
        self.max_workers = max_workers
        self.skip_optimize = skip_optimize
        self.batch_name = batch_name or default_batch_name(source_dir)
        self.pilot_batch_limit = pilot_batch_limit
        self.config.set_batch_name(self.batch_name)

        self.organized_dir = self.config.get_organized_dir()
        self.entities_dir = self.config.get_entity_relationship_dir()
        self.rules_dir = self.config.get_rules_extracted_dir()
        self.merged_dir = self.config.get_rules_with_entities_dir()
        self.optimized_dir = self.config.get_optimized_dir()
        self.dag_dir = self.config.get_dag_dir()
        self.executable_models_dir = self.config.get_executable_models_dir()

        self._limiter_state_file = os.getenv(
            "KG_GLOBAL_LLM_STATE_FILE",
            str(self.config.get_pipeline_base_path() / ".llm_limiter.sqlite3"),
        )
        profile = self.config.get_performance_profile()
        self._perf_env = {}
        self._last_exit_codes: dict[str, int] = {}
        for env_name, (key, fallback) in _PERFORMANCE_ENV.items():
            value = profile.get(key, fallback)
            if isinstance(value, bool):
                value = str(value).lower()
            self._perf_env[env_name] = os.getenv(env_name, str(value))

        # Run-level reporting: metrics aggregation + terminal/JSON rendering.
        # Constructed unconditionally so every real pipeline run gets a
        # polished config panel, live stage table, and final summary; see
        # `_reporting_enabled()` for why bare test doubles (`object.__new__`)
        # that skip __init__ safely no-op instead of touching these.
        run_config: dict = {
            "target_rules": target_rules,
            "model": self.config.get_reasoning_model(),
            "reasoning_effort": self.config.get_reasoning_effort(),
            "provider": self.config.get_model_provider(),
            "workers": max_workers,
            "skip_optimize": skip_optimize,
            "performance": dict(self._perf_env),
            "output_path": str(self.config.get_pipeline_base_path()),
        }
        if pilot_batch_limit is not None:
            run_config["pilot_batch_limit"] = pilot_batch_limit
        self.metrics = RunMetrics(
            batch_name=self.batch_name, domain=domain, source_dir=str(source_dir), config=run_config,
        )
        self.reporter = make_reporter(output)
        self._planned_stage_ids: list[str] = []

    def _env(self) -> dict:
        env = os.environ.copy()
        env.setdefault("KG_GLOBAL_LLM_STATE_FILE", self._limiter_state_file)
        for name, value in self._perf_env.items():
            env.setdefault(name, value)
        env["KG_PROVIDER"] = self.config.get_model_provider()
        env["KG_DOMAIN"] = self.domain
        env["KG_BATCH_NAME"] = self.batch_name
        if self.max_workers:
            env["MAX_WORKERS"] = str(self.max_workers)
        env["TARGET_RULES"] = str(self.target_rules)
        # Unset unless explicitly requested: absence means full coverage
        # (see agents/agent_03_rules_extractor.py::read_text_files_batch).
        # `--target-rules` never controls chunk/batch coverage -- only how
        # many rules agent_03 tries to extract per batch.
        if self.pilot_batch_limit is not None:
            env["PILOT_BATCH_LIMIT"] = str(self.pilot_batch_limit)
        return env

    def _reporting_enabled(self) -> bool:
        """False for test doubles built via ``object.__new__`` that skip ``__init__``."""

        return getattr(self, "reporter", None) is not None and getattr(self, "metrics", None) is not None

    def _operator_message(self, message: str, kind: str = "plain") -> None:
        """Emit a monitoring message through the selected reporter.

        Routing orchestration notices through the reporter keeps ``--output
        json`` machine-readable (the JSON reporter sends these to stderr) and
        gives the text reporter one consistent place to render the operator
        emojis.  Bare test doubles still receive the historical stdout output.
        """

        if self._reporting_enabled():
            self.reporter.log_line(message, kind)
        else:
            print(message)

    def _begin_run(self, stage_ids: list[str], selection_label: str) -> None:
        """Start run-level reporting: populate the stage plan and print the config panel."""

        if not self._reporting_enabled():
            return
        self._planned_stage_ids = list(stage_ids)
        self.metrics.config["stages_selected"] = selection_label
        for stage_id in stage_ids:
            self.metrics.stage(stage_id, stage_label(stage_id))
        self.reporter.run_start(self.metrics)

    def _end_run(self, overall_status: str) -> None:
        """Finish run-level reporting: print the final summary and persist run_metrics.json."""

        if not self._reporting_enabled():
            return
        self.metrics.finish(overall_status=overall_status)
        self.reporter.run_end(self.metrics)
        try:
            self.metrics.write_json(self.config.get_pipeline_base_path() / "run_metrics.json")
        except OSError as exc:
            self.reporter.error(f"Could not write run_metrics.json: {exc}")

    def _final_status(self, *, completed: bool) -> str:
        """Summarize review as review, never as either pass or failure."""
        if not self._reporting_enabled():
            return PASS if completed else FAIL
        statuses = {stage.status for stage in self.metrics.stages.values()}
        if FAIL in statuses:
            return FAIL
        if REVIEW in statuses:
            return REVIEW
        return PASS if completed else FAIL

    def _stage_position(self, agent_id: str) -> tuple[int, int]:
        planned = self._planned_stage_ids or [agent_id]
        try:
            index = planned.index(agent_id) + 1
        except ValueError:
            index = 1
        return index, len(planned)

    def _run(
        self,
        agent_id: str,
        args: list[str],
        extra_env: dict[str, str] | None = None,
    ) -> bool:
        spec = agent_spec(agent_id)
        label = stage_label(agent_id)
        stage = self.metrics.stage(agent_id, label)
        stage.start()
        index, total = self._stage_position(agent_id)
        self.reporter.stage_start(stage, index, total)

        cmd = [sys.executable, str(_ROOT / "agents" / spec.module)] + args
        self.reporter.log_line(f"🛠️ command: $ {' '.join(cmd)}", "plain")
        env = self._env()
        if extra_env:
            env.update(extra_env)
        process = subprocess.Popen(
            cmd, cwd=_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=env,
        )
        for line in process.stdout:
            call = parse_llm_cost_line(line)
            if call is not None:
                # Structured [LLM_COST] marker: aggregate, don't display raw JSON.
                stage.record_llm_call(call)
                continue
            kind = classify_log_line(line)
            if kind in ("warning", "error"):
                stage.observe_log_line(line)
            self.reporter.log_line(line, kind)
        code = process.wait()
        self._last_exit_codes[agent_id] = code
        ok = code == 0
        status = PASS if ok else (REVIEW if code == 3 else FAIL)
        stage.finish(status=status, exit_code=code)
        self.reporter.stage_end(stage, self.metrics)
        return ok

    def run_agent_01(self) -> bool:
        # ``--files`` filters by basename and is therefore only safe for a
        # flat source directory. Benchmark corpora preserve nested split
        # directories; let Agent 01 recursively discover those files instead
        # of passing an empty flat-file selection.
        # Ignore hidden filesystem metadata (notably macOS ``.DS_Store``),
        # which is not a supported document and can otherwise be handed to
        # the single-file filter as if it were source content.
        # Only pass supported top-level documents to the organizer's basename
        # filter.  Benchmark roots commonly contain metadata manifests (for
        # example ``_manifest.json``) alongside nested ``.txt`` documents;
        # treating metadata as a selected source file makes Agent 01 skip the
        # actual recursive corpus entirely.
        supported_suffixes = {
            ".csv", ".docx", ".markdown", ".md", ".pdf", ".text",
            ".tsv", ".txt", ".xls", ".xlsm", ".xlsx",
        }
        files = [
            str(p) for p in sorted(self.source_dir.iterdir())
            if p.is_file()
            and not p.name.startswith(".")
            and p.suffix.lower() in supported_suffixes
        ]
        if not files:
            nested_files = [p for p in self.source_dir.rglob("*") if p.is_file()]
            if not nested_files:
                self._operator_message(f"❌ No files found in {self.source_dir}", "error")
                return False
            return self._run("agent_01", [str(self.source_dir), str(self.organized_dir)])
        return self._run(
            "agent_01",
            [str(self.source_dir), str(self.organized_dir), "--files"]
            + [Path(f).name for f in files],
        )

    def run_agent_02(self) -> bool:
        return self._run("agent_02", [])

    def run_agent_03(self) -> bool:
        # No CLI args: agent_03 reads TARGET_RULES via config.get_target_rules().
        return self._run("agent_03", [])

    def run_agent_04(self) -> bool:
        rules_file = self.rules_dir / "compliance_rules_with_entities.json"
        validation_dir = self.config.get_pipeline_base_path() / output_dir_name("agent_04")
        return self._run(
            "agent_04",
            ["--rules-file", str(rules_file), "--source-dir", str(self.organized_dir),
             "--output-dir", str(validation_dir)],
        )

    def run_agent_05(self) -> bool:
        return self._run("agent_05", [])

    def run_agent_06(self) -> bool:
        if self.skip_optimize:
            if self._reporting_enabled():
                stage = self.metrics.stage("agent_06", stage_label("agent_06"))
                stage.finish(status=SKIPPED, exit_code=None, note="--skip-optimize")
                self.reporter.stage_end(stage, self.metrics)
            else:
                self._operator_message(f"\n⏭️ {stage_label('agent_06')} — SKIPPED (--skip-optimize)")
            return True
        return self._run("agent_06", [])

    def run_agent_07(self, *, reuse_conflicts: bool = False) -> bool:
        extra_env = {"KG_READINESS_SKIP_CONFLICTS": "true"} if reuse_conflicts else None
        return self._run(
            "agent_07", [], extra_env=extra_env
        )

    def run_agent_08(self) -> bool:
        return self._run("agent_08", [])

    def run_agent_09(self) -> bool:
        return self._run("agent_09", [])

    def run_agent_10(self) -> bool:
        return self._run("agent_10", [])

    def run_agent_11(self) -> bool:
        return self._run("agent_11", [])

    def run_agent_12(self) -> bool:
        """Build the UML business information model from the certified graph."""
        return self._run("agent_12", [])

    def run_agent_13(self) -> bool:
        """Generate the self-contained business knowledge report."""
        return self._run("agent_13", [])

    def _review_only_readiness(self) -> bool:
        """Return true when readiness is structurally sound but still review-gated.

        Exit code 3 is a deliberate data-quality signal from agents 07/08, not
        a process failure. We may continue to independent grounding and DAG
        generation in this state, provided all four readiness invariants pass;
        the report and each affected rule retain ``requires_review: true``.
        """
        report_path = self.optimized_dir / "kg_readiness_report.json"
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        invariants = report.get("invariants") or {}
        return bool(invariants) and all(
            isinstance(value, dict) and value.get("pass") is True
            for value in invariants.values()
        ) and bool(report.get("rules_requiring_review"))

    def _readiness_requests_remediation(self) -> bool:
        """Return whether Agent 07 produced findings Agent 08 may repair.

        Review items with passing invariants are the normal remediation path.
        A schema-only invariant failure may also be repairable after contract
        normalization. Corpus, naming, or referential-integrity failures are
        not rule-evidence problems and must never be waved through merely
        because the same report also contains review-required rules.
        """
        report_path = self.optimized_dir / "kg_readiness_report.json"
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not report.get("rules_requiring_review"):
            return False
        invariants = report.get("invariants")
        if not isinstance(invariants, dict) or not invariants:
            return False
        failed = {
            str(name)
            for name, result in invariants.items()
            if not isinstance(result, dict) or result.get("pass") is not True
        }
        return not failed or failed <= {"schema_consistency"}

    def _review_only_grounding(self) -> bool:
        """Return true for a complete, fail-closed grounding review.

        Agent 09 uses exit code 3 when claims are contradicted or lack
        evidence. That is a data-quality signal, not an orchestration crash,
        when every requested response was returned exactly once. In that
        state the final DAG stage can still generate a fully covered DAG while retaining
        the grounding failures on each rule.
        """
        report_path = self.optimized_dir / "kg_grounding_report.json"
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return (
            report.get("pass") is False
            and report.get("total_rules", 0) > 0
            and report.get("claim_coverage_percent") == 100.0
            and report.get("response_claims_returned") == report.get("model_claims")
            and report.get("missing_claim_responses") == 0
            and report.get("duplicate_claim_responses") == 0
            and report.get("unexpected_claim_responses") == 0
        )

    def run_all(self) -> bool:
        self._begin_run(list(AGENT_IDS), f"full pipeline ({len(AGENT_IDS)} stages)")
        ok = self._run_all_stages()
        self._end_run(overall_status=self._final_status(completed=ok))
        return ok

    def _run_all_stages(self) -> bool:
        start = datetime.now()
        if not self.run_agent_01():
            return False
        if not self.run_agent_02():
            return False
        if not self.run_agent_03():
            return False
        self.run_agent_04()  # advisory; never blocks the pipeline
        if not self.run_agent_05():
            return False
        if not self.run_agent_06():
            return False

        if not self.skip_optimize:
            if not self.run_agent_07():
                # Exit 3 is Agent 07's review/remediation signal. Exit 2 is
                # also remediable, but only when the freshly written report
                # proves schema_consistency is the sole failed invariant.
                # Runtime/configuration errors (exit 1) and non-schema
                # invariant failures must never use a possibly stale report.
                if (
                    self._last_exit_codes.get("agent_07") not in {2, 3}
                    or not self._readiness_requests_remediation()
                ):
                    self._operator_message("\n🛑 STOPPED: agent_07 failed without a valid remediation signal; agent_08 was not started.", "error")
                    return False
                self._operator_message("\n🩹 agent_07 requested focused remediation → running agent_08")
                if not self.run_agent_08():
                    if self._last_exit_codes.get("agent_08") != 3:
                        return False
                    self._operator_message("🔎 agent_08 retained review-required rules; continuing fail-closed", "warning")
                if not self.run_agent_07(reuse_conflicts=True):
                    if self._last_exit_codes.get("agent_07") != 3 or not self._review_only_readiness():
                        self._operator_message("\n🛑 STOPPED: readiness invariants still failing after remediation.", "error")
                        return False
                    self._operator_message("🔎 readiness remains review-gated; preserving review flags and continuing", "warning")

        if not self.run_agent_09():
            if self._last_exit_codes.get("agent_09") != 3 or not self._review_only_grounding():
                self._operator_message("\n🛑 STOPPED: agent_09 grounding certification failed.", "error")
                return False
            self._operator_message("🔎 grounding remains review-gated with complete response coverage; continuing fail-closed", "warning")

        if not self.run_agent_10():
            return False
        if not self.run_agent_11():
            return False
        if not self.run_agent_12():
            return False
        if not self.run_agent_13():
            return False

        elapsed = datetime.now() - start
        self._operator_message("\n🎉 PIPELINE COMPLETE in " + str(elapsed))
        self._operator_message(f"📦 optimized graph: {self.optimized_dir / 'optimized_compliance_knowledge_graph.json'}")
        self._operator_message(f"🕸️ dependency DAGs: {self.dag_dir / 'dependency_dags.json'}")
        self._operator_message(f"⚙️ executable models: {getattr(self, 'executable_models_dir', self.dag_dir)}")
        return True

    def run_agent(self, agent_id: str) -> bool:
        dispatch = {
            "agent_01": self.run_agent_01, "agent_02": self.run_agent_02,
            "agent_03": self.run_agent_03, "agent_04": self.run_agent_04,
            "agent_05": self.run_agent_05, "agent_06": self.run_agent_06,
            "agent_07": self.run_agent_07, "agent_08": self.run_agent_08,
            "agent_09": self.run_agent_09, "agent_10": self.run_agent_10,
            "agent_11": self.run_agent_11, "agent_12": self.run_agent_12,
            "agent_13": self.run_agent_13,
        }
        if agent_id not in dispatch:
            self._operator_message(f"❌ Invalid agent: {agent_id}. Valid: {', '.join(AGENT_IDS)}", "error")
            return False
        return dispatch[agent_id]()

    def run_stages(self, stage_ids: list[str], *, keep_going: bool = False,
                    selection_label: str | None = None) -> bool:
        """Run one or more canonical agents, in order.

        The single-stage selectors (``--agent``/``--stage``/``--step``) and the
        multi-stage ``--stages`` selector all funnel through here so every CLI
        invocation gets the same config panel / stage table / final summary.
        By default, stops at the first failing stage; pass ``keep_going=True``
        (``--keep-going``) to run every selected stage regardless of earlier
        failures and report the aggregate result.
        """

        if selection_label is None:
            selection_label = ", ".join(stage_ids)
        planned_stage_ids = list(stage_ids)
        if "agent_08" in stage_ids:
            remediation_index = stage_ids.index("agent_08")
            has_downstream = any(
                selected in stage_ids[remediation_index + 1:]
                for selected in ("agent_09", "agent_10", "agent_11", "agent_12", "agent_13")
            )
            if has_downstream and "agent_07" not in stage_ids[:remediation_index]:
                # A resume beginning at Agent 08 automatically rechecks Agent
                # 07 before grounding. Put that real execution in the plan up
                # front so its row and selected position are not appended as
                # an unexplained "01/N" stage midway through the run.
                planned_stage_ids.insert(remediation_index + 1, "agent_07")
                selection_label += " + automatic agent_07 recheck"
        self._begin_run(planned_stage_ids, selection_label)
        overall_ok = True
        readiness_pending = False
        for index, agent_id in enumerate(stage_ids):
            ok = self.run_agent(agent_id)

            if agent_id == "agent_07" and not ok:
                has_remediator = "agent_08" in stage_ids[index + 1:]
                if (
                    has_remediator
                    and self._last_exit_codes.get("agent_07") in {2, 3}
                    and self._readiness_requests_remediation()
                ):
                    readiness_pending = True
                    self._operator_message("\n🩹 agent_07 requested focused remediation → continuing to selected agent_08")
                    continue
                if (
                    self._last_exit_codes.get("agent_07") == 3
                    and self._review_only_readiness()
                ):
                    self._operator_message("🔎 readiness is structurally valid and remains review-gated", "warning")
                    continue

            if agent_id == "agent_08":
                remediation_review_only = (
                    not ok and self._last_exit_codes.get("agent_08") == 3
                )
                if not ok and not remediation_review_only:
                    overall_ok = False
                    if not keep_going:
                        break
                    continue

                # A selective resume beginning at Agent 08 must perform the
                # same readiness recheck as a full run before grounding.
                should_recheck = readiness_pending or "agent_07" not in stage_ids[:index]
                if should_recheck and any(
                    selected in stage_ids[index + 1:]
                    for selected in ("agent_09", "agent_10", "agent_11", "agent_12", "agent_13")
                ):
                    readiness_pending = False
                    recheck_ok = self.run_agent_07(reuse_conflicts=True)
                    if not recheck_ok and not (
                        self._last_exit_codes.get("agent_07") == 3
                        and self._review_only_readiness()
                    ):
                        overall_ok = False
                        if not keep_going:
                            break
                    elif not recheck_ok:
                        self._operator_message("🔎 readiness remains review-gated; preserving review flags and continuing", "warning")
                continue

            if agent_id == "agent_09" and not ok:
                if (
                    self._last_exit_codes.get("agent_09") == 3
                    and self._review_only_grounding()
                ):
                    self._operator_message("🔎 grounding remains review-gated with complete response coverage; continuing fail-closed", "warning")
                    continue

            if not ok:
                overall_ok = False
                if not keep_going:
                    break
        self._end_run(overall_status=self._final_status(completed=overall_ok))
        return overall_ok

    def run_step(self, step: str) -> bool:
        """Run a legacy selector without changing its historical meaning."""

        if step not in LEGACY_STEP_ALIASES:
            valid = ", ".join(LEGACY_STEP_ALIASES)
            self._operator_message(
                f"❌ Invalid legacy step: {step}. Valid legacy steps: {valid}; use --stage or --agent",
                "error",
            )
            return False
        agent_id = LEGACY_STEP_ALIASES[step]
        self._operator_message(f"🧭 Legacy --step {step} maps to {stage_label(agent_id)}")
        return self.run_stages([agent_id], selection_label=f"legacy step {step} ({stage_label(agent_id)})")

    def run_stage(self, stage: str) -> bool:
        """Run one canonical, one-based pipeline stage."""

        try:
            agent_id = agent_id_for_stage(stage)
        except ValueError as exc:
            self._operator_message(f"❌ {exc}", "error")
            return False
        return self.run_stages([agent_id], selection_label=f"single stage ({stage_label(agent_id)})")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", required=True, help="Directory of source documents under compliance-files/")
    parser.add_argument("--domain", required=True, choices=DOMAINS)
    parser.add_argument(
        "--batch-name", default=None,
        help="Output folder name under pipeline-output/. Default: "
             "<source-basename>-run-YYYY-MM-DD-HH-MM in US Pacific time "
             "(PST/PDT); pass an explicit name to resume a prior run.",
    )
    parser.add_argument("--target-rules", type=int, default=30, help="Target business rules agent_03 tries to extract per batch (default: 30). Does NOT bound chunk/batch coverage -- see --pilot-batch-limit for that.")
    parser.add_argument("--pilot-batch-limit", type=int, default=None, help="Cap the number of word-balanced batches agent_03 processes, for a cheap smoke run. Omit for full coverage (default): every organized chunk is read whole and every batch is processed. A capped run is never corpus coverage.")
    parser.add_argument("--workers", type=int, default=None, help="Local scheduling workers (default: config.json pipeline.max_workers)")
    parser.add_argument("--provider", choices=sorted(MODEL_PROVIDERS), default=None,
                         help="Model provider for every agent subprocess this run (default: KG_PROVIDER env var, "
                              "then config.json's llm.provider, then 'openai'). Requires the matching API key "
                              "(OPENAI_API_KEY or ANTHROPIC_API_KEY) and, for anthropic, the model names under "
                              "anthropic.models.* in config.json to actually be Claude models.")
    parser.add_argument("--skip-optimize", action="store_true", help="Skip agents agent_06 through agent_08 (optimization, readiness, remediation); independent agent_09 grounding still runs")
    parser.add_argument("--keep-going", action="store_true", help="With --stages, run every selected stage even after an earlier one fails, instead of stopping at the first failure")
    parser.add_argument("--output", choices=["text", "json"], default="text",
                         help="'text' (default): polished interactive terminal display. "
                              "'json': line-delimited JSON events on stdout for automation/scripting "
                              "(run_start/stage_start/stage_end/run_end/error); raw subprocess log lines "
                              "go to stderr instead so stdout stays machine-parseable.")
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--agent", choices=list(AGENT_IDS), help="Run one canonical agent only (for example: agent_07)")
    selector.add_argument("--stage", type=_parse_stage_arg, choices=list(CANONICAL_STAGE_NUMBERS), help="Run one canonical pipeline stage (1–13; Stage 07 maps to agent_07 and Stage 13 maps to agent_13)")
    selector.add_argument("--step", choices=list(LEGACY_STEP_ALIASES), help="Deprecated legacy selector; use --stage or --agent (fractional aliases retain historical meanings)")
    selector.add_argument("--stages", type=_parse_stages_arg, metavar="RANGE",
                           help="Run multiple canonical stages in order, e.g. '3-6', '3,5,7', or '3-6,9,11' "
                                "(mutually exclusive with --agent/--stage/--step; see --keep-going)")
    args = parser.parse_args()

    source_dir = Path(args.dir)
    if not source_dir.is_absolute():
        source_dir = _ROOT / "compliance-files" / args.dir
    if not source_dir.exists():
        message = f"Source directory not found: {source_dir}"
        if args.output == "json":
            print(json.dumps({"event": "error", "message": message}, ensure_ascii=False), flush=True)
        else:
            print(f"❌ {message}")
        sys.exit(1)

    pipeline = ExtractionPipeline(
        source_dir=source_dir, domain=args.domain, target_rules=args.target_rules,
        max_workers=args.workers, skip_optimize=args.skip_optimize, batch_name=args.batch_name,
        pilot_batch_limit=args.pilot_batch_limit, output=args.output, provider=args.provider,
    )
    if args.agent:
        ok = pipeline.run_stages([args.agent], selection_label=f"single agent ({stage_label(args.agent)})")
    elif args.stage:
        ok = pipeline.run_stage(args.stage)
    elif args.step:
        ok = pipeline.run_step(args.step)
    elif args.stages:
        numbers = ", ".join(agent_id.rsplit("_", 1)[-1] for agent_id in args.stages)
        ok = pipeline.run_stages(
            args.stages, keep_going=args.keep_going,
            selection_label=f"{len(args.stages)} selected stages (agent_{{{numbers}}})",
        )
    else:
        ok = pipeline.run_all()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
