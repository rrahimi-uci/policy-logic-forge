import pytest

from bench.exception_reading import ExceptionReadingError, select_reading


def _alternatives():
    return {reading: [{"source_annotation_agreement": score}] for reading, score in
            (("defeater_or", 0.8), ("conjunctive", 0.9), ("refuse", 0.7))}


def test_selection_is_outcome_blind_and_frozen():
    result = select_reading(_alternatives())
    assert result["selected"] == "conjunctive"
    assert result["outcome_blind"] is True


def test_selection_rejects_outcome_contamination():
    alternatives = _alternatives()
    alternatives["defeater_or"][0]["oe"] = 1.0
    with pytest.raises(ExceptionReadingError, match="outcome fields"):
        select_reading(alternatives)
