"""LLM extraction: cú pháp g2-v1, chốt chặn trung thành, extractor, nối LangGraph. Không gọi mạng."""
import dataclasses
import json
import string
from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.agent.decision import DecisionConfig  # noqa: E402
from app.llm.fakes import FakeLLMClient  # noqa: E402
from app.agent.graph import Services, TurnInput, TutorEngine  # noqa: E402
from app.llm.client import LLMCall, LLMCallFailed, LLMTimeout  # noqa: E402
from app.agent.stubs import StubAnalyzer  # noqa: E402
from app.extraction.contracts import (  # noqa: E402
    FIDELITY_REASONS, LLM_REASONS, ExtractedStep, ExtractionRecord, ExtractionResult, Reason,
)
from app.extraction.extractor import (  # noqa: E402
    EXTRACTOR_VERSION, INSTRUCTIONS, OUTPUT_SCHEMA, PROMPT_VERSION, StepExtractor,
)
from app.extraction.grammar import GRAMMAR_VERSION, GrammarIssue, Kind, check_equation, tokenize  # noqa: E402
from app.extraction.guards import GuardIssue, locate_spans  # noqa: E402
from research.extraction.evaluate_extraction import (  # noqa: E402
    evaluate, load_cases, main, oracle_client, run_case, run_info, summarize,
)

CASES = {c.id: c for c in load_cases()}
PROBLEM = "Giải phương trình 2(x - 3) = 10."
CONFIG = DecisionConfig(configuration="rule_policy", policy_version="rule-policy-test")


def spans(*items):
    return {"status": "extracted", "spans": list(items), "reasons": []}


def extract(lines, llm_output=None, problem=PROBLEM):
    client = FakeLLMClient([llm_output]) if llm_output is not None else None
    return StepExtractor(client)(problem, lines)


def reasons(outcome):
    return [r.value for r in outcome.result.reasons]


# ---------------------------------------------------------------- cú pháp g2-v1

def keys(text):
    return [t.text for t in tokenize(text)]


def test_tokens_keep_numbers_whole_and_map_unicode():
    assert keys("2×(x − 3) = 10") == ["2", "*", "(", "x", "-", "3", ")", "=", "10"]
    assert keys("x = 6 5") == ["x", "=", "6", "5"]  # hai số, không bao giờ thành 65
    assert keys("X = 6.5") == ["x", "=", "6.5"]
    assert [t.kind for t in tokenize("a => b → c")] == [Kind.WORD, Kind.SEP, Kind.SEP, Kind.WORD, Kind.SEP, Kind.WORD]
    assert [t.kind for t in tokenize("xét x")] == [Kind.WORD, Kind.VAR]


def test_token_positions_point_into_the_original_text():
    text = "Vậy 2x − 6 = 10 ạ"
    tokens = [t for t in tokenize(text) if t.kind != Kind.WORD]
    assert text[tokens[0].start:tokens[-1].end] == "2x − 6 = 10"


@pytest.mark.parametrize("text, normalized", [
    ("2x - 6 = 10", "2x-6=10"), ("2(x - 3) = 10", "2(x-3)=10"), ("-3x = 12", "-3x=12"),
    ("x = (10 + 6)/2", "x=(10+6)/2"), ("5x - 7 = 2x + 8", "5x-7=2x+8"), ("x = -6", "x=-6"),
    ("2 * x = 16", "2*x=16"), ("x = 6.5", "x=6.5"), ("2 x = 16", "2x=16"),
])
def test_valid_equations(text, normalized):
    assert check_equation(tokenize(text)) == normalized


@pytest.mark.parametrize("text, reason", [
    ("x = 6,5", "decimal_comma"), ("1/2x = 4", "ambiguous_fraction"), ("x/2(x+1) = 4", "ambiguous_fraction"),
    ("2x = 10 + 6 = 16", "chained_equals"), ("2x - 6", "no_equation"), ("x = 6 5", "syntax"),
    ("x = ", "syntax"), ("2x = (16", "syntax"), ("x2 = 4", "syntax"), ("x = 123456", "syntax"),
    ("x = 1.23456", "syntax"), ("x^2 = 4", "unsupported_notation"), ("y = 3", "unsupported_notation"),
    ("x = " + "(" * 14 + "8" + ")" * 14, "syntax"), ("", "syntax"),
])
def test_invalid_equations(text, reason):
    with pytest.raises(GrammarIssue) as issue:
        check_equation(tokenize(text))
    assert issue.value.reason == reason


