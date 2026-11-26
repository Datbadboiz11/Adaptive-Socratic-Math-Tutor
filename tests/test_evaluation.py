"""Rubric Socratic và quy trình chấm ẩn cấu hình: kappa, bootstrap, tạo bộ bài, đọc phiếu, tổng hợp."""
import csv
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from research.evaluation.agreement import bootstrap_mean_ci, cohen_kappa, weighted_kappa  # noqa: E402
from research.evaluation.build_rating_packet import (  # noqa: E402
    build_packet, main as build_main, pair_item, parse_compare, pilot_outputs, write_packet,
)
from research.evaluation.rubric import (  # noqa: E402
    Dimension, PacketKey, Rating, SevereFlag, SystemOutput,
)
from research.evaluation.score_ratings import (  # noqa: E402
    RatingFileError, canonical_choice, main as score_main, parse_ratings, score, shown_choice,
)

ALL_TWO = {d: 2 for d in Dimension}


# --------------------------------------------------------------------------- thống kê

def test_cohen_kappa_matches_the_textbook_example():
    # 50 câu: cả hai "có" 20, A có/B không 5, A không/B có 10, cả hai "không" 15 → po = 0.7, pe = 0.5.
    a = ["yes"] * 25 + ["no"] * 25
    b = ["yes"] * 20 + ["no"] * 5 + ["yes"] * 10 + ["no"] * 15
    assert cohen_kappa(a, b) == pytest.approx(0.4)


def test_weighted_kappa_by_hand():
    a, b = [0, 1, 2, 2], [0, 2, 2, 1]
    assert weighted_kappa(a, b, (0, 1, 2), "quadratic") == pytest.approx(7 / 11)
    assert weighted_kappa(a, b, (0, 1, 2), "linear") == pytest.approx(3 / 7)
    assert weighted_kappa([0, 1, 2], [0, 1, 2], (0, 1, 2)) == pytest.approx(1)


def test_kappa_is_undefined_without_variation_and_rejects_bad_input():
    assert cohen_kappa([True] * 4, [True] * 4, (False, True)) is None
    assert weighted_kappa([2, 2], [2, 2], (0, 1, 2)) is None
    assert cohen_kappa([], []) is None
    with pytest.raises(ValueError):
        cohen_kappa([1, 2], [1])
    with pytest.raises(ValueError):
        weighted_kappa([3], [0], (0, 1, 2))


def test_bootstrap_resamples_scenarios_not_items():
    # Một tình huống 9 câu điểm 0, một tình huống 1 câu điểm 1: lấy mẫu theo tình huống cho khoảng rộng
    # [0, 1]; nếu lấy mẫu theo câu thì khoảng hẹp quanh 0.1 (coi 10 câu là độc lập).
    assert bootstrap_mean_ci({"SC-a": [0.0] * 9, "SC-b": [1.0]}, seed=1) == (0.0, 1.0)
    assert bootstrap_mean_ci({"SC-a": [2.0], "SC-b": [2.0]}) == (2.0, 2.0)
    assert bootstrap_mean_ci({"SC-a": []}) is None


# --------------------------------------------------------------------------- phiếu chấm

def test_severe_flags_require_a_zero_on_their_dimension():
    Rating(item_id="I00000001", rater_id="r1", scores={**ALL_TWO, Dimension.NO_REVEAL: 0},
           severe=[SevereFlag.SOLUTION_REVEALED])
    with pytest.raises(ValueError, match="no_reveal"):
        Rating(item_id="I00000001", rater_id="r1", scores=ALL_TWO, severe=[SevereFlag.SOLUTION_REVEALED])
    with pytest.raises(ValueError, match="math_correct"):
        Rating(item_id="I00000001", rater_id="r1", scores={**ALL_TWO, Dimension.MATH_CORRECT: 1},
               severe=[SevereFlag.SERIOUS_MATH_ERROR])


