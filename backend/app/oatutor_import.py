"""Bounded OATutor pilot adapter. Source selection and human approval stay explicit."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

from app.authoring_math import audit_case, polynomial, scalar
from app.content_authoring import (
    DraftRequest, GeneratedContent, check_draft, make_draft, review_template,
)
from app.curriculum import Source

REPOSITORY = "https://github.com/CAHLR/OATutor-Content"
RAW_ROOT = "https://raw.githubusercontent.com/CAHLR/OATutor-Content"
LICENSE = "https://creativecommons.org/licenses/by/4.0/"
SOURCE_ID = "SRC-OATUTOR-PILOT-V1"
PROTOCOL = "oatutor-pilot-1.0.0"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def item_paths(problem_id, step_letters):
    require(bool(re.fullmatch(r"[A-Za-z0-9]{1,60}", problem_id)), "Unsupported upstream ID")
    require(step_letters and len(set(step_letters)) == len(step_letters)
            and all(s in ("a", "b") for s in step_letters), "Unsupported step selection")
    root = f"content-pool/{problem_id}"
    result = [f"{root}/{problem_id}.json"]
    for letter in step_letters:
        step = problem_id + letter
        result += [f"{root}/steps/{step}/{step}.json",
                   f"{root}/steps/{step}/tutoring/{step}DefaultPathway.json"]
    return result


def selection_paths(selection):
    require(bool(re.fullmatch(r"[a-f0-9]{40}", selection["upstream_commit"])), "Pin a full commit SHA")
    require(selection["repository"] == REPOSITORY, "Unexpected repository")
    paths = ["README.md"]
    for concept in selection["concepts"]:
        for spec in concept["problems"]:
            if spec["origin_kind"] == "oatutor_adapted":
                paths.extend(item_paths(spec["upstream_problem_id"], spec["upstream_steps"]))
    paths = sorted(set(paths))
    require(len(paths) <= 40, "Pilot download exceeds the selected-file budget")
    return paths


def fetch_snapshot(selection, destination):
    """Fetch only selected files from a fixed host; collect before claiming a new directory."""
    destination = Path(destination)
    require(not destination.exists(), "Source destination already exists; never overwrite a snapshot")
    paths = selection_paths(selection)
    commit = selection["upstream_commit"]
    payloads = {}
    for path in paths:
        request = Request(f"{RAW_ROOT}/{commit}/{path}", headers={"User-Agent": "Member2-OATutor-pilot"})
        with urlopen(request, timeout=30) as response:
            require(response.status == 200, "Upstream file unavailable")
            require(response.geturl() == request.full_url, "Unexpected upstream redirect")
            data = response.read(1024 * 1024 + 1)
        require(len(data) <= 1024 * 1024, "Source file exceeds one MiB")
        if path.endswith(".json"):
            json.loads(data)
        payloads[path] = data
    readme = payloads["README.md"].decode("utf-8")
    require(LICENSE in readme and "All content in this repository" in readme,
            "Repository license statement changed; review before proceeding")
    destination.mkdir(parents=True, exist_ok=False)
    files = []
    for name, data in payloads.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
        files.append({"path": name, "sha256": hashlib.sha256(data).hexdigest(),
                      "url": f"{REPOSITORY}/blob/{commit}/{name}"})
    manifest = {"protocol_version": PROTOCOL, "repository": REPOSITORY, "commit": commit,
                "retrieved_at": datetime.now(timezone.utc).isoformat(), "files": files,
                "coverage": "Selected A02/E02 pilot only; not an inventory of the entire repository"}
    write_json(destination / "snapshot.json", manifest)
    return manifest


def verify_snapshot(selection, root):
    root = Path(root).resolve()
    manifest = read_json(root / "snapshot.json")
    require(manifest["protocol_version"] == PROTOCOL and manifest["repository"] == REPOSITORY
            and manifest["commit"] == selection["upstream_commit"], "Source snapshot identity mismatch")
    paths = selection_paths(selection)
    require(sorted(f["path"] for f in manifest["files"]) == paths, "Source snapshot file selection mismatch")
    for entry in manifest["files"]:
        path = (root / entry["path"]).resolve()
        require(path.is_relative_to(root), "Source path escapes snapshot")
        require(file_hash(path) == entry["sha256"], "Changed upstream file: " + entry["path"])
        require(entry["url"] == f"{REPOSITORY}/blob/{manifest['commit']}/{entry['path']}", "Incorrect source URL")
    return manifest


def normalize_math(text, variable="x"):
    """Deliberately small TeX subset. Unsupported markup is rejected, never evaluated."""
    require(variable in ("x", "y", "m"), "Undeclared variable rename")
    matches = re.findall(r"\$\$(.*?)\$\$", text, flags=re.S)
    if matches:
        require(len(matches) == 1, "Expected exactly one math span")
        text = matches[0]
    else:
        require("$" not in text, "Unsupported math delimiter")
    text = text.replace(r"\left", "").replace(r"\right", "")
    text = re.sub(r"\s+", "", text)
    text = text.replace(variable, "x")
    require(0 < len(text) <= 160 and bool(re.fullmatch(r"[0-9x+*/().=\-]+", text)),
            "Unsupported source math; extend the adapter with tests before importing")
    text = re.sub(r"(?<=[0-9])(?=x)", "*", text)
    text = re.sub(r"(?<=[0-9x)])(?=\()", "*", text)
    text = re.sub(r"(?<=\))(?=[0-9x])", "*", text)
    return text


def source_item(spec, root):
    pid = spec["upstream_problem_id"]
    paths = item_paths(pid, spec["upstream_steps"])
    values = [read_json(Path(root) / p) for p in paths]
    parent, steps, tutoring = values[0], values[1::2], values[2::2]
    require(parent["id"] == pid, "Wrong upstream parent")
    require(spec["split_group"] == "OATUTOR-LESSON-" + parent["lessonId"], "Keep a whole source lesson in one split group")
    for letter, step in zip(spec["upstream_steps"], steps):
        require(step["id"] == pid + letter, "Wrong upstream step")
        require(not step.get("variabilization"), "Variabilized content needs a separate adapter")
    require(not parent.get("variabilization"), "Variabilized parent is unsupported")
    records = [parent, *steps, *[hint for pathway in tutoring for hint in pathway]]
    for record in records:
        license_text = record.get("license", "")
        require(not license_text or LICENSE in license_text, "Nonstandard per-item license needs review")
    expression_text = parent["body"] if spec["expression_from"] == "parent_body" else steps[0]["stepTitle"]
    expression = normalize_math(expression_text, spec.get("variable", "x"))
    if spec.get("answer_from") == "coefficient_and_constant":
        require(len(steps) == 2 and all(len(s["stepAnswer"]) == 1 for s in steps), "Need coefficient and constant steps")
        require("coefficient" in steps[0]["stepTitle"].lower() and "constant" in steps[1]["stepTitle"].lower(),
                "Upstream component question order changed")
        coefficient, constant = [scalar(normalize_math(s["stepAnswer"][0], spec.get("variable", "x"))) for s in steps]
        require(polynomial(expression) == (constant, coefficient, 0), "Source component answers disagree")
        answer = f"{coefficient}*x+({constant})"
    else:
        require(len(steps) == 1 and len(steps[0]["stepAnswer"]) == 1, "Unsupported answer alternatives")
        answer = normalize_math(steps[0]["stepAnswer"][0], spec.get("variable", "x"))
    return expression, answer, {
        "upstream_problem_id": pid, "upstream_step_ids": [s["id"] for s in steps],
        "raw_files": paths, "oer": parent.get("oer"), "course": parent.get("courseName"),
        "lesson": parent.get("lesson"), "lesson_id": parent.get("lessonId"),
        "upstream_license_fields": [{"record_id": r.get("id"), "license": r.get("license", "")} for r in records],
        "license_basis": "repository_README_CC_BY_4.0; retain per-item fields, including blanks",
        "attribution": "Adapted from OATutor Project / OpenStax; " + REPOSITORY + "/tree/" + spec["commit"]
                       + "/content-pool/" + pid + "; " + LICENSE,
        "changes": spec["changes"],
        "upstream_tutoring_usage": "Archived for review only; raw hintAnswer and terminal hints are not teaching chunks",
    }


def registry_with_source(registry, selection, accessed_on):
    source = Source(source_id=SOURCE_ID, title="OATutor-Content: selected A02/E02 pilot",
                    url=REPOSITORY + "/tree/" + selection["upstream_commit"],
                    publisher="OATutor Project / OpenStax", accessed_on=accessed_on,
                    note="CC BY 4.0 per pinned README; item-level notices retained separately. "
                         "Supplemental exercises, not authority for Vietnamese grade alignment; human review pending.")
    data = registry.model_dump(mode="json")
    require(SOURCE_ID not in {s["source_id"] for s in data["sources"]}, "Source overlay would replace an existing source")
    data["sources"].append(source.model_dump(mode="json"))
    for cid, override in selection.get("scope_overrides", {}).items():
        concept = next((c for c in data["concepts"] if c["concept_id"] == cid), None)
        require(concept is not None and concept["review"]["status"] == "draft", "Only draft concept scopes can be narrowed")
        require(set(override) == {"supported_forms"}, "Scope overlays may only narrow supported forms")
        forms = override["supported_forms"]
        require(forms and len(forms) == len(set(forms)) and set(forms).issubset(concept["supported_forms"]),
                "Scope overlay cannot introduce new forms")
        concept["supported_forms"] = forms
    return type(registry).model_validate(data)


def prepare_packs(selection, source_root, registry, bank, configs):
    """Return new drafts plus per-record provenance; do not mutate the canonical bank."""
    source = verify_snapshot(selection, source_root)
    staged_registry = registry_with_source(registry, selection, source["retrieved_at"][:10])
    prepared = {}
    for data in selection["concepts"]:
        cid = data["concept_id"]
        require(cid in ("A02", "E02"), "Pilot scope is A02/E02")
        require(cid not in prepared, "Duplicate concept in selection")
        config = dict(configs[cid])
        if "families" in data:
            config["families"] = data["families"]
        config.update(revision=selection["revision"], model="offline-codex-assisted",
                      source_ids=[*config["source_ids"], SOURCE_ID])
        request = DraftRequest.model_validate(config)
        problems, provenance = [], []
        for i, spec in enumerate(data["problems"], 1):
            record_id = request.id_prefix + f"P-{i:02}"
            require(type(spec["family_index"]) is int and 0 <= spec["family_index"] < 3, "Invalid family index")
            family = request.families[spec["family_index"]]
            kind = "polynomial" if cid == "A02" else "linear_equation"
            if spec["origin_kind"] == "oatutor_adapted":
                expression, answer, origin = source_item({**spec, "commit": selection["upstream_commit"]}, source_root)
                origin_text = origin["attribution"] + " Changes: " + "; ".join(spec["changes"])
            else:
                require(spec["origin_kind"] == "ai_generated_supplement", "Unknown origin kind")
                expression, answer = spec["expression"], spec["answer"]
                origin = {"upstream_problem_id": None, "raw_files": [], "changes": [],
                          "generation_method": "Codex-assisted authoring in this session; no external API call",
                          "reason": spec["reason"], "not_observed_student_data": True}
                origin_text = "AI-generated supplement; not an OATutor problem. " + spec["reason"]
            problem = {"case_id": record_id, "concept_id": cid,
                       "primary_skill_id": "SK-A02-DISTRIBUTE" if cid == "A02" else "SK-E02-SOLVE",
                       "family_id": family.family_id, "source_group": family.source_group,
                       "difficulty": "introductory" if spec["family_index"] == 0 else "standard",
                       "prompt": spec["instruction_vi"] + " " + expression + ". Trình bày các bước.",
                       "task": {"kind": kind, "expression": expression, "variable_value": None},
                       "reference_answer": answer, "reference_steps": spec["steps"],
                       "split": "authoring_dev", "origin": origin_text}
            problems.append(problem)
            provenance.append({"record_id": record_id, "record_type": "problem", "origin_kind": spec["origin_kind"],
                               "split_group": spec["split_group"], "human_review": "pending", **origin})
        examples = [{"case_id": request.id_prefix + f"EX-{i:02}",
                     "task": {"kind": "polynomial" if cid == "A02" else "linear_equation",
                              "expression": e["expression"], "variable_value": None},
                     "reference_answer": e["answer"], "reference_steps": e["steps"]}
                    for i, e in enumerate(data["examples"], 1)]
        errors = [{"error_id": request.id_prefix + f"ERR-{i:02}",
                   "problem_id": problems[e["problem_index"]]["case_id"],
                   **{k: v for k, v in e.items() if k != "problem_index"}}
                  for i, e in enumerate(data["errors"], 1)]
        content = GeneratedContent(explanation=data["explanation"], problems=problems,
                                   examples=examples, errors=errors, hints=data["hints"])
        pack = make_draft(content, request)
        pack.review.source = "Staged source pilot: " + REPOSITORY + "/tree/" + selection["upstream_commit"] \
            + "; per-record provenance.json distinguishes adaptations from AI supplements; human review pending."
        for case in [*pack.problems, *pack.examples]:
            audit_case(case)
        result = check_draft(pack, request, staged_registry, bank)
        require(result.passed, "Draft has machine-check errors: " + result.model_dump_json())
        for record_type, records, id_key in (("example", examples, "case_id"), ("error_fixture", errors, "error_id")):
            for record in records:
                provenance.append({"record_id": record[id_key], "record_type": record_type,
                                   "origin_kind": "ai_generated_supplement", "upstream_problem_id": None,
                                   "generation_method": "Codex-assisted authoring; no external API call",
                                   "human_review": "pending", "split_group": f"PROJECT-{cid}-SUPPORT-DEV",
                                   "not_observed_student_data": True})
        provenance.append({"record_id": cid + "-teaching-text", "record_type": "explanation_and_hints",
                           "origin_kind": "ai_generated_supplement", "upstream_problem_id": None,
                           "generation_method": "Codex-assisted authoring; no external API call",
                           "human_review": "pending", "split_group": f"PROJECT-{cid}-SUPPORT-DEV",
                           "not_observed_student_data": True})
        prepared[cid] = {"request.json": request.model_dump(mode="json"), "draft.json": pack.model_dump(mode="json"),
                         "checks.json": {**result.model_dump(mode="json"), "passed": result.passed},
                         "review-template.json": review_template(pack), "provenance.json": provenance}
    require(set(prepared) == {"A02", "E02"}, "Both pilot concepts required exactly once")
    return staged_registry, prepared
