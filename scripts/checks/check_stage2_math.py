"""Independent SymPy cross-check of staged answers, every reference step and first-error labels."""
import ast
import json
from pathlib import Path
import re

import sympy as sp

ROOT = Path(__file__).resolve().parents[2]
BATCH = ROOT / "content/authoring/batches/a02-e02-oatutor.v2"
X = sp.Symbol("x", real=True)


def symbolic(text):
    # No eval/sympify of source strings: construct a bounded SymPy expression from AST nodes.
    if len(text) > 160 or not re.fullmatch(r"[0-9x+*/().\s-]+", text):
        raise ValueError("Unsupported symbolic audit input")
    tree = ast.parse(text.strip(), mode="eval")
    if len(list(ast.walk(tree))) > 80:
        raise ValueError("Audit input exceeds the node budget")

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return sp.Rational(ast.get_source_segment(text.strip(), node))
        if isinstance(node, ast.Name) and node.id == "x":
            return X
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return visit(node.operand) if isinstance(node.op, ast.UAdd) else -visit(node.operand)
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if isinstance(node.op, ast.Div) and right != 0: return left / right
        raise ValueError("Unsupported symbolic audit operator")

    return sp.expand(visit(tree.body))


def value(kind, expression):
    if kind == "polynomial" or "=" not in expression:
        return symbolic(expression)
    if expression.count("=") != 1:
        raise ValueError("Expected one equation")
    left, right = expression.split("=")
    equation = symbolic(left) - symbolic(right)
    if sp.Poly(equation, X).degree() != 1:
        raise ValueError("Expected a linear equation with a unique solution")
    return sp.solve(equation, X)[0]


def audit():
    data = lambda name: json.loads((BATCH / name).read_text(encoding="utf-8"))
    containers = [data(cid + "/draft.json") for cid in ("A02", "E02")] + [data("A07-fragment.json")]
    cases, errors, steps_checked = [], [], 0
    for container in containers:
        for case in [*container["problems"], *container["examples"]]:
            kind = case["task"]["kind"]
            target = value(kind, case["task"]["expression"])
            for response in [case["reference_answer"], *case["reference_steps"]]:
                if sp.simplify(value(kind, response) - target) != 0:
                    raise ValueError("Independent math mismatch: " + case["case_id"])
            steps_checked += len(case["reference_steps"])
            cases.append({"case_id": case["case_id"], "target": str(target), "passed": True})
        problems = {p["case_id"]: p for p in container["problems"]}
        for error in container["errors"]:
            problem = problems[error["problem_id"]]
            kind = problem["task"]["kind"]
            target = value(kind, problem["task"]["expression"])
            different = [index for index, response in enumerate(error["response_steps"], 1)
                         if sp.simplify(value(kind, response) - target) != 0]
            if not different or different[0] != error["first_error_step"]:
                raise ValueError("Independent first-error mismatch: " + error["error_id"])
            errors.append({"error_id": error["error_id"], "first_error_step": different[0], "passed": True})
    return {"engine": "SymPy", "version": sp.__version__, "passed": True, "cases": len(cases),
            "reference_steps": steps_checked, "error_fixtures": len(errors), "case_results": cases,
            "error_results": errors, "note": "Authoring audit only, not an online learner validator or human review"}


if __name__ == "__main__":
    result = audit()
    print(json.dumps({key: value for key, value in result.items() if key not in ("case_results", "error_results")}, ensure_ascii=True))
