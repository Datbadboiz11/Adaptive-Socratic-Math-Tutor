"""Trace-based misconception catalog for algebra and equation skills.

Detectors consume only a SymPy-verified incorrect step and authored trace
metadata. They never inspect learner explanations or LLM-generated text.
"""

from dataclasses import dataclass
import re
import sympy as sp

CONCEPT_IDS = frozenset(
    [f'A0{i}' for i in range(1, 9)] + [f'E0{i}' for i in range(1, 7)]
)


@dataclass(frozen=True)
class TraceContext:
    problem: dict
    concept_id: str
    step_index: int
    before_text: str
    after_text: str
    previous_steps: tuple[str, ...]
    before_state: dict | None = None
    after_state: dict | None = None


def _canonical_trace(text):
    text = str(text).lower()
    for source, replacement in (
        ('Ã¢Ë†â€™', '-'), ('âˆ’', '-'), ('−', '-'),
        ('Ã—', '*'), ('×', '*'), ('·', '*'),
    ):
        text = text.replace(source, replacement)
    text = re.sub(r'(?<=[0-9xy)])\*(?=[xy(])', '', text)
    return re.sub(r'\s+', '', text)


def _sympy_equal(left, right):
    return sp.cancel(left - right) == 0


def _parsed_side_rows(text, state):
    """Parse trace sides with the bounded learner Parser, never a SymPy string parser."""
    from .math_validator import Parser, parse_expression, split_rows

    if state is not None and state.get('kind') == 'solution_set':
        return None
    if state is not None and state.get('kind') == 'expression':
        expr = parse_expression(text).expr
        return [(expr, None, text, None)]

    rows = []
    for row in split_rows(text):
        if row.count('=') == 1:
            left_text, right_text = row.split('=')
            left = Parser(left_text).parse().expr
            right = Parser(right_text).parse().expr
            rows.append((left, right, left_text, right_text))
        else:
            expr = parse_expression(row).expr
            rows.append((expr, None, row, None))
    return rows


def _transition_side_matches(context, side_rule):
    try:
        before_rows = _parsed_side_rows(context.before_text, context.before_state)
        after_rows = _parsed_side_rows(context.after_text, context.after_state)
        if before_rows is None or after_rows is None or len(before_rows) != len(after_rows):
            return False
        for row_index, (before_row, after_row) in enumerate(zip(before_rows, after_rows)):
            for side_index in (0, 1):
                before_expr, after_expr = before_row[side_index], after_row[side_index]
                before_text = before_row[side_index + 2]
                if before_expr is None or before_text is None:
                    continue
                if not side_rule(before_text, before_expr, after_expr):
                    continue
                unchanged = True
                for other_row_index, (other_before, other_after) in enumerate(zip(before_rows, after_rows)):
                    for other_side_index in (0, 1):
                        if (other_row_index, other_side_index) == (row_index, side_index):
                            continue
                        left = other_before[other_side_index]
                        right = other_after[other_side_index]
                        if left is None or right is None:
                            if left is not right:
                                unchanged = False
                                break
                        elif not _sympy_equal(left, right):
                            unchanged = False
                            break
                    if not unchanged:
                        break
                if unchanged:
                    return True
    except Exception:
        return False
    return False


def _scaled_binomial(source_text):
    """Return (outer coefficient, variable coefficient, constant, variable, inner)."""
    from .math_validator import Parser

    match = re.fullmatch(
        r'\s*([+-]?\d+(?:\.\d+)?)\s*\*?\s*\((.*)\)\s*',
        source_text,
    )
    if not match:
        return None
    outer_text, inner_text = match.groups()
    inner = Parser(inner_text).parse().expr
    variables = tuple(inner.free_symbols)
    if len(variables) != 1:
        return None
    variable = variables[0]
    try:
        polynomial = sp.Poly(inner, variable)
    except Exception:
        return None
    if polynomial.degree() != 1:
        return None
    outer: sp.Expr = sp.sympify(sp.Rational(outer_text))
    coefficient = polynomial.coeff_monomial(variable)
    constant = polynomial.coeff_monomial(1)
    return outer, coefficient, constant, variable, inner


def _distribution_missing_term(source_text, before, after):
    parts = _scaled_binomial(source_text)
    if parts is None:
        return False
    outer, coefficient, constant, variable, inner = parts
    if outer == 1 or constant == 0 or coefficient == 0:
        return False
    incorrect = outer * coefficient * variable + constant
    correct = outer * inner
    return not _sympy_equal(incorrect, correct) and _sympy_equal(after, incorrect)


