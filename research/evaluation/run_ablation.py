"""Chạy các cấu hình ablation trên cùng bộ tình huống và ghi câu của từng cấu hình (plan §18; RQ1b, RQ2, RQ5).

    python research/evaluation/run_ablation.py --out data/ablation/dev-fake      # LLM giả, không gọi API
    python research/evaluation/run_ablation.py --llm openai --yes --max-calls 272 --out data/ablation/dev-01
                                                                                 # GỌI API THẬT, tốn phí

Mỗi cặp (tình huống, cấu hình) chạy một lượt qua đúng các node LangGraph của hệ thống, bắt đầu từ sau
khi bài làm đã được chấm và ghi observation (state của tình huống là state ở thời điểm đó):

    readiness → context → decide → generate → verify → commit

Mọi cấu hình bắt đầu từ cùng state (plan §18.2) và dùng cùng generator, verifier, gate. Khác nhau đúng
ở phần plan §18.1 mô tả:
- No-BKT, Heuristic: policy không thấy xác suất mastery (``graph.project_state``); readiness tính lại
  theo ước lượng còn được phép.
- No-KG: context không có cạnh prerequisite, concept kế tiếp, và nội dung chỉ lấy được nhờ các cạnh đó.
- No-RAG: context không có nội dung truy xuất.
- Rule-policy: luật thay Agent LLM; vẫn chạy trong LangGraph.

Socratic LLM baseline (``socratic_llm``, plan §18.1) không có student model hay policy nên không đi qua
graph và không có ``PedagogicalDecision``: model nhận đề và cửa sổ hội thoại của cùng tình huống, dùng
cùng client và cùng kiểm tra chống lộ lời giải của verifier (``socratic_baseline.py``). Các chỉ số về
quyết định của nó để trống.

Đầu ra trong ``--out`` (để trong ``data/``, đã ignore; không ghi đè thư mục đã có):

    outputs.jsonl   SystemOutput của lần chạy thứ nhất: đầu vào của build_rating_packet.py --outputs
    runs.jsonl      mọi lượt chạy, kể cả lượt lỗi: quyết định, các lần sinh câu, latency, token, chi phí
    summary.json    tổng hợp theo cấu hình và phiên bản của các thành phần

``--llm fake`` dùng LLM giả (Agent lặp lại đề xuất của Rule-policy, generator lặp lại câu template) để
kiểm tra đường chạy và định dạng. Số liệu của chế độ này KHÔNG nói gì về model thật. Đây là bộ tình
huống dev (plan §11.5, §19.3): không dùng kết quả ở đây làm kết quả RQ.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
import time

from langgraph.checkpoint.memory import InMemorySaver

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from app.agent.decide import RulePolicyProposer  # noqa: E402
from app.agent.decision import MAX_REGENERATIONS, ExperimentConfiguration, StudentState  # noqa: E402
from app.agent.graph import WORKFLOW_VERSION, Services, build_graph  # noqa: E402
from app.agent.llm_proposer import (  # noqa: E402
    AGENT_POLICY_VERSION, PROMPT_VERSION as AGENT_PROMPT_VERSION, LLMProposer, decision_config, proposal_to_output,
)
from app.agent.rule_policy import POLICY_VERSION as RULE_POLICY_VERSION, READINESS_VERSION, rule_policy  # noqa: E402
from app.agent.approved_content import any_answer_key, any_problem_prompt, load_approved_content  # noqa: E402
from app.agent.stubs import retrieval_skills  # noqa: E402
from app.agent.tools import TurnContext  # noqa: E402
from app.generation.llm_generator import PROMPT_VERSION as RESPONSE_PROMPT_VERSION, LLMResponseGenerator  # noqa: E402
from app.generation.templates import TEMPLATE_VERSION, TemplateGenerator  # noqa: E402
from app.generation.verifier import VERIFIER_VERSION, ResponseVerifier  # noqa: E402
from app.llm.fakes import FakeLLMClient  # noqa: E402
from research.agent.scenarios import Scenario, load_scenarios, scenario_file  # noqa: E402
from research.evaluation.rubric import SystemOutput  # noqa: E402
from research.evaluation.socratic_baseline import (  # noqa: E402
    NAME as SOCRATIC_LLM, PROMPT_VERSION as BASELINE_PROMPT_VERSION, BaselineFailed, BaselineTurn,
    SocraticLLMBaseline, unenforced_checks,
)
from research.llm_support import (  # noqa: E402
    DEFAULT_MAX_CALLS, format_ms, format_usage, real_client, timing_stats, usage_summary,
)

E = ExperimentConfiguration
# Mọi cấu hình của plan §18.1, theo thứ tự chạy trong từng tình huống. Phần tử là chuỗi: E là StrEnum.
CONFIGURATIONS: tuple[str, ...] = (*(c.value for c in E), SOCRATIC_LLM)
WITHOUT_BKT = frozenset({E.NO_BKT.value, E.HEURISTIC.value})
WITHOUT_DECISION = frozenset({SOCRATIC_LLM})  # không có policy, nên không có PedagogicalDecision
WITHOUT_AGENT = frozenset({E.RULE_POLICY.value, SOCRATIC_LLM})
CALLS_PER_RESPONSE = 1 + MAX_REGENERATIONS
# Một verifier cho mọi cấu hình, kể cả baseline: cùng đáp án, cùng kiểm tra (plan §18.2).
# Đáp án của bài mẫu hoặc của bài đã duyệt (bộ approved.dev), chỉ verifier đọc.
VERIFIER = ResponseVerifier(any_answer_key)
# State của tình huống đã có kết quả chấm và observation: chạy tiếp từ sau node này.
ENTRY_NODE = "observe"


# --------------------------------------------------------------------------- cấu hình

def project_context(ctx: TurnContext, state: StudentState, configuration: E) -> TurnContext:
    """Context của tình huống như tool trả về dưới cấu hình đó. Full giữ nguyên context đã soạn.

    Cạnh, concept kế tiếp và nội dung: cùng quy tắc với ``stubs.StubTools`` và ``ApprovedTools``. Bài ứng
    viên theo tool đã tạo ra bộ tình huống (``candidate_problems``)."""
    kg = ctx.kg_enabled and configuration != E.NO_KG
    rag = ctx.rag_enabled and configuration != E.NO_RAG
    edges = ctx.edges if kg else []
    # Nội dung của skill mà RAG chỉ biết tới nhờ cạnh prerequisite: No-KG không được giữ.
    via_kg_only = retrieval_skills(state, ctx.edges) - retrieval_skills(state, edges)
    return ctx.model_copy(update={
        "edges": edges, "next_concepts": ctx.next_concepts if kg else [],
        "retrieved": [c for c in ctx.retrieved if c.skill_id not in via_kg_only] if rag else [],
        "problems": candidate_problems(ctx, state, kg),
        "kg_enabled": kg, "rag_enabled": rag,
        "kg_source": ctx.kg_source if kg else None, "graph_version": ctx.graph_version if kg else None,
        "tool_calls_used": kg + rag + 1})  # KG, RAG và problem bank


def candidate_problems(ctx: TurnContext, state: StudentState, kg: bool) -> list:
    """Bài ứng viên như tool thật trả về. Bộ trên bài đã duyệt (``approved_dev``): ``ApprovedTools`` lấy
    bài của concept đang học, prerequisite và concept kế tiếp theo KG, nên tắt KG chỉ còn bài của concept
    đang học (``ApprovedContent.candidates``). Bộ bài mẫu: ``StubTools`` trả cả ngân hàng mẫu, không theo
    KG, nên giữ nguyên."""
    if kg:
        return ctx.problems
    content = load_approved_content()
    if state.current.problem_id not in content.problems:
        return ctx.problems
    return content.candidates([state.current.concept_id])


def max_calls(scenarios: int, configurations: list[str], repeat: int) -> int:
    """Trần số lần gọi model: một lần cho Agent (trừ Rule-policy và baseline), và mỗi câu tối đa một lần
    sinh lại."""
    agents = sum(c not in WITHOUT_AGENT for c in configurations)
    return scenarios * repeat * (agents + len(configurations) * CALLS_PER_RESPONSE)


# --------------------------------------------------------------------------- model

class CountingClient:
    """Bọc client để đếm mọi lần gọi model, kể cả lần mà node gọi nó bị lỗi trước khi usage kịp ghi vào
    checkpoint. Chênh lệch với số usage đã ghi được báo riêng, không âm thầm tính là 0."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = 0

    @property
    def model(self) -> str:
        return self.inner.model

    def complete_json(self, **request):
        self.calls += 1
        return self.inner.complete_json(**request)


