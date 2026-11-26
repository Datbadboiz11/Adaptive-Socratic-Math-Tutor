"""Immutable authoring runs and explicit manual review. No runtime bank writes."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

import httpx
from pydantic import ValidationError

from app.content_authoring import (
    AUTHORING_VERSION, MEMBER2_PROMPT_VERSION, PROMPT_VERSION, ContentReview, DraftRequest, GeneratedContent,
    apply_review, build_prompt, canonical_json, check_draft, digest, make_draft,
    request_concept, review_template,
)
from app.curriculum import ConceptPack, CurriculumRegistry, PilotBank, load_curriculum

ROOT = Path(__file__).resolve().parents[2]
RUN_ROOT = ROOT / "artifacts/authoring"
TEMPLATE = ROOT / "content/authoring/prompts/draft.v1.txt"
MEMBER2_TEMPLATE = ROOT / "content/authoring/prompts/draft.v2.txt"
MEMBER2_RELEASE = ROOT / "content/authoring/batches/member2-original.v2"
MAX_JSON_BYTES = 2 * 1024 * 1024


class GenerationError(ValueError):
    pass


def load_json(path):
    path = Path(path)
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("Authoring JSON exceeds the two MiB limit")
    return json.loads(path.read_text(encoding="utf-8"))


def load_authoring_source(source="legacy"):
    if source == "legacy":
        return load_curriculum()
    if source != "member2-v2":
        raise ValueError("Unknown authoring source")
    from app.member2_foundation import load_workboard
    manifest = load_json(MEMBER2_RELEASE / "manifest.json")
    files = {name: (MEMBER2_RELEASE / name).read_bytes() for name in ("registry-snapshot.json", "approved-bank.json")}
    if (manifest["basis"] != "user_confirmed_approval" or manifest["review_status"] != "human_approved"
            or manifest["files_sha256"] != {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}):
        raise ValueError("Authoring source approval or file checksum mismatch")
    registry = CurriculumRegistry.model_validate_json(files["registry-snapshot.json"])
    bank = PilotBank.model_validate_json(files["approved-bank.json"])
    assigned = set(next(row.concept_ids for row in load_workboard().assignments if row.owner == "Member 2"))
    if (registry.content_version != bank.content_version or bank.content_version != manifest["content_version"]
            or {pack.concept_id for pack in bank.packs} != assigned or set(manifest["packs"]) != assigned):
        raise ValueError("Authoring source differs from the 13-concept workboard")
    for pack in bank.packs:
        if pack.review.status != "human_approved" or digest(pack.model_dump(mode="json")) != manifest["packs"][pack.concept_id]["approved_pack_sha256"]:
            raise ValueError("Approved authoring pack checksum mismatch")
    return registry, bank


def authoring_prompt(request, registry, source="legacy"):
    template = MEMBER2_TEMPLATE if source == "member2-v2" else TEMPLATE
    version = MEMBER2_PROMPT_VERSION if source == "member2-v2" else PROMPT_VERSION
    if source == "member2-v2":
        from app.member2_foundation import load_workboard
        assigned = next(row.concept_ids for row in load_workboard().assignments if row.owner == "Member 2")
        if request.concept_id not in assigned:
            raise ValueError("Choose one of the 13 assigned Member 2 concepts")
    prompt = build_prompt(request, registry, template.read_text(encoding="utf-8"), prompt_version=version)
    if source == "member2-v2":
        context = json.loads(prompt[1]["content"])
        context["required_problem_slots"] = [
            {"case_id": f"{request.id_prefix}P-{2 * index + offset:02}", "family_id": family.family_id,
             "source_group": family.source_group, "difficulty": difficulty, "description": family.description}
            for index, family in enumerate(request.families)
            for offset, difficulty in ((1, "introductory"), (2, "standard"))
        ]
        context["snapshot_rule"] = {
            "reference_steps": "For this draft use exactly [reference_answer], a single complete final snapshot.",
            "response_steps": "For each error use one syntactically valid wrong final answer and first_error_step=1.",
            "numeric_example": {"expression": "4*-2/-1", "reference_answer": "8", "reference_steps": ["8"]},
            "wrong_example": {"response_steps": ["-8"], "first_error_step": 1},
        }
        prompt[1]["content"] = canonical_json(context)
    return prompt


def check_source_draft(pack, request, registry, bank, source="legacy"):
    check = check_draft(pack, request, registry, bank)
    if source == "member2-v2":
        for issue in check.issues:
            if issue.code == "partial_concept_scope":
                issue.severity = "error"
    return check


def generate_openai(request, prompt, client_factory=None):
    if os.getenv("AUTHORING_LLM_ENABLED", "false").lower() != "true" or not os.getenv("OPENAI_API_KEY"):
        raise GenerationError("OpenAI authoring is unconfigured: set AUTHORING_LLM_ENABLED and the server API key")
    if client_factory is None:
        from openai import OpenAI
        client_factory = OpenAI
    try:
        with client_factory(api_key=os.environ["OPENAI_API_KEY"], base_url="https://api.openai.com/v1",
                            timeout=request.timeout_seconds, max_retries=0) as client:
            response = client.responses.parse(
                model=request.model, input=prompt, text_format=GeneratedContent,
                store=False, max_output_tokens=request.max_output_tokens,
            )
        if response.status != "completed" or response.output_parsed is None:
            raise GenerationError("model_incomplete_or_refused")
        content = GeneratedContent.model_validate(response.output_parsed.model_dump(mode="json"))
        return content, {"provider": "openai", "model_requested": request.model,
                         "model_returned": response.model, "response_id": response.id,
                         "usage": response.usage.model_dump() if response.usage else None,
                         "model_calls": 1}
    except GenerationError:
        raise
    except Exception as error:
        # Provider exception messages may contain request data or credentials.
        status_code = getattr(error, "status_code", None)
        if type(status_code) is int and 400 <= status_code < 600:
            raise GenerationError(f"provider_http_{status_code}") from None
        raise GenerationError("provider_failure:" + type(error).__name__) from None


def gemini_schema(schema):
    """Send Gemini's structural subset. Pydantic enforces the full constraints locally."""
    result = {key: value for key, value in schema.items()
              if key in ("type", "enum", "required", "$ref", "additionalProperties")}
    if "const" in schema:
        result["enum"] = [schema["const"]]
    for key in ("properties", "$defs"):
        if key in schema:
            result[key] = {name: gemini_schema(child) for name, child in schema[key].items()}
    if "items" in schema:
        result["items"] = gemini_schema(schema["items"])
    if "anyOf" in schema:
        result["anyOf"] = [gemini_schema(child) for child in schema["anyOf"]]
    return result


