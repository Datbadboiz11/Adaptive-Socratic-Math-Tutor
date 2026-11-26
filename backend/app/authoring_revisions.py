"""Stage 2 revision checks and traceable A07 draft fragments, without publication."""
import ast
import re

from app.authoring_math import audit_case, first_error, polynomial, scalar
from app.content_authoring import digest
from app.curriculum import AuthoredProblem, ErrorFixture, MathCase
from app.oatutor_import import require


def check_text_encoding(value):
    """Catch common lossy Windows pipe conversions, while allowing real question marks."""
    if isinstance(value, str):
        require("\ufffd" not in value and "\x00" not in value
                and not re.search(r"[A-Za-z]\?[A-Za-z]|\?{2,}[A-Za-z]", value),
                "Possible lossy text encoding; preserve UTF-8 before freezing a revision")
    elif isinstance(value, dict):
        for item in value.values():
            check_text_encoding(item)
    elif isinstance(value, list):
        for item in value:
            check_text_encoding(item)


def distribution_shape(expression):
    # Parse only after the bounded checker has rejected unsupported syntax.
    polynomial(expression)
    node = ast.parse(expression, mode="eval").body
    require(isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult), "A02 requires a factor times a binomial")
    factor, binomial = node.left, node.right
    coefficient = scalar(ast.unparse(factor))
    require(coefficient != 0 and isinstance(binomial, ast.BinOp)
            and isinstance(binomial.op, (ast.Add, ast.Sub)), "A02 requires a nonzero factor and a sum/difference")
    require(polynomial(ast.unparse(binomial))[1] != 0, "A02 binomial must contain the variable")
    return coefficient, "sum" if isinstance(binomial.op, ast.Add) else "difference"


def check_expanded_linear_answer(expression):
    polynomial(expression)
    node = ast.parse(expression, mode="eval").body

    def number(term):
        if isinstance(term, ast.Constant):
            return type(term.value) in (int, float)
        if isinstance(term, ast.UnaryOp) and isinstance(term.op, (ast.USub, ast.UAdd)):
            return number(term.operand)
        return (isinstance(term, ast.BinOp) and isinstance(term.op, ast.Div)
                and number(term.left) and number(term.right))

    def degrees(term):
        if isinstance(term, ast.BinOp) and isinstance(term.op, (ast.Add, ast.Sub)):
            return degrees(term.left) + degrees(term.right)
        if number(term):
            return [0]
        if isinstance(term, ast.Name) and term.id == "x":
            return [1]
        if isinstance(term, ast.BinOp) and isinstance(term.op, ast.Mult):
            if number(term.left) and isinstance(term.right, ast.Name) and term.right.id == "x":
                return [1]
            if number(term.right) and isinstance(term.left, ast.Name) and term.left.id == "x":
                return [1]
        raise ValueError("A02 final answer must be expanded and collected")

    terms = degrees(node)
    require(terms.count(0) <= 1 and terms.count(1) <= 1, "A02 final answer has uncollected terms")


def check_stage2_scope(prepared, staged_registry):
    a02 = prepared["A02"]["draft.json"]
    concept = next(c for c in staged_registry.concepts if c.concept_id == "A02")
    require("Đặt nhân tử chung tuyến tính" not in concept.supported_forms, "A02 scope still includes A07")
    families = prepared["A02"]["request.json"]["families"]
    for problem in a02["problems"]:
        coefficient, operation = distribution_shape(problem["task"]["expression"])
        family_index = next(i for i, f in enumerate(families) if f["family_id"] == problem["family_id"])
        require((family_index == 0 and coefficient > 0 and operation == "sum")
                or (family_index == 1 and coefficient > 0 and operation == "difference")
                or (family_index == 2 and coefficient < 0), "A02 problem does not match its declared family")
    for example in a02["examples"]:
        distribution_shape(example["task"]["expression"])
    for case in [*a02["problems"], *a02["examples"]]:
        check_expanded_linear_answer(case["reference_answer"])
    for text in [a02["explanation"], *[h["text"] for h in a02["hints"]]]:
        require("nhân tử chung" not in text.casefold(), "A07 instructions remain in A02 teaching text")
    e02 = prepared["E02"]["draft.json"]
    require("chia cho 0 không xác định" in e02["explanation"], "E02 needs the reason for nonzero division")


