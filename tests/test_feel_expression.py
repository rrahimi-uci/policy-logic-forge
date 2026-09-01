from utils.feel_expression import compile_feel_expression, evaluate_feel_expression


def _variables():
    return [
        {"name": "loan_balance", "type": "number", "role": "input", "unit": "USD"},
        {"name": "appraised_value", "type": "number", "role": "input", "unit": "USD"},
        {"name": "maximum_amount", "type": "number", "role": "output", "unit": "USD"},
    ]


def test_compiles_declared_arithmetic_and_natural_operator_aliases_to_feel():
    assert compile_feel_expression(
        "the lesser of loan balance and appraised value",
        _variables(),
        output_variable="maximum_amount",
    ) == "min(loan_balance, appraised_value)"


def test_compiles_matching_unit_literal_without_treating_unit_as_a_symbol():
    assert compile_feel_expression(
        "min(500 USD, loan_balance * 0.01)",
        _variables(),
        output_variable="maximum_amount",
    ) == "min(500, (loan_balance * 0.01))"


def test_rejects_unknown_names_functions_and_output_self_references():
    assert compile_feel_expression("loan_balance + invented_amount", _variables(), output_variable="maximum_amount") is None
    assert compile_feel_expression("external_lookup(loan_balance)", _variables(), output_variable="maximum_amount") is None
    assert compile_feel_expression("maximum_amount + 1", _variables(), output_variable="maximum_amount") is None
    assert compile_feel_expression("loan_balance > appraised_value", _variables(), output_variable="maximum_amount") is None
    assert compile_feel_expression("abs(loan_balance, appraised_value)", _variables(), output_variable="maximum_amount") is None


def test_rejects_natural_language_that_cannot_be_lowered_exactly():
    assert compile_feel_expression(
        "lower score when two scores are obtained; middle score when three scores are obtained",
        _variables(),
        output_variable="maximum_amount",
    ) is None


def test_evaluates_only_the_compiler_numeric_subset():
    assert evaluate_feel_expression("((first + second) / min(limit, 2))", {"first": 2, "second": 4, "limit": 3}) == 3
    assert evaluate_feel_expression("unknown + 1", {}) is None
    assert evaluate_feel_expression("1 / zero", {"zero": 0}) is None