def _distribution_constant_sign(source_text, before, after):
    parts = _scaled_binomial(source_text)
    if parts is None:
        return False
    outer, coefficient, constant, variable, inner = parts
    if sp.Rel(outer, 0, '>=') == True or constant == 0 or coefficient == 0:
        return False
    incorrect = outer * coefficient * variable - outer * constant
    correct = outer * inner
    return not _sympy_equal(incorrect, correct) and _sympy_equal(after, incorrect)


def _binomial_square(source_text) -> tuple[sp.Expr, sp.Expr] | None:
    from .math_validator import Parser

    match = re.fullmatch(r'\s*\((.*)\)\s*\^\s*2\s*', source_text)
    if not match:
        return None
    inner = Parser(match.group(1)).parse().expr
    terms = sp.Add.make_args(inner)
    if len(terms) != 2:
        return None
    return sp.sympify(terms[0]), sp.sympify(terms[1])


def _square_missing_middle(source_text, before, after):
    terms = _binomial_square(source_text)
    if terms is None or _sympy_equal(2 * terms[0] * terms[1], 0):
        return False
    incorrect = sp.Pow(terms[0], 2) + sp.Pow(terms[1], 2)
    return _sympy_equal(after, incorrect) and not _sympy_equal(after, before)


def _square_as_difference(source_text, before, after):
    terms = _binomial_square(source_text)
    if terms is None:
        return False
    variable_terms = [term for term in terms if term.free_symbols]
    constants = [term for term in terms if not term.free_symbols]
    if len(variable_terms) != 1 or len(constants) != 1:
        return False
    incorrect = sp.Pow(variable_terms[0], 2) - sp.Pow(constants[0], 2)
    return _sympy_equal(after, incorrect) and not _sympy_equal(after, before)


def _binomial_product(source_text) -> tuple[tuple[sp.Expr, sp.Expr], tuple[sp.Expr, sp.Expr]] | None:
    from .math_validator import Parser

    match = re.fullmatch(r'\s*\((.*)\)\s*\((.*)\)\s*', source_text)
    if not match:
        return None
    left, right = (Parser(part).parse().expr for part in match.groups())
    left_terms, right_terms = sp.Add.make_args(left), sp.Add.make_args(right)
    if len(left_terms) != 2 or len(right_terms) != 2:
        return None
    return (
        (sp.sympify(left_terms[0]), sp.sympify(left_terms[1])),
        (sp.sympify(right_terms[0]), sp.sympify(right_terms[1])),
    )


def _product_missing_cross_terms(source_text, before, after):
    parts = _binomial_product(source_text)
    if parts is None:
        return False
    left_terms, right_terms = parts
    left_variable = next((term for term in left_terms if term.free_symbols), None)
    right_variable = next((term for term in right_terms if term.free_symbols), None)
    left_constant = next((term for term in left_terms if not term.free_symbols), None)
    right_constant = next((term for term in right_terms if not term.free_symbols), None)
    if any(term is None for term in (left_variable, right_variable, left_constant, right_constant)):
        return False
    assert left_variable is not None and right_variable is not None
    assert left_constant is not None and right_constant is not None
    incorrect = left_variable * right_variable + left_constant * right_constant
    return _sympy_equal(after, incorrect) and not _sympy_equal(after, before)


def _product_constant_sign(source_text, before, after):
    parts = _binomial_product(source_text)
    if parts is None:
        return False
    left_terms, right_terms = parts
    left_constant = next((term for term in left_terms if not term.free_symbols), None)
    right_constant = next((term for term in right_terms if not term.free_symbols), None)
    if left_constant is None or right_constant is None or left_constant * right_constant == 0:
        return False
    correct = (left_terms[0] + left_terms[1]) * (right_terms[0] + right_terms[1])
    incorrect = correct - 2 * left_constant * right_constant
    return _sympy_equal(after, incorrect) and not _sympy_equal(after, before)


def _difference_square_constant_sign(source_text, before, after):
    parts = _binomial_product(source_text)
    if parts is None:
        return False
    left_terms, right_terms = parts
    left_variable = next((term for term in left_terms if term.free_symbols), None)
    right_variable = next((term for term in right_terms if term.free_symbols), None)
    left_constant = next((term for term in left_terms if not term.free_symbols), None)
    right_constant = next((term for term in right_terms if not term.free_symbols), None)
    if any(term is None for term in (left_variable, right_variable, left_constant, right_constant)):
        return False
    if not _sympy_equal(left_variable, right_variable) or not _sympy_equal(left_constant, -right_constant):
        return False
    return _product_constant_sign(source_text, before, after)


def _finite_roots(state) -> set[sp.Expr] | None:
    from .math_validator import state_signature

    if state is None:
        return None
    if state.get('kind') == 'solution_set':
        return {sp.sympify(r) for r in state['roots']}
    if state.get('kind') != 'equations' or 'y' in state.get('variables', ()):
        return None
    try:
        signature = state_signature(state)
    except Exception:
        return None
    roots = signature[2]
    if roots[0] != 'finite':
        return None
    return {sp.sympify(r) for r in roots[1]}


