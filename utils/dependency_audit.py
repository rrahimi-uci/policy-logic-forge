"""Deterministic dependency precision/recall evaluation for a frozen frame.

The evaluator requires a declared rule universe, explicit negative edge cases,
two independent annotations, and adjudication.  The checked-in frame is
synthetic and marked ``fixture_only``; it validates the audit contract without
making a dependency-quality claim about the compliance corpus.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping


DEPENDENCY_TYPES = {
    "prerequisite",
    "sequential",
    "conditional",
    "complementary",
    "contradictory",
    "override",
}


class DependencyAuditError(ValueError):
    """Raised when a dependency audit frame violates its provenance contract."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DependencyAuditError(f"cannot read JSON fixture {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DependencyAuditError(f"fixture {path} must contain a JSON object")
    return value


def _edge_key(edge: Mapping[str, Any]) -> tuple[str, str, str]:
    source = edge.get("source_rule_id")
    target = edge.get("target_rule_id")
    kind = edge.get("dependency_type")
    if (
        not isinstance(source, str)
        or not source.strip()
        or not isinstance(target, str)
        or not target.strip()
        or not isinstance(kind, str)
        or not kind.strip()
    ):
        raise DependencyAuditError("every dependency edge needs source_rule_id, target_rule_id, and dependency_type")
    return source.strip(), target.strip(), kind.strip().lower()


def _validate_rule_ids(raw_ids: Any) -> set[str]:
    if not isinstance(raw_ids, list):
        raise DependencyAuditError("universe.rule_ids must be a list of non-empty strings")
    rule_ids: set[str] = set()
    for index, raw_id in enumerate(raw_ids):
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise DependencyAuditError(f"universe.rule_ids[{index}] must be a non-empty string")
        rule_id = raw_id.strip()
        if rule_id in rule_ids:
            raise DependencyAuditError(f"universe.rule_ids contains duplicate rule ID {rule_id!r}")
        rule_ids.add(rule_id)
    if len(rule_ids) < 2:
        raise DependencyAuditError("universe.rule_ids must contain at least two rules")
    return rule_ids


def _validate_candidate_edges(raw_edges: Any, *, rule_ids: set[str]) -> set[tuple[str, str, str]]:
    if not isinstance(raw_edges, list) or not raw_edges:
        raise DependencyAuditError("universe.candidate_edges must be a non-empty list")
    candidate_edges: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(raw_edges):
        if not isinstance(raw, Mapping):
            raise DependencyAuditError(f"universe.candidate_edges[{index}] must be an object")
        key = _edge_key(raw)
        source, target, kind = key
        if source == target:
            raise DependencyAuditError(f"universe.candidate_edges[{index}] contains a self-loop: {source}")
        if source not in rule_ids or target not in rule_ids:
            raise DependencyAuditError(
                f"universe.candidate_edges[{index}] references a rule outside the declared universe"
            )
        if kind not in DEPENDENCY_TYPES:
            raise DependencyAuditError(
                f"universe.candidate_edges[{index}] has unsupported dependency_type {kind!r}"
            )
        if key in candidate_edges:
            raise DependencyAuditError(f"universe.candidate_edges contains duplicate edge {key}")
        candidate_edges.add(key)
    return candidate_edges


def _validate_edges(
    edges: Any,
    *,
    label: str,
    rule_ids: set[str],
    candidate_edges: set[tuple[str, str, str]],
    allow_empty: bool = True,
) -> list[dict[str, Any]]:
    if not isinstance(edges, list):
        raise DependencyAuditError(f"{label} must be a list")
    if not allow_empty and not edges:
        raise DependencyAuditError(f"{label} must not be empty")
    checked: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(edges):
        if not isinstance(raw, Mapping):
            raise DependencyAuditError(f"{label}[{index}] must be an object")
        edge = dict(raw)
        key = _edge_key(edge)
        source, target, kind = key
        if source == target:
            raise DependencyAuditError(f"{label}[{index}] contains a self-loop: {source}")
        if source not in rule_ids or target not in rule_ids:
            raise DependencyAuditError(f"{label}[{index}] references a rule outside the declared universe")
        if kind not in DEPENDENCY_TYPES:
            raise DependencyAuditError(f"{label}[{index}] has unsupported dependency_type {kind!r}")
        if key not in candidate_edges:
            raise DependencyAuditError(f"{label}[{index}] is outside the declared candidate-edge universe")
        if key in seen:
            raise DependencyAuditError(f"{label} contains duplicate edge {key}")
        seen.add(key)
        edge["source_rule_id"] = source
        edge["target_rule_id"] = target
        edge["dependency_type"] = kind
        checked.append(edge)
    return checked


def _edge_set(edges: list[Mapping[str, Any]]) -> set[tuple[str, str, str]]:
    return {_edge_key(edge) for edge in edges}


def _require_complete_labels(
    positive_edges: list[Mapping[str, Any]],
    negative_edges: list[Mapping[str, Any]],
    *,
    label: str,
    candidate_edges: set[tuple[str, str, str]],
) -> None:
    """Require exactly one binary label for every candidate edge."""

    positive = _edge_set(positive_edges)
    negative = _edge_set(negative_edges)
    overlap = positive & negative
    if overlap:
        raise DependencyAuditError(f"{label} labels an edge both positive and negative: {sorted(overlap)[0]}")
    missing = candidate_edges - (positive | negative)
    if missing:
        raise DependencyAuditError(
            f"{label} must label every candidate edge exactly once; missing {sorted(missing)[0]}"
        )


def _wilson_interval(successes: int, trials: int, *, z: float = 1.959963984540054) -> dict[str, Any]:
    """Return a descriptive 95% Wilson interval for one frozen frame."""

    if trials < 0 or successes < 0 or successes > trials:
        raise DependencyAuditError("interval successes/trials must satisfy 0 <= successes <= trials")
    if trials == 0:
        return {
            "method": "wilson_95_binomial",
            "confidence": 0.95,
            "successes": successes,
            "trials": trials,
            "lower": None,
            "upper": None,
            "interpretation": "descriptive frame-level interval; not a population estimate",
        }
    proportion = successes / trials
    z_squared = z * z
    denominator = 1 + z_squared / trials
    center = (proportion + z_squared / (2 * trials)) / denominator
    margin = z / denominator * math.sqrt(
        proportion * (1 - proportion) / trials + z_squared / (4 * trials * trials)
    )
    return {
        "method": "wilson_95_binomial",
        "confidence": 0.95,
        "successes": successes,
        "trials": trials,
        "lower": max(0.0, center - margin),
        "upper": min(1.0, center + margin),
        "interpretation": "descriptive frame-level interval; not a population estimate",
    }


def load_frame(fixture_dir: str | Path) -> dict[str, Any]:
    """Load and validate a complete dependency audit frame."""

    root = Path(fixture_dir).resolve()
    frame = _read_json(root / "frame.json")
    if frame.get("schema_version") != "1.0":
        raise DependencyAuditError("frame.schema_version must be '1.0'")
    if frame.get("evidence_status") != "fixture_only":
        raise DependencyAuditError("PIPE-4 fixtures must declare evidence_status='fixture_only'")
    if not isinstance(frame.get("claim_boundary"), str) or not frame["claim_boundary"].strip():
        raise DependencyAuditError("frame.claim_boundary must be a non-empty string")

    universe = frame.get("universe")
    if not isinstance(universe, Mapping):
        raise DependencyAuditError("universe is required")
    rule_ids = _validate_rule_ids(universe.get("rule_ids"))
    candidate_edges = _validate_candidate_edges(universe.get("candidate_edges"), rule_ids=rule_ids)
    negative_edges = _validate_edges(
        universe.get("negative_edges"),
        label="universe.negative_edges",
        rule_ids=rule_ids,
        candidate_edges=candidate_edges,
    )
    negative_set = _edge_set(negative_edges)
    if not negative_set.issubset(candidate_edges):
        raise DependencyAuditError("negative_edges must be contained in candidate_edges")

    annotators = frame.get("annotators")
    if not isinstance(annotators, list) or len(annotators) != 2:
        raise DependencyAuditError("exactly two annotator records are required")
    annotator_ids: set[str] = set()
    checked_annotators: list[dict[str, Any]] = []
    for index, record in enumerate(annotators):
        if not isinstance(record, Mapping):
            raise DependencyAuditError(f"annotators[{index}] must be an object")
        annotator_id = record.get("annotator_id")
        if (
            not isinstance(annotator_id, str)
            or not annotator_id.strip()
            or annotator_id.strip() in annotator_ids
        ):
            raise DependencyAuditError("annotator IDs must be present and unique")
        annotator_id = annotator_id.strip()
        if record.get("independent") is not True:
            raise DependencyAuditError(f"annotators[{index}] must declare independent=true")
        annotator_ids.add(annotator_id)
        checked_annotators.append({
            **dict(record),
            "edges": _validate_edges(
                record.get("edges"), label=f"annotators[{index}].edges", rule_ids=rule_ids, candidate_edges=candidate_edges
            ),
            "negative_edges": _validate_edges(
                record.get("negative_edges"), label=f"annotators[{index}].negative_edges", rule_ids=rule_ids, candidate_edges=candidate_edges
            ),
        })
        _require_complete_labels(
            checked_annotators[-1]["edges"],
            checked_annotators[-1]["negative_edges"],
            label=f"annotators[{index}]",
            candidate_edges=candidate_edges,
        )

    adjudication = frame.get("adjudication")
    if (
        not isinstance(adjudication, Mapping)
        or not isinstance(adjudication.get("method"), str)
        or not adjudication["method"].strip()
    ):
        raise DependencyAuditError("adjudication with a method is required")
    checked_adjudication = {
        **dict(adjudication),
        "edges": _validate_edges(
            adjudication.get("edges"), label="adjudication.edges", rule_ids=rule_ids, candidate_edges=candidate_edges
        ),
        "negative_edges": _validate_edges(
            adjudication.get("negative_edges"), label="adjudication.negative_edges", rule_ids=rule_ids, candidate_edges=candidate_edges
        ),
    }
    _require_complete_labels(
        checked_adjudication["edges"],
        checked_adjudication["negative_edges"],
        label="adjudication",
        candidate_edges=candidate_edges,
    )
    adjudicated_positive = _edge_set(checked_adjudication["edges"])
    adjudicated_negative = _edge_set(checked_adjudication["negative_edges"])
    if adjudicated_positive & adjudicated_negative:
        raise DependencyAuditError("an adjudicated edge cannot be both positive and negative")

    predictions = _validate_edges(
        frame.get("predictions"), label="predictions", rule_ids=rule_ids, candidate_edges=candidate_edges
    )
    result = dict(frame)
    result["rule_ids"] = sorted(rule_ids)
    result["candidate_edges"] = candidate_edges
    result["negative_edges"] = negative_edges
    result["annotators"] = checked_annotators
    result["adjudication"] = checked_adjudication
    result["predictions"] = predictions
    return result


def evaluate_frame(frame: Mapping[str, Any]) -> dict[str, Any]:
    gold = _edge_set(frame["adjudication"]["edges"])
    negatives = _edge_set(frame["adjudication"]["negative_edges"])
    predictions = _edge_set(frame["predictions"])
    matched = gold & predictions
    false_positives = predictions - gold
    missing = gold - predictions
    annotator_positive_sets = [_edge_set(record["edges"]) for record in frame["annotators"]]
    annotator_negative_sets = [_edge_set(record["negative_edges"]) for record in frame["annotators"]]
    positive_union = set.union(*annotator_positive_sets)
    negative_union = set.union(*annotator_negative_sets)
    positive_intersection = set.intersection(*annotator_positive_sets)
    negative_intersection = set.intersection(*annotator_negative_sets)
    positive_iaa = len(positive_intersection) / len(positive_union) if positive_union else 1.0
    negative_iaa = len(negative_intersection) / len(negative_union) if negative_union else 1.0
    exact_label_set_agreement = all(
        _edge_set(record["edges"]) == annotator_positive_sets[0]
        and _edge_set(record["negative_edges"]) == annotator_negative_sets[0]
        for record in frame["annotators"][1:]
    )
    return {
        "status": "fixture_only",
        "evidence_status": frame["evidence_status"],
        "claim_boundary": frame["claim_boundary"],
        "rule_universe_size": len(frame["rule_ids"]),
        "candidate_edge_count": len(frame["candidate_edges"]),
        "declared_negative_edges": len(negatives),
        "gold_edges": len(gold),
        "predicted_edges": len(predictions),
        "matched_edges": len(matched),
        "missing_edges": len(missing),
        "false_positive_edges": len(false_positives),
        "recall": len(matched) / len(gold) if gold else None,
        "precision": len(matched) / len(predictions) if predictions else None,
        "recall_uncertainty": _wilson_interval(len(matched), len(gold)),
        "precision_uncertainty": _wilson_interval(len(matched), len(predictions)),
        "missing_edge_keys": [list(edge) for edge in sorted(missing)],
        "false_positive_edge_keys": [list(edge) for edge in sorted(false_positives)],
        "annotator_count": len(frame["annotators"]),
        "positive_edge_iaa_jaccard": positive_iaa,
        "negative_edge_iaa_jaccard": negative_iaa,
        "annotator_agreement": {
            "metric": "typed_edge_label_jaccard",
            "annotator_count": len(frame["annotators"]),
            "positive_jaccard": positive_iaa,
            "negative_jaccard": negative_iaa,
            "exact_label_set_agreement": exact_label_set_agreement,
            "interpretation": "descriptive edge-label agreement; chance-corrected IAA remains a real-frame requirement",
        },
        "adjudication_method": frame["adjudication"]["method"],
    }


def evaluate_fixture(fixture_dir: str | Path) -> dict[str, Any]:
    return evaluate_frame(load_frame(fixture_dir))
