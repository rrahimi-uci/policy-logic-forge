"""Tests for agent_01's defensive JSON-response parsing.

Context: response_format={"type": "json_object"} is requested for both of
agent_01's AI-reasoning calls (TOC analysis, document-structure chunking),
but the two call sites used bare json.loads() with no fallback -- unlike
every other agent in this pipeline (agent_02/03/06/07/08/09), which all
strip a markdown code fence and fall back to json_repair on a minor
structural defect. Added _parse_json_response() to close that gap and
match the established pattern, for both providers equally (not
Anthropic-specific -- OpenAI's JSON mode can also occasionally wrap output
or emit a trailing comma).
"""

from agents.agent_01_document_organizer import _parse_json_response


def test_parses_clean_json_object():
    assert _parse_json_response('{"has_toc": true, "toc_entries": []}') == {
        "has_toc": True, "toc_entries": [],
    }


def test_strips_a_markdown_code_fence():
    wrapped = '```json\n{"sections": [{"title": "Intro"}]}\n```'
    assert _parse_json_response(wrapped) == {"sections": [{"title": "Intro"}]}


def test_strips_a_bare_triple_backtick_fence_without_language_tag():
    wrapped = '```\n{"has_toc": false, "toc_entries": []}\n```'
    assert _parse_json_response(wrapped) == {"has_toc": False, "toc_entries": []}


def test_repairs_a_trailing_comma():
    malformed = '{"sections": [{"title": "Intro"},]}'
    assert _parse_json_response(malformed) == {"sections": [{"title": "Intro"}]}


def test_repairs_an_unterminated_object():
    malformed = '{"has_toc": true, "toc_entries": [{"title": "Intro"'
    result = _parse_json_response(malformed)
    assert isinstance(result, dict)
    assert result.get("has_toc") is True


def test_leading_trailing_whitespace_is_tolerated():
    assert _parse_json_response('\n\n  {"has_toc": false, "toc_entries": []}  \n') == {
        "has_toc": False, "toc_entries": [],
    }


def test_genuinely_unrecoverable_content_never_raises_uncaught():
    """json_repair's own contract: it does not raise on ununiterpretable
    input, it returns its best-effort guess (often '' for pure prose) --
    matching the same repair_json(..., strict=True) call every other agent
    in this pipeline already relies on. The result is not guaranteed to be
    a dict; callers here (like elsewhere) rely on their own outer
    try/except around each chat_completion call site, not on this
    function raising, to handle that case."""
    result = _parse_json_response("this is not JSON and cannot be repaired into any object <<<")
    assert not isinstance(result, dict)