class RuleEchoAgent(LLMProposer):
    """Agent với LLM giả: model "trả" đúng đề xuất của Rule-policy trên state và context nó nhận.
    Đi hết đường Agent (prompt, schema, parse, gate, log) mà không gọi API."""

    def __call__(self, state, ctx):
        self.client.inner.push(proposal_to_output(rule_policy(state, ctx)))
        return super().__call__(state, ctx)


class TemplateEchoGenerator(LLMResponseGenerator):
    """Generator với LLM giả: model "trả" câu template của quyết định. Câu vẫn qua verifier như câu
    của model thật, nên có thể bị thay bằng template dự phòng."""

    templates = TemplateGenerator()

    def __call__(self, inp, feedback):
        self.client.inner.push({"message": self.templates(inp),
                                "content_ids_used": [c.content_id for c in inp.content]})
        return super().__call__(inp, feedback)


class EchoBaseline(SocraticLLMBaseline):
    """Baseline với LLM giả: model "trả" một câu hỏi chung cố định, rồi câu đó qua verifier như câu thật."""

    MESSAGE = "Em giải thích giúp mình em đã làm bài này theo cách nào được không?"

    def draft(self, turn, feedback):
        self.client.inner.push({"message": self.MESSAGE})
        return super().draft(turn, feedback)


