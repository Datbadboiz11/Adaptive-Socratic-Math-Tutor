"""Replay khớp state của graph, điều kiện observation, chia nhóm chống rò rỉ và nối vào ablation."""
import copy
import json
from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from app.agent.decide import RulePolicyProposer  # noqa: E402
from app.agent.decision import ACTION_SPECS, DecisionConfig, SupportState  # noqa: E402
from app.agent.graph import Services, TurnInput, TutorEngine  # noqa: E402
from app.kg.graph import KnowledgeGraph  # noqa: E402
from app.knowledge import update  # noqa: E402
from research.agent.scenarios import load_scenarios  # noqa: E402
from research.evaluation.run_ablation import main as ablation_main  # noqa: E402
from research.scenarios.build import build, grouped_splits, main  # noqa: E402
from research.scenarios.contracts import ScenarioDataset  # noqa: E402
from research.scenarios.replay import observe, replay  # noqa: E402

N01, A02, E02 = "SK-N01-SIGNED-ADD", "SK-A02-DISTRIBUTE", "SK-E02-SOLVE"


@pytest.fixture
def source():
    return json.loads((ROOT / "contracts/scenarios/examples.dev.v1.json").read_text(encoding="utf-8"))


def dataset(source):
    return ScenarioDataset.model_validate(source)


def replayed(source, index):
    data = dataset(source)
    return replay(data.scenarios[index], data)


def task(source, problem_id, relation="initial", opportunity_id=None):
    ref = next(p["problem"] for p in source["problems"] if p["problem"]["problem_id"] == problem_id)
    return {**ref, "opportunity_id": opportunity_id or str(uuid4()), "relation": relation}


def student(on, kind, **extra):
    return {"turn_id": str(uuid4()), "request_id": str(uuid4()), "task": on, "actor": "student", "kind": kind, **extra}


def graded(on, lines, status, **assessment):
    return student(on, "submit", submission=lines, assessment={
        "assessment_id": str(uuid4()), "assessment_status": status, "primary_skill_id": on["target_skill_id"],
        **assessment})


def tutor(on, action, intent, hint_level=0, **extra):
    return {"turn_id": str(uuid4()), "request_id": str(uuid4()), "task": on, "actor": "tutor", "kind": "decision",
            "action": action, "intent": intent, "hint_level": hint_level, **extra}


# --------------------------------------------------------------------------- replay khớp graph

class RecordingProposer(RulePolicyProposer):
    """Giữ lại state mà graph đưa cho policy ở mỗi lượt: đó là state "ngay trước quyết định"."""

    def __init__(self):
        self.seen = []

    def __call__(self, state, ctx):
        self.seen.append(state)
        return super().__call__(state, ctx)


