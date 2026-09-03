import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from cli.extract import (
    DOMAINS,
    ExtractionPipeline,
    _PERFORMANCE_ENV,
    _parse_stage_arg,
    _parse_stages_arg,
    default_batch_name,
)
from utils.config import Config


def test_default_batch_name_uses_source_basename_and_pacific_timestamp():
    pacific = ZoneInfo("America/Los_Angeles")
    now = datetime(2026, 9, 1, 9, 5, tzinfo=pacific)
    assert default_batch_name(Path("/source/mortgage"), now=now) == "mortgage-run-2026-09-01-09-05"


def test_default_batch_name_converts_aware_time_to_pacific():
    utc = ZoneInfo("UTC")
    now = datetime(2026, 1, 15, 20, 7, tzinfo=utc)
    assert default_batch_name(Path("/source/nda_confidentiality"), now=now) == "nda_confidentiality-run-2026-01-15-12-07"


@pytest.mark.parametrize("domain", DOMAINS)
def test_default_batch_name_is_domain_independent(domain):
    pacific = ZoneInfo("America/Los_Angeles")
    now = datetime(2026, 9, 1, 9, 5, tzinfo=pacific)
    assert default_batch_name(Path(f"/source/{domain}"), now=now) == (
        f"{domain}-run-2026-09-01-09-05"
    )


def test_stage_argument_accepts_display_number_with_or_without_zero_padding():
    assert _parse_stage_arg("7") == "7"
    assert _parse_stage_arg("07") == "7"


def test_stages_argument_accepts_a_range():
    assert _parse_stages_arg("3-6") == ["agent_03", "agent_04", "agent_05", "agent_06"]


def test_stages_argument_accepts_a_comma_list():
    assert _parse_stages_arg("3,5,7") == ["agent_03", "agent_05", "agent_07"]


def test_stages_argument_accepts_a_mix_dedupes_and_sorts():
    assert _parse_stages_arg("9-12,1,3,3") == ["agent_01", "agent_03", "agent_09", "agent_10", "agent_11", "agent_12"]


def test_stages_argument_rejects_out_of_range():
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_stages_arg("0-3")
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_stages_arg("14")


def test_stages_argument_rejects_backwards_range():
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_stages_arg("6-3")


def test_stages_argument_rejects_empty_input():
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_stages_arg("")
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_stages_arg("  , ,")


def test_run_stages_stops_at_first_failure_by_default(monkeypatch):
    pipeline = object.__new__(ExtractionPipeline)
    calls = []
    monkeypatch.setattr(
        pipeline, "run_agent",
        lambda agent_id: (calls.append(agent_id), agent_id != "agent_05")[1],
    )
    ok = pipeline.run_stages(["agent_03", "agent_04", "agent_05", "agent_06"])
    assert ok is False
    assert calls == ["agent_03", "agent_04", "agent_05"]  # agent_06 never attempted


def test_run_stages_keep_going_runs_every_selected_stage(monkeypatch):
    pipeline = object.__new__(ExtractionPipeline)
    calls = []
    monkeypatch.setattr(
        pipeline, "run_agent",
        lambda agent_id: (calls.append(agent_id), agent_id != "agent_05")[1],
    )
    ok = pipeline.run_stages(["agent_03", "agent_04", "agent_05", "agent_06"], keep_going=True)
    assert ok is False  # one stage failed
    assert calls == ["agent_03", "agent_04", "agent_05", "agent_06"]  # but every stage still ran


def test_run_stages_all_pass_returns_true(monkeypatch):
    pipeline = object.__new__(ExtractionPipeline)
    calls = []
    monkeypatch.setattr(pipeline, "run_agent", lambda agent_id: calls.append(agent_id) or True)
    assert pipeline.run_stages(["agent_01", "agent_02"]) is True
    assert calls == ["agent_01", "agent_02"]


