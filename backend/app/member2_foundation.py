"""Reproducible Part 1 coverage, proposals, and public contract projections."""
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from app.contracts import Contract, Identifier
from app.curriculum import load_curriculum, safe_chunks
from app.member2_contracts import ConceptId, ConceptReadiness, project_problem

ROOT = Path(__file__).resolve().parents[2]
WORKBOARD = ROOT / "content/curriculum/member2-workboard.v1.json"
Member = Literal["Member 1", "Member 2", "Member 3"]


class Assignment(Contract):
    owner: Member
    reviewer: Member
    concept_ids: list[ConceptId] = Field(min_length=1)

    @model_validator(mode="after")
    def independent_reviewer(self):
        if self.owner == self.reviewer or len(self.concept_ids) != len(set(self.concept_ids)):
            raise ValueError("Assignments require a different reviewer and unique concepts")
        return self


class IntegrationGate(Contract):
    id: Identifier
    topic: Identifier
    owner: Member
    reviewer: Member
    status: Literal["pending_review", "accepted"]
    reviewed_by: Member | None = None
    reviewed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def actual_review(self):
        if self.owner == self.reviewer:
            raise ValueError("Gate reviewer must differ from the owner")
        if self.status == "accepted":
            if self.reviewed_by != self.reviewer or self.reviewed_at is None:
                raise ValueError("Acceptance requires the designated reviewer and timestamp")
        elif self.reviewed_by is not None or self.reviewed_at is not None:
            raise ValueError("Pending review cannot carry an acceptance signature")
        return self


class RuntimeEvidence(Contract):
    legacy_concept_id: Identifier
    legacy_skill_id: Identifier
    validator_version: Literal["linear-rational-1.0.0"]
    task_kinds: list[Literal["linear_equation"]] = Field(min_length=1, max_length=1)
    mode: Literal["internal_demo"]
    canonical_mapping_status: Literal["proposed_not_active"]


class Workboard(Contract):
    schema_version: Literal["1.0.0"]
    status: Literal["proposed_pending_team_review"]
    assignments: list[Assignment] = Field(min_length=3, max_length=3)
    runtime_evidence: RuntimeEvidence
    integration_gates: list[IntegrationGate] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def unique_work_items(self):
        ids = [c for a in self.assignments for c in a.concept_ids]
        if len(ids) != len(set(ids)) or len({a.owner for a in self.assignments}) != 3:
            raise ValueError("Concept assignments overlap or a member is missing")
        if {g.id for g in self.integration_gates} != {f"M2-C0{i}" for i in range(1, 6)}:
            raise ValueError("All five distinct interface gates are required")
        return self


def load_workboard(path=WORKBOARD) -> Workboard:
    return Workboard.model_validate_json(path.read_text(encoding="utf-8"))


def build_coverage(registry=None, bank=None, workboard=None) -> dict:
    if registry is None or bank is None:
        if registry is not None or bank is not None:
            raise ValueError("Provide both registry and bank, or neither")
        registry, bank = load_curriculum()
    workboard = workboard or load_workboard()
    if registry.content_version != bank.content_version:
        raise ValueError("Registry/pilot version mismatch")
    assignments = {c: a for a in workboard.assignments for c in a.concept_ids}
    if set(assignments) != {c.concept_id for c in registry.concepts}:
        raise ValueError("Workboard must cover every registry concept exactly once")
    packs = {p.concept_id: p for p in bank.packs}
    concepts = {c.concept_id: c for c in registry.concepts}
    rows = []
    contract_reviewed = all(g.status == "accepted" for g in workboard.integration_gates)
    for concept in sorted(registry.concepts, key=lambda c: c.concept_id):
        pack = packs.get(concept.concept_id)
        incoming = [e for e in registry.edges if e.relation == "PREREQUISITE_OF"
                    and e.target_concept_id == concept.concept_id]
        readiness = ConceptReadiness(
            concept_id=concept.concept_id, has_pack=pack is not None,
            alignment_approved=concept.alignment.status == "human_approved",
            concept_approved=concept.review.status == "human_approved",
            pack_approved=pack is not None and pack.review.status == "human_approved",
            prerequisites_approved=all(e.review.status == "human_approved" and
                concepts[e.source_concept_id].review.status == "human_approved" and
                concepts[e.source_concept_id].alignment.status == "human_approved" for e in incoming),
            # Legacy support is not canonical support until an adapter and tests exist.
            validator_integrated=False, ui_policy_verified=False,
            contract_review_complete=contract_reviewed,
        )
        assignment = assignments[concept.concept_id]
        rows.append({
            "concept_id": concept.concept_id, "title": concept.title,
            "proposed_owner": assignment.owner, "proposed_reviewer": assignment.reviewer,
            "objective": concept.objective,
            "skills": [s.model_dump() for s in concept.skills],
            "authoring_task_kinds": concept.authoring_task_kinds,
            "supported_forms": concept.supported_forms, "excluded_forms": concept.excluded_forms,
            "alignment": concept.alignment.model_dump(mode="json"),
            "concept_review": concept.review.model_dump(mode="json"),
            "pack_review": pack.review.model_dump(mode="json") if pack else None,
            "prerequisite_edge_ids": [e.edge_id for e in incoming],
            "problems": len(pack.problems) if pack else 0,
            "families": len({p.family_id for p in pack.problems}) if pack else 0,
            "examples": len(pack.examples) if pack else 0,
            "error_fixtures": len(pack.errors) if pack else 0,
            "hints": len(pack.hints) if pack else 0,
            "public_chunks": len(safe_chunks(registry, bank, concept.concept_id)),
            "readiness": {**readiness.model_dump(), "ready": readiness.ready, "blockers": readiness.blockers},
            "last_human_review_at": pack.review.reviewed_at.isoformat() if pack and pack.review.reviewed_at else None,
            "learner_test_status": "not_verified_for_canonical_ids",
        })
    return {
        "schema_version": "1.0.0", "content_version": registry.content_version,
        "assignment_status": workboard.status,
        "summary": {
            "registry_concepts": len(rows), "draft_packs": sum(r["pack_review"] is not None and
                r["pack_review"]["status"] != "human_approved" for r in rows),
            "packs_present": len(packs),
            "approved_packs": sum(r["pack_review"] is not None and
                r["pack_review"]["status"] == "human_approved" for r in rows),
            "ready_concepts": sum(r["readiness"]["ready"] for r in rows),
            **{k: sum(r[k] for r in rows) for k in ("problems", "examples", "error_fixtures", "hints", "public_chunks")},
            "proposed_owner_counts": dict(sorted(Counter(r["proposed_owner"] for r in rows).items())),
        },
        "runtime_evidence": workboard.runtime_evidence.model_dump(),
        "integration_gates": [g.model_dump(mode="json") for g in workboard.integration_gates],
        "input_sha256": source_hashes(),
        "concepts": rows,
    }