@dataclass(frozen=True)
class Models:
    """Agent, generator và baseline của một lô chạy, dùng chung một client: mọi cấu hình cùng model
    (plan §18.2)."""

    client: CountingClient
    agent: LLMProposer
    generator: LLMResponseGenerator
    baseline: SocraticLLMBaseline

    @classmethod
    def real(cls, client) -> "Models":
        counted = CountingClient(client)
        return cls(counted, LLMProposer(counted), LLMResponseGenerator(counted), SocraticLLMBaseline(counted, VERIFIER))

    @classmethod
    def fake(cls) -> "Models":
        counted = CountingClient(FakeLLMClient())
        return cls(counted, RuleEchoAgent(counted), TemplateEchoGenerator(counted), EchoBaseline(counted, VERIFIER))


# --------------------------------------------------------------------------- chạy

def prompt_source(sc: Scenario):
    """Đề bài theo mã bài: của bộ tình huống đã replay nếu có, không thì của problem bank."""
    return sc.problem_prompts.get if sc.problem_refs else any_problem_prompt


def seeded_graph(sc: Scenario, configuration: str, models: Models, attempt: int):
    """Graph của hệ thống cho một cấu hình, với state của tình huống đã nạp vào checkpoint."""
    configuration = E(configuration)
    proposer = RulePolicyProposer() if configuration == E.RULE_POLICY else models.agent
    context = project_context(sc.context, sc.state, configuration)
    services = Services(tools=lambda state, config: context, proposer=proposer,
                        response_generator=models.generator, verifier=VERIFIER, problem_prompt=prompt_source(sc))
    if sc.problem_refs:
        services.problem_ref = sc.problem_refs.__getitem__
    graph = build_graph(services, decision_config(configuration, proposer, context.graph_version), InMemorySaver())
    thread = {"configurable": {"thread_id": f"{sc.id}:{configuration.value}:{attempt}"}, "recursion_limit": 25}
    # Như node load: mỗi lượt có ngân sách sinh lại mới.
    student = sc.state.model_copy(update={"budget": type(sc.state.budget)()})
    graph.update_state(thread, {
        "student": student.model_dump(mode="json"),
        "turn_input": {"request_id": str(student.request_id), "trigger": student.trigger},
        "response_attempts": [], "response": None}, as_node=ENTRY_NODE)
    return graph, thread


