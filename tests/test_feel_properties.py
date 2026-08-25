"""Small deterministic property checks for the bounded reference evaluator."""

from __future__ import annotations

import pytest

from utils.feel import evaluate_formula


X_TRUE = {"op": "eq", "left": {"symbol": "x"}, "right": {"literal": True, "type": "bool"}}
X_FALSE = {"op": "eq", "left": {"symbol": "x"}, "right": {"literal": False, "type": "bool"}}


@pytest.mark.parametrize(
    ("op", "left", "right", "expected"),
    [
        ("and", True, True, True),
        ("and", True, False, False),
        ("and", True, None, None),
        ("or", False, False, False),
        ("or", False, True, True),
        ("or", False, None, None),
    ],
)
def test_kleene_truth_table_is_stable(op, left, right, expected):
    environment = {"x": left, "y": right}
    formula = {"op": op, "args": [X_TRUE, {"op": "eq", "left": {"symbol": "y"}, "right": {"literal": True, "type": "bool"}}]}
    assert evaluate_formula(formula, environment) is expected


def test_double_negation_preserves_known_and_unknown_values():
    for value, expected in ((True, True), (False, False), (None, None)):
        formula = {"op": "not", "arg": {"op": "not", "arg": X_TRUE}}
        assert evaluate_formula(formula, {"x": value}) is expected


def test_is_null_is_the_only_explicit_missing_value_test():
    is_null = {"op": "is_null", "arg": {"symbol": "x"}}
    assert evaluate_formula(is_null, {}) is True
    assert evaluate_formula(is_null, {"x": None}) is True
    assert evaluate_formula(is_null, {"x": False}) is False