# ---------------------------------------------------------------- chốt chặn: LLM không được sửa bài

def locate(lines, *items):
    return locate_spans([tokenize(line) for line in lines], list(items))


def test_spans_are_found_in_order_ignoring_spacing():
    found = locate(["em có 2x-3=10", "Vậy x = 6.5"], "2x - 3 = 10", "x=6.5")
    assert [(f.line, f.source(raw)) for f, raw in zip(found, ["em có 2x-3=10", "Vậy x = 6.5"])] == \
        [(0, "2x-3=10"), (1, "x = 6.5")]


@pytest.mark.parametrize("lines, items, reason", [
    (["em có 2x - 3 = 10"], ["2x - 6 = 10"], "not_verbatim"),              # sửa lỗi của học sinh
    (["em có x = 6 5"], ["x = 65"], "not_verbatim"),                       # ghép hai số
    (["2x = 16 nên x = 8"], ["x = 8", "2x = 16"], "not_verbatim"),         # đảo thứ tự
    (["em có 2x = 16"], ["2x = 16", "x = 8"], "not_verbatim"),             # bịa thêm bước
    (["em có 2x = 16"], ["x = 16"], "partial_span"),                       # bỏ hệ số
    (["em có 2x = 16 + 4"], ["2x = 16"], "partial_span"),                  # cắt vế phải
    (["em có x = 6,5"], ["x = 6"], "partial_span"),                        # cắt phần thập phân
    (["em có 3 + x = 6"], ["x = 6"], "partial_span"),
    (["Bài 2 x = 8"], ["x = 8"], "partial_span"),                          # "2 x" có thể là 2x: không đoán
    (["2x = 16 nên x = 8"], ["2x = 16"], "unextracted_math"),              # bỏ sót một bước
    (["em có 2x = 16"], [], "unextracted_math"),
    (["em có 2x = 16"], ["   "], "not_verbatim"),
])
def test_guards_reject_unfaithful_spans(lines, items, reason):
    with pytest.raises(GuardIssue) as issue:
        locate(lines, *items)
    assert issue.value.reason == reason


@pytest.mark.parametrize("line", [
    "em được x = 8^2", "em được √x = 8", "em được x = 8y", "em được x = 8 : 2", "em được x = 8²",
    "em được x = 8 y", "em được x = 8%", "em được x = 8 ± 1", "em được x = 8π", "8: x = 8",
])
def test_guards_reject_spans_cut_from_unsupported_notation(line):
    # Review: LLM trả "x = 8" từ các bài này từng được chấp nhận, rồi được chấm đúng và ghi BKT.
    with pytest.raises(GuardIssue) as issue:
        locate([line], "x = 8")
    assert issue.value.reason == "partial_span"


@pytest.mark.parametrize("line", [
    "em được x = 8 π", "em được x = 8 sin(2)", "em được x = 8 (sin 2)", "em được x = 8 cos 2",
    "em được x = 8 log(2)", "em được x = 8 f(2)", "em được x = 8 α", "em được x = 8 (2)", "π x = 8",
    "em được x = 8 (π)", "em được x = 8 Sqrt 2",
])
def test_guards_reject_spans_cut_from_math_written_as_words(line):
    # Review: π, sin... bị tokenize thành chữ nên từng bị coi là lời văn, kể cả trong ngoặc.
    with pytest.raises(GuardIssue) as issue:
        locate([line], "x = 8")
    assert issue.value.reason == "partial_span"


