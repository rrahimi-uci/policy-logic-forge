"""Tests for the shared corpus-anchored citation verification/repair module.

utils.citations is the single implementation used both by agent_07 (which
CREATES citations in its completion resolver) and agent_09 (which CERTIFIES
them) -- see each module's own docstring/comments for how a citation reaches
this code and why. These tests exercise the module directly, independent of
either agent, so the underlying logic is verified once regardless of how
many callers it gains.

The strategies and thresholds here were validated against a real mortgage
run before being written (PRs #77, #80): a citation is only ever repaired to
literal corpus text, never to the model's own wording, and only when the
match is strong enough that recovering it isn't a guess.
"""

from utils.citations import (
    MAX_ANCHOR_SPAN_EXPANSION,
    MIN_REPAIR_CHARS,
    MIN_REPAIR_COVERAGE,
    normalise_text,
    normalise_text_preserve_case,
    repair_by_anchors,
    repair_citation,
)


CHUNK = (
    "The lender must obtain and review the executed lease agreement between the "
    "borrower and the third-party solar provider before the loan is delivered "
    "to Fannie Mae for purchase or securitization."
)


def test_normalise_text_unifies_whitespace_quotes_and_case():
    assert normalise_text("A   B\n\tC") == "a b c"
    assert normalise_text("“quoted” ‘text’") == '"quoted" \'text\''


def test_normalise_text_preserve_case_matches_normalise_text_up_to_case():
    value = "A   B\n\tC “quoted”"
    assert normalise_text_preserve_case(value).casefold() == normalise_text(value)
    assert normalise_text_preserve_case(value) == 'A B C "quoted"'


def test_repair_citation_recovers_an_edge_drift_as_literal_corpus_text():
    edge_drift = CHUNK + " per policy."
    ratio = len(normalise_text(CHUNK)) / len(normalise_text(edge_drift))
    assert ratio >= MIN_REPAIR_COVERAGE, "fixture must sit in the contiguous-repair band"
    repaired = repair_citation(edge_drift, CHUNK)
    assert repaired == CHUNK
    assert repaired in CHUNK


def test_repair_citation_falls_back_to_anchors_for_middle_drift():
    middle_drift = (
        "The lender must obtain and review the executed lease agreement between the "
        "borrower and the solar company before closing "
        "to Fannie Mae for purchase or securitization."
    )
    repaired = repair_citation(middle_drift, CHUNK)
    assert repaired == CHUNK
    assert "solar company" not in repaired


def test_repair_citation_refuses_an_unrelated_quote():
    unrelated = "This sentence shares no real relationship with the cited passage whatsoever."
    assert repair_citation(unrelated, CHUNK) is None


def test_repair_by_anchors_refuses_a_span_wider_than_the_expansion_cap():
    far_chunk = CHUNK + (" Unrelated intervening policy text. " * 40) + "for purchase or securitization."
    quote = (
        "The lender must obtain and review the executed lease agreement between the borrower and "
        "for purchase or securitization."
    )
    recovered = repair_by_anchors(quote, far_chunk)
    if recovered is not None:
        assert len(normalise_text(recovered)) <= MAX_ANCHOR_SPAN_EXPANSION * len(normalise_text(quote))


def test_repair_by_anchors_refuses_a_quote_too_short_to_anchor():
    assert repair_by_anchors("must obtain and review", CHUNK) is None


def test_thresholds_are_the_values_validated_against_real_production_data():
    """Pins the constants so a future edit changes them deliberately, not by
    accident -- both were chosen from a real run's measured failure
    distribution (see utils/citations.py's module docstring history in
    PRs #77/#80), not arbitrary."""
    assert MIN_REPAIR_COVERAGE == 0.9
    assert MIN_REPAIR_CHARS == 40
    assert MAX_ANCHOR_SPAN_EXPANSION == 2.0
