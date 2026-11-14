"""Rule-policy v1: chọn action bằng luật cố định theo bảng plan §9.

Dùng cho hai việc: fallback khi Agent lỗi hoặc bị gate từ chối, và baseline Rule-policy của RQ5.
Mọi đề xuất ở đây phải qua được policy gate; test kiểm tra điều đó trên bộ tình huống mẫu.
Ngưỡng là giá trị khởi đầu để thử trên dev (plan §10), chưa phải ngưỡng đã chốt.
"""
from __future__ import annotations

from app.agent.decision import (
    MAX_BACKTRACK_DEPTH, MAX_SUPPORT_TURNS_PER_NODE, DecisionIntent, DecisionProposal,
    EvidenceKind, EvidenceRef, Hypothesis, PedagogicalAction, Readiness, StudentState,
)
from app.agent.mastery import estimate, prerequisite_evidence, probed, standing, threshold
from app.agent.tools import GraphEdge, NextConcept, ProblemRef, RetrievedContent, TurnContext

POLICY_VERSION = "rule-policy-0.4.0"
READINESS_VERSION = "stop-0.1.0"

A, I = PedagogicalAction, DecisionIntent

# Họ lỗi coi là lỗi thao tác (plan §9: "lỗi số học đơn lẻ, lịch sử tốt"). Cần khớp mã họ lỗi của Member 1.
CARELESS_FAMILIES = frozenset({"arithmetic_error", "sign_error", "copy_error"})
READY_MIN_OBSERVATIONS = 3
ESCALATE_AFTER_NO_PROGRESS = 2

# Thứ tự ưu tiên giữa các loại bằng chứng khi chọn prerequisite để ôn (mạnh nhất trước).
EVIDENCE_ORDER = {"error_attributed": 0, "probe_failed": 1, "hypothesis": 2, "low_estimate": 3}


# --------------------------------------------------------------------------- helpers

def compute_readiness(s: StudentState) -> Readiness:
    """Điều kiện xem xét chuyển concept (plan §10). Chưa kiểm tra 'hai bài thuộc mẫu khác nhau'.

    No-BKT không có ước lượng nên bỏ điều kiện ngưỡng, chỉ giữ điều kiện trên evidence log:
    đủ số observation, hai lần độc lập gần nhất đúng, không còn giả thuyết lỗi mở."""
    skill_id = s.current.target_skill_id
    skill = s.skill(skill_id)
    value, _ = estimate(skill, s.mastery_view)
    unmet = []
    if skill is None or skill.independent_observations < READY_MIN_OBSERVATIONS:
        unmet.append("too_few_observations")
    if s.mastery_view != "none" and (value is None or value < threshold(s, "ready")):
        unmet.append("estimate_below_threshold")
    if skill is None or skill.recent_independent[-2:] != [True, True]:
        unmet.append("last_two_not_correct")
    if any(h.skill_id == skill_id and h.status in {"suspected", "supported"} for h in s.hypotheses):
        unmet.append("unresolved_hypothesis")
    return Readiness(ready_to_advance=not unmet, criteria_version=READINESS_VERSION, unmet=unmet)


def _proposal(action, intent, reason, *, skill=None, level=0, evidence=(), content=None, edge=None,
              problem=None) -> DecisionProposal:
    """``edge`` là cạnh KG làm căn cứ: GraphEdge (prerequisite) hoặc NextConcept (concept kế tiếp)."""
    return DecisionProposal(
        action=action, intent=intent, target_skill_id=skill, hint_level=level, evidence=list(evidence),
        content_ids=[content.content_id] if content else [], edge_ids=[edge.edge_id] if edge else [],
        problem_id=problem.problem_id if isinstance(problem, ProblemRef) else problem, reason=reason)


def _end(intent, reason) -> DecisionProposal:
    return _proposal(A.END_SESSION, intent, reason)


def _assessment_ref(s: StudentState) -> list[EvidenceRef]:
    return [EvidenceRef(kind=EvidenceKind.ASSESSMENT, id=str(s.latest_assessment.assessment_id))]


def _message_ref(s: StudentState) -> list[EvidenceRef]:
    return [EvidenceRef(kind=EvidenceKind.STUDENT_MESSAGE, id=str(s.turn_id))]


def _hypothesis_ref(h: Hypothesis) -> EvidenceRef:
    return EvidenceRef(kind=EvidenceKind.HYPOTHESIS, id=h.hypothesis_id)