def run_turn(sc: Scenario, configuration: str, models: Models, attempt: int = 1) -> dict:
    """Một lượt của một cấu hình trên một tình huống, qua graph của hệ thống (baseline: không qua graph).

    Node lỗi không dừng cả lô (lô chạy thật đã tốn phí). Lượt lỗi vẫn giữ những gì các node trước đó
    đã ghi vào checkpoint: quyết định, các lần sinh câu và usage của chúng."""
    if configuration == SOCRATIC_LLM:
        return run_baseline_turn(sc, models, attempt)
    graph, thread = seeded_graph(sc, configuration, models, attempt)
    calls, started, error = models.client.calls, time.perf_counter(), None
    try:
        values = graph.invoke(None, thread)
    except Exception as failure:  # noqa: BLE001
        values, error = graph.get_state(thread).values, f"{type(failure).__name__}: {failure}"[:300]
    turn_ms = round((time.perf_counter() - started) * 1000, 3)
    return turn_row(sc, configuration, attempt, values, error=error, turn_ms=turn_ms,
                    model_calls=models.client.calls - calls)


def run_baseline_turn(sc: Scenario, models: Models, attempt: int = 1) -> dict:
    """Một lượt của Socratic LLM baseline trên cùng tình huống. Cửa sổ hội thoại giống lượt chạy qua graph:
    state của tình huống không mang câu gia sư nào trước đó, nên ``previous_messages`` rỗng ở mọi cấu hình."""
    turn = BaselineTurn.from_state(sc.state, prompt_source(sc))
    calls, started, error, outcome, done = models.client.calls, time.perf_counter(), None, None, ()
    try:
        outcome = models.baseline.run(turn)
        done = outcome.attempts
    except Exception as failure:  # noqa: BLE001
        # Như lượt lỗi qua graph: giữ các lần sinh đã có cùng usage của chúng.
        if isinstance(failure, BaselineFailed):
            done, failure = failure.attempts, failure.__cause__ or failure
        error = f"{type(failure).__name__}: {failure}"[:300]
    turn_ms = round((time.perf_counter() - started) * 1000, 3)
    attempts = [a.model_dump(mode="json") for a in done]
    row = turn_row(sc, SOCRATIC_LLM, attempt, {"response_attempts": attempts}, error=error, turn_ms=turn_ms,
                   model_calls=models.client.calls - calls)
    if outcome:
        row |= {"message": outcome.message, "response_source": outcome.final_source,
                "llm_skipped_reason": outcome.llm_skipped_reason,
                "unenforced_checks": unenforced_checks(turn, outcome.message) if outcome.final_source == "llm" else []}
    return row


def turn_row(sc: Scenario, configuration: str, attempt: int, values: dict, *, error: str | None, turn_ms: float,
             model_calls: int) -> dict:
    """Dòng kết quả từ state của graph. Lượt lỗi chỉ có phần đã chạy tới."""
    decision, response = values.get("decision"), values.get("response")
    attempts = values.get("response_attempts", [])
    llm_attempts = [a for a in attempts if a["source"] == "llm"]
    row = {
        "scenario": sc.id, "configuration": str(configuration), "attempt": attempt, "error": error,
        "turn_ms": turn_ms, "model_calls": model_calls,
        "agent_usage": decision["agent_usage"] if decision else None,
        "generation_usages": [a["usage"] for a in llm_attempts if a["usage"]],
        "llm_violations": [v for a in llm_attempts for v in a["violations"]],
        "regenerations_used": max(0, len(llm_attempts) - 1),
        "decision": decision, "attempts": attempts,
    }
    if decision:
        proposed, final = decision["proposed"], decision["final"]
        row |= {
            "final_action": final["action"], "final_intent": final["intent"], "hint_level": final["hint_level"],
            "problem_id": final["problem_id"],
            "final_acceptable": final["action"] in sc.acceptable_actions,
            "final_forbidden": final["action"] in sc.forbidden_actions,
            # Khớp nhãn ở mức intent/skill; None khi tình huống không có nhãn chi tiết.
            "final_detail_acceptable": sc.detail_acceptable(final["action"], final["intent"],
                                                            final["target_skill_id"]),
            "proposed_action": proposed["action"] if proposed else None,
            "proposed_forbidden": bool(proposed) and proposed["action"] in sc.forbidden_actions,
            "gate": decision["gate"]["status"] if decision["gate"] else None,
            "decision_source": decision["final_source"], "fallback_reason": decision["fallback_reason"],
            "decision_ms": decision["decision_latency_ms"],
            # Graph luôn tính lại readiness; tình huống soạn tay có thể ghi giá trị khác.
            "ready_to_advance": values["student"]["readiness"]["ready_to_advance"],
            "fixture_ready_to_advance": sc.state.readiness.ready_to_advance,
        }
    if response:
        row |= {"message": response["message"], "response_source": response["final_source"]}
    return row


