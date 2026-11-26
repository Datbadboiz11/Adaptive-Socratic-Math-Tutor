"""Apply the team's recorded Stage 1 confirmation to the archived workboard."""
from collections import Counter
from datetime import date
from hashlib import sha256
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.contracts import Contract, Identifier
from app.member2_foundation import (
    ROOT, WORKBOARD, IntegrationGate, Member, Workboard, build_coverage, load_workboard, render_coverage,
)

CONFIRMATION = ROOT / "content/curriculum/member2-workboard-confirmation.v1.json"
CONFIRMED_SCOPE = (
    WORKBOARD.relative_to(ROOT).as_posix(),
    "content/curriculum/registry.v1.json",
    "backend/app/member2_contracts.py",
    "contracts/member2/v0.2.0/examples.json",
    "contracts/member2/v0.2.0/FoundationExamples.schema.json",
)
UPDATE_CONFIRMATION = ROOT / "content/curriculum/member2-stage1-update-confirmation.v1.json"
UPDATE_SCOPE = (
    CONFIRMATION.relative_to(ROOT).as_posix(),
    "backend/app/member2_problem_contract.py",
    "backend/app/session_contracts.py",
    "backend/app/sessions.py",
    "contracts/member2/v0.3.0/examples.json",
    "contracts/member2/v0.3.0/PublicProblemExamples.schema.json",
    "contracts/phase3/openapi.json",
    "content/curriculum/registry.v2.json",
    "content/curriculum/pilot.v2.json",
    "content/authoring/member2-original-pilot.v1.json",
    "content/authoring/batches/a02-e02-original.v1/manifest.json",
)
UPDATE_SECTIONS = {
    "public_problem_contract_and_legacy_adapter", "topic_and_session_readiness",
    "concept_and_pack_coverage", "curriculum_graph", "legacy_canonical_mapping",
}


class TeamConfirmation(Contract):
    schema_version: Literal["1.0.0"]
    recorded_on: date
    basis: Literal["user_attested_team_confirmation"]
    signature: str = Field(min_length=1)
    confirmed_members: list[Member]
    confirmed_concept_count: Literal[40]
    contract_version: Literal["member2-proposal-0.2.0"]
    accepted_gates: list[Identifier]
    scope_sha256: dict[str, str]


class Stage1UpdateConfirmation(Contract):
    schema_version: Literal["1.0.0"]
    record_id: Identifier
    recorded_on: date
    basis: Literal["user_attested_team_confirmation"]
    signature: Literal["Codex — ký ghi nhận theo ủy quyền của người dùng"]
    confirmed_members: list[Member]
    public_problem_contract_version: Literal["member2-proposal-0.3.0"]
    confirmed_sections: list[str]
    registry_version: str
    confirmed_edge_count: int = Field(ge=0)
    confirmed_legacy_mapping_count: int = Field(ge=0)
    scope_sha256: dict[str, Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]]


class TeamAcceptedGate(IntegrationGate):
    """Acceptance backed by the team record on the workboard."""

    status: Literal["accepted"]

    @model_validator(mode="after")
    def actual_review(self):
        if self.owner == self.reviewer or self.reviewed_by is not None or self.reviewed_at is not None:
            raise ValueError("Team acceptance must retain roles and use the shared confirmation")
        return self


class ConfirmedWorkboard(Workboard):
    status: Literal["confirmed_by_team"]
    integration_gates: list[TeamAcceptedGate] = Field(min_length=5, max_length=5)
    team_confirmation: TeamConfirmation

    @model_validator(mode="after")
    def validate_confirmation_scope(self):
        confirmation = self.team_confirmation
        if sorted(confirmation.confirmed_members) != sorted(a.owner for a in self.assignments):
            raise ValueError("Team confirmation must cover the three workboard members")
        if sum(len(a.concept_ids) for a in self.assignments) != confirmation.confirmed_concept_count:
            raise ValueError("Team confirmation must cover all 40 workboard concepts")
        if sorted(confirmation.accepted_gates) != sorted(g.id for g in self.integration_gates):
            raise ValueError("Team confirmation must cover the five workboard gates")
        return self


