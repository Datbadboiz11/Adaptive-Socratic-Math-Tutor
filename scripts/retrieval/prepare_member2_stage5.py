"""Prepare Stage 5 only for Member 2's thirteen approved concepts, without provider calls."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for folder in (ROOT, ROOT / "backend"):
    sys.path.insert(0, str(folder))

from app.content_authoring import digest
from app.kb_projection import load_example_publications, load_profile, load_source, project
from app.member2_foundation import load_workboard
from research.retrieval.dataset import (
    audit_splits, json_bytes, make_workset, require, review_template, sha256, write_new_bundle,
)

DATASET = "research/retrieval/stage5/member2-13.v1"
DATASET_ID = "stage5-member2-13-dev-1.0.0"
BENCHMARK = "research/retrieval/dev/member2-13.v1"

# Topic-specific wording, not independent human judgments or final test queries.
INTENTS = {
    "A01": ("thay giá trị vào biểu thức", "thay số âm có cần đặt ngoặc ở mọi vị trí x không", "Em hay nhầm thế số âm và tính bình phương số âm."),
    "A04": ("nhân đơn thức và đa thức", "mỗi hạng tử phải nhân với những hạng tử nào", "Em muốn hỏi về nhân da thuc và các tích chéo."),
    "A07": ("đặt nhân tử chung", "đưa nhân tử ra ngoài rồi phần trong ngoặc được tính thế nào", "Nhân tử chung có giống một hạng tử được mang nguyên ra ngoài không?"),
    "A10": ("phép toán phân thức", "khử nhân tử rồi có giữ điều kiện mẫu ban đầu không", "Em nhầm điều kiện của phân thức chia với điều kiện mẫu của nó."),
    "E03": ("lập phương trình từ lời văn", "chọn ẩn, đơn vị và quan hệ hơn kém theo thứ tự nào", "Em không biết chuyển chữ hơn thành biểu thức thế nào."),
    "E06": ("biệt thức và nghiệm phương trình bậc hai", "biệt thức bằng không và âm khác nhau thế nào", "Em chưa phân biệt nghiệm kép với không có nghiệm thực."),
    "E09": ("khử ẩn trong hệ phương trình", "có phải nhân cả hai vế trước khi cộng hoặc trừ hai hàng không", "Em muốn hỏi phep cong dai so khi các hệ số chưa đối nhau."),
    "F02": ("tập xác định", "mẫu khác không và biểu thức dưới căn không âm khác nhau thế nào", "Miền xác định có phải chỉ loại các giá trị làm mẫu bằng không không?"),
    "F05": ("đỉnh và trục đối xứng parabol", "tọa độ đỉnh khác phương trình trục đối xứng thế nào", "Em cứ nhầm hoành độ đỉnh với cả tọa độ đỉnh."),
    "F08": ("quy tắc hàm số mũ", "khi nhân, chia hoặc lấy lũy thừa của lũy thừa thì xử lý số mũ thế nào", "Em đang nhầm cộng số mũ với nhân số mũ và điều kiện cơ số."),
    "N02": ("nhân chia số nguyên có dấu", "chia hai số âm thì kết quả mang dấu nào", "Em biết chia giá trị tuyệt đối nhưng hay quên dau của kết quả."),
    "N05": ("quy đồng và so sánh phân số", "so sánh hai phân số âm có giống so sánh giá trị tuyệt đối không", "Quy dong xong thì em so sánh tử hay mẫu?"),
    "N08": ("đổi phân số, thập phân và phần trăm", "đổi số thập phân sang phần trăm phải thay đổi theo hệ số nào", "Em hay nhầm vị trí dấu phẩy khi đổi thap phan sang phần trăm."),
}

CATEGORY_LABELS = {
    "SIGNED-OPERATION": "Xác định dấu trong phép nhân hoặc chia số có dấu",
    "FRACTION-ORDER": "Đặt dấu so sánh sau quy đồng",
    "NEGATIVE-FRACTION-ORDER": "Thứ tự của hai phân số âm",
    "EQUIVALENT-FRACTIONS": "Nhận ra hai phân số tương đương",
    "DECIMAL-PLACE": "Vị trí dấu thập phân của thương",
    "PERCENT-SCALE": "Hệ số chuyển số thập phân sang phần trăm",
    "REDUCTION-INVARIANCE": "Chia tử và mẫu cùng hệ số khi rút gọn",
    "SUBSTITUTION-SIGN": "Giữ dấu của số được thay vào biến",
    "SQUARE-SIGN": "Bình phương một số âm",
    "FRACTION-MULTIPLICATION": "Thế phân số và nhân đúng tử, mẫu",
    "DISTRIBUTE-ALL-TERMS": "Phân phối đủ các tích hạng tử",
    "PRODUCT-SIGN": "Dấu của tích có hệ số âm",
    "COMMON-FACTOR-QUOTIENT": "Chia mọi hạng tử cho nhân tử chung",
    "FACTOR-QUOTIENT-SIGN": "Giữ dấu khi chia cho nhân tử chung",
    "SUBTRACT-PARENTHESES": "Dấu trừ tác động lên toàn bộ nhóm hạng tử",
    "PRESERVE-DOMAIN": "Giữ điều kiện gốc sau khử nhân tử",
    "NONZERO-DIVISOR": "Phân thức chia phải khác không",
    "WORD-QUANTITY-GROUP": "Tính đủ các nhóm đại lượng trong lời văn",
    "WORD-RELATION-SIGN": "Dịch đúng dấu của quan hệ hơn kém hoặc lấy bớt",
    "QUADRATIC-FORMULA-SIGN": "Dấu đối của hệ số b trong công thức nghiệm",
    "FACTOR-TWO-DENOMINATOR": "Hệ số hai trong mẫu công thức bậc hai",
    "DISCRIMINANT-CASE": "Phân loại số nghiệm thực theo biệt thức",
    "BACK-SUBSTITUTION-SIGN": "Giữ dấu khi thế ngược vào hệ",
    "ELIMINATION-SUBTRACTION": "Trừ đủ và đúng các hệ số, vế phải",
    "SCALE-WHOLE-EQUATION": "Nhân mọi hạng tử và hai vế với hệ số",
    "DOMAIN-EQUATION-SIGN": "Dấu khi giải giá trị làm mẫu bằng không",
    "INEQUALITY-DIRECTION": "Giữ hoặc đổi chiều theo dấu số chia",
    "VERTEX-ORDINATE": "Tính tung độ đỉnh bằng giá trị hàm",
    "QUADRATIC-COEFFICIENT-SIGN": "Giữ dấu hệ số bậc hai",
    "EXPONENT-PRODUCT": "Cộng số mũ khi nhân cùng cơ số",
    "EXPONENT-QUOTIENT": "Thứ tự trừ số mũ khi chia cùng cơ số",
    "POWER-OF-POWER": "Nhân số mũ của lũy thừa của lũy thừa",
}
CATEGORY_MAP = {
    "A01": ("SUBSTITUTION-SIGN", "SQUARE-SIGN", "FRACTION-MULTIPLICATION"),
    "A04": ("DISTRIBUTE-ALL-TERMS", "PRODUCT-SIGN", "DISTRIBUTE-ALL-TERMS"),
    "A07": ("COMMON-FACTOR-QUOTIENT", "COMMON-FACTOR-QUOTIENT", "FACTOR-QUOTIENT-SIGN"),
    "A10": ("SUBTRACT-PARENTHESES", "PRESERVE-DOMAIN", "NONZERO-DIVISOR"),
    "E03": ("WORD-QUANTITY-GROUP", "WORD-RELATION-SIGN", "WORD-RELATION-SIGN"),
    "E06": ("QUADRATIC-FORMULA-SIGN", "FACTOR-TWO-DENOMINATOR", "DISCRIMINANT-CASE"),
    "E09": ("BACK-SUBSTITUTION-SIGN", "ELIMINATION-SUBTRACTION", "SCALE-WHOLE-EQUATION"),
    "F02": ("DOMAIN-EQUATION-SIGN", "INEQUALITY-DIRECTION", "INEQUALITY-DIRECTION"),
    "F05": ("VERTEX-ORDINATE", "FACTOR-TWO-DENOMINATOR", "QUADRATIC-COEFFICIENT-SIGN"),
    "F08": ("EXPONENT-PRODUCT", "EXPONENT-QUOTIENT", "POWER-OF-POWER"),
    "N02": ("SIGNED-OPERATION", "SIGNED-OPERATION", "SIGNED-OPERATION"),
    "N05": ("FRACTION-ORDER", "NEGATIVE-FRACTION-ORDER", "EQUIVALENT-FRACTIONS"),
    "N08": ("DECIMAL-PLACE", "PERCENT-SCALE", "REDUCTION-INVARIANCE"),
}


def approved_inputs():
    workboard = load_workboard()
    assignment = next(row for row in workboard.assignments if row.owner == "Member 2")
    assigned = set(assignment.concept_ids)
    registry, bank, origin = load_source("member2-v2")
    require(len(assigned) == 13 and {pack.concept_id for pack in bank.packs} == assigned,
            "The active dataset must match exactly the Member 2 assignment")
    require(set(INTENTS) == set(CATEGORY_MAP) == assigned, "Missing or foreign concept specification")
    profile = load_profile()
    projection = project(registry, bank, profile, origin=origin, examples=load_example_publications("member2-v2"))
    projection.validate()
    corpus = json.loads((ROOT / BENCHMARK / "corpus.json").read_text(encoding="utf-8"))
    require(not projection.blocked and projection.snapshot_id == corpus["snapshot_id"], "Approved snapshot mismatch")
    require({doc["content_id"]: doc for doc in corpus["documents"]} == {
        chunk.content_id: chunk.model_dump(mode="json") for chunk in projection.chunks}, "Teaching corpus drift")
    return registry, bank, workboard, corpus, profile


def build_queries(registry, bank, corpus):
    concepts = {concept.concept_id: concept for concept in registry.concepts}
    queries = []
    for pack in sorted(bank.packs, key=lambda pack: pack.concept_id):
        cid = pack.concept_id
        concept = concepts[cid]
        topic, misconception, terminology = INTENTS[cid]
        # All examples are distinct from the active problem and its family.
        # Case text below comes from the public prompt, never its reference answer.
        a, b, c = (pack.problems[index] for index in (0, 2, 4))
        specs = [
            ("EXPLAIN", f"Em cần hiểu nguyên tắc {topic} và điều kiện áp dụng.", "explanation", 0, "explanation", "retrieve", a),
            ("MISCONCEPTION", f"Về {topic}, em phân vân: {misconception}?", "explanation", 0, "misconception", "retrieve", a),
            ("TERMINOLOGY", terminology, "explanation", 0, "terminology_or_typo", "retrieve", b),
            ("HINT-1", f"{a.prompt} Em nên tự hỏi câu nào trước khi bắt đầu? Chỉ gợi mở một ý.", "hint", 1, "hint", "retrieve", a),
            ("HINT-2", f"{b.prompt} Em cần chiến lược tiếp theo để tự làm, chưa cần giải ra đáp án.", "hint", 2, "hint", "retrieve", b),
            ("HINT-3", f"{c.prompt} Cho em khung các bước để tự kiểm tra, không điền kết quả của bài này.", "hint", 3, "hint", "retrieve", c),
            ("EXAMPLE-1", f"Em muốn xem một ví dụ khác về {topic}, tránh họ bài hiện tại, rồi tự đối chiếu cách làm.", "example", 3, "example", "retrieve", b),
            ("EXAMPLE-2", f"Cho em một ví dụ có giải thích từng bước về {topic}, khác bài và nguồn đang được đo.", "example", 3, "example", "retrieve", a),
            ("EXAMPLE-PARAPHRASE", f"Với {topic}, em học tốt hơn khi nhìn một bài tương tự đã làm. Đổi sang họ bài khác giúp em.", "example", 3, "paraphrase", "retrieve", c),
            ("EMPTY", f"Cho em ví dụ về {topic}, nhưng không dùng bất kỳ họ ví dụ nào trong danh sách loại trừ.", "example", 3, "no_eligible_content", "empty", a),
            ("AMBIGUOUS", f"Cái đoạn đó trong {topic} làm sao ấy, em chưa biết đang hỏi bước nào.", "explanation", 0, "ambiguous", "clarify", a),
            ("OUT-OF-SCOPE", f"Em đang ở mục {topic} nhưng muốn hướng dẫn dựng hình không gian từ ảnh chụp.", "explanation", 0, "out_of_scope", "out_of_scope", a),
        ]
        for suffix, text, purpose, level, query_class, route, active in specs:
            query = {"query_id": f"M2S5-{cid}-{suffix}", "query": text, "concept_id": cid,
                     "target_skill_id": active.primary_skill_id, "purpose": purpose, "top_k": 5,
                     "allowed_hint_level": level, "grade_levels": concept.alignment.grade_levels,
                     "difficulty": active.difficulty, "active_problem_id": active.case_id,
                     "excluded_source_groups": [active.source_group], "excluded_family_ids": [active.family_id],
                     "excluded_lineage_ids": [active.source_group, active.family_id],
                     "intent_group": f"M2S5-{cid}-" + ("EXPLANATION" if purpose == "explanation" and route == "retrieve" else suffix),
                     "split": "dev", "content_status": "ready", "snapshot_id": corpus["snapshot_id"],
                     "query_class": query_class, "expected_route": route, "review_status": "pending"}
            if route == "empty":
                examples = [doc for doc in corpus["documents"] if doc["concept_id"] == cid and doc["kind"] == "example"]
                query.update(excluded_source_groups=sorted({doc["source_group"] for doc in examples}),
                             excluded_family_ids=sorted({doc["family_id"] for doc in examples}),
                             excluded_lineage_ids=sorted({value for doc in examples for value in doc["lineage_ids"]}))
            queries.append(query)
    return queries


def build_taxonomy(bank):
    mappings = []
    for pack in sorted(bank.packs, key=lambda pack: pack.concept_id):
        require(len(pack.errors) == len(CATEGORY_MAP[pack.concept_id]), "Error fixture coverage changed")
        for error, category in zip(pack.errors, CATEGORY_MAP[pack.concept_id]):
            mappings.append({"error_id": error.error_id, "concept_id": pack.concept_id,
                "problem_id": error.problem_id, "category_id": "MC-" + category,
                "source_family_label": error.family, "hypothesis": error.hypothesis,
                "first_error_step": error.first_error_step, "fixture_sha256": digest(error.model_dump(mode="json")),
                "mapping_review_status": "proposed_pending_independent_review"})
    used = {row["category_id"] for row in mappings}
    return {"schema_version": "1.0.0", "owner": "Member 2", "status": "proposed_pending_independent_review",
            "runtime_publication": False, "categories": [{"category_id": "MC-" + key, "label": label}
                for key, label in sorted(CATEGORY_LABELS.items()) if "MC-" + key in used],
            "mappings": mappings, "fixture_count": len(mappings), "proposed_category_count": len(used)}


def pilot_packet(corpus, queries, selected):
    docs = {doc["content_id"]: doc for doc in corpus["documents"]}
    lines = ["# Pilot relevance — 13 concept Member 2", "", "26 query; đọc và chấm độc lập theo guideline. "
             "Các dấu trống dưới đây chưa phải nhãn. Tài liệu chỉ chứa teaching projection đã duyệt.", ""]
    for query in queries:
        if query["query_id"] not in selected:
            continue
        lines += [f"## {query['query_id']}", "", query["query"], "",
                  f"Purpose: {query['purpose']}; hint tối đa: {query['allowed_hint_level']}; "
                  f"bài đang học: `{query['active_problem_id']}`.", ""]
        for content_id in query["eligible_candidate_ids"]:
            doc = docs[content_id]
            lines += [f"### `{content_id}` — `{doc['content_version']}`", "", doc["text"], "",
                      "Relevance (0/1/2): ___ ; lý do: ___", ""]
    return "\n".join(lines).encode("utf-8")


def build_assets():
    registry, bank, workboard, corpus, profile = approved_inputs()
    queries = build_queries(registry, bank, corpus)
    qrels = make_workset(corpus, queries)
    assigned = sorted(pack.concept_id for pack in bank.packs)
    split_counts = audit_splits(queries, assigned)
    assets = {}
    add = lambda name, value: assets.update({f"{DATASET}/{name}": json_bytes(value)})
    add("corpus.json", corpus)
    add("queries.json", queries)
    add("qrels.unjudged.json", qrels)
    taxonomy = build_taxonomy(bank)
    add("misconception-taxonomy.json", taxonomy)
    pilot_ids = [query["query_id"] for query in queries
                 if query["query_id"].endswith(("MISCONCEPTION", "HINT-2"))]
    concepts = {concept.concept_id: concept for concept in registry.concepts}
    assignment = next(row for row in workboard.assignments if row.owner == "Member 2")
    rows = [{"concept_id": pack.concept_id, "title": concepts[pack.concept_id].title,
             "owner": assignment.owner, "reviewer": assignment.reviewer, "pack_review_status": pack.review.status,
             "content_version": pack.content_version, "pack_sha256": digest(pack.model_dump(mode="json")),
             "skills": [skill.model_dump(mode="json") for skill in concepts[pack.concept_id].skills],
             "authoring_task_kinds": concepts[pack.concept_id].authoring_task_kinds,
             "problems": len(pack.problems), "families": len({p.family_id for p in pack.problems}),
             "examples": len(pack.examples), "error_fixtures": len(pack.errors),
             "teaching_chunks": sum(doc["concept_id"] == pack.concept_id for doc in corpus["documents"]),
             "queries": 12, "content_status": "ready", "label_review_status": "pending"}
            for pack in sorted(bank.packs, key=lambda pack: pack.concept_id)]
    add("coverage.json", {"scope": "Member 2 only", "concepts": rows, "summary": {
        "owned_concepts": len(rows), "approved_packs": len(bank.packs),
        "approved_problems": sum(row["problems"] for row in rows),
        "approved_examples": sum(row["examples"] for row in rows),
        "error_fixtures": taxonomy["fixture_count"], "proposed_error_categories": taxonomy["proposed_category_count"],
        "query_count": len(queries), "concepts_awaiting_reviewed_content": 0}})
    add("integration-status.json", {"active_owner": "Member 2", "active_concept_ids": assigned,
        "blocks_current_scope": False, "waiting_for": [
            {"owner": row.owner, "concept_ids": row.concept_ids, "status": "awaiting_owner_delivery",
             "source_manifest": None} for row in workboard.assignments if row.owner != "Member 2"],
        "intake_requirements": ["versioned_registry_and_pack", "review_and_source_provenance",
                                "task_checker_and_public_projection", "family_source_lineage", "regression_evidence"]})
    for selection, selected in (("pilot", pilot_ids), ("full", [query["query_id"] for query in queries])):
        for slot in ("A", "B"):
            add(f"{selection}-review-{slot}.template.json", review_template(DATASET_ID,
                sha256(assets[f"{DATASET}/corpus.json"]), sha256(assets[f"{DATASET}/queries.json"]),
                queries, qrels, selected, slot))
    assets[f"{DATASET}/pilot-review.md"] = pilot_packet(corpus, queries, set(pilot_ids))
    lines = ["# Chặng 5 — 13 concept Member 2", "", "Nguồn hiện hành: 13 pack đã duyệt. "
             "Nhãn relevance và mapping taxonomy mới chờ review độc lập; 27 concept khác đợi chủ sở hữu bàn giao.", "",
             "| Concept | Chủ đề | Bài | Họ bài | Ví dụ | Mẫu lỗi | Chunk | Query |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    lines += [f"| {row['concept_id']} | {row['title']} | {row['problems']} | {row['families']} | "
              f"{row['examples']} | {row['error_fixtures']} | {row['teaching_chunks']} | {row['queries']} |" for row in rows]
    lines += ["", "[coverage.json](coverage.json) · [pilot-review.md](pilot-review.md) · "
              "[integration-status.json](integration-status.json)", ""]
    assets[f"{DATASET}/coverage.md"] = "\n".join(lines).encode("utf-8")
    source_names = ["content/curriculum/member2-workboard.v1.json", "content/kb/embedding-profile.v1.json",
        "content/kb/member2-v2/manifest.json", "content/kb/member2-v2/example-publications.json",
        "research/retrieval/dataset.py", "scripts/retrieval/prepare_member2_stage5.py",
        "scripts/retrieval/curate_stage5.py", f"{BENCHMARK}/manifest.json", f"{BENCHMARK}/corpus.json"]
    old_manifest = json.loads((ROOT / BENCHMARK / "manifest.json").read_text(encoding="utf-8"))
    sources = {name: sha256((ROOT / name).read_bytes()) for name in source_names}
    for name, expected in old_manifest["source_file_sha256"].items():
        require(sha256((ROOT / name).read_bytes()) == expected, "Approved source hash mismatch: " + name)
        sources[name] = expected
    add("manifest.json", {"schema_version": "1.0.0", "dataset_id": DATASET_ID,
        "status": "candidate_pending_content_and_independent_review", "scope_status": "content_ready_labels_pending",
        "owner": "Member 2", "concept_ids": assigned, "concept_count": len(assigned),
        "snapshot_id": corpus["snapshot_id"], "embedding_profile_id": profile.profile_id,
        "query_count": len(queries), "document_count": len(corpus["documents"]), "judgment_count": len(qrels),
        "human_reviewed_judgments": 0, "pilot_query_ids": pilot_ids, "split_counts": split_counts,
        "query_class_counts": dict(sorted(Counter(query["query_class"] for query in queries).items())),
        "reserved_dev_concepts": assigned, "missing_content_queries": 0, "other_members_block_current_scope": False,
        "test_policy": "All queries are dev: these concepts were already used in authoring and development. "
                       "No paraphrase split is presented as an independent final test.",
        "completion_requirements": ["independent_query_and_label_reviews", "taxonomy_mapping_review",
                                    "resolve_label_disagreements", "design_independent_final_test_then_freeze_inputs"],
        "relevance_threshold": 2, "ndcg_gain_by_grade": {"0": 0, "1": 1, "2": 3},
        "source_sha256": sources, "files_sha256": {name.removeprefix(DATASET + "/"): sha256(content)
                                                   for name, content in assets.items()}})
    return assets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Read-only reproducibility check")
    parser.add_argument("--output-root", type=Path, default=ROOT, help="New destination; never replace an existing file")
    args = parser.parse_args()
    try:
        assets = build_assets()
        if args.check:
            stale = [name for name, content in assets.items() if not (args.output_root / name).is_file()
                     or (args.output_root / name).read_bytes() != content]
            require(not stale, "Missing/stale Member 2 assets: " + ", ".join(stale))
        else:
            write_new_bundle(args.output_root, assets)
        print(json.dumps({"status": "passed", "owner": "Member 2", "concepts": 13,
                          "queries": 156, "files": len(assets), "model_api_calls": 0}))
        return 0
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