def _one_missing_root(context):
    before_roots = _finite_roots(context.before_state)
    after_roots = _finite_roots(context.after_state)
    return (
        before_roots is not None and after_roots is not None
        and len(before_roots) == 2 and len(after_roots) == 1
        and after_roots < before_roots
    )


def _divided_out_zero_factor(context):
    before_roots = _finite_roots(context.before_state)
    after_roots = _finite_roots(context.after_state)
    if (
        before_roots is None or after_roots is None
        or len(before_roots) != 2 or len(after_roots) != 1
        or not (after_roots < before_roots)
    ):
        return False
    if sp.Integer(0) not in (before_roots - after_roots):
        return False
    compact = _canonical_trace(context.before_text)
    return re.search(r'(?<![a-z0-9])x\*?\(', compact) is not None


def _lost_domain_condition(context):
    from .math_validator import state_signature

    try:
        before_signature = state_signature(context.before_state)
        after_signature = state_signature(context.after_state)
    except Exception:
        return False
    if before_signature[0] != 'one_variable_equations' or after_signature[0] != 'one_variable_equations':
        return False
    before_domain, after_domain = before_signature[1], after_signature[1]
    if before_domain[0] != 'cofinite_domain' or after_domain[0] != 'cofinite_domain':
        return False
    return bool(before_domain[1] - after_domain[1])


def _accepted_excluded_root(context):
    from .math_validator import state_signature

    try:
        before_signature = state_signature(context.before_state)
    except Exception:
        return False
    if before_signature[0] != 'one_variable_equations':
        return False
    domain, _ = before_signature[1], before_signature[2]
    after_roots = _finite_roots(context.after_state)
    return (
        domain[0] == 'cofinite_domain' and bool(domain[1])
        and after_roots is not None and bool(domain[1] & after_roots)
    )


def _poly_for(expr, variable=None):
    symbols = tuple(expr.free_symbols)
    if variable is None:
        if len(symbols) != 1:
            return None
        variable = symbols[0]
    try:
        polynomial = sp.Poly(expr, variable)
    except Exception:
        return None
    return variable, polynomial


def _substitution_sign(source_text, before, after):
    from .math_validator import Parser

    matches = list(re.finditer(r'\(\s*-\s*(\d+(?:\.\d+)?)\s*\)', source_text))
    for match in matches:
        positive = f'({match.group(1)})'
        candidate = source_text[:match.start()] + positive + source_text[match.end():]
        try:
            incorrect = Parser(candidate).parse().expr
        except Exception:
            continue
        if _sympy_equal(after, incorrect) and not _sympy_equal(before, after):
            return True
    return False


def _power_as_identity(source_text, before, after):
    before_poly = _poly_for(before)
    after_poly = _poly_for(after)
    if before_poly is None or after_poly is None or before_poly[0] != after_poly[0]:
        return False
    variable = before_poly[0]
    left, right = before_poly[1], after_poly[1]
    return (
        left.degree() == 2 and right.degree() == 1
        and left.coeff_monomial(variable) == 0
        and left.coeff_monomial(variable ** 2) != 0
        and _sympy_equal(left.coeff_monomial(variable ** 2),
                         right.coeff_monomial(variable))
        and _sympy_equal(left.coeff_monomial(1), right.coeff_monomial(1))
        and not _sympy_equal(before, after)
    )


def _like_terms_multiplied(source_text, before, after):
    before_poly = _poly_for(before)
    after_poly = _poly_for(after)
    if before_poly is None or after_poly is None or before_poly[0] != after_poly[0]:
        return False
    variable = before_poly[0]
    left, right = before_poly[1], after_poly[1]
    if str(variable) != 'x':
        return False
    match = re.fullmatch(
        r'\s*([+-]?(?:\d+(?:\.\d+)?)?)\s*\*?\s*x\s*([+-])\s*'
        r'(\d+(?:\.\d+)?)\s*\*?\s*x\s*',
        source_text,
    )
    if not match:
        return False
    first_text, operator, second_text = match.groups()
    first: sp.Expr = sp.sympify(
        sp.Rational(first_text) if first_text not in ('', '+', '-') else (-1 if first_text == '-' else 1)
    )
    second: sp.Expr = sp.sympify(sp.Rational(second_text)) * (-1 if operator == '-' else 1)
    multiplied_coefficient = sp.cancel(first * second)
    return (
        left.degree() == 1 and right.degree() == 2
        and not _sympy_equal(multiplied_coefficient, left.coeff_monomial(variable))
        and _sympy_equal(right.coeff_monomial(variable ** 2), multiplied_coefficient)
        and right.coeff_monomial(variable) == 0
        and right.coeff_monomial(1) == left.coeff_monomial(1)
    )