def confirmed_coverage(registry, bank):
    payload = CONFIRMATION.read_bytes()
    confirmation = TeamConfirmation.model_validate_json(payload)
    hashes = {p: sha256((ROOT / p).read_bytes()).hexdigest() for p in CONFIRMED_SCOPE}
    if confirmation.scope_sha256 != hashes:
        raise ValueError("Stage 1 confirmation does not match the current registry, workboard or contract")

    workboard = load_workboard().model_dump()
    for gate in workboard["integration_gates"]:
        gate["status"] = "accepted"
    confirmed = ConfirmedWorkboard.model_validate({
        **workboard, "status": "confirmed_by_team", "team_confirmation": confirmation,
    })
    report = build_coverage(registry, bank, confirmed)
    report["team_confirmation"] = confirmation.model_dump(mode="json")
    report["summary"]["confirmed_assignments"] = confirmation.confirmed_concept_count
    report["summary"]["accepted_integration_gates"] = len(confirmed.integration_gates)
    report["summary"]["approved_concepts"] = sum(c.review.status == "human_approved" for c in registry.concepts)
    report["summary"]["approved_alignments"] = sum(c.alignment.status == "human_approved" for c in registry.concepts)
    report["edge_review_counts"] = dict(sorted(Counter(edge.review.status for edge in registry.edges).items()))
    report["legacy_mappings"] = [mapping.model_dump(mode="json") for mapping in registry.legacy_mappings]
    report["input_sha256"][CONFIRMATION.relative_to(ROOT).as_posix()] = sha256(payload).hexdigest()
    return report


def add_pack_inventory(report, sources):
    """Inventory each source version and count unique concepts across releases."""
    rows = {row["concept_id"]: row for row in report["concepts"]}
    for row in rows.values():
        row["pack_sources"] = {}
    inventory = {}
    with_pack, with_approval = set(), set()
    for name, (source, packs) in sources.items():
        concepts = {pack.concept_id for pack in packs}
        approved = {pack.concept_id for pack in packs if pack.review.status == "human_approved"}
        with_pack.update(concepts)
        with_approval.update(approved)
        inventory[name] = {"source": source, "pack_count": len(packs), "approved_pack_count": len(approved),
                           "concept_ids": sorted(concepts)}
        for pack in packs:
            rows[pack.concept_id]["pack_sources"][name] = {
                "content_version": pack.content_version,
                "review": pack.review.model_dump(mode="json"),
                "task_kinds": sorted({problem.task.kind for problem in pack.problems}),
                "problems": len(pack.problems), "families": len({problem.family_id for problem in pack.problems}),
                "examples": len(pack.examples), "error_fixtures": len(pack.errors), "hints": len(pack.hints),
            }
    report["pack_inventory"] = inventory
    report["summary"].update(concepts_with_any_pack=len(with_pack), concepts_with_any_approved_pack=len(with_approval),
                             concepts_without_pack=len(rows) - len(with_pack))


