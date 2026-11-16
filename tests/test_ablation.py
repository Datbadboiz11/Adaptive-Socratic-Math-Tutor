"""Script chạy ablation: chiếu cấu hình, chạy qua graph của hệ thống, đầu ra cho bộ chấm, tổng hợp."""
import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from app.agent.decision import ExperimentConfiguration as E  # noqa: E402
from app.agent.graph import WORKFLOW_VERSION  # noqa: E402
from research.agent.scenarios import load_scenarios  # noqa: E402
from research.evaluation.build_rating_packet import main as build_main  # noqa: E402
from research.evaluation.rubric import PacketKey, SystemOutput  # noqa: E402
from research.evaluation.run_ablation import (  # noqa: E402
    Models, main, max_calls, project_context, run_ablation, run_turn, summarize, system_outputs,
)

SCENARIOS = {sc.id: sc for sc in load_scenarios()}


@pytest.fixture
def models():
    return Models.fake()


def agent_input(models) -> dict:
    """Dữ liệu Agent nhận ở lần gọi gần nhất."""
    requests = models.client.inner.requests
    return json.loads(next(r for r in reversed(requests) if r["schema_name"] == "pedagogical_decision")["input"])


def fail(message):
    def raiser(*args, **kwargs):
        raise RuntimeError(message)
    return raiser


# --------------------------------------------------------------------------- chiếu cấu hình

def test_full_keeps_the_authored_context_and_each_ablation_removes_only_its_part():
    for sc in SCENARIOS.values():
        assert project_context(sc.context, sc.state, E.FULL) == sc.context, sc.id
        for configuration in (E.NO_BKT, E.HEURISTIC, E.RULE_POLICY):
            assert project_context(sc.context, sc.state, configuration) == sc.context
    sc = SCENARIOS["SC-04"]  # lỗi thuộc skill đang học: nội dung của prerequisite chỉ có nhờ KG
    no_kg = project_context(sc.context, sc.state, E.NO_KG)
    assert (no_kg.edges, no_kg.next_concepts, no_kg.kg_enabled, no_kg.tool_calls_used) == ([], [], False, 2)
    assert {c.skill_id for c in no_kg.retrieved} == {sc.state.current.target_skill_id}
    assert no_kg.problems == sc.context.problems and no_kg.rag_enabled
    no_rag = project_context(sc.context, sc.state, E.NO_RAG)
    assert (no_rag.retrieved, no_rag.rag_enabled, no_rag.tool_calls_used) == ([], False, 2)
    assert no_rag.edges == sc.context.edges and no_rag.kg_enabled


def test_no_kg_gives_the_agent_no_prerequisite_relation(models):
    row = run_turn(SCENARIOS["SC-08"], E.NO_KG, models)  # Full ở đây sẽ backtrack theo KG
    sent = agent_input(models)
    assert sent["context"]["edges"] == [] and sent["context"]["next_concepts"] == []
    assert sent["context"]["kg_enabled"] is False and sent["facts"]["prerequisite_evidence"] == {}
    assert "PRE-" not in json.dumps(sent)  # không còn mã cạnh nào trong prompt (plan §18.2)
    assert row["final_action"] != "backtrack" and row["decision"]["candidate_edge_ids"] == []
    assert run_turn(SCENARIOS["SC-08"], E.FULL, models)["final_action"] == "backtrack"


@pytest.mark.parametrize("configuration, view", [(E.NO_BKT, "none"), (E.HEURISTIC, "recent_ratio")])
def test_agent_without_bkt_sees_evidence_but_no_mastery_probability(models, configuration, view):
    run_turn(SCENARIOS["SC-01"], E.FULL, models)
    assert [k["p_mastery"] for k in agent_input(models)["state"]["skills"]] == [0.42, 0.61]
    run_turn(SCENARIOS["SC-01"], configuration, models)
    state = agent_input(models)["state"]
    assert state["mastery_view"] == view and [k["p_mastery"] for k in state["skills"]] == [None, None]
    assert [k["independent_observations"] for k in state["skills"]] == [3, 4]  # evidence log được giữ
    # Readiness là bản tóm tắt suy từ ước lượng: No-BKT không có điều kiện ngưỡng.
    assert ("estimate_below_threshold" in state["readiness"]["unmet"]) == (configuration == E.HEURISTIC)


# --------------------------------------------------------------------------- chạy qua graph

