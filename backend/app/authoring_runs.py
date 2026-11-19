"""Immutable authoring runs and explicit manual review. No runtime bank writes."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from pydantic import ValidationError

from app.content_authoring import (
    AUTHORING_VERSION, PROMPT_VERSION, ContentReview, DraftRequest, GeneratedContent,
    apply_review, build_prompt, canonical_json, check_draft, digest, make_draft,
    request_concept, review_template,
)
from app.curriculum import ConceptPack, load_curriculum

ROOT = Path(__file__).resolve().parents[2]
RUN_ROOT = ROOT / "artifacts/authoring"
TEMPLATE = ROOT / "content/authoring/prompts/draft.v1.txt"
MAX_JSON_BYTES = 2 * 1024 * 1024


class GenerationError(ValueError):
    pass


def load_json(path):
    path = Path(path)
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("Authoring JSON exceeds the two MiB limit")
    return json.loads(path.read_text(encoding="utf-8"))


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
               store=None, client_factory=None):
    store = store or RunStore()
    registry, bank = load_curriculum()
    request_concept(request, registry)
    template = TEMPLATE.read_text(encoding="utf-8")
    prompt = build_prompt(request, registry, template)
    path = store.create(run_id)  # Claim before any model call; never overwrite/retry a run implicitly.
    hashes = {}

    def write(name, value):
        hashes[name] = store.write(path / name, value)

    write("request.json", request.model_dump(mode="json"))
    write("prompt.json", prompt)
    metadata = {"provider": provider, "model_calls": 0}
    status = "failed"
    failure = None
    try:
        if provider == "openai":
            metadata = {"provider": "openai", "model_requested": request.model,
                        "model_call_attempts": int(os.getenv("AUTHORING_LLM_ENABLED", "false").lower() == "true"
                                                   and bool(os.getenv("OPENAI_API_KEY")))}
            content, metadata = generate_openai(request, prompt, client_factory)
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
        check = check_draft(pack, request, registry, bank)
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
        "protocol_version": AUTHORING_VERSION, "prompt_version": PROMPT_VERSION,
        "run_id": run_id, "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status, "generation": metadata, "request_sha256": digest(request.model_dump(mode="json")),
        "prompt_sha256": digest(prompt), "registry_sha256": digest(registry.model_dump(mode="json")),
        "bank_sha256": digest(bank.model_dump(mode="json")), "artifact_sha256": hashes,
        "publication": "draft_only_not_seeded", "human_review": "pending",
    }
    store.write(path / "manifest.json", manifest)
    return path, manifest


def verify_run(path):
    manifest = load_json(path / "manifest.json")
    # Artifact names are protocol-owned, never arbitrary paths supplied in a manifest.
    allowed = {"request.json", "prompt.json", "generated.json", "draft.json", "checks.json", "review-template.json", "failure.json"}
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
    return manifest


def review_run(run_id, review: ContentReview, *, store=None):
    store = store or RunStore()
    path = store.path(run_id)
    manifest = verify_run(path)
    registry, bank = load_curriculum()
    if (manifest["registry_sha256"] != digest(registry.model_dump(mode="json"))
            or manifest["bank_sha256"] != digest(bank.model_dump(mode="json"))):
        raise ValueError("Registry/bank changed; create a fresh review run")
    request = DraftRequest.model_validate(load_json(path / "request.json"))
    pack = ConceptPack.model_validate(load_json(path / "draft.json"))
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
