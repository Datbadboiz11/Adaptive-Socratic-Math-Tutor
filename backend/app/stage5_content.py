"""Two unpublished arithmetic packs to start the Stage 5 expansion safely offline."""
from copy import deepcopy

from app.content_authoring import DraftRequest, GeneratedContent, check_draft, make_draft, review_template
from app.curriculum import CurriculumRegistry, PilotBank

VERSION = "0.5.0-stage5-draft"
REVISION = "S5-R001"

# These are original drafts, not model-provider output or human-reviewed material.
SEEDS = {
    "N03": {
        "families": ["Nhân trước cộng hoặc trừ", "Ưu tiên biểu thức trong ngoặc", "Phép toán cùng mức từ trái sang phải"],
        "explanation": "Tính biểu thức trong ngoặc trước. Ngoài ngoặc, thực hiện nhân và chia trước cộng và trừ. Các phép nhân/chia cùng mức, hoặc cộng/trừ cùng mức, thực hiện từ trái sang phải. Không đổi vị trí các phép trừ hay chia nếu chưa có phép biến đổi hợp lệ.",
        "problems": [
            ("8 + 3*4", "20", ["8 + 12", "20"]),
            ("25 - 2*7", "11", ["25 - 14", "11"]),
            ("(8 + 3)*4", "44", ["11*4", "44"]),
            ("30/(7 - 2)", "6", ["30/5", "6"]),
            ("24/3*2", "16", ["8*2", "16"]),
            ("18 - 7 + 2", "13", ["11 + 2", "13"]),
        ],
        "examples": [
            ("6 + 2*5", "16", ["6 + 10", "16"]),
            ("(6 + 2)*5", "40", ["8*5", "40"]),
            ("36/6*3", "18", ["6*3", "18"]),
        ],
        "errors": [
            (0, ["11*4", "44"], "ORDER-ADD-BEFORE-MULTIPLY", "Có thể đã cộng trước khi nhân.", "Trong biểu thức không có ngoặc, phép nhân và phép cộng được ưu tiên thế nào?"),
            (4, ["24/(3*2)", "4"], "ORDER-RIGHT-GROUPING", "Có thể đã tự thêm ngoặc vào chuỗi chia rồi nhân.", "Hai phép chia và nhân cùng mức được thực hiện từ phía nào?"),
        ],
        "hints": ["Em thấy dấu ngoặc hoặc những nhóm phép toán nào trong biểu thức?",
                  "Xác định phần trong ngoặc trước; sau đó phân biệt nhóm nhân/chia với nhóm cộng/trừ.",
                  "Mỗi dòng chỉ tính một phép được ưu tiên, chép nguyên phần còn lại. Với các phép cùng mức, bắt đầu từ bên trái."],
    },
    "N06": {
        "families": ["Cộng hoặc trừ hai phân số cùng mẫu", "Hai mẫu khác nhau có quan hệ chia hết", "Hai mẫu cần tìm mẫu chung"],
        "explanation": "Muốn cộng hoặc trừ hai phân số, đưa chúng về cùng một mẫu khác không bằng cách nhân cả tử và mẫu với cùng một số khác không. Khi đã cùng mẫu, cộng hoặc trừ các tử và giữ nguyên mẫu chung; sau đó rút gọn nếu có thể. Với phân số âm, giữ dấu của từng tử khi quy đồng và khi thực hiện phép trừ.",
        "problems": [
            ("2/7 + 3/7", "5/7", ["(2 + 3)/7", "5/7"]),
            ("6/11 - 2/11", "4/11", ["(6 - 2)/11", "4/11"]),
            ("1/3 + 1/6", "1/2", ["2/6 + 1/6", "3/6", "1/2"]),
            ("5/8 - 1/4", "3/8", ["5/8 - 2/8", "3/8"]),
            ("2/3 + 1/5", "13/15", ["10/15 + 3/15", "13/15"]),
            ("-1/4 - 1/6", "-5/12", ["-3/12 - 2/12", "-5/12"]),
        ],
        "examples": [
            ("1/9 + 5/9", "2/3", ["6/9", "2/3"]),
            ("3/10 - 1/5", "1/10", ["3/10 - 2/10", "1/10"]),
            ("1/2 + 2/7", "11/14", ["7/14 + 4/14", "11/14"]),
        ],
        "errors": [
            (0, ["(2 + 3)/(7 + 7)", "5/14"], "FRACTION-ADD-DENOMINATORS", "Có thể đã cộng cả hai mẫu khi cộng hai phân số.", "Khi hai phân số đã cùng mẫu, mẫu số biểu thị đơn vị phần nào?"),
            (3, ["5/8 - 1/8", "4/8"], "FRACTION-CHANGE-DENOMINATOR-ONLY", "Có thể đã đổi mẫu nhưng không nhân tử với cùng hệ số.", "Để đổi một phần tư sang mẫu tám mà giữ nguyên giá trị, tử số cần thay đổi thế nào?"),
        ],
        "hints": ["Hai phân số đang có cùng mẫu chưa? Mẫu số của chúng có khác không?",
                  "Chọn một mẫu chung, rồi nhân cả tử lẫn mẫu của mỗi phân số với cùng hệ số phù hợp.",
                  "Viết lại hai phân số cùng mẫu trên một dòng. Cộng hoặc trừ các tử theo đúng dấu, giữ mẫu chung rồi kiểm tra rút gọn."],
    },
}


