"""Synthetic tests for the first Academy math validator."""

from fractions import Fraction

import pytest

from custom_components.family_assistant.academy.rational import check_rational


@pytest.mark.parametrize("answer", ["1/2", "2/4", "0.5", "0,50", "+1 / 2", "  0.500  "])
def test_equivalent_answers(answer):
    result = check_rational(answer, Fraction(1, 2))
    assert (result.status, result.code, result.normalized) == (
        "correct", "equivalent_value", "1/2"
    )


@pytest.mark.parametrize("answer", ["−3/4", "-0.75", "-0,750", "-6/8"])
def test_negative_answers(answer):
    assert check_rational(answer, Fraction(-3, 4)).status == "correct"


@pytest.mark.parametrize("answer", ["", "1/0", "1 / 0", "1/2/3", "2**8", "1e5", "NaN",
    "1_000", "1,000.5", "1/-2", "１２", "1" * 13, "0." + "1" * 13,
    " " * 81, "__import__('os')", "1/" + "2" * 13, "1.2.3", None, 0.5])
def test_invalid_answers(answer):
    result = check_rational(answer, Fraction(1, 2))
    assert result.status == "invalid"
    assert result.normalized is None


def test_unequal_answer():
    result = check_rational("0.333333333333", Fraction(1, 3))
    assert result.status == "incorrect"
    assert result.code == "different_value"


@pytest.mark.parametrize("answer", ["2/4", "0.5"])
def test_reduced_form_required(answer):
    result = check_rational(answer, Fraction(1, 2), require_reduced_fraction=True)
    assert result.code == "reduced_fraction_required"
    assert result.status == "incorrect"


def test_reduced_form_success():
    assert check_rational("1/2", Fraction(1, 2), require_reduced_fraction=True).status == "correct"


def test_zero_and_integer():
    assert check_rational("0/3", Fraction(0)).status == "correct"
    assert check_rational("-2", Fraction(-2)).status == "correct"
    assert check_rational("0/1", Fraction(0), require_reduced_fraction=True).status == "correct"


def test_requires_exact_expected_answer():
    with pytest.raises(TypeError):
        check_rational("0.5", 0.5)
