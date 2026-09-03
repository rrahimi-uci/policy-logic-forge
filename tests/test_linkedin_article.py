"""Regression checks for the repository-grounded LinkedIn article package."""

from __future__ import annotations

import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

from utils.agent_names import PIPELINE_AGENTS, PIPELINE_STAGE_COUNT


ROOT = Path(__file__).resolve().parents[1]
ARTICLE_DIR = ROOT / "linkedin-article"
ARTICLE = ARTICLE_DIR / "policy-logic-forge-linkedin-article.md"
PUBLISHING_KIT = ARTICLE_DIR / "publishing-kit.md"

VISUAL_STEMS = (
    "01-policy-logic-forge-hero",
    "02-policy-translation-gap",
    "03-capabilities-evidence-spine",
    "04-policy-logic-forge-architecture",
    "05-standards-by-question",
    "06-policy-to-code-infographic",
)

TECHNICAL_GROUNDING_FILES = (
    "utils/agent_names.py",
    "utils/rule_contract.py",
    "utils/rule_dependencies.py",
    "utils/kg_readiness.py",
    "agents/agent_09_grounding_verifier.py",
    "utils/dag_builder.py",
    "utils/executable_models.py",
    "utils/semantic_artifacts.py",
    "utils/information_model.py",
    "agents/agent_13_business_knowledge_report.py",
    "utils/regdelta_engine.py",
)


def _png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_article_tracks_the_canonical_pipeline_contract() -> None:
    article = ARTICLE.read_text(encoding="utf-8")
    kit = PUBLISHING_KIT.read_text(encoding="utf-8")

    assert PIPELINE_STAGE_COUNT == 13
    assert len(PIPELINE_AGENTS) == 13
    assert "13-stage" in article
    assert "13-stage" in kit
    assert "12-stage" not in article
    assert "12-stage" not in kit
    assert "Stage 13" in article


def test_article_states_important_claim_boundaries() -> None:
    article = ARTICLE.read_text(encoding="utf-8")

    required_boundaries = (
        "not a full collaborative workflow application",
        "not full SBVR interchange conformance",
        "LExec is an internal IR",
        "Current alignment is exact-ID based",
        "No numerical extraction-quality benchmark is claimed",
        "machine-readable is not the same as production-ready",
    )
    for boundary in required_boundaries:
        assert boundary.casefold() in article.casefold()


def test_article_visual_references_exist_and_use_the_new_story_set() -> None:
    article = ARTICLE.read_text(encoding="utf-8")
    referenced = set(re.findall(r"!\[[^]]*]\((images/[^)]+)\)", article))
    expected = {f"images/{stem}.png" for stem in VISUAL_STEMS}

    assert referenced == expected
    for relative_path in referenced:
        assert (ARTICLE_DIR / relative_path).is_file()


def test_visual_masters_are_valid_and_pngs_are_publication_resolution() -> None:
    for stem in VISUAL_STEMS:
        svg_path = ARTICLE_DIR / "images" / f"{stem}.svg"
        png_path = ARTICLE_DIR / "images" / f"{stem}.png"

        root = ET.parse(svg_path).getroot()
        assert root.tag.endswith("svg")
        assert root.find("{http://www.w3.org/2000/svg}title") is not None
        assert root.find("{http://www.w3.org/2000/svg}desc") is not None

        expected_dimensions = (2160, 2700) if stem.startswith("06-") else (3200, 1800)
        assert _png_dimensions(png_path) == expected_dimensions


def test_technical_grounding_links_point_to_repository_files() -> None:
    article = ARTICLE.read_text(encoding="utf-8")

    for relative_path in TECHNICAL_GROUNDING_FILES:
        assert (ROOT / relative_path).is_file()
        expected_url = (
            "https://github.com/rrahimi-uci/policy-logic-forge/blob/main/"
            f"{relative_path}"
        )
        assert expected_url in article