def test_every_configuration_starts_from_the_same_state_and_runs_the_product_graph(models):
    before = copy.deepcopy((SCENARIOS["SC-01"].state, SCENARIOS["SC-01"].context))
    rows = run_ablation([SCENARIOS["SC-01"]], list(E), models)
    assert (SCENARIOS["SC-01"].state, SCENARIOS["SC-01"].context) == before  # tình huống gốc không bị sửa
    assert [r["configuration"] for r in rows] == [c.value for c in E] and all(r["error"] is None for r in rows)
    decisions = [r["decision"] for r in rows]
    assert {d["workflow_version"] for d in decisions} == {WORKFLOW_VERSION}
    assert len({(d["session_id"], d["turn_id"], d["state_version"]) for d in decisions}) == 1
    for row, d in zip(rows, decisions):
        rule = row["configuration"] == "rule_policy"
        assert d["config"]["configuration"] == row["configuration"]
        assert d["proposed_by"] == ("rule_policy" if rule else "agent")
        assert (row["agent_usage"] is None) == rule and (d["config"]["model_id"] is None) == rule
        assert row["generation_usages"] and row["attempts"][-1]["message"] == row["message"]  # cùng generator
        assert row["model_calls"] == (0 if rule else 1) + len(row["generation_usages"])


def test_rule_policy_reproduces_the_scenario_regression_unless_readiness_was_hand_set(models):
    rows = run_ablation(list(SCENARIOS.values()), [E.RULE_POLICY], models)
    summary = summarize(rows)
    assert summary["readiness_differs_from_fixture"] == ["SC-12"]  # graph tính lại, không tin giá trị soạn tay
    for r in rows:
        sc = SCENARIOS[r["scenario"]]
        if sc.id != "SC-12":
            assert (r["final_action"], r["final_intent"]) == (sc.expected_rule_action, sc.expected_rule_intent)
    rule = summary["configurations"]["rule_policy"]
    assert rule["final_acceptable"] == len(SCENARIOS) and rule["agent"]["llm_calls"] == 0
    assert rule["model_calls"] == rule["generation"]["llm_calls"] and rule["model_calls_without_usage"] == 0


# --------------------------------------------------------------------------- tổng hợp

def test_summary_compares_strategy_and_full_decision_with_full(models):
    rows = run_ablation([SCENARIOS[i] for i in ("SC-04", "SC-06", "SC-08")], [E.FULL, E.NO_BKT, E.NO_KG, E.NO_RAG],
                        models)
    s = summarize(rows)["configurations"]
    assert s["full"]["action"] == s["full"]["decision"] == {"differs_from_full": None, "unstable": None}
    assert s["no_bkt"]["action"]["differs_from_full"] == ["SC-04"]  # thiếu mastery: hỏi chẩn đoán thay vì gợi ý
    assert s["no_bkt"]["final_acceptable"] == 2
    assert s["no_kg"]["action"]["differs_from_full"] == ["SC-08"]
    # SC-06: No-RAG vẫn gợi ý, nhưng không còn nội dung để trích. Cùng action, khác quyết định.
    assert s["no_rag"]["action"]["differs_from_full"] == []
    assert s["no_rag"]["decision"]["differs_from_full"] == ["SC-06"]
    assert s["full"]["cost_usd_per_turn"] is None  # model giả không có giá: không báo số 0


def test_repeats_that_give_another_problem_are_unstable_even_with_the_same_action(models):
    rows = run_ablation([SCENARIOS["SC-04"], SCENARIOS["SC-10"]], [E.FULL], models, repeat=2)
    full = summarize(rows)["configurations"]["full"]
    assert full["action"]["unstable"] == full["decision"]["unstable"] == []
    second = copy.deepcopy(next(r for r in rows if r["scenario"] == "SC-10" and r["attempt"] == 2))
    assert second["decision"]["final"]["problem_id"] == "E02-P003"
    second["decision"]["final"]["problem_id"] = "E02-P002"  # cùng check_transfer, giao bài khác
    changed = [second if r["scenario"] == "SC-10" and r["attempt"] == 2 else r for r in rows]
    full = summarize(changed)["configurations"]["full"]
    assert full["action"]["unstable"] == [] and full["decision"]["unstable"] == ["SC-10"]
    assert len(system_outputs(rows)) == 2  # chỉ lần chạy thứ nhất vào bộ chấm


# --------------------------------------------------------------------------- lượt lỗi

def test_a_turn_that_fails_after_the_model_answered_keeps_its_calls_and_messages(models, monkeypatch):
    monkeypatch.setattr("app.generation.verifier.ResponseVerifier.check_generated", fail("verifier broke"))
    row = run_turn(SCENARIOS["SC-01"], E.FULL, models)
    assert "verifier broke" in row["error"] and "message" not in row
    assert row["model_calls"] == 2 and row["agent_usage"] and len(row["generation_usages"]) == 1
    assert row["final_action"] == "diagnose" and row["attempts"][0]["message"]  # câu model viết còn để phân tích
    s = summarize([row])["configurations"]["full"]
    assert (s["runs"], s["errors"], s["final_acceptable"]) == (1, 1, 0)
    assert (s["agent"]["llm_calls"], s["generation"]["llm_calls"], s["model_calls_without_usage"]) == (1, 1, 0)
    assert system_outputs([row]) == []