def generate_gemini(request, prompt, client_factory=None):
    api_key = os.getenv("GEMINI_API_KEY")
    if os.getenv("AUTHORING_LLM_ENABLED", "false").lower() != "true" or not api_key:
        raise GenerationError("Gemini authoring requires AUTHORING_LLM_ENABLED and GEMINI_API_KEY")
    if not re.fullmatch(r"gemini-[A-Za-z0-9][A-Za-z0-9._-]{0,119}", request.model):
        raise GenerationError("invalid_gemini_model_name")
    generation = {
        "maxOutputTokens": request.max_output_tokens, "candidateCount": 1,
        "responseMimeType": "application/json", "responseJsonSchema": gemini_schema(GeneratedContent.model_json_schema()),
    }
    if request.model.startswith("gemini-3.1-flash-lite"):
        generation["thinkingConfig"] = {"thinkingLevel": "MINIMAL"}
    body = {
        "systemInstruction": {"parts": [{"text": prompt[0]["content"]}]},
        "contents": [{"role": "user", "parts": [{"text": prompt[1]["content"]}]}],
        "generationConfig": generation,
    }
    try:
        with (client_factory or httpx.Client)(timeout=request.timeout_seconds, follow_redirects=False,
                                             trust_env=False) as client:
            response = client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{request.model}:generateContent",
                headers={"x-goog-api-key": api_key}, json=body,
            )
            response.raise_for_status()
            result = response.json()
        candidates = result.get("candidates", [])
        if len(candidates) != 1 or candidates[0].get("finishReason") != "STOP":
            raise GenerationError("model_incomplete_or_refused")
        parts = candidates[0].get("content", {}).get("parts", [])
        output = "".join(part.get("text", "") for part in parts if not part.get("thought"))
        content = GeneratedContent.model_validate_json(output)
        return content, {
            "provider": "gemini", "model_requested": request.model,
            "model_returned": result.get("modelVersion"), "response_id": result.get("responseId"),
            "usage": result.get("usageMetadata"), "model_calls": 1, "http_status": response.status_code,
        }
    except (GenerationError, ValidationError):
        raise
    except httpx.HTTPStatusError as error:
        raise GenerationError(f"provider_http_{error.response.status_code}") from None
    except Exception as error:
        raise GenerationError("provider_failure:" + type(error).__name__) from None