def _opposite_constants_added(source_text, before, after):
    match = re.fullmatch(
        r'\s*([+-]?\d+(?:\.\d+)?)\s*([+-])\s*\(?\s*([+-]?\d+(?:\.\d+)?)\s*\)?\s*',
        source_text,
    )
    if not match:
        return False
    left_text, operator, right_text = match.groups()
    left: sp.Expr = sp.sympify(sp.Rational(left_text))
    right: sp.Expr = sp.sympify(sp.Rational(right_text))
    if operator == '-':
        right = -right
    if sp.Rel(left * right, 0, '>=') == True:
        return False
    incorrect = sp.Abs(left) + sp.Abs(right)
    return _sympy_equal(after, incorrect) and not _sympy_equal(before, after)


def _incomplete_common_factor(source_text, before, after):
    before_poly, after_poly = _poly_for(before), _poly_for(after)
    if before_poly is None or after_poly is None or before_poly[0] != after_poly[0]:
        return False
    variable = before_poly[0]
    source, target = before_poly[1], after_poly[1]
    coefficient = source.coeff_monomial(variable)
    constant = source.coeff_monomial(1)
    return (
        source.degree() == target.degree() == 1
        and coefficient != 1 and constant != 0
        and _sympy_equal(target.coeff_monomial(variable), coefficient)
        and _sympy_equal(target.coeff_monomial(1), coefficient * constant)
    )


def _common_factor_variable_lost(source_text, before, after):
    before_poly, after_poly = _poly_for(before), _poly_for(after)
    if before_poly is None or after_poly is None or before_poly[0] != after_poly[0]:
        return False
    variable = before_poly[0]
    source, target = before_poly[1], after_poly[1]
    coefficient2 = source.coeff_monomial(variable ** 2)
    coefficient1 = source.coeff_monomial(variable)
    return (
        source.degree() == target.degree() == 2
        and coefficient2 != 0 and coefficient1 != 0
        and source.coeff_monomial(1) == 0
        and _sympy_equal(target.coeff_monomial(variable ** 2), coefficient2)
        and target.coeff_monomial(variable) == 0
        and _sympy_equal(target.coeff_monomial(1), coefficient1)
    )


def _equation_rows(context):
    before_rows = _parsed_side_rows(context.before_text, context.before_state)
    after_rows = _parsed_side_rows(context.after_text, context.after_state)
    if (before_rows is None or after_rows is None or len(before_rows) != 1
            or len(after_rows) != 1 or before_rows[0][1] is None or after_rows[0][1] is None):
        return None
    return before_rows[0], after_rows[0]


def _one_sided_inverse(context):
    rows = _equation_rows(context)
    if rows is None:
        return False
    before, after = rows
    for variable_side in (0, 1):
        other_side = 1 - variable_side
        variable_expr, other_expr = before[variable_side], before[other_side]
        target_variable, target_other = after[variable_side], after[other_side]
        poly_info = _poly_for(variable_expr)
        if poly_info is None:
            continue
        variable, polynomial = poly_info
        if polynomial.degree() != 1 or other_expr.free_symbols:
            continue
        coefficient = polynomial.coeff_monomial(variable)
        constant = polynomial.coeff_monomial(1)
        target_poly_info = _poly_for(target_variable, variable)
        if target_poly_info is None:
            continue
        target_poly = target_poly_info[1]
        if (coefficient != 0 and constant != 0
                and target_poly.degree() == 1
                and _sympy_equal(target_poly.coeff_monomial(variable), coefficient)
                and target_poly.coeff_monomial(1) == 0
                and target_other.free_symbols == set()
                and _sympy_equal(target_other, other_expr + constant)
                and not _sympy_equal(before[0] - before[1], after[0] - after[1])):
            return True
    return False


def _division_sign_lost(context):
    rows = _equation_rows(context)
    if rows is None:
        return False
    before, after = rows
    for variable_side in (0, 1):
        other_side = 1 - variable_side
        poly_info = _poly_for(before[variable_side])
        if poly_info is None or before[other_side].free_symbols:
            continue
        variable, polynomial = poly_info
        coefficient = polynomial.coeff_monomial(variable)
        if (polynomial.degree() != 1 or coefficient == 0
                or polynomial.coeff_monomial(1) != 0):
            continue
        right_value = before[other_side]
        correct_root = sp.cancel(right_value / coefficient)
        if sp.Rel(correct_root, 0, '>=') == True:
            continue
        target_poly_info = _poly_for(after[variable_side], variable)
        if target_poly_info is None:
            continue
        target_poly = target_poly_info[1]
        if (target_poly.degree() == 1
                and target_poly.coeff_monomial(variable) == 1
                and target_poly.coeff_monomial(1) == 0
                and after[other_side].free_symbols == set()
                and _sympy_equal(after[other_side], -correct_root)):
            return True
    return False


