"""Build/check the reviewed 13-concept KB publication and retrieval-dev assets."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT / "backend", ROOT, ROOT / "scripts/authoring"):
    sys.path.insert(0, str(path))

from app.kb_contracts import ExamplePublication
from app.kb_projection import load_profile, load_source, project
from app.manage import digest
from prepare_member2_pilot import rendered_pilot

SOURCE = ROOT / "content/authoring/batches/member2-original.v2"
PUBLICATION = ROOT / "content/kb/member2-v2"
BENCHMARK = ROOT / "research/retrieval/dev/member2-13.v1"
EXAMPLE_VERSION = "0.4.1-member2-kb-examples"

TOPICS = {
    "A01": "thay giá trị vào biểu thức",
    "A04": "nhân và thu gọn đa thức",
    "A07": "đặt nhân tử chung",
    "A10": "thực hiện phép toán với phân thức đại số",
    "E03": "lập phương trình từ bài toán có lời văn",
    "E06": "giải phương trình bậc hai bằng biệt thức",
    "E09": "giải hệ phương trình bằng phương pháp khử",
    "F02": "tìm tập xác định của hàm số",
    "F05": "tìm đỉnh hoặc trục đối xứng của parabol",
    "F08": "vận dụng quy tắc của hàm số mũ",
    "N02": "nhân và chia số nguyên có dấu",
    "N05": "so sánh phân số bằng quy đồng",
    "N08": "đổi giữa phân số, số thập phân và phần trăm",
}


def file_hash_bytes(content):
    return hashlib.sha256(content).hexdigest()


def file_hash(path):
    return file_hash_bytes(Path(path).read_bytes())


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def task_text(example):
    task = example.task
    suffix = f" khi x = {task.variable_value}" if task.variable_value is not None else ""
    return f"`{task.expression}`{suffix}"


def build_examples(bank):
    artifacts, _ = rendered_pilot("v2")
    approval = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    publications = []
    for pack in bank.packs:
        material = artifacts[f"{pack.concept_id}/review.md"]
        if file_hash_bytes(material.encode("utf-8")) != approval["packs"][pack.concept_id]["review_material_sha256"]:
            raise ValueError("Example teaching material differs from the approved review: " + pack.concept_id)
        sections = material.split("**Ví dụ** ")[1:]
        if len(sections) != len(pack.examples):
            raise ValueError("Reviewed example sections are missing")
        for index, example in enumerate(pack.examples):
            # The three reviewed examples follow the three reviewed problem
            # families.  Keep that lineage so a nearby example is excluded.
            related = pack.problems[index * 2]
            # Copy the displayed prompt and worked explanation verbatim from the
            # exact review material approved by the user. No private answer field
            # is turned into prose and no new human approval is invented.
            teaching_text = sections[index].split("\n\nDạng đáp án dùng trong checker ", 1)[0].strip()
            publications.append(ExamplePublication(
                case_id=example.case_id,
                content_version=EXAMPLE_VERSION,
                pack_hash=digest(pack.model_dump(mode="json")),
                family_id=related.family_id,
                source_group=f"EXAMPLE-{pack.concept_id}-M2-ORIG02-{index + 1}",
                lineage_ids=[related.source_group, related.family_id],
                difficulty=None,
                teaching_text=teaching_text,
                review=pack.review,
            ))
    if len(publications) != 39 or len({item.case_id for item in publications}) != 39:
        raise ValueError("Expected 39 unique reviewed example publications")
    return publications


def eligible(chunk, query):
    return (
        chunk.concept_id == query["concept_id"]
        and query["target_skill_id"] in chunk.skill_ids
        and chunk.kind == query["purpose"]
        and chunk.hint_level <= query["allowed_hint_level"]
        and set(chunk.grade_levels).intersection(query["grade_levels"])
        and (chunk.difficulty is None or chunk.difficulty == query["difficulty"])
        and chunk.problem_id != query["active_problem_id"]
        and chunk.source_group not in query["excluded_source_groups"]
        and not (chunk.kind == "example" and (
            chunk.family_id in query["excluded_family_ids"]
            or set(chunk.lineage_ids).intersection(query["excluded_lineage_ids"])
        ))
    )


def scope_fields(pack, concept, active):
    return {
        "concept_id": pack.concept_id,
        "target_skill_id": concept.skills[0].skill_id,
        "active_problem_id": active.case_id,
        "excluded_source_groups": [active.source_group],
        "excluded_family_ids": [active.family_id],
        "excluded_lineage_ids": [active.source_group, active.family_id],
        "grade_levels": concept.alignment.grade_levels,
        "difficulty": active.difficulty,
    }


def build_benchmark(registry, bank, projection):
    concepts = {item.concept_id: item for item in registry.concepts}
    chunks = list(projection.chunks)
    queries = []

    def add(pack, suffix, text, purpose, allowed, active, target_ids, *, exclusions=None):
        row = {
            "query_id": f"M2-{pack.concept_id}-{suffix}",
            "query": text,
            "purpose": purpose,
            "top_k": 5,
            "allowed_hint_level": allowed,
            **scope_fields(pack, concepts[pack.concept_id], active),
            "target_content_ids": target_ids,
            "label_status": "deterministic_dev_judgment_from_reviewed_teaching_intent",
            "human_reviewed": False,
        }
        if exclusions:
            row.update(exclusions)
        row["eligible_candidate_ids"] = [chunk.content_id for chunk in chunks if eligible(chunk, row)]
        if not set(target_ids).issubset(row["eligible_candidate_ids"]):
            raise ValueError("A benchmark target is outside its server scope: " + row["query_id"])
        queries.append(row)

    for pack in bank.packs:
        topic = TOPICS[pack.concept_id]
        active = pack.problems[0]
        add(pack, "EXPLANATION", f"Em chưa hiểu cách {topic}; hãy giải thích nguyên tắc chính.",
            "explanation", 0, active, [pack.concept_id + "-explanation"])
        hint_queries = (
            f"Em chưa biết bắt đầu bài {topic} từ đâu; chỉ hỏi em một câu định hướng.",
            f"Em cần một chiến lược tiếp theo để tự làm bài {topic}, chưa cần lời giải.",
            f"Em vẫn mắc kẹt với bài {topic}; hãy nêu khung bước cụ thể nhưng không giải bài hiện tại.",
        )
        for level, text in enumerate(hint_queries, 1):
            add(pack, f"HINT-{level}", text, "hint", level, active,
                [f"{pack.concept_id}-hint-{level}"])
        example_chunks = [chunk for chunk in chunks
                          if chunk.concept_id == pack.concept_id and chunk.kind == "example"]
        for index, example in enumerate(pack.examples):
            # Exclude a different family so the requested target stays eligible
            # while the benchmark still exercises family/lineage filtering.
            active_example_problem = pack.problems[((index + 1) % 3) * 2]
            add(pack, f"EXAMPLE-{index + 1}",
                f"Cho em một ví dụ khác về {topic}, gần với dạng {task_text(example)}, có kết quả để tự đối chiếu.",
                "example", 3, active_example_problem, [example.case_id])
        add(pack, "FALLBACK", f"Cho em một ví dụ khác về {topic} nhưng không dùng lại bất kỳ họ bài đã loại nào.",
            "example", 3, active, [], exclusions={
                "excluded_source_groups": [chunk.source_group for chunk in example_chunks],
                "excluded_family_ids": sorted({chunk.family_id for chunk in example_chunks}),
                "excluded_lineage_ids": sorted({lineage for chunk in example_chunks for lineage in chunk.lineage_ids}),
            })

    qrels = []
    for query in queries:
        targets = set(query["target_content_ids"])
        for content_id in query["eligible_candidate_ids"]:
            qrels.append({
                "query_id": query["query_id"],
                "content_id": content_id,
                "relevance": 2 if content_id in targets else 1,
                "label_status": query["label_status"],
                "human_reviewed": False,
                "rationale": "Exact intended teaching unit" if content_id in targets else "Eligible related unit for the same purpose",
            })
    if len(queries) != 104 or len({q["query_id"] for q in queries}) != 104:
        raise ValueError("Expected eight benchmark queries for each of 13 concepts")
    if sum(not q["eligible_candidate_ids"] for q in queries) != 13:
        raise ValueError("Expected one explicit fallback query per concept")
    corpus = {
        "snapshot_id": projection.snapshot_id,
        "content_version": registry.content_version,
        "documents": [chunk.model_dump(mode="json") for chunk in chunks],
    }
    return corpus, queries, qrels


def assets():
    registry, bank, _ = load_source("member2-v2")
    examples = build_examples(bank)
    examples_data = [item.model_dump(mode="json") for item in examples]
    examples_content = json_bytes(examples_data)
    source_hashes = {
        "content/authoring/batches/member2-original.v2/manifest.json": file_hash(SOURCE / "manifest.json"),
        "content/authoring/batches/member2-original.v2/approved-bank.json": file_hash(SOURCE / "approved-bank.json"),
        "content/authoring/batches/member2-original.v2/registry-snapshot.json": file_hash(SOURCE / "registry-snapshot.json"),
        "content/kb/member2-v2/example-publications.json": file_hash_bytes(examples_content),
    }
    approval = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    source_hashes.update(approval["source_sha256"])
    publication_manifest = {
        "publication_version": "member2-kb-publication-1.0.0",
        "content_version": registry.content_version,
        "example_content_version": EXAMPLE_VERSION,
        "concept_ids": [pack.concept_id for pack in bank.packs],
        "concept_count": len(bank.packs),
        "pack_count": len(bank.packs),
        "explanation_hint_chunk_count": len(bank.packs) * 4,
        "example_count": len(examples),
        "expected_runtime_chunk_count": len(bank.packs) * 7,
        "review_basis": "Verbatim example prompts and worked explanations extracted from the exact review materials approved in M2-ORIG02; no new human review claimed.",
        "review_material_sha256": {cid: entry["review_material_sha256"] for cid,entry in approval["packs"].items()},
        "source_file_sha256": source_hashes,
    }
    projection = project(registry, bank, load_profile(), origin="content/authoring/batches/member2-original.v2",
                         examples=examples)
    if len(projection.chunks) != 91 or projection.blocked:
        raise ValueError("The approved 13-concept projection must publish 91 chunks without blockers")
    corpus, queries, qrels = build_benchmark(registry, bank, projection)
    corpus_content, queries_content, qrels_content = map(json_bytes, (corpus, queries, qrels))
    benchmark_manifest = {
        "benchmark_version": "member2-13-retrieval-dev-1.0.0",
        "snapshot_id": projection.snapshot_id,
        "content_version": registry.content_version,
        "concept_ids": [pack.concept_id for pack in bank.packs],
        "concept_count": len(bank.packs),
        "document_count": len(corpus["documents"]),
        "query_count": len(queries),
        "judgment_count": len(qrels),
        "fallback_query_count": sum(not query["eligible_candidate_ids"] for query in queries),
        "relevance_threshold": 2,
        "ndcg_gain_by_grade": {"0": 0, "1": 1, "2": 3},
        "label_review": "deterministic_development_labels_not_independent_human_gold",
        "runtime_publication": True,
        "source_file_sha256": source_hashes,
        "output_file_sha256": {
            "corpus.json": file_hash_bytes(corpus_content),
            "queries.json": file_hash_bytes(queries_content),
            "qrels.json": file_hash_bytes(qrels_content),
        },
    }
    return {
        PUBLICATION / "example-publications.json": examples_content,
        PUBLICATION / "manifest.json": json_bytes(publication_manifest),
        BENCHMARK / "corpus.json": corpus_content,
        BENCHMARK / "queries.json": queries_content,
        BENCHMARK / "qrels.json": qrels_content,
        BENCHMARK / "manifest.json": json_bytes(benchmark_manifest),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = assets()
    for path, content in generated.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != content:
                raise ValueError("Missing or stale Stage 3 asset: " + str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    print(json.dumps({"status": "passed", "mode": "check" if args.check else "write",
                      "files": len(generated), "concepts": 13, "chunks": 91,
                      "queries": 104}, ensure_ascii=True))


if __name__ == "__main__":
    main()