def test_a_turn_that_fails_at_commit_keeps_the_decision_and_the_verified_message(models, monkeypatch):
    monkeypatch.setattr("app.agent.graph.apply_decision", fail("problem bank is down"))
    row = run_turn(SCENARIOS["SC-10"], E.RULE_POLICY, models)
    assert "problem bank is down" in row["error"] and row["message"] and row["response_source"] == "llm"
    assert row["final_action"] == "check_transfer" and row["model_calls"] == len(row["generation_usages"]) == 1


def test_calls_whose_usage_was_lost_are_reported_not_counted_as_free(models, monkeypatch):
    monkeypatch.setattr("app.agent.decide.resolve_decision", fail("decide broke"))  # sau khi Agent đã được gọi
    row = run_turn(SCENARIOS["SC-01"], E.FULL, models)
    assert row["decision"] is None and row["agent_usage"] is None and row["model_calls"] == 1
    s = summarize([row])["configurations"]["full"]
    assert (s["model_calls"], s["model_calls_without_usage"], s["cost_usd_per_turn"]) == (1, 1, None)


# --------------------------------------------------------------------------- CLI

def test_outputs_feed_the_rating_packet(tmp_path, capsys):
    out = tmp_path / "ablation"
    assert main(["--scenarios", "SC-01", "SC-08", "--out", str(out)]) == 0
    assert "khác Full về action: SC-08" in capsys.readouterr().out
    outputs = [SystemOutput.model_validate_json(line)
               for line in (out / "outputs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(outputs) == 12 and len((out / "runs.jsonl").read_text(encoding="utf-8").splitlines()) == 12
    info = json.loads((out / "summary.json").read_text(encoding="utf-8"))["run"]
    assert info["llm"] == "fake" and info["versions"]["workflow"] == WORKFLOW_VERSION and info["scenario_split"] == "dev"

    packet = tmp_path / "packet"
    assert build_main(["--outputs", str(out / "outputs.jsonl"), "--raters", "r1", "r2",
                       "--compare", "full:no_kg", "full:rule_policy", "--out", str(packet)]) == 0
    key = PacketKey.model_validate_json((packet / "key.json").read_text(encoding="utf-8"))
    assert len(key.items) == 12 and len(key.pairs) == 4
    assert {i.action for i in key.items if i.scenario_id == "SC-08"} == {"backtrack", "scaffold"}


def test_results_are_never_overwritten_and_failed_turns_do_not_lose_the_batch(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("app.agent.graph.apply_decision", fail("problem bank is down"))
    out = tmp_path / "ablation"
    assert main(["--scenarios", "SC-01", "--configs", "full", "no_rag", "--out", str(out)]) == 1
    rows = [json.loads(line) for line in (out / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2 and all("problem bank is down" in r["error"] and r["agent_usage"] for r in rows)
    assert (out / "outputs.jsonl").read_text(encoding="utf-8") == ""
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["configurations"]["no_rag"]["errors"] == 1 and len(summary["errors"]) == 2
    assert "LỖI SC-01 no_rag lần 1 (đã gọi model 2 lần)" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main(["--out", str(out)])


def test_openai_mode_refuses_without_confirmation(monkeypatch, tmp_path):
    monkeypatch.setattr("research.llm_support.read_env", lambda: {"LLM_ENABLED": "true", "OPENAI_API_KEY": "sk-test"})
    monkeypatch.setattr("research.llm_support.OpenAIResponsesClient", fail("must not create a real client"))
    out = tmp_path / "ablation"
    assert max_calls(16, list(E), 1) == 16 * (5 + 6 * 2)  # 5 cấu hình gọi Agent; mỗi câu tối đa 2 lần sinh
    assert max_calls(2, [E.RULE_POLICY], 3) == 12
    assert main(["--llm", "openai", "--out", str(out)]) == 2
    assert main(["--llm", "openai", "--yes", "--out", str(out)]) == 2  # 272 lần > trần mặc định
    monkeypatch.setattr("research.llm_support.read_env", lambda: {})
    assert main(["--llm", "openai", "--yes", "--max-calls", "500", "--out", str(out)]) == 2
    assert not out.exists()  # chưa được phép gọi thì chưa tạo gì
    with pytest.raises(SystemExit):  # lượt gọi tốn phí phải có nơi lưu kết quả
        main(["--llm", "openai", "--yes"])