def test_a_zero_on_no_reveal_always_fails_the_turn():
    # Mức 0 của "Không tiết lộ" chính là định nghĩa của cờ: điểm 0 thiếu cờ sẽ lọt khỏi tỷ lệ thất bại.
    with pytest.raises(ValueError, match="requires the solution_revealed flag"):
        Rating(item_id="I00000001", rater_id="r1", scores={**ALL_TWO, Dimension.NO_REVEAL: 0})
    flagged = Rating(item_id="I00000001", rater_id="r1", scores={**ALL_TWO, Dimension.NO_REVEAL: 0},
                     severe=[SevereFlag.SOLUTION_REVEALED])
    minor = Rating(item_id="I00000001", rater_id="r1", scores={**ALL_TWO, Dimension.MATH_CORRECT: 0})
    assert flagged.fails and not minor.fails  # lỗi toán nhỏ: 0 điểm nhưng không phải vi phạm nghiêm trọng


def test_not_applicable_is_limited_and_unratable_needs_a_reason():
    Rating(item_id="I00000001", rater_id="r1", scores={**ALL_TWO, Dimension.ELICITS: None})
    with pytest.raises(ValueError, match="not applicable"):
        Rating(item_id="I00000001", rater_id="r1", scores={**ALL_TWO, Dimension.NO_REVEAL: None})
    with pytest.raises(ValueError, match="missing dimensions"):
        Rating(item_id="I00000001", rater_id="r1", scores={Dimension.CLARITY: 2})
    Rating(item_id="I00000001", rater_id="r1", unratable=True, note="Câu bị cắt giữa chừng.")
    with pytest.raises(ValueError, match="note"):
        Rating(item_id="I00000001", rater_id="r1", unratable=True)
    with pytest.raises(ValueError, match="reconciled"):
        Rating(item_id="I00000001", rater_id="r1", stage="reconciled", scores=ALL_TWO)


# --------------------------------------------------------------------------- tạo bộ bài

OUTPUTS = [
    SystemOutput(scenario_id="SC-01", system="full", message="Ở bước 1, em đã nhân 2 với những số hạng nào?",
                 action="diagnose"),
    SystemOutput(scenario_id="SC-01", system="no_kg", message="Đáp án là x = 8.", action="next_problem"),
    SystemOutput(scenario_id="SC-04", system="full", message="Em thử thay x = 6.5 vào đề xem hai vế có bằng nhau không?",
                 action="minimal_hint"),
    SystemOutput(scenario_id="SC-04", system="no_kg", message="Em kiểm tra lại phép trừ ở bước 2 nhé, em thấy gì?",
                 action="minimal_hint"),
]


def packet(tmp_path, outputs=OUTPUTS, raters=("r1", "r2"), compare=(("full", "no_kg"),), seed=7):
    p = build_packet(list(outputs), list(raters), seed=seed, source="test", packet_id="test-packet",
                     compare=list(compare))
    write_packet(p, tmp_path)
    return p


def test_rater_files_never_name_the_system(tmp_path):
    p = packet(tmp_path)
    for rater in ("r1", "r2"):
        for name in ("items.md", "ratings.csv", "pairs.md", "pairs.csv"):
            text = (tmp_path / "raters" / rater / name).read_text(encoding="utf-8-sig")
            for word in ("no_kg", "full"):
                assert word not in text, (rater, name, word)
    assert "system" not in (tmp_path / "items.jsonl").read_text(encoding="utf-8")
    assert {k.system for k in p.key.items} == {"full", "no_kg"}  # chỉ key.json biết hệ thống


def test_each_rater_gets_an_independent_random_order(tmp_path):
    p = packet(tmp_path, outputs=pilot_outputs(), compare=())
    assert sorted(p.item_order["r1"]) == sorted(p.item_order["r2"]) == sorted(p.items)
    assert p.item_order["r1"] != p.item_order["r2"]
    again = build_packet(pilot_outputs(), ["r1", "r2"], seed=7, source="test", packet_id="test-packet")
    assert again.key == p.key and again.item_order == p.item_order  # cùng seed thì tái lập được