def run_ablation(scenarios: list[Scenario], configurations: list[str], models: Models, repeat: int = 1,
                 on_row=None) -> list[dict]:
    """Các cấu hình chạy xen kẽ trong từng tình huống, để thay đổi của API theo thời gian không dồn vào
    một cấu hình."""
    rows = []
    for attempt in range(1, repeat + 1):
        for sc in scenarios:
            for configuration in configurations:
                rows.append(run_turn(sc, configuration, models, attempt))
                if on_row is not None:
                    on_row(rows[-1])
    return rows


def system_outputs(rows: list[dict]) -> list[SystemOutput]:
    """Câu đưa vào bộ chấm: lần chạy thứ nhất của mỗi (tình huống, cấu hình), bỏ lượt lỗi. Các lần lặp
    chỉ để đo độ ổn định (plan §18.2)."""
    return [SystemOutput(scenario_id=r["scenario"], system=r["configuration"], message=r["message"],
                         action=r.get("final_action"), intent=r.get("final_intent"), hint_level=r.get("hint_level"),
                         problem_id=r.get("problem_id"), response_source=r["response_source"])
            for r in rows if r["attempt"] == 1 and r["error"] is None]


# --------------------------------------------------------------------------- tổng hợp

# Hai mức so sánh quyết định: chiến lược (action, intent) và toàn bộ phần học sinh nhận được. Không so
# reason và evidence: đó là lời giải thích, hai lần chạy cùng quyết định vẫn có thể viết khác nhau.
ACTION_FIELDS = ("action", "intent")
DECISION_FIELDS = (*ACTION_FIELDS, "target_skill_id", "hint_level", "problem_id", "content_ids", "edge_ids")
COMPARISONS = {"action": ACTION_FIELDS, "decision": DECISION_FIELDS}


def _choices(rows: list[dict], fields: tuple[str, ...], attempt: int | None = None) -> dict[str, set]:
    """scenario → các quyết định cuối đã chọn, rút gọn về ``fields``."""
    out: dict[str, set] = {}
    for r in rows:
        if attempt is None or r["attempt"] == attempt:
            final = r["decision"]["final"]
            out.setdefault(r["scenario"], set()).add(
                tuple(tuple(sorted(final[f])) if isinstance(final[f], list) else final[f] for f in fields))
    return out


def _compare(ok: list[dict], full: list[dict] | None, fields: tuple[str, ...], repeated: bool) -> dict:
    """``differs_from_full``: tình huống mà lần chạy thứ nhất chọn khác Full (thành phần bị bỏ có đổi
    quyết định không). ``unstable``: tình huống mà các lần lặp không chọn giống nhau."""
    differs = None
    if full is not None:
        reference = _choices(full, fields, attempt=1)
        differs = sorted(sc for sc, chosen in _choices(ok, fields, attempt=1).items()
                         if sc in reference and chosen != reference[sc])
    unstable = sorted(sc for sc, chosen in _choices(ok, fields).items() if len(chosen) > 1) if repeated else None
    return {"differs_from_full": differs, "unstable": unstable}


