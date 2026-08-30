from cli.extract import ExtractionPipeline, _PERFORMANCE_ENV, _parse_stage_arg


def test_stage_argument_accepts_display_number_with_or_without_zero_padding():
    assert _parse_stage_arg("7") == "7"
    assert _parse_stage_arg("07") == "7"


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
                 "run_agent_05", "run_agent_06", "run_agent_09", "run_agent_10", "run_agent_11"):
        monkeypatch.setattr(pipeline, name, ok(name))

    readiness_calls = iter((False, False))

    def readiness(*, reuse_conflicts=False):
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
    assert calls[-3:] == ["run_agent_09", "run_agent_10", "run_agent_11"]


def test_run_all_continues_to_dag_for_complete_review_only_grounding(tmp_path, monkeypatch):
    pipeline = object.__new__(ExtractionPipeline)
    pipeline.skip_optimize = True
    pipeline.optimized_dir = tmp_path
    pipeline.dag_dir = tmp_path / "dag"
    pipeline._last_exit_codes = {}
    calls = []

    for name in ("run_agent_01", "run_agent_02", "run_agent_03", "run_agent_04",
                 "run_agent_05", "run_agent_06", "run_agent_10", "run_agent_11"):
        monkeypatch.setattr(pipeline, name, lambda name=name: calls.append(name) or True)

    def grounding():
        calls.append("run_agent_09")
        pipeline._last_exit_codes["agent_09"] = 3
        return False

    monkeypatch.setattr(pipeline, "run_agent_09", grounding)
    monkeypatch.setattr(pipeline, "_review_only_grounding", lambda: True)
    assert pipeline.run_all() is True
    assert calls[-3:] == ["run_agent_09", "run_agent_10", "run_agent_11"]


def test_readiness_verification_reuses_remediated_conflicts(monkeypatch):
    pipeline = object.__new__(ExtractionPipeline)
    observed = {}

    def fake_run(self, agent_id, args, extra_env=None):
        observed["agent_id"] = agent_id
        observed["extra_env"] = extra_env
        return True

    monkeypatch.setattr(ExtractionPipeline, "_run", fake_run)

    assert pipeline.run_agent_07(reuse_conflicts=True)
    assert observed == {"agent_id": "agent_07", "extra_env": {"KG_READINESS_SKIP_CONFLICTS": "true"}}


def test_canonical_stage_selector_dispatches_by_agent_number(monkeypatch):
    pipeline = object.__new__(ExtractionPipeline)
    observed = []
    monkeypatch.setattr(pipeline, "run_agent", lambda agent_id: observed.append(agent_id) or True)

    assert pipeline.run_stage("7") is True
    assert observed == ["agent_07"]


def test_legacy_step_selector_remains_explicit_compatibility_alias(monkeypatch, capsys):
    pipeline = object.__new__(ExtractionPipeline)
    observed = []
    monkeypatch.setattr(pipeline, "run_agent", lambda agent_id: observed.append(agent_id) or True)

    assert pipeline.run_step("5.7") is True
    assert observed == ["agent_09"]
    assert "Legacy --step 5.7 maps to Stage 09/11 · agent_09" in capsys.readouterr().out


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
    assert _PERFORMANCE_ENV["KG_ORGANIZER_WORKERS"] == ("document_workers", 16)


def test_orchestrator_fast_profile_keeps_stage_and_global_limits_aligned():
    """Every subprocess inherits the measured safe 16-request ceiling."""
    expected = {
        "KG_LLM_CONCURRENCY": ("llm_concurrency", 16),
        "KG_GLOBAL_LLM_CONCURRENCY_INITIAL": ("global_llm_concurrency_initial", 8),
        "KG_GLOBAL_LLM_CONCURRENCY_MAX": ("global_llm_concurrency_max", 16),
        "KG_READINESS_LLM_CONCURRENCY": ("readiness_llm_concurrency", 16),
        "KG_REMEDIATION_LLM_CONCURRENCY": ("remediation_llm_concurrency", 16),
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