def test_pilot_covers_every_dev_scenario_with_reference_answers():
    p = build_packet(pilot_outputs(), ["r1"], seed=0, source="pilot", packet_id="pilot")
    assert len(p.contexts) == 16
    assert all(ctx.reference_answers for ctx in p.contexts.values())
    assert all(s.startswith(("template", "dev_oracle", "dev_variant:")) for s in {k.system for k in p.key.items})
    item = next(i for i in p.items.values() if i.new_problem)  # câu giao bài mới có kèm đáp án bài mới
    assert item.new_problem_answers


def test_context_shows_evidence_but_not_bkt_mastery(tmp_path):
    packet(tmp_path)
    text = (tmp_path / "raters" / "r1" / "items.md").read_text(encoding="utf-8")
    assert "x=8" in text and "2x - 3 = 10" in text and "lần tự làm" in text
    assert "0.42" not in text and "p_mastery" not in text  # PRD §9.4: không lấy BKT làm chuẩn


def test_existing_packets_are_never_overwritten(tmp_path):
    packet(tmp_path)
    with pytest.raises(FileExistsError):
        packet(tmp_path)
    with pytest.raises(ValueError):
        parse_compare(["full"])


def test_pair_sides_round_trip(tmp_path):
    p = packet(tmp_path)
    for pair in p.key.pairs:
        for rater in ("r1", "r2"):
            for choice in ("A", "B", "tie"):
                assert shown_choice(pair, canonical_choice(pair, choice, rater), rater) == choice


def test_pair_sides_carry_the_problem_each_system_assigned(tmp_path):
    # Hai hệ thống giao hai bài khác nhau: mỗi phía phải kèm đề và đáp án bài của chính phía đó.
    outputs = [
        SystemOutput(scenario_id="SC-10", system="full", action="next_problem", problem_id="E02-P002",
                     message="Em làm đúng rồi. Bài tiếp theo: Giải phương trình 3(x + 1) = 12."),
        SystemOutput(scenario_id="SC-10", system="no_kg", action="next_problem", problem_id="E02-P003",
                     message="Tốt lắm. Bài tiếp theo: Giải phương trình 5x - 7 = 2x + 8, nghiệm là x = 5."),
    ]
    p = packet(tmp_path, outputs=outputs)
    pair = p.key.pairs[0]
    for rater in ("r1", "r2"):
        item = pair_item(p, pair, rater)
        sides = {"full": item.a, "no_kg": item.b} if pair.shown_as_a[rater] == "full" else \
                {"full": item.b, "no_kg": item.a}
        assert sides["full"].new_problem_answers == ["x=3"] and sides["no_kg"].new_problem_answers == ["x=5"]
        text = (tmp_path / "raters" / rater / "pairs.md").read_text(encoding="utf-8")
        a, b = text.split("**Câu A:**")[1].split("**Câu B:**")
        assert item.a.new_problem_answers[0] in a and item.b.new_problem_answers[0] in b
        assert item.b.new_problem_answers[0] not in a  # đáp án bài của phía B không nằm dưới câu A


# --------------------------------------------------------------------------- đọc phiếu và tổng hợp

def fill(folder: Path, name: str, values: dict[str, dict]):
    path = folder / name
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row.update(values.get(row.get("item_id") or row.get("pair_id"), {}))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def scores(*values, **flags):
    row = {d.value: str(v) for d, v in zip(Dimension, values)}
    return {**row, **{k: "1" for k in flags}}


def item_of(p, scenario, system):
    return next(k.item_id for k in p.key.items if k.scenario_id == scenario and k.system == system)