@pytest.mark.parametrize("line", [
    "em tính giai thừa được x = 8!", "em được x = 8 !", "em được x = 8°", "em được x = 8&2", "em được x = 8#",
    "em được x = 8@2", "em được x = 8~", "!x = 8", "#x = 8",
])
def test_guards_reject_spans_next_to_other_symbols(line):
    # Review: "x = 8!" (giai thừa) từng được tách thành x=8. Dấu sát biểu thức mà không chắc là dấu câu
    # thì coi là ký hiệu và hỏi lại.
    with pytest.raises(GuardIssue) as issue:
        locate([line], "x = 8")
    assert issue.value.reason == "partial_span"


@pytest.mark.parametrize("char", sorted(set(string.punctuation) - {".", ",", "?", '"', "(", ")", ";"}))
def test_any_punctuation_glued_after_an_expression_blocks_the_span(char):
    # Danh sách trắng, không phải danh sách đen: mọi dấu ASCII ngoài dấu kết câu đứng sát sau biểu
    # thức đều chặn, kể cả dấu chưa ai nghĩ tới. ";" là dấu ngắt bước, "(" ")" có luật riêng.
    with pytest.raises(GuardIssue):
        locate([f"em được x = 8{char}"], "x = 8")


@pytest.mark.parametrize("lines", [
    ["em được x^2 rồi suy ra x = 8"], ["√64 nên x = 8"], ["x = 8", "kiểm tra: 8 : 2"], ["x = 8", "16 - 8"],
    ["em được x = 8 rồi sin(2) = 0"], ["x = 8", "nhân thêm π"], ["x = 8", "rồi lấy log 2"],
    ["x = 8", "rồi 5! = 120"], ["x = 8", "kiểm tra 3!"], ["x = 8", "góc 30°"],
])
def test_guards_reject_math_left_outside_spans(lines):
    with pytest.raises(GuardIssue) as issue:
        locate(lines, "x = 8")
    assert issue.value.reason == "unextracted_math"


@pytest.mark.parametrize("line", [
    "em được x = 8", "Bước 1: x = 8", "Đáp số: x = 8.", "em được x = 8 (đúng không ạ)", "vậy x = 8, đúng ạ",
    "“x = 8”", "em được x = 8 (bước 2)", "em được x = 8 rồi ạ", "câu a: x = 8", "em được x = 8?",
    "x = 8… ạ", "đúng rồi! x = 8", "em làm xong rồi! Vậy x = 8.", "em nhân 2 vào ngoặc rồi được x = 8",
    "chia hai vế cho 2 thì được x = 8",
])
def test_guards_still_accept_plain_labels_and_text(line):
    assert len(locate([line], "x = 8")) == 1


def test_unsupported_notation_never_reaches_the_validator():
    client = FakeLLMClient([spans("x = 8")])
    engine, analyzer, sid = engine_with(client)
    reply = submit(engine, sid, "em được x = 8^2")
    assert analyzer.seen == [] and (reply.action, reply.intent) == ("clarify", "resolve_input")
    assert engine.state(sid).skills == []  # không thêm observation nào
    assert engine.extractions(sid)[0].result.reasons == [Reason.PARTIAL_SPAN]


@pytest.mark.parametrize("line", [
    "em được x = 8 nhân 2", "em được x = 8 chia 2", "em được x = 8 mũ 2", "em được x = 8 cộng thêm 2",
    "em được x = 8 trừ 1", "em được x = 8 bình phương", "em được x = 8 lần", "em được x = 8, nhân 2",
    "em được x = 8 nhan 2", "căn x = 8", "em được căn x = 8",
])
def test_guards_reject_operations_written_in_words_next_to_the_span(line):
    # Review: "x = 8 nhân 2" từng được tách thành x=8, chấm đúng và ghi observation.
    with pytest.raises(GuardIssue) as issue:
        locate([line], "x = 8")
    assert issue.value.reason == "partial_span"


def test_operation_in_words_never_reaches_the_validator():
    engine, analyzer, sid = engine_with(FakeLLMClient([spans("x = 8")]))
    reply = submit(engine, sid, "em được x = 8 nhân 2")
    assert analyzer.seen == [] and (reply.action, reply.intent) == ("clarify", "resolve_input")
    assert engine.state(sid).skills == []