def update_scope_hashes():
    return {path: sha256((ROOT / path).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            for path in UPDATE_SCOPE}


def apply_update_confirmation(report):
    payload = UPDATE_CONFIRMATION.read_bytes()
    record = Stage1UpdateConfirmation.model_validate_json(payload)
    baseline = report["team_confirmation"]
    if (sorted(record.confirmed_members) != sorted(baseline["confirmed_members"])
            or record.recorded_on < date.fromisoformat(baseline["recorded_on"])
            or sorted(record.confirmed_sections) != sorted(UPDATE_SECTIONS)
            or set(record.scope_sha256) != set(UPDATE_SCOPE)):
        raise ValueError("Stage 1 update confirmation does not match the recorded review scope")

    hashes = update_scope_hashes()
    contract_paths = ("backend/app/member2_problem_contract.py", "contracts/member2/v0.3.0/examples.json",
                      "contracts/member2/v0.3.0/PublicProblemExamples.schema.json")
    contract_matches = (record.public_problem_contract_version == report["public_problem_contract"]["version"]
                        and all(hashes.get(path) == record.scope_sha256[path] for path in contract_paths))
    scope_matches = (record.scope_sha256 == hashes and contract_matches and record.registry_version == report["content_version"]
                     and record.confirmed_edge_count == sum(report["edge_review_counts"].values())
                     and record.confirmed_legacy_mapping_count == len(report["legacy_mappings"]))

    report["stage1_update_confirmation"] = record.model_dump(mode="json")
    report["stage1_update_scope_matches"] = scope_matches
    report["public_problem_contract"]["review_status"] = "confirmed_by_team" if contract_matches else "pending_team_review"
    report["input_sha256"][UPDATE_CONFIRMATION.relative_to(ROOT).as_posix()] = sha256(payload).hexdigest()


def render_confirmed_coverage(report):
    confirmation = report["team_confirmation"]
    summary = report["summary"]
    text = render_coverage(report)
    text = text.replace(
        "Owner/reviewer là đề xuất để cân bằng khối lượng; chưa phải xác nhận phân công của nhóm.",
        "Cả ba thành viên đã xác nhận danh mục, phân công 40 concept và thông qua C01–C05. "
        "Xem [hồ sơ có chữ ký ghi nhận](../../../../content/curriculum/member2-workboard-confirmation.v1.json).\n"
        f"Registry {report['content_version']} ghi nhận {summary['approved_concepts']} concept và "
        f"{summary['approved_alignments']} alignment đã duyệt.",
    ).replace("| Owner đề xuất | Reviewer đề xuất |", "| Owner | Reviewer |")
    text = text.replace(
        "canonical IDs chưa có adapter/tích hợp hoặc nghiệm thu UI/policy.",
        "adapter đọc bài cũ giữ nguyên ID; mapping sang canonical vẫn ở trạng thái `proposed`. "
        "Xem [đặc tả nháp](task-specifications.md) cho 30 concept ngoài pilot canonical.",
    ).replace("| chưa đặc tả |", "| Chờ checker, có đặc tả nháp |")
    inventory = report["pack_inventory"]
    lines = ["", "## Độ phủ theo nguồn pack", "",
             f"{summary['concepts_with_any_pack']} concept có pack ở ít nhất một nguồn, "
             f"{summary['concepts_with_any_approved_pack']} concept có pack đã duyệt, "
             f"{summary['concepts_without_pack']} concept chưa có pack. Bảng phía trên dùng pilot canonical.", "",
             f"**Demo nội bộ** hỗ trợ {summary['demo_concepts_supported']} concept từ bản M2-ORIG02 sau khi bootstrap. "
             "Bộ chấm xác minh kết quả cuối. Xem [nghiệm thu demo](../part4/README.md).", "",
             "| Nguồn | Số pack | Pack đã duyệt |", "|---|---|---|"]
    for name, data in inventory.items():
        label = (f"[{name}](../../../../{data['source']})" if (ROOT / data['source']).exists()
                 else f"{name} (hồ sơ lịch sử không còn trong checkout)")
        lines.append(f"| {label} | {data['pack_count']} | {data['approved_pack_count']} |")
    lines += ["", "| " + " | ".join(["Concept", *inventory]) + " |", "|---" * (len(inventory) + 1) + "|"]
    for row in report["concepts"]:
        packs = row["pack_sources"]
        if not packs:
            continue
        cells = [f"{packs[name]['review']['status']} ({packs[name]['problems']} bài)" if name in packs else "—"
                 for name in inventory]
        lines.append("| " + " | ".join([row["concept_id"], *cells]) + " |")
    lines += ["", "Chi tiết từng phiên bản, loại bài, người duyệt, ngày review và các cổng còn thiếu nằm trong "
              "[coverage.json](coverage.json). Trạng thái này dựa trên các nguồn có version trong repo.", ""]
    update = report["stage1_update_confirmation"]
    update_path = UPDATE_CONFIRMATION.relative_to(ROOT).as_posix()
    update_status = ("Xác nhận khớp với hiện trạng." if report["stage1_update_scope_matches"] else
                     "Hồ sơ lưu phạm vi phiên bản đã được xác nhận. API tích hợp có thể kiểm riêng theo kết quả nghiệm thu.")
    lines += ["", "## Xác nhận cập nhật Chặng 1", "",
              f"Nhóm xác nhận contract {update['public_problem_contract_version']}, capability theo chủ đề, ma trận độ phủ, "
              f"{update['confirmed_edge_count']} cạnh đồ thị và {update['confirmed_legacy_mapping_count']} ánh xạ legacy–canonical.",
              f"Hồ sơ ghi ngày {update['recorded_on']} với chữ ký **{update['signature']}**. {update_status}",
              f"Xem [hồ sơ xác nhận cập nhật](../../../../{update_path}).", "",
              f"Trạng thái tích hợp hiện ghi {summary['ready_concepts']} concept canonical đủ điều kiện mở luồng học. "
              "Registry tiếp tục ghi cạnh `draft` và ánh xạ `proposed` cho đến bước đưa vào runtime.", ""]
    return text + (
        f"\nHồ sơ xác nhận được ghi ngày {confirmation['recorded_on']}. "
        f"Chữ ký ghi nhận **{confirmation['signature']}**.\n" + "\n".join(lines)
    )
