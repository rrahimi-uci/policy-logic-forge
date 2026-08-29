"""Corpus-anchored citation verification and repair.

Shared by the agents that produce citations (agent_07's completion
resolver) and the one that certifies them (agent_09), so a citation is
repaired the same way wherever it is created. Every repair returns literal
text from the cited chunk -- never a model's paraphrase -- so a repaired
citation cannot carry transcription drift forward by construction.

Extracted verbatim from agent_09 (PRs #77/#80) when agent_07 needed the
same logic; the strategies and their thresholds are unchanged.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Any


def normalise_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("\u00ad", "").replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().casefold()


def normalise_text_preserve_case(value: Any) -> str:
    """Identical to _normalise_text minus the final .casefold().

    Same character-level transforms (NFKC, quote unification, whitespace
    collapse), so the result stays index-aligned with _normalise_text's
    output for the same input -- a span found by matching against the
    casefolded string can be sliced out of this one unchanged, recovering
    the source's real casing/punctuation instead of a downcased copy.
    """
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("­", "").replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip()


def _normalised_text_with_source_offsets(value: Any) -> tuple[str, list[int]]:
    """Normalize text while retaining an offset map into the original value."""

    source = str(value or "")
    output: list[str] = []
    offsets: list[int] = []
    whitespace_pending: int | None = None
    for source_index, character in enumerate(source):
        normalized = unicodedata.normalize("NFKC", character)
        normalized = normalized.replace("\u00ad", "").replace("’", "'").replace("‘", "'")
        normalized = normalized.replace("“", '"').replace("”", '"').casefold()
        for item in normalized:
            if item.isspace():
                if output and whitespace_pending is None:
                    whitespace_pending = source_index
                continue
            if whitespace_pending is not None:
                output.append(" ")
                offsets.append(whitespace_pending)
                whitespace_pending = None
            output.append(item)
            offsets.append(source_index)
    return "".join(output), offsets


def resolve_citation_span(quote: str, chunk_text: str) -> dict[str, Any] | None:
    """Resolve a citation to an exact source substring and stable offsets.

    Matching may tolerate Unicode, quote, case, or whitespace normalization,
    and may use the existing conservative repair strategies. The returned text
    is always sliced from ``chunk_text`` itself, so ``start_offset`` and
    ``end_offset`` are exact and independently reproducible.
    """

    if not quote or not chunk_text:
        return None
    exact_start = chunk_text.find(quote)
    if exact_start >= 0:
        return {
            "source_text": quote,
            "start_offset": exact_start,
            "end_offset": exact_start + len(quote),
            "source_text_repaired": False,
        }
    candidates = [(quote, False)]
    repaired = repair_citation(quote, chunk_text)
    if repaired and normalise_text(repaired) != normalise_text(quote):
        candidates.append((repaired, True))
    elif repaired:
        candidates.append((repaired, repaired != quote))
    normal_chunk, offsets = _normalised_text_with_source_offsets(chunk_text)
    for candidate, was_repaired in candidates:
        normal_candidate = normalise_text(candidate)
        position = normal_chunk.find(normal_candidate)
        if position < 0 or not normal_candidate or not offsets:
            continue
        start = offsets[position]
        end = offsets[position + len(normal_candidate) - 1] + 1
        exact_text = chunk_text[start:end]
        return {
            "source_text": exact_text,
            "start_offset": start,
            "end_offset": end,
            "source_text_repaired": was_repaired or exact_text != quote,
        }
    return None


# A citation is only auto-repaired when the model's claimed source_text is
# almost entirely (not just partially) one contiguous run of real corpus
# text: found empirically (see _repair_near_match's docstring) that this
# bar cleanly separates "the model paraphrased a boundary/word or two but
# the real quote is genuinely there" from "the model summarized/fabricated
# most of this and only a short, possibly-coincidental phrase overlaps."
MIN_REPAIR_COVERAGE = 0.9
MIN_REPAIR_CHARS = 40

# Anchor recovery (the second, broader strategy below). The extraction agent
# is reliable at identifying WHERE a passage is and unreliable at
# TRANSCRIBING it -- so its first and last few words are used only as
# pointers into the real chunk, and everything between them is taken from
# the corpus rather than from the model. Tried longest-anchor-first; a
# shorter anchor is more likely to match by coincidence, so it is only a
# fallback. The span expansion cap is what keeps a coincidental tail match
# from silently widening a citation into surrounding paragraphs.
ANCHOR_WORD_SIZES = (6, 5, 4)
MAX_ANCHOR_SPAN_EXPANSION = 2.0


def repair_by_anchors(quote: str, chunk_text: str) -> str | None:
    """Recover a citation by treating the model's first/last few words as
    pointers into `chunk_text` and returning the REAL text between them.

    Complements _repair_near_match's single-contiguous-run strategy, which
    by construction only recovers a citation whose drift is at its edges.
    This one recovers the far more common real failure: the model located
    the right passage but compressed or paraphrased its MIDDLE. Because the
    middle is taken from the corpus and never from the model, a citation
    repaired this way cannot carry the model's paraphrase forward -- the
    drifted wording is discarded, not blessed.

    Measured on a real mortgage run (479 citations that failed an exact
    match and whose chunk resolved): the contiguous strategy alone recovers
    ~24%, this one recovers 45%, and the recovered spans stay tight against
    what was claimed (median 1.09x the claimed length, p90 1.62x) rather
    than ballooning. The residual ~54% is genuinely unrecoverable
    deterministically: mostly heavy compression where the tail anchor is
    absent or implausibly distant, plus a smaller set citing the wrong
    chunk entirely -- both correctly left to fail closed.
    """
    normal_quote = normalise_text(quote)
    normal_chunk = normalise_text(chunk_text)
    if not normal_quote or not normal_chunk:
        return None
    words = normal_quote.split()
    if len(words) < 2 * min(ANCHOR_WORD_SIZES):
        # Too short to split into two non-overlapping anchors; a single
        # short phrase is exactly the coincidental-match case to avoid.
        return None
    cased_chunk = normalise_text_preserve_case(chunk_text)
    if len(cased_chunk) != len(normal_chunk):
        # Casefold changed the string length for some character, so the two
        # normalised strings are no longer index-aligned and slicing the
        # cased one at the casefolded one's offsets would return the wrong
        # span. Fail closed, same as _repair_near_match.
        return None
    for size in ANCHOR_WORD_SIZES:
        if len(words) < 2 * size:
            continue
        head = " ".join(words[:size])
        tail = " ".join(words[-size:])
        start = normal_chunk.find(head)
        if start == -1:
            continue
        # Search for the tail only AFTER the head so the recovered span can
        # never run backwards, and take the first such occurrence so a
        # repeated phrase later in the chunk cannot stretch the span.
        tail_at = normal_chunk.find(tail, start + len(head))
        if tail_at == -1:
            continue
        end = tail_at + len(tail)
        if end - start > MAX_ANCHOR_SPAN_EXPANSION * len(normal_quote):
            continue
        return cased_chunk[start:end]
    return None


def repair_citation(quote: str, chunk_text: str) -> str | None:
    """If `quote` isn't a verbatim substring of `chunk_text` but a genuine,
    near-total (>=MIN_REPAIR_COVERAGE) contiguous run of it is, return that
    real substring (in the chunk's own casing) instead of the model's
    possibly-imprecise wording. Return None if no such run exists.

    This never invents text: the repaired citation is always a literal
    substring the corpus actually contains, never the model's paraphrase --
    so even if the model's original wording had drifted from the source in
    some way, the repaired citation cannot, by construction. It just
    recognises that a real citation is present when the model got the
    exact word boundaries slightly wrong, instead of discarding it outright.

    Confirmed against a real run: of 583 evidence citations that failed an
    exact match, splitting them by longest-contiguous-match coverage of the
    claimed quote showed a clean bimodal split -- roughly a quarter were
    >=90% covered by one real contiguous run (a boundary/word-level miss,
    safe to repair), while the rest were 70% or less (a genuine paraphrase
    or compression of multiple sentences, where discarding the unmatched
    tail would mean guessing at what the model meant instead of reporting
    what the corpus actually says -- left for a human or a real
    re-verification, not silently patched).
    """
    normal_quote = normalise_text(quote)
    normal_chunk = normalise_text(chunk_text)
    if not normal_quote or not normal_chunk:
        return None
    matcher = difflib.SequenceMatcher(None, normal_quote, normal_chunk, autojunk=False)
    match = matcher.find_longest_match(0, len(normal_quote), 0, len(normal_chunk))
    if match.size < MIN_REPAIR_CHARS or match.size / len(normal_quote) < MIN_REPAIR_COVERAGE:
        # Edge-drift recovery does not apply. Fall back to anchor recovery,
        # which handles the much more common middle-drift case. Ordered this
        # way deliberately: the contiguous strategy returns exactly the real
        # run the model almost transcribed, while anchors return the real
        # span BETWEEN two pointers -- a strictly wider claim, so it is only
        # used when the tighter strategy cannot answer.
        return repair_by_anchors(quote, chunk_text)
    cased_chunk = normalise_text_preserve_case(chunk_text)
    if len(cased_chunk) != len(normal_chunk):
        # Casefold changed the string length for some character (rare, but
        # real for a few non-ASCII letters) -- the two strings are no longer
        # index-aligned, so slicing cased_chunk at normal_chunk's offsets
        # would silently return the wrong span. Fail closed instead.
        return None
    return cased_chunk[match.b : match.b + match.size]

