"""Deterministic semantic-rule recall evaluation for a frozen annotation frame.

The evaluator deliberately separates fixture wiring from research evidence.  A
frame is accepted only when it contains two annotator files, an explicit
adjudication file, source hashes, and prediction records.  The checked-in
fixture is marked ``fixture_only`` because it is synthetic and not a human
annotated corpus sample; it exercises the contract without authorizing a
semantic recall claim.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping


REQUIRED_RULE_FIELDS = ("rule_key", "source_id", "rule_type", "subject", "action", "object")
SEMANTIC_FIELDS = ("source_id", "rule_type", "subject", "action", "object")


class RuleRecallError(ValueError):
    """Raised when a frozen recall frame violates its provenance contract."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuleRecallError(f"cannot read JSON fixture {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuleRecallError(f"fixture {path} must contain a JSON object")
    return value


def _normalise_text(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _rule_signature(rule: Mapping[str, Any]) -> tuple[str, ...]:
    missing = [field for field in REQUIRED_RULE_FIELDS if not str(rule.get(field, "")).strip()]
    if missing:
        raise RuleRecallError(f"rule is missing required fields: {', '.join(missing)}")
    # Rule IDs are annotator/model-local identifiers and must not affect a
    # semantic match.  Matching on them would turn equivalent annotations
    # with different IDs into false negatives.
    return tuple(_normalise_text(rule[field]) for field in SEMANTIC_FIELDS)


def _validate_rules(rules: Any, *, label: str) -> list[dict[str, Any]]:
    if not isinstance(rules, list):
        raise RuleRecallError(f"{label}.rules must be a list")
    checked: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for index, raw in enumerate(rules):
        if not isinstance(raw, Mapping):
            raise RuleRecallError(f"{label}.rules[{index}] must be an object")
        rule = dict(raw)
        signature = _rule_signature(rule)
        if signature in seen:
            raise RuleRecallError(f"{label}.rules contains duplicate semantic rule {signature[0]!r}")
        seen.add(signature)
        checked.append(rule)
    return checked


def _validate_source_manifest(frame: Mapping[str, Any], fixture_dir: Path) -> dict[str, dict[str, Any]]:
    sources = frame.get("source_manifest")
    if not isinstance(sources, list) or not sources:
        raise RuleRecallError("source_manifest must be a non-empty list")
    indexed: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(sources):
        if not isinstance(raw, Mapping):
            raise RuleRecallError(f"source_manifest[{index}] must be an object")
        source_id = str(raw.get("source_id", "")).strip()
        relative_path = str(raw.get("path", "")).strip()
        expected_hash = str(raw.get("sha256", "")).strip()
        if not source_id or not relative_path or len(expected_hash) != 64:
            raise RuleRecallError(f"source_manifest[{index}] needs source_id, path, and sha256")
        if source_id in indexed:
            raise RuleRecallError(f"duplicate source_id {source_id!r}")
        path = (fixture_dir / relative_path).resolve()
        if fixture_dir.resolve() not in path.parents:
            raise RuleRecallError(f"source path escapes fixture directory: {relative_path}")
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise RuleRecallError(f"cannot read source {relative_path}: {exc}") from exc
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != expected_hash:
            raise RuleRecallError(f"source hash mismatch for {source_id}: expected {expected_hash}, got {actual_hash}")
        entry = dict(raw)
        entry["path"] = relative_path
        entry["content"] = content.decode("utf-8")
        indexed[source_id] = entry
    return indexed


def _validate_rule_sources(rules: list[dict[str, Any]], sources: Mapping[str, Mapping[str, Any]], label: str) -> None:
    for index, rule in enumerate(rules):
        source_id = str(rule["source_id"])
        source = sources.get(source_id)
        if source is None:
            raise RuleRecallError(f"{label}.rules[{index}] references unknown source_id {source_id!r}")
        quote = str(rule.get("source_quote", "")).strip()
        if not quote:
            raise RuleRecallError(f"{label}.rules[{index}] must include source_quote")
        if quote not in str(source["content"]):
            raise RuleRecallError(f"{label}.rules[{index}] source_quote is not present in {source_id}")


def _wilson_interval(successes: int, trials: int, *, z: float = 1.959963984540054) -> dict[str, Any]:
    """Return a descriptive 95% Wilson interval for one frozen frame.

    The interval is deliberately labeled frame-level: PIPE-2B cannot turn it
    into a corpus estimate without the declared stratified sampling weights and
    a licensed real annotation frame.
    """

    if trials < 0 or successes < 0 or successes > trials:
        raise RuleRecallError("interval successes/trials must satisfy 0 <= successes <= trials")
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


def _annotator_agreement(annotators: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize semantic-key agreement without treating it as legal IAA."""

    semantic_sets = [
        {_rule_signature(rule) for rule in record["rules"]}
        for record in annotators
    ]
    union = set.union(*semantic_sets) if semantic_sets else set()
    intersection = set.intersection(*semantic_sets) if semantic_sets else set()
    return {
        "metric": "semantic_key_jaccard",
        "annotator_count": len(semantic_sets),
        "annotator_rule_counts": [len(values) for values in semantic_sets],
        "intersection": len(intersection),
        "union": len(union),
        "jaccard": len(intersection) / len(union) if union else 1.0,
        "exact_set_agreement": bool(semantic_sets) and all(values == semantic_sets[0] for values in semantic_sets[1:]),
        "interpretation": "descriptive semantic-key agreement; chance-corrected IAA remains a real-frame requirement",
    }


def load_frame(fixture_dir: str | Path) -> dict[str, Any]:
    """Load and validate a complete frozen frame from ``fixture_dir``."""

    root = Path(fixture_dir).resolve()
    frame = _read_json(root / "frame.json")
    if frame.get("schema_version") != "1.0":
        raise RuleRecallError("frame.schema_version must be '1.0'")
    if frame.get("evidence_status") != "fixture_only":
        raise RuleRecallError("PIPE-2B fixtures must declare evidence_status='fixture_only'")

    sources = _validate_source_manifest(frame, root)
    annotators = frame.get("annotators")
    if not isinstance(annotators, list) or len(annotators) != 2:
        raise RuleRecallError("exactly two annotator records are required")
    annotator_ids = set()
    for index, record in enumerate(annotators):
        if not isinstance(record, Mapping):
            raise RuleRecallError(f"annotators[{index}] must be an object")
        annotator_id = str(record.get("annotator_id", "")).strip()
        if not annotator_id or annotator_id in annotator_ids:
            raise RuleRecallError("annotator IDs must be present and unique")
        if record.get("independent") is not True:
            raise RuleRecallError(f"annotators[{index}] must declare independent=true")
        annotator_ids.add(annotator_id)
        rules = _validate_rules(record.get("rules"), label=f"annotators[{index}]")
        _validate_rule_sources(rules, sources, f"annotators[{index}]")

    adjudication = frame.get("adjudication")
    if not isinstance(adjudication, Mapping):
        raise RuleRecallError("adjudication record is required")
    if str(adjudication.get("method", "")).strip() == "":
        raise RuleRecallError("adjudication.method is required")
    adjudicated_rules = _validate_rules(adjudication.get("rules"), label="adjudication")
    _validate_rule_sources(adjudicated_rules, sources, "adjudication")

    predictions = _validate_rules(frame.get("predictions"), label="predictions")
    _validate_rule_sources(predictions, sources, "predictions")
    result = dict(frame)
    result["fixture_dir"] = str(root)
    result["sources"] = sources
    result["adjudicated_rules"] = adjudicated_rules
    result["predictions"] = predictions
    return result


def evaluate_frame(frame: Mapping[str, Any]) -> dict[str, Any]:
    """Return deterministic precision/recall metrics for a validated frame."""

    gold = [_rule_signature(rule) for rule in frame["adjudicated_rules"]]
    predictions = [_rule_signature(rule) for rule in frame["predictions"]]
    gold_set, prediction_set = set(gold), set(predictions)
    matched = gold_set & prediction_set
    missing = gold_set - prediction_set
    false_positives = prediction_set - gold_set
    per_source: dict[str, dict[str, Any]] = {}
    source_ids = sorted({signature[0] for signature in gold + predictions})
    for source_id in source_ids:
        source_gold = {signature for signature in gold_set if signature[0] == source_id}
        source_predictions = {signature for signature in prediction_set if signature[0] == source_id}
        source_matched = source_gold & source_predictions
        per_source[source_id] = {
            "gold": len(source_gold),
            "predicted": len(source_predictions),
            "matched": len(source_matched),
            "recall": len(source_matched) / len(source_gold) if source_gold else None,
            "precision": len(source_matched) / len(source_predictions) if source_predictions else None,
            "recall_uncertainty": _wilson_interval(len(source_matched), len(source_gold)),
            "precision_uncertainty": _wilson_interval(len(source_matched), len(source_predictions)),
        }

    return {
        "status": "fixture_only",
        "evidence_status": frame["evidence_status"],
        "claim_boundary": frame["claim_boundary"],
        "gold_rules": len(gold_set),
        "predicted_rules": len(prediction_set),
        "matched_rules": len(matched),
        "missing_rules": len(missing),
        "false_positive_rules": len(false_positives),
        "recall": len(matched) / len(gold_set) if gold_set else None,
        "precision": len(matched) / len(prediction_set) if prediction_set else None,
        "recall_uncertainty": _wilson_interval(len(matched), len(gold_set)),
        "precision_uncertainty": _wilson_interval(len(matched), len(prediction_set)),
        "missing_rule_keys": sorted(
            str(rule["rule_key"])
            for rule in frame["adjudicated_rules"]
            if _rule_signature(rule) in missing
        ),
        "false_positive_rule_keys": sorted(
            str(rule["rule_key"])
            for rule in frame["predictions"]
            if _rule_signature(rule) in false_positives
        ),
        "per_source": per_source,
        "annotator_count": len(frame["annotators"]),
        "annotator_agreement": _annotator_agreement(frame["annotators"]),
        "adjudication_method": frame["adjudication"]["method"],
    }


def evaluate_fixture(fixture_dir: str | Path) -> dict[str, Any]:
    return evaluate_frame(load_frame(fixture_dir))