def _additive_model_reversed(context):
    rows = _equation_rows(context)
    if rows is None:
        return False
    before, after = rows
    for variable_side in (0, 1):
        other_side = 1 - variable_side
        source_info = _poly_for(before[variable_side])
        target_info = _poly_for(after[variable_side])
        if source_info is None or target_info is None or source_info[0] != target_info[0]:
            continue
        variable = source_info[0]
        source, target = source_info[1], target_info[1]
        constant = source.coeff_monomial(1)
        if (source.degree() == target.degree() == 1 and constant != 0
                and _sympy_equal(source.coeff_monomial(variable), 1)
                and _sympy_equal(target.coeff_monomial(variable), 1)
                and _sympy_equal(target.coeff_monomial(1), -constant)
                and _sympy_equal(before[other_side], after[other_side])):
            return True
    return False


def _model_product_as_sum(context):
    rows = _equation_rows(context)
    if rows is None:
        return False
    before, after = rows
    for variable_side in (0, 1):
        other_side = 1 - variable_side
        source_info = _poly_for(before[variable_side])
        target_info = _poly_for(after[variable_side])
        if source_info is None or target_info is None or source_info[0] != target_info[0]:
            continue
        variable = source_info[0]
        source, target = source_info[1], target_info[1]
        coefficient = source.coeff_monomial(variable)
        right_value = before[other_side]
        if (source.degree() == 1 and source.coeff_monomial(1) == 0
                and coefficient not in (0, 1)
                and target.degree() == 1
                and target.coeff_monomial(variable) == 1
                and target.coeff_monomial(1) == 0
                and not after[other_side].free_symbols
                and _sympy_equal(after[other_side], right_value + coefficient)):
            return True
    return False


def _difference_squares_as_square(source_text, before, after):
    before_info, after_info = _poly_for(before), _poly_for(after)
    if before_info is None or after_info is None or before_info[0] != after_info[0]:
        return False
    variable = before_info[0]
    source, target = before_info[1], after_info[1]
    if source.degree() != 2 or target.degree() != 2:
        return False
    leading = source.coeff_monomial(variable ** 2)
    constant = source.coeff_monomial(1)
    if (sp.Rel(leading, 0, '<=') == True or sp.Rel(constant, 0, '>=') == True
            or source.coeff_monomial(variable) != 0
            or not _sympy_equal(target.coeff_monomial(variable ** 2), leading)):
        return False
    linear = target.coeff_monomial(variable)
    if not _sympy_equal(linear ** 2 - 4 * leading * target.coeff_monomial(1), 0):
        return False
    repeated_root = -linear / (2 * leading)
    return _sympy_equal(repeated_root ** 2, -constant / leading)


def _wrong_grouping(context, sign_error=False):
    try:
        before_rows = _parsed_side_rows(context.before_text, context.before_state)
        after_rows = _parsed_side_rows(context.after_text, context.after_state)
        if before_rows is None or after_rows is None or len(before_rows) != len(after_rows):
            return False
        for before_row, after_row in zip(before_rows, after_rows):
            for side_index in (0, 1):
                source = before_row[side_index]
                target = after_row[side_index]
                target_text = after_row[side_index + 2]
                if source is None or target is None or target_text is None:
                    continue
                source_info = _poly_for(source)
                factors = _binomial_product(target_text)
                if source_info is None or factors is None:
                    continue
                variable = source_info[0]
                source_poly = source_info[1]
                if (source_poly.degree() != 2
                        or not _sympy_equal(source_poly.coeff_monomial(variable ** 2), 1)):
                    continue
                constants = []
                for factor in factors:
                    constant = next((term for term in factor if not term.free_symbols), None)
                    if constant is None:
                        constants = []
                        break
                    constants.append(constant)
                if len(constants) != 2:
                    continue
                middle = source_poly.coeff_monomial(variable)
                constant = source_poly.coeff_monomial(1)
                if not sign_error and (_sympy_equal(sum(constants), middle)
                                       and not _sympy_equal(constants[0] * constants[1], constant)):
                    return True
                if sign_error and (_sympy_equal(constants[0] * constants[1], -constant)
                                   and not _sympy_equal(sum(constants), middle)):
                    return True
    except Exception:
        return False
    return False


def _negated_quadratic_roots(context):
    before_roots = _finite_roots(context.before_state)
    after_roots = _finite_roots(context.after_state)
    return (
        before_roots is not None and after_roots is not None
        and len(before_roots) == len(after_roots) == 2
        and {0 - sp.sympify(root) for root in before_roots} == after_roots
        and before_roots != after_roots
    )


