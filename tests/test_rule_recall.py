import json
from pathlib import Path

import pytest

from utils.rule_recall import RuleRecallError, evaluate_fixture, load_frame


ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "rule_recall_gold"


def test_fixture_matches_semantics_not_annotator_or_model_rule_ids():
    report = evaluate_fixture(FIXTURE)

    assert report["status"] == "fixture_only"
    assert report["gold_rules"] == 3
    assert report["predicted_rules"] == 3
    assert report["matched_rules"] == 2
    assert report["missing_rules"] == 1
    assert report["false_positive_rules"] == 1
    assert report["recall"] == pytest.approx(2 / 3)
    assert report["precision"] == pytest.approx(2 / 3)
    assert report["missing_rule_keys"] == ["privacy.other_data_request"]
    assert report["false_positive_rule_keys"] == ["model-r003"]


def test_fixture_requires_two_independent_annotators_and_adjudication(tmp_path):
    frame = json.loads((FIXTURE / "frame.json").read_text(encoding="utf-8"))
    frame["annotators"] = frame["annotators"][:1]
    (tmp_path / "source").mkdir()
    (tmp_path / "source" / "sample_privacy.txt").write_text(
        (FIXTURE / "source" / "sample_privacy.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "frame.json").write_text(json.dumps(frame), encoding="utf-8")

    with pytest.raises(RuleRecallError, match="exactly two annotator"):
        load_frame(tmp_path)


def test_fixture_rejects_source_hash_drift(tmp_path):
    frame = json.loads((FIXTURE / "frame.json").read_text(encoding="utf-8"))
    frame["source_manifest"][0]["sha256"] = "0" * 64
    (tmp_path / "source").mkdir()
    (tmp_path / "source" / "sample_privacy.txt").write_text(
        (FIXTURE / "source" / "sample_privacy.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "frame.json").write_text(json.dumps(frame), encoding="utf-8")

    with pytest.raises(RuleRecallError, match="source hash mismatch"):
        load_frame(tmp_path)
