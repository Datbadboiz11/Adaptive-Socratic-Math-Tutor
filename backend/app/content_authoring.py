"""Offline authoring contracts/checks. Passing a machine check never approves content."""
from collections import Counter
from datetime import datetime
import hashlib
import json
import re
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, model_validator

from app.authoring_math import audit_case, first_error, response_value, scalar
from app.contracts import Contract, Identifier
from app.curriculum import (
    AuthoredProblem, ConceptPack, CurriculumRegistry, ErrorFixture, Hint, MathCase, PilotBank, Text,
)
from app.member2_contracts import ConceptId

AUTHORING_VERSION = "authoring-1.0.0"
PROMPT_VERSION = "draft-pack-1.0.0"
MEMBER2_PROMPT_VERSION = "draft-pack-2.2.0"
Revision = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,23}$")]


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class FamilySpec(Contract):
    family_id: Identifier
    source_group: Identifier
    description: Text


class DraftRequest(Contract):
    protocol_version: Literal[AUTHORING_VERSION] = AUTHORING_VERSION
    concept_id: ConceptId
    revision: Revision
    author: Annotated[str, Field(min_length=1, max_length=160)]
    content_version: Annotated[str, Field(min_length=1, max_length=80)]
    source_ids: list[Identifier] = Field(min_length=1)
    families: list[FamilySpec] = Field(min_length=3, max_length=3)
    model: Annotated[str, Field(min_length=1, max_length=160)]
    max_output_tokens: int = Field(default=8000, strict=True, ge=512, le=16000)
    timeout_seconds: int = Field(default=45, strict=True, ge=1, le=60)

    @property
    def id_prefix(self):
        return f"D-{self.concept_id}-{self.revision}-"

    @model_validator(mode="after")
    def distinct_families(self):
        for values in ([f.family_id for f in self.families], [f.source_group for f in self.families], self.source_ids):
            if len(values) != len(set(values)):
                raise ValueError("Duplicate family, source group or source ID")
        return self


class GeneratedContent(Contract):
    """The model supplies content only, never review, version or publication metadata."""
    explanation: Text
    problems: list[AuthoredProblem] = Field(min_length=6, max_length=6)
    examples: list[MathCase] = Field(min_length=3, max_length=3)
    errors: list[ErrorFixture] = Field(min_length=2, max_length=4)
    hints: list[Hint] = Field(min_length=3, max_length=3)


class CheckIssue(Contract):
    severity: Literal["error", "warning"]
    code: Identifier
    path: str
    message: Text


class DraftCheck(Contract):
    protocol_version: Literal[AUTHORING_VERSION] = AUTHORING_VERSION
    pack_sha256: str
    issues: list[CheckIssue]

    @property
    def passed(self):
        return not any(i.severity == "error" for i in self.issues)


def request_concept(request: DraftRequest, registry: CurriculumRegistry):
    concept = next((c for c in registry.concepts if c.concept_id == request.concept_id), None)
    if concept is None or not concept.authoring_task_kinds:
        raise ValueError("Concept has no supported authoring checker; define its scope first")
    if request.content_version != registry.content_version:
        raise ValueError("Request content version must match its registry snapshot")
    if not set(request.source_ids).issubset({s.source_id for s in registry.sources}):
        raise ValueError("Request contains an unknown source")
    if concept.alignment.source_id not in request.source_ids:
        raise ValueError("Include the concept's curriculum source in the request")
    return concept


def build_prompt(request: DraftRequest, registry: CurriculumRegistry, template: str, *, prompt_version=PROMPT_VERSION):
    concept = request_concept(request, registry)
    context = {
        "prompt_version": prompt_version, "request": request.model_dump(mode="json"),
        "concept": concept.model_dump(mode="json"), "id_prefix": request.id_prefix,
        "sources": [s.model_dump(mode="json") for s in registry.sources if s.source_id in request.source_ids],
        "source_note": "Source metadata is context, not proof that a human checked curriculum alignment.",
    }
    return [{"role": "system", "content": template},
            {"role": "user", "content": canonical_json(context)}]