def test_factorial_never_reaches_the_validator():
    # Review: "8!" từng bị đổi thành 8 rồi được chấm. Phải hỏi lại trước analyzer và BKT.
    client = FakeLLMClient([spans("x = 8")])
    engine, analyzer, sid = engine_with(client)
    reply = submit(engine, sid, "em tính giai thừa được x = 8!")
    assert analyzer.seen == [] and (reply.action, reply.intent) == ("clarify", "resolve_input")
    assert engine.state(sid).skills == []
    assert engine.extractions(sid)[0].result.reasons == [Reason.PARTIAL_SPAN]


def test_guards_accept_markers_comments_and_arrows():
    assert len(locate(["1) 2x - 6 = 10", "2. x = 8"], "2x - 6 = 10", "x = 8")) == 2
    assert len(locate(["Bước 1: 2x = 16 (chuyển vế)", "Vậy x = 8."], "2x = 16", "x = 8")) == 2
    assert len(locate(["ta có 2x = 16 => x = 8"], "2x = 16 => x = 8")) == 2  # LLM gộp hai bước: tự tách


# ---------------------------------------------------------------- extractor trên bộ ca dev

@pytest.mark.parametrize("cid", sorted(CASES))
def test_dev_cases_with_faithful_llm(cid):
    case = CASES[cid]
    client, before = oracle_client()
    before(case)
    row = run_case(case, StepExtractor(client))
    assert row["exact"], row
    assert row["llm_called"] == case.needs_llm  # luật đủ thì không tốn lần gọi model


@pytest.mark.parametrize("cid", sorted(c.id for c in CASES.values() if c.needs_llm))
def test_cases_needing_llm_ask_again_without_one(cid):
    outcome = StepExtractor()(CASES[cid].problem_prompt, list(CASES[cid].lines))
    assert outcome.result.status == "needs_clarification" and outcome.usage is None
    assert set(reasons(outcome)) <= {"mixed_text", "syntax"}


def test_normalized_differs_from_source_only_by_deterministic_mapping():
    client, before = oracle_client()
    for case in CASES.values():
        before(case)
        for step in StepExtractor(client)(case.problem_prompt, list(case.lines)).result.steps:
            assert keys(step.source) == keys(step.normalized), case.id
            assert step.source in case.lines[step.line - 1] or step.source in " ".join(case.lines)


@pytest.mark.parametrize("cid", sorted(c.id for c in CASES.values() if c.oracle and c.status == "extracted"))
def test_any_altered_or_dropped_span_is_blocked(cid):
    # Với mọi ca LLM tách được: đổi một chữ số của một đoạn, hoặc bỏ một đoạn, đều phải bị chặn.
    case = CASES[cid]
    originals = case.oracle["spans"]
    for i, span in enumerate(originals):
        digit = next(ch for ch in span if ch.isdigit())
        altered = span.replace(digit, str((int(digit) + 1) % 10), 1)
        for mutated in (originals[:i] + [altered] + originals[i + 1:], originals[:i] + originals[i + 1:]):
            outcome = StepExtractor(FakeLLMClient([spans(*mutated)]))(case.problem_prompt, list(case.lines))
            assert outcome.result.status == "needs_clarification", (cid, mutated)
            assert set(outcome.result.reasons) & FIDELITY_REASONS, (cid, mutated)


def test_student_error_survives_extraction():
    outcome = extract(["em nhân vào được 2x - 3 = 10", "Vậy x = 6.5"], spans("2x - 3 = 10", "x = 6.5"))
    assert outcome.result.graded_lines() == ["2x-3=10", "x=6.5"] and outcome.result.method == "llm"
    assert [s.source for s in outcome.result.steps] == ["2x - 3 = 10", "x = 6.5"]


def test_restated_problem_is_kept_but_not_numbered():
    result = extract(["2(x − 3) = 10", "2x - 6 = 10", "x = 8"]).result
    assert [(s.role, s.index, s.line) for s in result.steps] == \
        [("restated_problem", None, 1), ("step", 1, 2), ("step", 2, 3)]
    # Phương trình chỉ giống một phần của đề thì không phải chép đề.
    assert extract(["x - 3 = 10", "x = 13"]).result.steps[0].role == "step"