def test_selective_readiness_failure_routes_through_remediation_and_recheck(monkeypatch):
    pipeline = object.__new__(ExtractionPipeline)
    pipeline._last_exit_codes = {}
    calls = []

    def run_agent(agent_id):
        calls.append(agent_id)
        if agent_id == "agent_07":
            pipeline._last_exit_codes[agent_id] = 2
            return False
        return True

    monkeypatch.setattr(pipeline, "run_agent", run_agent)
    monkeypatch.setattr(pipeline, "_readiness_requests_remediation", lambda: True)
    monkeypatch.setattr(
        pipeline,
        "run_agent_07",
        lambda *, reuse_conflicts=False, reuse_evidence=False: calls.append("agent_07_recheck") or True,
    )

    assert pipeline.run_stages(["agent_07", "agent_08", "agent_09"]) is True
    assert calls == ["agent_07", "agent_08", "agent_07_recheck", "agent_09"]


def test_selective_readiness_runtime_failure_never_uses_stale_remediation_report(monkeypatch):
    pipeline = object.__new__(ExtractionPipeline)
    pipeline._last_exit_codes = {}
    calls = []

    def run_agent(agent_id):
        calls.append(agent_id)
        pipeline._last_exit_codes[agent_id] = 1
        return False

    monkeypatch.setattr(pipeline, "run_agent", run_agent)
    monkeypatch.setattr(pipeline, "_readiness_requests_remediation", lambda: True)

    assert pipeline.run_stages(["agent_07", "agent_08", "agent_09"]) is False
    assert calls == ["agent_07"]


def test_single_readiness_review_is_nonblocking_when_invariants_pass(monkeypatch):
    pipeline = object.__new__(ExtractionPipeline)
    pipeline._last_exit_codes = {}

    def run_agent(agent_id):
        pipeline._last_exit_codes[agent_id] = 3
        return False

    monkeypatch.setattr(pipeline, "run_agent", run_agent)
    monkeypatch.setattr(pipeline, "_review_only_readiness", lambda: True)

    assert pipeline.run_stages(["agent_07"]) is True


def test_resume_from_agent_08_plans_automatic_readiness_recheck(monkeypatch):
    pipeline = object.__new__(ExtractionPipeline)
    pipeline._last_exit_codes = {}
    planned = {}

    def begin(stage_ids, label):
        planned["ids"] = stage_ids
        planned["label"] = label

    monkeypatch.setattr(pipeline, "_begin_run", begin)
    monkeypatch.setattr(pipeline, "_end_run", lambda overall_status: None)
    monkeypatch.setattr(pipeline, "run_agent", lambda agent_id: True)
    monkeypatch.setattr(
        pipeline,
        "run_agent_07",
        lambda *, reuse_conflicts=False, reuse_evidence=False: True,
    )

    assert pipeline.run_stages(["agent_08", "agent_09", "agent_10"]) is True
    assert planned["ids"] == ["agent_08", "agent_07", "agent_09", "agent_10"]
    assert "automatic agent_07 recheck" in planned["label"]


def test_selective_grounding_review_with_complete_coverage_continues(monkeypatch):
    pipeline = object.__new__(ExtractionPipeline)
    pipeline._last_exit_codes = {}
    calls = []

    def run_agent(agent_id):
        calls.append(agent_id)
        if agent_id == "agent_09":
            pipeline._last_exit_codes[agent_id] = 3
            return False
        return True

    monkeypatch.setattr(pipeline, "run_agent", run_agent)
    monkeypatch.setattr(pipeline, "_review_only_grounding", lambda: True)

    assert pipeline.run_stages(["agent_09", "agent_10"]) is True
    assert calls == ["agent_09", "agent_10"]