def _cost_per_turn(usages: list[dict], turns: int, calls_without_usage: int) -> float | None:
    """None khi có lần gọi không biết giá hoặc không ghi được usage: không báo số thấp hơn chi phí thật."""
    costs = [u["cost_usd"] for u in usages]
    if not usages or None in costs or calls_without_usage:
        return None
    return round(sum(costs) / turns, 6)


def _decision_summary(ok: list[dict], full: list[dict] | None, repeated: bool) -> dict:
    detailed = [r["final_detail_acceptable"] for r in ok if r["final_detail_acceptable"] is not None]
    return {
        "final_acceptable": sum(r["final_acceptable"] for r in ok),
        # Chỉ tính trên các lượt mà tình huống có nhãn intent/skill; mẫu số ghi kèm.
        "final_detail_acceptable": {"ok": sum(detailed), "of": len(detailed)},
        "final_forbidden": sum(r["final_forbidden"] for r in ok),
        "proposed_forbidden": sum(r["proposed_forbidden"] for r in ok),
        "gate_rejected": sum(r["gate"] == "rejected" for r in ok),
        "fallbacks": dict(Counter(r["fallback_reason"] for r in ok if r["fallback_reason"])),
        **{label: _compare(ok, full, fields, repeated) for label, fields in COMPARISONS.items()},
        "decision_ms": timing_stats([r["decision_ms"] for r in ok]),
    }


def _no_decision_summary() -> dict:
    """Cấu hình không có policy: không có action để so với tập chấp nhận được, không có gate hay
    fallback. Để trống, không ghi 0."""
    return {"final_acceptable": None, "final_detail_acceptable": None, "final_forbidden": None,
            "proposed_forbidden": None, "gate_rejected": None,
            "fallbacks": {}, **{label: {"differs_from_full": None, "unstable": None} for label in COMPARISONS},
            "decision_ms": timing_stats([])}


def summarize(rows: list[dict]) -> dict:
    by_config: dict[str, list[dict]] = {}
    for r in rows:
        by_config.setdefault(r["configuration"], []).append(r)
    done = {name: [r for r in group if r["error"] is None] for name, group in by_config.items()}
    repeated = max((r["attempt"] for r in rows), default=1) > 1
    configurations = {}
    for name, group in by_config.items():
        ok = done[name]
        full = done.get(E.FULL.value) if name != E.FULL.value else None
        # Usage tính cả lượt lỗi: lượt đó vẫn đã gọi model.
        agent = [r["agent_usage"] for r in group if r["agent_usage"]]
        generation = [u for r in group for u in r["generation_usages"]]
        model_calls = sum(r["model_calls"] for r in group)
        without_usage = model_calls - len(agent) - len(generation)
        configurations[name] = {
            "runs": len(group), "errors": len(group) - len(ok),
            **(_decision_summary(ok, full, repeated) if name not in WITHOUT_DECISION else _no_decision_summary()),
            "response_sources": dict(Counter(r["response_source"] for r in ok)),
            "regenerated": sum(r["regenerations_used"] > 0 for r in ok),
            "llm_violations": dict(Counter(v for r in group for v in r["llm_violations"])),
            "turn_ms": timing_stats([r["turn_ms"] for r in ok]),
            "model_calls": model_calls, "model_calls_without_usage": without_usage,
            "agent": usage_summary(agent), "generation": usage_summary(generation),
            "cost_usd_per_turn": _cost_per_turn(agent + generation, len(group), without_usage),
        }
        if name in WITHOUT_DECISION:  # baseline: lỗi lời văn mà hệ thống chặn còn baseline chỉ ghi lại
            configurations[name]["unenforced_checks"] = dict(Counter(c for r in ok for c in r["unenforced_checks"]))
    # Chỉ so ở cấu hình còn dùng BKT: No-BKT và Heuristic tính readiness theo ước lượng khác là đúng thiết kế.
    hand_set = sorted({r["scenario"] for name, ok in done.items() if name not in WITHOUT_BKT | WITHOUT_DECISION
                       for r in ok if r["ready_to_advance"] != r["fixture_ready_to_advance"]})
    return {"configurations": configurations, "readiness_differs_from_fixture": hand_set,
            "errors": [{k: r[k] for k in ("scenario", "configuration", "attempt", "error", "model_calls")}
                       for r in rows if r["error"] is not None]}


