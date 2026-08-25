"""Contract checks for the fail-closed anchor reuse posture (A3)."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
POSTURE = ROOT / "docs" / "data_licensing.md"


def test_anchor_posture_is_pinned_and_fail_closed() -> None:
    text = " ".join(POSTURE.read_text(encoding="utf-8").split())

    assert "6a4844fb235d4f958d0810bba7089a2e9078099e" in text
    assert "CC BY 4.0" in text
    assert "as an assumption" in text
    assert "not permission to re-host" in text
    assert "must remain absent" in text
    assert "No author or maintainer contact was made" in text


def test_posture_names_the_non_redistributable_asset_classes() -> None:
    text = " ".join(POSTURE.read_text(encoding="utf-8").split())

    for asset in ("raw Dutch legal XML", "source DMN", "gold-model", "generated-model"):
        assert asset in text
