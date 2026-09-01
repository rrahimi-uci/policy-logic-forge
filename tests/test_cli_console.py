"""Tests for cli/console.py: the text and JSON reporters cli/extract.py drives."""

import io
import json

from cli.console import JsonReporter, TextReporter, make_reporter, stage_icon, status_icon
from utils.pipeline_metrics import FAIL, PASS, REVIEW, RunMetrics, parse_llm_cost_line


def _sample_run() -> RunMetrics:
    run = RunMetrics(
        batch_name="demo", domain="nda_confidentiality", source_dir="/src",
        config={"target_rules": 20, "model": "gpt-5.6-luna"},
    )
    run.stage("agent_01", "Stage 01/12 · agent_01 · Document Organizer")
    run.stage("agent_02", "Stage 02/12 · agent_02 · Entity Extractor")
    return run


def test_make_reporter_dispatches_by_output_mode():
    assert isinstance(make_reporter("text"), TextReporter)
    assert isinstance(make_reporter("json"), JsonReporter)
    assert isinstance(make_reporter("anything-else"), TextReporter)  # safe default


def test_human_status_and_stage_icons_cover_monitoring_states():
    assert status_icon(PASS) == "✅"
    assert status_icon(REVIEW) == "🔎"
    assert status_icon(FAIL) == "❌"
    assert status_icon("unknown") == "❔"
    assert stage_icon("agent_01") == "📚"
    assert stage_icon("agent_02") == "🧩"
    assert stage_icon("agent_12") == "📊"
    assert stage_icon("unknown") == "🔹"


def test_text_reporter_full_lifecycle_does_not_raise():
    run = _sample_run()
    buf = io.StringIO()
    reporter = TextReporter(stream=buf)

    reporter.run_start(run)
    stage = run.stages["agent_01"]
    stage.start()
    reporter.stage_start(stage, 1, 2)
    reporter.log_line("hello from the subprocess", "plain")
    reporter.log_line("⚠️ a warning line", "warning")
    stage.record_llm_call(parse_llm_cost_line(
        '[LLM_COST]{"model": "gpt-5.6-luna", "prompt_tokens": 100, "completion_tokens": 20, '
        '"total_tokens": 120, "cached_tokens": 40, "cost": 0.0005}'
    ))
    stage.finish(status=PASS, exit_code=0)
    reporter.stage_end(stage, run)
    run.finish(overall_status=PASS)
    reporter.run_end(run)
    reporter.error("a fatal error message")

    output = buf.getvalue()
    assert "demo" in output
    assert "🚀 run started" in output
    assert "🔄" in output
    assert "📚 Stage 01/12" in output
    assert "selected 01/02" in output
    assert "✅" in output
    assert "hello from the subprocess" in output
    assert "Run summary" in output
    assert "a fatal error message" in output


def test_json_reporter_emits_valid_ndjson_events_on_stdout():
    run = _sample_run()
    out = io.StringIO()
    err = io.StringIO()
    reporter = JsonReporter(stream=out, log_stream=err)

    reporter.run_start(run)
    stage = run.stages["agent_01"]
    stage.start()
    reporter.stage_start(stage, 1, 2)
    reporter.log_line("raw subprocess line\n", "plain")
    stage.finish(status=PASS, exit_code=0)
    reporter.stage_end(stage, run)
    run.finish(overall_status=PASS)
    reporter.run_end(run)

    lines = [ln for ln in out.getvalue().splitlines() if ln.strip()]
    events = [json.loads(ln) for ln in lines]
    assert [e["event"] for e in events] == ["run_start", "stage_start", "stage_end", "run_end"]
    assert events[0]["batch_name"] == "demo"
    assert events[2]["stage_id"] == "agent_01"
    assert events[2]["status"] == "pass"
    assert events[3]["overall_status"] == "pass"
    # Raw log passthrough goes to stderr, not stdout, in JSON mode.
    assert "raw subprocess line" in err.getvalue()
    assert "raw subprocess line" not in out.getvalue()


def test_json_reporter_error_event():
    out = io.StringIO()
    reporter = JsonReporter(stream=out, log_stream=io.StringIO())
    reporter.error("source directory not found")
    event = json.loads(out.getvalue().strip())
    assert event == {"event": "error", "message": "source directory not found"}


def test_text_reporter_labels_review_as_review_not_failure():
    run = _sample_run()
    run.stages["agent_01"].finish(status=REVIEW, exit_code=3)
    run.finish(overall_status=REVIEW)
    output = io.StringIO()

    TextReporter(stream=output).run_end(run)

    assert "Review summary" in output.getvalue()
    assert "REVIEW" in output.getvalue()


def test_json_reporter_stdout_contains_only_valid_json_lines():
    """Automation consumers must be able to parse every stdout line as JSON."""

    run = _sample_run()
    out = io.StringIO()
    reporter = JsonReporter(stream=out, log_stream=io.StringIO())
    reporter.run_start(run)
    run.finish(overall_status=FAIL)
    reporter.run_end(run)
    for line in out.getvalue().splitlines():
        if line.strip():
            json.loads(line)  # raises if not valid JSON
