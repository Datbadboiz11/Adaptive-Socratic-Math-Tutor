"""Bộ tình huống dev trên 78 bài đã duyệt của Member 2: nguồn của ``contracts/scenarios/approved.dev.v1.json``.

Khác bộ pilot (``pilot_dev.py``) ở ba chỗ:

- Bài, đề và nội dung KB là bản thật đã duyệt (``app.agent.approved_content``), không phải bài mẫu.
- Mọi assessment do chính validator của hệ thống chấm (``Session.work``); người soạn chỉ viết bài làm
  và kết quả mong đợi, chấm ra khác thì dừng ngay.
- Context lấy bằng ``ApprovedTools``, cùng luật chặn ví dụ cùng họ và cùng mức tiết lộ như lúc chạy.

13 pack này chỉ chấm đáp án cuối, nên hệ thống không tạo observation BKT từ chúng (``not_target_evidence``,
giống web). Vì vậy bộ này đo hành vi của tutor trên từng lượt (hỏi lại, gợi ý, đổi bài, dừng), không đo
ngưỡng mastery hay chuyển concept: những ca đó cần nhóm quyết định cách ghi bằng chứng trước.

Nhãn do AI soạn dưới sự chỉ đạo của Member 3 (``author = ai_draft``) và còn là bản nháp
(``review_status = draft``): Member 3 cần duyệt trước khi dùng để chọn ngưỡng hay báo kết quả.

    python -m research.scenarios.approved_dev            # ghi lại file JSON
    python -m research.scenarios.approved_dev --check    # file JSON có khớp nguồn này không
    python -m research.scenarios.approved_dev --sheet out.md [--blind]   # phiếu rà nhãn
"""
from __future__ import annotations

import argparse
from functools import lru_cache
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app import math_validator  # noqa: E402
from app.agent.approved_content import ApprovedTools, load_approved_content  # noqa: E402
from app.agent.kg_tool import KGTool  # noqa: E402
from app.agent.validator_analyzer import ValidatorAnalyzer  # noqa: E402
from research.scenarios.authoring import Session  # noqa: E402
from research.scenarios.contracts import (  # noqa: E402
    BKTParameters, ProblemSource, ScenarioDataset, ScenarioDraft, StrategyLabels,
)

OUT = ROOT / "contracts" / "scenarios" / "approved.dev.v1.json"
DATASET_VERSION = "adaptive-approved-dev-0.1.0"
SOURCE = ("AI-drafted scenarios under Member 3 on the 78 human-approved Member 2 problems (member2-v2). "
          "Every submission graded by the system validator. Strategy labels are drafts awaiting Member 3 review.")
AUTHOR = "ai_draft"

CONTENT = load_approved_content()
KG = KGTool(include_drafts=True)


def P(concept: str, number: int) -> str:
    return f"D-{concept}-M2-ORIG02-P-{number:02d}"


PROBLEMS = [ProblemSource(problem=p.ref, original_problem_id=p.source_group, prompt=p.prompt,
                          target_evidence=CONTENT.counts_as_evidence(pid))
            for pid, p in sorted(CONTENT.problems.items())]

# BKT không được cập nhật trên các bài này; tham số chỉ để replay dựng được state ban đầu.
PARAMETERS = {skill: BKTParameters(
    parameter_version="scenario-demo-0.1.0",
    source="Engineering assumptions for synthetic replay examples. Not fitted or calibrated for Vietnamese learners.",
    prior=0.2, learn=0.1, guess=0.2, slip=0.1)
    for skill in sorted({p.problem.target_skill_id for p in PROBLEMS})}


def session(scenario_id: str, first_problem: str) -> Session:
    analyzer = ValidatorAnalyzer(CONTENT.validator_task, validate=math_validator.validate)
    return Session(scenario_id, first_problem, problems=PROBLEMS, parameters=PARAMETERS, content=[], kg=KG,
                   source_reference=SOURCE, analyzer=analyzer, tools=ApprovedTools(CONTENT, KG))