def test_limits():
    assert reasons(extract([f"x = {i}" for i in range(13)])) == ["too_many_steps"]
    assert reasons(extract(["x = " + "+".join(["1"] * 90)])) == ["step_too_long"]


# ---------------------------------------------------------------- extractor: lỗi của LLM

def call(text, **kw):
    fields = dict(model_id="gpt-4o-mini-2024-07-18", input_tokens=500, cached_input_tokens=0, output_tokens=30,
                  latency_ms=700.0)
    fields.update(kw)
    return LLMCall(text=text, **fields)


PROSE = ["em nhân vào được 2x - 3 = 10"]


@pytest.mark.parametrize("item, reason, error", [
    (LLMTimeout(8000.0), "llm_unavailable", "timeout"),
    (LLMCallFailed("RateLimitError", 90.0), "llm_unavailable", "RateLimitError"),
    (call(None, refusal="no"), "llm_invalid_output", "refusal"),
    (call(None, incomplete_reason="max_output_tokens"), "llm_invalid_output", "incomplete:max_output_tokens"),
    (call('{"status": "extracted"'), "llm_invalid_output", "invalid_output"),
    (call(json.dumps({"status": "extracted", "spans": "2x - 3 = 10", "reasons": []})), "llm_invalid_output",
     "invalid_output"),
    (call(json.dumps({"status": "done", "spans": [], "reasons": []})), "llm_invalid_output", "invalid_output"),
])
def test_llm_failures_become_clarification_with_usage(item, reason, error):
    outcome = StepExtractor(FakeLLMClient([item], model="gpt-4o-mini"))(PROBLEM, PROSE)
    assert outcome.result.status == "needs_clarification" and reasons(outcome) == [reason]
    assert outcome.usage.error == error and outcome.usage.prompt_version == PROMPT_VERSION


def test_failed_call_has_unknown_tokens_and_successful_call_has_cost():
    failed = StepExtractor(FakeLLMClient([LLMTimeout(8000.0)], model="gpt-4o-mini"))(PROBLEM, PROSE)
    assert not failed.usage.tokens_known and failed.usage.cost_usd is None
    ok = StepExtractor(FakeLLMClient([call(json.dumps(spans("2x - 3 = 10")))]))(PROBLEM, PROSE)
    assert ok.result.status == "extracted" and ok.usage.cost_usd is not None and ok.usage.error is None


def test_llm_reasons_are_limited_to_what_the_llm_may_report():
    made_up = {"status": "needs_clarification", "spans": [], "reasons": ["not_verbatim", "anything"]}
    assert reasons(extract(PROSE, made_up)) == ["unreadable"]
    words = {"status": "needs_clarification", "spans": ["2x - 3 = 10"], "reasons": ["math_in_words"]}
    outcome = extract(PROSE, words)
    assert reasons(outcome) == ["math_in_words"] and outcome.result.steps == []


def test_llm_is_not_called_when_rules_decide():
    client = FakeLLMClient()  # gọi tới là lỗi vì không có đầu ra nào
    for lines in (["2x - 6 = 10", "x = 8"], ["x = 6,5"], ["em nghĩ x = 6,5"], ["8"], [""]):
        assert StepExtractor(client)(PROBLEM, lines).usage is None
    assert client.requests == []


def test_request_sends_only_problem_and_submission():
    client = FakeLLMClient([spans("2x - 3 = 10")])
    StepExtractor(client)(PROBLEM, PROSE)
    request = client.requests[0]
    assert json.loads(request["input"]) == {"problem": PROBLEM, "lines": PROSE}
    assert request["instructions"] == INSTRUCTIONS and request["schema"] == OUTPUT_SCHEMA


