"""Policy gate: luật bắt buộc phụ thuộc state, chạy sau kiểm tra hình dạng.

Mã ``S..`` lấy từ ``structural_violations``; mã ``G..`` là luật ở đây. Bảng luật và căn cứ:
docs/implementation/agent/pedagogical-decision.v1.md §6.
"""
from __future__ import annotations

from app.agent.decision import (
    MAX_BACKTRACK_DEPTH, MAX_SUPPORT_TURNS_PER_NODE, ACTION_SPECS, DecisionIntent, DecisionProposal,
    EvidenceKind, GateResult, PedagogicalAction, StudentState, structural_violations,
)
from app.agent.mastery import prerequisite_evidence
from app.agent.tools import ProblemRef, TurnContext

GATE_VERSION = "gate-0.4.0"

A, I = PedagogicalAction, DecisionIntent
ACTIVE_HYPOTHESIS = frozenset({"suspected", "supported"})
ADVANCE_INTENTS = frozenset({I.ADVANCE_DIFFICULTY, I.ADVANCE_CONCEPT})
LEAVE_PROBLEM_INTENTS = frozenset({I.CONTINUE_PRACTICE, I.ADVANCE_DIFFICULTY, I.ADVANCE_CONCEPT,
                                   I.RETURN_TO_PARENT})
STUCK_ALLOWED_ACTIONS = frozenset({A.SCAFFOLD, A.BACKTRACK, A.END_SESSION})
# Bài mới phải nằm trong skill/concept hiện tại (G20).
SAME_SCOPE_ACTIONS = frozenset({A.CHECK_TRANSFER})
SAME_SCOPE_INTENTS = frozenset({I.CONTINUE_PRACTICE, I.SWITCH_PROBLEM, I.ADVANCE_DIFFICULTY})


def evidence_index(s: StudentState) -> dict[EvidenceKind, set[str]]:
    """ID bằng chứng mà một quyết định được phép trỏ tới trong lượt này."""
    index = {kind: set() for kind in EvidenceKind}
    if s.latest_assessment is not None:
        index[EvidenceKind.ASSESSMENT].add(str(s.latest_assessment.assessment_id))
    if s.observation is not None and s.observation.observation_id is not None:
        index[EvidenceKind.OBSERVATION].add(str(s.observation.observation_id))
    index[EvidenceKind.HYPOTHESIS] = {h.hypothesis_id for h in s.hypotheses}
    index[EvidenceKind.STUDENT_MESSAGE].add(str(s.turn_id))
    for turn in s.recent_turns:
        if turn.actor == "student":
            index[EvidenceKind.STUDENT_MESSAGE].add(str(turn.turn_id))
        elif turn.kind == "decision":
            index[EvidenceKind.DECISION].add(str(turn.turn_id))
    return index


def _scope_violations(s: StudentState, p: DecisionProposal, problem: ProblemRef, ctx: TurnContext) -> list[str]:
    """G20: mỗi loại bài mới chỉ được đi tới đúng phạm vi của nó.

    - check_transfer, continue_practice, switch_problem, advance_difficulty: cùng skill và cùng
      concept với bài đang làm. Kiểm tra chuyển giao sang skill khác không phải bằng chứng chuyển
      giao; luyện tiếp sang concept khác là chuyển concept trá hình (kể cả khi tắt KG).
    - advance_difficulty: bài mới phải khó hơn bài đang làm; không biết độ khó bài hiện tại thì
      không chấp nhận.
    - Chuyển concept chỉ qua advance_concept (G19), ôn prerequisite chỉ qua backtrack (G05/G08)."""
    if p.action not in SAME_SCOPE_ACTIONS and p.intent not in SAME_SCOPE_INTENTS:
        return []
    out = []
    if p.target_skill_id != s.current.target_skill_id or problem.concept_id != s.current.concept_id:
        out.append("G20_problem_outside_current_scope")
    if p.intent == I.ADVANCE_DIFFICULTY:
        current = s.current.difficulty
        if current is None:
            known = ctx.problem(s.current.problem_id)
            current = known.difficulty if known else None
        if current is None:
            out.append("G20_current_difficulty_unknown")
        elif problem.difficulty <= current:
            out.append("G20_difficulty_not_higher")
    return out


