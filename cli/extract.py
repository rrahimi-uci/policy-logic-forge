#!/usr/bin/env python3
"""
Extraction orchestrator: compliance documents -> a grounding-certified,
DMN/BPMN-ready knowledge graph.

This is a lean, single-batch orchestrator by design (see README.md "Scope").
It runs the ten canonical agents in order, streaming each subprocess's output:

  agent_01  Document Organizer       chunk raw documents
  agent_02  Entity Extractor         entities & relationships
  agent_03  Rules Extractor           business rules (v2 contract)
  agent_04  Rule Validator             advisory quality pass (non-blocking)
  agent_05  Rules+Entities Merger      first complete knowledge graph
  agent_06  KG Optimizer               dedup + dependency analysis
  agent_07  Executable Readiness       four-invariant gate; DMN/BPMN projection
  agent_08  Readiness Remediator       focused fix-up (only if agent_07 requests it)
  agent_09  Grounding Verifier         independent claim-level certification
  agent_10  Dependency DAG Generator   100%-coverage DAG partition of the graph

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

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from utils.agent_names import AGENT_IDS, agent_spec, output_dir_name  # noqa: E402
from utils.config import get_config  # noqa: E402

DOMAINS = [
    "nda_confidentiality", "privacy_policy", "mobile_app_privacy", "commercial_contracts",
    "deonticbench", "mortgage",
]

# Env vars every agent subprocess inherits, mapped from pipeline.performance in
# config.json. Kept as a flat table (name -> (config_key, fallback)) so a new
# knob only needs one line here, matching the source pipeline's convention.
_PERFORMANCE_ENV = {
    "KG_LLM_CONCURRENCY": ("llm_concurrency", 16),
    # Agent 01 has a separate document-level worker pool.  Propagate the
    # configured value instead of accidentally using the request concurrency
    # (which can overload the provider on large corpora).
    "KG_ORGANIZER_WORKERS": ("document_workers", 6),
    "KG_REASONING_MAX_COMPLETION_TOKENS": ("reasoning_max_completion_tokens", 24576),
    "KG_GLOBAL_LLM_CONCURRENCY_INITIAL": ("global_llm_concurrency_initial", 8),
    "KG_GLOBAL_LLM_CONCURRENCY_MAX": ("global_llm_concurrency_max", 16),
    "KG_GLOBAL_LLM_CONCURRENCY_MIN": ("global_llm_concurrency_min", 1),
    "KG_GLOBAL_LLM_SUCCESS_WINDOW": ("global_llm_success_window", 3),
    "KG_GLOBAL_LLM_LEASE_SECONDS": ("global_llm_lease_seconds", 300),
    "KG_GLOBAL_LLM_POLL_SECONDS": ("global_llm_poll_seconds", 0.1),
    "KG_LLM_WATCHDOG_MARGIN": ("llm_watchdog_margin", 30),
    "KG_BATCH_CONNECTION_BACKOFF_SECONDS": ("batch_connection_backoff_seconds", 10),
    "KG_READINESS_WORKERS": ("readiness_workers", 40),
    "KG_READINESS_LLM_CONCURRENCY": ("readiness_llm_concurrency", 16),
    "KG_READINESS_RULES_PER_REQUEST": ("readiness_rules_per_request", 8),
    "KG_READINESS_MAX_EVIDENCE_CHARS": ("readiness_max_evidence_chars", 12000),
    "KG_REMEDIATION_WORKERS": ("remediation_workers", 40),
    "KG_REMEDIATION_LLM_CONCURRENCY": ("remediation_llm_concurrency", 4),
    "KG_REMEDIATION_RULES_PER_REQUEST": ("remediation_rules_per_request", 8),
    "KG_REMEDIATION_PAIRS_PER_REQUEST": ("remediation_pairs_per_request", 12),
    "KG_REMEDIATION_MAX_CONFLICT_PAIRS": ("remediation_max_conflict_pairs", 5000),
    "KG_REMEDIATION_MAX_PASSES": ("remediation_max_passes", 3),
    "KG_GROUNDING_WORKERS": ("grounding_workers", 40),
    "KG_GROUNDING_LLM_CONCURRENCY": ("grounding_llm_concurrency", 8),
    "KG_GROUNDING_RULES_PER_REQUEST": ("grounding_rules_per_request", 4),
    "KG_GROUNDING_CLAIMS_PER_REQUEST": ("grounding_claims_per_request", 48),
    "KG_GROUNDING_RELATIONSHIPS_PER_REQUEST": ("grounding_relationships_per_request", 48),
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
                 skip_optimize: bool, batch_name: str | None, pilot_batch_limit: int | None = None):
        self.config = get_config(domain=domain)
        self.source_dir = source_dir
        self.domain = domain
        self.target_rules = target_rules
        self.max_workers = max_workers
        self.skip_optimize = skip_optimize
        self.batch_name = batch_name or source_dir.name
        self.pilot_batch_limit = pilot_batch_limit
        self.config.set_batch_name(self.batch_name)

        self.organized_dir = self.config.get_organized_dir()
        self.entities_dir = self.config.get_entity_relationship_dir()
        self.rules_dir = self.config.get_rules_extracted_dir()
        self.merged_dir = self.config.get_rules_with_entities_dir()
        self.optimized_dir = self.config.get_optimized_dir()
        self.dag_dir = self.config.get_dag_dir()

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

        print("=" * 80)
        print(f"compliance-to-code: extraction pipeline")
        print(f"  domain:       {domain}")
        print(f"  source:       {source_dir}")
        print(f"  batch name:   {self.batch_name}")
        print(f"  target rules: {target_rules}")
        if pilot_batch_limit is not None:
            print(f"  ⚠ pilot batch limit: {pilot_batch_limit} (NOT a full-coverage run)")
        print(f"  output:       {self.config.get_pipeline_base_path()}")
        print("=" * 80)

    def _env(self) -> dict:
        env = os.environ.copy()
        env.setdefault("KG_GLOBAL_LLM_STATE_FILE", self._limiter_state_file)
        for name, value in self._perf_env.items():
            env.setdefault(name, value)
        env["KG_PROVIDER"] = "openai"
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

    def _run(
        self,
        agent_id: str,
        args: list[str],
        extra_env: dict[str, str] | None = None,
    ) -> bool:
        spec = agent_spec(agent_id)
        print("\n" + "=" * 80)
        print(f"{agent_id}: {spec.role}")
        print("=" * 80)
        cmd = [sys.executable, str(_ROOT / "agents" / spec.module)] + args
        print(f"$ {' '.join(cmd)}\n", flush=True)
        env = self._env()
        if extra_env:
            env.update(extra_env)
        process = subprocess.Popen(
            cmd, cwd=_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=env,
        )
        for line in process.stdout:
            print(line, end="", flush=True)
        code = process.wait()
        self._last_exit_codes[agent_id] = code
        ok = code == 0
        print(f"\n{'PASS' if ok else 'FAIL'} {agent_id}: {spec.role} (exit {code})")
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
                print(f"No files found in {self.source_dir}")
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
            print("\nagent_06: Knowledge Graph Optimizer -- SKIPPED (--skip-optimize)")
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
                # agent_07 exits nonzero either on a hard invariant failure
                # (unrecoverable here) or because rules need agent_08 remediation.
                report_path = self.optimized_dir / "kg_readiness_report.json"
                needs_remediation = False
                if report_path.exists():
                    try:
                        report = json.loads(report_path.read_text())
                        needs_remediation = bool(report.get("rules_requiring_review"))
                    except (OSError, json.JSONDecodeError):
                        pass
                if not needs_remediation:
                    print("\nSTOPPED: agent_07 invariant failure (not remediable by agent_08).")
                    return False
                print("\nagent_07 requested focused remediation -> running agent_08")
                if not self.run_agent_08():
                    if self._last_exit_codes.get("agent_08") != 3:
                        return False
                    print("agent_08 retained review-required rules; continuing fail-closed")
                if not self.run_agent_07(reuse_conflicts=True):
                    if self._last_exit_codes.get("agent_07") != 3 or not self._review_only_readiness():
                        print("\nSTOPPED: readiness invariants still failing after remediation.")
                        return False
                    print("readiness remains review-gated; preserving review flags and continuing")

        if not self.run_agent_09():
            if self._last_exit_codes.get("agent_09") != 3 or not self._review_only_grounding():
                print("\nSTOPPED: agent_09 grounding certification failed.")
                return False
            print("grounding remains review-gated with complete response coverage; continuing fail-closed")

        if not self.run_agent_10():
            return False

        elapsed = datetime.now() - start
        print("\n" + "=" * 80)
        print(f"COMPLETE in {elapsed}")
        print(f"  optimized graph: {self.optimized_dir / 'optimized_compliance_knowledge_graph.json'}")
        print(f"  dependency DAGs: {self.dag_dir / 'dependency_dags.json'}")
        print("=" * 80)
        return True

    def run_agent(self, agent_id: str) -> bool:
        dispatch = {
            "agent_01": self.run_agent_01, "agent_02": self.run_agent_02,
            "agent_03": self.run_agent_03, "agent_04": self.run_agent_04,
            "agent_05": self.run_agent_05, "agent_06": self.run_agent_06,
            "agent_07": self.run_agent_07, "agent_08": self.run_agent_08,
            "agent_09": self.run_agent_09, "agent_10": self.run_agent_10,
        }
        if agent_id not in dispatch:
            print(f"Invalid agent: {agent_id}. Valid: {', '.join(AGENT_IDS)}")
            return False
        return dispatch[agent_id]()

    def run_step(self, step: str) -> bool:
        """Run a legacy numeric stage selector for backwards compatibility."""

        legacy_steps = {
            "1": "agent_01", "2": "agent_02", "3": "agent_03", "3.5": "agent_04",
            "4": "agent_05", "5": "agent_06", "5.5": "agent_07", "5.6": "agent_08",
            "5.7": "agent_09", "6": "agent_10",
        }
        if step not in legacy_steps:
            print(f"Invalid step: {step}. Valid agents: {', '.join(AGENT_IDS)}")
            return False
        return self.run_agent(legacy_steps[step])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", required=True, help="Directory of source documents under compliance-files/")
    parser.add_argument("--domain", required=True, choices=DOMAINS)
    parser.add_argument("--batch-name", default=None, help="Output folder name under pipeline-output/ (default: --dir's basename)")
    parser.add_argument("--target-rules", type=int, default=30, help="Target business rules agent_03 tries to extract per batch (default: 30). Does NOT bound chunk/batch coverage -- see --pilot-batch-limit for that.")
    parser.add_argument("--pilot-batch-limit", type=int, default=None, help="Cap the number of word-balanced batches agent_03 processes, for a cheap smoke run. Omit for full coverage (default): every organized chunk is read whole and every batch is processed. A capped run is never corpus coverage.")
    parser.add_argument("--workers", type=int, default=None, help="Local scheduling workers (default: config.json pipeline.max_workers)")
    parser.add_argument("--skip-optimize", action="store_true", help="Skip agents agent_06 through agent_09 (optimization, readiness, remediation, grounding)")
    parser.add_argument("--agent", choices=list(AGENT_IDS), help="Run one canonical agent only")
    parser.add_argument("--step", choices=["1", "2", "3", "3.5", "4", "5", "5.5", "5.6", "5.7", "6"], help="Deprecated numeric stage selector; use --agent")
    args = parser.parse_args()

    source_dir = Path(args.dir)
    if not source_dir.is_absolute():
        source_dir = _ROOT / "compliance-files" / args.dir
    if not source_dir.exists():
        print(f"Source directory not found: {source_dir}")
        sys.exit(1)

    pipeline = ExtractionPipeline(
        source_dir=source_dir, domain=args.domain, target_rules=args.target_rules,
        max_workers=args.workers, skip_optimize=args.skip_optimize, batch_name=args.batch_name,
        pilot_batch_limit=args.pilot_batch_limit,
    )
    if args.agent and args.step:
        parser.error("--agent and --step cannot be used together")
    ok = pipeline.run_agent(args.agent) if args.agent else pipeline.run_step(args.step) if args.step else pipeline.run_all()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
