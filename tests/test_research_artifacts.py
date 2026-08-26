from pathlib import Path

from scripts.validate_research_artifacts import validate


def test_retained_research_artifacts_are_fail_closed():
    checked = validate(Path(__file__).parents[1])
    assert len(checked) == 8