def test_replay_rebuilds_the_state_the_graph_holds_before_each_decision(source):
    # Một phiên thật qua graph: chẩn đoán, hỏi khái niệm, gợi ý, chia nhỏ, backtrack, quay lại bài
    # cha, kiểm tra chuyển giao, nhắn tin, tạm dừng và tiếp tục. Lịch sử của phiên đó, đem replay,
    # phải cho lại đúng state mà graph đã đưa cho policy ở từng lượt.
    data = dataset(source)
    proposer = RecordingProposer()
    engine = TutorEngine(DecisionConfig(configuration="rule_policy", policy_version="rule-policy-0.1.0"), Services(
        proposer=proposer, observer=lambda state, a, seen: observe(state, seen, data.parameters)[0]))
    sid = engine.start("demo-a", "E02-P001").session_id
    wrong, right = ["2x - 3 = 10", "2x = 13", "x = 6.5"], ["2x - 6 = 10", "2x = 16", "x = 8"]
    turns = [("submit", wrong), ("submit", wrong), ("request_hint",), ("request_hint",), ("submit", wrong),
             ("submit", ["-6y - 8"]), ("submit", right), ("message", "Em chưa hiểu đề bài này"), ("pause",),
             ("resume",)]
    for trigger, *payload in turns:
        fields = {"steps": payload[0]} if trigger == "submit" else {"message": payload[0]} if payload else {}
        engine.turn(sid, TurnInput(request_id=uuid4(), trigger=trigger, **fields))
    decisions = [d.final for d in engine.decisions(sid)]
    assert {d.action for d in decisions} >= {"diagnose", "scaffold", "backtrack", "check_transfer", "end_session"}
    assert "return_to_parent" in {d.intent for d in decisions}

    history = []
    for seen, decision, record in zip(proposer.seen, decisions, engine.decisions(sid)):
        on = seen.current.model_dump(mode="json")
        history.append(student(on, seen.trigger, turn_id=str(seen.turn_id), request_id=str(seen.request_id),
                               message=seen.latest_student_message)
                       if seen.trigger != "submit" else
                       student(on, "submit", turn_id=str(seen.turn_id), request_id=str(seen.request_id),
                               message=seen.latest_student_message, submission=seen.latest_submission,
                               assessment=seen.latest_assessment.model_dump(mode="json")))
        draft = {**source["scenarios"][0], "student_id": "demo-a", "session_id": str(sid), "history": list(history)}
        state, _ = replay(dataset({**source, "scenarios": [draft]}).scenarios[0], data)
        untouched = [k for k in state.skills if seen.skill(k.skill_id) is None]
        assert all(k.independent_observations == 0 and k.assisted_correct == 0 for k in untouched)
        # Replay khai báo sẵn mọi skill có tham số, graph tạo skill khi gặp: so phần chung, không kể thứ tự.
        ours, theirs = (s.model_copy(update={"skills": sorted(
            (k for k in s.skills if k not in untouched), key=lambda k: k.skill_id)}).model_dump(mode="json")
            for s in (state, seen))
        assert not {k: (ours[k], theirs[k]) for k in ours if ours[k] != theirs[k]}, (len(history), seen.trigger)
        assigned = decision.problem_id if ACTION_SPECS[decision.action].requires_problem else None
        history.append(tutor(on, decision.action, decision.intent, decision.hint_level, problem_id=assigned,
                             turn_id=str(record.decision_id), target_skill_id=decision.target_skill_id))


def test_hypotheses_come_from_the_assessment_like_in_the_graph(source):
    # AD-EX-05: assessment có misconception_candidate. Graph tạo một giả thuyết "suspected" từ đó.
    state, _ = replayed(source, 4)
    assert [(h.misconception_id, h.skill_id, h.status) for h in state.hypotheses] == [("M_DIST_01", A02, "suspected")]
    assert state.hypotheses[0].evidence_ids == [str(state.latest_assessment.assessment_id)]


@pytest.mark.parametrize("field", ["hypotheses", "made_progress"])
def test_events_cannot_carry_state_the_system_derives(source, field):
    source["scenarios"][0]["history"][0][field] = []
    with pytest.raises(ValueError):
        dataset(source)


def test_student_turns_and_tutor_decisions_alternate(source):
    case = source["scenarios"][0]
    case["history"].append(student(case["history"][0]["task"], "request_hint"))
    with pytest.raises(ValueError, match="alternate"):
        replayed(source, 0)
    # AD-EX-06 có quyết định của tutor giữa lần nộp sai và lời xin đáp án: lượt đó tính là hỗ trợ.
    state, _ = replayed(source, 5)
    assert state.trigger == "message" and state.state_version == 2
    assert state.support.support_turns_on_node == 1 and state.support.hint_level == 0


@pytest.mark.parametrize("change", [{"intent": None}, {"intent": "review_prerequisite"}, {"hint_level": 3},
                                    {"problem_id": "E02-P002"},
                                    {"action": "check_transfer", "intent": "independent_check", "hint_level": 0,
                                     "problem_id": "E02-P003", "target_skill_id": None}])
def test_tutor_events_must_be_decisions_the_system_can_make(source, change):
    case = source["scenarios"][1]
    case["history"][1].update(change)
    with pytest.raises(ValueError):
        dataset(source)


# --------------------------------------------------------------------------- observation và BKT

