from __future__ import annotations

import sys

from bench.harness import run_anchor_harness


def _command():
    code = (
        "import json,sys; "
        "[print(json.dumps({'protocol':'anchor-harness/1.0','case_id':x['case_id'],'status':'completed','output':x['inputs']})) for x in map(json.loads,sys.stdin)]"
    )
    return [sys.executable, "-c", code]


def test_missing_anchor_is_explicitly_unrun():
    report = run_anchor_harness([{"case_id": "c1", "inputs": {"x": 1}, "expected": {"x": 1}}], artifact={"rules": []}, command=None)
    assert report["status"] == "unrun"
    assert not report["claimable"]


def test_pinned_adapter_round_trip_is_claimable():
    report = run_anchor_harness([{"case_id": "c1", "inputs": {"x": 1}, "expected": {"x": 1}}],
                                artifact={"rules": []}, command=_command())
    assert report["status"] == "completed"
    assert report["summary"] == {"total": 1, "agree": 1, "disagree": 0}


def test_protocol_failures_are_invalid():
    code = "print('{}')"
    report = run_anchor_harness([{"case_id": "c1", "inputs": {}, "expected": {}}], artifact={"x": 1},
                                command=[sys.executable, "-c", code])
    assert report["status"] == "invalid"
