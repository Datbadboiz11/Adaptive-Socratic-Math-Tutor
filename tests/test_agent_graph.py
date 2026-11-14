"""Khung LangGraph: luồng nhiều lượt, checkpoint/resume, idempotency, fallback và ablation."""
from pathlib import Path
import sys
import threading
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.agent.decide import ProposalOutcome, RulePolicyProposer  # noqa: E402
from app.agent.decision import DecisionConfig, DecisionProposal, DecisionSource  # noqa: E402
from app.agent.gate import policy_gate  # noqa: E402
from app.agent.graph import (  # noqa: E402
    WORKFLOW_VERSION, InProcessSessionLocks, Services, SessionClosed, TurnInProgress, TurnInput, TutorEngine,
    TutorReply,
)
from app.agent.kg_tool import KGTool  # noqa: E402
from app.agent.fakes import ScriptedProposer  # noqa: E402
from app.agent.stubs import StubTools, TemplateGenerator  # noqa: E402

WRONG = ["2x - 3 = 10", "2x = 13", "x = 6.5"]
RIGHT = ["2x - 6 = 10", "2x = 16", "x = 8"]


def config(name="rule_policy"):
    return DecisionConfig(configuration=name, policy_version="rule-policy-0.1.0")


def run(engine, sid, trigger, steps=(), request_id=None) -> TutorReply:
    return engine.turn(sid, TurnInput(request_id=request_id or uuid4(), trigger=trigger, steps=list(steps)))


@pytest.fixture
def engine():
    return TutorEngine(config())


def test_full_session_flow(engine):
    sid = engine.start("demo-a", "E02-P001").session_id
    flow = [
        (("submit", WRONG), "diagnose"),
        (("submit", WRONG), "conceptual_question"),
        (("request_hint",), "minimal_hint"),
        (("request_hint",), "scaffold"),
        (("submit", WRONG), "backtrack"),
        (("submit", ["-6y - 8"]), "next_problem"),
        (("submit", RIGHT), "check_transfer"),
    ]
    for args, expected in flow:
        reply = run(engine, sid, *args)
        assert reply.action == expected, (args, reply)
    state = engine.state(sid)
    assert state.current.problem_id == "E02-P003" and state.current.relation == "cross_family"
    assert state.return_stack == [] and state.attempted_problem_ids == ["E02-P001", "A02-P001"]
    decisions = engine.decisions(sid)
    assert len(decisions) == len(flow) and all(d.final_source == DecisionSource.RULE_POLICY for d in decisions)
    assert [d.state_version for d in decisions] == list(range(1, len(flow) + 1))
    # KG thật: quyết định backtrack trích cạnh registry, log giữ ứng viên và nguồn trả lời.
    back = decisions[4]
    assert back.final.edge_ids == ["PRE-A02-E02"] and back.kg_source == "registry_file"
    assert {"PRE-A02-E02", "PRE-A03-E02", "PRE-E01-E02"} <= set(back.candidate_edge_ids)
    assert back.graph_version and back.graph_version.startswith("0.1.0+")


def test_bkt_only_updates_on_independent_first_attempt(engine):
    sid = engine.start("demo-a", "E02-P001").session_id
    run(engine, sid, "submit", WRONG)
    first = engine.state(sid).skill("SK-A02-DISTRIBUTE")
    assert first.independent_observations == 1
    run(engine, sid, "submit", WRONG)  # cùng opportunity: không thêm observation
    run(engine, sid, "request_hint")
    run(engine, sid, "submit", RIGHT)  # đúng sau hỗ trợ: chỉ tăng assisted_correct
    state = engine.state(sid)
    assert state.skill("SK-A02-DISTRIBUTE") == first
    assert state.skill("SK-E02-SOLVE").independent_observations == 0
    assert state.skill("SK-E02-SOLVE").assisted_correct == 1