def _pick_content(ctx: TurnContext, skill_id, types, max_level) -> RetrievedContent | None:
    options = [c for c in ctx.retrieved
               if c.skill_id == skill_id and c.content_type in types and c.disclosure_level <= max_level]
    return max(options, key=lambda c: c.disclosure_level, default=None)


def _question_content(ctx: TurnContext, skill_id, max_level) -> RetrievedContent | None:
    """Câu hỏi khái niệm phải là câu hỏi: ưu tiên nội dung loại question, rồi mới tới hint."""
    return _pick_content(ctx, skill_id, {"question"}, max_level) or _pick_content(ctx, skill_id, {"hint"}, max_level)


def _pick_problem(ctx: TurnContext, s: StudentState, skill_id, *, other_family=False,
                  concept_id=None, harder_than=None) -> ProblemRef | None:
    for p in sorted(ctx.problems, key=lambda p: (p.difficulty, p.problem_id)):
        if p.target_skill_id != skill_id or p.problem_id == s.current.problem_id \
                or p.problem_id in s.attempted_problem_ids:
            continue
        if other_family and p.template_family_id == s.current.template_family_id:
            continue
        if concept_id is not None and p.concept_id != concept_id:
            continue
        if harder_than is not None and p.difficulty <= harder_than:
            continue
        return p
    return None


def _active_hypothesis(s: StudentState, skill_id) -> Hypothesis | None:
    active = [h for h in s.hypotheses if h.skill_id == skill_id and h.status in {"suspected", "supported"}]
    return max(active, key=lambda h: (h.status == "supported", len(h.evidence_ids)), default=None)


def _last_tutor_action(s: StudentState) -> PedagogicalAction | None:
    for turn in reversed(s.recent_turns):
        if turn.actor == "tutor" and turn.action is not None:
            return turn.action
    return None


def _prerequisite_edges(s: StudentState, ctx: TurnContext) -> list[GraphEdge]:
    """Prerequisite trực tiếp (tầng 1) của concept đang học, bỏ concept đã ghé trong nhánh này.
    Tầng 2 chỉ để Agent tham khảo: mỗi bước backtrack lùi đúng một tầng."""
    branch = {s.current.concept_id} | {f.concept_id for f in s.return_stack}
    return [e for e in ctx.edges if e.depth == 1 and e.target_concept_id == s.current.concept_id
            and e.source_concept_id not in branch]


def _backtrack(s: StudentState, ctx: TurnContext, reason) -> DecisionProposal | None:
    """Ôn một prerequisite trực tiếp mà học sinh có bằng chứng đang thiếu (FR08-AC3). Graph chỉ
    đưa ứng viên: prerequisite chưa có bằng chứng thì không được chọn ở đây."""
    if len(s.return_stack) >= MAX_BACKTRACK_DEPTH:
        return None
    candidates = []
    for edge in _prerequisite_edges(s, ctx):
        for skill in edge.source_skill_ids:
            kind = prerequisite_evidence(s, skill)
            if kind is not None:
                candidates.append((EVIDENCE_ORDER[kind], edge.edge_id, skill, edge, kind))
    for _, _, skill, edge, kind in sorted(candidates, key=lambda c: c[:3]):
        problem = _pick_problem(ctx, s, skill, concept_id=edge.source_concept_id)
        if problem is not None:
            return _proposal(A.BACKTRACK, I.REVIEW_PREREQUISITE, f"{reason} Căn cứ: {kind}.", skill=skill,
                             evidence=_assessment_ref(s), edge=edge, problem=problem)
    return None


def _weak_prerequisite(s: StudentState, ctx: TurnContext) -> tuple[GraphEdge, str] | None:
    for edge in _prerequisite_edges(s, ctx):
        for skill_id in edge.source_skill_ids:
            if standing(s, skill_id) == "low":
                return edge, skill_id
    return None


def _unchecked_prerequisite(s: StudentState, ctx: TurnContext) -> tuple[GraphEdge, str] | None:
    """Prerequisite trực tiếp chưa có bằng chứng gì (không yếu, không tốt), chưa hỏi kiểm tra trên
    bài này và có bài để ôn: ứng viên để hỏi kiểm tra trước khi quyết định có backtrack hay không."""
    for edge in sorted(_prerequisite_edges(s, ctx), key=lambda e: e.edge_id):
        for skill_id in edge.source_skill_ids:
            if standing(s, skill_id) == "unknown" and prerequisite_evidence(s, skill_id) is None \
                    and not probed(s, skill_id) \
                    and _pick_problem(ctx, s, skill_id, concept_id=edge.source_concept_id) is not None:
                return edge, skill_id
    return None