def pilot_replay(request, bank):
    source = next((p for p in bank.packs if p.concept_id == request.concept_id), None)
    if source is None:
        raise ValueError("Pilot replay requires an existing concept pack")
    body = source.model_dump(mode="json", exclude={"concept_id", "content_version", "review"})
    mapping = {}
    for index, problem in enumerate(body["problems"], 1):
        original = problem["case_id"]
        problem["case_id"] = f"{request.id_prefix}P-{index:02}"
        mapping[original] = problem["case_id"]
        problem["origin"] = "Replay từ pilot " + original + "; không phải nội dung mới. " + problem["origin"]
    for index, example in enumerate(body["examples"], 1):
        example["case_id"] = f"{request.id_prefix}EX-{index:02}"
    for index, error in enumerate(body["errors"], 1):
        error["error_id"] = f"{request.id_prefix}ERR-{index:02}"
        error["problem_id"] = mapping[error["problem_id"]]
    return GeneratedContent.model_validate(body), {
        "provider": "pilot_replay", "model_calls": 0, "source_pack_sha256": digest(source.model_dump(mode="json")),
        "note": "Existing draft content replayed for pipeline verification; family/source groups preserved.",
    }


def safe_validation_errors(error):
    return [{"path": ".".join(map(str, e["loc"])), "type": e["type"], "message": e["msg"]}
            for e in error.errors(include_input=False, include_url=False)]


class RunStore:
    def __init__(self, root=RUN_ROOT):
        self.root = Path(root).resolve()
        artifact_root = (ROOT / "artifacts").resolve()
        if not artifact_root.is_relative_to(ROOT.resolve()) or not self.root.is_relative_to(artifact_root):
            raise ValueError("Authoring runs must stay inside repository artifacts/")

    def path(self, run_id):
        # Reuse the bounded revision identifier; never interpolate arbitrary paths.
        from pydantic import TypeAdapter
        from app.content_authoring import Revision
        TypeAdapter(Revision).validate_python(run_id)
        path = (self.root / run_id).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ValueError("Invalid authoring run path")
        return path

    def create(self, run_id):
        path = self.path(run_id)
        path.mkdir(parents=True, exist_ok=False)
        return path

    @staticmethod
    def write(path, value):
        content = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


def create_run(request: DraftRequest, run_id: str, provider: str, *, input_path=None,
               store=None, client_factory=None, source="legacy"):
    store = store or RunStore()
    registry, bank = load_authoring_source(source)
    request_concept(request, registry)
    prompt = authoring_prompt(request, registry, source)
    path = store.create(run_id)  # Claim before any model call; never overwrite/retry a run implicitly.
    hashes = {}

    def write(name, value):
        hashes[name] = store.write(path / name, value)

    write("request.json", request.model_dump(mode="json"))
    write("prompt.json", prompt)
    if source == "member2-v2":
        write("registry-snapshot.json", registry.model_dump(mode="json"))
        write("bank-snapshot.json", bank.model_dump(mode="json"))
    metadata = {"provider": provider, "model_calls": 0}
    status = "failed"
    failure = None
    try:
        if provider in ("openai", "gemini"):
            provider_key = "OPENAI_API_KEY" if provider == "openai" else "GEMINI_API_KEY"
            metadata = {"provider": provider, "model_requested": request.model,
                        "model_call_attempts": int(os.getenv("AUTHORING_LLM_ENABLED", "false").lower() == "true"
                                                   and bool(os.getenv(provider_key)))}
            generate = generate_openai if provider == "openai" else generate_gemini
            content, metadata = generate(request, prompt, client_factory)
        elif provider == "pilot_replay":
            content, metadata = pilot_replay(request, bank)
        elif provider == "replay":
            if input_path is None:
                raise ValueError("Replay requires an input JSON payload")
            payload = load_json(input_path)
            content = GeneratedContent.model_validate(payload)
            metadata = {"provider": "replay", "model_calls": 0, "payload_sha256": digest(payload)}
        else:
            raise ValueError("Unknown authoring provider")
        write("generated.json", content.model_dump(mode="json"))
        pack = make_draft(content, request)
        check = check_source_draft(pack, request, registry, bank, source)
        write("draft.json", pack.model_dump(mode="json"))
        write("checks.json", {**check.model_dump(mode="json"), "passed": check.passed})
        write("review-template.json", review_template(pack))
        status = "draft_ready" if check.passed else "check_failed"
    except ValidationError as error:
        failure = {"type": "schema_validation", "issues": safe_validation_errors(error)}
    except (ValueError, OSError) as error:
        failure = {"type": type(error).__name__}
        if isinstance(error, GenerationError):
            failure["reason"] = str(error)
    if failure:
        write("failure.json", failure)
    manifest = {
        "protocol_version": AUTHORING_VERSION, "prompt_version": json.loads(prompt[1]["content"])["prompt_version"],
        "run_id": run_id, "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status, "generation": metadata, "request_sha256": digest(request.model_dump(mode="json")),
        "prompt_sha256": digest(prompt), "registry_sha256": digest(registry.model_dump(mode="json")),
        "bank_sha256": digest(bank.model_dump(mode="json")), "artifact_sha256": hashes,
        "publication": "draft_only_not_seeded", "human_review": "pending",
    }
    if source != "legacy":
        manifest["source"] = source
    store.write(path / "manifest.json", manifest)
    return path, manifest


