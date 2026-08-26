from pathlib import Path

import pytest

from ui.backend.review_store import ReviewStore


def test_review_overlay_round_trip(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.db")
    comment = store.add_comment(reviewer="ana", run_id="run", artifact_type="rule", artifact_id="r1", text="Check quote", field_path="description", artifact_hash="abc")
    decision = store.add_decision(reviewer="ana", run_id="run", artifact_type="rule", artifact_id="r1", disposition="defer", rationale="Need policy owner", artifact_hash="abc")
    label = store.add_label(reviewer="ana", run_id="run", artifact_type="rule", artifact_id="r1", label="policy-owner-needed")
    records = store.for_artifact("run", "rule", "r1")
    assert records["comments"][0]["id"] == comment["id"]
    assert records["comments"][0]["resolved"] is False
    assert records["decisions"][0]["id"] == decision["id"]
    assert records["labels"][0]["id"] == label["id"]
    view = store.save_view(reviewer="ana", run_id="run", name="Open rules", definition={"queue": "requires_review"})
    assert store.list_views("run")[0]["id"] == view["id"]
    assert store.list_views("run")[0]["definition"]["queue"] == "requires_review"
    assert store.history("run")
    with pytest.raises(ValueError):
        store.add_comment(reviewer="a", run_id="r", artifact_type="rule", artifact_id="x", text=" ")
    with pytest.raises(ValueError):
        store.add_decision(reviewer="a", run_id="r", artifact_type="rule", artifact_id="x", disposition="unknown")
    with pytest.raises(ValueError):
        store.add_label(reviewer="a", run_id="r", artifact_type="rule", artifact_id="x", label=" ")
    with pytest.raises(ValueError):
        store.save_view(reviewer="a", run_id="r", name=" ", definition={})