def make_draft(content: GeneratedContent, request: DraftRequest):
    return ConceptPack.model_validate({
        **content.model_dump(mode="json"), "concept_id": request.concept_id,
        "content_version": request.content_version,
        "review": {"status": "draft", "author": request.author,
                   "source": "AI-assisted authoring draft; source IDs: " + ", ".join(request.source_ids)},
    })


def check_draft(pack: ConceptPack, request: DraftRequest, registry: CurriculumRegistry, bank: PilotBank):
    concept = request_concept(request, registry)
    issues = []

    def issue(code, path, message, severity="error"):
        issues.append(CheckIssue(severity=severity, code=code, path=path, message=message))

    if pack.concept_id != request.concept_id or pack.content_version != request.content_version:
        issue("identity_mismatch", "$", "Pack identity/version differs from the request")
    if pack.review.status != "draft" or pack.review.human_reviewer or pack.review.reviewed_at:
        issue("invented_review", "review", "Generated drafts must not carry human approval")
    if pack.review.author != request.author:
        issue("author_mismatch", "review.author", "Draft author differs from the server request")
    if len(pack.problems) != 6 or len(pack.examples) != 3 or not 2 <= len(pack.errors) <= 4:
        issue("coverage", "$", "Require six problems, three examples and two to four error fixtures")

    current_ids = [c.case_id for p in bank.packs for c in [*p.problems, *p.examples]]
    current_ids += [e.error_id for p in bank.packs for e in p.errors]
    ids = [c.case_id for c in [*pack.problems, *pack.examples]] + [e.error_id for e in pack.errors]
    for record_id, count in Counter(ids).items():
        if count != 1 or record_id in current_ids or not record_id.startswith(request.id_prefix):
            issue("invalid_record_id", "$", "Duplicate, existing or incorrectly namespaced ID: " + record_id)

    families = {f.family_id: f.source_group for f in request.families}
    counts = Counter(p.family_id for p in pack.problems)
    if set(counts) != set(families) or any(counts[f] != 2 for f in families):
        issue("family_coverage", "problems", "Each declared family must supply exactly two problems")
    skill_ids = {s.skill_id for s in concept.skills}
    seen_tasks = set()
    for index, problem in enumerate(pack.problems):
        if problem.primary_skill_id not in skill_ids:
            issue("unknown_skill", f"problems[{index}].primary_skill_id", "Skill does not belong to this concept")
        if families.get(problem.family_id) != problem.source_group:
            issue("source_group", f"problems[{index}].source_group", "Family/source-group mapping differs from the request")
        task_key = canonical_json(problem.task.model_dump())
        if task_key in seen_tasks:
            issue("duplicate_task", f"problems[{index}].task", "Exact duplicate problem task")
        seen_tasks.add(task_key)

    for group, cases in (("problems", pack.problems), ("examples", pack.examples)):
        for index, case in enumerate(cases):
            path = f"{group}[{index}]"
            if group == "examples" and canonical_json(case.task.model_dump()) in seen_tasks:
                issue("example_reuses_problem", path + ".task", "A support example must not repeat an assessed task")
            if case.task.kind not in concept.authoring_task_kinds:
                issue("unsupported_task", path + ".task.kind", "Task kind is outside the declared authoring scope")
                continue
            try:
                audit_case(case)
                if pack.concept_id == "A04" and case.task.kind == "polynomial":
                    from app.authoring_extended_math import check_expanded_quadratic
                    check_expanded_quadratic(case.reference_answer)
                if pack.concept_id == "N04" and case.reference_answer != str(scalar(case.reference_answer)):
                    issue("fraction_not_reduced", path + ".reference_answer", "Use a reduced fraction with positive denominator")
            except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
                issue("invalid_math", path, "Reference answer/step is incorrect, unsafe or outside the bounded checker")
    problems = {p.case_id: p for p in pack.problems}
    for index, error in enumerate(pack.errors):
        path = f"errors[{index}]"
        problem = problems.get(error.problem_id)
        if problem is None:
            issue("unknown_problem", path + ".problem_id", "Error fixture refers to an unknown problem")
            continue
        try:
            # Validate every snapshot, including snapshots after the first wrong step.
            for step in error.response_steps:
                response_value(problem.task, step)
            if first_error(problem, error.response_steps) != error.first_error_step:
                issue("wrong_error_label", path + ".first_error_step", "First-error label disagrees with exact checking")
        except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
            issue("invalid_error_trace", path, "Error trace contains unsupported or unsafe expressions")

    for index, hint in enumerate(pack.hints):
        compact = re.sub(r"\s+", "", hint.text)
        for problem in pack.problems:
            answer = re.sub(r"\s+", "", problem.reference_answer)
            if problem.task.kind == "polynomial" and len(answer) >= 5 and answer in compact:
                issue("answer_disclosure", f"hints[{index}].text", "Hint repeats a reference answer")
                break
            if problem.task.kind == "linear_equation":
                for match in re.finditer(r"\bx\s*=\s*([+-]?\d+(?:\.\d+)?(?:/\d+)?)", hint.text):
                    try:
                        if scalar(match[1]) == response_value(problem.task, problem.reference_answer):
                            issue("answer_disclosure", f"hints[{index}].text", "Hint supplies a current problem solution")
                    except (ValueError, SyntaxError, ZeroDivisionError):
                        pass
    issue("human_review_required", "$", "Curriculum, source rights, Vietnamese, pedagogical goal/form and hint math/disclosure require independent human review", "warning")
    if pack.concept_id == "F05":
        task_kinds = {problem.task.kind for problem in pack.problems}
        if not {"quadratic_vertex", "quadratic_axis"}.issubset(task_kinds):
            issue("partial_concept_scope", "$", "F05 requires separate practice for vertex coordinates and the symmetry axis", "warning")
    return DraftCheck(pack_sha256=digest(pack.model_dump(mode="json")), issues=issues)


