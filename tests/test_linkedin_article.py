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
    "07-verification-ladder",
)

# The article is a claim that this repository does what it says, so it must
# keep pointing at the code that backs each claim.  Editorial rewrites may
# reasonably swap *which* module illustrates a point -- what must not happen
# is the article drifting into unsourced assertion, or linking a file that
# no longer exists.  So this list is the floor, not the exact set: every
# entry must stay linked, and separately every link in the article must
# resolve to a real file.
TECHNICAL_GROUNDING_FILES = (
    "utils/agent_names.py",
    "utils/rule_contract.py",
    "utils/rule_dependencies.py",
    "utils/kg_readiness.py",
    "agents/agent_09_grounding_verifier.py",
    "utils/dag_builder.py",
    "utils/executable_models.py",
    "utils/semantic_artifacts.py",
    "agents/agent_13_business_knowledge_report.py",
    "utils/regdelta_engine.py",
)

BLOB_PREFIX = "https://github.com/rrahimi-uci/policy-logic-forge/blob/main/"


def _png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_article_states_no_stale_pipeline_stage_count() -> None:
    """The article deliberately states no stage count at all.

    Describing the pipeline by its responsibilities rather than by a number
    is an editorial decision recorded in ``publishing-kit.md``: a count
    invites "why that many?" instead of "what does each boundary catch?".

    So the guard is inverted from what it used to be.  Rather than requiring
    the article to name the current count -- which made every rewrite a test
    failure -- it requires that no *wrong* count appears.  A stale "11-stage"
    left behind by a rewrite is the actual failure mode worth catching.
    """
    article = ARTICLE.read_text(encoding="utf-8")
    kit = PUBLISHING_KIT.read_text(encoding="utf-8")

    assert PIPELINE_STAGE_COUNT == 13
    assert len(PIPELINE_AGENTS) == 13

    stale = re.compile(r"\b(\d+)[- ](?:stage|agent)\b", re.IGNORECASE)
    for name, text in (("article", article), ("publishing kit", kit)):
        wrong = {n for n in stale.findall(text) if int(n) != PIPELINE_STAGE_COUNT}
        assert not wrong, (
            f"{name} names stage/agent count(s) {sorted(wrong)}, but the "
            f"pipeline has {PIPELINE_STAGE_COUNT} stages"
        )


def test_article_states_important_claim_boundaries() -> None:
    """The article must keep disclaiming what it does not establish.

    These are the piece's credibility, not boilerplate.  Each entry below is
    a short fragment of a boundary the article has to keep making; the
    phrasings are deliberately short so an editorial rewrite does not break
    them, but if one *does* break, the fix is to update the fragment to the
    new wording -- never to delete the entry.  Dropping a boundary is the
    regression this test exists to catch.
    """
    article = ARTICLE.read_text(encoding="utf-8").casefold()

    required_boundaries = (
        # it is a pipeline, not a product
        "not a hosted governance platform",
        # structural checks are not legal correctness
        "do not prove legal correctness",
        # the prover is sound but deliberately incomplete
        "bounded formal verification, not general theorem proving",
        # the SBVR artifact is a profile, not conformance
        "not full omg interchange conformance",
        # RegDelta aligns by exact identifier
        "aligns rules by exact identifier",
        # no accuracy claim is being made
        "does **not** establish a universal accuracy rate",
        # machine-readable is not production-ready
        "machine-readable is not the same as production-ready",
    )
    missing = [b for b in required_boundaries if b.casefold() not in article]
    assert not missing, (
        "the article dropped these claim boundaries: "
        + "; ".join(missing)
        + " -- if they were reworded, update the fragment here rather than "
        "removing the check"
    )


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
        assert BLOB_PREFIX + relative_path in article


def test_every_repository_link_in_the_article_resolves() -> None:
    """No link may point at a file that does not exist.

    The floor list above cannot catch this on its own: an editorial rewrite
    is free to link a module that is not on it, and a link to a since-renamed
    file would otherwise ship as a dead link in a piece whose whole argument
    is "you can go and check my work".
    """
    article = ARTICLE.read_text(encoding="utf-8")

    linked = sorted(set(re.findall(re.escape(BLOB_PREFIX) + r"([\w/.-]+)", article)))
    assert linked, "the article no longer links any repository file"

    dead = [path for path in linked if not (ROOT / path).exists()]
    assert not dead, f"article links files that do not exist: {dead}"