def build_drafts(registry, existing_bank):
    data = deepcopy(registry.model_dump(mode="json"))
    data["content_version"] = VERSION
    for concept in data["concepts"]:
        concept["pilot"] = concept["concept_id"] in SEEDS
        if concept["concept_id"] in SEEDS:
            concept["authoring_task_kinds"] = ["numeric"]
            concept["review"] = {"status": "draft", "author": "Codex",
                                 "source": "Stage 5 proposed numeric checker binding; independent scope review pending"}
    snapshot = CurriculumRegistry.model_validate(data)
    packs, requests, checks, reviews = [], {}, {}, {}
    for cid, seed in SEEDS.items():
        concept = next(c for c in snapshot.concepts if c.concept_id == cid)
        request = DraftRequest(concept_id=cid, revision=REVISION, author="Codex", content_version=VERSION,
            source_ids=[concept.alignment.source_id], model="offline-original-draft-no-api",
            families=[{"family_id": f"FAM-{cid}-{REVISION}-{i}", "source_group": f"GROUP-{cid}-{REVISION}-{i}",
                       "description": description} for i, description in enumerate(seed["families"], 1)])

        def case(row, index, kind):
            expression, answer, steps = row
            return {"case_id": f"{request.id_prefix}{kind}-{index + 1:02}",
                    "task": {"kind": "numeric", "expression": expression},
                    "reference_answer": answer, "reference_steps": steps}

        problems = []
        for index, row in enumerate(seed["problems"]):
            family = request.families[index // 2]
            problems.append({**case(row, index, "P"), "concept_id": cid,
                "primary_skill_id": concept.skills[0].skill_id, "family_id": family.family_id,
                "source_group": family.source_group, "difficulty": "introductory" if index < 2 else "standard",
                "prompt": f"Tính giá trị biểu thức {row[0]}. Viết các bước theo thứ tự rồi ghi kết quả.",
                "split": "authoring_dev", "origin": "Original offline AI-assisted draft; no external problem copied"})
        generated = GeneratedContent.model_validate({"explanation": seed["explanation"], "problems": problems,
            "examples": [case(row, index, "X") for index, row in enumerate(seed["examples"])],
            "errors": [{"error_id": f"{request.id_prefix}ERR-{index + 1:02}",
                        "problem_id": problems[problem]["case_id"], "response_steps": steps,
                        "first_error_step": 1, "family": family, "hypothesis": hypothesis,
                        "diagnostic_question": question, "diagnosis_status": "suspected"}
                       for index, (problem, steps, family, hypothesis, question) in enumerate(seed["errors"])],
            "hints": [{"level": level, "text": text, "disclosure": disclosure}
                      for level, text, disclosure in zip((1, 2, 3), seed["hints"], ("conceptual", "strategy", "scaffold"))]})
        pack = make_draft(generated, request)
        check = check_draft(pack, request, snapshot, existing_bank)
        if not check.passed:
            raise ValueError("Stage 5 draft failed checker: " + cid)
        packs.append(pack)
        requests[cid] = request.model_dump(mode="json")
        checks[cid] = {**check.model_dump(mode="json"), "passed": check.passed}
        reviews[cid] = review_template(pack)
    bank = PilotBank(schema_version="1.0.0", content_version=VERSION, packs=packs)
    return snapshot, bank, requests, checks, reviews