def _trace_detector(concept_id, aliases=(), examples=(), rule=None, side_rule=None):
    aliases = frozenset(str(alias).lower() for alias in aliases)
    examples = frozenset(
        (_canonical_trace(before), _canonical_trace(after))
        for before, after in examples
    )

    def pattern_detector(context):
        if not isinstance(context, TraceContext) or context.concept_id != concept_id:
            return False
        if rule is not None:
            try:
                if rule(context):
                    return True
            except Exception:
                pass
        if side_rule is not None:
            try:
                if _transition_side_matches(context, side_rule):
                    return True
            except Exception:
                pass
        pair = (_canonical_trace(context.before_text), _canonical_trace(context.after_text))
        if pair in examples:
            return True

        # Authored common-error traces provide a second exact trace source.
        for trace in context.problem.get('common_errors', ()):
            if not isinstance(trace, dict):
                continue
            trace_id = str(trace.get('error_id', '')).lower()
            family = str(trace.get('family', '')).lower()
            if trace_id not in aliases and family not in aliases:
                continue
            raw_index = trace.get('first_error_step')
            if not isinstance(raw_index, (int, str)):
                continue
            try:
                error_index = int(raw_index)
            except ValueError:
                continue
            trace_steps = trace.get('steps')
            if (error_index != context.step_index or not isinstance(trace_steps, list)
                    or error_index < 1 or error_index > len(trace_steps)):
                continue
            if _canonical_trace(trace_steps[error_index - 1]) != pair[1]:
                continue
            if error_index > 1:
                if len(context.previous_steps) < 1:
                    continue
                if _canonical_trace(trace_steps[error_index - 2]) != _canonical_trace(context.previous_steps[-1]):
                    continue
            return True
        return False

    pattern_detector.__name__ = f'detect_{concept_id.lower()}'
    return pattern_detector


def _misconception(
    concept_id, error_id, description, aliases=(), examples=(), rule=None, side_rule=None,
):
    detector = _trace_detector(concept_id, aliases, examples, rule, side_rule)
    detector.__name__ = f'detect_{error_id.lower()}'
    return {
        'error_id': error_id,
        'description': description,
        'pattern_detector': detector,
        'trace_aliases': tuple(aliases),
        'trace_examples': tuple(examples),
    }


