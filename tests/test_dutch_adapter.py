"""BENCH-1 contract tests for the pinned Dutch anchor split."""

from __future__ import annotations

import copy

import pytest

from bench.adapters.dutch_dmn import (
    ManifestValidationError,
    excluded_models,
    included_models,
    load_manifest,
    iter_models,
)


def test_manifest_freezes_the_95_to_58_plus_37_population() -> None:
    manifest = load_manifest()
    included = included_models(manifest)
    excluded = excluded_models(manifest)

    assert manifest["upstream"]["commit"] == "6a4844fb235d4f958d0810bba7089a2e9078099e"
    assert len(tuple(iter_models(manifest))) == 95
    assert len(included) == 58
    assert len(excluded) == 37
    assert {(model.kind, model.activity_id) for model in included}.isdisjoint(
        {(model.kind, model.activity_id) for model in excluded}
    )
    assert sum(model.kind == "Outcome" for model in included) == 24
    assert sum(model.kind == "Requirements" for model in included) == 34


def test_paths_are_pinned_and_requirements_use_the_recorded_gold_family() -> None:
    manifest = load_manifest()
    outcome = next(model for model in included_models(manifest) if model.activity_id == "Parkeergarage")
    requirement = next(model for model in included_models(manifest) if model.activity_id == "BouwwerkSlopen")

    assert outcome.artifact_path("source") == "source_models/Outcome - Parkeergarage.xml"
    assert outcome.artifact_path("gold") == "gold_models/Outcome - Parkeergarage.json"
    assert outcome.artifact_path("generated", condition="srl_conditions", run_id=5) == (
        "generated_models/Outcome/srl_conditions/Parkeergarage_run5.json"
    )
    assert requirement.artifact_path("gold") == "gold_models/SR Permit - BouwwerkSlopen.json"
    assert requirement.artifact_path("source") == "source_models/SR Permit - BouwwerkSlopen.xml"


def test_generated_grid_is_exactly_1900_observations() -> None:
    manifest = load_manifest()
    included = included_models(manifest)
    generated_paths = {
        model.artifact_path("generated", condition=condition, run_id=run_id)
        for model in included
        for condition in manifest["population"]["conditions"]
        for run_id in range(1, manifest["population"]["runs_per_condition"] + 1)
    }

    assert len(generated_paths) == 58 * 4 * 5


def test_invalid_manifest_cannot_change_the_frozen_denominator() -> None:
    manifest = copy.deepcopy(load_manifest())
    manifest["families"]["Outcome"]["included"].pop()

    with pytest.raises(ManifestValidationError, match="Outcome.included/.excluded do not partition"):
        tuple(iter_models(manifest))


def test_exclusions_are_explicit_and_explainable() -> None:
    excluded = excluded_models()

    assert excluded
    assert all(model.exclusion_reason for model in excluded)
    assert any(model.activity_id == "PropaanOpslaan" for model in excluded)
    assert any(model.activity_id == "Dakkapel" for model in excluded)
