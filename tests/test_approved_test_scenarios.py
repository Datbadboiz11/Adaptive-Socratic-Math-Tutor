"""Bộ tình huống test trên bài đã duyệt (research/scenarios/approved_test.py) và cách chia họ bài với dev."""
from collections import Counter
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from research.scenarios import approved_dev, approved_test  # noqa: E402
from research.scenarios.build import PLAN_CASE_TAGS, build, grouped_splits  # noqa: E402
from research.scenarios.contracts import ScenarioDataset, ScenarioDraft  # noqa: E402
from research.scenarios.replay import replay  # noqa: E402

CONTENT = approved_dev.CONTENT


@pytest.fixture(scope="module")
def dev():
    return approved_dev.dataset()


@pytest.fixture(scope="module")
def test():
    return approved_test.dataset()


def concept(s) -> str:
    return s.history[-1].task.concept_id


def test_the_committed_file_is_what_the_source_generates():
    assert approved_test.main(["--check"]) == 0


def test_test_cases_wait_for_two_independent_raters(test):
    assert len(test.scenarios) == 39
    assert all(s.split == "test" and s.labels is None for s in test.scenarios)
    assert Counter(concept(s) for s in test.scenarios) == {c: 3 for c in approved_dev.TEST_FAMILIES}


def test_every_concept_has_four_dev_cases(dev):
    counts = Counter(concept(s) for s in dev.scenarios)
    assert set(counts) == set(approved_dev.TEST_FAMILIES) and min(counts.values()) >= 4


def test_both_sets_cover_the_plan_situation_categories(dev, test):
    for data in (dev, test):
        assert PLAN_CASE_TAGS <= {tag for s in data.scenarios for tag in s.tags}


def test_each_concept_keeps_at_least_one_family_on_each_side():
    families = {}
    for pid, p in CONTENT.problems.items():
        families.setdefault(p.ref.concept_id, {}).setdefault(approved_dev.family_split(pid), set()).add(
            p.ref.template_family_id)
    assert set(families) == set(approved_dev.TEST_FAMILIES)
    assert all(sides.get("dev") and sides.get("test") for sides in families.values())


def test_dev_and_test_share_no_problem_family(dev, test):
    assert approved_test.leaks(dev, test) == []


def test_a_dev_case_on_a_test_family_is_caught(dev, test):
    """AT-01 dùng bài A01 họ 2: một ca dev trên bài đó phải bị báo, cả theo bảng họ lẫn theo grouped_splits."""
    stray = approved_dev.session("AP-X", approved_dev.P("A01", 4)).work(["1"], "verified_correct").scenario(
        "lộ bài", ["correct_independent"], approved_dev.first_correct())
    leaked = dev.model_copy(update={"scenarios": [*dev.scenarios, stray]})
    found = approved_test.leaks(leaked, test)
    assert any("AP-X (dev)" in f for f in found)
    assert any("Conflicting splits" in f for f in found)


def test_no_case_offers_or_shows_the_other_side(dev, test):
    """Bài ứng viên và ví dụ mẫu trong context cũng thuộc họ của phía mình: ca dev không đưa bài hay lời
    giải mẫu của test cho hệ thống chọn và chép lại (review: dev giao nguyên đề test)."""
    for split, data in (("dev", dev), ("test", test)):
        for s in data.scenarios:
            assert s.context.problems, s.scenario_id
            assert {approved_dev.family_split(p.problem_id) for p in s.context.problems} == {split}, s.scenario_id
            assert {approved_dev.content_split(c.content_id) for c in s.context.retrieved} <= {None, split}
    examples = {c.content.content_id for c in CONTENT.chunks if c.content.content_type == "example"}
    assert {approved_dev.content_split(i) for i in examples} == {"dev", "test"}


def test_a_dev_case_offering_test_problems_is_caught(dev, test):
    """Ca dev soạn bằng công cụ thấy cả ngân hàng (như bản v0.2.0) phải bị báo, dù lịch sử chỉ có bài dev."""
    from app.agent.approved_content import ApprovedTools

    s = approved_dev.session("AP-X", approved_dev.P("A01", 1))
    s.tools = ApprovedTools(CONTENT, approved_dev.KG)
    stray = s.work(["1"], "verified_incorrect").scenario("lộ bài ứng viên", ["final_answer_only"],
                                                         approved_dev.first_wrong())
    found = approved_test.leaks(dev.model_copy(update={"scenarios": [*dev.scenarios, stray]}), test)
    assert any(f.startswith("AP-X offers") for f in found)


