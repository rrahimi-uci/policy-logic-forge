from pathlib import Path
import sys

import pytest


PAPER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PAPER / "scripts"))
import validate_paper  # noqa: E402
import render_checklist  # noqa: E402
import generate_evidence  # noqa: E402


def test_source_contract_passes():
    assert validate_paper.check_source(PAPER / "main.tex") == []


def test_official_template_is_present_and_manifested():
    manifest = PAPER / "template/official/template-manifest.json"
    assert manifest.is_file()
    assert (PAPER / "template/official/neurips_2026.sty").is_file()
    assert validate_paper.sha256(PAPER / "template/official/neurips_2026.sty")


def test_build_check_requires_a_nonempty_pdf(tmp_path):
    errors = validate_paper.check_build(tmp_path)
    assert errors and "missing compiled PDF" in errors[0]


def test_checklist_renderer_removes_instructions_and_todos(tmp_path):
    output = tmp_path / "checklist.tex"
    render_checklist.render(PAPER / "template/official/checklist.tex", output)
    rendered = output.read_text(encoding="utf-8")
    assert "NeurIPS Paper Checklist" in rendered
    assert "%%% BEGIN INSTRUCTIONS %%%" not in rendered
    assert "answerTODO" not in rendered
    assert "justificationTODO" not in rendered


def test_evidence_generator_projects_retained_artifacts(tmp_path):
    macro_path, manifest_path = generate_evidence.generate(PAPER.parent, tmp_path)
    macros = macro_path.read_text(encoding="utf-8")
    manifest = manifest_path.read_text(encoding="utf-8")
    assert r"\newcommand{\RuleRecallMatched}{2}" in macros
    assert r"\newcommand{\ReplayMismatchRows}{792}" in macros
    assert r"\newcommand{\ReplayMismatchPercent}{41.7}" in macros
    assert r"\newcommand{\PrivacyRules}{879}" in macros
    assert r"\newcommand{\PrivacyCertifiedPercent}{12.3}" in macros
    assert "paper-evidence-manifest/1.0" in manifest


@pytest.mark.skipif(
    not (PAPER.parent / "pipeline-output/privacy-policy-full-20260825").is_dir(),
    reason="non-redistributable local pipeline bundle is unavailable",
)
def test_evidence_generator_rejects_stale_local_bundle(tmp_path):
    observation = PAPER / "data/privacy_operational_run.json"
    original = observation.read_text(encoding="utf-8")
    try:
        observation.write_text(original.replace('"rules": 879', '"rules": 878'), encoding="utf-8")
        try:
            generate_evidence.generate(PAPER.parent, tmp_path)
        except ValueError as exc:
            assert "observation mismatch for rules" in str(exc)
        else:
            raise AssertionError("stale observation metadata was accepted")
    finally:
        observation.write_text(original, encoding="utf-8")