def verify_run(path):
    manifest = load_json(path / "manifest.json")
    # Artifact names are protocol-owned, never arbitrary paths supplied in a manifest.
    allowed = {"request.json", "prompt.json", "generated.json", "draft.json", "checks.json", "review-template.json", "failure.json",
               "registry-snapshot.json", "bank-snapshot.json"}
    if not set(manifest["artifact_sha256"]).issubset(allowed):
        raise ValueError("Unknown authoring artifact")
    for name, expected in manifest["artifact_sha256"].items():
        if hashlib.sha256((path / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Authoring artifact changed: " + name)
    if manifest["status"] not in ("draft_ready", "check_failed"):
        raise ValueError("Run has no reviewable draft")
    required = {"request.json", "prompt.json", "generated.json", "draft.json", "checks.json", "review-template.json"}
    if not required.issubset(manifest["artifact_sha256"]):
        raise ValueError("Incomplete authoring run")
    if manifest.get("source", "legacy") == "member2-v2":
        if not {"registry-snapshot.json", "bank-snapshot.json"}.issubset(manifest["artifact_sha256"]):
            raise ValueError("Missing versioned authoring source snapshots")
    elif manifest.get("source", "legacy") != "legacy":
        raise ValueError("Unknown run source")
    return manifest


def run_context(path, manifest):
    if manifest.get("source", "legacy") == "member2-v2":
        registry = CurriculumRegistry.model_validate(load_json(path / "registry-snapshot.json"))
        bank = PilotBank.model_validate(load_json(path / "bank-snapshot.json"))
    else:
        registry, bank = load_curriculum()
    if (manifest["registry_sha256"] != digest(registry.model_dump(mode="json"))
            or manifest["bank_sha256"] != digest(bank.model_dump(mode="json"))):
        raise ValueError("Registry/bank changed; create a fresh review run")
    return registry, bank


def check_run(path):
    manifest = verify_run(path)
    registry, bank = run_context(path, manifest)
    request = DraftRequest.model_validate(load_json(path / "request.json"))
    pack = ConceptPack.model_validate(load_json(path / "draft.json"))
    return check_source_draft(pack, request, registry, bank, manifest.get("source", "legacy"))


def review_run(run_id, review: ContentReview, *, store=None):
    store = store or RunStore()
    path = store.path(run_id)
    manifest = verify_run(path)
    registry, bank = run_context(path, manifest)
    request = DraftRequest.model_validate(load_json(path / "request.json"))
    pack = ConceptPack.model_validate(load_json(path / "draft.json"))
    if review.decision == "approved" and not check_source_draft(pack, request, registry, bank, manifest.get("source", "legacy")).passed:
        raise ValueError("Cannot review a draft with failed source checks")
    approved = apply_review(pack, review, request, registry, bank)
    if review.reviewed_at < datetime.fromisoformat(manifest["created_at"]):
        raise ValueError("Review timestamp predates this run")
    destination = path / "reviews" / review.review_id
    if not destination.resolve().is_relative_to(path.resolve()):
        raise ValueError("Invalid review destination")
    destination.mkdir(parents=True, exist_ok=False)
    store.write(destination / "review.json", review.model_dump(mode="json"))
    if approved is not None:
        store.write(destination / "approved-pack.json", approved.model_dump(mode="json"))
    return destination, approved is not None