def test_no_kg_runs_keep_to_the_same_side(dev):
    """No-KG lấy bài của concept đang học từ chính tình huống, không lấy lại từ cả ngân hàng."""
    from app.agent.decision import ExperimentConfiguration
    from research.evaluation.run_ablation import project_context

    for s in dev.scenarios:
        state, _ = replay(s, dev, approved_dev.KG)
        ctx = project_context(s.context, state, ExperimentConfiguration.NO_KG)
        assert ctx.problems and {approved_dev.family_split(p.problem_id) for p in ctx.problems} == {"dev"}
        assert {p.concept_id for p in ctx.problems} == {state.current.concept_id}


def gate_blocks(state, action, problems=None) -> str | None:
    """Luật gate mà action này chắc chắn vi phạm ở state đó, với mọi đề xuất cụ thể. ``problems``: bài
    ứng viên trong context; action giao bài mà không có bài nào hợp lệ thì cũng chắc chắn bị chặn."""
    from app.agent.decision import ACTION_SPECS, MAX_SUPPORT_TURNS_PER_NODE, PedagogicalAction as A
    from app.agent.gate import STUCK_ALLOWED_ACTIONS

    a = state.latest_assessment
    status = a.assessment_status if a else None
    spec = ACTION_SPECS[A(action)]
    if state.trigger == "pause" and action != "end_session":
        return "G14"
    if state.trigger == "submit" and status in {"unverified", "needs_clarification"} \
            and action not in {"clarify", "end_session"}:
        return "G01"
    if spec.counts_as_assistance and min(spec.hint_levels) > state.support.hint_level + 1:
        return "G02"
    stuck = state.support.support_turns_on_node >= MAX_SUPPORT_TURNS_PER_NODE and status != "verified_correct"
    if stuck and A(action) not in STUCK_ALLOWED_ACTIONS and action != "next_problem":
        return "G10"
    if status == "verified_incorrect" and state.support.hint_level >= 3 \
            and action in {"minimal_hint", "conceptual_question"}:
        return "G11"
    if status == "verified_incorrect" and action == "check_transfer":
        return "G06"
    if problems is not None:
        cur = state.current
        others = [p for p in problems if p.problem_id != cur.problem_id]
        if action == "next_problem" and not others:
            return "G13"
        transfer = [p for p in others if p.concept_id == cur.concept_id and p.target_skill_id == cur.target_skill_id
                    and p.template_family_id != cur.template_family_id]
        if action == "check_transfer" and not transfer:
            return "G12"
    return None


def test_every_acceptable_action_can_pass_the_gate(dev, test):
    """Nhãn không được chấp nhận action mà gate chắc chắn từ chối ở state đó (review: AP-45 nhận scaffold
    ở mức gợi ý 1, trong khi scaffold là mức 3 và gate chỉ cho lên một nấc)."""
    for data in (dev, test):
        for s in data.scenarios:
            if s.labels is None:
                continue
            state, _ = replay(s, data, approved_dev.KG)
            blocked = {a.value: gate_blocks(state, a.value, s.context.problems) for a in s.labels.acceptable_actions}
            assert not any(blocked.values()), (s.scenario_id, blocked)
    state, _ = replay(next(s for s in dev.scenarios if s.scenario_id == "AP-45"), dev, approved_dev.KG)
    assert gate_blocks(state, "scaffold") == "G02"


def test_transfer_is_only_accepted_where_a_new_family_is_offered(dev):
    """Concept mà phía dev chỉ có một họ thì không có bài khác họ để kiểm tra chuyển giao (G12): nhãn
    chuyển check_transfer sang bị cấm và ghi lý do (review: 9 ca dev vẫn nhận giao bài chuyển giao)."""
    cases = {s.scenario_id: s for s in dev.scenarios}
    no_family = {sid for sid, s in cases.items() if not approved_dev.transfer_problems(s)
                 and "check_transfer" in s.labels.forbidden_actions and "(G12)" in s.labels.rationale}
    assert {"AP-01", "AP-02", "AP-06", "AP-12", "AP-14", "AP-24", "AP-32", "AP-34", "AP-51"} <= no_family
    assert "check_transfer" in cases["AP-09"].labels.acceptable_actions  # A04 còn hai họ ở dev
    assert [a.value for a in cases["AP-14"].labels.acceptable_actions] == ["next_problem"]