def test_prompt_and_schema_cover_llm_reasons():
    enum = OUTPUT_SCHEMA["properties"]["reasons"]["items"]["enum"]
    assert set(enum) == {r.value for r in LLM_REASONS}
    assert all(value in INSTRUCTIONS for value in enum)
    assert OUTPUT_SCHEMA["additionalProperties"] is False
    assert sorted(OUTPUT_SCHEMA["required"]) == sorted(OUTPUT_SCHEMA["properties"])


def test_extractor_scope_is_the_grammar_concepts():
    extractor = StepExtractor()
    assert extractor.applies_to("E02") and not extractor.applies_to("A02")


# ---------------------------------------------------------------- hợp đồng

def step(**kw):
    fields = dict(role="step", index=1, line=1, source="x = 8", normalized="x=8")
    fields.update(kw)
    return ExtractedStep(**fields)


def test_result_contract():
    ok = ExtractionResult(grammar_version=GRAMMAR_VERSION, status="extracted", method="rules", steps=[step()])
    assert ok.graded_lines() == ["x=8"]
    bad = [
        dict(status="extracted", steps=[]),                                         # không có bước
        dict(status="extracted", steps=[step()], reasons=[Reason.SYNTAX]),          # vừa tách vừa có lý do
        dict(status="needs_clarification", steps=[step()], reasons=[Reason.SYNTAX]),  # hỏi lại mà vẫn đưa bước
        dict(status="needs_clarification"),                                         # hỏi lại không lý do
        dict(status="extracted", steps=[step(index=2)]),                            # đánh số sai
        dict(status="extracted", steps=[step(), step(role="restated_problem", index=None)]),
    ]
    for fields in bad:
        with pytest.raises(ValueError):
            ExtractionResult(grammar_version=GRAMMAR_VERSION, method="rules", **fields)
    with pytest.raises(ValueError):
        step(role="restated_problem")  # dòng chép đề không có số bước


def test_record_traces_llm_only_when_called():
    by_rules = extract(["x = 8"]).record(uuid4())
    assert (by_rules.extractor_version, by_rules.prompt_version, by_rules.usage) == (EXTRACTOR_VERSION, None, None)
    by_llm = extract(PROSE, spans("2x - 3 = 10")).record(uuid4())
    assert by_llm.prompt_version == PROMPT_VERSION and by_llm.usage is not None
    with pytest.raises(ValueError):
        ExtractionRecord(turn_id=uuid4(), extractor_version="x", prompt_version="p", result=by_rules.result)
    with pytest.raises(ValueError):  # đầu ra thô chỉ có khi đã gọi LLM
        ExtractionRecord(turn_id=uuid4(), extractor_version="x", result=by_rules.result, llm_output="{}")


def test_record_keeps_raw_llm_output_even_when_blocked():
    # Review: bị chốt chặn từ chối thì phải còn đúng đoạn model đã trả, để phân biệt model sai với chặn nhầm.
    raw = json.dumps(spans("x = 6"))
    blocked = StepExtractor(FakeLLMClient([call(raw)]))(PROBLEM, ["em có 2x = 6"])
    assert blocked.result.status == "needs_clarification" and blocked.record(uuid4()).llm_output == raw
    refused = StepExtractor(FakeLLMClient([call(None, refusal="no")]))(PROBLEM, PROSE)
    assert refused.llm_output == "no"
    failed = StepExtractor(FakeLLMClient([LLMTimeout(8000.0)], model="gpt-4o-mini"))(PROBLEM, PROSE)
    assert failed.llm_output is None and failed.usage is not None
    assert extract(["x = 8"]).llm_output is None  # luật xử lý, không gọi LLM


# ---------------------------------------------------------------- trong LangGraph

class SpyAnalyzer(StubAnalyzer):
    def __init__(self):
        self.seen = []

    def __call__(self, state, steps):
        self.seen.append(list(steps))
        return super().__call__(state, steps)


def engine_with(client=None):
    analyzer = SpyAnalyzer()
    engine = TutorEngine(CONFIG, Services(analyzer=analyzer, extractor=StepExtractor(client)))
    return engine, analyzer, engine.start("demo-a", "E02-P001").session_id