def test_replay_matches_backend_prediction_and_keeps_assisted_results_separate(source):
    data = dataset(source)
    case = data.scenarios[1]
    state, trace = replay(case, data)
    skill = state.skill(case.history[-1].task.target_skill_id)
    params = data.parameters[skill.skill_id]
    expected = update(params.prior, False, params.model_dump())
    assert skill.independent_observations == 1 and skill.recent_independent == [False]
    assert skill.p_mastery == pytest.approx(expected["mastery_after"])
    assert skill.assisted_correct == 1 and state.observation.eligible is False
    assert trace[0].prediction_before == expected["prediction_before"]
    assert trace[1].reason == "already_observed" and trace[1].mastery_before == trace[1].mastery_after
    assert state.support.hint_level == 1 and state.support.support_turns_on_node == 1
    assert state.state_version == 2 and state.readiness.ready_to_advance is False


def test_returning_to_a_parent_problem_does_not_update_bkt(source):
    source["scenarios"][0]["history"][0]["task"]["relation"] = "repeat"
    state, trace = replayed(source, 0)
    assert state.skill(N01).independent_observations == 0
    assert not trace[0].eligible and trace[0].prediction_before is None


def test_wrong_non_target_skill_and_ambiguous_input_do_not_update_mastery(source):
    for index in (3, 4):
        state, trace = replayed(source, index)
        assert not state.observation.eligible
        assert all(s.independent_observations == 0 for s in state.skills)
        assert trace[0].mastery_before == trace[0].mastery_after


def test_identical_retry_is_idempotent_and_conflicting_retry_is_rejected(source):
    case = source["scenarios"][0]
    case["history"].append(copy.deepcopy(case["history"][0]))
    state, trace = replayed(source, 0)
    assert len(trace) == state.state_version == 1
    case["history"][-1]["submission"] = ["123"]
    with pytest.raises(ValueError, match="conflicting duplicate"):
        replayed(source, 0)


def test_hint_request_and_pause_do_not_create_observations(source):
    case = source["scenarios"][0]
    on = case["history"][0]["task"]
    case["history"] += [tutor(on, "diagnose", "elicit_reasoning", target_skill_id=N01), student(on, "request_hint"),
                        tutor(on, "minimal_hint", "recall_rule", 1, target_skill_id=N01), student(on, "pause")]
    state, trace = replayed(source, 0)
    # Như node load của graph: lượt xin dừng vẫn là lượt của phiên đang chạy; quyết định mới đổi status.
    assert state.status == "active" and state.trigger == "pause" and state.observation is None
    assert len(trace) == 1 and state.skill(N01).independent_observations == 1
    assert state.support.hint_level == 1 and state.support.support_turns_on_node == 2

    case["history"] += [tutor(on, "end_session", "student_request"), student(on, "resume")]
    state, _ = replayed(source, 0)
    assert state.status == "active" and state.trigger == "resume"
    case["history"][-1] = student(on, "request_hint")
    with pytest.raises(ValueError, match="paused"):
        replayed(source, 0)


def assisted_correct_on_e02(source):
    """AD-EX-05 nối thêm: sau lần sai có một gợi ý, rồi học sinh làm đúng bài E02-P001."""
    case = source["scenarios"][4]
    on = case["history"][0]["task"]
    case["history"] += [tutor(on, "minimal_hint", "locate_error", 1, target_skill_id=E02),
                        graded(on, ["2x-6=10", "2x=16", "x=8"], "verified_correct")]
    return case, on


@pytest.mark.parametrize("action,intent,problem_id,skill,relation,rule", [
    # Review: check_transfer sang bài cùng họ mẫu. Graph ghi "cross_family" cho mọi check_transfer vì
    # gate đã chặn trường hợp này; replay nhận nó thì tính thêm một observation độc lập.
    ("check_transfer", "independent_check", "E02-P002", E02, "cross_family", "G12_transfer_needs_new_family"),
    ("check_transfer", "independent_check", "A02-P002", A02, "cross_family", "G20_problem_outside_current_scope"),
    ("check_transfer", "independent_check", "E02-P003", A02, "cross_family", "G13_problem_skill_mismatch"),
    ("check_transfer", "independent_check", "E02-P001", E02, "cross_family", "G13_same_problem"),
    ("next_problem", "continue_practice", "N01-P001", N01, "cross_family", "G20_problem_outside_current_scope"),
    ("next_problem", "advance_difficulty", "E02-P002", E02, "initial", "G20_difficulty_not_higher"),
    ("next_problem", "advance_concept", "N01-P001", N01, "initial", "G19_advance_concept_requires_edge"),
])
def test_history_cannot_assign_a_problem_the_gate_forbids(source, action, intent, problem_id, skill, relation, rule):
    case, on = assisted_correct_on_e02(source)
    case["history"] += [tutor(on, action, intent, problem_id=problem_id, target_skill_id=skill),
                        graded(task(source, problem_id, relation), ["x=3"], "verified_correct")]
    with pytest.raises(ValueError, match=rule):
        replayed(source, 4)