def test_every_test_submission_is_graded_by_the_system_validator(test):
    from app import math_validator
    from app.agent.validator_analyzer import ValidatorAnalyzer

    analyzer = ValidatorAnalyzer(CONTENT.validator_task, validate=math_validator.validate)
    submissions = [e for s in test.scenarios for e in s.history if e.kind == "submit"]
    assert len(submissions) == 41
    for event in submissions:
        view = analyzer(SimpleNamespace(current=event.task), list(event.submission))
        assert (view.assessment_status, view.unfinished, view.final_answer_only) == (
            event.assessment.assessment_status, event.assessment.unfinished, event.assessment.final_answer_only)


def test_test_cases_replay_without_bkt_evidence(test):
    for draft in test.scenarios:
        state, trace = replay(draft, test, approved_dev.KG)
        assert all(k.independent_observations == 0 for k in state.skills), draft.scenario_id
        assert all(r.reason == "not_target_evidence" for r in trace), draft.scenario_id


def test_unlabeled_cases_cannot_be_built_or_scored(test):
    with pytest.raises(ValueError, match="without labels"):
        build(test)


def draft_labels():
    return approved_dev.labels(["diagnose"], ["next_problem"], "nhãn nháp của một người")


def adjudicated_labels():
    from research.scenarios.contracts import RaterLabel

    raters = [RaterLabel(rater=r, acceptable_actions=["diagnose"], rationale="gán độc lập") for r in ("r1", "r2")]
    return draft_labels().model_copy(update={"review_status": "adjudicated", "independent_labels": raters})


def test_a_draft_label_is_not_enough_to_score_a_test_case(test):
    """Một người điền nhãn nháp chưa đủ: ca test cần nhãn đã hòa giải của hai người (plan §12)."""
    one = test.model_copy(update={"scenarios": [test.scenarios[0].model_copy(update={"labels": draft_labels()})]})
    with pytest.raises(ValueError, match="adjudicated"):
        build(one)
    # Ca chưa gán split mà grouped_splits xếp vào test cũng vậy.
    free = test.model_copy(update={"scenarios": [s.model_copy(update={"split": None, "labels": draft_labels()})
                                                 for s in test.scenarios]})
    assert "test" in {split for split, _ in grouped_splits(free, "adaptive-split-v1").values()}
    with pytest.raises(ValueError, match="adjudicated"):
        build(free)
    ok = test.model_copy(update={"scenarios": [test.scenarios[0].model_copy(update={"labels": adjudicated_labels()})]})
    sets, _, _ = build(ok)
    assert [s.scenario_id for s in sets["test"].scenarios] == [test.scenarios[0].scenario_id]


def test_the_scorer_refuses_a_test_set_with_draft_labels(test, tmp_path):
    """File test dựng ngoài ``build`` mà còn nhãn nháp cũng không vào được bước chấm."""
    from research.agent.scenarios import load_scenarios

    ok = test.model_copy(update={"scenarios": [test.scenarios[0].model_copy(update={"labels": adjudicated_labels()})]})
    built = build(ok)[0]["test"]
    path = tmp_path / "test.json"
    path.write_text(built.model_dump_json(), encoding="utf-8")
    assert len(load_scenarios(path=path)) == 1
    forged = built.model_copy(update={"scenarios": [built.scenarios[0].model_copy(update={"labels": draft_labels()})]})
    path.write_text(forged.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="adjudicated"):
        load_scenarios(path=path)


def test_only_test_cases_may_wait_for_labels(test):
    raw = test.scenarios[0].model_dump(mode="json")
    with pytest.raises(ValueError, match="Only test"):
        ScenarioDraft.model_validate({**raw, "split": "dev"})
    with pytest.raises(ValueError, match="Only test"):
        ScenarioDraft.model_validate({**raw, "split": None})
    ScenarioDataset.model_validate(test.model_dump(mode="json"))


def test_the_rater_sheet_shows_no_label(test, tmp_path):
    out = tmp_path / "sheet.md"
    assert approved_test.main(["--sheet", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert all(f"## {s.scenario_id}. Concept {concept(s)}\n" in text for s in test.scenarios)
    assert "**Nhãn" not in text and "Lý do:** " not in text
    # Tiêu đề và loại ca là cách người soạn diễn giải lỗi: không được lọt vào phiếu.
    assert "- Loại:" not in text
    # Kết quả chấm vẫn phải đủ: "đúng giá trị nhưng chưa hoàn tất" khác với "chưa chấm được".
    unfinished = [s for s in test.scenarios if any(e.kind == "submit" and e.assessment.unfinished for e in s.history)]
    assert unfinished
    for s in unfinished:
        block = text.split(f"## {s.scenario_id}. ", 1)[1].split("\n## ", 1)[0]
        assert "chưa hoàn tất" in block, s.scenario_id
    assert not [s.scenario_id for s in test.scenarios if s.title in text]