MISCONCEPTION_CATALOG = {
    'A01': (
        _misconception('A01', 'M_SUB_01', 'Bỏ dấu âm của giá trị khi thay vào biểu thức.',
                       aliases=('substitution_sign', 'ERR-A01-01'),
                       examples=(('2*(-2)+3', '2*2+3'),),
                       side_rule=_substitution_sign),
        _misconception('A01', 'M_SUB_02', 'Thay tích của biến với chính nó bằng một lần biến.',
                       aliases=('power_as_identity', 'ERR-A01-02'),
                       examples=(('3*x*x', '3*x'),),
                       side_rule=_power_as_identity),
    ),
    'A02': (
        _misconception('A02', 'M_DIST_01', 'Chỉ phân phối hệ số ngoài ngoặc cho hạng tử đầu.',
                       aliases=('distribution_missing_term', 'ERR-A02-01', 'ERR-LIN-003',
                                'ERR-E02-02'),
                       examples=(('3*(x+2)', '3x+2'),),
                       side_rule=_distribution_missing_term),
        _misconception('A02', 'M_DIST_02', 'Sai dấu khi nhân hệ số âm với hạng tử trong ngoặc.',
                       aliases=('distribution_sign', 'ERR-A02-02', 'ERR-LIN-004'),
                       examples=(('-2*(x-5)', '-2x-10'),),
                       side_rule=_distribution_constant_sign),
    ),
    'A03': (
        _misconception('A03', 'M_LIKE_01', 'Nhân các hạng tử thay vì cộng hệ số của hạng tử đồng dạng.',
                       aliases=('combine_as_multiply', 'ERR-A03-01'),
                       examples=(('2x+3x', '5x*x'),),
                       side_rule=_like_terms_multiplied),
        _misconception('A03', 'M_LIKE_02', 'Cộng độ lớn của các hằng số trái dấu.',
                       aliases=('constant_group', 'ERR-A03-02'),
                       examples=(('6+(-4)', '10'),),
                       side_rule=_opposite_constants_added),
    ),
    'A04': (
        _misconception('A04', 'M_POLY_01', 'Bỏ các hạng tử chéo khi nhân hai nhị thức.',
                       aliases=('missing_cross_term', 'polynomial_product_missing_terms'),
                       examples=(('(x+2)(x+3)', 'x^2+6'),),
                       side_rule=_product_missing_cross_terms),
        _misconception('A04', 'M_POLY_02', 'Sai dấu của tích hai hạng tử tự do khi nhân nhị thức.',
                       aliases=('polynomial_product_sign', 'cross_term_sign'),
                       examples=(('(x-2)(x+3)', 'x^2+x+6'),),
                       side_rule=_product_constant_sign),
    ),
    'A05': (
        _misconception('A05', 'M_SQUARE_01', 'Khai triển bình phương một tổng nhưng bỏ hạng tử giữa 2ab.',
                       aliases=('square_missing_middle_term', 'binomial_square_missing_cross_term'),
                       examples=(('(x+2)^2', 'x^2+4'),),
                       side_rule=_square_missing_middle),
        _misconception('A05', 'M_SQUARE_02', 'Nhầm bình phương một hiệu với hiệu hai bình phương.',
                       aliases=('square_as_difference_of_squares', 'binomial_square_sign'),
                       examples=(('(x-3)^2', 'x^2-9'),),
                       side_rule=_square_as_difference),
    ),
    'A06': (
        _misconception('A06', 'M_DIFFSQ_01', 'Sai dấu khi dùng hằng đẳng thức hiệu hai bình phương.',
                       aliases=('difference_of_squares_sign', 'difference_square_sign'),
                       examples=(('(x+4)(x-4)', 'x^2+16'),),
                       side_rule=_difference_square_constant_sign),
        _misconception('A06', 'M_DIFFSQ_02', 'Nhầm hiệu hai bình phương với bình phương một hiệu.',
                       aliases=('difference_of_squares_as_binomial_square',),
                       examples=(('x^2-25', '(x-5)^2'),),
                       side_rule=_difference_squares_as_square),
    ),
    'A07': (
        _misconception('A07', 'M_FACTOR_01', 'Đặt nhân tử chung nhưng không chia từng hạng tử trong ngoặc.',
                       aliases=('common_factor_incomplete', 'factor_first_term_only'),
                       examples=(('6x+9', '6(x+9)'),),
                       side_rule=_incomplete_common_factor),
        _misconception('A07', 'M_FACTOR_02', 'Bỏ mất một thừa số biến khi đưa nhân tử chung ra ngoài.',
                       aliases=('common_factor_variable_lost', 'factor_variable_lost'),
                       examples=(('4x^2+6x', '2(2x^2+3)'),),
                       side_rule=_common_factor_variable_lost),
    ),
    'A08': (
        _misconception('A08', 'M_GROUP_01', 'Ghép nhóm hạng tử không tạo thành tích tương đương.',
                       aliases=('grouping_mismatch', 'factor_by_grouping_wrong'),
                       examples=(('x^2+5x+6', '(x+1)(x+4)'),),
                       rule=lambda context: _wrong_grouping(context, sign_error=False)),
        _misconception('A08', 'M_GROUP_02', 'Phân tích tam thức thành nhân tử với cặp dấu sai.',
                       aliases=('grouping_sign', 'factorization_sign'),
                       examples=(('x^2-x-6', '(x-3)(x-2)'),),
                       rule=lambda context: _wrong_grouping(context, sign_error=True)),
    ),
    'E01': (
        _misconception('E01', 'M_EQ_01', 'Chỉ thực hiện phép toán ngược ở một vế phương trình.',
                       aliases=('one_sided_inverse', 'ERR-LIN-001', 'ERR-LIN-005'),
                       examples=(('2x+3=7', '2x=10'),),
                       rule=_one_sided_inverse),
        _misconception('E01', 'M_EQ_02', 'Làm mất dấu âm khi chia hai vế cho hệ số âm.',
                       aliases=('division_sign', 'ERR-LIN-002'),
                       examples=(('-2x=8', 'x=4'),),
                       rule=_division_sign_lost),
    ),
    'E02': (
        _misconception('E02', 'M_INV_01', 'Dùng sai phép toán ngược khi cô lập ẩn.',
                       aliases=('inverse_operation', 'one_sided_inverse', 'ERR-LIN-001',
                                'ERR-LIN-005', 'ERR-LIN-006', 'ERR-E02-01'),
                       examples=(('3x+5=20', '3x=25'),),
                       rule=_one_sided_inverse),
        _misconception('E02', 'M_SIGN_01', 'Bỏ dấu âm của hệ số khi chia để tìm ẩn.',
                       aliases=('division_sign', 'ERR-LIN-002'),
                       examples=(('-2x=8', 'x=4'),),
                       rule=_division_sign_lost),
        _misconception('E02', 'M_EQ_DIST_01', 'Chỉ phân phối hệ số cho hạng tử đầu khi giải phương trình.',
                       aliases=('distribution_missing_term', 'ERR-LIN-003', 'ERR-E02-02'),
                       examples=(('2*(x-3)=10', '2x-3=10'),),
                       side_rule=_distribution_missing_term),
        _misconception('E02', 'M_EQ_DIST_02', 'Sai dấu khi phân phối hệ số âm trong phương trình.',
                       aliases=('distribution_sign', 'ERR-LIN-004'),
                       examples=(('-3*(x-2)=12', '-3x-6=12'),),
                       side_rule=_distribution_constant_sign),
    ),
    'E03': (
        _misconception('E03', 'M_MODEL_01', 'Đổi phép cộng thành phép trừ khi lập quan hệ từ lời bài toán.',
                       aliases=('model_operation_reversed', 'word_problem_inverse'),
                       examples=(('x+4=13', 'x-4=13'),),
                       rule=_additive_model_reversed),
        _misconception('E03', 'M_MODEL_02', 'Đổi quan hệ nhân thành phép cộng khi biểu diễn đại lượng.',
                       aliases=('model_product_as_sum', 'word_problem_scale'),
                       examples=(('3x=21', 'x=21+3'),),
                       rule=_model_product_as_sum),
    ),
    'E04': (
        _misconception('E04', 'M_ZERO_02', 'Chia bỏ thừa số biến trong phương trình tích dù thừa số đó có thể bằng không.',
                       aliases=('product_variable_division', 'zero_factor_divided_out'),
                       examples=(('x*(x-4)=0', 'x-4=0'),),
                       rule=_divided_out_zero_factor),
        _misconception('E04', 'M_ZERO_01', 'Chỉ cho một thừa số bằng không và bỏ nhánh nghiệm còn lại.',
                       aliases=('zero_product_one_factor', 'product_equation_missing_branch'),
                       examples=(('(x-2)(x+3)=0', 'x-2=0'),),
                       rule=_one_missing_root),
    ),
    'E05': (
        _misconception('E05', 'M_DOMAIN_02', 'Nhận nghiệm làm mẫu số bằng không mà không loại nghiệm đó.',
                       aliases=('extraneous_denominator_root', 'denominator_zero_accepted'),
                       examples=(('(x-1)/(x+2)=0', 'x=-2'),),
                       rule=_accepted_excluded_root),
        _misconception('E05', 'M_DOMAIN_01', 'Rút gọn mẫu thức nhưng làm mất điều kiện mẫu khác không.',
                       aliases=('cancel_denominator_condition', 'domain_condition_lost'),
                       examples=(('(x-2)/(x-2)=1', '1=1'),),
                       rule=_lost_domain_condition),
    ),
    'E06': (
        _misconception('E06', 'M_QUAD_01', 'Chỉ giữ một nghiệm khi phương trình bậc hai có hai nghiệm.',
                       aliases=('quadratic_missing_root', 'one_quadratic_root'),
                       examples=(('x^2=9', 'x=3'),),
                       rule=_one_missing_root),
        _misconception('E06', 'M_QUAD_02', 'Sai dấu nghiệm khi giải phương trình bậc hai.',
                       aliases=('quadratic_root_sign', 'quadratic_formula_sign'),
                       examples=(('x^2-5x+6=0', 'x=-2 or x=-3'),),
                       rule=_negated_quadratic_roots),
    ),
}


