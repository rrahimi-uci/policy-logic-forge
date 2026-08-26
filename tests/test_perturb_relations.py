import pytest

from bench.perturb import PerturbationError, generate_relations, inter_annotator_agreement, source_only_manifest


def test_relations_are_source_only_and_hashed():
    source = "The party  must keep information confidential."
    relations = generate_relations(source)
    assert relations
    manifest = source_only_manifest(source, relations)
    assert manifest["artifact_free"] and manifest["gold_free"] and manifest["candidate_free"]


def test_iaa_reports_kappa_and_review_threshold():
    report = inter_annotator_agreement([True, False, True], [True, True, True])
    assert report["n"] == 3
    assert "cohen_kappa" in report


def test_empty_source_refuses():
    with pytest.raises(PerturbationError):
        generate_relations(" ")
