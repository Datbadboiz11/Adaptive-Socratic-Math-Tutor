"""Bộ tình huống test trên 78 bài đã duyệt của Member 2: nguồn của ``contracts/scenarios/approved.test.v1.json``.

Dựng như bộ dev (``approved_dev.py``): bài, đề và KB là bản đã duyệt, mọi lần nộp do validator của hệ
thống chấm, context lấy bằng ``ApprovedTools``. Khác ở hai chỗ:

- Chỉ dùng bài thuộc các họ dành cho test (``approved_dev.TEST_FAMILIES``); bộ dev chỉ dùng các họ còn lại.
  Công cụ của mỗi phía chỉ thấy bài và ví dụ mẫu của họ mình (``approved_dev.side_content``), nên bài ứng
  viên để giao tiếp và nội dung KB trong context cũng không sang phía kia. ``leaks()`` kiểm cả lịch sử,
  bài ứng viên lẫn nội dung KB của hai phía, và gộp hai bộ qua ``build.grouped_splits`` để chắc không ca
  test nào nối với ca dev qua bài gốc, họ mẫu hay lịch sử.
- Không có nhãn. Theo plan §12, nhãn test do hai người gán độc lập rồi hòa giải; người dựng tình huống
  không viết nhãn. ``build`` chỉ nhận ca test có nhãn đã hòa giải từ ít nhất hai người
  (``review_status = adjudicated``), nên chưa ai chạy hay chấm được bộ này.

Giới hạn cần ghi khi báo cáo: tình huống test do cùng quy trình AI dưới Member 3 dựng như bộ dev, chỉ khác
bài; 13 pack chỉ chấm đáp án cuối, nên validator không chỉ ra bước sai đầu tiên kể cả ở ca lỗi kéo theo.

    python -m research.scenarios.approved_test            # ghi lại file JSON
    python -m research.scenarios.approved_test --check    # file JSON khớp nguồn và không lộ bài sang dev
    python -m research.scenarios.approved_test --sheet out.md   # phiếu gán nhãn độc lập (không có nhãn)
"""
from __future__ import annotations

import argparse
from functools import lru_cache
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from research.scenarios import approved_dev as dev  # noqa: E402
from research.scenarios.approved_dev import P  # noqa: E402
from research.scenarios.build import grouped_splits  # noqa: E402
from research.scenarios.contracts import ScenarioDataset, ScenarioDraft  # noqa: E402

OUT = ROOT / "contracts" / "scenarios" / "approved.test.v1.json"
DATASET_VERSION = "adaptive-approved-test-0.2.0"
SOURCE = ("AI-built test situations under Member 3 on the 78 human-approved Member 2 problems (member2-v2), "
          "using only the problem families reserved for test. Every submission graded by the system validator. "
          "No strategy labels: two independent raters label these before adjudication.")


def session(scenario_id: str, first_problem: str):
    s = dev.session(scenario_id, first_problem)
    s.source_reference = SOURCE
    return s


