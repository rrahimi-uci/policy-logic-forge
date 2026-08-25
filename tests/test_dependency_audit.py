import json
from pathlib import Path

import pytest

from utils.dependency_audit import DependencyAuditError, _wilson_interval, evaluate_fixture, load_frame


ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "dependency_gold"


def test_fixture_reports_dependency_precision_recall_and_iaa():
    report = evaluate_fixture(FIXTURE)

    assert report["status"] == "fixture_only"
    assert report["rule_universe_size"] == 4
    assert report["candidate_edge_count"] == 4
    assert report["declared_negative_edges"] == 2
    assert report["gold_edges"] == 2
    assert report["predicted_edges"] == 2
    assert report["matched_edges"] == 1
    assert report["missing_edges"] == 1
    assert report["false_positive_edges"] == 1
    assert report["recall"] == pytest.approx(0.5)
    assert report["precision"] == pytest.approx(0.5)
    assert report["positive_edge_iaa_jaccard"] == pytest.approx(1.0)
    assert report["negative_edge_iaa_jaccard"] == pytest.approx(1.0)
    assert report["recall_uncertainty"]["method"] == "wilson_95_binomial"
    assert report["recall_uncertainty"]["successes"] == 1
    assert report["recall_uncertainty"]["trials"] == 2
    assert report["recall_uncertainty"]["lower"] <= report["recall"] <= report["recall_uncertainty"]["upper"]
    assert report["annotator_agreement"]["exact_label_set_agreement"] is True
    assert "chance-corrected IAA" in report["annotator_agreement"]["interpretation"]


def test_fixture_requires_explicit_negative_edges(tmp_path):
    frame = json.loads((FIXTURE / "frame.json").read_text(encoding="utf-8"))
    frame["universe"].pop("negative_edges")
    (tmp_path / "frame.json").write_text(json.dumps(frame), encoding="utf-8")

    with pytest.raises(DependencyAuditError, match="negative_edges"):
        load_frame(tmp_path)


def test_fixture_rejects_prediction_outside_declared_candidate_universe(tmp_path):
    frame = json.loads((FIXTURE / "frame.json").read_text(encoding="utf-8"))
    frame["predictions"].append(
        {"source_rule_id": "r1", "target_rule_id": "r2", "dependency_type": "prerequisite"}
    )
    (tmp_path / "frame.json").write_text(json.dumps(frame), encoding="utf-8")

    with pytest.raises(DependencyAuditError, match="outside the declared candidate"):
        load_frame(tmp_path)


def test_fixture_rejects_unlabelled_candidate_edge(tmp_path):
    frame = json.loads((FIXTURE / "frame.json").read_text(encoding="utf-8"))
    frame["adjudication"]["negative_edges"].pop()
    (tmp_path / "frame.json").write_text(json.dumps(frame), encoding="utf-8")

    with pytest.raises(DependencyAuditError, match="label every candidate edge"):
        load_frame(tmp_path)


def test_fixture_rejects_edge_labelled_both_positive_and_negative(tmp_path):
    frame = json.loads((FIXTURE / "frame.json").read_text(encoding="utf-8"))
    frame["annotators"][0]["negative_edges"].append(frame["annotators"][0]["edges"][0])
    (tmp_path / "frame.json").write_text(json.dumps(frame), encoding="utf-8")

    with pytest.raises(DependencyAuditError, match="both positive and negative"):
        load_frame(tmp_path)


def test_wilson_interval_handles_empty_denominator():
    interval = _wilson_interval(0, 0)

    assert interval["method"] == "wilson_95_binomial"
    assert interval["lower"] is None
    assert interval["upper"] is None