def test_duplicate_request_is_not_processed_twice(engine):
    sid = engine.start("demo-a", "E02-P001").session_id
    request_id = uuid4()
    first = run(engine, sid, "submit", WRONG, request_id=request_id)
    second = run(engine, sid, "submit", WRONG, request_id=request_id)
    assert second.duplicate and second.decision_id == first.decision_id
    assert engine.state(sid).state_version == first.state_version
    assert len(engine.decisions(sid)) == 1
    assert engine.state(sid).skill("SK-A02-DISTRIBUTE").independent_observations == 1


def test_old_request_replayed_after_other_turns_returns_stored_reply(engine):
    # Review P1: A → B → gửi lại A từng bị xử lý như lượt mới và chấm theo bài mới.
    sid = engine.start("demo-a", "E02-P001").session_id
    a = uuid4()
    first = run(engine, sid, "submit", RIGHT, request_id=a)
    run(engine, sid, "request_hint")
    replay = run(engine, sid, "submit", RIGHT, request_id=a)
    assert replay.duplicate and replay.decision_id == first.decision_id and replay.message == first.message
    assert len(engine.decisions(sid)) == 2


class FailOnce:
    """Bọc một service để nó raise đúng một lần."""

    def __init__(self, inner):
        self.inner, self.failed = inner, False

    def __call__(self, *args):
        if not self.failed:
            self.failed = True
            raise RuntimeError("down")
        return self.inner(*args)


class FlakyGenerator(TemplateGenerator):
    failed = False

    def __call__(self, state, p, ctx):
        if not self.failed:
            self.failed = True
            raise RuntimeError("generator down")
        return super().__call__(state, p, ctx)


def test_retry_after_mid_turn_failure_resumes_without_reanalysis():
    # Review P1: retry chạy lại analyze nên một bài nộp thành hai bằng chứng.
    eng = TutorEngine(config(), Services(generator=FlakyGenerator()))
    sid = eng.start("demo-a", "E02-P001").session_id
    request = TurnInput(request_id=uuid4(), trigger="submit", steps=WRONG)
    with pytest.raises(RuntimeError, match="generator down"):
        eng.turn(sid, request)
    with pytest.raises(TurnInProgress):  # request khác phải đợi lượt dở dang xong
        run(eng, sid, "request_hint")
    reply = eng.turn(sid, request)
    state = eng.state(sid)
    assert [(h.status, len(h.evidence_ids)) for h in state.hypotheses] == [("suspected", 1)]
    assert state.support.no_progress_turns == 1
    assert state.skill("SK-A02-DISTRIBUTE").independent_observations == 1
    assert len(eng.decisions(sid)) == 1 and reply.action == "diagnose"
    assert eng.turn(sid, request).duplicate


def test_tool_failure_degrades_instead_of_breaking_turn():
    eng = TutorEngine(config(), Services(tools=FailOnce(StubTools())))
    sid = eng.start("demo-a", "E02-P001").session_id
    reply = run(eng, sid, "submit", WRONG)
    record = eng.decisions(sid)[0]
    assert record.tool_errors == ["RuntimeError"] and record.tool_calls_used == 0
    assert reply.action == "diagnose"
    state = eng.state(sid)
    assert [(h.status, len(h.evidence_ids)) for h in state.hypotheses] == [("suspected", 1)]


class DownNeo4j:
    def neighbourhood(self, concept_id, *, include_drafts=False):
        raise ConnectionError("neo4j down")


def test_neo4j_outage_falls_back_to_registry_without_losing_kg():
    tools = StubTools(kg=KGTool(neo4j=DownNeo4j(), include_drafts=True))
    eng = TutorEngine(config(), Services(tools=tools))
    sid = eng.start("demo-a", "E02-P001").session_id
    for args in [("submit", WRONG), ("submit", WRONG), ("request_hint",), ("request_hint",)]:
        run(eng, sid, *args)
    assert run(eng, sid, "submit", WRONG).action == "backtrack"  # vẫn backtrack được nhờ bản đọc từ file
    records = eng.decisions(sid)
    assert records[0].tool_errors == ["kg_neo4j:ConnectionError"] and records[0].tool_calls_used == 3
    assert all(r.kg_source == "registry_file" for r in records)
    assert records[1].tool_errors == []  # đang nghỉ gọi Neo4j nên không lặp lại lỗi mỗi lượt