def submit(engine, sid, message=None, steps=()):
    return engine.turn(sid, TurnInput(request_id=uuid4(), trigger="submit", steps=list(steps), message=message))


def test_engine_grades_extracted_steps_and_logs_the_call():
    client = FakeLLMClient([call(json.dumps(spans("2x - 3 = 10", "x = 6.5")))])
    engine, analyzer, sid = engine_with(client)
    reply = submit(engine, sid, "em nhân 2 vào ngoặc được 2x - 3 = 10\nVậy x = 6.5")
    assert analyzer.seen == [["2x-3=10", "x=6.5"]] and reply.action == "diagnose"
    state = engine.state(sid)
    assert state.latest_assessment.assessment_status == "verified_incorrect"
    assert state.latest_submission == ["2x-3=10", "x=6.5"]  # Agent thấy đúng bài đã chấm
    (record,) = engine.extractions(sid)
    assert record.result.method == "llm" and record.usage.cost_usd is not None and record.turn_id == state.turn_id


def test_engine_asks_again_without_grading_when_extraction_is_unsure():
    engine, analyzer, sid = engine_with()
    reply = submit(engine, sid, steps=["2x = 13", "x = 6,5"])
    assert analyzer.seen == [] and (reply.action, reply.intent) == ("clarify", "resolve_input")
    state = engine.state(sid)
    assert state.latest_assessment.assessment_status == "needs_clarification"
    assert state.observation.eligible is False and state.skills == []  # không ghi BKT (FR04-AC2)
    assert engine.extractions(sid)[0].result.reasons == [Reason.DECIMAL_COMMA]


def test_engine_rules_only_extraction_needs_no_llm():
    engine, analyzer, sid = engine_with()
    submit(engine, sid, steps=["2(x − 3) = 10", "2x − 6 = 10", "x = 8"])
    assert analyzer.seen == [["2x-6=10", "x=8"]]  # dòng chép đề không đưa vào chấm
    (record,) = engine.extractions(sid)
    assert record.usage is None and record.result.method == "rules"
    # Làm đúng thì Agent giao bài mới và xóa kết quả chấm của bài cũ; kết quả nằm trong lịch sử lượt.
    graded = [t.assessment_status for t in engine.state(sid).recent_turns if t.actor == "student"]
    assert graded == ["verified_correct"]


class FlakyAnalyzer(SpyAnalyzer):
    """Lỗi ở lần gọi đầu, chạy bình thường từ lần sau."""

    def __call__(self, state, steps):
        if not self.seen:
            self.seen.append(None)
            raise RuntimeError("analyzer down")
        return super().__call__(state, steps)


def test_analyzer_failure_keeps_extraction_and_retry_reuses_it():
    # Review: extraction và analyzer từng nằm chung một node, nên analyzer lỗi làm mất log extraction
    # và khi gửi lại thì LLM bị gọi lần hai (tốn thêm, kết quả có thể khác).
    client = FakeLLMClient([call(json.dumps(spans("2x - 3 = 10"))), call(json.dumps(spans("2x - 6 = 10")))])
    analyzer = FlakyAnalyzer()
    engine = TutorEngine(CONFIG, Services(analyzer=analyzer, extractor=StepExtractor(client)))
    sid = engine.start("demo-a", "E02-P001").session_id
    turn = TurnInput(request_id=uuid4(), trigger="submit", message="em nhân vào được 2x - 3 = 10")
    with pytest.raises(RuntimeError):
        engine.turn(sid, turn)
    assert len(client.requests) == 1 and len(engine.extractions(sid)) == 1
    engine.turn(sid, turn)
    assert len(client.requests) == 1 and len(engine.extractions(sid)) == 1
    assert analyzer.seen[-1] == ["2x-3=10"]  # đúng kết quả đã lưu, không phải lần gọi thứ hai