def labels(acceptable: list[str], forbidden: list[str], rationale: str, *, intents: list[str] = (),
           skills: list[str] = ()) -> StrategyLabels:
    return StrategyLabels(acceptable_actions=acceptable, forbidden_actions=forbidden, acceptable_intents=list(intents),
                          acceptable_target_skill_ids=list(skills), author=AUTHOR, rationale=rationale,
                          review_status="draft")


# ---------------------------------------------------------------- nhãn dùng lại

def first_correct() -> StrategyLabels:
    return labels(["next_problem", "check_transfer", "diagnose"],
                  ["minimal_hint", "scaffold", "backtrack", "conceptual_question"],
                  "Đáp án cuối đúng ngay lần đầu: giao bài khác (luyện tiếp, tăng độ khó hoặc khác họ mẫu), hoặc hỏi em đã "
                  "làm thế nào. Bài chỉ chấm đáp án cuối nên chưa có bằng chứng để chuyển concept; gợi ý là thừa.",
                  intents=["continue_practice", "advance_difficulty", "elicit_reasoning"])


def first_wrong() -> StrategyLabels:
    return labels(["diagnose", "minimal_hint"], ["backtrack", "scaffold", "conceptual_question", "next_problem",
                                                 "check_transfer"],
                  "Một đáp án cuối sai, không có bước nào để định vị lỗi: hỏi em làm thế nào, nhắc em tự kiểm tra hoặc "
                  "nhắc quy tắc ở mức nhẹ. Chưa có bằng chứng hiểu sai hay thiếu kiến thức nền; không đổi bài khi vừa sai.",
                  intents=["elicit_reasoning", "prompt_self_check", "recall_rule"])


# Gate G01: bài nộp chưa chấm được (unverified, needs_clarification) chỉ nhận clarify hoặc end_session.
# Lời nhắc làm nốt hay rút gọn đi qua clarify/resolve_input. Muốn cho gợi ý ở bài đọc được nhưng chưa
# xong thì phải đổi G01 trước, rồi mới sửa hai nhãn dưới đây.
NOT_GRADED_FORBIDDEN = ["minimal_hint", "diagnose", "next_problem", "check_transfer", "backtrack", "scaffold",
                        "conceptual_question"]


def unfinished() -> StrategyLabels:
    return labels(["clarify"], NOT_GRADED_FORBIDDEN,
                  "Bài làm đúng giá trị nhưng chưa phải đáp án cuối (chưa tính xong hoặc chưa rút gọn): đề nghị em làm "
                  "nốt và nộp đúng dạng đề yêu cầu. Không coi là đúng, không coi là sai, không đổi bài. Theo G01, lời "
                  "nhắc này đi qua clarify.",
                  intents=["resolve_input"])


def unclear(rationale: str) -> StrategyLabels:
    return labels(["clarify"], NOT_GRADED_FORBIDDEN, rationale + " Theo G01, lời nhắc này đi qua clarify.",
                  intents=["resolve_input", "restate_task"])


def correct_after_hint() -> StrategyLabels:
    return labels(["check_transfer", "next_problem"], ["minimal_hint", "scaffold", "backtrack", "end_session"],
                  "Đúng nhờ gợi ý chưa phải bằng chứng độc lập: giao bài khác họ mẫu không kèm gợi ý, hoặc luyện tiếp. "
                  "Chưa tăng độ khó hay chuyển concept.",
                  intents=["continue_practice"])


def misread() -> StrategyLabels:
    return labels(["clarify", "minimal_hint", "diagnose"], ["next_problem", "backtrack", "check_transfer", "scaffold"],
                  "Em chưa hiểu đề hoặc cách nộp: diễn đạt lại yêu cầu, hỏi em hiểu đến đâu, hoặc gợi ý bước đầu ở mức "
                  "nhẹ. Chưa có bài làm nào để kết luận thiếu kiến thức nền.",
                  intents=["restate_task", "elicit_reasoning", "recall_rule"])