def resolve_concept_id(problem):
    if not isinstance(problem, dict):
        return None
    explicit = problem.get('concept_id')
    if isinstance(explicit, str) and explicit in CONCEPT_IDS:
        return explicit
    for field in ('primary_skill_id', 'target_skill_id', 'skill_id'):
        value = problem.get(field)
        if isinstance(value, str):
            match = re.search(r'\b(A0[1-8]|E0[1-6])\b', value.upper())
            if match and match.group(1) in CONCEPT_IDS:
                return match.group(1)
    for field in ('problem_id', 'task_id'):
        value = problem.get(field)
        if isinstance(value, str):
            match = re.search(r'\b(A0[1-8]|E0[1-6])\b', value.upper())
            if match and match.group(1) in CONCEPT_IDS:
                return match.group(1)
    if str(problem.get('primary_skill_id', '')).upper() == 'SK-LIN-SOLVE':
        return 'E02'
    if str(problem.get('problem_id', '')).upper().startswith('LIN-'):
        return 'E02'
    return None


def detect_misconception(
    problem, *, step_index, before_text, after_text, previous_steps=(),
    before_state=None, after_state=None,
):
    """Return one catalog ID for a verified bad trace, or None if it is unknown."""
    concept_id = resolve_concept_id(problem)
    if concept_id is None or concept_id not in MISCONCEPTION_CATALOG:
        return None
    context = TraceContext(
        problem=problem,
        concept_id=concept_id,
        step_index=step_index,
        before_text=before_text,
        after_text=after_text,
        previous_steps=tuple(previous_steps),
        before_state=before_state,
        after_state=after_state,
    )
    for entry in MISCONCEPTION_CATALOG[concept_id]:
        if entry['pattern_detector'](context):
            return entry['error_id']
    return None