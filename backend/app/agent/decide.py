"""Ghép đề xuất → policy gate → fallback thành một bản ghi PedagogicalDecision.

Chuỗi fallback: đề xuất (Agent hoặc Rule-policy) → Rule-policy → last_resort. Quyết định cuối
luôn qua được gate; nếu không, đó là lỗi lập trình và hàm raise thay vì gửi phản hồi sai luật.

``run_decision`` là điểm vào dùng chung cho node ``decide`` của LangGraph và script đánh giá: gọi
proposer, đổi lỗi của proposer thành fallback, và đo thời gian của cả chuỗi.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import time
from typing import Callable
from uuid import UUID

from pydantic import ValidationError

from app.agent.decision import (
    DecisionConfig, DecisionProposal, DecisionSource, ExperimentConfiguration, PedagogicalDecision, StudentState,
)
from app.llm.types import LLMUsage
from app.agent.gate import policy_gate
from app.agent.rule_policy import last_resort, rule_policy
from app.agent.tools import TurnContext


@dataclass(frozen=True)
class ProposalOutcome:
    """Kết quả của bước đề xuất. ``error`` khác None khi Agent không đưa ra được đề xuất;
    ``usage`` ghi lần gọi LLM (kể cả lần lỗi) để đo latency/cost."""

    proposal: DecisionProposal | None
    proposed_by: DecisionSource
    error: str | None = None
    usage: LLMUsage | None = None


def resolve_decision(s: StudentState, ctx: TurnContext, outcome: ProposalOutcome, config: DecisionConfig,
                     *, decision_id: UUID, created_at: datetime) -> PedagogicalDecision:
    gate = None
    final, final_source, fallback_reason, fallback_gate = None, None, None, None
    if outcome.proposal is not None:
        gate = policy_gate(s, outcome.proposal, ctx)
        if gate.status == "accepted":
            final, final_source = outcome.proposal, outcome.proposed_by
        else:
            fallback_reason = "gate_rejected"
    else:
        fallback_reason = outcome.error or "agent_error"

    if final is None:
        candidate = rule_policy(s, ctx)
        fallback_gate = policy_gate(s, candidate, ctx)
        if fallback_gate.status != "accepted" or candidate == outcome.proposal:
            candidate = last_resort(s)
            fallback_gate = policy_gate(s, candidate, ctx)
        if fallback_gate.status != "accepted":
            raise RuntimeError(f"fallback rejected by gate: {fallback_gate.violated_rules}")
        final, final_source = candidate, DecisionSource.FALLBACK

    return PedagogicalDecision(
        decision_id=decision_id, session_id=s.session_id, turn_id=s.turn_id,
        opportunity_id=s.current.opportunity_id, state_version=s.state_version,
        proposed_by=outcome.proposed_by, proposed=outcome.proposal, gate=gate, final=final,
        final_source=final_source, fallback_reason=fallback_reason, fallback_gate=fallback_gate,
        tool_calls_used=ctx.tool_calls_used, tool_errors=ctx.tool_errors,
        candidate_edge_ids=[e.edge_id for e in ctx.edges], kg_source=ctx.kg_source,
        graph_version=ctx.graph_version, agent_usage=outcome.usage, config=config,
        created_at=created_at)


Proposer = Callable[[StudentState, TurnContext], ProposalOutcome]


class RulePolicyProposer:
    """Rule-policy dùng làm proposer: cấu hình ``rule_policy`` của RQ5 (và baseline khi không có LLM)."""

    def __call__(self, state: StudentState, ctx: TurnContext) -> ProposalOutcome:
        return ProposalOutcome(rule_policy(state, ctx), DecisionSource.RULE_POLICY)


def run_decision(s: StudentState, ctx: TurnContext, proposer: Proposer, config: DecisionConfig, *,
                 decision_id: UUID, created_at: datetime, workflow_version: str | None = None,
                 timer: Callable[[], float] = time.perf_counter) -> PedagogicalDecision:
    """Proposer → gate → fallback cho một lượt. Lỗi bất kỳ của proposer không làm hỏng lượt dạy.

    ``decision_latency_ms`` đo cả chuỗi (gồm lần gọi LLM nếu có), giống nhau cho mọi cấu hình;
    latency riêng của lần gọi API nằm ở ``agent_usage.latency_ms``."""
    proposed_by = (DecisionSource.RULE_POLICY if config.configuration == ExperimentConfiguration.RULE_POLICY
                   else DecisionSource.AGENT)
    started = timer()
    try:
        outcome = proposer(s, ctx)
    except ValidationError:
        outcome = ProposalOutcome(None, proposed_by, "agent_schema_error")
    except TimeoutError:
        outcome = ProposalOutcome(None, proposed_by, "agent_timeout")
    except Exception:  # noqa: BLE001 - mọi lỗi của Agent đều chuyển thành fallback
        outcome = ProposalOutcome(None, proposed_by, "agent_error")
    record = resolve_decision(s, ctx, outcome, config, decision_id=decision_id, created_at=created_at)
    elapsed = round((timer() - started) * 1000, 3)
    return record.model_copy(update={"decision_latency_ms": elapsed, "workflow_version": workflow_version})