def test_approved_only_kg_gives_no_edges_while_registry_is_draft():
    eng = TutorEngine(config(), Services(tools=StubTools(kg=KGTool())))
    sid = eng.start("demo-a", "E02-P001").session_id
    for args in [("submit", WRONG), ("submit", WRONG), ("request_hint",), ("request_hint",)]:
        run(eng, sid, *args)
    assert run(eng, sid, "submit", WRONG).action == "scaffold"
    assert all(not d.candidate_edge_ids for d in eng.decisions(sid))


PROBE_FLOW = [("submit", ["7x = 15"]), ("submit", ["7x = 15"]), ("request_hint",), ("request_hint",),
              ("submit", ["7x = 15"])]


def probing_engine(checker=None):
    """Đưa phiên tới lúc tutor hỏi kiểm tra prerequisite A02 (lỗi thuộc skill giải, chưa có bằng
    chứng nào về skill nền)."""
    eng = TutorEngine(config(), Services(probe_checker=checker) if checker else None)
    sid = eng.start("demo-a", "E02-P003").session_id
    replies = [run(eng, sid, *args) for args in PROBE_FLOW]
    assert (replies[-1].action, replies[-1].intent) == ("diagnose", "probe_prerequisite")
    assert [(q.skill_id, q.status) for q in eng.state(sid).probes] == [("SK-A02-DISTRIBUTE", "pending")]
    return eng, sid


def test_asking_a_probe_is_not_evidence_for_backtrack():
    # Review P1: tutor hỏi kiểm tra A02, học sinh chỉ xin gợi ý thì từng bị backtrack ngay.
    eng, sid = probing_engine()
    reply = run(eng, sid, "request_hint")
    assert reply.action == "scaffold"
    assert eng.state(sid).probes[0].status == "pending" and eng.state(sid).return_stack == []


def test_unverified_probe_answer_is_not_evidence():
    eng, sid = probing_engine()  # bộ xác minh mặc định chưa kết luận được gì
    reply = engine_message(eng, sid, "Em nhân 2 với x thôi ạ.")
    assert reply.action != "backtrack"
    answered = eng.state(sid).probes[0]
    assert answered.status == "unverified" and answered.answer_turn_id is not None


def test_verified_failed_probe_allows_backtrack():
    seen = []

    def checker(state, probe, message):
        seen.append((probe.skill_id, message))
        return "not_demonstrated"

    eng, sid = probing_engine(checker)
    reply = engine_message(eng, sid, "Em không nhớ quy tắc ạ.")
    assert reply.action == "backtrack" and seen == [("SK-A02-DISTRIBUTE", "Em không nhớ quy tắc ạ.")]
    record = eng.decisions(sid)[-1]
    assert record.final.edge_ids == ["PRE-A02-E02"] and "probe_failed" in record.final.reason
    assert eng.state(sid).probes == []  # đổi bài thì xóa câu hỏi kiểm tra của bài cũ


def test_demonstrated_probe_blocks_backtrack_and_reprobe():
    eng, sid = probing_engine(lambda state, probe, message: "demonstrated")
    reply = engine_message(eng, sid, "Nhân 2 với cả x và 3 ạ.")
    assert reply.action != "backtrack" and reply.intent != "probe_prerequisite"


def engine_message(eng, sid, text):
    return eng.turn(sid, TurnInput(request_id=uuid4(), trigger="message", message=text))