def test_transfer_to_another_family_is_new_independent_evidence(source):
    case, on = assisted_correct_on_e02(source)
    state, trace = replayed(source, 4)
    assert [r.reason for r in trace] == ["not_target_evidence", "assisted"]
    assert state.skill(E02).independent_observations == 0 and state.skill(E02).assisted_correct == 1
    case["history"] += [tutor(on, "check_transfer", "independent_check", problem_id="E02-P003", target_skill_id=E02),
                        graded(task(source, "E02-P003", "cross_family"), ["x=5"], "verified_correct")]
    state, trace = replayed(source, 4)
    assert trace[-1].reason == "first_independent_verified" and state.skill(E02).independent_observations == 1
    assert state.attempted_problem_ids == ["E02-P001"]
    # Bài đã giao trong phiên không được giao lại làm bài mới (G13).
    back = state.current.model_dump(mode="json")
    case["history"] += [tutor(back, "next_problem", "continue_practice", problem_id="E02-P001", target_skill_id=E02),
                        student(task(source, "E02-P001", "cross_family"), "request_hint")]
    with pytest.raises(ValueError, match="G13_problem_already_attempted"):
        replayed(source, 4)


def test_a_new_task_needs_a_new_opportunity_id(source):
    case, on = assisted_correct_on_e02(source)
    case["history"] += [tutor(on, "check_transfer", "independent_check", problem_id="E02-P003", target_skill_id=E02),
                        student(task(source, "E02-P003", "cross_family", on["opportunity_id"]), "request_hint")]
    with pytest.raises(ValueError, match="reuse"):
        replayed(source, 4)


def test_the_graph_decides_how_the_next_problem_relates_to_the_last(source):
    case = source["scenarios"][4]
    on = case["history"][0]["task"]
    case["history"] += [tutor(on, "next_problem", "switch_problem", problem_id="E02-P002", target_skill_id=E02),
                        graded(task(source, "E02-P002", "initial"), ["x=3"], "verified_correct")]
    with pytest.raises(ValueError, match="task differs"):
        replayed(source, 4)


@pytest.mark.parametrize("hinted", [False, True])
def test_same_family_problem_counts_unless_the_family_was_assisted(source, hinted):
    """Protocol của Member 1: bài cùng họ mẫu chỉ bị loại khi trong phiên đã có bài cùng họ nhận trợ
    giúp. Graph gán "near_practice" chỉ vì cùng họ, nhãn đó không đủ để loại."""
    case = source["scenarios"][4]
    on = case["history"][0]["task"]
    if hinted:
        case["history"] += [tutor(on, "minimal_hint", "locate_error", 1, target_skill_id=E02),
                            student(on, "message", message="Em nghĩ thêm ạ")]
    case["history"] += [tutor(on, "next_problem", "switch_problem", problem_id="E02-P002", target_skill_id=E02),
                        graded(task(source, "E02-P002", "near_practice"), ["x=3"], "verified_correct")]
    state, trace = replayed(source, 4)
    if hinted:
        assert trace[-1].reason == "near_practice" and state.skill(E02).independent_observations == 0
    else:
        assert trace[-1].reason == "first_independent_verified"
        assert state.skill(E02).independent_observations == 1
    assert state.attempted_problem_ids == ["E02-P001"]


