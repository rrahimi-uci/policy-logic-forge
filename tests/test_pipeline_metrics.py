"""Tests for utils/pipeline_metrics.py: [LLM_COST] parsing, log-line
classification, and per-stage/per-run metrics aggregation."""

import json

from utils.pipeline_metrics import (
    FAIL,
    PASS,
    PENDING,
    RunMetrics,
    StageMetrics,
    classify_log_line,
    format_cost,
    format_duration,
    format_tokens,
    parse_llm_cost_line,
)


def _cost_line(**overrides) -> str:
    payload = {
        "model": "gpt-5.6-luna", "prompt_tokens": 1000, "completion_tokens": 200,
        "total_tokens": 1200, "cached_tokens": 300, "cost": 0.0042,
    }
    payload.update(overrides)
    return f"[LLM_COST]{json.dumps(payload)}"


def test_parse_llm_cost_line_extracts_fields():
    record = parse_llm_cost_line(_cost_line())
    assert record is not None
    assert record.model == "gpt-5.6-luna"
    assert record.prompt_tokens == 1000
    assert record.completion_tokens == 200
    assert record.total_tokens == 1200
    assert record.cached_tokens == 300
    assert record.cost_usd == 0.0042


def test_parse_llm_cost_line_ignores_unrelated_lines():
    assert parse_llm_cost_line("  💾 Prompt cache hit: 300 tokens cached (of 1000 prompt tokens)") is None
    assert parse_llm_cost_line("Extracting business rules...") is None
    assert parse_llm_cost_line("") is None


def test_parse_llm_cost_line_tolerates_malformed_json():
    assert parse_llm_cost_line("[LLM_COST]{not json") is None
    assert parse_llm_cost_line("[LLM_COST]42") is None  # valid JSON, not a dict


def test_parse_llm_cost_line_defaults_missing_numeric_fields_to_zero():
    record = parse_llm_cost_line("[LLM_COST]{\"model\": \"gpt-5.6-luna\"}")
    assert record is not None
    assert record.prompt_tokens == 0
    assert record.cost_usd == 0.0


def test_classify_log_line_matches_known_markers():
    assert classify_log_line("❌ ERROR: something broke") == "error"
    assert classify_log_line("ERROR: something broke") == "error"
    assert classify_log_line("Traceback (most recent call last):") == "error"
    assert classify_log_line("⚠️  Response truncated, retrying") == "warning"
    assert classify_log_line("WARNING: low confidence") == "warning"
    assert classify_log_line("✅ organized 12 documents") == "success"
    assert classify_log_line("PASS agent_01: Document Organizer (exit 0)") == "success"
    assert classify_log_line("Extracting business rules...") == "plain"


def test_classify_log_line_does_not_misfire_on_content_containing_keywords():
    """A rule whose *content* mentions "error"/"warning" is not a line-start marker."""

    assert classify_log_line("  rule text: the error rate must be below 5%") == "plain"
    assert classify_log_line("  this clause issues a warning to the tenant") == "plain"


def test_stage_metrics_aggregates_multiple_llm_calls():
    stage = StageMetrics(stage_id="agent_03", label="Stage 03/11 · agent_03 · Rules Extractor")
    stage.start()
    stage.record_llm_call(parse_llm_cost_line(_cost_line(prompt_tokens=1000, cached_tokens=500)))
    stage.record_llm_call(parse_llm_cost_line(_cost_line(prompt_tokens=1000, cached_tokens=0)))
    stage.finish(status=PASS, exit_code=0)

    assert stage.llm_call_count == 2
    assert stage.prompt_tokens == 2000
    assert stage.cached_tokens == 500
    assert stage.cache_hit_rate_percent == 25.0
    assert stage.duration_seconds is not None


def test_stage_metrics_cache_hit_rate_is_none_without_prompt_tokens():
    stage = StageMetrics(stage_id="agent_10", label="Stage 10/11 · agent_10 · Dependency DAG Generator")
    assert stage.cache_hit_rate_percent is None


def test_stage_metrics_observe_log_line_counts_warnings_and_errors():
    stage = StageMetrics(stage_id="agent_04", label="Stage 04/11 · agent_04 · Rule Validator")
    stage.observe_log_line("⚠️  low confidence on rule R12")
    stage.observe_log_line("❌ ERROR: validation crashed")
    stage.observe_log_line("plain informational line")
    assert stage.warning_count == 1
    assert stage.error_count == 1


def test_run_metrics_stage_is_get_or_create_and_preserves_order():
    run = RunMetrics(batch_name="b", domain="nda_confidentiality", source_dir="/src")
    run.stage("agent_02", "Stage 02")
    run.stage("agent_01", "Stage 01")
    run.stage("agent_02", "Stage 02 (again)")  # get, not re-create
    assert list(run.stages) == ["agent_02", "agent_01"]
    assert run.stages["agent_02"].label == "Stage 02"  # first write wins


def test_run_metrics_totals_sum_across_stages():
    run = RunMetrics(batch_name="b", domain="nda_confidentiality", source_dir="/src")
    s1 = run.stage("agent_03", "Stage 03")
    s1.record_llm_call(parse_llm_cost_line(_cost_line(prompt_tokens=1000, cached_tokens=400, cost=0.01)))
    s2 = run.stage("agent_09", "Stage 09")
    s2.record_llm_call(parse_llm_cost_line(_cost_line(prompt_tokens=2000, cached_tokens=200, cost=0.02)))

    assert run.total_prompt_tokens == 3000
    assert run.total_cached_tokens == 600
    assert round(run.total_cost_usd, 2) == 0.03
    assert run.overall_cache_hit_rate_percent == 20.0


def test_run_metrics_to_dict_and_write_json_round_trip(tmp_path):
    run = RunMetrics(batch_name="b", domain="nda_confidentiality", source_dir="/src", config={"target_rules": 20})
    stage = run.stage("agent_01", "Stage 01/11 · agent_01 · Document Organizer")
    stage.start()
    stage.finish(status=PASS, exit_code=0)
    run.finish(overall_status=PASS)

    out = tmp_path / "nested" / "run_metrics.json"
    run.write_json(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["batch_name"] == "b"
    assert data["overall_status"] == "pass"
    assert data["config"] == {"target_rules": 20}
    assert data["stages"][0]["stage_id"] == "agent_01"
    assert data["totals"]["llm_calls"] == 0


def test_stage_pending_status_has_no_duration():
    stage = StageMetrics(stage_id="agent_11", label="Stage 11/11")
    assert stage.status == PENDING
    assert stage.duration_seconds is None


def test_run_metrics_finish_marks_fail_status_and_duration():
    run = RunMetrics(batch_name="b", domain="nda_confidentiality", source_dir="/src")
    run.finish(overall_status=FAIL)
    assert run.overall_status == FAIL
    assert run.finished_at is not None
    assert run.duration_seconds is not None


def test_format_duration_buckets():
    assert format_duration(None) == "--"
    assert format_duration(3.2) == "3.2s"
    assert format_duration(64) == "1m 04s"
    assert format_duration(3725) == "1h 02m"


def test_format_cost_buckets():
    assert format_cost(0) == "$0.00"
    assert format_cost(0.0034) == "$0.0034"
    assert format_cost(1.5) == "$1.50"


def test_format_tokens_buckets():
    assert format_tokens(500) == "500"
    assert format_tokens(1500) == "1.5k"
    assert format_tokens(2_500_000) == "2.50M"
