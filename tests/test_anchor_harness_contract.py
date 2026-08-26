import json
from pathlib import Path

from bench.harness import render_harness_report


def test_retained_j1_result_is_explicitly_unrun():
    result = json.loads((Path(__file__).parents[1] / "results/aggregates/j1.json").read_text())
    assert result["status"] == "unrun"
    assert result["claimable"] is False
    assert "gold-I/O" in result["reason"]
    assert "Status: **unrun**" in render_harness_report(result)