def test_prerequisite_and_return_follow_the_graph(source):
    parent = source["scenarios"][4]
    on = parent["history"][0]["task"]
    child = task(source, "A02-P001", "prerequisite")
    parent["history"] += [
        tutor(on, "backtrack", "review_prerequisite", 1, problem_id="A02-P001", target_skill_id=A02),
        graded(child, ["-6y-8"], "verified_correct")]
    state, trace = replayed(source, 4)
    assert len(state.return_stack) == 1 and state.current.concept_id == "A02"
    assert state.support == SupportState() and trace[-1].eligible
    # Làm đúng độc lập bài prerequisite: giả thuyết lỗi của skill đó được coi là đã kiểm tra.
    assert [h.status for h in state.hypotheses] == ["ruled_out"]

    back = {**on, "relation": "repeat"}
    parent["history"] += [
        tutor(child, "next_problem", "return_to_parent", problem_id="E02-P001", target_skill_id=E02),
        student(back, "message", message="Em quay lại bài cũ")]
    state, _ = replayed(source, 4)
    assert not state.return_stack and state.current.model_dump(mode="json") == back
    # Graph xóa bài làm cũ khi đổi bài và chỉ giữ lại mức hint của bài cha.
    assert state.latest_submission == [] and state.latest_assessment is None
    assert state.support == SupportState() and state.attempted_problem_ids == ["E02-P001", "A02-P001"]

    parent["history"][-1]["task"] = on  # tác giả ghi lại relation cũ của bài cha
    with pytest.raises(ValueError, match="task differs"):
        replayed(source, 4)


def test_backtrack_follows_a_direct_prerequisite_edge_of_the_registry(source):
    parent = source["scenarios"][4]
    on = parent["history"][0]["task"]
    # E02-P003 cùng concept với bài đang làm; N01 là prerequisite của A02, cách E02 hai tầng.
    for problem_id, skill in (("E02-P003", E02), ("N01-P001", N01)):
        parent["history"][1:] = [
            tutor(on, "backtrack", "review_prerequisite", problem_id=problem_id, target_skill_id=skill),
            student(task(source, problem_id, "prerequisite"), "request_hint")]
        with pytest.raises(ValueError, match="direct prerequisite"):
            replayed(source, 4)


def test_return_to_parent_needs_the_problem_on_the_return_stack(source):
    case, on = assisted_correct_on_e02(source)
    case["history"] += [tutor(on, "next_problem", "return_to_parent", problem_id="A02-P001", target_skill_id=A02),
                        student(task(source, "A02-P001", "repeat"), "request_hint")]
    with pytest.raises(ValueError, match="G09_return_target_mismatch"):
        replayed(source, 4)


@pytest.mark.parametrize("field", ["p_mastery", "skills", "readiness"])
def test_authoring_cannot_set_computed_state(source, field):
    source["scenarios"][0][field] = 0.99
    with pytest.raises(ValueError):
        dataset(source)


# --------------------------------------------------------------------------- chia nhóm và độ phủ

def test_transitive_grouping_links_original_family_and_history(source):
    # A--B qua lịch sử, B--C qua họ mẫu. A và C cũng phải cùng split.
    a, b, c = source["scenarios"][0], source["scenarios"][2], source["scenarios"][4]
    for case in source["scenarios"]:
        case["split"] = None
    a["history_group_id"] = b["history_group_id"]
    family = b["history"][0]["task"]["template_family_id"]
    c["history"][0]["task"]["template_family_id"] = family
    for p in source["problems"]:
        if p["problem"]["problem_id"] == c["history"][0]["task"]["problem_id"]:
            p["problem"]["template_family_id"] = family
    result = grouped_splits(dataset(source), "seed")
    assert result[a["scenario_id"]] == result[b["scenario_id"]] == result[c["scenario_id"]]
    assert result == grouped_splits(dataset(source), "seed")


def test_already_used_dev_group_cannot_be_moved_into_test(source):
    source["scenarios"][1]["split"] = "test"
    with pytest.raises(ValueError, match="Conflicting splits"):
        build(dataset(source))


