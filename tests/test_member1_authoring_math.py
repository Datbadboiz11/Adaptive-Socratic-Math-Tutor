"""Regression tests for Member 1's bounded, draft-only math checkers."""
import sys
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.authoring_extended_math import TASK_CHECKS  # noqa: E402


def expected(kind, expression):
    return TASK_CHECKS[kind][0](expression)


def submitted(kind, expression, response):
    return TASK_CHECKS[kind][1](expression, response)


def test_square_root_is_principal_and_rejects_negative_radicands():
    assert expected("square_root", "49/64") == submitted("square_root", "49/64", "7/8")
    assert expected("square_root", "2") == submitted("square_root", "2", "sqrt(2)")
    assert expected("square_root", "2") != submitted("square_root", "2", "-sqrt(2)")
    with pytest.raises(ValueError):
        expected("square_root", "-1")
    with pytest.raises((ValueError, SyntaxError)):
        expected("square_root", "__import__('os').system('whoami')")


def test_rational_simplification_preserves_original_denominator_domain():
    expression = "2*x+10|x+5"
    assert expected("rational_simplify", expression) == submitted(
        "rational_simplify", expression, "2|1; {-5}"
    )
    assert expected("rational_simplify", expression) != submitted(
        "rational_simplify", expression, "2|1; {}"
    )


def test_rational_equation_excludes_denominator_roots_and_rejects_them_as_solutions():
    expression = "x*x-4|x-2; 4|1"
    assert expected("rational_equation", expression) == (
        frozenset({Fraction(2)}), frozenset(),
    )
    assert expected("rational_equation", expression) == submitted(
        "rational_equation", expression, "x!=2; S={}"
    )
    assert expected("rational_equation", expression) != submitted(
        "rational_equation", expression, "x!=2; S={2}"
    )
    assert expected("rational_equation", expression) != submitted(
        "rational_equation", expression, "x!=none; S={}"
    )


def test_system_substitution_answer_uses_a_valid_source_equation():
    expression = "2*x+3*y=13; 4*x-1*y=5"
    assert expected("linear_substitution", expression) == submitted(
        "linear_substitution", expression, "x; 1; (2,3)"
    )
    with pytest.raises(ValueError):
        submitted("linear_substitution", expression, "z; 1; (2,3)")
    with pytest.raises(ValueError):
        submitted("linear_substitution", expression, "x; 3; (2,3)")


def test_linear_function_sign_depends_on_slope_sign():
    positive = "-2*x+8"
    negative = "3*x-12"
    assert expected("linear_function_sign", positive) == submitted(
        "linear_function_sign", positive, "x=4; positive:x<4; negative:x>4"
    )
    assert expected("linear_function_sign", negative) == submitted(
        "linear_function_sign", negative, "x=4; positive:x>4; negative:x<4"
    )
    assert expected("linear_function_sign", positive) != submitted(
        "linear_function_sign", positive, "x=4; positive:x>4; negative:x<4"
    )


def test_quadratic_sign_handles_two_roots_no_roots_and_a_double_root():
    two_roots = "<; x*x-5*x+6"
    assert expected("quadratic_sign", two_roots) == submitted(
        "quadratic_sign", two_roots,
        "roots={2,3}; signs=+,0,-,0,+; solution=(2,3)",
    )
    no_roots = "sign; x*x+4*x+8"
    assert expected("quadratic_sign", no_roots) == submitted(
        "quadratic_sign", no_roots, "roots={}; signs=+",
    )
    double_root = "<=; x*x+2*x+1"
    assert expected("quadratic_sign", double_root) == submitted(
        "quadratic_sign", double_root,
        "roots={-1}; signs=+,0,+; solution={-1}",
    )
    closed = "<=; -x*x+2*x+8"
    assert expected("quadratic_sign", closed) == submitted(
        "quadratic_sign", closed,
        "roots={-2,4}; signs=-,0,+,0,-; solution=(-inf,-2]U[4,inf)",
    )
    all_except_root = ">; x*x-6*x+9"
    assert expected("quadratic_sign", all_except_root) == submitted(
        "quadratic_sign", all_except_root,
        "roots={3}; signs=+,0,+; solution=(-inf,3)U(3,inf)",
    )
