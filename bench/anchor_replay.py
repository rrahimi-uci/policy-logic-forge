"""Validate and summarize a deterministic replay of the Dutch anchor evaluator.

The upstream anchor repository is intentionally not vendored here.  A replay
is performed in a temporary checkout at the pinned commit, then its CSV is
compared with the released ``results/metrics.csv`` using this module.  Path
roots and integer/float formatting are normalized, but semantic metric
mismatches are retained and reported rather than tuned away.

The comparison is deliberately separate from the paper's headline claims. It
records both row-level and test-input-weighted outcome aggregates, making the
observation unit and inclusion rule visible before any manuscript number is
used.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "anchor-replay/1.0"
ANCHOR_REPOSITORY = "https://github.com/opengov-lab/legal-text-to-decision-model"
PINNED_COMMIT = "6a4844fb235d4f958d0810bba7089a2e9078099e"
EXPECTED_CONDITIONS = ("baseline", "srl", "conditions", "srl_conditions")
EXPECTED_RUN_IDS = (1, 2, 3, 4, 5)
EXPECTED_ACTIVITIES_BY_TYPE = {"Outcome": 50, "Requirements": 45}

KEY_FIELDS = ("activity_id", "condition", "run_id", "dmn_type")
PATH_FIELDS = {"gold_path", "gen_path"}
BOOL_FIELDS = {"generation_success", "outcome_testable"}
FLOAT_FIELDS = {"sp_kernel", "outcome_agreement"}
NUMERIC_FIELDS = {
    "gold_nodes", "gold_edges", "gold_ext_vars", "gold_rules",
    "gen_nodes", "gen_edges", "gen_ext_vars", "gen_rules",
    "outcome_num_tests", "outcome_agree_count", "outcome_disagree_count",
    *FLOAT_FIELDS,
}
REQUIRED_FIELDS = (
    "activity_id", "condition", "run_id", "dmn_type", "dmn_subtype",
    "generation_success", "gold_path", "gen_path",
    "gold_nodes", "gold_edges", "gold_ext_vars", "gold_rules",
    "gen_nodes", "gen_edges", "gen_ext_vars", "gen_rules", "sp_kernel",
    "outcome_testable", "outcome_num_tests", "outcome_agree_count",
    "outcome_disagree_count", "outcome_agreement",
)


class ReplayValidationError(ValueError):
    """Raised when an anchor metrics file violates its observation contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReplayValidationError(message)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_run_id(value: Any) -> int:
    try:
        parsed = int(float(str(value).strip()))
    except (TypeError, ValueError) as exc:
        raise ReplayValidationError(f"run_id must be an integer: {value!r}") from exc
    _require(str(value).strip() in {str(parsed), f"{parsed}.0"}, f"run_id must be integral: {value!r}")
    return parsed


def load_metrics(path: str | Path) -> list[dict[str, str]]:
    """Load and structurally validate one evaluator CSV."""

    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        _require(reader.fieldnames is not None, "metrics CSV is missing a header")
        missing = sorted(set(REQUIRED_FIELDS) - set(reader.fieldnames or ()))
        _require(not missing, f"metrics CSV is missing fields: {missing}")
        rows = [dict(row) for row in reader]
    _require(rows, "metrics CSV must contain at least one observation")
    return rows


def _row_key(
    row: Mapping[str, Any],
    *,
    conditions: Sequence[str] = EXPECTED_CONDITIONS,
    run_ids: Sequence[int] = EXPECTED_RUN_IDS,
) -> tuple[str, str, int, str]:
    activity = str(row.get("activity_id", "")).strip()
    condition = str(row.get("condition", "")).strip()
    dmn_type = str(row.get("dmn_type", "")).strip()
    _require(bool(activity), "activity_id must be non-empty")
    _require(condition in conditions, f"unknown condition: {condition!r}")
    _require(dmn_type in EXPECTED_ACTIVITIES_BY_TYPE, f"unknown dmn_type: {dmn_type!r}")
    run_id = _parse_run_id(row.get("run_id"))
    _require(run_id in run_ids, f"run_id outside configured range: {run_id}")
    return activity, condition, run_id, dmn_type