def test_extraction_of_one_turn_is_not_reused_by_the_next():
    client = FakeLLMClient([call(json.dumps(spans("2x - 3 = 10")))])
    engine, analyzer, sid = engine_with(client)
    submit(engine, sid, "em nhân vào được 2x - 3 = 10")
    engine.turn(sid, TurnInput(request_id=uuid4(), trigger="request_hint"))
    submit(engine, sid, steps=["2x - 6 = 10", "x = 8"])
    assert analyzer.seen == [["2x-3=10"], ["2x-6=10", "x=8"]]
    assert [r.result.method for r in engine.extractions(sid)] == ["llm", "rules"]


def test_extraction_is_skipped_outside_its_concepts_and_when_disabled():
    analyzer = SpyAnalyzer()
    scoped = TutorEngine(CONFIG, Services(analyzer=analyzer, extractor=StepExtractor()))
    sid = scoped.start("demo-a", "A02-P001").session_id  # A02 nằm ngoài grammar g2-v1
    submit(scoped, sid, steps=["-6y - 8"])
    assert analyzer.seen == [["-6y - 8"]] and scoped.extractions(sid) == []

    disabled = TutorEngine(CONFIG)
    sid = disabled.start("demo-a", "E02-P001").session_id
    submit(disabled, sid, steps=["2x - 6 = 10"])
    assert disabled.extractions(sid) == []


# ---------------------------------------------------------------- script đánh giá (không gọi API)

def test_evaluation_with_oracle():
    client, before = oracle_client()
    cases = list(CASES.values())
    summary = summarize(evaluate(cases, client, before))
    assert summary["exact"] == summary["cases"] == len(cases)
    assert summary["llm_calls"] == sum(c.needs_llm for c in cases) and summary["fidelity_blocks"] == 0
    assert summary["clarification_precision"] == summary["clarification_recall"] == 1.0


def test_evaluation_counts_fidelity_blocks():
    case = CASES["EX-20"]
    client = FakeLLMClient([spans("2x - 6 = 10", "2x = 13", "x = 6.5")])  # LLM "sửa giúp" bước sai
    summary = summarize(evaluate([case], client))
    assert (summary["exact"], summary["fidelity_blocks"], summary["silent_changes"]) == (0, 1, 0)


def test_evaluation_counts_silent_changes_against_the_answer_key():
    # Ca lọt không bị chặn nên fidelity_blocks không thấy; chỉ so với đáp án của ca mới phát hiện được.
    client, before = oracle_client()
    case = CASES["EX-20"]
    wrong_key = dataclasses.replace(case, steps=("2x-6=10", "2x=16", "x=8"))
    before(case)
    row = run_case(wrong_key, StepExtractor(client))
    assert row["silent_change"] and not row["fidelity_block"]
    should_ask = dataclasses.replace(CASES["EX-01"], status="needs_clarification", steps=(), reasons=frozenset({"x"}))
    assert run_case(should_ask, StepExtractor())["silent_change"]


def test_evaluation_rows_are_reproducible():
    client, before = oracle_client()
    run = run_info("fake", client)
    rows = evaluate([CASES["EX-20"]], client, before, run)
    assert rows[0]["run"] == run and rows[0]["llm_output"] == json.dumps(CASES["EX-20"].oracle, ensure_ascii=False)
    assert {"extractor_version", "prompt_version", "grammar_version", "model", "cases_file"} <= set(run)


def test_cases_file_is_consistent():
    assert len(CASES) == 32
    for case in CASES.values():
        assert case.needs_llm == (case.oracle is not None), case.id
        assert (case.status == "extracted") == bool(case.steps) == (not case.reasons), case.id


def test_openai_mode_refuses_without_confirmation(monkeypatch):
    monkeypatch.setattr("research.llm_support.read_env", lambda: {"LLM_ENABLED": "true", "OPENAI_API_KEY": "sk-test"})

    def forbidden(*args, **kwargs):
        raise AssertionError("must not build a real client")

    monkeypatch.setattr("research.llm_support.OpenAIResponsesClient", forbidden)
    assert main(["--llm", "openai"]) == 2
    assert main(["--llm", "openai", "--max-calls", "3", "--yes"]) == 2
    monkeypatch.setattr("research.llm_support.read_env", lambda: {})
    assert main(["--llm", "openai", "--yes"]) == 2