def test_run_stages_is_safe_without_reporting_configured(monkeypatch):
    """object.__new__ test doubles have no self.metrics/self.reporter; run_stages must not crash."""

    pipeline = object.__new__(ExtractionPipeline)
    assert not hasattr(pipeline, "metrics")
    assert not hasattr(pipeline, "reporter")
    monkeypatch.setattr(pipeline, "run_agent", lambda agent_id: True)
    assert pipeline.run_stages(["agent_01"]) is True


def test_review_only_readiness_is_non_blocking_but_fail_closed(tmp_path):
    pipeline = object.__new__(ExtractionPipeline)
    pipeline.optimized_dir = tmp_path
    (tmp_path / "kg_readiness_report.json").write_text(
        '{"invariants": {"corpus_integrity": {"pass": true}, '
        '"naming_consistency": {"pass": true}}, "rules_requiring_review": 2}'
    )
    pipeline._last_exit_codes = {"agent_07": 3, "agent_08": 3}
    assert pipeline._review_only_readiness() is True


def test_failed_readiness_invariant_remains_blocking(tmp_path):
    pipeline = object.__new__(ExtractionPipeline)
    pipeline.optimized_dir = tmp_path
    (tmp_path / "kg_readiness_report.json").write_text(
        '{"invariants": {"corpus_integrity": {"pass": false}}, '
        '"rules_requiring_review": 2}'
    )
    assert pipeline._review_only_readiness() is False


def test_remediation_request_rejects_non_schema_invariant_failures(tmp_path):
    pipeline = object.__new__(ExtractionPipeline)
    pipeline.optimized_dir = tmp_path
    (tmp_path / "kg_readiness_report.json").write_text(
        '{"invariants": {"corpus_integrity": {"pass": false}, '
        '"schema_consistency": {"pass": false}}, "rules_requiring_review": 2}'
    )

    assert pipeline._readiness_requests_remediation() is False


def test_remediation_request_accepts_schema_only_failure(tmp_path):
    pipeline = object.__new__(ExtractionPipeline)
    pipeline.optimized_dir = tmp_path
    (tmp_path / "kg_readiness_report.json").write_text(
        '{"invariants": {"corpus_integrity": {"pass": true}, '
        '"naming_consistency": {"pass": true}, '
        '"schema_consistency": {"pass": false}, '
        '"referential_integrity": {"pass": true}}, "rules_requiring_review": 2}'
    )

    assert pipeline._readiness_requests_remediation() is True


def test_complete_fail_closed_grounding_is_allowed_to_reach_dag(tmp_path):
    pipeline = object.__new__(ExtractionPipeline)
    pipeline.optimized_dir = tmp_path
    (tmp_path / "kg_grounding_report.json").write_text(
        '{"pass": false, "total_rules": 10, "model_claims": 20, '
        '"response_claims_returned": 20, "claim_coverage_percent": 100.0, '
        '"missing_claim_responses": 0, "duplicate_claim_responses": 0, '
        '"unexpected_claim_responses": 0}'
    )
    pipeline._last_exit_codes = {"agent_09": 3}
    assert pipeline._review_only_grounding() is True


def test_incomplete_grounding_response_remains_blocking(tmp_path):
    pipeline = object.__new__(ExtractionPipeline)
    pipeline.optimized_dir = tmp_path
    (tmp_path / "kg_grounding_report.json").write_text(
        '{"pass": false, "total_rules": 10, "model_claims": 20, '
        '"response_claims_returned": 19, "claim_coverage_percent": 99.0, '
        '"missing_claim_responses": 1, "duplicate_claim_responses": 0, '
        '"unexpected_claim_responses": 0}'
    )
    assert pipeline._review_only_grounding() is False