def validate_observation_grid(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_activities_by_type: Mapping[str, int] | None = EXPECTED_ACTIVITIES_BY_TYPE,
    conditions: Sequence[str] = EXPECTED_CONDITIONS,
    run_ids: Sequence[int] = EXPECTED_RUN_IDS,
) -> None:
    """Validate uniqueness and completeness of the model × condition × run unit."""

    keys: set[tuple[str, str, int, str]] = set()
    activities: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        key = _row_key(row, conditions=conditions, run_ids=run_ids)
        _require(key not in keys, f"duplicate observation key: {key}")
        keys.add(key)
        activities[key[3]].add(key[0])

    if expected_activities_by_type is None:
        return
    for dmn_type, expected_count in expected_activities_by_type.items():
        observed = activities.get(dmn_type, set())
        _require(
            len(observed) == expected_count,
            f"{dmn_type} activity count {len(observed)} != expected {expected_count}",
        )
        expected_keys = {
            (activity, condition, run_id, dmn_type)
            for activity in observed
            for condition in conditions
            for run_id in run_ids
        }
        missing = sorted(expected_keys - keys)
        _require(not missing, f"missing observations (first 5): {missing[:5]}")
    expected_total = sum(
        expected_activities_by_type[dmn_type] * len(conditions) * len(run_ids)
        for dmn_type in expected_activities_by_type
    )
    _require(len(rows) == expected_total, f"row count {len(rows)} != expected {expected_total}")


def _normalize_path(value: Any, field: str) -> str:
    text = str(value or "").replace("\\", "/")
    if field == "gold_path":
        marker = "/gold_models/"
        if marker in text:
            return "gold_models/" + text.split(marker, 1)[1]
    if field == "gen_path":
        marker = "/generated_models/"
        if marker in text:
            return "generated_models/" + text.split(marker, 1)[1]
    return text


def _normalize_value(field: str, value: Any) -> Any:
    text = str(value if value is not None else "").strip()
    if field in PATH_FIELDS:
        return _normalize_path(text, field)
    if field in BOOL_FIELDS:
        lowered = text.lower()
        if lowered in {"true", "1"}:
            return True
        if lowered in {"false", "0", ""}:
            return False
        return lowered
    if field in NUMERIC_FIELDS:
        if text == "":
            return None
        try:
            return float(text)
        except ValueError:
            return text
    return text


def _values_equal(field: str, left: Any, right: Any) -> bool:
    left_value = _normalize_value(field, left)
    right_value = _normalize_value(field, right)
    if isinstance(left_value, float) and isinstance(right_value, float):
        if math.isnan(left_value) and math.isnan(right_value):
            return True
        return math.isclose(left_value, right_value, rel_tol=1e-12, abs_tol=1e-12)
    return left_value == right_value


@dataclass(frozen=True)
class MetricMismatch:
    key: tuple[str, str, int, str]
    field: str
    replayed: Any
    released: Any

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": {
                "activity_id": self.key[0],
                "condition": self.key[1],
                "run_id": self.key[2],
                "dmn_type": self.key[3],
            },
            "field": self.field,
            "replayed": self.replayed,
            "released": self.released,
        }


@dataclass(frozen=True)
class ReplayComparison:
    rows_compared: int
    exact_rows: int
    mismatch_rows: int
    field_mismatch_counts: Mapping[str, int]
    examples: tuple[MetricMismatch, ...]

    @property
    def status(self) -> str:
        return "match" if self.mismatch_rows == 0 else "mismatch_reported"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "rows_compared": self.rows_compared,
            "exact_rows": self.exact_rows,
            "mismatch_rows": self.mismatch_rows,
            "field_mismatch_counts": dict(sorted(self.field_mismatch_counts.items())),
            "examples": [example.as_dict() for example in self.examples],
        }


