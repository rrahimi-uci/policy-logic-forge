"""Pinned metadata adapter for the Dutch DMN anchor corpus.

The upstream release is intentionally not vendored.  This adapter makes the
population, evaluator-compatible 58/37 split, path conventions, conditions,
and run count explicit so a later evaluator can consume a checked-out or
approved local copy without silently changing the denominator.

The split is a metadata contract, not an evaluation result.  In particular,
``included`` means that the pinned upstream evaluator can enumerate its gold
model's inputs within its declared limit; it does not mean that a generated
model is correct or that an outcome has been reproduced here.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping


DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "splits" / "dutch_58.json"
EXPECTED_SCHEMA_VERSION = "dutch-anchor-split/1.0"
FAMILIES = ("Outcome", "Requirements")
_SAFE_ACTIVITY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_]+$")


class ManifestValidationError(ValueError):
    """Raised when a frozen anchor manifest is malformed or inconsistent."""


@dataclass(frozen=True)
class DutchModel:
    """One model in the pinned 95-model population."""

    kind: str
    activity_id: str
    included: bool
    gold_family: str
    manifest: Mapping[str, Any]

    @property
    def exclusion_reason(self) -> str | None:
        if self.included:
            return None
        return self.manifest["selection_basis"][f"excluded_{self.kind.lower()}"]

    def artifact_path(self, artifact: str, *, condition: str | None = None,
                      run_id: int | None = None) -> str:
        """Resolve one pinned upstream-relative artifact path.

        ``source`` and ``gold`` identify one model artifact.  ``generated``
        requires one of the four frozen conditions and one run in 1..5.
        Paths are returned for lookup only; this method never downloads data.
        """
        if artifact not in {"source", "gold", "generated"}:
            raise ValueError(f"unknown artifact kind: {artifact}")
        if not _SAFE_ACTIVITY_ID.fullmatch(self.activity_id):
            raise ManifestValidationError(f"unsafe activity id: {self.activity_id!r}")
        templates = self.manifest["path_templates"]
        if artifact == "generated":
            conditions = self.manifest["population"]["conditions"]
            if condition not in conditions:
                raise ValueError(f"condition must be one of {conditions!r}: {condition!r}")
            runs = self.manifest["population"]["runs_per_condition"]
            if not isinstance(run_id, int) or not 1 <= run_id <= runs:
                raise ValueError(f"run_id must be an integer in 1..{runs}: {run_id!r}")
            return templates[artifact].format(
                kind=self.kind,
                condition=condition,
                activity_id=self.activity_id,
                run_id=run_id,
            )
        return templates[artifact][self.kind].format(
            activity_id=self.activity_id,
            gold_family=self.gold_family,
        )


def _error(message: str) -> None:
    raise ManifestValidationError(message)


def _validate_manifest(manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        _error(f"schema_version must be {EXPECTED_SCHEMA_VERSION!r}")
    upstream = manifest.get("upstream")
    if not isinstance(upstream, Mapping) or not re.fullmatch(r"[0-9a-f]{40}", str(upstream.get("commit", ""))):
        _error("upstream.commit must be a 40-character lowercase SHA-1")

    population = manifest.get("population")
    if not isinstance(population, Mapping):
        _error("population must be an object")
    conditions = population.get("conditions")
    if conditions != ["baseline", "srl", "conditions", "srl_conditions"]:
        _error("population.conditions must preserve the four pinned upstream conditions")
    if population.get("runs_per_condition") != 5:
        _error("population.runs_per_condition must be 5")

    families = manifest.get("families")
    if not isinstance(families, Mapping) or set(families) != set(FAMILIES):
        _error(f"families must contain exactly {FAMILIES!r}")
    observed_total = observed_included = observed_excluded = 0
    for kind in FAMILIES:
        family = families[kind]
        if not isinstance(family, Mapping):
            _error(f"family {kind} must be an object")
        all_ids = family.get("all")
        included = family.get("included")
        excluded = family.get("excluded")
        for label, values in (("all", all_ids), ("included", included), ("excluded", excluded)):
            if not isinstance(values, list) or not values or any(
                not isinstance(value, str) or not _SAFE_ACTIVITY_ID.fullmatch(value) for value in values
            ):
                _error(f"{kind}.{label} must contain safe non-empty activity IDs")
            if len(values) != len(set(values)):
                _error(f"{kind}.{label} contains duplicate activity IDs")
        if set(included) & set(excluded):
            _error(f"{kind}.included and .excluded overlap")
        if set(included) | set(excluded) != set(all_ids):
            _error(f"{kind}.included/.excluded do not partition .all")
        sorted_ids = lambda values: sorted(values, key=str.casefold)
        if all_ids != sorted_ids(all_ids) or included != sorted_ids(included) or excluded != sorted_ids(excluded):
            _error(f"{kind} activity IDs must be sorted for deterministic manifests")
        if kind == "Outcome" and len(included) != 24:
            _error("Outcome included split must contain 24 models")
        if kind == "Requirements" and len(included) != 34:
            _error("Requirements included split must contain 34 models")
        if kind == "Requirements":
            mapping = family.get("gold_family_by_activity")
            if not isinstance(mapping, Mapping) or set(mapping) != set(all_ids):
                _error("Requirements.gold_family_by_activity must cover every model")
            if any(value not in family.get("gold_families", []) for value in mapping.values()):
                _error("Requirements gold-family mapping contains an unknown family")
        observed_total += len(all_ids)
        observed_included += len(included)
        observed_excluded += len(excluded)

    expected = {
        "models": observed_total,
        "included": observed_included,
        "excluded": observed_excluded,
    }
    for key, value in expected.items():
        if population.get(key) != value:
            _error(f"population.{key}={population.get(key)!r} does not equal observed {value}")
    expected_observations = observed_total * len(conditions) * population["runs_per_condition"]
    if population.get("expected_generated_observations") != expected_observations:
        _error("population.expected_generated_observations does not match the frozen grid")

    templates = manifest.get("path_templates")
    if not isinstance(templates, Mapping) or set(templates) != {"source", "gold", "generated"}:
        _error("path_templates must define source, gold, and generated paths")
    if "{activity_id}" not in str(templates["generated"]):
        _error("generated path template must contain {activity_id}")


def load_manifest(path: str | Path = DEFAULT_MANIFEST) -> Mapping[str, Any]:
    """Load and validate the pinned split manifest."""
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(manifest, Mapping):
        _error("manifest root must be an object")
    _validate_manifest(manifest)
    return manifest


def iter_models(manifest: Mapping[str, Any] | None = None, *, kind: str | None = None,
                included: bool | None = None) -> Iterator[DutchModel]:
    """Yield deterministic model references filtered by family and inclusion."""
    checked = manifest if manifest is not None else load_manifest()
    _validate_manifest(checked)
    kinds: Iterable[str] = FAMILIES if kind is None else (kind,)
    for selected_kind in kinds:
        if selected_kind not in FAMILIES:
            raise ValueError(f"kind must be one of {FAMILIES!r}: {selected_kind!r}")
        family = checked["families"][selected_kind]
        included_ids = set(family["included"])
        gold_family = family.get("gold_family")
        gold_by_activity = family.get("gold_family_by_activity", {})
        for activity_id in family["all"]:
            is_included = activity_id in included_ids
            if included is not None and is_included != included:
                continue
            yield DutchModel(
                kind=selected_kind,
                activity_id=activity_id,
                included=is_included,
                gold_family=gold_family or gold_by_activity[activity_id],
                manifest=checked,
            )


def included_models(manifest: Mapping[str, Any] | None = None) -> tuple[DutchModel, ...]:
    """Return the frozen 58-model executable subset."""
    return tuple(iter_models(manifest, included=True))


def excluded_models(manifest: Mapping[str, Any] | None = None) -> tuple[DutchModel, ...]:
    """Return the explicit 37-model exclusion set."""
    return tuple(iter_models(manifest, included=False))