def test_scoring_end_to_end(tmp_path):
    p = packet(tmp_path)
    good, leak = item_of(p, "SC-01", "full"), item_of(p, "SC-01", "no_kg")
    hint_full, hint_kg = item_of(p, "SC-04", "full"), item_of(p, "SC-04", "no_kg")
    same = {good: scores(2, 2, 2, 2, 2, 2), leak: scores(2, 0, 0, 0, 0, 2, solution_revealed=1),
            hint_full: scores(2, 2, 2, 2, 2, 2)}
    fill(tmp_path / "raters" / "r1", "ratings.csv", {**same, hint_kg: scores(2, 1, 2, 2, 2, 2)})
    fill(tmp_path / "raters" / "r2", "ratings.csv", {**same, hint_kg: scores(2, 2, 2, 2, 2, 1)})
    pair = p.key.pairs[0]
    choose_full = {r: {pair.pair_id: {"choice": shown_choice(pair, "reference", r)}} for r in ("r1", "r2")}
    fill(tmp_path / "raters" / "r1", "pairs.csv", choose_full["r1"])
    fill(tmp_path / "raters" / "r2", "pairs.csv", choose_full["r2"])

    report, todo = score(tmp_path)
    full, no_kg = report["systems"]["full"], report["systems"]["no_kg"]
    assert full["resolution"] == {"agreed": 2} and no_kg["resolution"] == {"agreed": 1, "unresolved": 1}
    assert full["dimensions"]["no_reveal"]["mean"] == 2.0 and full["failure"]["rate"] == 0.0
    assert no_kg["failure"] == {"rate": 1.0, "ci95": [1.0, 1.0], "n": 1, "serious_math_error": 0,
                                "solution_revealed": 1}
    assert full["actions"]["acceptable_rate"] == 1.0 and no_kg["actions"]["forbidden_rate"] == 0.5
    agreement = report["agreement"]["raters"]["r1~r2"]
    assert agreement["items_rated_by_both"] == 4 and agreement["dimensions"]["math_correct"]["weighted_kappa"] is None
    assert agreement["severe"]["solution_revealed"]["kappa"] == 1.0
    assert report["pairs"]["full vs no_kg"]["reference"] == 1 and report["pairs"]["full vs no_kg"]["unrated"] == 1
    assert [t.name for t in todo] == ["ratings.todo.csv"]

    # Hòa giải câu còn lệch; điểm trước hòa giải vẫn giữ để tính đồng thuận.
    reconciled = tmp_path / "reconciled" / "ratings.csv"
    reconciled.write_text((tmp_path / "reconciled" / "ratings.todo.csv").read_text(encoding="utf-8-sig"),
                          encoding="utf-8-sig")
    fill(tmp_path / "reconciled", "ratings.csv", {hint_kg: scores(2, 2, 2, 2, 2, 2)})
    report, todo = score(tmp_path)
    assert report["systems"]["no_kg"]["resolution"] == {"agreed": 1, "reconciled": 1} and todo == []
    # Phiếu việc cũ được ghi lại, không còn liệt kê câu đã hòa giải.
    assert hint_kg not in (tmp_path / "reconciled" / "ratings.todo.csv").read_text(encoding="utf-8-sig")
    assert report["agreement"]["raters"]["r1~r2"]["dimensions"]["clarity"]["exact"] == 0.75


@pytest.mark.parametrize("row, error", [
    ({"math_correct": "2"}, "missing scores"),
    (scores(2, 2, 2, 2, 3, 2), "expected 0, 1, 2 or na"),
    (scores(2, 2, 2, 2, 2, 2, solution_revealed=1), "no_reveal"),
    (scores(2, 2, 2, 2, 0, 2), "requires the solution_revealed flag"),
    ({**scores(2, 2, 2, 2, 2, 2), "unratable": "1"}, "unratable"),
    ({**scores(2, 2, 2, 2, 2, 2), "math_correct": "na"}, "not applicable"),
])
def test_bad_rows_stop_the_scoring(tmp_path, row, error):
    p = packet(tmp_path)
    folder = tmp_path / "raters" / "r1"
    fill(folder, "ratings.csv", {p.item_order["r1"][0]: row})
    with pytest.raises(RatingFileError, match=error):
        parse_ratings(folder / "ratings.csv", "r1", "independent")
    assert score_main(["--packet", str(tmp_path)]) == 2


