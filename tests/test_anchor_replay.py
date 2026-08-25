"""A1B tests for anchor observation validation and mismatch reporting."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from bench.anchor_replay import (
    REQUIRED_FIELDS,
    ReplayValidationError,
    aggregate_outcomes,
    compare_metrics,
    load_metrics,
)


def _row(activity: str, condition: str, run_id: int, dmn_type: str, *, agree: int = 1) -> dict[str, str]:
    row = {field: "" for field in REQUIRED_FIELDS}
    row.update(
        {
            "activity_id": activity,
            "condition": condition,
            "run_id": str(run_id),
            "dmn_type": dmn_type,
            "dmn_subtype": dmn_type,
            "generation_success": "True",
            "gold_path": f"gold_models/{dmn_type} - {activity}.json",
            "gen_path": f"generated_models/{dmn_type}/baseline/{activity}_run{run_id}.json",
            "gold_nodes": "1",
            "gold_edges": "0",
            "gold_ext_vars": "1",
            "gold_rules": "1",
            "gen_nodes": "1",
            "gen_edges": "0",
            "gen_ext_vars": "1",
            "gen_rules": "1",
            "sp_kernel": "1.0",
            "outcome_testable": "True",
            "outcome_num_tests": "2.0",
            "outcome_agree_count": f"{agree}.0",
            "outcome_disagree_count": f"{2 - agree}.0",
            "outcome_agreement": str(agree / 2),
        }
    )
    return row


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def test_load_metrics_and_compare_normalizes_paths_and_numeric_formatting(tmp_path: Path) -> None:
    released = [_row("A", "baseline", 1, "Outcome")]
    replayed = [_row("A", "baseline", 1, "Outcome")]
    replayed[0]["gold_path"] = "/tmp/upstream/gold_models/Outcome - A.json"
    replayed[0]["gen_path"] = "/tmp/upstream/generated_models/Outcome/baseline/A_run1.json"
    replayed[0]["outcome_num_tests"] = "2"

    released_path = tmp_path / "released.csv"
    replayed_path = tmp_path / "replayed.csv"
    _write_csv(released_path, released)
    _write_csv(replayed_path, replayed)

    comparison = compare_metrics(
        load_metrics(replayed_path),
        load_metrics(released_path),
        expected_activities_by_type={"Outcome": 1},
        conditions=("baseline",),
        run_ids=(1,),
    )
    assert comparison.status == "match"
    assert comparison.exact_rows == 1


def test_semantic_mismatch_is_retained_and_counted() -> None:
    released = [_row("A", "baseline", 1, "Outcome", agree=0)]
    replayed = [_row("A", "baseline", 1, "Outcome", agree=1)]

    comparison = compare_metrics(
        replayed,
        released,
        expected_activities_by_type={"Outcome": 1},
        conditions=("baseline",),
        run_ids=(1,),
    )
    assert comparison.status == "mismatch_reported"
    assert comparison.mismatch_rows == 1
    assert comparison.field_mismatch_counts["outcome_agree_count"] == 1
    assert comparison.examples[0].field == "outcome_agree_count"


def test_custom_grid_parameters_are_honored() -> None:
    released = [_row("A", "baseline", 7, "Outcome")]
    replayed = [_row("A", "baseline", 7, "Outcome")]
    comparison = compare_metrics(
        replayed,
        released,
        expected_activities_by_type={"Outcome": 1},
        conditions=("baseline",),
        run_ids=(7,),
    )
    assert comparison.status == "match"


def test_duplicate_or_incomplete_observation_grid_is_rejected() -> None:
    row = _row("A", "baseline", 1, "Outcome")
    with pytest.raises(ReplayValidationError, match="duplicate observation"):
        compare_metrics(
            [row, row],
            [row, row],
            expected_activities_by_type={"Outcome": 1},
            conditions=("baseline",),
            run_ids=(1,),
        )

    with pytest.raises(ReplayValidationError, match="activity count"):
        compare_metrics(
            [row],
            [row],
            expected_activities_by_type={"Outcome": 2},
            conditions=("baseline",),
            run_ids=(1,),
        )


def test_aggregation_keeps_row_unit_and_excludes_untestable_rows() -> None:
    rows = [_row("A", "baseline", 1, "Outcome", agree=1), _row("A", "baseline", 2, "Outcome", agree=2)]
    rows[1]["outcome_testable"] = "False"
    report = aggregate_outcomes(rows)
    group = report["groups"]["Outcome/baseline"]
    assert report["inclusion_rule"] == "generation_success == true and outcome_testable == true"
    assert group["observation_unit"] == "generation_row"
    assert group["rows"] == 1
    assert group["test_inputs"] == 2
    assert group["test_input_weighted_agreement"] == 0.5