def gate_violations(s: StudentState, p: DecisionProposal, ctx: TurnContext) -> list[str]:
    v = list(structural_violations(p))
    a = s.latest_assessment
    status = a.assessment_status if a is not None else None
    incorrect, correct = status == "verified_incorrect", status == "verified_correct"
    # Kẹt là đã hỗ trợ đủ số lượt mà bài vẫn chưa giải được. Vừa làm đúng thì không còn kẹt: phải
    # được đi tiếp bình thường (quay lại bài gốc, kiểm tra chuyển giao...).
    stuck = s.support.support_turns_on_node >= MAX_SUPPORT_TURNS_PER_NODE and not correct

    if s.trigger == "pause" and not (p.action == A.END_SESSION and p.intent == I.STUDENT_REQUEST):
        v.append("G14_pause_must_end_session")
    if s.trigger == "submit" and status in {"unverified", "needs_clarification"} \
            and p.action not in {A.CLARIFY, A.END_SESSION}:
        v.append("G01_unclear_input_requires_clarify")
    if ACTION_SPECS[p.action].counts_as_assistance and p.hint_level > s.support.hint_level + 1:
        v.append("G02_hint_level_jump")

    known = evidence_index(s)
    v += [f"G03_unknown_evidence:{r.kind}/{r.id}" for r in p.evidence if r.id not in known[r.kind]]

    for content_id in p.content_ids:
        item = ctx.content(content_id)
        if item is None:
            v.append(f"G04_content_not_retrieved:{content_id}")
        elif item.disclosure_level > p.hint_level:
            v.append(f"G04_disclosure_above_hint_level:{content_id}")

    edges = []
    if p.intent == I.ADVANCE_CONCEPT:
        # Chuyển concept là đi theo KG: phải trích đúng một cạnh tới concept kế tiếp mà KG trả về
        # trong lượt, và bài được chọn phải thuộc concept đó. Không có KG thì không chuyển concept.
        chosen = ctx.problem(p.problem_id) if p.problem_id else None
        if not ctx.kg_enabled:
            v.append("G19_advance_concept_requires_kg")
        elif len(p.edge_ids) != 1:
            v.append("G19_advance_concept_requires_edge")
        else:
            following = next((n for n in ctx.next_concepts if n.edge_id == p.edge_ids[0]), None)
            if following is None:
                v.append(f"G05_edge_not_returned:{p.edge_ids[0]}")
            elif chosen is None or chosen.concept_id != following.concept_id:
                v.append("G05_edge_does_not_link_target")
    else:
        edges = [e for e in map(ctx.edge, p.edge_ids) if e is not None]
        v += [f"G05_edge_not_returned:{edge_id}" for edge_id in p.edge_ids if ctx.edge(edge_id) is None]
        if p.edge_ids and len(edges) == len(p.edge_ids):
            # Các cạnh phải nối thành đường từ concept đang học tới skill được nhắm, tối đa 2 tầng.
            chain = ctx.prerequisite_chain(p.edge_ids, s.current.concept_id)
            if chain is None or p.target_skill_id not in chain:
                v.append("G05_edge_does_not_link_target")
            elif p.action == A.BACKTRACK and chain[p.target_skill_id] != 1:
                v.append("G08_backtrack_one_level_per_step")

    if incorrect and (p.action == A.CHECK_TRANSFER
                      or (p.action == A.NEXT_PROBLEM and p.intent in LEAVE_PROBLEM_INTENTS)):
        v.append("G06_new_error_blocks_advance")
    if p.intent in ADVANCE_INTENTS and not s.readiness.ready_to_advance:
        v.append("G07_readiness_required")

    if p.action == A.BACKTRACK:
        if len(s.return_stack) >= MAX_BACKTRACK_DEPTH:
            v.append("G08_backtrack_depth")
        branch = {s.current.concept_id} | {f.concept_id for f in s.return_stack}
        if any(e.source_concept_id in branch for e in edges):
            v.append("G08_backtrack_loop")
        if correct:
            v.append("G08_no_backtrack_when_correct")
        # Graph chỉ đưa ứng viên: phải có bằng chứng học sinh thiếu skill nền đó (PRD FR08-AC3).
        if p.target_skill_id is not None and prerequisite_evidence(s, p.target_skill_id) is None:
            v.append("G18_backtrack_requires_prerequisite_evidence")
    if p.intent == I.RETURN_TO_PARENT and (
            not s.return_stack or p.problem_id != s.return_stack[-1].problem_id):
        v.append("G09_return_target_mismatch")

    if stuck and not (p.action in STUCK_ALLOWED_ACTIONS or p.intent == I.SWITCH_PROBLEM):
        v.append("G10_stuck_limit")
    if p.intent == I.SWITCH_PROBLEM and not stuck:
        v.append("G10_switch_requires_stuck")
    if incorrect and s.support.hint_level >= 3 and p.action in {A.MINIMAL_HINT, A.CONCEPTUAL_QUESTION}:
        v.append("G11_high_level_requires_new_approach")

    if p.problem_id is not None and p.intent != I.RETURN_TO_PARENT:
        problem = ctx.problem(p.problem_id)
        if problem is None:
            v.append("G13_problem_not_in_bank")
        else:
            if problem.target_skill_id != p.target_skill_id:
                v.append("G13_problem_skill_mismatch")
            if p.problem_id == s.current.problem_id:
                v.append("G13_same_problem")
            elif p.problem_id in s.attempted_problem_ids:
                v.append("G13_problem_already_attempted")
            if p.action == A.CHECK_TRANSFER and problem.template_family_id == s.current.template_family_id:
                v.append("G12_transfer_needs_new_family")
            v += _scope_violations(s, p, problem, ctx)

    if p.action == A.CHECK_TRANSFER and not correct:
        v.append("G16_transfer_requires_correct")
    if p.action == A.CONCEPTUAL_QUESTION or p.intent == I.DISTINGUISH_HYPOTHESIS:
        active = {h.hypothesis_id for h in s.hypotheses
                  if h.status in ACTIVE_HYPOTHESIS and h.skill_id == p.target_skill_id}
        if not any(r.kind == EvidenceKind.HYPOTHESIS and r.id in active for r in p.evidence):
            v.append("G17_active_hypothesis_required")
    return list(dict.fromkeys(v))


def policy_gate(s: StudentState, p: DecisionProposal, ctx: TurnContext) -> GateResult:
    violations = gate_violations(s, p, ctx)
    return GateResult(status="rejected" if violations else "accepted", violated_rules=violations,
                      gate_version=GATE_VERSION)