def _next_concept(s: StudentState, ctx: TurnContext) -> tuple[NextConcept, ProblemRef] | None:
    """Concept kế tiếp trên KG. Bỏ concept còn prerequisite khác đang yếu; ưu tiên concept mà
    các prerequisite khác đã có bằng chứng tốt."""
    ranked = []
    for candidate in ctx.next_concepts:
        standings = [standing(s, skill_id) for skill_id in candidate.other_prerequisite_skill_ids]
        if "low" not in standings:
            ranked.append((standings.count("unknown"), candidate.concept_id, candidate))
    for _, _, candidate in sorted(ranked, key=lambda r: r[:2]):
        problem = next((p for p in sorted(ctx.problems, key=lambda p: (p.difficulty, p.problem_id))
                        if p.concept_id == candidate.concept_id
                        and p.problem_id not in s.attempted_problem_ids), None)
        if problem is not None:
            return candidate, problem
    return None


# --------------------------------------------------------------------------- policy

def rule_policy(s: StudentState, ctx: TurnContext) -> DecisionProposal:
    if s.trigger == "pause":
        return _end(I.STUDENT_REQUEST, "Học sinh xin tạm dừng.")
    a, support = s.latest_assessment, s.support

    # Giới hạn hỗ trợ chỉ áp khi bài chưa giải được: vừa làm đúng thì đi tiếp bình thường (ví dụ quay
    # lại bài gốc sau khi giải được bài nền), dù đã hỗ trợ đủ 6 lượt.
    solved = a is not None and a.assessment_status == "verified_correct"
    if support.support_turns_on_node >= MAX_SUPPORT_TURNS_PER_NODE and not solved:
        evidence = _assessment_ref(s) if a else _message_ref(s)
        problem = _pick_problem(ctx, s, s.current.target_skill_id)
        if problem is not None:
            return _proposal(A.NEXT_PROBLEM, I.SWITCH_PROBLEM, "Đã hỗ trợ 6 lượt trên cùng bước mà chưa tiến triển.",
                             skill=problem.target_skill_id, evidence=evidence, problem=problem)
        return _end(I.STUCK_LIMIT, "Đã hỗ trợ 6 lượt trên cùng bước và không còn bài thay thế.")

    if s.trigger == "resume" or (a is None and s.trigger == "message"):
        return _proposal(A.CLARIFY, I.RESTATE_TASK, "Bắt đầu lại hoặc chưa có bài làm để chấm; nhắc lại đề.",
                         evidence=_message_ref(s))
    if a is None:
        level = min(support.hint_level + 1, 2)
        return _proposal(A.MINIMAL_HINT, I.RECALL_RULE, "Học sinh xin gợi ý trước khi nộp bài.",
                         skill=s.current.target_skill_id, level=level, evidence=_message_ref(s),
                         content=_pick_content(ctx, s.current.target_skill_id, {"hint"}, level))
    if a.assessment_status in {"unverified", "needs_clarification"}:
        return _proposal(A.CLARIFY, I.RESOLVE_INPUT, "Bài làm chưa chấm được; cần học sinh viết rõ hơn.",
                         evidence=_assessment_ref(s))
    if a.assessment_status == "verified_correct":
        return _after_correct(s, ctx)
    return _after_incorrect(s, ctx)


