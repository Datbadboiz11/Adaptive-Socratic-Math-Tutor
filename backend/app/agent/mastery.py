"""Ước lượng mức nắm vững và bằng chứng thiếu skill nền, dùng chung cho gate và Rule-policy.

Ngưỡng là giá trị khởi đầu để thử trên dev (plan §10), chưa phải ngưỡng đã chốt.
"""
from __future__ import annotations

from typing import Literal

from app.agent.decision import SkillState, StudentState

# Ngưỡng theo loại ước lượng. Plan §18.2: ngưỡng của Heuristic phải chọn riêng trên dev, không
# áp nguyên ngưỡng xác suất BKT. Hiện hai bộ có cùng giá trị khởi đầu, CHƯA tune.
THRESHOLDS = {
    "bkt": {"low": 0.4, "good": 0.6, "ready": 0.8},
    "recent_ratio": {"low": 0.4, "good": 0.6, "ready": 0.8},
}
MIN_OBSERVATIONS_FOR_ESTIMATE = 2

PrerequisiteEvidence = Literal["error_attributed", "probe_failed", "hypothesis", "low_estimate"]


def estimate(skill: SkillState | None, view: str = "bkt") -> tuple[float | None, int]:
    """Ước lượng mức nắm vững và số bằng chứng theo ``StudentState.mastery_view``.

    - ``bkt``: P(L) do BKT tính.
    - ``recent_ratio`` (Heuristic): tỷ lệ đúng của tối đa 5 observation độc lập gần nhất.
    - ``none`` (No-BKT): không có ước lượng; policy chỉ dùng bằng chứng của lượt hiện tại.
    """
    if skill is None:
        return None, 0
    if view == "bkt":
        return skill.p_mastery, skill.independent_observations
    if view == "recent_ratio" and skill.recent_independent:
        return sum(skill.recent_independent) / len(skill.recent_independent), len(skill.recent_independent)
    return None, skill.independent_observations


def threshold(s: StudentState, name: str) -> float:
    return THRESHOLDS[s.mastery_view][name]


def standing(s: StudentState, skill_id: str) -> Literal["low", "good", "unknown"]:
    """Xếp một skill theo ước lượng hiện có: thấp, tốt, hoặc chưa đủ bằng chứng để nói."""
    value, n = estimate(s.skill(skill_id), s.mastery_view)
    if value is None or n < MIN_OBSERVATIONS_FOR_ESTIMATE:
        return "unknown"
    if value < threshold(s, "low"):
        return "low"
    return "good" if value >= threshold(s, "good") else "unknown"


def prerequisite_evidence(s: StudentState, skill_id: str) -> PrerequisiteEvidence | None:
    """Bằng chứng cho thấy học sinh có thể đang thiếu skill nền này (PRD FR08-AC3).

    Graph chỉ đưa ra ứng viên; muốn coi một prerequisite là điểm yếu thì phải có một trong:
    lỗi vừa chấm được quy cho skill đó, câu trả lời cho câu hỏi kiểm tra skill đó đã được xác
    minh là chưa đạt, một giả thuyết lỗi còn mở trên skill đó, hoặc ước lượng thấp từ lịch sử.
    Việc tutor đã hỏi kiểm tra mà chưa có câu trả lời được xác minh thì KHÔNG phải bằng chứng."""
    a = s.latest_assessment
    if a is not None and a.assessment_status == "verified_incorrect" and a.primary_skill_id == skill_id:
        return "error_attributed"
    if any(q.skill_id == skill_id and q.status == "not_demonstrated" for q in s.probes):
        return "probe_failed"
    if any(h.skill_id == skill_id and h.status in {"suspected", "supported"} for h in s.hypotheses):
        return "hypothesis"
    if standing(s, skill_id) == "low":
        return "low_estimate"
    return None


def probed(s: StudentState, skill_id: str) -> bool:
    """Đã hỏi kiểm tra skill này trên bài hiện tại chưa (bất kể kết quả)."""
    return any(q.skill_id == skill_id for q in s.probes)