def test_new_engine_reads_shared_checkpointer():
    """Engine mới đọc tiếp phiên qua checkpointer dùng chung (cùng tiến trình).

    Không chứng minh khởi động lại tiến trình thật: InMemorySaver mất dữ liệu khi tắt.
    Việc đó cần checkpointer bền (PostgreSQL) và test bằng hai tiến trình riêng."""
    saver = InMemorySaver()
    sid = TutorEngine(config(), checkpointer=saver).start("demo-a", "E02-P001").session_id
    run(TutorEngine(config(), checkpointer=saver), sid, "submit", WRONG)
    second = TutorEngine(config(), checkpointer=saver)
    reply = run(second, sid, "submit", WRONG)
    assert reply.action == "conceptual_question"  # nhớ hypothesis và lượt diagnose trước đó
    assert len(second.decisions(sid)) == 2
    with pytest.raises(KeyError):
        TutorEngine(config(), checkpointer=InMemorySaver()).state(sid)


def test_pause_resume_and_completed_session(engine):
    sid = engine.start("demo-a", "E02-P001").session_id
    paused = run(engine, sid, "pause")
    assert (paused.status, paused.next_actions) == ("paused", ["resume"])
    resumed = run(engine, sid, "resume")
    assert resumed.status == "active" and resumed.intent == "restate_task"
    assert engine.state(sid).latest_assessment is None  # tạm dừng không bị ghi thành câu trả lời sai


def test_completed_session_rejects_turns():
    script = ScriptedProposer([{"action": "end_session", "intent": "session_goal_met", "reason": "Xong."}])
    eng = TutorEngine(config("full"), Services(proposer=script))
    sid = eng.start("demo-a", "E02-P001").session_id
    assert run(eng, sid, "message").status == "completed"
    with pytest.raises(SessionClosed):
        run(eng, sid, "submit", RIGHT)


def test_unclear_input_asks_to_clarify_without_observation(engine):
    sid = engine.start("demo-a", "E02-P001").session_id
    reply = run(engine, sid, "submit", ["x là bao nhiêu ạ???"])
    assert reply.action == "clarify"
    assert engine.state(sid).skills == []


@pytest.mark.parametrize("item,reason", [
    ({"action": "next_problem", "intent": "advance_concept", "target_skill_id": "SK-E03-PRIMARY",
      "evidence": [], "problem_id": "E03-P001", "reason": "x"}, "agent_schema_error"),
    (TimeoutError(), "agent_timeout"),
    (RuntimeError("boom"), "agent_error"),
])
def test_agent_failures_fall_back(item, reason):
    eng = TutorEngine(config("full"), Services(proposer=ScriptedProposer([item])))
    sid = eng.start("demo-a", "E02-P001").session_id
    reply = run(eng, sid, "submit", WRONG)
    record = eng.decisions(sid)[0]
    assert record.fallback_reason == reason and record.final_source == DecisionSource.FALLBACK
    assert reply.action == "diagnose"


def test_agent_proposal_rejected_by_gate_is_logged():
    bad = {"action": "next_problem", "intent": "advance_concept", "target_skill_id": "SK-E03-PRIMARY",
           "evidence": [{"kind": "student_message", "id": "unknown"}], "problem_id": "E03-P001", "reason": "x"}
    eng = TutorEngine(config("full"), Services(proposer=ScriptedProposer([bad])))
    sid = eng.start("demo-a", "E02-P001").session_id
    run(eng, sid, "submit", WRONG)
    record = eng.decisions(sid)[0]
    assert record.gate.status == "rejected"
    assert {"G03", "G06", "G07"} <= {code[:3] for code in record.gate.violated_rules}
    assert record.proposed.action == "next_problem" and record.final.action == "diagnose"


class LeakyGenerator(TemplateGenerator):
    def __call__(self, state, p, ctx):
        return "Đáp án là x = 8 nhé.", "llm"


