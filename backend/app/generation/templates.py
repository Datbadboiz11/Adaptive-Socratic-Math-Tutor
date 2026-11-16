"""Template phản hồi theo intent: đường sinh chính khi không bật LLM, và câu dự phòng khi câu của LLM
không đạt (PRD FR12-AC1, FR09-AC3).

Template chỉ chèn nội dung đã truy xuất mà quyết định trích, đề bài công khai và số bước sai; không
nhận đáp án. Chữ trong template là bản nháp của Member 3, chưa qua người duyệt nội dung; đổi chữ thì
tăng ``TEMPLATE_VERSION``.
"""
from __future__ import annotations

from app.agent.decision import DecisionIntent, DecisionProposal
from app.generation.contracts import ResponseInput

TEMPLATE_VERSION = "templates-0.2.0"

I = DecisionIntent

TEMPLATES = {
    I.RESOLVE_INPUT: "Mình chưa đọc được bài làm này. Em viết mỗi bước trên một dòng, ví dụ: 2x + 1 = 7 nhé.",
    I.RESTATE_TASK: "Mình cùng đọc lại đề nhé: {prompt} Đề bài đang yêu cầu em tìm gì?",
    I.ELICIT_REASONING: "Em giải thích giúp mình vì sao em viết được bước{step} như vậy không?",
    I.DISTINGUISH_HYPOTHESIS: "Ở bước{step}, em đã biến đổi phần nào của biểu thức? "
                              "Em kiểm tra xem phép biến đổi đó đã áp dụng cho đủ các phần chưa nhé.",
    I.PROBE_PREREQUISITE: "Trước khi làm tiếp, em thử trả lời câu này nhé: {content}",
    I.PROMPT_SELF_CHECK: "Em thử thay kết quả vào đề bài để tự kiểm tra lại nhé.",
    I.LOCATE_ERROR: "Bài làm có chỗ cần xem lại ở bước{step}. {content}",
    I.RECALL_RULE: "{content}",
    I.TARGET_MISCONCEPTION: "{content}",
    I.DECOMPOSE_STEP: "Mình chia nhỏ bước này nhé. {content} Giờ em làm lại riêng bước{step} thôi.",
    I.ANALOGOUS_EXAMPLE: "Mình xem một ví dụ khác trước nhé. {content} Giờ em thử áp dụng vào bài của mình.",
    I.EXPLAIN_CONCEPT: "{content} Em thử làm lại bài của mình theo cách này nhé.",
    I.REVIEW_PREREQUISITE: "Mình cùng ôn một kiến thức nền trước, xong sẽ quay lại bài cũ. Bài ôn: {new_prompt}",
    I.INDEPENDENT_CHECK: "Em sửa được rồi! Giờ em tự làm bài mới này nhé, không có gợi ý: {new_prompt}",
    I.CONTINUE_PRACTICE: "Đúng rồi! Em làm tiếp bài này nhé: {new_prompt}",
    I.ADVANCE_DIFFICULTY: "Em làm tốt rồi. Mình thử một bài khó hơn nhé: {new_prompt}",
    I.ADVANCE_CONCEPT: "Em đã sẵn sàng cho phần tiếp theo. Bài mới: {new_prompt}",
    I.RETURN_TO_PARENT: "Tốt lắm! Giờ mình quay lại bài lúc nãy nhé: {new_prompt}",
    I.SWITCH_PROBLEM: "Mình đổi sang một bài khác để thử cách tiếp cận mới nhé: {new_prompt}",
    I.STUDENT_REQUEST: "Mình tạm dừng ở đây nhé. Lần sau em có thể tiếp tục từ bài đang làm.",
    I.SESSION_GOAL_MET: "Em đã hoàn thành mục tiêu của buổi học hôm nay. Hẹn gặp lại!",
    I.BUDGET_EXHAUSTED: "Buổi học hôm nay đến đây là hết thời lượng. Em có thể tiếp tục vào lần sau.",
    I.STUCK_LIMIT: "Mình đã thử nhiều cách cho bước này rồi. Em nghỉ một chút rồi quay lại sau nhé.",
    I.CONTENT_EXHAUSTED: "Em đã làm hết bài luyện của phần này trong buổi hôm nay. Mình tạm dừng, lần sau học tiếp nhé.",
    I.SYSTEM_FALLBACK: "Hệ thống đang trục trặc nên mình tạm dừng lượt này. Bài làm của em đã được lưu.",
}
GENERIC_CONTENT = {
    I.RECALL_RULE: "Em nhớ lại quy tắc của dạng bài này rồi áp dụng vào bước đang làm nhé.",
    I.TARGET_MISCONCEPTION: "Em thử giải thích lại quy tắc em đã dùng ở bước này bằng lời của mình nhé.",
    I.PROBE_PREREQUISITE: "em nhắc lại quy tắc nền của dạng bài này giúp mình nhé.",
}

# Dùng thay GENERIC_CONTENT khi biết tên chủ đề của skill được nhắm: câu hỏi về một skill nền phải
# nói được nó hỏi về phần nào.
TOPIC_CONTENT = {
    I.PROBE_PREREQUISITE: 'em nhắc lại bằng lời của mình cách làm của phần "{topic}" được không?',
}

# Câu dừng cố định khi cả template cũng không qua kiểm tra.
SYSTEM_MESSAGE = "Mình cần kiểm tra lại câu trả lời này. Em đợi một chút rồi gửi lại nhé."


def _generic(intent: DecisionIntent, topic: str | None = None) -> str:
    if topic and intent in TOPIC_CONTENT:
        return TOPIC_CONTENT[intent].format(topic=topic)
    return GENERIC_CONTENT.get(intent, "")


def _fill(intent: DecisionIntent, **values: str) -> str:
    return " ".join(TEMPLATES[intent].format(**values).split())


class TemplateGenerator:
    """Sinh câu từ template + nội dung được trích. Không nhận đáp án hay lời giải của bài."""

    def __call__(self, inp: ResponseInput) -> str:
        p, a = inp.decision, inp.assessment
        content = " ".join(c.text for c in inp.content)
        return _fill(p.intent, content=content or _generic(p.intent, inp.target_skill_title),
                     step=f" {a.first_error_step}" if a and a.first_error_step else " vừa rồi",
                     prompt=inp.problem_prompt or "", new_prompt=inp.new_problem_prompt or "")

    def safe(self, p: DecisionProposal) -> str:
        """Bản dự phòng không chèn nội dung truy xuất hay đề bài."""
        return _fill(p.intent, content=_generic(p.intent), step=" vừa rồi", prompt="", new_prompt="")