def test_unassigned_groups_put_every_concept_in_both_splits(source):
    # Mỗi concept có hai nhóm độc lập (hai họ mẫu). Chỉ cân theo số ca thì một concept có thể nằm
    # trọn trong dev; plan §12 cần ít nhất 2 ca test/concept.
    def moved(case, problem_id):
        new = copy.deepcopy(case)
        on = task(source, problem_id)
        new.update(scenario_id=f"{case['scenario_id']}-B", history_group_id=f"{case['history_group_id']}-B",
                   session_id=str(uuid4()))
        for event in new["history"]:
            event.update(turn_id=str(uuid4()), request_id=str(uuid4()), task=on)
        return new

    originals = [source["scenarios"][i] for i in (0, 2, 4)]
    source["scenarios"] = originals + [moved(case, problem_id) for case, problem_id in
                                       zip(originals, ("N01-EX-P002", "A02-P002", "E02-P003"))]
    for case in source["scenarios"]:
        case["split"] = None
    data = dataset(source)
    for seed in map(str, range(12)):
        result = grouped_splits(data, seed)
        splits = {}
        for case in data.scenarios:
            splits.setdefault(case.history[-1].task.concept_id, set()).add(result[case.scenario_id][0])
        assert splits == {"N01": {"dev", "test"}, "A02": {"dev", "test"}, "E02": {"dev", "test"}}, seed


def test_coverage_includes_uncovered_concepts_and_separate_sources(source):
    sets, report, matrix = build(dataset(source))
    assert len(matrix) == 40 and len(sets["dev"].scenarios) == 6 and not sets["test"].scenarios
    assert report["coverage_warnings"]
    assert next(r for r in matrix if r["concept_id"] == "F10")["test"] == 0
    assert report["splits"]["dev"]["sources"] == {"synthetic_authoring": 6}
    assert report["splits"]["dev"]["label_statuses"] == {"draft": 6}


def test_graph_context_comes_from_the_registry(source):
    sets, report, _ = build(dataset(source))
    graph = KnowledgeGraph.load()
    registry = {e.edge_id: (e.source_concept_id, e.target_concept_id) for e in graph.registry.edges}
    for case in sets["dev"].scenarios:
        context, concept = case.context, case.state.current.concept_id
        assert context.kg_source == "registry_file" and context.graph_version == graph.version
        assert all(registry[e.edge_id] == (e.source_concept_id, e.target_concept_id) for e in context.edges)
        assert {e.target_concept_id for e in context.edges if e.depth == 1} <= {concept}
    by_id = {case.scenario_id: case.context for case in sets["dev"].scenarios}
    assert by_id["AD-EX-05"].prerequisite_chain(["PRE-A02-E02"], "E02") == {A02: 1}
    assert report["kg_include_drafts"] is True
    # Cạnh soạn tay bị từ chối: có thể lệch registry.
    source["scenarios"][4]["context"]["edges"] = [by_id["AD-EX-05"].edges[0].model_dump(mode="json")]
    with pytest.raises(ValueError, match="registry"):
        build(dataset(source))


def test_export_load_and_ablation_through_normal_cli(tmp_path, source):
    path = tmp_path / "input.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    out = tmp_path / "dataset"
    assert main(["--input", str(path), "--out", str(out)]) == 0
    assert (out / "coverage.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    scenarios = load_scenarios(path=out / "dev.json")
    assert len(scenarios) == 6 and scenarios[0].expected_rule_action is None
    runs = tmp_path / "runs"
    assert ablation_main(["--scenario-set", str(out / "dev.json"), "--configs", "rule_policy", "no_kg",
                          "--out", str(runs)]) == 0
    summary = json.loads((runs / "summary.json").read_text(encoding="utf-8"))
    assert summary["run"]["scenario_split"] == "dev"
    assert summary["run"]["dataset_version"] == source["dataset_version"]
    assert summary["configurations"]["rule_policy"]["runs"] == 6
    with pytest.raises(SystemExit):
        main(["--input", str(path), "--out", str(out)])


@pytest.mark.parametrize("change", ["wrong_prompt", "wrong_skill", "labels_overlap", "unknown_skill"])
def test_inconsistent_metadata_and_labels_fail_before_export(source, change):
    case = source["scenarios"][0]
    if change == "wrong_prompt":
        case["context"]["current_problem_prompt"] = "Another problem"
    elif change == "wrong_skill":
        source["problems"][0]["problem"]["target_skill_id"] = "SK-E02-SOLVE"
    elif change == "labels_overlap":
        case["labels"]["forbidden_actions"] = case["labels"]["acceptable_actions"]
    else:
        case["history"][0]["assessment"]["primary_skill_id"] = "SK-NOT-IN-REGISTRY"
    with pytest.raises(ValueError):
        build(dataset(source))