def render_coverage(report: dict) -> str:
    summary = report["summary"]
    lines = ["# Ma trận độ phủ Member 2 — Phần 1", "",
        "Sinh từ registry/pilot/workboard bằng `scripts/checks/check_member2_foundation.py`.",
        "Owner/reviewer là đề xuất để cân bằng khối lượng; chưa phải xác nhận phân công của nhóm.", "",
        f"{summary['registry_concepts']} concept; {summary['packs_present']} pack; "
        f"{summary['problems']} bài; {summary['examples']} ví dụ; {summary['error_fixtures']} mẫu lỗi; "
        f"{summary['hints']} mức hint. {summary['approved_packs']} pack được duyệt, "
        f"{summary['public_chunks']} public chunk và {summary['ready_concepts']} concept sẵn sàng.", "",
        "Task dưới đây là khả năng kiểm tra authoring. Validator online hiện chỉ chạy trên ID legacy; "
        "canonical IDs chưa có adapter/tích hợp hoặc nghiệm thu UI/policy.", "",
        "| Concept | Tên | Owner đề xuất | Reviewer đề xuất | Bài/họ/ví dụ/lỗi/hint | Pack | Alignment | Ready |",
        "|---|---|---|---|---|---|---|---|",
    ]
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    for row in report["concepts"]:
        counts = "/".join(str(row[k]) for k in ("problems", "families", "examples", "error_fixtures", "hints"))
        review = row["pack_review"]["status"] if row["pack_review"] else "chưa có"
        values = [row["concept_id"], row["title"], row["proposed_owner"], row["proposed_reviewer"],
                  counts, review, row["alignment"]["status"], "có" if row["readiness"]["ready"] else "chưa"]
        lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    lines += ["", "## Skill và task cần tích hợp", "",
        "| Concept | Skill | Hành vi đo | Task authoring | Nguồn chương trình |",
        "|---|---|---|---|---|",
    ]
    for row in report["concepts"]:
        for skill in row["skills"]:
            values = [row["concept_id"], skill["skill_id"], skill["observable_behavior"],
                      ", ".join(row["authoring_task_kinds"]) or "chưa đặc tả",
                      row["alignment"]["source_id"]]
            lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    lines += ["", "## Các cổng review", "",
              "| ID | Chủ đề | Owner | Reviewer | Trạng thái |", "|---|---|---|---|---|"]
    for gate in report["integration_gates"]:
        lines.append("| " + " | ".join(gate[k] for k in ("id", "topic", "owner", "reviewer", "status")) + " |")
    lines += ["", "Thông tin đầy đủ về nguồn, scope, ngày review và từng readiness gate nằm trong "
              "[coverage.json](coverage.json). Ngày review trống nghĩa là chưa ghi nhận review thực tế.", ""]
    return "\n".join(lines)


def public_problem_examples(registry=None, bank=None):
    if registry is None or bank is None:
        registry, bank = load_curriculum()
    seen, examples = set(), []
    for pack in bank.packs:
        for problem in pack.problems:
            if problem.task.kind not in seen:
                seen.add(problem.task.kind)
                examples.append(project_problem(problem, pack.content_version).model_dump(mode="json"))
    return examples


def source_hashes() -> dict:
    paths = ["content/curriculum/registry.v1.json", "content/curriculum/pilot.v1.json",
             "content/curriculum/member2-workboard.v1.json", "content/linear_equations.v1.json",
             "content/bkt.bootstrap.v1.json"]
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}