def _after_correct(s: StudentState, ctx: TurnContext) -> DecisionProposal:
    skill_id, evidence = s.current.target_skill_id, _assessment_ref(s)
    if s.return_stack:
        frame = s.return_stack[-1]
        return _proposal(A.NEXT_PROBLEM, I.RETURN_TO_PARENT, "Đã làm đúng bài prerequisite; quay lại bài trước.",
                         skill=frame.skill_id, evidence=evidence, problem=frame.problem_id)
    assisted = s.support.hint_level > 0 or s.support.support_turns_on_node > 0
    if assisted:
        problem = _pick_problem(ctx, s, skill_id, other_family=True)
        if problem is not None:
            return _proposal(A.CHECK_TRANSFER, I.INDEPENDENT_CHECK, "Đúng sau hỗ trợ; cần bài khác họ mẫu, không hint.",
                             skill=skill_id, evidence=evidence, problem=problem)
    if s.readiness.ready_to_advance:
        # Concept tiếp theo là concept nhận concept hiện tại làm prerequisite (cạnh đi ra trong KG).
        # Không có KG (No-KG) thì chỉ tăng độ khó trong concept hiện tại.
        following = _next_concept(s, ctx)
        if following is not None:
            candidate, problem = following
            return _proposal(A.NEXT_PROBLEM, I.ADVANCE_CONCEPT,
                             f"Đủ điều kiện sẵn sàng; chuyển sang {candidate.concept_id} qua {candidate.edge_id}.",
                             skill=problem.target_skill_id, evidence=evidence, edge=candidate, problem=problem)
        known = ctx.problem(s.current.problem_id)
        difficulty = s.current.difficulty if s.current.difficulty is not None else (known.difficulty if known else None)
        problem = _pick_problem(ctx, s, skill_id, harder_than=difficulty) if difficulty is not None else None
        if problem is not None:
            return _proposal(A.NEXT_PROBLEM, I.ADVANCE_DIFFICULTY, "Đủ điều kiện sẵn sàng; tăng độ khó.",
                             skill=skill_id, evidence=evidence, problem=problem)
        return _end(I.SESSION_GOAL_MET, "Đủ điều kiện sẵn sàng và đã hết bài trong phạm vi.")
    problem = _pick_problem(ctx, s, skill_id, other_family=True) or _pick_problem(ctx, s, skill_id)
    if problem is not None:
        return _proposal(A.NEXT_PROBLEM, I.CONTINUE_PRACTICE, "Làm đúng nhưng chưa đủ bằng chứng sẵn sàng.",
                         skill=skill_id, evidence=evidence, problem=problem)
    return _end(I.CONTENT_EXHAUSTED, "Không còn bài phù hợp để luyện tiếp.")