def test_run_all_continues_to_grounding_and_dag_for_review_only_readiness(tmp_path, monkeypatch):
    pipeline = object.__new__(ExtractionPipeline)
    pipeline.skip_optimize = False
    pipeline.optimized_dir = tmp_path
    pipeline.dag_dir = tmp_path / "dag"
    pipeline._last_exit_codes = {}
    (tmp_path / "kg_readiness_report.json").write_text(
        '{"invariants": {"corpus_integrity": {"pass": true}, '
        '"naming_consistency": {"pass": true}}, "rules_requiring_review": 1}'
    )
    calls = []

    def ok(name):
        def run():
            calls.append(name)
            return True
        return run

    for name in ("run_agent_01", "run_agent_02", "run_agent_03", "run_agent_04",
                 "run_agent_05", "run_agent_06", "run_agent_09", "run_agent_10", "run_agent_11", "run_agent_12",
                 "run_agent_13"):
        monkeypatch.setattr(pipeline, name, ok(name))

    readiness_calls = iter((False, False))

    def readiness(*, reuse_conflicts=False, reuse_evidence=False):
        calls.append("run_agent_07")
        pipeline._last_exit_codes["agent_07"] = 3
        return next(readiness_calls)

    def remediation():
        calls.append("run_agent_08")
        pipeline._last_exit_codes["agent_08"] = 3
        return False

    monkeypatch.setattr(pipeline, "run_agent_07", readiness)
    monkeypatch.setattr(pipeline, "run_agent_08", remediation)
    assert pipeline.run_all() is True
    assert calls[-5:] == ["run_agent_09", "run_agent_10", "run_agent_11", "run_agent_12", "run_agent_13"]


def test_run_all_continues_to_dag_for_complete_review_only_grounding(tmp_path, monkeypatch):
    pipeline = object.__new__(ExtractionPipeline)
    pipeline.skip_optimize = True
    pipeline.optimized_dir = tmp_path
    pipeline.dag_dir = tmp_path / "dag"
    pipeline._last_exit_codes = {}
    calls = []

    for name in ("run_agent_01", "run_agent_02", "run_agent_03", "run_agent_04",
                 "run_agent_05", "run_agent_06", "run_agent_10", "run_agent_11", "run_agent_12",
                 "run_agent_13"):
        monkeypatch.setattr(pipeline, name, lambda name=name: calls.append(name) or True)

    def grounding():
        calls.append("run_agent_09")
        pipeline._last_exit_codes["agent_09"] = 3
        return False

    monkeypatch.setattr(pipeline, "run_agent_09", grounding)
    monkeypatch.setattr(pipeline, "_review_only_grounding", lambda: True)
    assert pipeline.run_all() is True
    assert calls[-5:] == ["run_agent_09", "run_agent_10", "run_agent_11", "run_agent_12", "run_agent_13"]


def test_readiness_verification_reuses_remediated_conflicts(monkeypatch):
    pipeline = object.__new__(ExtractionPipeline)
    observed = {}

    def fake_run(self, agent_id, args, extra_env=None):
        observed["agent_id"] = agent_id
        observed["extra_env"] = extra_env
        return True

    monkeypatch.setattr(ExtractionPipeline, "_run", fake_run)

    assert pipeline.run_agent_07(reuse_conflicts=True, reuse_evidence=True)
    assert observed == {
        "agent_id": "agent_07",
        "extra_env": {
            "KG_READINESS_SKIP_CONFLICTS": "true",
            "KG_READINESS_SKIP_EVIDENCE": "true",
        },
    }


def test_canonical_stage_selector_dispatches_by_agent_number(monkeypatch):
    pipeline = object.__new__(ExtractionPipeline)
    observed = []
    monkeypatch.setattr(pipeline, "run_agent", lambda agent_id: observed.append(agent_id) or True)

    assert pipeline.run_stage("7") is True
    assert observed == ["agent_07"]


def test_canonical_stage_12_selector_dispatches_business_report(monkeypatch):
    pipeline = object.__new__(ExtractionPipeline)
    observed = []
    monkeypatch.setattr(pipeline, "run_agent", lambda agent_id: observed.append(agent_id) or True)

    assert pipeline.run_stage("12") is True
    assert observed == ["agent_12"]