def a07_fragment(previous_files, registry, selection):
    pack = previous_files["A02/draft.json"]
    require(digest(pack) == selection["previous_pack_sha256"], "Previous A02 pack changed")
    concept = next(c for c in registry.concepts if c.concept_id == "A07")
    original_problems = [p for p in pack["problems"] if p["family_id"] == "FAM-A02-reverse"]
    require(len(original_problems) == 2, "Expected exactly two A07 transfers")
    provenance_by_id = {p["record_id"]: p for p in previous_files["A02/provenance.json"]}
    problems, provenance, mapping = [], [], {}
    for index, original in enumerate(original_problems, 1):
        new_id = f"D-A07-{selection['revision']}-P-{index:02}"
        data = {**original, "case_id": new_id, "concept_id": "A07", "primary_skill_id": concept.skills[0].skill_id,
                "family_id": "FAM-A07-linear-common", "source_group": "GROUP-A07-linear-common",
                "origin": "Transferred AI-authored draft from " + original["case_id"] + "; not a newly collected problem."}
        problem = AuthoredProblem.model_validate(data)
        audit_case(problem)
        problems.append(problem.model_dump(mode="json"))
        mapping[original["case_id"]] = new_id
        provenance.append({"record_id": new_id, "previous_record_id": original["case_id"],
                           "previous_pack_sha256": digest(pack), "origin_kind": "relocated_ai_generated_draft",
                           "split_group": provenance_by_id[original["case_id"]]["split_group"],
                           "human_review": "pending", "not_a_new_independent_problem": True})
    examples = []
    for original in pack["examples"]:
        expression = original["task"]["expression"]
        if expression == "9*x-36":
            data = {**original, "case_id": f"D-A07-{selection['revision']}-EX-01"}
            example = MathCase.model_validate(data)
            audit_case(example)
            examples.append(example.model_dump(mode="json"))
            provenance.append({"record_id": data["case_id"], "previous_record_id": original["case_id"],
                               "origin_kind": "relocated_ai_generated_draft", "split_group": "PROJECT-A02-SUPPORT-DEV",
                               "human_review": "pending", "not_a_new_independent_problem": True})
    errors = []
    for original in pack["errors"]:
        if original["problem_id"] in mapping:
            data = {**original, "error_id": f"D-A07-{selection['revision']}-ERR-{len(errors)+1:02}",
                    "problem_id": mapping[original["problem_id"]]}
            error = ErrorFixture.model_validate(data)
            problem = next(p for p in problems if p["case_id"] == error.problem_id)
            require(first_error(AuthoredProblem.model_validate(problem), error.response_steps) == error.first_error_step,
                    "Transferred error label is incorrect")
            errors.append(error.model_dump(mode="json"))
    query_ids = {"DEV-A02-03", "DEV-A02-04", "DEV-A02-09", "DEV-A02-10"}
    queries = [{"previous_query_id": q["query_id"], "concept_id": "A07", "target_skill_id": concept.skills[0].skill_id,
                "text": q["text"], "purpose": q["purpose"], "label_status": "unlabeled_fragment",
                "split_group": "PROJECT-A02-REVERSE-DEV"}
               for q in previous_files["dev-proposal.json"]["queries"] if q["query_id"] in query_ids]
    require(len(examples) == 1 and len(errors) == 1 and len(queries) == 4, "Incomplete A07 transfer provenance")
    return {"concept_id": "A07", "revision": selection["revision"], "status": "partial_draft_not_pack",
            "complete_pack": False, "runtime_publication": False, "human_review": "pending",
            "previous_batch": selection["previous_batch"], "previous_pack_sha256": digest(pack),
            "problems": problems, "examples": examples, "errors": errors, "query_drafts": queries,
            "provenance": provenance, "new_independent_problems": 0,
            "remaining": "Needs at least six problems across three families, explanation/hints, curriculum review "
                         "and integration capability; two transferred problems do not complete A07."}
