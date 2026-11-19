"""Check proposed contracts, example consistency and generated coverage; no DB/API calls."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.curriculum import load_curriculum
from app.math_validator import VERSION as VALIDATOR_VERSION
from app.member2_contracts import FoundationExamples, ServerRetrievalScope
from app.member2_foundation import build_coverage, load_workboard, public_problem_examples, render_coverage

EXAMPLES = ROOT / "contracts/member2/v0.2.0/examples.json"
SCHEMA = ROOT / "contracts/member2/v0.2.0/FoundationExamples.schema.json"
COVERAGE = ROOT / "docs/implementation/member2/part1/coverage.json"
COVERAGE_MD = ROOT / "docs/implementation/member2/part1/coverage.md"


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def check_examples(registry=None, bank=None):
    if registry is None or bank is None:
        registry, bank = load_curriculum()
    examples = FoundationExamples.model_validate_json(EXAMPLES.read_text(encoding="utf-8"))
    if [p.model_dump(mode="json") for p in examples.problems] != public_problem_examples(registry, bank):
        raise ValueError("Public problem fixtures no longer match the authoring projections")
    concepts = {c.concept_id: c for c in registry.concepts}
    for exchange in examples.retrieval_exchanges:
        ServerRetrievalScope.from_registry(registry, **exchange.request.scope.model_dump())
        query = exchange.request.query
        if query.target_skill_id not in {s.skill_id for s in concepts[query.concept_id].skills}:
            raise ValueError("Retrieval fixture references an unknown concept/skill mapping")
    return examples


def rendered_artifacts():
    registry, bank = load_curriculum()
    check_examples(registry, bank)
    workboard = load_workboard()
    legacy = json.loads((ROOT / "content/linear_equations.v1.json").read_text(encoding="utf-8"))
    parameters = json.loads((ROOT / "content/bkt.bootstrap.v1.json").read_text(encoding="utf-8"))
    evidence = workboard.runtime_evidence
    if (evidence.validator_version != VALIDATOR_VERSION or parameters["skill_id"] != evidence.legacy_skill_id
            or any(p["concept_id"] != evidence.legacy_concept_id or
                   p["primary_skill_id"] != evidence.legacy_skill_id for p in legacy["problems"])):
        raise ValueError("Legacy evidence changed; review the workboard before regenerating")
    report = build_coverage(registry, bank, workboard)
    return {
        "schema": (SCHEMA, json_text(FoundationExamples.model_json_schema())),
        "coverage-json": (COVERAGE, json_text(report)),
        "coverage-md": (COVERAGE_MD, render_coverage(report)),
    }, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", choices=["schema", "coverage-json", "coverage-md"])
    args = parser.parse_args()
    artifacts, report = rendered_artifacts()
    if args.render:
        print(artifacts[args.render][1], end="")
        return
    errors = [str(p.relative_to(ROOT)) for p, content in artifacts.values()
              if not p.exists() or p.read_text(encoding="utf-8") != content]
    if errors:
        raise SystemExit("Stale or missing generated artifacts: " + ", ".join(errors))
    print("PASS: Member 2 proposed schemas, synthetic fixtures and coverage are consistent")
    print(json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
