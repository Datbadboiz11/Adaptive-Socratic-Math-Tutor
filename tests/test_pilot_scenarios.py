"""Bộ tình huống dev pilot (plan §11.5, §12): nguồn khớp file, nhãn chi tiết, nhãn độc lập, công cụ soạn ca."""
from pathlib import Path
import sys

from pydantic import ValidationError
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from research.agent.scenarios import load_scenarios  # noqa: E402
from research.evaluation import select_thresholds  # noqa: E402
from research.evaluation.run_ablation import Models, run_turn, summarize  # noqa: E402
from research.scenarios import pilot_dev  # noqa: E402
from research.scenarios.build import PLAN_CASE_TAGS, build, label_agreement  # noqa: E402
from research.scenarios.contracts import RaterLabel, ScenarioDataset, StrategyLabels  # noqa: E402

BASE = dict(author="a", rationale="vì sao")


@pytest.fixture(scope="module")
def data() -> ScenarioDataset:
    return pilot_dev.dataset()


@pytest.fixture(scope="module")
def built(data):
    return build(data)


@pytest.fixture(scope="module")
def dev_file(built, tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("pilot") / "dev.json"
    path.write_text(built[0]["dev"].model_dump_json(), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- bộ pilot

def test_the_committed_file_is_what_the_source_generates():
    assert pilot_dev.main(["--check"]) == 0


def test_every_case_is_reviewed_pinned_to_dev_and_covers_the_plan_categories(data, built):
    sets, report, _ = built
    assert len(data.scenarios) == 33 and not sets["test"].scenarios and len(sets["dev"].scenarios) == 33
    assert all(s.split == "dev" and s.labels.review_status == "human_approved" and s.labels.author == pilot_dev.AUTHOR
               and s.labels.reviewer == pilot_dev.REVIEWER != pilot_dev.AUTHOR and not s.labels.independent_labels
               and s.source == "synthetic_authoring" for s in data.scenarios)
    assert PLAN_CASE_TAGS <= {tag for s in data.scenarios for tag in s.tags}
    assert report["splits"]["dev"]["label_statuses"] == {"human_approved": 33}
    assert report["splits"]["dev"]["detail_labels"] >= 15


def test_the_set_has_cases_that_reach_readiness_and_separates_threshold_sets(dev_file):
    scenarios = load_scenarios(path=dev_file)
    assert sum(sc.state.readiness.ready_to_advance for sc in scenarios) >= 2
    rows, selection = select_thresholds.run(scenarios)
    for view, s in selection.items():
        assert s["tied_with_selected"] < s["candidates"], view  # bộ 16 ca cũ: mọi bộ ngưỡng BKT hòa nhau
        assert s["start"]["detail_labeled"] >= 15 and s["start"]["errors"] == 0
    assert {r["ready_to_advance"] for r in rows} != {0}


def test_the_blind_sheet_hides_the_draft_labels():
    reviewed, blind = pilot_dev.review_sheet(), pilot_dev.review_sheet(blind=True)
    assert "Nhãn (human_approved), chấp nhận được" in reviewed and "DP-33" in reviewed
    assert "Nhãn (" not in blind and "Lý do: " in blind and "DP-33" in blind
    assert pilot_dev.dataset().scenarios[0].labels.rationale not in blind


def test_ablation_reports_the_detail_labels(dev_file):
    scenarios = {sc.id: sc for sc in load_scenarios(path=dev_file)}
    rows = [run_turn(scenarios[i], "rule_policy", Models.fake()) for i in ("DP-09", "DP-22")]
    assert rows[0]["final_detail_acceptable"] is None            # DP-09 không có nhãn intent/skill
    assert rows[1]["final_detail_acceptable"] in (True, False)   # DP-22 có
    assert summarize(rows)["configurations"]["rule_policy"]["final_detail_acceptable"]["of"] == 1


def test_a_slip_on_the_current_skill_does_not_send_the_student_back_to_a_weak_prerequisite(dev_file):
    """DP-33 (nhãn đã duyệt): vừa phân phối đúng, chỉ tính sai; ước lượng cũ của tính phân phối còn thấp.
    Lỗi thao tác quy cho skill đang học nên policy không hỏi kiểm tra skill nền. Cùng state nhưng lỗi
    không phải lỗi thao tác (họ lỗi chưa rõ) thì ước lượng thấp của skill nền vẫn dẫn tới hỏi kiểm tra."""
    from app.agent.rule_policy import rule_policy
    sc = {s.id: s for s in load_scenarios(path=dev_file)}["DP-33"]
    slip = rule_policy(sc.state, sc.context)
    assert slip.intent != "probe_prerequisite" and slip.target_skill_id == "SK-E02-SOLVE"
    assert sc.labels.accepts(slip.action, slip.intent, slip.target_skill_id)
    a = sc.state.latest_assessment.model_copy(update={"error_family": None})
    other = rule_policy(sc.state.model_copy(update={"latest_assessment": a}), sc.context)
    assert (other.intent, other.target_skill_id) == ("probe_prerequisite", "SK-A02-DISTRIBUTE")


def test_a_slip_still_uses_direct_evidence_about_the_prerequisite(dev_file):
    """Ca từ review: quy tắc chỉ bỏ ước lượng thấp cũ. (1) Lỗi tính quy cho chính skill nền: so với skill
    đích của bài, không với skill của lỗi, nên vẫn xử lý skill nền. (2) Câu kiểm tra skill nền đã xác minh
    là chưa đạt: bằng chứng trực tiếp, vẫn được dùng dù lỗi hiện tại là lỗi tính của skill đang học."""
    from uuid import uuid4
    from app.agent.decision import PrerequisiteProbe
    from app.agent.rule_policy import rule_policy
    sc = {s.id: s for s in load_scenarios(path=dev_file)}["DP-33"]
    on_prerequisite = sc.state.latest_assessment.model_copy(update={"primary_skill_id": "SK-A02-DISTRIBUTE"})
    first = rule_policy(sc.state.model_copy(update={"latest_assessment": on_prerequisite}), sc.context)
    assert first.target_skill_id == "SK-A02-DISTRIBUTE"
    failed = PrerequisiteProbe(decision_id=uuid4(), skill_id="SK-A02-DISTRIBUTE", status="not_demonstrated",
                               answer_turn_id=uuid4())
    second = rule_policy(sc.state.model_copy(update={"probes": [failed]}), sc.context)
    assert second.target_skill_id == "SK-A02-DISTRIBUTE" or second.action == "backtrack"


# --------------------------------------------------------------------------- hợp đồng nhãn

def test_listed_intents_restrict_only_their_own_action():
    label = StrategyLabels(acceptable_actions=["next_problem", "check_transfer"], acceptable_intents=["continue_practice"],
                           acceptable_target_skill_ids=["SK-E02-SOLVE"], **BASE)
    assert label.accepts("next_problem", "continue_practice", "SK-E02-SOLVE")
    assert not label.accepts("next_problem", "advance_concept", "SK-E02-SOLVE")   # intent ngoài danh sách
    assert label.accepts("check_transfer", "independent_check", "SK-E02-SOLVE")   # action không bị ràng buộc intent
    assert not label.accepts("check_transfer", "independent_check", "SK-A02-DISTRIBUTE")
    assert not label.accepts("minimal_hint", "recall_rule", "SK-E02-SOLVE")
    assert label.has_detail and not StrategyLabels(acceptable_actions=["clarify"], **BASE).has_detail


@pytest.mark.parametrize("fields", [
    dict(acceptable_actions=["diagnose"], acceptable_intents=["continue_practice"]),      # intent của action khác
    dict(acceptable_actions=["diagnose"], forbidden_actions=["diagnose"]),
    dict(acceptable_actions=["diagnose"], review_status="adjudicated"),                    # thiếu nhãn độc lập
    dict(acceptable_actions=["diagnose"], review_status="adjudicated",
         independent_labels=[dict(rater="r1", acceptable_actions=["diagnose"], rationale="x")] * 2),  # trùng người
])
def test_inconsistent_labels_are_rejected(fields):
    with pytest.raises(ValidationError):
        StrategyLabels(**fields, **BASE)


def test_agreement_is_computed_from_the_independent_labels(built):
    case = built[0]["dev"].scenarios[0]

    def labeled(*raters):
        final = case.labels.model_copy(update={"review_status": "adjudicated", "independent_labels": [
            RaterLabel(rater=name, acceptable_actions=ok, forbidden_actions=no, rationale="x")
            for name, ok, no in raters]})
        return case.model_copy(update={"labels": StrategyLabels.model_validate(final.model_dump())})

    same = labeled(("r1", ["next_problem"], []), ("r2", ["next_problem"], []))
    apart = labeled(("r1", ["next_problem", "check_transfer"], []), ("r2", ["next_problem"], ["check_transfer"]))
    assert label_agreement([case]) == {"double_labeled": 0, "pairs": 0, "exact_acceptable": None,
                                       "mean_jaccard_acceptable": None, "conflicts": None,
                                       "intent_disagreements": None, "skill_disagreements": None}
    assert label_agreement([same, apart]) == {"double_labeled": 2, "pairs": 2, "exact_acceptable": 0.5,
                                              "mean_jaccard_acceptable": 0.75, "conflicts": 1,
                                              "intent_disagreements": 0, "skill_disagreements": 0}


def test_raters_can_disagree_on_the_intent_and_skill_to_target(built):
    """Ca từ review: nhãn độc lập phải lưu được skill cần hướng tới, như nhãn cuối."""
    case = built[0]["dev"].scenarios[0]
    raters = [RaterLabel(rater="r1", acceptable_actions=["diagnose"], acceptable_intents=["probe_prerequisite"],
                         acceptable_target_skill_ids=["SK-A02-DISTRIBUTE"], rationale="x"),
              RaterLabel(rater="r2", acceptable_actions=["diagnose"], acceptable_intents=["elicit_reasoning"],
                         acceptable_target_skill_ids=["SK-E02-SOLVE"], rationale="x")]
    final = StrategyLabels(acceptable_actions=["diagnose"], review_status="adjudicated", independent_labels=raters,
                           **BASE)
    stats = label_agreement([case.model_copy(update={"labels": final})])
    assert (stats["exact_acceptable"], stats["intent_disagreements"], stats["skill_disagreements"]) == (1.0, 1, 1)


# --------------------------------------------------------------------------- công cụ soạn ca

def test_the_session_keeps_the_task_the_system_holds():
    s = (pilot_dev.session("T-01", "E02-P001").submit(pilot_dev.P001_DIST, "verified_incorrect", **pilot_dev.DIST)
         .tutor("backtrack", "review_prerequisite", problem="A02-P002"))
    assert s.state.current.problem_id == "A02-P002" and s.state.current.relation == "prerequisite"
    s.correct(["4a - 20"]).tutor("next_problem", "return_to_parent")
    assert (s.state.current.problem_id, s.state.current.relation) == ("E02-P001", "repeat")
    assert s.events[-1].problem_id == "E02-P001"  # bài cha lấy từ return stack


def test_the_session_refuses_what_the_system_could_not_have_done():
    s = pilot_dev.session("T-02", "E02-P001").correct(pilot_dev.P001_RIGHT)
    with pytest.raises(ValueError, match="G12"):   # check_transfer phải sang họ mẫu khác
        s.tutor("check_transfer", "independent_check", problem="E02-P002")
    with pytest.raises(ValueError, match="answers a student turn"):
        pilot_dev.session("T-03", "E02-P001").tutor("diagnose", "elicit_reasoning")
    with pytest.raises(ValueError, match="must answer"):
        pilot_dev.session("T-04", "E02-P001").hint().hint()