def _after_incorrect(s: StudentState, ctx: TurnContext) -> DecisionProposal:
    a, support = s.latest_assessment, s.support
    skill_id = a.primary_skill_id or s.current.target_skill_id
    evidence = _assessment_ref(s)
    level = support.hint_level
    step = f" ở bước {a.first_error_step}" if a.first_error_step else ""

    if level >= 3:
        back = _backtrack(s, ctx, "Đã lên mức hint 3 mà vẫn sai; ôn prerequisite rồi quay lại.")
        if back is not None:
            return back
        unchecked = _unchecked_prerequisite(s, ctx) if _last_tutor_action(s) != A.DIAGNOSE else None
        if unchecked is not None:
            edge, prereq_skill = unchecked
            return _proposal(A.DIAGNOSE, I.PROBE_PREREQUISITE,
                             "Mức hint cao vẫn kẹt, chưa có bằng chứng về skill nền; hỏi kiểm tra trước khi ôn.",
                             skill=prereq_skill, evidence=evidence, edge=edge)
        new_level = min(level + 1, 4)
        content = _pick_content(ctx, skill_id, {"example", "explanation", "template"}, new_level)
        if content is not None:
            intent = I.EXPLAIN_CONCEPT if new_level == 4 else I.ANALOGOUS_EXAMPLE
            return _proposal(A.SCAFFOLD, intent, "Mức hint cao vẫn kẹt; minh họa bằng ví dụ khác.",
                             skill=skill_id, level=new_level, evidence=evidence, content=content)
        return _proposal(A.DIAGNOSE, I.ELICIT_REASONING, "Mức hint cao, không có ví dụ phù hợp; hỏi lại cách nghĩ.",
                         skill=skill_id, evidence=evidence)

    if s.trigger == "request_hint" or support.no_progress_turns >= ESCALATE_AFTER_NO_PROGRESS:
        new_level = level + 1
        if new_level >= 3:
            content = _pick_content(ctx, skill_id, {"example", "template", "hint"}, new_level)
            if content is not None:
                intent = I.DECOMPOSE_STEP if new_level == 3 else I.ANALOGOUS_EXAMPLE
                return _proposal(A.SCAFFOLD, intent, "Chưa tiến triển hoặc xin thêm hỗ trợ; tăng mức hint.",
                                 skill=skill_id, level=new_level, evidence=evidence, content=content)
            new_level = 2
        hypothesis = _active_hypothesis(s, skill_id)
        if hypothesis is not None and hypothesis.status == "supported" \
                and _last_tutor_action(s) != A.CONCEPTUAL_QUESTION:
            return _proposal(A.CONCEPTUAL_QUESTION, I.TARGET_MISCONCEPTION,
                             f"Chưa tiến triển, {hypothesis.misconception_id} có bằng chứng lặp lại; hỏi khái niệm ở mức cao hơn.",
                             skill=hypothesis.skill_id, level=new_level,
                             evidence=evidence + [_hypothesis_ref(hypothesis)],
                             content=_question_content(ctx, hypothesis.skill_id, new_level))
        intent = I.LOCATE_ERROR if a.first_error_step else I.RECALL_RULE
        return _proposal(A.MINIMAL_HINT, intent, f"Chưa tiến triển hoặc xin thêm hỗ trợ{step}; tăng mức hint.",
                         skill=skill_id, level=new_level, evidence=evidence,
                         content=_pick_content(ctx, skill_id, {"hint"}, new_level))

    value, n = estimate(s.skill(skill_id), s.mastery_view)
    if a.error_family in CARELESS_FAMILIES and value is not None and n >= 2 and value >= threshold(s, "good"):
        return _proposal(A.MINIMAL_HINT, I.PROMPT_SELF_CHECK, f"Lỗi thao tác{step}, lịch sử kỹ năng tốt.",
                         skill=skill_id, level=max(1, min(level + 1, 2)), evidence=evidence)

    last_action = _last_tutor_action(s)
    hypothesis = _active_hypothesis(s, skill_id)
    weak = _weak_prerequisite(s, ctx) if ctx.kg_enabled else None
    if weak is not None and hypothesis is None:
        edge, prereq_skill = weak
        if last_action != A.DIAGNOSE and not probed(s, prereq_skill):
            return _proposal(A.DIAGNOSE, I.PROBE_PREREQUISITE, "Skill nền có ước lượng thấp; kiểm tra trước khi backtrack.",
                             skill=prereq_skill, evidence=evidence, edge=edge)
        back = _backtrack(s, ctx, "Kiểm tra prerequisite xong vẫn sai; ôn prerequisite.")
        if back is not None:
            return back

    if hypothesis is not None:
        evidence = evidence + [_hypothesis_ref(hypothesis)]
        if hypothesis.status == "supported" or last_action == A.DIAGNOSE:
            q_level = min(level, 2)
            return _proposal(A.CONCEPTUAL_QUESTION, I.TARGET_MISCONCEPTION,
                             f"Lỗi{step} khớp {hypothesis.misconception_id} có bằng chứng; hỏi vào khái niệm.",
                             skill=hypothesis.skill_id, level=q_level, evidence=evidence,
                             content=_question_content(ctx, hypothesis.skill_id, q_level))
        return _proposal(A.DIAGNOSE, I.DISTINGUISH_HYPOTHESIS,
                         f"Nghi {hypothesis.misconception_id}{step}, mới có ít bằng chứng; hỏi chẩn đoán.",
                         skill=hypothesis.skill_id, evidence=evidence)

    if a.diagnosis_status == "unknown" and last_action != A.DIAGNOSE:
        return _proposal(A.DIAGNOSE, I.ELICIT_REASONING, f"Sai{step} nhưng chưa rõ nguyên nhân; hỏi cách làm.",
                         skill=skill_id, evidence=evidence)
    new_level = max(1, min(level + 1, 2))
    return _proposal(A.MINIMAL_HINT, I.LOCATE_ERROR if a.first_error_step else I.RECALL_RULE,
                     f"Sai{step}; gợi ý nhẹ để tự sửa.", skill=skill_id, level=new_level, evidence=evidence,
                     content=_pick_content(ctx, skill_id, {"hint"}, new_level))


def last_resort(s: StudentState) -> DecisionProposal:
    """Quyết định luôn qua được gate: dùng khi cả Agent lẫn Rule-policy đều không hợp lệ."""
    if s.trigger == "pause":
        return _end(I.STUDENT_REQUEST, "Học sinh xin tạm dừng.")
    return _end(I.SYSTEM_FALLBACK, "Không chọn được hành động hợp lệ; dừng an toàn.")
