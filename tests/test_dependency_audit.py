import json
from pathlib import Path

import pytest

from utils.dependency_audit import DependencyAuditError, evaluate_fixture, load_frame


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