def compare_metrics(
    replayed_rows: Sequence[Mapping[str, Any]],
    released_rows: Sequence[Mapping[str, Any]],
    *,
    expected_activities_by_type: Mapping[str, int] | None = EXPECTED_ACTIVITIES_BY_TYPE,
    conditions: Sequence[str] = EXPECTED_CONDITIONS,
    run_ids: Sequence[int] = EXPECTED_RUN_IDS,
    max_examples: int = 20,
) -> ReplayComparison:
    """Compare replayed and released rows after only representation normalization."""

    validate_observation_grid(
        replayed_rows,
        expected_activities_by_type=expected_activities_by_type,
        conditions=conditions,
        run_ids=run_ids,
    )
    validate_observation_grid(
        released_rows,
        expected_activities_by_type=expected_activities_by_type,
        conditions=conditions,
        run_ids=run_ids,
    )
    replayed = {
        _row_key(row, conditions=conditions, run_ids=run_ids): row
        for row in replayed_rows
    }
    released = {
        _row_key(row, conditions=conditions, run_ids=run_ids): row
        for row in released_rows
    }
    _require(set(replayed) == set(released), "replayed and released observation keys differ")

    field_counts: Counter[str] = Counter()
    mismatch_rows = 0
    examples: list[MetricMismatch] = []
    comparable_fields = tuple(field for field in REQUIRED_FIELDS if field not in KEY_FIELDS)
    for key in sorted(replayed):
        row_mismatches = []
        for field in comparable_fields:
            if not _values_equal(field, replayed[key].get(field), released[key].get(field)):
                field_counts[field] += 1
                row_mismatches.append(MetricMismatch(key, field, replayed[key].get(field), released[key].get(field)))
        if row_mismatches:
            mismatch_rows += 1
            examples.extend(row_mismatches)

    return ReplayComparison(
        rows_compared=len(replayed),
        exact_rows=len(replayed) - mismatch_rows,
        mismatch_rows=mismatch_rows,
        field_mismatch_counts=dict(field_counts),
        examples=tuple(examples[:max_examples]),
    )


def _is_true(value: Any) -> bool:
    return _normalize_value("generation_success", value) is True


def aggregate_outcomes(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate testable, successful rows without hiding the row unit."""

    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if not _is_true(row.get("generation_success")) or not _is_true(row.get("outcome_testable")):
            continue
        grouped[(str(row["dmn_type"]), str(row["condition"]))].append(row)

    aggregates: dict[str, Any] = {}
    for (dmn_type, condition), group in sorted(grouped.items()):
        agreements = [float(row["outcome_agreement"]) for row in group if str(row.get("outcome_agreement", "")).strip()]
        tests = sum(float(row["outcome_num_tests"]) for row in group)
        agreed = sum(float(row["outcome_agree_count"]) for row in group)
        key = f"{dmn_type}/{condition}"
        aggregates[key] = {
            "observation_unit": "generation_row",
            "rows": len(group),
            "activities": len({str(row["activity_id"]) for row in group}),
            "test_inputs": int(tests) if tests.is_integer() else tests,
            "agree": int(agreed) if agreed.is_integer() else agreed,
            "disagree": int(tests - agreed) if (tests - agreed).is_integer() else tests - agreed,
            "row_macro_agreement": sum(agreements) / len(agreements) if agreements else None,
            "test_input_weighted_agreement": agreed / tests if tests else None,
        }
    return {
        "inclusion_rule": "generation_success == true and outcome_testable == true",
        "groups": aggregates,
    }


def build_replay_report(
    release_path: str | Path,
    replay_path: str | Path,
    *,
    release_commit: str = PINNED_COMMIT,
    source_repository: str = ANCHOR_REPOSITORY,
) -> dict[str, Any]:
    """Build the retained A1B report from two evaluator CSVs."""

    released_rows = load_metrics(release_path)
    replayed_rows = load_metrics(replay_path)
    comparison = compare_metrics(replayed_rows, released_rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "benchmark_id": "dutch-anchor",
        "status": comparison.status,
        "source_repository": source_repository,
        "release_commit": release_commit,
        "released_metrics": {"rows": len(released_rows), "sha256": sha256_file(release_path)},
        "replayed_metrics": {"rows": len(replayed_rows), "sha256": sha256_file(replay_path)},
        "comparison": comparison.as_dict(),
        "replayed_outcomes": aggregate_outcomes(replayed_rows),
        "released_outcomes": aggregate_outcomes(released_rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--released", required=True, type=Path)
    parser.add_argument("--replayed", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--release-commit", default=PINNED_COMMIT)
    args = parser.parse_args()
    report = build_replay_report(args.released, args.replayed, release_commit=args.release_commit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output)}))
    return 0 if report["status"] == "match" else 2


if __name__ == "__main__":
    raise SystemExit(main())