def run_info(llm: str, model: str, scenarios: list[Scenario], configurations: list[str], repeat: int) -> dict:
    """Phiên bản và cấu hình của lần chạy, để tái lập (NFR-04)."""
    return {"llm": llm, "model": model, "scenarios": [sc.id for sc in scenarios],
            "scenario_split": scenarios[0].split if scenarios else scenario_file()["split"],
            "dataset_version": scenarios[0].dataset_version if scenarios else None,
            "configurations": [str(c) for c in configurations],
            # Phiếu chấm chỉ ghép câu với đúng tình huống đã sinh ra nó (build_rating_packet.py).
            "scenario_fingerprints": {sc.id: sc.fingerprint for sc in scenarios},
            "repeat": repeat, "max_regenerations": MAX_REGENERATIONS,
            "versions": {"workflow": WORKFLOW_VERSION, "agent_policy": AGENT_POLICY_VERSION,
                         "agent_prompt": AGENT_PROMPT_VERSION, "rule_policy": RULE_POLICY_VERSION,
                         "readiness": READINESS_VERSION, "response_prompt": RESPONSE_PROMPT_VERSION,
                         "verifier": VERIFIER_VERSION, "template": TEMPLATE_VERSION,
                         "socratic_baseline_prompt": BASELINE_PROMPT_VERSION}}


def _count(scenarios: list[str] | None) -> str:
    return "-" if scenarios is None else str(len(scenarios))


def _number(value: int | None) -> str:
    return "-" if value is None else str(value)