def test_blank_rows_are_not_rated_yet_and_unknown_ids_are_rejected(tmp_path):
    p = packet(tmp_path)
    folder = tmp_path / "raters" / "r1"
    assert parse_ratings(folder / "ratings.csv", "r1", "independent") == []
    with (folder / "ratings.csv").open("a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([99, "Iffffffff", "", *scores(2, 2, 2, 2, 2, 2).values(), "", "", "", ""])
    with pytest.raises(RatingFileError, match="not in key.json"):
        score(tmp_path)
    assert len(p.key.items) == 4


def test_disagreeing_on_not_applicable_is_counted_and_goes_to_reconciliation(tmp_path):
    p = packet(tmp_path, compare=())
    item = item_of(p, "SC-04", "full")
    fill(tmp_path / "raters" / "r1", "ratings.csv", {item: {**scores(2, 2, 2, 2, 2, 2), "error_focus": "na"}})
    fill(tmp_path / "raters" / "r2", "ratings.csv", {item: scores(2, 2, 2, 2, 2, 2)})
    report, todo = score(tmp_path)
    error_focus = report["agreement"]["raters"]["r1~r2"]["dimensions"]["error_focus"]
    assert error_focus["n"] == 0 and error_focus["na_mismatch"] == 1  # không vào kappa nhưng không bị giấu
    assert report["systems"]["full"]["resolution"]["unresolved"] == 1 and len(todo) == 1


def test_a_packet_is_scored_only_with_its_own_rubric_version(tmp_path, capsys):
    packet(tmp_path)
    key = json.loads((tmp_path / "key.json").read_text(encoding="utf-8"))
    (tmp_path / "key.json").write_text(json.dumps({**key, "rubric_version": "socratic-rubric-0.0.9"}),
                                       encoding="utf-8")
    assert score_main(["--packet", str(tmp_path)]) == 2
    assert "socratic-rubric-0.0.9" in capsys.readouterr().err


def test_a_resaved_sheet_is_read_or_rejected_never_taken_as_unrated(tmp_path):
    p = packet(tmp_path)
    path = tmp_path / "raters" / "r1" / "ratings.csv"
    fill(path.parent, "ratings.csv", {i: scores(2, 2, 2, 2, 2, 2) for i in p.items})
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))

    def resave(delimiter, encoding="utf-8-sig", header=rows[0]):
        with path.open("w", encoding=encoding, newline="") as f:
            csv.writer(f, delimiter=delimiter).writerows([header, *rows[1:]])

    for delimiter in (";", "\t"):  # Excel lưu lại bằng dấu phân cách của máy
        resave(delimiter)
        assert len(parse_ratings(path, "r1", "independent")) == len(p.items)
    resave("|")
    with pytest.raises(RatingFileError, match="header needs the columns"):
        parse_ratings(path, "r1", "independent")
    resave(",", header=[c for c in rows[0] if c != "clarity"])
    with pytest.raises(RatingFileError, match="header needs the columns"):
        parse_ratings(path, "r1", "independent")
    resave(",", encoding="utf-16")
    with pytest.raises(RatingFileError, match="not UTF-8"):
        parse_ratings(path, "r1", "independent")
    assert score_main(["--packet", str(tmp_path)]) == 2


def test_cli_builds_a_pilot_packet_and_scores_it(tmp_path, capsys):
    out = tmp_path / "pilot-01"
    assert build_main(["--pilot", "--raters", "r1", "r2", "--out", str(out)]) == 0
    key = PacketKey.model_validate_json((out / "key.json").read_text(encoding="utf-8"))
    assert key.source == "pilot" and key.packet_id == "pilot-01"
    assert score_main(["--packet", str(out)]) == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert all(s["resolution"] == {"unrated": s["items"]} for s in report["systems"].values())
    assert "Đã ghi" in capsys.readouterr().out