class ReviewChecklist(Contract):
    mathematics: Literal["pass", "fail", "not_checked"]
    curriculum_scope: Literal["pass", "fail", "not_checked"]
    pedagogy_language: Literal["pass", "fail", "not_checked"]
    disclosure: Literal["pass", "fail", "not_checked"]
    source_rights: Literal["pass", "fail", "not_checked"]


class ContentReview(Contract):
    protocol_version: Literal[AUTHORING_VERSION] = AUTHORING_VERSION
    review_id: Identifier
    reviewer: Annotated[str, Field(min_length=1, max_length=160)]
    reviewed_at: AwareDatetime
    pack_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    decision: Literal["approved", "changes_requested", "content_pass_source_pending"]
    checklist: ReviewChecklist
    comments: Text

    @model_validator(mode="after")
    def complete_approval(self):
        checks = self.checklist.model_dump()
        if self.decision == "approved" and any(v != "pass" for v in checks.values()):
            raise ValueError("Approval requires all independent review checks to pass")
        if self.decision == "content_pass_source_pending":
            rights = checks.pop("source_rights")
            if rights == "pass" or any(v != "pass" for v in checks.values()):
                raise ValueError("Pending source clearance requires all other review checks to pass")
        return self


def review_template(pack: ConceptPack):
    return {"protocol_version": AUTHORING_VERSION, "review_id": "FILL-UNIQUE-REVIEW-ID",
            "reviewer": None, "reviewed_at": None, "pack_sha256": digest(pack.model_dump(mode="json")),
            "decision": "changes_requested", "checklist": {k: "not_checked" for k in ReviewChecklist.model_fields},
            "comments": "Điền người/thời điểm review thật, kết quả từng mục và nhận xét trước khi gửi."}


def apply_review(pack: ConceptPack, review: ContentReview, request, registry, bank):
    check = check_draft(pack, request, registry, bank)
    if review.pack_sha256 != check.pack_sha256:
        raise ValueError("Review is stale: draft hash changed")
    normalize = lambda s: " ".join(s.split()).casefold()
    if normalize(review.reviewer) == normalize(pack.review.author):
        raise ValueError("A different person must review the draft")
    if review.reviewed_at > datetime.now(review.reviewed_at.tzinfo):
        raise ValueError("Review timestamp is in the future")
    if review.decision != "approved":
        return None
    if not check.passed:
        raise ValueError("Cannot approve content with machine-check errors")
    return ConceptPack.model_validate({**pack.model_dump(mode="json"), "review": {
        "status": "human_approved", "author": pack.review.author, "source": pack.review.source,
        "human_reviewer": review.reviewer, "reviewed_at": review.reviewed_at,
    }})
