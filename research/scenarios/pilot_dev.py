"""Bộ tình huống dev pilot (plan §11.5, §12): nguồn của ``contracts/scenarios/pilot.dev.v1.json``.

33 ca tổng hợp, cố định split dev, dùng để thử quy trình gán nhãn và chọn ngưỡng. KHÔNG phải bộ test.
Lịch sử, assessment và nhãn do AI soạn dưới sự chỉ đạo của Member 3 (``author = ai_draft``); Member 3
đã duyệt nhãn (``review_status = human_approved``, ``reviewer = member3``). Nhãn được viết từ tình huống
sư phạm, không lấy đầu ra của Rule-policy làm đáp án. Chưa có nhãn độc lập của người thứ hai.

    python -m research.scenarios.pilot_dev            # ghi lại file JSON
    python -m research.scenarios.pilot_dev --check    # file JSON có khớp nguồn này không
    python -m research.scenarios.pilot_dev --describe # in state của từng ca để rà nhãn
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.agent.kg_tool import KGTool  # noqa: E402
from app.agent.stubs import DEMO_CONTENT, DEMO_PROBLEMS  # noqa: E402
from app.agent.tools import ProblemRef, RetrievedContent  # noqa: E402
from research.scenarios.authoring import Session  # noqa: E402
from research.scenarios.contracts import (  # noqa: E402
    BKTParameters, ProblemSource, ScenarioDataset, ScenarioDraft, StrategyLabels,
)

OUT = ROOT / "contracts" / "scenarios" / "pilot.dev.v1.json"
DATASET_VERSION = "adaptive-pilot-dev-0.2.0"
SOURCE = ("AI-drafted synthetic pilot under Member 3. Strategy labels reviewed and approved by Member 3; "
          "problems marked pilot-0.1.0 and their wording still need content review.")
AUTHOR = "ai_draft"
# Member 3 duyệt cả 33 nhãn. Member 3 phát triển policy, nên đây chưa phải nhãn độc lập: pilot hai người
# của plan §12 vẫn cần một thành viên khác gán nhãn bằng phiếu không có nhãn (--blind).
REVIEWER = "member3"

N01, A02, A03 = "SK-N01-SIGNED-ADD", "SK-A02-DISTRIBUTE", "SK-A03-COLLECT"
E02, E03, E05 = "SK-E02-SOLVE", "SK-E03-PRIMARY", "SK-E05-PRIMARY"

# Tham số BKT: cùng giả định kỹ thuật với bộ ví dụ, chưa fit và chưa hiệu chỉnh cho người học Việt Nam.
PARAMETERS = {skill: BKTParameters(
    parameter_version="scenario-demo-0.1.0",
    source="Engineering assumptions for synthetic replay examples. Not fitted or calibrated for Vietnamese learners.",
    prior=0.2, learn=0.1, guess=0.2, slip=0.1) for skill in (N01, A02, A03, E02, E03, E05)}


def _pilot(pid: str, concept: str, skill: str, family: str, prompt: str, difficulty: int = 1,
           version: str = "pilot-0.1.0") -> ProblemSource:
    ref = ProblemRef(problem_id=pid, problem_version=version, concept_id=concept, target_skill_id=skill,
                     template_family_id=family, difficulty=difficulty)
    return ProblemSource(problem=ref, original_problem_id=pid, prompt=prompt)


# Bài của ngân hàng mẫu (giữ nguyên mã, họ mẫu và đề) và bài pilot thêm họ mẫu mới để một skill có đủ
# bài khác họ cho các observation độc lập.
PROBLEMS = [
    *(ProblemSource(problem=p.ref, original_problem_id=pid, prompt=p.prompt) for pid, p in DEMO_PROBLEMS.items()),
    # Bài của bộ ví dụ (examples.dev.v1.json): giữ nguyên mã và phiên bản.
    _pilot("N01-EX-P002", "N01", N01, "signed_add_positive_first", "Tính 5 + (-8).", version="example-0.1.0"),
    _pilot("N01-PL-P003", "N01", N01, "signed_subtract", "Tính (-4) - 6."),
    _pilot("A02-PL-P003", "A02", A02, "distribute_coefficient", "Khai triển 3(2x - 5)."),
    _pilot("A03-PL-P001", "A03", A03, "collect_basic", "Thu gọn 3x + 5 - x + 2."),
    _pilot("A03-PL-P002", "A03", A03, "collect_negative", "Thu gọn 4a - 7 - 6a + 1."),
    _pilot("E02-PL-P004", "E02", E02, "linear_two_step", "Giải phương trình 3x + 5 = 20."),
    _pilot("E02-PL-P005", "E02", E02, "linear_negative_coefficient", "Giải phương trình -4x + 6 = -10."),
    _pilot("E02-PL-P006", "E02", E02, "linear_distribution_negative", "Giải phương trình 7 - 2(x + 1) = 1.", 2),
    _pilot("E05-PL-P001", "E05", E05, "rational_same_denominator",
           "Giải phương trình (x + 1)/(x - 2) = 3/(x - 2).", 2),
]

CONTENT = [
    *DEMO_CONTENT,
    RetrievedContent(content_id="KB-A03-HINT-PL-01", skill_id=A03, content_type="hint", disclosure_level=1,
                     text="Chỉ cộng trừ được các hạng tử có cùng phần biến; nhớ mang theo dấu đứng trước mỗi hạng tử."),
    RetrievedContent(content_id="KB-E03-HINT-PL-01", skill_id=E03, content_type="hint", disclosure_level=1,
                     text="Gọi số cần tìm là x, rồi viết lại từng ý của đề thành phép toán với x."),
    RetrievedContent(content_id="KB-E05-HINT-PL-01", skill_id=E05, content_type="hint", disclosure_level=1,
                     text="Phương trình chứa ẩn ở mẫu: tìm điều kiện để mẫu khác 0 trước, giải xong thì đối chiếu "
                          "nghiệm với điều kiện đó."),
]

KG = KGTool(include_drafts=True)

# Bài làm dùng lại nhiều lần.
P001_RIGHT = ["2x - 6 = 10", "2x = 16", "x = 8"]
P001_DIST = ["2x - 3 = 10", "2x = 13", "x = 6.5"]       # chỉ nhân 2 với số hạng đầu
P001_SLIP = ["2x - 6 = 10", "2x = 4", "x = 2"]          # phân phối đúng, cộng sai ở bước 2, kéo theo bước 3
DIST = dict(step=1, skill=A02, family="distribution_error", misconception="M_DIST_01")
SLIP = dict(step=2, family="arithmetic_error")


def session(scenario_id: str, first_problem: str) -> Session:
    return Session(scenario_id, first_problem, problems=PROBLEMS, parameters=PARAMETERS, content=CONTENT, kg=KG,
                   source_reference=SOURCE)


def labels(acceptable: list[str], forbidden: list[str], rationale: str, *, intents: list[str] = (),
           skills: list[str] = ()) -> StrategyLabels:
    return StrategyLabels(acceptable_actions=acceptable, forbidden_actions=forbidden, acceptable_intents=list(intents),
                          acceptable_target_skill_ids=list(skills), author=AUTHOR, rationale=rationale,
                          review_status="human_approved", reviewer=REVIEWER)


def e02_history(s: Session, results: str) -> Session:
    """Chuỗi bài E02 khác họ mẫu trước bài cần đánh giá: mỗi chữ là kết quả lần làm độc lập đầu tiên
    (T đúng, F sai). Sau lần sai, tutor gợi ý và học sinh sửa đúng (đúng có hỗ trợ, không tạo observation
    mới). Sau mỗi bài, tutor giao bài họ mẫu kế tiếp. Phiên phải bắt đầu ở E02-PL-P004."""
    chain = [("E02-PL-P004", ["3x = 15", "x = 5"], ["3x = 25", "x = 25/3"]),
             ("E02-PL-P005", ["-4x = -16", "x = 4"], ["-4x = -4", "x = 1"]),
             ("E02-P003", ["3x - 7 = 8", "3x = 15", "x = 5"], ["7x - 7 = 8", "7x = 15", "x = 15/7"]),
             ("E02-PL-P006", ["7 - 2x - 2 = 1", "5 - 2x = 1", "x = 2"], ["7 - 2x + 2 = 1", "9 - 2x = 1", "x = 4"])]
    following = ["E02-PL-P005", "E02-P003", "E02-PL-P006", "E02-P001"]
    for result, (_, right, wrong), upcoming in zip(results, chain, following):
        if result == "T":
            s.correct(right)
        else:
            s.submit(wrong, "verified_incorrect", step=1, family="arithmetic_error")
            s.tutor("minimal_hint", "locate_error", 1).correct(right)
        s.tutor("next_problem", "continue_practice", problem=upcoming)
    return s


def scenarios() -> list[ScenarioDraft]:
    out: list[ScenarioDraft] = []

    def add(s: Session, title: str, tags: list[str], label: StrategyLabels) -> None:
        out.append(s.scenario(title, tags, label))

    # ------------------------------------------------------------------ bài đúng
    after_first_correct = dict(
        intents=["continue_practice", "advance_difficulty"],
        rationale="Một lần làm đúng độc lập: luyện tiếp bài khác họ mẫu hoặc kiểm tra chuyển giao. Chưa đủ bằng "
                  "chứng để chuyển concept; gợi ý hay quay lại kiến thức nền là thừa.")
    add(session("DP-01", "E02-P001").correct(P001_RIGHT),
        "Làm đúng đầy đủ các bước ngay lần đầu", ["correct_independent"],
        labels(["next_problem", "check_transfer"], ["minimal_hint", "scaffold", "backtrack", "conceptual_question"],
               **after_first_correct))
    add(session("DP-02", "E02-P001").correct(["x - 3 = 5", "x = 8"]),
        "Làm đúng theo cách khác: chia hai vế cho 2 trước", ["correct_independent", "alternative_correct"],
        labels(["next_problem", "check_transfer"], ["minimal_hint", "scaffold", "backtrack", "conceptual_question"],
               **after_first_correct))
    add(session("DP-03", "E02-P001").correct(["x = 8"], final_only=True),
        "Chỉ ghi đáp án cuối và đáp án đúng", ["correct_independent", "final_answer_only"],
        labels(["next_problem", "check_transfer", "diagnose"], ["minimal_hint", "scaffold", "backtrack"],
               "Đáp án đúng nhưng không thấy cách làm: giao bài khác để kiểm tra, hoặc hỏi em đã làm thế nào. "
               "Không khẳng định cách giải đúng và chưa chuyển concept.",
               intents=["continue_practice", "advance_difficulty", "elicit_reasoning"]))

    # ------------------------------------------------------------------ bài sai, lần đầu
    add(session("DP-04", "E02-P001").submit(["x = 6.5"], "verified_incorrect", final_only=True),
        "Chỉ ghi đáp án cuối và đáp án sai", ["final_answer_only", "insufficient_evidence"],
        labels(["diagnose", "minimal_hint"], ["backtrack", "scaffold", "conceptual_question", "next_problem"],
               "Không có bước nào để định vị lỗi: hỏi cách làm hoặc nhắc tự kiểm tra. Chưa có bằng chứng về hiểu sai "
               "hay kiến thức nền để hỏi khái niệm hoặc quay lại.",
               intents=["elicit_reasoning", "prompt_self_check"]))
    add(session("DP-05", "E02-P002").submit(["3x + 1 = 12", "3x = 11", "x = 11/3"], "verified_incorrect", **DIST),
        "Lỗi phân phối lần đầu, nghi hiểu sai", ["misconception_suspected"],
        labels(["diagnose", "conceptual_question", "minimal_hint"], ["scaffold", "next_problem", "check_transfer"],
               "Một lần sai mới chỉ là nghi ngờ: hỏi để phân biệt, hỏi khái niệm phân phối hoặc gợi ý nhẹ. Chưa cần "
               "chia nhỏ bước, và không chuyển bài khi vừa làm sai."))
    add(session("DP-06", "E02-P001").submit(P001_DIST, "verified_incorrect", **DIST)
        .tutor("diagnose", "distinguish_hypothesis")
        .submit(["2x - 3 = 10", "2x = 13", "x = 13/2"], "verified_incorrect", **DIST),
        "Lặp lại đúng lỗi phân phối sau khi đã được hỏi chẩn đoán", ["misconception_repeated", "prerequisite_gap"],
        labels(["conceptual_question", "minimal_hint", "backtrack", "scaffold"],
               ["next_problem", "check_transfer", "end_session"],
               "Hai lần cùng một lỗi: giả thuyết hiểu sai đã có bằng chứng lặp lại. Nhắm thẳng vào tính phân phối "
               "(hỏi khái niệm, nhắc quy tắc, ôn kiến thức nền hoặc ví dụ tương tự). Hỏi chung chung lần nữa không "
               "thêm thông tin.",
               intents=["recall_rule", "locate_error", "analogous_example", "explain_concept"], skills=[A02]))
    add(session("DP-07", "E02-P001").submit(P001_SLIP, "verified_incorrect", **SLIP),
        "Phân phối đúng, tính sai ở bước 2 và kéo theo bước 3", ["careless_error", "error_propagation"],
        labels(["minimal_hint", "diagnose"], ["backtrack", "scaffold", "conceptual_question", "next_problem"],
               "Bước sai đầu tiên là bước 2; bước 3 chỉ sai theo. Chỉ vùng cần xem lại hoặc hỏi cách làm ở bước đó. "
               "Không có dấu hiệu hiểu sai khái niệm hay thiếu kiến thức nền.",
               intents=["locate_error", "prompt_self_check"]))
    add(session("DP-08", "E05-PL-P001").submit(["x + 1 = 3", "x = 2"], "verified_incorrect", step=2,
                                               family="condition_error"),
        "Bỏ qua điều kiện mẫu khác 0, nhận nghiệm làm mẫu bằng 0", ["condition_error"],
        labels(["minimal_hint", "diagnose", "conceptual_question"], ["next_problem", "check_transfer", "backtrack"],
               "Biến đổi đại số đúng nhưng kết luận sai vì không đối chiếu điều kiện. Gợi ý thử lại nghiệm, hỏi về "
               "điều kiện xác định. Kỹ năng giải phương trình bậc nhất không phải chỗ hỏng nên không quay lại.",
               skills=[E05]))

    # ------------------------------------------------------------------ input chưa đủ để chấm
    add(session("DP-09", "E02-P001").submit(["2x = 16 hoặc 2x = 4"], "needs_clarification"),
        "Bài làm ghi hai khả năng, không rõ em chọn dòng nào", ["ambiguous_input"],
        labels(["clarify"], ["minimal_hint", "scaffold", "backtrack", "conceptual_question", "next_problem"],
               "Chưa chấm được: hỏi lại em muốn nộp dòng nào. Gợi ý lúc này là đoán lỗi khi chưa có bài làm rõ ràng."))
    add(session("DP-10", "E02-P003").submit(["em thử x = 5 thấy hai vế bằng nhau"], "unverified"),
        "Trả lời bằng lời, không có bước giải để xác minh", ["insufficient_evidence"],
        labels(["clarify", "diagnose"], ["backtrack", "scaffold", "conceptual_question", "minimal_hint"],
               "Câu trả lời bằng lời chưa được xác minh: đề nghị em viết các bước, hoặc hỏi em tìm ra bằng cách nào. "
               "Không coi là đúng hay sai và không gợi ý sửa lỗi.",
               intents=["resolve_input", "elicit_reasoning"]))

    # ------------------------------------------------------------------ lời nhắn và yêu cầu của học sinh
    add(session("DP-11", "E02-P001").submit(P001_DIST, "verified_incorrect", **DIST)
        .tutor("diagnose", "elicit_reasoning").message("Thầy cho em đáp án luôn được không ạ?"),
        "Xin đáp án trực tiếp sau một lần sai", ["requests_answer", "misconception_suspected"],
        labels(["minimal_hint", "conceptual_question", "diagnose"], ["next_problem", "check_transfer", "end_session"],
               "Không đưa đáp án. Tăng hỗ trợ một nấc (gợi ý nhẹ hoặc hỏi khái niệm) hoặc hỏi lại chỗ em thấy khó. "
               "Kết thúc phiên hay đổi bài là bỏ mặc yêu cầu hỗ trợ."))
    add(session("DP-12", "E02-P003").hint(),
        "Xin gợi ý khi chưa nộp bước nào", ["hint_request", "insufficient_evidence"],
        labels(["diagnose", "minimal_hint", "clarify"], ["scaffold", "backtrack", "next_problem", "conceptual_question"],
               "Chưa có bài làm nên chưa biết em kẹt ở đâu: hỏi em đã thử gì, hoặc nhắc quy tắc ở mức nhẹ. Chia nhỏ "
               "bước hay ví dụ mẫu là hỗ trợ quá mức khi em chưa thử.",
               intents=["elicit_reasoning", "recall_rule", "restate_task"]))
    add(session("DP-13", "E03-P001").message("Em không hiểu đề bài hỏi gì ạ."),
        "Nhắn là không hiểu đề bài toán lời văn", ["misread_task"],
        labels(["clarify", "minimal_hint", "diagnose"], ["next_problem", "backtrack", "check_transfer"],
               "Em chưa hiểu đề: diễn đạt lại yêu cầu, hỏi em hiểu đến đâu, hoặc gợi ý cách đặt ẩn. Chưa có bài làm "
               "nào để kết luận thiếu kiến thức nền.",
               intents=["restate_task", "elicit_reasoning", "recall_rule"]))
    add(session("DP-14", "E02-P001").submit(P001_DIST, "verified_incorrect", **DIST)
        .tutor("minimal_hint", "recall_rule", 1).pause("Em mệt rồi, cho em nghỉ một lát ạ."),
        "Xin tạm dừng giữa lúc đang sai", ["pause_request"],
        labels(["end_session"], ["minimal_hint", "diagnose", "scaffold", "conceptual_question", "backtrack",
                                 "next_problem", "check_transfer"],
               "Học sinh xin dừng thì cho dừng; không tiếp tục hỏi hay gợi ý. Tạm dừng không bị tính là trả lời sai.",
               intents=["student_request"]))
    add(session("DP-15", "E02-P001").submit(P001_DIST, "verified_incorrect", **DIST)
        .tutor("minimal_hint", "recall_rule", 1).pause("Em nghỉ một chút ạ.")
        .tutor("end_session", "student_request").resume(),
        "Quay lại sau khi tạm dừng ở bài đang sai", ["resume"],
        labels(["minimal_hint", "diagnose", "clarify", "conceptual_question"], ["next_problem", "end_session", "backtrack"],
               "Em quay lại bài còn dang dở: nhắc lại yêu cầu, hỏi em nhớ đến đâu hoặc gợi ý tiếp ở mức đã dừng. "
               "Không đổi bài và không kết thúc phiên lần nữa."))

    # ------------------------------------------------------------------ sau khi đã hỗ trợ
    add(session("DP-16", "E02-P001").submit(P001_DIST, "verified_incorrect", **DIST)
        .tutor("minimal_hint", "recall_rule", 1).correct(P001_RIGHT),
        "Sửa đúng sau một gợi ý", ["correct_after_hint"],
        labels(["check_transfer", "next_problem"], ["minimal_hint", "scaffold", "backtrack", "end_session"],
               "Đúng nhờ hỗ trợ chưa phải bằng chứng độc lập: giao bài khác họ mẫu không kèm gợi ý, hoặc luyện tiếp. "
               "Chưa được tăng độ khó hay chuyển concept.",
               intents=["continue_practice"]))
    wrong_move = dict(step=1, family="sign_error", misconception="M_MOVE_SIGN")
    add(session("DP-17", "E02-P003").submit(["7x - 7 = 8", "7x = 15", "x = 15/7"], "verified_incorrect", **wrong_move)
        .tutor("diagnose", "elicit_reasoning")
        .submit(["7x = 15", "x = 15/7"], "verified_incorrect", **wrong_move)
        .tutor("minimal_hint", "locate_error", 1)
        .submit(["7x - 7 = 8", "7x = 1", "x = 1/7"], "verified_incorrect", **wrong_move)
        .tutor("minimal_hint", "recall_rule", 2).hint("Em vẫn chưa hiểu sai ở đâu ạ."),
        "Kẹt sau khi đã hỏi và gợi ý hai mức, vẫn lặp lỗi chuyển vế", ["stuck_after_hints", "misconception_repeated"],
        labels(["scaffold", "conceptual_question"], ["next_problem", "check_transfer", "diagnose"],
               "Ba lần sai cùng một lỗi sau hai mức gợi ý: cần hỗ trợ mạnh hơn (chia nhỏ thao tác chuyển vế, ví dụ "
               "tương tự) hoặc hỏi khái niệm ở mức cao hơn. Hỏi chẩn đoán lại là lặp, đổi bài là bỏ lỗi chưa sửa."))

    # ------------------------------------------------------------------ lỗi thao tác theo lịch sử (ngưỡng good)
    slip_title = "Lỗi tính toán ở bài mới sau lịch sử E02 độc lập: "
    add(e02_history(session("DP-18", "E02-PL-P004"), "TTTT").submit(P001_SLIP, "verified_incorrect", **SLIP),
        slip_title + "4/4 đúng", ["careless_error", "history_strong", "threshold_good"],
        labels(["minimal_hint"], ["backtrack", "scaffold", "conceptual_question", "next_problem"],
               "Bốn bài khác họ mẫu đều đúng độc lập, lần này phân phối đúng và chỉ cộng sai: nhắc em tự kiểm tra "
               "hoặc chỉ bước cần xem lại là đủ. Hỏi chẩn đoán hay hỗ trợ nặng hơn là thừa với lịch sử này.",
               intents=["prompt_self_check", "locate_error"]))
    add(e02_history(session("DP-19", "E02-PL-P004"), "TFTT").submit(P001_SLIP, "verified_incorrect", **SLIP),
        slip_title + "3/4 đúng", ["careless_error", "threshold_good"],
        labels(["minimal_hint", "diagnose"], ["backtrack", "scaffold", "next_problem"],
               "Lịch sử khá nhưng đã có một lần sai: nhắc tự kiểm tra, chỉ bước cần xem lại, hoặc hỏi cách làm đều hợp "
               "lý. Ca nằm giữa: không ràng buộc intent."))
    add(e02_history(session("DP-20", "E02-PL-P004"), "FTFT").submit(P001_SLIP, "verified_incorrect", **SLIP),
        slip_title + "2/4 đúng", ["careless_error", "threshold_good"],
        labels(["minimal_hint", "diagnose"], ["backtrack", "next_problem"],
               "Lịch sử nửa đúng nửa sai: chưa thể coi đây là sơ suất đơn lẻ. Chỉ bước sai hoặc hỏi cách làm; chỉ "
               "bảo 'kiểm tra lại' thì chưa đủ cho em này.",
               intents=["locate_error", "recall_rule", "elicit_reasoning"]))
    add(e02_history(session("DP-21", "E02-PL-P004"), "FFFT").submit(P001_SLIP, "verified_incorrect", **SLIP),
        slip_title + "1/4 đúng", ["careless_error", "history_weak", "threshold_good"],
        labels(["diagnose", "minimal_hint"], ["next_problem", "check_transfer"],
               "Ba trong bốn bài trước sai ở lần đầu: lỗi tính lần này nhiều khả năng không phải sơ suất. Hỏi cách "
               "làm hoặc chỉ rõ bước sai kèm quy tắc; không dừng ở mức nhắc tự kiểm tra.",
               intents=["locate_error", "recall_rule", "elicit_reasoning"]))

    # ------------------------------------------------------------------ đủ điều kiện chuyển tiếp (ngưỡng ready)
    ready_title = "Làm đúng bài E02 thứ tư; kết quả độc lập gồm cả bài này: "
    last = ["7 - 2x - 2 = 1", "5 - 2x = 1", "x = 2"]
    add(e02_history(session("DP-22", "E02-PL-P004"), "TTT").correct(last),
        ready_title + "4/4 đúng", ["correct_independent", "history_strong", "threshold_ready"],
        labels(["next_problem"], ["minimal_hint", "scaffold", "backtrack", "diagnose", "conceptual_question"],
               "Bốn bài khác họ mẫu, hai mức độ khó, đều đúng độc lập và không còn giả thuyết lỗi: chuyển sang concept "
               "kế tiếp hoặc tăng độ khó. Luyện thêm cùng mức là giữ chân em không cần thiết.",
               intents=["advance_concept", "advance_difficulty"]))
    add(e02_history(session("DP-23", "E02-PL-P004"), "FTT").correct(last),
        ready_title + "3/4 đúng, ba lần gần nhất đúng", ["correct_independent", "threshold_ready"],
        labels(["next_problem", "check_transfer"], ["minimal_hint", "scaffold", "backtrack", "conceptual_question"],
               "Sai bài đầu rồi đúng ba bài liên tiếp: chuyển tiếp hay luyện thêm một bài đều chấp nhận được. Ca nằm "
               "giữa: không ràng buộc intent."))
    add(e02_history(session("DP-24", "E02-PL-P004"), "FFT").correct(last),
        ready_title + "2/4 đúng, hai lần gần nhất đúng", ["correct_independent", "threshold_ready"],
        labels(["next_problem", "check_transfer"], ["minimal_hint", "scaffold", "backtrack", "conceptual_question"],
               "Hai bài đầu sai, hai bài sau mới đúng: tiến bộ nhưng bằng chứng còn mỏng. Luyện tiếp hoặc kiểm tra "
               "chuyển giao; chưa chuyển concept.",
               intents=["continue_practice", "advance_difficulty"]))
    add(e02_history(session("DP-25", "E02-PL-P004"), "TFF").correct(last),
        ready_title + "2/4 đúng, lần gần nhất trước đó sai", ["correct_independent", "threshold_ready"],
        labels(["next_problem", "check_transfer"], ["minimal_hint", "scaffold", "backtrack", "conceptual_question"],
               "Vừa sai hai bài liên tiếp rồi mới đúng lại một bài: chưa ổn định. Luyện tiếp cùng mức hoặc kiểm tra "
               "chuyển giao; chưa tăng độ khó và chưa chuyển concept.",
               intents=["continue_practice"]))

    # ------------------------------------------------------------------ kiến thức nền (ngưỡng low)
    def in_prerequisite_branch(scenario_id: str) -> Session:
        return (session(scenario_id, "E02-P001").submit(P001_DIST, "verified_incorrect", **DIST)
                .tutor("diagnose", "distinguish_hypothesis")
                .submit(["2x - 3 = 10", "2x = 13", "x = 13/2"], "verified_incorrect", **DIST)
                .tutor("backtrack", "review_prerequisite", problem="A02-P002"))

    add(in_prerequisite_branch("DP-26").submit(["4a - 5"], "verified_incorrect", **DIST)
        .tutor("minimal_hint", "recall_rule", 1).correct(["4a - 20"])
        .tutor("next_problem", "continue_practice", problem="A02-PL-P003")
        .submit(["6x - 5"], "verified_incorrect", **DIST),
        "Trong nhánh ôn tính phân phối: sai lần đầu ở cả hai bài nền", ["prerequisite_gap", "misconception_repeated",
                                                                       "history_weak", "threshold_low"],
        labels(["scaffold", "conceptual_question", "minimal_hint"], ["next_problem", "check_transfer", "end_session"],
               "Em lặp lỗi phân phối ngay ở bài nền dù vừa được nhắc quy tắc: cần giải thích hoặc ví dụ về tính phân "
               "phối, hay câu hỏi khái niệm. Chưa quay lại bài gốc và chưa đổi bài khi lỗi nền chưa sửa.",
               skills=[A02]))
    add(in_prerequisite_branch("DP-27").correct(["4a - 20"]),
        "Trong nhánh ôn tính phân phối: làm đúng bài nền ngay lần đầu", ["prerequisite_gap", "correct_independent"],
        labels(["next_problem", "check_transfer"], ["minimal_hint", "scaffold", "backtrack", "conceptual_question"],
               "Bài nền đúng độc lập: quay lại bài gốc đang dang dở, hoặc kiểm tra thêm một bài phân phối khác họ mẫu. "
               "Không ôn sâu hơn khi chưa có bằng chứng thiếu kiến thức nền tầng dưới.",
               intents=["return_to_parent"]))
    strong_a02 = (session("DP-28", "A02-P001").correct(["-6y - 8"])
                  .tutor("next_problem", "continue_practice", problem="A02-P002").correct(["4a - 20"])
                  .tutor("next_problem", "continue_practice", problem="A02-PL-P003").correct(["6x - 15"])
                  .tutor("next_problem", "advance_concept", problem="E02-P001")
                  .submit(P001_DIST, "verified_incorrect", **DIST))
    add(strong_a02, "Vừa làm đúng độc lập ba bài phân phối, sang phương trình thì phân phối sai",
        ["careless_error", "history_strong", "threshold_low"],
        labels(["minimal_hint", "diagnose", "conceptual_question"], ["backtrack", "scaffold", "next_problem"],
               "Kiến thức nền vừa được chứng minh bằng ba bài độc lập: lỗi này nhiều khả năng do bối cảnh mới. Chỉ bước "
               "cần xem lại hoặc hỏi em đã nhân thế nào. Quay lại ôn tính phân phối là không cần thiết."))

    back_title = "Quay lại bài gốc sau nhánh ôn tính phân phối rồi lặp lỗi phân phối; kết quả độc lập ở bài nền: "
    add(in_prerequisite_branch("DP-31").submit(["4a - 5"], "verified_incorrect", **DIST)
        .tutor("minimal_hint", "recall_rule", 1).correct(["4a - 20"])
        .tutor("next_problem", "continue_practice", problem="A02-PL-P003")
        .submit(["6x - 5"], "verified_incorrect", **DIST)
        .tutor("scaffold", "explain_concept", 4).correct(["6x - 15"])
        .tutor("next_problem", "return_to_parent")
        .submit(P001_DIST, "verified_incorrect", **DIST),
        back_title + "0/2 đúng", ["prerequisite_gap", "misconception_repeated", "history_weak", "threshold_low"],
        labels(["scaffold", "conceptual_question", "backtrack"], ["next_problem", "check_transfer", "diagnose"],
               "Cả hai bài nền đều sai ở lần đầu, chỉ đúng khi có hỗ trợ, và về bài gốc em lặp đúng lỗi cũ: kiến thức "
               "nền chưa vững. Hỗ trợ phải nhắm vào tính phân phối (giải thích, ví dụ, câu hỏi khái niệm, hoặc ôn lại). "
               "Hỏi chẩn đoán lần nữa không thêm thông tin; đổi bài là bỏ lỗi chưa sửa.",
               skills=[A02]))
    add(in_prerequisite_branch("DP-32").submit(["4a - 5"], "verified_incorrect", **DIST)
        .tutor("minimal_hint", "recall_rule", 1).correct(["4a - 20"])
        .tutor("next_problem", "continue_practice", problem="A02-PL-P003").correct(["6x - 15"])
        .tutor("next_problem", "return_to_parent")
        .submit(P001_DIST, "verified_incorrect", **DIST),
        back_title + "1/2 đúng", ["prerequisite_gap", "misconception_repeated", "threshold_low"],
        labels(["conceptual_question", "minimal_hint", "diagnose", "scaffold"], ["next_problem", "check_transfer"],
               "Bài nền thứ hai đã đúng độc lập nhưng về bài gốc em vẫn phân phối sai: có thể em chưa chuyển được quy "
               "tắc sang phương trình. Hỏi khái niệm, chỉ bước sai, hỏi em đã nhân thế nào hoặc ví dụ tương tự đều hợp "
               "lý. Ca nằm giữa: không ràng buộc intent hay skill."))

    add(in_prerequisite_branch("DP-33").submit(["4a - 5"], "verified_incorrect", **DIST)
        .tutor("minimal_hint", "recall_rule", 1).correct(["4a - 20"])
        .tutor("next_problem", "continue_practice", problem="A02-PL-P003")
        .submit(["6x - 5"], "verified_incorrect", **DIST)
        .tutor("scaffold", "explain_concept", 4).correct(["6x - 15"])
        .tutor("next_problem", "return_to_parent")
        .submit(P001_SLIP, "verified_incorrect", **SLIP),
        "Quay lại bài gốc sau nhánh ôn: lần này phân phối đúng, chỉ tính sai ở bước 2",
        ["careless_error", "prerequisite_gap", "history_weak", "threshold_low"],
        labels(["minimal_hint", "diagnose"], ["backtrack", "next_problem", "check_transfer"],
               "Ước lượng kiến thức nền còn thấp (hai bài nền sai ở lần đầu), nhưng chính bài làm này cho thấy em vừa "
               "phân phối đúng. Lỗi mới là lỗi tính ở bước 2: chỉ bước đó hoặc hỏi em tính thế nào. Kiểm tra hay ôn lại "
               "tính phân phối lúc này là bỏ qua bằng chứng mới nhất.",
               intents=["locate_error", "prompt_self_check", "elicit_reasoning"], skills=[E02]))

    # ------------------------------------------------------------------ concept khác
    add(session("DP-29", "N01-P001").correct(["-4"], final_only=True)
        .tutor("next_problem", "continue_practice", problem="N01-EX-P002")
        .submit(["3"], "verified_incorrect", family="sign_error", final_only=True),
        "Cộng số có dấu: đúng một bài, bài kế tiếp sai dấu kết quả", ["final_answer_only"],
        labels(["minimal_hint", "diagnose"], ["backtrack", "scaffold", "next_problem"],
               "Bài tính một bước nên chỉ có đáp án là bình thường. Sai dấu sau một bài đúng: nhắc quy tắc dấu hoặc hỏi "
               "em xác định dấu thế nào. N01 không có kiến thức nền để quay lại."))
    add(session("DP-30", "A03-PL-P001").submit(["4x + 7"], "verified_incorrect", step=1, family="sign_error"),
        "Thu gọn hạng tử: cộng thay vì trừ hệ số", ["careless_error"],
        labels(["minimal_hint", "diagnose"], ["scaffold", "next_problem", "check_transfer"],
               "Một lần sai dấu khi gom hạng tử, chưa có lịch sử: chỉ hạng tử cần xem lại, nhắc mang theo dấu, hoặc "
               "hỏi cách gom. Chưa đủ căn cứ cho hỗ trợ nặng hay quay lại kiến thức nền."))
    return out


def dataset() -> ScenarioDataset:
    return ScenarioDataset(dataset_version=DATASET_VERSION, parameters=PARAMETERS, problems=PROBLEMS,
                           scenarios=scenarios())


def rendered() -> bytes:
    return (dataset().model_dump_json(indent=2) + "\n").encode("utf-8")


def describe() -> None:
    from research.scenarios.replay import replay
    data = dataset()
    for draft in data.scenarios:
        s, _ = replay(draft, data, KG)
        a = s.latest_assessment
        skills = "; ".join(f"{k.skill_id.split('-', 1)[1]} p={k.p_mastery:.2f} n={k.independent_observations} "
                           f"{''.join('T' if r else 'F' for r in k.recent_independent)}"
                           for k in s.skills if k.independent_observations or k.assisted_correct)
        print(f"{draft.scenario_id} {draft.title}\n   {s.current.problem_id} ({s.current.relation}) trigger={s.trigger} "
              f"assessment={a.assessment_status if a else None} hint={s.support.hint_level} "
              f"support_turns={s.support.support_turns_on_node} no_progress={s.support.no_progress_turns}\n"
              f"   skills: {skills or '-'} | ready={s.readiness.ready_to_advance} unmet={s.readiness.unmet} "
              f"| hypotheses={[(h.misconception_id, h.status) for h in s.hypotheses]} stack={len(s.return_stack)}")


STATUS_TEXT = {"verified_correct": "đúng", "verified_incorrect": "sai", "unverified": "chưa xác minh được",
               "needs_clarification": "cần làm rõ"}
STUDENT_TEXT = {"request_hint": "xin gợi ý", "message": "nhắn", "pause": "xin tạm dừng", "resume": "quay lại"}


def review_sheet(blind: bool = False) -> str:
    """Phiếu rà soát bằng Markdown: mỗi ca có đề, lịch sử, state trước quyết định và nhãn.
    ``blind`` bỏ nhãn và lý do, để người thứ hai gán nhãn độc lập (plan §12)."""
    from research.scenarios.replay import replay
    data = dataset()
    prompts = {p.problem.problem_id: p.prompt for p in data.problems}
    lines = [f"# Phiếu {'gán nhãn độc lập' if blind else 'rà soát nhãn'}: {data.dataset_version}", "",
             "Mỗi ca kết thúc ở lượt của học sinh; cần chọn gia sư nên làm gì tiếp theo.",
             "Action: clarify, diagnose, minimal_hint, conceptual_question, scaffold, backtrack, check_transfer, "
             "next_problem, end_session.", ""]
    for draft in data.scenarios:
        state, _ = replay(draft, data, KG)
        lines += [f"## {draft.scenario_id}. {draft.title}", "",
                  f"- Loại: {', '.join(draft.tags)}", f"- Bài đang làm: {prompts[state.current.problem_id]}", "- Lịch sử:"]
        for event in draft.history:
            if event.actor == "tutor":
                given = f"; giao bài: {prompts[event.problem_id]}" if event.problem_id else ""
                lines.append(f"  - Gia sư: {event.action.value} / {event.intent.value}, mức hint {event.hint_level}{given}")
                continue
            if event.kind != "submit":
                lines.append(f"  - Học sinh {STUDENT_TEXT[event.kind]}" + (f": “{event.message}”" if event.message else ""))
                continue
            a = event.assessment
            grade = STATUS_TEXT[a.assessment_status]
            for name, value in (("bước sai đầu tiên", a.first_error_step), ("họ lỗi", a.error_family),
                                ("skill của lỗi", a.primary_skill_id if a.error_family else None),
                                ("nghi hiểu sai", a.misconception_candidate)):
                if value is not None:
                    grade += f"; {name}: {value}"
            lines.append(f"  - Học sinh nộp ({prompts[event.task.problem_id]}): {' → '.join(event.submission)}  "
                         f"[chấm: {grade}{'; chỉ có đáp án cuối' if a.final_answer_only else ''}]")
        seen = [f"{k.skill_id}: {''.join('Đ' if r else 'S' for r in k.recent_independent)} "
                f"(BKT {k.p_mastery:.2f}, đúng có hỗ trợ {k.assisted_correct})"
                for k in state.skills if k.independent_observations or k.assisted_correct]
        lines += [f"- Kết quả độc lập gần nhất (cũ → mới): {'; '.join(seen) or 'chưa có'}",
                  f"- Hỗ trợ trên bài này: mức hint {state.support.hint_level}, {state.support.support_turns_on_node} lượt "
                  f"hỗ trợ, {state.support.no_progress_turns} lượt chưa tiến bộ"
                  + ("; đang trong nhánh ôn kiến thức nền" if state.return_stack else "")]
        if blind:
            lines += ["- Action chấp nhận được: ", "- Action bị cấm: ", "- Intent hoặc skill cần hướng tới (nếu cần): ",
                      "- Lý do: ", ""]
            continue
        label = draft.labels
        lines += [f"- **Nhãn ({label.review_status}), chấp nhận được:** "
                  f"{', '.join(a.value for a in label.acceptable_actions)}",
                  f"- **Nhãn, bị cấm:** {', '.join(a.value for a in label.forbidden_actions) or 'không có'}"]
        if label.acceptable_intents:
            lines.append(f"- **Intent được chấp nhận:** {', '.join(i.value for i in label.acceptable_intents)} "
                         "(action không có intent nào ở đây thì nhận mọi intent)")
        if label.acceptable_target_skill_ids:
            lines.append(f"- **Skill cần hướng tới:** {', '.join(label.acceptable_target_skill_ids)}")
        lines += [f"- **Lý do:** {label.rationale}", "- Người duyệt: ☐ đồng ý  ☐ sửa nhãn:  ☐ sửa toán/tag: ", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="chỉ kiểm tra file JSON khớp nguồn")
    parser.add_argument("--describe", action="store_true", help="in state đã replay của từng ca")
    parser.add_argument("--sheet", type=Path, help="ghi phiếu rà soát Markdown ra file này")
    parser.add_argument("--blind", action="store_true", help="phiếu không có nhãn, để gán nhãn độc lập")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    if args.describe:
        describe()
        return 0
    if args.sheet:
        args.sheet.parent.mkdir(parents=True, exist_ok=True)
        args.sheet.write_bytes((review_sheet(args.blind) + "\n").encode("utf-8"))
        print(f"Wrote {args.sheet}")
        return 0
    content = rendered()
    if args.check:
        if not OUT.exists() or OUT.read_bytes() != content:
            print(f"FAIL: {OUT.relative_to(ROOT)} differs from research/scenarios/pilot_dev.py; run it without --check")
            return 1
        print(f"PASS: {OUT.relative_to(ROOT)} matches its source ({len(dataset().scenarios)} scenarios)")
        return 0
    OUT.write_bytes(content)
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(dataset().scenarios)} scenarios)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