def test_answer_leak_is_replaced():
    eng = TutorEngine(config(), Services(generator=LeakyGenerator()))
    sid = eng.start("demo-a", "E02-P001").session_id
    reply = run(eng, sid, "submit", WRONG)
    assert "x = 8" not in reply.message and reply.response_source == "template_fallback"
    assert eng.decisions(sid)[0].regenerations_used == 1


def test_agent_cannot_advance_concept_without_kg_edge():
    # Review P1: No-KG, Agent đề xuất chuyển E02 → A02 không trích cạnh từng được gate chấp nhận.
    jump = {"action": "next_problem", "intent": "advance_concept", "target_skill_id": "SK-A02-DISTRIBUTE",
            "problem_id": "A02-P001", "reason": "Chuyển concept."}

    def proposer(state, ctx):
        evidence = [{"kind": "assessment", "id": str(state.latest_assessment.assessment_id)}]
        ready = state.model_copy(update={"readiness": state.readiness.model_copy(
            update={"ready_to_advance": True, "unmet": []})})
        proposal = DecisionProposal.model_validate({**jump, "evidence": evidence})
        assert policy_gate(ready, proposal, ctx).status == "rejected"  # kể cả khi readiness hợp lệ
        return ProposalOutcome(proposal, DecisionSource.AGENT)

    eng = TutorEngine(config("no_kg"), Services(proposer=proposer))
    sid = eng.start("demo-a", "E02-P001").session_id
    reply = run(eng, sid, "submit", RIGHT)
    record = eng.decisions(sid)[0]
    assert "G19_advance_concept_requires_kg" in record.gate.violated_rules
    assert record.final_source == DecisionSource.FALLBACK and eng.state(sid).current.concept_id == "E02"
    assert reply.intent != "advance_concept"


def test_no_kg_cannot_backtrack():
    eng = TutorEngine(config("no_kg"), Services(proposer=ScriptedProposer([None] * 10)))
    sid = eng.start("demo-a", "E02-P001").session_id
    for args in [("submit", WRONG), ("submit", WRONG), ("request_hint",), ("request_hint",)]:
        run(eng, sid, *args)
    reply = run(eng, sid, "submit", WRONG)
    assert reply.action == "scaffold"
    assert all(not d.final.edge_ids for d in eng.decisions(sid))


def test_no_bkt_hides_mastery_from_policy_only():
    script = ScriptedProposer([None] * 3)
    eng = TutorEngine(config("no_bkt"), Services(proposer=script))
    sid = eng.start("demo-a", "E02-P001").session_id
    run(eng, sid, "submit", WRONG)
    run(eng, sid, "submit", WRONG)
    assert all(s.mastery_view == "none" for s in script.seen_states)
    assert all(k.p_mastery is None for s in script.seen_states for k in s.skills)
    assert engine_skill(eng, sid).p_mastery is not None  # BKT vẫn chạy để báo cáo
    assert eng.state(sid).mastery_view == "bkt"


def engine_skill(eng, sid):
    return eng.state(sid).skill("SK-A02-DISTRIBUTE")


# ---------------------------------------------------------------- Nhất quán lượt khi gửi đồng thời (FR-11)

class _BarrierProposer:
    """Giữ cả hai luồng ở bước đề xuất cho tới khi cùng tới nơi (nếu không có khóa) hoặc hết giờ."""

    def __init__(self, parties=2, timeout=0.5):
        self.barrier = threading.Barrier(parties, timeout=timeout)
        self.calls = 0

    def __call__(self, state, ctx):
        self.calls += 1
        try:
            self.barrier.wait()
        except threading.BrokenBarrierError:
            pass
        return RulePolicyProposer()(state, ctx)


def _concurrently(*calls):
    out, errors = [], []

    def run(fn):
        try:
            out.append(fn())
        except Exception as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=run, args=(fn,)) for fn in calls]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return out, errors