def scenarios() -> list[ScenarioDraft]:
    out: list[ScenarioDraft] = []

    def add(s: Session, title: str, tags: list[str], label: StrategyLabels) -> None:
        out.append(s.scenario(title, tags, label))

    # ------------------------------------------------------------------ đúng ngay lần đầu
    for sid, concept, number, answer in [("AP-01", "N02", 1, "52"), ("AP-06", "A01", 1, "-39"),
                                         ("AP-09", "A04", 5, "6*x*x+19*x-36"), ("AP-12", "A07", 1, "6*(3*x+5)"),
                                         ("AP-17", "E03", 1, "x; quyển; positive_integer; 4*x+7=39"),
                                         ("AP-20", "E06", 1, "25;{1/2,3}"), ("AP-24", "E09", 1, "1,1;(3,2)"),
                                         ("AP-26", "F02", 3, "[-7,+inf)"), ("AP-32", "F08", 1, "3^3=27;R"),
                                         ("AP-34", "N05", 1, "45/126 < 49/126"), ("AP-37", "N08", 1, "0.325")]:
        add(session(sid, P(concept, number)).work([answer], "verified_correct"),
            f"{concept}: đáp án cuối đúng ngay lần đầu", ["correct_independent", "final_answer_only"], first_correct())
    add(session("AP-02", P("N02", 1)).work(["13*4", "52"], "verified_correct"),
        "N02: nhân hai giá trị tuyệt đối trước rồi ghi đáp án đúng", ["correct_independent", "alternative_correct"],
        first_correct())
    add(session("AP-22", P("E06", 5)).work(["-56;{}"], "verified_correct"),
        "E06: biệt thức âm, ghi đúng tập nghiệm rỗng", ["correct_independent", "final_answer_only"], first_correct())

    # ------------------------------------------------------------------ sai lần đầu
    for sid, concept, number, answer, tag in [("AP-03", "N02", 1, "-52", "sign_error"),
                                              ("AP-10", "A04", 5, "6*x*x-36", "expansion_error"),
                                              ("AP-27", "F02", 3, "[7,+inf)", "sign_error"),
                                              ("AP-30", "F05", 1, "(-3,88)", "sign_error"),
                                              ("AP-36", "N05", 1, "45/126 > 49/126", "comparison_error")]:
        add(session(sid, P(concept, number)).work([answer], "verified_incorrect"),
            f"{concept}: đáp án cuối sai ở lần đầu", ["final_answer_only", "insufficient_evidence", tag], first_wrong())
    add(session("AP-15", P("A10", 3)).work(["x-2|x-5;{5}"], "verified_incorrect"),
        "A10: rút gọn đúng nhưng thiếu một giá trị bị loại của ẩn", ["condition_error", "final_answer_only"],
        labels(["minimal_hint", "diagnose"], ["next_problem", "check_transfer", "backtrack", "scaffold"],
               "Phân thức kết quả đúng nhưng điều kiện thiếu giá trị làm mẫu của phân thức ban đầu bằng 0: nhắc em xét "
               "mọi mẫu xuất hiện trong phép tính, hoặc hỏi em tìm điều kiện thế nào. Không đổi bài khi chưa sửa.",
               intents=["recall_rule", "prompt_self_check", "locate_error", "elicit_reasoning"]))
    add(session("AP-33", P("F08", 1)).work(["3^3=27;(0,+inf)"], "verified_incorrect"),
        "F08: lũy thừa đúng nhưng ghi tập giá trị thay cho tập xác định", ["final_answer_only", "concept_confusion"],
        labels(["minimal_hint", "diagnose"], ["next_problem", "check_transfer", "backtrack", "scaffold"],
               "Phần lũy thừa đúng; phần tập xác định em ghi (0,+inf), là tập giá trị của hàm mũ. Nhắc lại tập xác "
               "định là tập các x được phép, hoặc hỏi em hiểu tập xác định là gì. Chưa đủ để giải thích dài.",
               intents=["recall_rule", "locate_error", "elicit_reasoning"]))

    # ------------------------------------------------------------------ đúng giá trị nhưng chưa xong
    for sid, concept, number, answer, title in [
            ("AP-04", "N02", 1, "(-13)*(-4)", "chép lại phép tính của đề"),
            ("AP-07", "A01", 1, "7*(-4)-11", "mới thay x, chưa tính"),
            ("AP-21", "E06", 1, "25;{2/4,3}", "nghiệm chưa rút gọn"),
            ("AP-29", "F05", 3, "x=12/8", "phân số chưa tối giản")]:
        add(session(sid, P(concept, number)).work([answer], "unfinished"),
            f"{concept}: đúng giá trị nhưng {title}", ["unfinished_answer"], unfinished())

    # ------------------------------------------------------------------ chưa chấm được
    add(session("AP-05", P("N02", 1)).work(["abc ?"], "needs_clarification"),
        "N02: nộp nội dung không đọc được", ["ambiguous_input"],
        labels(["clarify"], ["minimal_hint", "scaffold", "backtrack", "conceptual_question", "next_problem"],
               "Không có gì để chấm: hỏi lại em muốn nộp gì và nhắc cách nộp. Gợi ý lúc này là đoán lỗi khi chưa có bài "
               "làm.", intents=["resolve_input", "restate_task"]))
    add(session("AP-13", P("A07", 1)).work(["2*(9*x+15)"], "needs_clarification"),
        "A07: đặt nhân tử chung nhưng chưa phải nhân tử chung lớn nhất", ["ambiguous_input", "unfinished_answer"],
        unclear("Biểu thức bằng đề nhưng 2 chưa phải nhân tử chung lớn nhất, đề lại yêu cầu lớn nhất: nhắc em xem "
                "trong ngoặc còn đặt chung được nữa không, hoặc nhắc lại yêu cầu của đề. Không đổi bài."))
    add(session("AP-18", P("E03", 1)).work(["x = 8"], "needs_clarification"),
        "E03: giải ra x thay vì nộp ẩn, đơn vị, điều kiện và phương trình", ["ambiguous_input", "misread_task"],
        unclear("Đề yêu cầu lập phương trình theo mẫu nộp, em lại nộp giá trị của x: nhắc lại em cần nộp gì. Bài "
                "lời văn chưa có phương trình nên không chấm được cách lập."))
    add(session("AP-35", P("N05", 1)).work(["5/14 < 7/18"], "needs_clarification"),
        "N05: so sánh đúng nhưng chưa quy đồng như đề yêu cầu", ["ambiguous_input", "unfinished_answer"],
        unclear("Đề yêu cầu ghi hai phân số cùng mẫu; em chỉ ghi dấu so sánh: nhắc em quy đồng rồi ghi lại. Chưa xác "
                "minh được em so sánh bằng cách nào."))
    add(session("AP-40", P("N08", 5)).work(["6.25/100"], "needs_clarification"),
        "N08: đổi phần trăm thành phân số nhưng chưa đưa về phân số tối giản", ["ambiguous_input", "unfinished_answer"],
        unclear("Em mới viết lại 6,25% thành phép chia cho 100, chưa phải phân số tối giản như đề yêu cầu: đề nghị em "
                "làm tiếp hoặc nhắc dạng đáp án."))

    # ------------------------------------------------------------------ lời nhắn, xin gợi ý, xin đáp án
    add(session("AP-11", P("A04", 1)).hint(),
        "A04: xin gợi ý khi chưa nộp gì", ["hint_request", "insufficient_evidence"],
        labels(["diagnose", "minimal_hint", "clarify"], ["scaffold", "backtrack", "next_problem", "conceptual_question"],
               "Chưa có bài làm nên chưa biết em kẹt ở đâu: hỏi em đã thử gì, hoặc nhắc quy tắc nhân đơn thức với đa thức "
               "ở mức nhẹ. Chia nhỏ bước hay ví dụ mẫu là hỗ trợ quá mức khi em chưa thử.",
               intents=["elicit_reasoning", "recall_rule", "restate_task"]))
    add(session("AP-16", P("A10", 1)).message("Em không hiểu dấu | trong đề là gì ạ."),
        "A10: không hiểu cách ghi phân thức của đề", ["misread_task"], misread())
    add(session("AP-19", P("E03", 3)).message("Em không hiểu đề bài hỏi gì ạ."),
        "E03: nhắn là không hiểu đề bài toán lời văn", ["misread_task"], misread())
    add(session("AP-23", P("E06", 1)).work(["25;{-1/2,-3}"], "verified_incorrect")
        .tutor("diagnose", "elicit_reasoning").message("Thầy cho em đáp án luôn được không ạ?"),
        "E06: xin đáp án trực tiếp sau một lần sai dấu nghiệm", ["requests_answer"],
        labels(["minimal_hint", "diagnose"], ["next_problem", "check_transfer", "end_session", "scaffold"],
               "Không đưa đáp án. Biệt thức đúng, hai nghiệm sai dấu: nhắc lại công thức nghiệm (dấu của -b) hoặc hỏi "
               "em thay b vào thế nào. Kết thúc phiên hay đổi bài là bỏ mặc yêu cầu hỗ trợ.",
               intents=["recall_rule", "locate_error", "prompt_self_check", "elicit_reasoning"]))

    # ------------------------------------------------------------------ sau khi đã hỗ trợ
    add(session("AP-08", P("A01", 1)).work(["-17"], "verified_incorrect")
        .tutor("diagnose", "elicit_reasoning").work(["-17"], "verified_incorrect"),
        "A01: nộp lại đúng đáp án sai sau khi được hỏi cách làm", ["repeated_error", "final_answer_only"],
        labels(["minimal_hint"], ["diagnose", "next_problem", "check_transfer", "end_session", "backtrack"],
               "Em nộp lại đúng đáp án sai, không trả lời câu hỏi cách làm: hỏi tiếp không thêm thông tin. Tăng một "
               "nấc: nhắc quy tắc nhân số âm hoặc chỉ phần cần tính lại (7·(-4)).",
               intents=["recall_rule", "locate_error"]))
    add(session("AP-14", P("A07", 1)).work(["6*(3*x+30)"], "verified_incorrect")
        .tutor("minimal_hint", "prompt_self_check", 1).work(["6*(3*x+5)"], "verified_correct"),
        "A07: sửa đúng sau một gợi ý tự kiểm tra", ["correct_after_hint"], correct_after_hint())
    add(session("AP-25", P("E09", 1)).work(["1,1;(3,-2)"], "verified_incorrect")
        .tutor("diagnose", "elicit_reasoning").work(["1,1;(3,-2)"], "verified_incorrect")
        .tutor("minimal_hint", "locate_error", 1).work(["1,1;(3,-2)"], "verified_incorrect")
        .tutor("minimal_hint", "recall_rule", 2).hint("Em vẫn chưa thấy sai ở đâu ạ."),
        "E09: kẹt sau khi đã hỏi và gợi ý hai mức, vẫn sai dấu của y", ["stuck_after_hints", "repeated_error"],
        labels(["scaffold"], ["next_problem", "check_transfer", "diagnose", "end_session"],
               "Ba lần cùng một đáp án sai sau hai mức gợi ý: cần hỗ trợ mạnh hơn, như chia nhỏ bước thay x vào một "
               "phương trình để tìm y, hoặc một ví dụ tương tự. Hỏi lại là lặp; đổi bài là bỏ lỗi chưa sửa."))
    add(session("AP-28", P("F02", 1)).work(["R\\{-19}"], "verified_incorrect")
        .tutor("minimal_hint", "recall_rule", 1).work(["R\\{19}"], "verified_correct")
        .tutor("check_transfer", "independent_check", problem=P("F02", 3)).work(["[-7,+inf)"], "verified_correct"),
        "F02: sửa đúng nhờ gợi ý rồi làm đúng bài kiểm tra khác họ mẫu", ["correct_independent", "transfer_success"],
        labels(["next_problem"], ["minimal_hint", "scaffold", "backtrack", "diagnose", "conceptual_question"],
               "Bài khác họ mẫu (căn thức thay cho phân thức) đúng không cần gợi ý: luyện tiếp hoặc tăng độ khó. Bài "
               "chỉ chấm đáp án cuối nên chưa có bằng chứng để chuyển concept.",
               intents=["continue_practice", "advance_difficulty"]))
    add(session("AP-31", P("F05", 3)).work(["x=3/2"], "verified_correct")
        .tutor("check_transfer", "independent_check", problem=P("F05", 1)).work(["(-3,88)"], "verified_incorrect"),
        "F05: đúng trục đối xứng, sang bài tìm đỉnh khác họ mẫu thì sai", ["transfer_failure", "final_answer_only"],
        labels(["diagnose", "minimal_hint"], ["next_problem", "check_transfer", "end_session", "backtrack", "scaffold"],
               "Đúng hoành độ đỉnh ở bài trước nhưng bài này sai cả dấu hoành độ: hỏi em tìm hoành độ đỉnh thế nào, hoặc "
               "nhắc công thức -b/(2a). Không đổi bài khi vừa sai.",
               intents=["elicit_reasoning", "recall_rule", "prompt_self_check"]))

    # ------------------------------------------------------------------ tạm dừng
    add(session("AP-38", P("N08", 1)).work(["3.25"], "verified_incorrect")
        .tutor("minimal_hint", "prompt_self_check", 1).pause("Em mệt rồi, cho em nghỉ một lát ạ."),
        "N08: xin tạm dừng giữa lúc đang sai", ["pause_request"],
        labels(["end_session"], ["minimal_hint", "diagnose", "scaffold", "conceptual_question", "backtrack",
                                 "next_problem", "check_transfer"],
               "Học sinh xin dừng thì cho dừng; không tiếp tục hỏi hay gợi ý. Tạm dừng không bị tính là trả lời sai.",
               intents=["student_request"]))
    add(session("AP-39", P("N08", 1)).work(["3.25"], "verified_incorrect")
        .tutor("minimal_hint", "prompt_self_check", 1).pause("Em nghỉ một chút ạ.")
        .tutor("end_session", "student_request").resume(),
        "N08: quay lại sau khi tạm dừng ở bài đang sai", ["resume"],
        labels(["minimal_hint", "diagnose", "clarify"], ["next_problem", "end_session", "backtrack", "check_transfer"],
               "Em quay lại bài còn dang dở: nhắc lại yêu cầu, hỏi em nhớ đến đâu hoặc gợi ý tiếp ở mức đã dừng. "
               "Không đổi bài và không kết thúc phiên lần nữa."))
    return sorted(out, key=lambda s: s.scenario_id)


