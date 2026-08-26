from cli.extract import ExtractionPipeline


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
                 "run_agent_05", "run_agent_06", "run_agent_09", "run_agent_10"):
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
    assert calls[-2:] == ["run_agent_09", "run_agent_10"]


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


def test_initial_readiness_analysis_does_not_reuse_conflicts(monkeypatch):
    pipeline = object.__new__(ExtractionPipeline)
    observed = {}

    def fake_run(self, agent_id, args, extra_env=None):
        observed["extra_env"] = extra_env
        return True

    monkeypatch.setattr(ExtractionPipeline, "_run", fake_run)

    assert pipeline.run_agent_07()
    assert observed["extra_env"] is None