def scenarios() -> list[ScenarioDraft]:
    out: list[ScenarioDraft] = []

    def add(s, title: str, tags: list[str]) -> None:
        out.append(s.scenario(title, tags, None, split="test"))

    # ------------------------------------------------------------------ đúng ngay lần đầu
    for sid, concept, number, answer in [("AT-01", "A01", 3, "20"), ("AT-13", "E03", 5, "x; lọ; positive_integer; 58-4*x=26"),
                                         ("AT-16", "E06", 3, "0;{-5/3}"), ("AT-19", "E09", 3, "1,-1;(2,4)"),
                                         ("AT-22", "F02", 5, "(-inf,31/4]"), ("AT-25", "F05", 5, "x=-5/2"),
                                         ("AT-28", "F08", 3, "5^-2=1/25;R"), ("AT-31", "N02", 3, "-13"),
                                         ("AT-34", "N05", 3, "-48/176 > -55/176"), ("AT-37", "N08", 3, "18.4%")]:
        add(session(sid, P(concept, number)).work([answer], "verified_correct"),
            f"{concept}: đáp án cuối đúng ngay lần đầu", ["correct_independent", "final_answer_only"])
    add(session("AT-06", P("A04", 3)).work(["18*x-12*x*x-42"], "verified_correct"),
        "A04: khai triển đúng, viết các hạng tử theo thứ tự khác", ["correct_independent", "alternative_correct"])
    add(session("AT-35", P("N05", 5)).work(["3/7 = 3/7"], "verified_correct"),
        "N05: rút gọn cả hai phân số trước rồi so sánh", ["correct_independent", "alternative_correct"])

    # ------------------------------------------------------------------ sai lần đầu
    for sid, concept, number, answer, title, tags in [
            ("AT-04", "A04", 3, "-12*x*x-18*x-42", "sai dấu một hạng tử khi nhân -6 vào ngoặc", ["sign_error"]),
            ("AT-14", "E03", 6, "x; thẻ; positive_integer; 73+5*x=38", "cộng số thẻ đã phát thay vì trừ", ["sign_error"]),
            ("AT-17", "E06", 4, "0;{-7/4}", "đúng biệt thức, sai dấu nghiệm kép", ["sign_error"]),
            ("AT-26", "F05", 6, "x=-3/2", "sai dấu hoành độ trục đối xứng", ["sign_error"]),
            ("AT-29", "F08", 4, "3^-4=1/81;R", "trừ sai số mũ âm khi chia hai lũy thừa", ["sign_error"]),
            ("AT-30", "F08", 6, "R", "coi y = 1^x là hàm số mũ", ["concept_confusion"]),
            ("AT-36", "N05", 4, "-28/72 < -33/72", "quy đồng đúng, so sánh sai hai phân số âm", ["comparison_error"]),
            ("AT-38", "N08", 4, "10.87%", "dời dấu phẩy một chữ số khi đổi sang phần trăm", ["place_value_error"])]:
        add(session(sid, P(concept, number)).work([answer], "verified_incorrect"),
            f"{concept}: {title}", ["final_answer_only", "insufficient_evidence", *tags])
    for sid, concept, number, answer, title in [
            ("AT-10", "A10", 5, "x+3|x-7;{7,-3}", "phân thức đúng nhưng thiếu giá trị loại -1 của phân thức chia"),
            ("AT-23", "F02", 6, "[-9/5,+inf)", "không đổi chiều bất phương trình khi chia cho số âm")]:
        add(session(sid, P(concept, number)).work([answer], "verified_incorrect"),
            f"{concept}: {title}", ["condition_error", "final_answer_only"])

    # ------------------------------------------------------------------ lỗi kéo theo (validator chỉ chấm đáp án cuối)
    for sid, concept, number, lines, title in [
            ("AT-02", "A01", 4, ["-2*8+28+5", "-16+33", "17"], "tính 4·4 thành 8 rồi kéo theo đến đáp án"),
            ("AT-20", "E09", 4, ["1,-1;(2,2)"], "sai dấu của y rồi thay vào tìm x cũng sai"),
            ("AT-32", "N02", 5, ["54/(-3)", "-18"], "mất dấu âm ở tích trong ngoặc rồi kéo theo đến thương")]:
        add(session(sid, P(concept, number)).work(lines, "verified_incorrect"),
            f"{concept}: {title}", ["error_propagation", "sign_error", "final_answer_only"])

    # ------------------------------------------------------------------ đúng giá trị nhưng chưa xong, chưa chấm được
    for sid, concept, number, answer, title, tags in [
            ("AT-07", "A07", 5, "6*x*(4*x-6)", "đặt nhân tử chung nhưng chưa phải lớn nhất", ["ambiguous_input", "unfinished_answer"]),
            ("AT-09", "A07", 6, "-9*x*(3*x-5)", "đặt nhân tử chung âm trong khi đề yêu cầu hệ số dương", ["condition_error", "ambiguous_input"]),
            ("AT-21", "E09", 5, "x=1, y=2", "chỉ ghi nghiệm, thiếu hai hệ số nhân", ["ambiguous_input", "misread_task"]),
            ("AT-39", "N08", 3, "18.4", "thiếu ký hiệu phần trăm", ["ambiguous_input", "unfinished_answer"])]:
        add(session(sid, P(concept, number)).work([answer], "needs_clarification"), f"{concept}: {title}", tags)
    add(session("AT-27", P("F05", 5)).work(["x=15/(-6)"], "unfinished"),
        "F05: đúng giá trị nhưng chưa rút gọn phân số", ["unfinished_answer"])

    # ------------------------------------------------------------------ lời nhắn, xin gợi ý, xin đáp án
    add(session("AT-05", P("A04", 4)).message("Thầy cho em đáp án luôn được không ạ?"),
        "A04: xin đáp án ngay khi chưa làm gì", ["requests_answer", "insufficient_evidence"])
    add(session("AT-11", P("A10", 6)).hint(), "A10: xin gợi ý khi chưa nộp gì", ["hint_request", "insufficient_evidence"])
    add(session("AT-15", P("E03", 5)).message("Em không biết phải đặt x là gì ạ."),
        "E03: không biết chọn ẩn cho bài toán lời văn", ["misread_task"])
    add(session("AT-18", P("E06", 3)).work(["0;{5/3}"], "verified_incorrect")
        .tutor("diagnose", "elicit_reasoning").message("Thầy nói đáp án luôn đi ạ, em làm mãi không ra."),
        "E06: xin đáp án trực tiếp sau một lần sai dấu nghiệm kép", ["requests_answer"])

    # ------------------------------------------------------------------ sau khi đã hỗ trợ, chuyển giao, tạm dừng
    add(session("AT-03", P("A01", 3)).work(["20"], "verified_correct")
        .tutor("check_transfer", "independent_check", problem=P("A01", 5)).work(["14/3"], "verified_incorrect"),
        "A01: đúng bài số nguyên, sang bài thay phân số khác họ mẫu thì sai", ["transfer_failure", "final_answer_only"])
    add(session("AT-08", P("A07", 3)).work(["x*(7*x+11)"], "verified_correct")
        .tutor("check_transfer", "independent_check", problem=P("A07", 5)).work(["12*x*(2*x-3)"], "verified_correct"),
        "A07: làm đúng cả bài kiểm tra khác họ mẫu", ["correct_independent", "transfer_success"])
    add(session("AT-12", P("A10", 6)).work(["x+2|x-9;{-2,9,6}"], "verified_incorrect")
        .tutor("minimal_hint", "prompt_self_check", 1).work(["x+2|x-9;{-2,9,6}"], "verified_incorrect")
        .tutor("minimal_hint", "locate_error", 2).work(["x+2|x-9;{-2,9,6}"], "verified_incorrect"),
        "A10: nghịch đảo nhầm phân thức, nộp lại y nguyên sau hai mức gợi ý", ["stuck_after_hints", "repeated_error"])
    add(session("AT-24", P("F02", 5)).work(["[31/4,+inf)"], "verified_incorrect")
        .tutor("minimal_hint", "prompt_self_check", 1).pause("Em phải đi học thêm, em dừng ở đây ạ."),
        "F02: xin tạm dừng giữa lúc đang sai", ["pause_request"])
    add(session("AT-33", P("N02", 4)).work(["17"], "verified_incorrect")
        .tutor("minimal_hint", "recall_rule", 1).work(["-17"], "verified_correct"),
        "N02: sửa đúng dấu của thương sau một gợi ý nhắc quy tắc", ["correct_after_hint"])
    return sorted(out, key=lambda s: s.scenario_id)