def test_legacy_step_selector_remains_explicit_compatibility_alias(monkeypatch, capsys):
    pipeline = object.__new__(ExtractionPipeline)
    observed = []
    monkeypatch.setattr(pipeline, "run_agent", lambda agent_id: observed.append(agent_id) or True)

    assert pipeline.run_step("5.7") is True
    assert observed == ["agent_09"]
    assert "Legacy --step 5.7 maps to Stage 09/13 · agent_09" in capsys.readouterr().out


def test_initial_readiness_analysis_does_not_reuse_conflicts(monkeypatch):
    pipeline = object.__new__(ExtractionPipeline)
    observed = {}

    def fake_run(self, agent_id, args, extra_env=None):
        observed["extra_env"] = extra_env
        return True

    monkeypatch.setattr(ExtractionPipeline, "_run", fake_run)

    assert pipeline.run_agent_07()
    assert observed["extra_env"] is None


def test_agent_01_recursively_discovers_nested_sources(tmp_path, monkeypatch):
    source = tmp_path / "source"
    (source / "split" / "hard").mkdir(parents=True)
    (source / "split" / "hard" / "case.txt").write_text("source", encoding="utf-8")
    pipeline = ExtractionPipeline(
        source_dir=source,
        domain="deonticbench",
        target_rules=30,
        max_workers=40,
        skip_optimize=False,
        batch_name="nested-source-test",
    )
    calls = []

    def fake_run(agent_id, args, extra_env=None):
        calls.append((agent_id, args))
        return True

    monkeypatch.setattr(pipeline, "_run", fake_run)
    assert pipeline.run_agent_01() is True
    assert calls == [("agent_01", [str(source), str(pipeline.organized_dir)])]


def test_agent_01_ignores_top_level_metadata_manifest(tmp_path, monkeypatch):
    """A corpus manifest must not suppress recursively discovered documents."""
    source = tmp_path / "benchmark"
    source.mkdir()
    (source / "_manifest.json").write_text("{}", encoding="utf-8")
    (source / "split" / "whole").mkdir(parents=True)
    (source / "split" / "whole" / "case.txt").write_text("source", encoding="utf-8")
    pipeline = ExtractionPipeline(
        source_dir=source,
        domain="deonticbench",
        target_rules=30,
        max_workers=40,
        skip_optimize=False,
        batch_name="manifest-source-test",
    )
    calls = []

    def fake_run(agent_id, args, extra_env=None):
        calls.append((agent_id, args))
        return True

    monkeypatch.setattr(pipeline, "_run", fake_run)
    assert pipeline.run_agent_01() is True
    assert calls == [("agent_01", [str(source), str(pipeline.organized_dir)])]


def test_orchestrator_propagates_document_worker_profile():
    assert _PERFORMANCE_ENV["KG_ORGANIZER_WORKERS"] == ("document_workers", 32)


def test_orchestrator_safe_profile_keeps_stage_and_global_limits_aligned():
    """Every subprocess inherits the provider-safe 16-request ceiling."""
    expected = {
        "KG_LLM_CONCURRENCY": ("llm_concurrency", 16),
        "KG_ORGANIZER_WORKERS": ("document_workers", 32),
        "KG_GLOBAL_LLM_CONCURRENCY_INITIAL": ("global_llm_concurrency_initial", 8),
        "KG_GLOBAL_LLM_CONCURRENCY_MAX": ("global_llm_concurrency_max", 16),
        "KG_READINESS_WORKERS": ("readiness_workers", 80),
        "KG_READINESS_LLM_CONCURRENCY": ("readiness_llm_concurrency", 16),
        "KG_REMEDIATION_WORKERS": ("remediation_workers", 80),
        "KG_REMEDIATION_LLM_CONCURRENCY": ("remediation_llm_concurrency", 16),
        "KG_GROUNDING_WORKERS": ("grounding_workers", 80),
        "KG_GROUNDING_LLM_CONCURRENCY": ("grounding_llm_concurrency", 16),
        "KG_GROUNDING_RELATIONSHIPS_PER_REQUEST": ("grounding_relationships_per_request", 12),
    }
    for env_name, profile_entry in expected.items():
        assert _PERFORMANCE_ENV[env_name] == profile_entry


