from pathlib import Path
import sys


PAPER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PAPER / "scripts"))
import validate_paper  # noqa: E402
import render_checklist  # noqa: E402


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