def test_concurrent_same_request_is_processed_once():
    # Review: hai lời gọi cùng request_id từng cho hai decision_id khác nhau, cùng state_version.
    proposer = _BarrierProposer()
    engine = TutorEngine(config(), Services(proposer=proposer), locks=InProcessSessionLocks())
    sid = engine.start("demo-a", "E02-P001").session_id
    turn = TurnInput(request_id=uuid4(), trigger="submit", steps=WRONG)
    replies, errors = _concurrently(lambda: engine.turn(sid, turn), lambda: engine.turn(sid, turn))
    assert not errors and proposer.calls == 1
    assert len({r.decision_id for r in replies}) == 1 and sorted(r.duplicate for r in replies) == [False, True]
    assert len(engine.decisions(sid)) == 1 and engine.state(sid).state_version == 2


def test_two_engines_sharing_checkpointer_and_locks_process_once():
    saver, locks, proposer = InMemorySaver(), InProcessSessionLocks(), _BarrierProposer()
    first = TutorEngine(config(), Services(proposer=proposer), checkpointer=saver, locks=locks)
    second = TutorEngine(config(), Services(proposer=proposer), checkpointer=saver, locks=locks)
    sid = first.start("demo-a", "E02-P001").session_id
    turn = TurnInput(request_id=uuid4(), trigger="submit", steps=WRONG)
    _, errors = _concurrently(lambda: first.turn(sid, turn), lambda: second.turn(sid, turn))
    assert not errors and proposer.calls == 1 and len(first.decisions(sid)) == 1


def test_concurrent_different_requests_run_one_after_another():
    engine = TutorEngine(config(), Services(proposer=_BarrierProposer()), locks=InProcessSessionLocks())
    sid = engine.start("demo-a", "E02-P001").session_id
    _, errors = _concurrently(
        lambda: run(engine, sid, "submit", WRONG), lambda: run(engine, sid, "request_hint"))
    assert not errors
    assert [d.state_version for d in engine.decisions(sid)] == [1, 2] and engine.state(sid).state_version == 3


def test_start_does_not_overwrite_an_existing_session(engine):
    sid = engine.start("demo-a", "E02-P001").session_id
    run(engine, sid, "submit", WRONG)
    with pytest.raises(ValueError):
        engine.start("demo-a", "E02-P001", session_id=sid)
    assert len(engine.decisions(sid)) == 1


# ---------------------------------------------------------------- Bài làm và lời nhắn

def test_submission_comes_from_steps_or_message_lines():
    both = TurnInput(request_id=uuid4(), trigger="submit", steps=["2x = 16"], message="em làm vậy")
    assert both.submission == ["2x = 16"]
    from_message = TurnInput(request_id=uuid4(), trigger="submit", message="2x - 6 = 10\n\n x = 8 ")
    assert from_message.submission == ["2x - 6 = 10", "x = 8"]
    assert TurnInput(request_id=uuid4(), trigger="message", message="x = 8").submission == []
    with pytest.raises(ValueError):  # quá 12 dòng: không thể chấm đúng như đã lưu
        TurnInput(request_id=uuid4(), trigger="submit", message="\n".join(["x = 1"] * 13))


def test_new_problem_clears_graded_work_and_hint_keeps_it(engine):
    sid = engine.start("demo-a", "E02-P001").session_id
    run(engine, sid, "submit", WRONG)
    assert engine.state(sid).latest_submission == WRONG
    run(engine, sid, "request_hint")
    state = engine.state(sid)
    assert state.latest_submission == WRONG and state.latest_student_message is None
    flow = [("submit", WRONG), ("request_hint",), ("submit", WRONG)]
    for args in flow:
        reply = run(engine, sid, *args)
    assert reply.action == "backtrack" and engine.state(sid).latest_submission == []


def test_decisions_record_workflow_version(engine):
    sid = engine.start("demo-a", "E02-P001").session_id
    run(engine, sid, "submit", WRONG)
    assert engine.decisions(sid)[0].workflow_version == WORKFLOW_VERSION
