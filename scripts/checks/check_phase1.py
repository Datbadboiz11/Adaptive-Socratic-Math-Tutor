"""Audit curated authoring content; this is NOT the learner-input validator."""
import ast
from collections import Counter
from fractions import Fraction
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.contracts import ContentBank  # noqa: E402


def linear_expression(source: str) -> tuple[Fraction, Fraction]:
    """Evaluate a bounded arithmetic AST as ax+b, without eval or symbolic parsing."""
    if len(source) > 160 or not re.fullmatch(r"[0-9x+*/().\s-]+", source):
        raise ValueError("Unsupported expression")
    source = re.sub(r"(?<=[0-9)])(?=[x(])", "*", source.replace(" ", ""))
    tree = ast.parse(source, mode="eval")
    if len(list(ast.walk(tree))) > 80:
        raise ValueError("Expression too complex")

    def visit(node, depth=0):
        if depth > 12:
            raise ValueError("Expression too deep")
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            text = ast.get_source_segment(source, node)
            if not re.fullmatch(r"\d{1,5}(?:\.\d{1,4})?", text):
                raise ValueError("Number exceeds grammar")
            return Fraction(0), Fraction(text)
        if isinstance(node, ast.Name) and node.id == "x":
            return Fraction(1), Fraction(0)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            a, b = visit(node.operand, depth + 1)
            return (-a, -b) if isinstance(node.op, ast.USub) else (a, b)
        if isinstance(node, ast.BinOp):
            a, b = visit(node.left, depth + 1)
            c, d = visit(node.right, depth + 1)
            if isinstance(node.op, ast.Add):
                return a + c, b + d
            if isinstance(node.op, ast.Sub):
                return a - c, b - d
            if isinstance(node.op, ast.Mult) and not (a and c):
                return a * d + b * c, b * d
            if isinstance(node.op, ast.Div) and c == 0 and d:
                return a / d, b / d
        raise ValueError("Unsupported operator or nonlinear expression")

    return visit(tree.body)


def solution(equation: str) -> Fraction:
    if equation.count("=") != 1:
        raise ValueError("Expected one equation")
    left, right = equation.split("=")
    a, b = linear_expression(left)
    c, d = linear_expression(right)
    if a == c:
        raise ValueError("Expected a unique solution")
    return (d - b) / (a - c)


def audit():
    bank = ContentBank.model_validate_json((ROOT / "content/linear_equations.v1.json").read_text(encoding="utf-8"))
    results = []
    for problem in bank.problems:
        answer = solution(problem.equation)
        assert answer == Fraction(problem.reference_answer), problem.problem_id
        for method in problem.reference_methods:
            assert all(solution(step) == answer for step in method.steps), (problem.problem_id, method.name)
        for error in problem.common_errors:
            prior = answer
            wrong_steps = []
            for index, step in enumerate(error.steps, 1):
                current = solution(step)
                if current != prior:
                    wrong_steps.append(index)
                prior = current
            assert wrong_steps == [error.first_error_step], (problem.problem_id, wrong_steps)
        example = problem.worked_example
        example_answer = solution(example.equation)
        assert example_answer == Fraction(example.answer)
        assert example_answer != answer, "Avoid accidentally revealing the current answer"
        assert all(solution(step) == example_answer for step in example.steps)
        public = problem.to_public().model_dump()
        assert not {"reference_answer", "reference_methods", "common_errors", "hint_ladder", "worked_example"}.intersection(public)
        results.append({"problem_id": problem.problem_id, "math_check": "pass", "human_review": problem.review.status})
    families = Counter(p.family_id for p in bank.problems)
    assert len(families) == 3 and all(count >= 2 for count in families.values())
    return {"content_version": bank.content_version, "problems": results, "family_counts": dict(families), "note": "Authoring checks only; human pedagogical review and learner validator are pending."}


if __name__ == "__main__":
    result = audit()
    if "--write-report" in sys.argv:
        target = ROOT / "docs/implementation/mvp/phase1/evidence/content-check.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
