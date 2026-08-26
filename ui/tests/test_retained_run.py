from pathlib import Path

import pytest

from ui.backend.review_index import ReviewIndex


REPO_ROOT = Path(__file__).resolve().parents[2]
RETAINED_RUN = REPO_ROOT / "pipeline-output" / "privacy-policy-full-20260825"


@pytest.mark.skipif(not RETAINED_RUN.is_dir(), reason="retained pipeline output is not checked into CI")
def test_privacy_policy_bundle_is_reviewable() -> None:
    index = ReviewIndex.from_directory(RETAINED_RUN)
    assert index.run_summary["rule_count"] == 879
    assert index.run_summary["document_count"] >= 1000
    assert index.run_summary["completed_stage_count"] == 10
    assert index.run_summary["diagnostic_count"] > 0
    assert index.queue("requires_review")
    assert index.search("retention")
    assert index.relationships
    assert index.evidence