@lru_cache(maxsize=1)
def dataset() -> ScenarioDataset:
    return ScenarioDataset(dataset_version=DATASET_VERSION, parameters=PARAMETERS, problems=PROBLEMS,
                           scenarios=scenarios())


def rendered() -> bytes:
    return (dataset().model_dump_json(indent=2) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    from research.scenarios.pilot_dev import review_sheet

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="chỉ kiểm tra file JSON khớp nguồn")
    parser.add_argument("--sheet", type=Path, help="ghi phiếu rà soát Markdown ra file này")
    parser.add_argument("--blind", action="store_true", help="phiếu không có nhãn, để gán nhãn độc lập")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    if args.sheet:
        args.sheet.parent.mkdir(parents=True, exist_ok=True)
        args.sheet.write_bytes((review_sheet(args.blind, dataset(), KG) + "\n").encode("utf-8"))
        print(f"Wrote {args.sheet}")
        return 0
    content = rendered()
    if args.check:
        if not OUT.exists() or OUT.read_bytes() != content:
            print(f"FAIL: {OUT.relative_to(ROOT)} differs from research/scenarios/approved_dev.py; "
                  "run it without --check")
            return 1
        print(f"PASS: {OUT.relative_to(ROOT)} matches its source ({len(dataset().scenarios)} scenarios)")
        return 0
    OUT.write_bytes(content)
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(dataset().scenarios)} scenarios)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
