from cli.extract import ExtractionPipeline


def test_readiness_verification_reuses_remediated_conflicts(monkeypatch):
    pipeline = object.__new__(ExtractionPipeline)
    observed = {}

    def fake_run(self, step, label, script, args, extra_env=None):
        observed["step"] = step
        observed["extra_env"] = extra_env
        return True

    monkeypatch.setattr(ExtractionPipeline, "_run", fake_run)

    assert pipeline.step5_5(reuse_conflicts=True)
    assert observed == {"step": "5.5", "extra_env": {"KG_READINESS_SKIP_CONFLICTS": "true"}}


def test_initial_readiness_analysis_does_not_reuse_conflicts(monkeypatch):
    pipeline = object.__new__(ExtractionPipeline)
    observed = {}

    def fake_run(self, step, label, script, args, extra_env=None):
        observed["extra_env"] = extra_env
        return True

    monkeypatch.setattr(ExtractionPipeline, "_run", fake_run)

    assert pipeline.step5_5()
    assert observed["extra_env"] is None
