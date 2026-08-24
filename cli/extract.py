#!/usr/bin/env python3
"""
Extraction orchestrator: compliance documents -> a grounding-certified,
DMN/BPMN-ready knowledge graph.

This is a lean, single-batch orchestrator by design (see README.md "Scope").
It runs ten stages in order, streaming each agent subprocess's output:

  1    Document Organizer         chunk raw documents
  2    Entity Extractor           entities & relationships
  3    Rules Extractor            business rules (v2 contract)
  3.5  Rule Validator             advisory quality pass (non-blocking)
  4    Rules+Entities Merger      first complete knowledge graph
  5    KG Optimizer               dedup + dependency analysis
  5.5  Executable Readiness       four-invariant gate; DMN/BPMN projection
  5.6  Readiness Remediator       focused fix-up (only if 5.5 requests it)
  5.7  Grounding Verifier         independent claim-level certification
  6    Dependency DAG Generator   100%-coverage DAG partition of the graph

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

from utils.config import get_config  # noqa: E402

DOMAINS = ["nda_confidentiality", "privacy_policy", "mobile_app_privacy", "commercial_contracts"]

# Env vars every agent subprocess inherits, mapped from pipeline.performance in
# config.json. Kept as a flat table (name -> (config_key, fallback)) so a new
# knob only needs one line here, matching the source pipeline's convention.
_PERFORMANCE_ENV = {
    "KG_LLM_CONCURRENCY": ("llm_concurrency", 16),
    "KG_REASONING_MAX_COMPLETION_TOKENS": ("reasoning_max_completion_tokens", 32768),
    "KG_GLOBAL_LLM_CONCURRENCY_INITIAL": ("global_llm_concurrency_initial", 12),
    "KG_GLOBAL_LLM_CONCURRENCY_MAX": ("global_llm_concurrency_max", 32),
    "KG_GLOBAL_LLM_CONCURRENCY_MIN": ("global_llm_concurrency_min", 1),
    "KG_GLOBAL_LLM_SUCCESS_WINDOW": ("global_llm_success_window", 3),
    "KG_GLOBAL_LLM_LEASE_SECONDS": ("global_llm_lease_seconds", 900),
    "KG_GLOBAL_LLM_POLL_SECONDS": ("global_llm_poll_seconds", 0.1),
    "KG_READINESS_WORKERS": ("readiness_workers", 40),
    "KG_READINESS_LLM_CONCURRENCY": ("readiness_llm_concurrency", 16),
    "KG_READINESS_RULES_PER_REQUEST": ("readiness_rules_per_request", 4),
    "KG_REMEDIATION_WORKERS": ("remediation_workers", 40),
    "KG_REMEDIATION_LLM_CONCURRENCY": ("remediation_llm_concurrency", 16),
    "KG_REMEDIATION_RULES_PER_REQUEST": ("remediation_rules_per_request", 4),
    "KG_REMEDIATION_PAIRS_PER_REQUEST": ("remediation_pairs_per_request", 12),
    "KG_REMEDIATION_MAX_PASSES": ("remediation_max_passes", 3),
    "KG_GROUNDING_WORKERS": ("grounding_workers", 40),
    "KG_GROUNDING_LLM_CONCURRENCY": ("grounding_llm_concurrency", 24),
    "KG_GROUNDING_RULES_PER_REQUEST": ("grounding_rules_per_request", 4),
    "KG_GROUNDING_CLAIMS_PER_REQUEST": ("grounding_claims_per_request", 48),
    "KG_GROUNDING_RELATIONSHIPS_PER_REQUEST": ("grounding_relationships_per_request", 12),
    "KG_ENTITY_EARLY_STOP": ("entity_early_stop", True),
    "KG_ENTITY_MIN_ITERATIONS": ("entity_min_iterations", 2),
}


def _count_business_rules(data: dict) -> int:
    """Count rules whether the graph keeps them flat (Agent 4+) or nested
    under entity_types/relationships (Agent 3's raw output)."""
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
                 skip_optimize: bool, batch_name: str | None):
        self.config = get_config(domain=domain)
        self.source_dir = source_dir
        self.domain = domain
        self.target_rules = target_rules
        self.max_workers = max_workers
        self.skip_optimize = skip_optimize
        self.batch_name = batch_name or source_dir.name
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
        return env

    def _run(self, step: str, label: str, script: str, args: list[str]) -> bool:
        print("\n" + "=" * 80)
        print(f"STEP {step}: {label}")
        print("=" * 80)
        cmd = [sys.executable, str(_ROOT / "agents" / script)] + args
        print(f"$ {' '.join(cmd)}\n", flush=True)
        process = subprocess.Popen(
            cmd, cwd=_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=self._env(),
        )
        for line in process.stdout:
            print(line, end="", flush=True)
        code = process.wait()
        ok = code == 0
        print(f"\n{'PASS' if ok else 'FAIL'} STEP {step}: {label} (exit {code})")
        return ok

    def step1(self) -> bool:
        files = [str(p) for p in sorted(self.source_dir.iterdir()) if p.is_file()]
        if not files:
            print(f"No files found in {self.source_dir}")
            return False
        return self._run("1", "Document Organizer", "agent_01_document_organizer.py",
                          [str(self.source_dir), str(self.organized_dir), "--files"] + [Path(f).name for f in files])

    def step2(self) -> bool:
        return self._run("2", "Entity Extractor", "agent_02_entity_extractor.py", [])

    def step3(self) -> bool:
        # No CLI args: agent_3 reads TARGET_RULES purely via config.get_target_rules().
        return self._run("3", "Rules Extractor", "agent_03_rules_extractor.py", [])

    def step3_5(self) -> bool:
        rules_file = self.rules_dir / "compliance_rules_with_entities.json"
        validation_dir = self.config.get_pipeline_base_path() / "agent-3-5-validation"
        return self._run("3.5", "Rule Validator", "agent_04_rule_validator.py",
                          ["--rules-file", str(rules_file), "--source-dir", str(self.organized_dir),
                           "--output-dir", str(validation_dir)])

    def step4(self) -> bool:
        return self._run("4", "Rules+Entities Merger", "agent_05_rules_with_entities_merger.py", [])

    def step5(self) -> bool:
        if self.skip_optimize:
            print("\nSTEP 5: Knowledge Graph Optimizer -- SKIPPED (--skip-optimize)")
            return True
        return self._run("5", "KG Optimizer", "agent_06_knowledge_graph_optimizer.py", [])

    def step5_5(self) -> bool:
        return self._run("5.5", "Executable Readiness", "agent_07_executable_readiness.py", [])

    def step5_6(self) -> bool:
        return self._run("5.6", "Readiness Remediator", "agent_08_readiness_remediator.py", [])

    def step5_7(self) -> bool:
        return self._run("5.7", "Grounding Verifier", "agent_09_grounding_verifier.py", [])

    def step6(self) -> bool:
        return self._run("6", "Dependency DAG Generator", "agent_10_dag_generator.py", [])

    def run_all(self) -> bool:
        start = datetime.now()
        if not self.step1():
            return False
        if not self.step2():
            return False
        if not self.step3():
            return False
        self.step3_5()  # advisory; never blocks the pipeline
        if not self.step4():
            return False
        if not self.step5():
            return False

        if not self.skip_optimize:
            if not self.step5_5():
                # 5.5 exits nonzero either on a hard invariant failure
                # (unrecoverable here) or because rules need 5.6 remediation.
                report_path = self.optimized_dir / "kg_readiness_report.json"
                needs_remediation = False
                if report_path.exists():
                    try:
                        report = json.loads(report_path.read_text())
                        needs_remediation = bool(report.get("rules_requiring_review"))
                    except (OSError, json.JSONDecodeError):
                        pass
                if not needs_remediation:
                    print("\nSTOPPED: Agent 5.5 invariant failure (not remediable by 5.6).")
                    return False
                print("\nAgent 5.5 requested focused remediation -> running Step 5.6")
                if not self.step5_6():
                    return False
                if not self.step5_5():
                    print("\nSTOPPED: readiness still failing after remediation.")
                    return False

            if not self.step5_7():
                print("\nSTOPPED: Agent 5.7 grounding certification failed.")
                return False

        if not self.step6():
            return False

        elapsed = datetime.now() - start
        print("\n" + "=" * 80)
        print(f"COMPLETE in {elapsed}")
        print(f"  optimized graph: {self.optimized_dir / 'optimized_compliance_knowledge_graph.json'}")
        print(f"  dependency DAGs: {self.dag_dir / 'dependency_dags.json'}")
        print("=" * 80)
        return True

    def run_step(self, step: str) -> bool:
        dispatch = {
            "1": self.step1, "2": self.step2, "3": self.step3, "3.5": self.step3_5,
            "4": self.step4, "5": self.step5, "5.5": self.step5_5, "5.6": self.step5_6,
            "5.7": self.step5_7, "6": self.step6,
        }
        if step not in dispatch:
            print(f"Invalid step: {step}. Valid: {', '.join(dispatch)}")
            return False
        return dispatch[step]()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", required=True, help="Directory of source documents under compliance-files/")
    parser.add_argument("--domain", required=True, choices=DOMAINS)
    parser.add_argument("--batch-name", default=None, help="Output folder name under pipeline-output/ (default: --dir's basename)")
    parser.add_argument("--target-rules", type=int, default=30, help="Target business rules to extract (default: 30 -- tuned for small pilot batches, not a 300+-document corpus)")
    parser.add_argument("--workers", type=int, default=None, help="Local scheduling workers (default: config.json pipeline.max_workers)")
    parser.add_argument("--skip-optimize", action="store_true", help="Skip steps 5/5.5/5.6/5.7 (dedup, readiness, remediation, grounding)")
    parser.add_argument("--step", choices=["1", "2", "3", "3.5", "4", "5", "5.5", "5.6", "5.7", "6"], help="Run a single step only")
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
    )
    ok = pipeline.run_step(args.step) if args.step else pipeline.run_all()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
