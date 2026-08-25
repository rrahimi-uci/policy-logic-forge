"""Tests for the optional, fail-closed DMN engine adapter protocol."""

from __future__ import annotations

import sys

from bench.dmn_engine_harness import render_backend_report, run_crosscheck
from tests.test_dmn_builder import _ir


ENGINE_METADATA = {
    "engine_id": "fixture-adapter",
    "engine_version": "0.0.0",
    "source": "https://example.invalid/fixture-adapter",
    "revision": "fixture-revision",
    "license": "MIT",
    "artifact_sha256": "a" * 64,
}


def _cases():
    return [
        {"case_id": "active", "table_id": "t1", "inputs": {"active": True}},
        {"case_id": "inactive", "table_id": "t1", "inputs": {"active": False}},
    ]


def _adapter(*, disagreement: bool = False, malformed: bool = False):
    behavior = "'deny'" if disagreement else "'allow'"
    if malformed:
        code = "print('not-json')"
    else:
        code = f"""
import json, sys
for line in sys.stdin:
    request = json.loads(line)
    matched = request['inputs'].get('active') is True
    output = {{'decision': {behavior}}} if matched else {{}}
    print(json.dumps({{'case_id': request['case_id'], 'status': 'matched' if matched else 'no_match', 'outputs': output, 'matched_rule_ids': ['r1'] if matched else [], 'unknown_rule_ids': []}}))
"""
    return [sys.executable, "-c", code]


def test_missing_engine_is_explicitly_unrun():
    report = run_crosscheck(_ir(), _cases())
    assert report["status"] == "unrun"
    assert report["claimable"] is False
    assert report["summary"]["total"] == 2


def test_adapter_protocol_records_complete_agreement_without_calling_it_a_native_engine():
    report = run_crosscheck(
        _ir(),
        _cases(),
        engine_command=_adapter(),
        engine_metadata=ENGINE_METADATA,
    )
    assert report["status"] == "completed"
    assert report["claimable"] is True
    assert report["summary"] == {"total": 2, "agree": 2, "disagree": 0}
    assert all(case["agree"] for case in report["cases"])
    assert len(report["dmn_sha256"]) == 64
    rendered = render_backend_report(report)
    assert "Status: **completed**" in rendered
    assert "`active`" in rendered


def test_behavioral_disagreement_is_retained_and_not_claimable():
    report = run_crosscheck(
        _ir(),
        _cases(),
        engine_command=_adapter(disagreement=True),
        engine_metadata=ENGINE_METADATA,
    )
    assert report["status"] == "disagreement"
    assert report["claimable"] is False
    assert report["summary"]["disagree"] == 1
    assert "outputs" in report["cases"][0]["differences"]


def test_protocol_failure_and_missing_pinning_metadata_are_invalid():
    malformed = run_crosscheck(
        _ir(),
        _cases(),
        engine_command=_adapter(malformed=True),
        engine_metadata=ENGINE_METADATA,
    )
    missing_metadata = run_crosscheck(_ir(), _cases(), engine_command=_adapter(), engine_metadata={})

    assert malformed["status"] == "invalid"
    assert missing_metadata["status"] == "invalid"
    assert malformed["claimable"] is False and missing_metadata["claimable"] is False