@lru_cache(maxsize=1)
def dataset() -> ScenarioDataset:
    return ScenarioDataset(dataset_version=DATASET_VERSION, parameters=dev.PARAMETERS, problems=dev.PROBLEMS,
                           scenarios=scenarios())


def leaks(dev_data: ScenarioDataset, test_data: ScenarioDataset) -> list[str]:
    """Các chỗ một ca dùng bài của họ thuộc phía bên kia; rỗng là không lộ. Gộp hai bộ qua
    ``grouped_splits`` thì ca test nối với ca dev sẽ báo xung đột split."""
    found = [f"{s.scenario_id} ({split}) uses {e.task.problem_id}"
             for split, data in (("dev", dev_data), ("test", test_data)) for s in data.scenarios
             for e in s.history if dev.family_split(e.task.problem_id) != split]
    found += [f"{s.scenario_id} assigns {e.problem_id}"
              for split, data in (("dev", dev_data), ("test", test_data)) for s in data.scenarios
              for e in s.history if e.problem_id and dev.family_split(e.problem_id) != split]
    found += [f"{s.scenario_id} offers {p.problem_id}"
              for split, data in (("dev", dev_data), ("test", test_data)) for s in data.scenarios
              for p in s.context.problems if dev.family_split(p.problem_id) != split]
    found += [f"{s.scenario_id} shows {c.content_id}"
              for split, data in (("dev", dev_data), ("test", test_data)) for s in data.scenarios
              for c in s.context.retrieved if dev.content_split(c.content_id) not in {None, split}]
    merged = ScenarioDataset(dataset_version="leak-check", parameters=dev_data.parameters, problems=dev_data.problems,
                             scenarios=[*dev_data.scenarios, *test_data.scenarios])
    try:
        grouped_splits(merged, "leak-check")
    except ValueError as error:
        found.append(str(error))
    return found


def rendered() -> bytes:
    return (dataset().model_dump_json(indent=2) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    from research.scenarios.pilot_dev import review_sheet

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="chỉ kiểm tra file JSON khớp nguồn và không lộ bài")
    parser.add_argument("--sheet", type=Path, help="ghi phiếu gán nhãn độc lập (Markdown) ra file này")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    if found := leaks(dev.dataset(), dataset()):
        print("FAIL: dev and test share problem families:\n  " + "\n  ".join(found))
        return 1
    if args.sheet:
        args.sheet.parent.mkdir(parents=True, exist_ok=True)
        args.sheet.write_bytes((review_sheet(True, dataset(), dev.KG) + "\n").encode("utf-8"))
        print(f"Wrote {args.sheet}")
        return 0
    content = rendered()
    if args.check:
        if not OUT.exists() or OUT.read_bytes() != content:
            print(f"FAIL: {OUT.relative_to(ROOT)} differs from research/scenarios/approved_test.py; "
                  "run it without --check")
            return 1
        print(f"PASS: {OUT.relative_to(ROOT)} matches its source ({len(dataset().scenarios)} scenarios, "
              "no family shared with dev)")
        return 0
    OUT.write_bytes(content)
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(dataset().scenarios)} scenarios)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