def test_mortgage_domain_is_supported_for_pdf_runs(tmp_path, monkeypatch):
    """The local Fannie Mae PDF is accepted by the normal CLI contract."""
    source = tmp_path / "mortgage"
    source.mkdir()
    (source / "guide.pdf").write_bytes(b"%PDF-1.4\n")
    (source / ".DS_Store").write_bytes(b"metadata")
    pipeline = ExtractionPipeline(
        source_dir=source,
        domain="mortgage",
        target_rules=30,
        max_workers=40,
        skip_optimize=True,
        batch_name="mortgage-test",
    )
    calls = []
    monkeypatch.setattr(pipeline, "_run", lambda agent_id, args, extra_env=None: calls.append((agent_id, args)) or True)
    assert pipeline.domain == "mortgage"
    assert pipeline.run_agent_01() is True
    assert calls == [("agent_01", [str(source), str(pipeline.organized_dir), "--files", "guide.pdf"])]


def _reset_config_singleton():
    """Reset BOTH singleton caches: Config._instance (Config.__new__'s own
    pattern) and utils.config's module-level `_config` global that
    get_config()/ExtractionPipeline actually read and mutate in place
    (get_config() reuses that cached object's ._provider across calls when
    provider=None, so a leftover "anthropic" from an earlier test silently
    leaks into every later get_config() call in the same process otherwise)."""
    import utils.config as config_module
    config_module._config = None
    Config._instance = None
    Config._config = None
    Config._provider = None
    Config._source_file_name = None
    Config._batch_name = None
    Config._domain = None


def test_env_propagates_default_openai_provider_to_every_agent_subprocess(tmp_path, monkeypatch):
    """Regression: _env() used to hardcode KG_PROVIDER=openai unconditionally,
    which would silently force every agent subprocess back to OpenAI even
    when the resolved provider was something else."""
    monkeypatch.delenv("KG_PROVIDER", raising=False)
    _reset_config_singleton()
    source = tmp_path / "src"
    source.mkdir()
    pipeline = ExtractionPipeline(
        source_dir=source, domain="deonticbench", target_rules=30, max_workers=4,
        skip_optimize=True, batch_name="provider-default-test",
    )
    assert pipeline._env()["KG_PROVIDER"] == "openai"


def test_env_propagates_explicit_anthropic_provider_to_every_agent_subprocess(tmp_path, monkeypatch):
    monkeypatch.delenv("KG_PROVIDER", raising=False)
    _reset_config_singleton()
    source = tmp_path / "src"
    source.mkdir()
    pipeline = ExtractionPipeline(
        source_dir=source, domain="deonticbench", target_rules=30, max_workers=4,
        skip_optimize=True, batch_name="provider-anthropic-test", provider="anthropic",
    )
    assert pipeline._env()["KG_PROVIDER"] == "anthropic"
    assert pipeline.metrics.config["provider"] == "anthropic"
    _reset_config_singleton()  # leave a clean singleton for tests that run after this one


def test_env_propagates_provider_selected_via_kg_provider_env(tmp_path, monkeypatch):
    monkeypatch.setenv("KG_PROVIDER", "anthropic")
    _reset_config_singleton()
    source = tmp_path / "src"
    source.mkdir()
    pipeline = ExtractionPipeline(
        source_dir=source, domain="deonticbench", target_rules=30, max_workers=4,
        skip_optimize=True, batch_name="provider-env-test",
    )
    assert pipeline._env()["KG_PROVIDER"] == "anthropic"
    _reset_config_singleton()  # leave a clean singleton for tests that run after this one
