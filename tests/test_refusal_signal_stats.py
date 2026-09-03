"""Validate the hand-rolled statistics behind the refusal-signal experiment.

scipy is not a dependency of this repository, so the experiment implements
Fisher's exact test, the Wilson score interval and Mann-Whitney U directly.
Its conclusions rest on those being right, so they are checked against
published reference values rather than against themselves.
"""

from __future__ import annotations

import math
import random

import pytest

from research.refusal_signal.analyse import (
    aurc,
    fisher_exact_two_sided,
    mann_whitney_u,
    risk_coverage,
    wilson,
)


@pytest.mark.parametrize(
    "table,expected,source",
    [
        ((3, 1, 1, 3), 0.4857142857, "Fisher's tea-tasting experiment"),
        ((1, 9, 11, 3), 0.0027594, "R fisher.test documentation example"),
        ((10, 0, 0, 10), 1.0825e-05, "perfect separation, n=20"),
        ((5, 5, 5, 5), 1.0, "no association"),
    ],
)
def test_fisher_exact_matches_published_values(table, expected, source):
    got = fisher_exact_two_sided(*table)
    assert got == pytest.approx(expected, rel=0.02, abs=1e-6), source


def test_fisher_exact_sums_tables_no_likelier_than_the_observed_one():
    """Pin the two-sided rule itself, not just a few reference p-values.

    The common wrong implementation doubles the one-sided tail, which
    disagrees with the sum-of-unlikelier-tables rule whenever the margins
    are asymmetric.  H1's verdict rests on this, so it is checked directly
    against an independent recomputation.
    """
    for a, b, c, d in ((2, 7, 8, 3), (1, 11, 9, 4), (6, 2, 3, 9)):
        n, row1, col1 = a + b + c + d, a + b, a + c
        hyper = {
            x: math.comb(row1, x) * math.comb(n - row1, col1 - x) / math.comb(n, col1)
            for x in range(max(0, col1 - (n - row1)), min(row1, col1) + 1)
        }
        expected = sum(p for p in hyper.values() if p <= hyper[a] * (1 + 1e-9))
        assert fisher_exact_two_sided(a, b, c, d) == pytest.approx(expected, abs=1e-12)

        one_sided = sum(p for x, p in hyper.items() if x <= a)
        if abs(min(1.0, 2 * one_sided) - expected) > 1e-6:
            # the doubling rule really is different here, so the check bites
            assert fisher_exact_two_sided(a, b, c, d) != pytest.approx(
                min(1.0, 2 * one_sided), abs=1e-9
            )


def test_fisher_exact_is_symmetric_under_row_and_column_swaps():
    a, b, c, d = 7, 3, 2, 8
    p = fisher_exact_two_sided(a, b, c, d)
    assert fisher_exact_two_sided(c, d, a, b) == pytest.approx(p)
    assert fisher_exact_two_sided(b, a, d, c) == pytest.approx(p)


@pytest.mark.parametrize(
    "k,n,lo,hi",
    [
        (0, 10, 0.0000, 0.2775),
        (5, 10, 0.2366, 0.7634),
        (10, 10, 0.7225, 1.0000),
    ],
)
def test_wilson_interval_matches_closed_form(k, n, lo, hi):
    got_lo, got_hi = wilson(k, n)
    assert got_lo == pytest.approx(lo, abs=5e-4)
    assert got_hi == pytest.approx(hi, abs=5e-4)


def test_wilson_interval_contains_the_point_estimate():
    for k, n in ((1, 3), (30, 36), (99, 110), (269, 306)):
        lo, hi = wilson(k, n)
        assert lo <= k / n <= hi


def test_wilson_handles_empty_sample():
    assert wilson(0, 0) == (0.0, 0.0)


def test_mann_whitney_auc_endpoints_and_midpoint():
    assert mann_whitney_u([1, 2, 3], [4, 5, 6])[0] == pytest.approx(0.0)
    assert mann_whitney_u([4, 5, 6], [1, 2, 3])[0] == pytest.approx(1.0)
    assert mann_whitney_u([1, 2, 3], [1, 2, 3])[0] == pytest.approx(0.5)


def test_mann_whitney_is_significant_on_cleanly_separated_samples():
    auc, p = mann_whitney_u(list(range(20, 40)), list(range(20)))
    assert auc == pytest.approx(1.0)
    assert p < 0.001


def test_mann_whitney_finds_no_signal_in_identical_distributions():
    auc, p = mann_whitney_u([5] * 30, [5] * 30)
    assert auc == pytest.approx(0.5)
    assert p == pytest.approx(1.0)


def test_mann_whitney_handles_an_empty_group():
    assert mann_whitney_u([], [1, 2]) == (0.5, 1.0)


def _records(pattern):
    """Build records whose score ordering matches `pattern` of correctness."""
    return [
        {"correct": c, "score": float(len(pattern) - i)}
        for i, c in enumerate(pattern)
    ]


def test_risk_coverage_is_monotone_in_answered_count():
    points = risk_coverage(_records([1, 1, 1, 0, 0]), "score")
    assert [round(c, 3) for c, _ in points] == [0.2, 0.4, 0.6, 0.8, 1.0]
    assert [round(r, 3) for _, r in points] == [0.0, 0.0, 0.0, 0.25, 0.4]


def test_aurc_is_lower_for_a_selector_that_ranks_errors_last():
    good = aurc(risk_coverage(_records([1] * 10 + [0] * 10), "score"))
    bad = aurc(risk_coverage(_records([0] * 10 + [1] * 10), "score"))
    assert good < bad


def test_aurc_of_a_random_selector_approaches_the_base_error_rate():
    rng = random.Random(0)
    records = [
        {"correct": rng.randint(0, 1), "score": rng.random()} for _ in range(4000)
    ]
    base = 1 - sum(r["correct"] for r in records) / len(records)
    assert aurc(risk_coverage(records, "score")) == pytest.approx(base, abs=0.03)


def test_risk_coverage_ignores_records_without_a_score():
    records = _records([1, 0]) + [{"correct": 1, "score": None}]
    assert len(risk_coverage(records, "score")) == 2
