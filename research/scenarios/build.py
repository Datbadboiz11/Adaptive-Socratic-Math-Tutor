"""Replay, chia nhóm và xuất độ phủ bộ tình huống thích ứng theo plan §11.5–§12.

    python -m research.scenarios.build --input contracts/scenarios/examples.dev.v1.json --out data/scenarios/example-v1
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from app.agent.kg_tool import KGTool  # noqa: E402
from app.agent.tools import TurnContext  # noqa: E402
from app.kg.graph import KnowledgeGraph  # noqa: E402
from research.scenarios.contracts import BuiltScenario, ScenarioDataset, ScenarioDraft, ScenarioSet  # noqa: E402
from research.scenarios.replay import REPLAY_VERSION, replay  # noqa: E402

PLAN_CASE_TAGS = frozenset({"alternative_correct", "error_propagation", "final_answer_only", "condition_error",
                            "ambiguous_input", "insufficient_evidence", "requests_answer"})
# Plan §12: ít nhất 4 ca/concept trong dev+test, trong đó ít nhất 2 ca test.
MIN_PER_CONCEPT = 4
MIN_TEST_PER_CONCEPT = 2


def grouped_splits(dataset: ScenarioDataset, seed: str) -> dict[str, tuple[str, str]]:
    """Gom liên thông theo mọi bài gốc/họ mẫu/lịch sử trước khi phân dev/test.

    Nhóm chưa gán split được xếp vào bên đang thiếu ca của các concept trong nhóm nhiều hơn (mỗi
    concept cần ``MIN_TEST_PER_CONCEPT`` ca ở mỗi bên), bằng nhau thì mới xét bên có ít ca hơn: chia
    đều theo số ca mà để một concept nằm trọn một bên thì không đạt độ phủ của plan §12."""
    parents = list(range(len(dataset.scenarios)))
    owners = {}
    sources = {p.problem.problem_id: p for p in dataset.problems}

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    for i, scenario in enumerate(dataset.scenarios):
        tokens = {("history", scenario.history_group_id), ("session", str(scenario.session_id))}
        for event in scenario.history:
            source = sources[event.task.problem_id]
            tokens |= {("original", source.original_problem_id), ("family", source.problem.template_family_id),
                       ("turn", str(event.turn_id))}
        for token in tokens:
            if token in owners:
                parents[root(i)] = root(owners[token])
            else:
                owners[token] = i
    groups = {}
    for i, scenario in enumerate(dataset.scenarios):
        groups.setdefault(root(i), []).append(scenario)
    counts = Counter()
    per_concept = {"dev": Counter(), "test": Counter()}

    def assign(group, gid, split):
        counts[split] += len(group)
        if split in per_concept:
            per_concept[split] += Counter(s.history[-1].task.concept_id for s in group)
        result.update({s.scenario_id: (split, gid) for s in group})

    result, pending = {}, []
    for group in groups.values():
        fixed = {s.split for s in group if s.split is not None}
        if len(fixed) > 1:
            raise ValueError("Conflicting splits in linked group: " + ", ".join(s.scenario_id for s in group))
        identity = "|".join(sorted(s.scenario_id for s in group))
        gid = "GRP-" + hashlib.sha256(identity.encode()).hexdigest()[:16]
        if fixed:
            assign(group, gid, fixed.pop())
        else:
            pending.append((group, gid))
    pending.sort(key=lambda item: (-len(item[0]), hashlib.sha256((seed + item[1]).encode()).hexdigest()))
    for group, gid in pending:
        concepts = {s.history[-1].task.concept_id for s in group}

        def shortfall(split):  # số ca split đó còn thiếu ở các concept của nhóm
            return sum(max(0, MIN_TEST_PER_CONCEPT - per_concept[split][c]) for c in concepts)

        assign(group, gid, max(("dev", "test"), key=lambda name: (shortfall(name), -counts[name])))
    return result


def with_graph_context(draft: ScenarioDraft, concept_id: str, kg: KGTool) -> TurnContext:
    """Context của tình huống với phần KG lấy từ registry, như tool của hệ thống trả về
    (``stubs.StubTools``). Cạnh soạn tay có thể lệch registry, và thiếu cạnh thì Full không khác
    No-KG, nên đầu vào phải để trống phần này."""
    context = draft.context
    if context.edges or context.next_concepts:
        raise ValueError(f"{draft.scenario_id}: leave edges and next_concepts empty; "
                         "build reads them from the registry")
    if not context.kg_enabled:
        return context
    found = kg(concept_id)
    return context.model_copy(update={
        "edges": found.edges, "next_concepts": found.next_concepts, "kg_source": found.source,
        "graph_version": found.graph_version, "tool_errors": [*context.tool_errors, *found.errors]})


def build(dataset: ScenarioDataset, *, seed: str = "adaptive-split-v1") -> tuple[dict[str, ScenarioSet], dict, list[dict]]:
    graph = KnowledgeGraph.load()
    known_skills = {skill for concept in graph.concepts.values() for skill in concept.skill_ids}
    if not set(dataset.parameters) <= known_skills:
        raise ValueError("Parameters contain skills outside the curriculum registry")
    sources = {p.problem.problem_id: p for p in dataset.problems}
    for p in dataset.problems:
        concept = graph.concepts.get(p.problem.concept_id)
        if concept is None or p.problem.target_skill_id not in concept.skill_ids:
            raise ValueError(f"Invalid concept/skill for {p.problem.problem_id}")
    for draft in dataset.scenarios:
        for event in draft.history:
            if event.task.problem_id not in sources:
                raise ValueError(f"{draft.scenario_id}: unknown history problem {event.task.problem_id}")
            skill_ids = {event.target_skill_id, event.assessment.primary_skill_id if event.assessment else None}
            if not skill_ids - {None} <= known_skills:
                raise ValueError(f"{draft.scenario_id}: event refers to a skill outside the curriculum registry")
        last_problem = sources[draft.history[-1].task.problem_id]
        if draft.context.current_problem_prompt != last_problem.prompt:
            raise ValueError(f"{draft.scenario_id}: context prompt differs from catalogue")
        for candidate in draft.context.problems:
            if candidate.problem_id not in sources or candidate != sources[candidate.problem_id].problem:
                raise ValueError("Context problem differs from source catalogue")
    assignments = grouped_splits(dataset, seed)
    kg = KGTool(graph, include_drafts=True)  # registry còn nháp: dùng cả cạnh nháp như chế độ dev của hệ thống
    sets = {split: ScenarioSet(dataset_version=dataset.dataset_version, split=split, replay_version=REPLAY_VERSION,
                              parameters=dataset.parameters, problems=dataset.problems,
                              scenarios=[]) for split in ("authoring", "dev", "test")}
    for draft in dataset.scenarios:
        state, trace = replay(draft, dataset, kg)
        split, gid = assignments[draft.scenario_id]
        sets[split].scenarios.append(BuiltScenario(
            scenario_id=draft.scenario_id, title=draft.title, split_group_id=gid, source=draft.source,
            source_reference=draft.source_reference, tags=draft.tags, labels=draft.labels,
            state=state, context=with_graph_context(draft, state.current.concept_id, kg), replay=trace))
    coverage, matrix = coverage_report(sets, graph)
    return sets, {"dataset_version": dataset.dataset_version, "replay_version": REPLAY_VERSION,
                  "seed": seed, "registry_version": graph.registry.content_version,
                  "registry_fingerprint": graph.fingerprint, "kg_include_drafts": kg.include_drafts,
                  "assignments": {sid: {"split": split, "group_id": gid} for sid, (split, gid) in assignments.items()},
                  **coverage}, matrix


def coverage_report(sets: dict[str, ScenarioSet], graph: KnowledgeGraph) -> tuple[dict, list[dict]]:
    matrix, warnings = [], []
    for cid, concept in graph.concepts.items():
        groups = {split: [s for s in data.scenarios if s.state.current.concept_id == cid] for split, data in sets.items()}
        all_cases = [s for cases in groups.values() for s in cases]
        scored = groups["dev"] + groups["test"]
        row = {"concept_id": cid, "title": concept.title, **{split: len(cases) for split, cases in groups.items()},
               "split_groups": len({s.split_group_id for s in all_cases}),
               "tags": ",".join(sorted({tag for s in all_cases for tag in s.tags})),
               "error_families": ",".join(sorted({s.state.latest_assessment.error_family for s in all_cases
                                                 if s.state.latest_assessment and s.state.latest_assessment.error_family})),
               "hint_levels": ",".join(map(str, sorted({s.state.support.hint_level for s in all_cases})))}
        matrix.append(row)
        if len(scored) < MIN_PER_CONCEPT or len(groups["test"]) < MIN_TEST_PER_CONCEPT:
            warnings.append(f"{cid}: dev+test={len(scored)}/{MIN_PER_CONCEPT}, "
                            f"test={len(groups['test'])}/{MIN_TEST_PER_CONCEPT}")
    test_count = len(sets["test"].scenarios)
    total = len(sets["dev"].scenarios) + test_count
    if not 160 <= total <= 200:
        warnings.append(f"Dev+test total {total}; plan target 160–200")
    if not 80 <= test_count <= 100:
        warnings.append(f"Test total {test_count}; plan target 80–100")
    for split in ("dev", "test"):
        present = {tag for case in sets[split].scenarios for tag in case.tags}
        for tag in sorted(PLAN_CASE_TAGS - present):
            warnings.append(f"{split}: missing situation category {tag}")
    details = {}
    for split, data in sets.items():
        cases = data.scenarios
        details[split] = {
            "scenarios": len(cases), "groups": len({s.split_group_id for s in cases}),
            "sources": dict(Counter(s.source for s in cases)),
            "label_statuses": dict(Counter(s.labels.review_status for s in cases)),
            "tags": dict(Counter(tag for s in cases for tag in set(s.tags))),
            "acceptable_actions": dict(Counter(a.value for s in cases for a in set(s.labels.acceptable_actions))),
            "assessment_statuses": dict(Counter(s.state.latest_assessment.assessment_status if s.state.latest_assessment
                                                 else "none" for s in cases)),
        }
    return {"splits": details, "coverage_warnings": warnings}, matrix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--seed", default="adaptive-split-v1")
    args = parser.parse_args(argv)
    if args.out.exists() and any(args.out.iterdir()):
        parser.error(f"{args.out} already contains files")
    raw = args.input.read_bytes()
    dataset = ScenarioDataset.model_validate_json(raw.decode("utf-8-sig"))
    sets, report, matrix = build(dataset, seed=args.seed)
    report["source_sha256"] = hashlib.sha256(raw).hexdigest()
    args.out.mkdir(parents=True, exist_ok=True)
    for split, data in sets.items():
        (args.out / f"{split}.json").write_text(data.model_dump_json(indent=2) + "\n", encoding="utf-8")
    (args.out / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (args.out / "coverage.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(matrix[0]))
        writer.writeheader()
        writer.writerows(matrix)
    print(f"Built {len(dataset.scenarios)} scenarios in {args.out}")
    print(f"Coverage warnings: {len(report['coverage_warnings'])}; see manifest.json and coverage.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
