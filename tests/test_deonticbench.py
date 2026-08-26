"""Provider-free contracts for the pinned DeonticBench materializer."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "benchmarks" / "deonticbench.json"
SCRIPT_PATH = ROOT / "benchmarks" / "scripts" / "download_deonticbench.py"
SPEC = importlib.util.spec_from_file_location("download_deonticbench", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_manifest_pins_all_configs_splits_and_counts() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["dataset"] == "gydou/DeonticBench"
    assert len(manifest["revision"]) == 40
    assert set(manifest["configurations"]) == {
        "sara_numeric", "sara_binary", "airline", "housing", "uscis-aao"
    }
    assert all(set(splits) == {"whole", "hard"} for splits in manifest["configurations"].values())
    assert sum(spec["rows"] for splits in manifest["configurations"].values() for spec in splits.values()) == 6483
    assert manifest["total_rows"] == 6483
    for splits in manifest["configurations"].values():
        for spec in splits.values():
            assert spec["bytes"] > 0
            assert len(spec["sha256"]) == 64


def test_source_text_contains_only_source_bearing_fields() -> None:
    row = {
        "id": "case-1",
        "text": "The applicant submitted the form.",
        "statutes": "§ 1. An applicant must submit a form.",
        "question": "Was the form submitted?",
        "label": "yes",
        "reference_prolog": "answer(yes).",
    }
    text = MODULE.source_text(row, configuration="airline")
    assert "configuration: airline" in text
    assert "case_id: case-1" in text
    assert "CASE FACTS" in text
    assert "STATUTES" in text
    assert "QUESTION" in text
    assert "answer(yes)" not in text
    assert "LABEL" not in text.upper()


def test_source_text_supports_housing_rows_without_text() -> None:
    text = MODULE.source_text({"id": "housing-1", "state": "Missouri", "statutes": "§ 1. A court may...", "question": "May it?"}, configuration="housing")
    assert "STATUTES\n§ 1" in text
    assert "QUESTION\nMay it?" in text
    assert "jurisdiction/state: Missouri" in text


def test_fetch_rows_paginates_and_rejects_bad_indexes(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = {
        0: {"num_rows_total": 3, "rows": [{"row_idx": 0, "row": {"id": "a"}}, {"row_idx": 1, "row": {"id": "b"}}]},
        2: {"num_rows_total": 3, "rows": [{"row_idx": 2, "row": {"id": "c"}}]},
    }
    monkeypatch.setattr(MODULE, "request_json", lambda url: pages[int(url.split("offset=")[1].split("&")[0])])
    monkeypatch.setattr(MODULE, "load_manifest", lambda: {"revision": "r"})
    assert [row["id"] for row in MODULE.fetch_rows("demo", "whole", 3)] == ["a", "b", "c"]

    bad = {"num_rows_total": 1, "rows": [{"row_idx": 9, "row": {"id": "a"}}]}
    monkeypatch.setattr(MODULE, "request_json", lambda url: bad)
    with pytest.raises(RuntimeError, match="row index mismatch"):
        MODULE.fetch_rows("demo", "whole", 1)


def test_read_parquet_rows_is_lossless_and_count_checked(tmp_path) -> None:
    parquet = pytest.importorskip("pyarrow.parquet")
    arrow = pytest.importorskip("pyarrow")
    path = tmp_path / "rows.parquet"
    rows = [{"id": "one", "question": "Q", "statutes": "S", "label": "yes", "reference_prolog": "p"}]
    parquet.write_table(arrow.Table.from_pylist(rows), path)
    assert MODULE.read_parquet_rows(path, 1) == rows
    with pytest.raises(RuntimeError, match="row count mismatch"):
        MODULE.read_parquet_rows(path, 2)


def test_existing_local_materialization_is_complete_when_present() -> None:
    output = ROOT / "compliance-files" / "deonticbench"
    if not output.exists():
        pytest.skip("DeonticBench is downloaded locally only; CI can run the downloader explicitly")
    result = subprocess.run(
        ["python3", str(SCRIPT_PATH), "--output", str(output), "--verify"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
