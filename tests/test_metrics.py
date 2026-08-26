import pytest

from bench.metrics import MetricValidationError, enrich_observation, summarize


def _row(**extra):
    return {"model_id": "m1", "system": "ours", "run_id": "1", "eligible_units": 4,
            "compiled_units": 3, "afs": 0.8, "soe": 0.7, "oe": 0.6, **extra}


def test_metrics_keep_afs_soe_oe_distinct():
    result = enrich_observation(_row())
    assert result["ey"] == 0.75
    assert result["metric_contract"]["soe"].endswith("gold_labeled")
    assert result["metric_contract"]["cqi"] == "conditional_quality_not_correctness"


def test_invalid_metric_range_refuses():
    with pytest.raises(MetricValidationError):
        enrich_observation(_row(afs=1.1))


def test_summary_retains_observation_unit():
    result = summarize([_row(), _row(model_id="m2")])
    assert result["observation_unit"] == "model_system_run"
    assert result["rows"] == 2
