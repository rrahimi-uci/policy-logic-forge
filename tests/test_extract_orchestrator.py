from cli.extract import ExtractionPipeline


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