def print_report(summary: dict) -> None:
    print("≠act / ≠dec: số tình huống chọn khác Full về action+intent / về toàn bộ quyết định; "
          "'-': không áp dụng (socratic_llm không có quyết định)")
    print(f"{'configuration':13} {'runs':>4} {'err':>3} {'accept':>6} {'forbid':>6} {'reject':>6} {'fallbk':>6} "
          f"{'llm':>4} {'regen':>5} {'≠act':>4} {'≠dec':>4} {'calls':>5}  turn_ms")
    for name, s in summary["configurations"].items():
        decided = name not in WITHOUT_DECISION
        print(f"{name:13} {s['runs']:>4} {s['errors']:>3} {_number(s['final_acceptable']):>6} "
              f"{_number(s['final_forbidden']):>6} {_number(s['gate_rejected']):>6} "
              f"{sum(s['fallbacks'].values()) if decided else '-':>6} {s['response_sources'].get('llm', 0):>4} "
              f"{s['regenerated']:>5} {_count(s['action']['differs_from_full']):>4} "
              f"{_count(s['decision']['differs_from_full']):>4} {s['model_calls']:>5}  {format_ms(s['turn_ms'])}")
    for name, s in summary["configurations"].items():
        notes = [line for part in ("agent", "generation") for line in format_usage(s[part])]
        if notes:
            notes.insert(0, f"    cost_usd_per_turn={s['cost_usd_per_turn']}")
        if s["model_calls_without_usage"]:
            notes.append(f"    {s['model_calls_without_usage']} lần gọi model không ghi được usage (lượt lỗi giữa chừng)")
        detail = s["final_detail_acceptable"]
        if detail and detail["of"]:
            notes.append(f"    khớp nhãn intent/skill: {detail['ok']}/{detail['of']} lượt có nhãn chi tiết")
        if s.get("unenforced_checks"):
            notes.append("    câu đã gửi có lỗi lời văn mà hệ thống chặn còn baseline không: "
                         + ", ".join(f"{check}={n}" for check, n in s["unenforced_checks"].items()))
        for label, title in (("action", "action"), ("decision", "quyết định đầy đủ")):
            if s[label]["differs_from_full"]:
                notes.append(f"    khác Full về {title}: {', '.join(s[label]['differs_from_full'])}")
            if s[label]["unstable"]:
                notes.append(f"    các lần lặp khác nhau về {title}: {', '.join(s[label]['unstable'])}")
        if notes:
            print(f"\n[{name}]")
            print("\n".join(notes))
    if summary["readiness_differs_from_fixture"]:
        print("\nReadiness tính lại khác giá trị soạn tay của tình huống (dùng giá trị tính lại): "
              + ", ".join(summary["readiness_differs_from_fixture"]))
    for e in summary["errors"]:
        print(f"LỖI {e['scenario']} {e['configuration']} lần {e['attempt']} (đã gọi model {e['model_calls']} lần): "
              f"{e['error']}", file=sys.stderr)


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--llm", choices=["fake", "openai"], default="fake")
    parser.add_argument("--configs", nargs="*", choices=CONFIGURATIONS, help="mặc định chạy tất cả")
    parser.add_argument("--scenarios", nargs="*", help="ID tình huống, mặc định chạy tất cả")
    parser.add_argument("--scenario-set", type=Path, help="dev.json hoặc test.json từ research.scenarios.build")
    parser.add_argument("--repeat", type=int, default=1, help="số lần chạy mỗi cặp, để đo độ ổn định")
    parser.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS,
                        help="trần số lần gọi model, dừng trước khi chạy nếu vượt")
    parser.add_argument("--yes", action="store_true", help="xác nhận gọi API thật (--llm openai)")
    parser.add_argument("--out", type=Path, help="thư mục mới, ví dụ data/ablation/dev-01")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    if args.repeat < 1:
        parser.error("--repeat must be >= 1")
    if args.llm == "openai" and not args.out:
        parser.error("--llm openai needs --out: results of paid calls must be saved")
    if args.out and args.out.exists() and any(args.out.iterdir()):
        parser.error(f"{args.out} already has files; results are never overwritten")

    if args.scenario_set:
        scenarios = load_scenarios(args.scenarios or None, path=args.scenario_set)
        scenario_set_hash = hashlib.sha256(args.scenario_set.read_bytes()).hexdigest()
    else:
        scenarios = load_scenarios(args.scenarios or None)
        scenario_set_hash = None
    if not scenarios:
        parser.error("Scenario set is empty")
    configurations = list(args.configs) if args.configs else list(CONFIGURATIONS)
    if args.llm == "openai":
        calls = max_calls(len(scenarios), configurations, args.repeat)
        client = real_client(calls, f"{len(scenarios)} tình huống × {len(configurations)} cấu hình × {args.repeat}",
                             max_calls=args.max_calls, confirmed=args.yes)
        if client is None:
            return 2
        models = Models.real(client)
    else:
        models = Models.fake()

    runs_file = None
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        runs_file = (args.out / "runs.jsonl").open("w", encoding="utf-8")

    def save(row: dict) -> None:  # ghi ngay từng lượt: lô dừng giữa chừng vẫn giữ phần đã chạy
        if runs_file is not None:
            runs_file.write(json.dumps(row, ensure_ascii=False) + "\n")
            runs_file.flush()

    try:
        rows = run_ablation(scenarios, configurations, models, args.repeat, save)
    finally:
        if runs_file is not None:
            runs_file.close()
    summary = summarize(rows)
    print_report(summary)
    if args.out:
        outputs = system_outputs(rows)
        (args.out / "outputs.jsonl").write_text("".join(o.model_dump_json() + "\n" for o in outputs), encoding="utf-8")
        info = run_info(args.llm, models.client.model, scenarios, configurations, args.repeat)
        if scenario_set_hash:
            info["scenario_set_sha256"] = scenario_set_hash
        (args.out / "summary.json").write_text(
            json.dumps({"run": info, **summary}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nĐã ghi {len(rows)} lượt và {len(outputs)} câu vào {args.out}")
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
