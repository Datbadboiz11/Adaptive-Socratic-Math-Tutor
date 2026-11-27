"""Bộ tình huống dev trên bài đã duyệt của Member 2 (research/scenarios/approved_dev.py)."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from research.agent.scenarios import load_scenarios  # noqa: E402
from research.evaluation.run_ablation import Models, run_turn  # noqa: E402
from research.scenarios import approved_dev  # noqa: E402
from research.scenarios.build import build  # noqa: E402
from research.scenarios.replay import replay  # noqa: E402

CONTENT = approved_dev.CONTENT


@pytest.fixture(scope="module")
def data():
    return approved_dev.dataset()


@pytest.fixture(scope="module")
def dev_file(data, tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("approved") / "dev.json"
    path.write_text(build(data)[0]["dev"].model_dump_json(), encoding="utf-8")
    return path


def test_the_committed_file_is_what_the_source_generates():
    assert approved_dev.main(["--check"]) == 0


def test_every_case_runs_on_approved_problems_and_covers_every_concept(data):
    assert len(data.problems) == 78 and {p.problem.problem_id for p in data.problems} == set(CONTENT.problems)
    assert all(p.prompt == CONTENT.problem_prompt(p.problem.problem_id) for p in data.problems)
    concepts = {s.history[-1].task.concept_id for s in data.scenarios}
    assert concepts == {p.ref.concept_id for p in CONTENT.problems.values()}
    assert all(s.split == "dev" and s.labels.review_status == "draft" and s.labels.author == "ai_draft"
               for s in data.scenarios)


def test_every_submission_is_graded_by_the_system_validator(data):
    """Assessment trong lịch sử phải đúng là thứ validator chấm ra cho bài làm đó."""
    from app import math_validator
    from app.agent.validator_analyzer import ValidatorAnalyzer
    from types import SimpleNamespace

    analyzer = ValidatorAnalyzer(CONTENT.validator_task, validate=math_validator.validate)
    submissions = [e for s in data.scenarios for e in s.history if e.kind == "submit"]
    assert len(submissions) == 44
    for event in submissions:
        view = analyzer(SimpleNamespace(current=event.task), list(event.submission))
        assert (view.assessment_status, view.unfinished, view.final_answer_only) == (
            event.assessment.assessment_status, event.assessment.unfinished, event.assessment.final_answer_only)


def test_replay_follows_the_web_rule_and_creates_no_bkt_evidence(data):
    for draft in data.scenarios:
        state, trace = replay(draft, data, approved_dev.KG)
        assert all(k.independent_observations == 0 and k.p_mastery == 0.2 for k in state.skills), draft.scenario_id
        assert all(r.reason == "not_target_evidence" for r in trace), draft.scenario_id
        assert not state.readiness.ready_to_advance


def test_authoring_stops_when_the_validator_disagrees_with_the_author():
    s = approved_dev.session("AP-X", approved_dev.P("N02", 1))
    with pytest.raises(ValueError, match="graded"):
        s.work(["-52"], "verified_correct")


def test_context_keeps_the_kb_rule_against_same_family_examples(data):
    for draft in data.scenarios:
        current = CONTENT.problems[draft.history[-1].task.problem_id]
        for item in draft.context.retrieved:
            chunk = next(c for c in CONTENT.chunks if c.content.content_id == item.content_id)
            if item.content_type == "example":
                assert chunk.family_id != current.ref.template_family_id, draft.scenario_id


def test_rule_policy_runs_on_the_set_and_new_problems_keep_their_statement(dev_file):
    scenarios = {sc.id: sc for sc in load_scenarios(path=dev_file)}
    for sid in ("AP-20", "AP-24", "AP-04"):
        row = run_turn(scenarios[sid], "rule_policy", Models.fake())
        assert row["error"] is None and row["final_acceptable"] is True, sid
        if row["problem_id"]:
            assert CONTENT.problem_prompt(row["problem_id"]) in row["message"], sid


# ---------------------------------------------------------------- verifier: đề chép nguyên văn

def _input(current, new):
    from app.agent.decision import DecisionProposal
    from app.generation.contracts import ResponseInput

    return ResponseInput(decision=DecisionProposal.model_construct(action="next_problem", problem_id=new),
                         problem_id=current, problem_prompt=CONTENT.problem_prompt(current),
                         new_problem_prompt=CONTENT.problem_prompt(new), content=(), assessment=None, submission=(),
                         student_message=None)


def test_quoting_a_new_problem_statement_is_not_an_answer_leak():
    """Đề E06-P-03 chứa "= 0", trùng đáp án biệt thức 0: chép đề không lộ gì, nói biệt thức bằng 0 thì lộ."""
    from app.agent.approved_content import any_answer_key
    from app.generation.contracts import Check
    from app.generation.verifier import ResponseVerifier

    verifier = ResponseVerifier(any_answer_key)
    current, new = approved_dev.P("E06", 1), approved_dev.P("E06", 3)
    inp = _input(current, new)
    prompt = CONTENT.problem_prompt(new)
    assert verifier.answer_check(inp, f"Em làm tiếp bài này nhé: {prompt}") is None
    assert verifier.answer_check(inp, f"Em làm tiếp bài này nhé: {prompt} Biệt thức bằng 0.") == Check.ANSWER_LEAK
    assert verifier.answer_check(inp, "Gợi ý: nghiệm là -5/3.") == Check.ANSWER_LEAK


def test_answer_keys_cover_demo_and_approved_problems():
    from app.agent.approved_content import any_answer_key, any_problem_prompt, reference_answers

    assert any_answer_key("E02-P001") is not None and any_problem_prompt("E02-P001")
    assert any_answer_key(approved_dev.P("N02", 1)).final_answers == ("52",)
    assert any_answer_key(approved_dev.P("E06", 5)) is None
    assert reference_answers(approved_dev.P("E06", 5)) == ["-56;{}"]
    assert any_answer_key("NOT-A-PROBLEM") is None and reference_answers("NOT-A-PROBLEM") == []


# ---------------------------------------------------------------- nhãn khớp gate, context theo cấu hình, phiếu chấm

def test_labels_never_accept_an_action_the_gate_always_rejects(dev_file):
    """G01: bài nộp chưa chấm được chỉ nhận clarify/end_session. G14: xin tạm dừng chỉ nhận end_session."""
    for sc in load_scenarios(path=dev_file):
        s = sc.state
        status = s.latest_assessment.assessment_status if s.latest_assessment else None
        if s.trigger == "submit" and status in {"unverified", "needs_clarification"}:
            assert set(sc.acceptable_actions) <= {"clarify", "end_session"}, sc.id
        if s.trigger == "pause":
            assert set(sc.acceptable_actions) == {"end_session"}, sc.id


@pytest.mark.parametrize("configuration", ["full", "no_kg", "no_rag"])
def test_runner_context_matches_what_approved_tools_return(dev_file, configuration):
    """Mỗi cấu hình nhận đúng bài ứng viên và nội dung mà ``ApprovedTools`` thật trả về: No-KG không được
    giữ bài của concept mà chỉ KG mới tìm ra (ví dụ E03 khi đang làm A01)."""
    from app.agent.approved_content import ApprovedTools
    from app.agent.decision import DecisionConfig, ExperimentConfiguration
    from research.evaluation.run_ablation import project_context

    tools = ApprovedTools(CONTENT, approved_dev.KG)
    config = DecisionConfig(configuration=configuration, policy_version="rule-policy-0.1.0")
    widened = 0
    for sc in load_scenarios(path=dev_file):
        runner = project_context(sc.context, sc.state, ExperimentConfiguration(configuration))
        real = tools(sc.state, config)
        assert [p.problem_id for p in runner.problems] == [p.problem_id for p in real.problems], sc.id
        assert [c.content_id for c in runner.retrieved] == [c.content_id for c in real.retrieved], sc.id
        assert (runner.kg_enabled, runner.rag_enabled) == (real.kg_enabled, real.rag_enabled)
        widened += len({p.concept_id for p in sc.context.problems}) > 1
    assert widened >= 6  # các ca mà Full có thêm bài của concept khác nhờ KG


def test_a_rating_packet_builds_from_approved_set_outputs(dev_file, tmp_path):
    from research.evaluation.build_rating_packet import build_packet, write_packet
    from research.evaluation.rubric import SystemOutput

    scenarios = {sc.id: sc for sc in load_scenarios(path=dev_file)}
    outputs = []
    for sid in ("AP-01", "AP-26"):
        for configuration in ("full", "no_kg"):
            row = run_turn(scenarios[sid], configuration, Models.fake())
            outputs.append(SystemOutput(scenario_id=sid, system=configuration, action=row["final_action"],
                                        intent=row["final_intent"], hint_level=row["hint_level"],
                                        problem_id=row["problem_id"], message=row["message"],
                                        response_source=row["response_source"]))
    with pytest.raises(KeyError, match="unknown scenario"):
        build_packet(outputs, ["r1"], seed=1, source="ap", packet_id="p")  # bộ mặc định không có AP-*
    packet = build_packet(outputs, ["r1", "r2"], seed=1, source="ap", packet_id="p", compare=[("full", "no_kg")],
                          scenario_set=dev_file)
    assert len(packet.items) == 4 and len(packet.key.pairs) == 2
    assert packet.contexts["AP-26"].reference_answers == ["[-7,+inf)"]  # nguyên đáp án, không chỉ "-7"
    assert packet.contexts["AP-01"].problem == CONTENT.problem_prompt(approved_dev.P("N02", 1))
    write_packet(packet, tmp_path / "p")
    assert (tmp_path / "p" / "key.json").exists() and (tmp_path / "p" / "raters" / "r1").is_dir()


def test_packet_rejects_another_scenario_set(dev_file, tmp_path):
    """Cùng mã AP-01 nhưng bài nộp đổi từ 52 thành -52: không được ghép câu đã chạy trên 52 vào bộ đó."""
    import json

    from research.evaluation.build_rating_packet import main as build_main
    from research.evaluation.run_ablation import main as run_main

    out = tmp_path / "run"
    assert run_main(["--llm", "fake", "--scenario-set", str(dev_file), "--scenarios", "AP-01", "--out", str(out)]) == 0
    data = json.loads(dev_file.read_text(encoding="utf-8"))
    case = next(s for s in data["scenarios"] if s["scenario_id"] == "AP-01")
    assert case["state"]["latest_submission"] == ["52"]
    case["state"]["latest_submission"] = ["-52"]
    other = tmp_path / "other.json"
    other.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    args = ["--outputs", str(out / "outputs.jsonl"), "--raters", "r1"]
    for wrong in (["--scenario-set", str(other)], []):  # bộ khác cùng mã, hoặc quên --scenario-set
        with pytest.raises(SystemExit) as error:
            build_main([*args, *wrong, "--out", str(tmp_path / "bad")])
        assert error.value.code == 2 and not (tmp_path / "bad").exists()
    assert build_main([*args, "--scenario-set", str(dev_file), "--out", str(tmp_path / "ok")]) == 0
    (out / "summary.json").unlink()
    with pytest.raises(SystemExit):  # không còn hash thì không biết câu chạy trên bộ nào
        build_main([*args, "--scenario-set", str(dev_file), "--out", str(tmp_path / "nohash")])


def test_an_older_ap_run_with_only_the_set_hash_still_builds_a_packet(dev_file, tmp_path):
    """Lô AP chạy trước khi có dấu vân tay từng ca chỉ ghi ``scenario_set_sha256``: đúng file thì tạo được
    phiếu; file khác hoặc thiếu --scenario-set thì không."""
    import json

    from research.evaluation.build_rating_packet import load_outputs, verify_outputs
    from research.evaluation.run_ablation import main as run_main

    out = tmp_path / "run"
    assert run_main(["--llm", "fake", "--scenario-set", str(dev_file), "--scenarios", "AP-01", "AP-26",
                     "--configs", "full", "no_kg", "--out", str(out)]) == 0
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    del summary["run"]["scenario_fingerprints"]
    assert summary["run"]["scenario_set_sha256"]
    (out / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    outputs = load_outputs(out / "outputs.jsonl")
    verify_outputs(outputs, out, dev_file)
    other = tmp_path / "other.json"
    other.write_bytes(dev_file.read_bytes() + b"\n")
    for scenario_set, message in ((other, "is not the scenario set"), (None, "pass that file")):
        with pytest.raises(ValueError, match=message):
            verify_outputs(outputs, out, scenario_set)
