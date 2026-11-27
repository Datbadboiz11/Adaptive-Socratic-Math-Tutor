"""Build/check Stage 5 drafts, the 40-concept backlog and an unjudged relevance workset."""
import argparse
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
for folder in (ROOT, ROOT / "backend"):
    sys.path.insert(0, str(folder))

from app.content_authoring import digest
from app.curriculum import load_curriculum
from app.kb_projection import load_source
from app.member2_foundation import load_workboard
from app.stage5_content import build_drafts
from research.retrieval.dataset import audit_splits, json_bytes, make_workset, review_template, sha256, write_new_bundle

DRAFTS = "content/authoring/batches/stage5-expansion.v1"
DATASET = "research/retrieval/stage5/coverage40.v1"
DATASET_ID = "stage5-coverage40-candidate-1.0.0"
BENCHMARK = "research/retrieval/dev/member2-13.v1"

MISCONCEPTIONS = {
    "N01": "cộng hai số trái dấu thì chọn dấu nào", "N02": "chia hai số âm có còn âm không",
    "N03": "gặp cộng rồi nhân thì có tính từ trái sang phải luôn không",
    "N04": "hai phân số bằng nhau thì phân số nào đã tối giản", "N05": "mẫu lớn hơn có làm phân số lớn hơn không",
    "N06": "cộng phân số có cộng cả hai mẫu không", "N07": "chia phân số thì đảo phân số nào",
    "N08": "đổi số thập phân sang phần trăm phải nhân hay chia", "N09": "số mũ âm có làm giá trị luôn âm không",
    "N10": "căn bậc hai số học có nhận giá trị âm không", "A01": "thay số âm vào biến có cần đặt ngoặc không",
    "A02": "dấu trừ trước ngoặc tác động lên những hạng tử nào", "A03": "hai hạng tử khác số mũ có gộp được không",
    "A04": "nhân đa thức có cần nhân mọi cặp hạng tử không", "A05": "bình phương một tổng có thiếu tích chéo không",
    "A06": "hiệu hai bình phương khác bình phương một hiệu thế nào", "A07": "nhân tử chung phải chia hết mọi hạng tử không",
    "A08": "đổi nhóm hạng tử thì cần giữ dấu thế nào", "A09": "rút gọn xong có bỏ điều kiện mẫu ban đầu không",
    "A10": "trừ hai phân thức thì dấu trừ tác động lên cả tử thứ hai không",
    "E01": "chia hai vế cho biểu thức chứa ẩn cần điều kiện gì", "E02": "chuyển vế thì hạng tử đổi dấu thế nào",
    "E03": "chọn ẩn và đơn vị trước khi lập phương trình thế nào", "E04": "một tích bằng không thì xét từng thừa số ra sao",
    "E05": "nghiệm sau khử mẫu có cần đối chiếu điều kiện không", "E06": "biệt thức bằng không thì có mấy nghiệm thực",
    "E07": "tổng và tích nghiệm có dấu như thế nào", "E08": "thế cả biểu thức vào phương trình còn lại có cần ngoặc không",
    "E09": "muốn khử một ẩn thì hai hệ số cần quan hệ thế nào", "E10": "nhân với số âm thì có đổi chiều bất phương trình không",
    "F01": "biến đầu vào và giá trị hàm số khác nhau thế nào", "F02": "mẫu khác không và căn không âm kết hợp thế nào",
    "F03": "hệ số góc và tung độ gốc được đọc từ đâu", "F04": "dấu của hàm số thay đổi qua nghiệm thế nào",
    "F05": "hoành độ đỉnh và trục đối xứng có quan hệ gì", "F06": "hai phía của đỉnh có cùng chiều biến thiên không",
    "F07": "dấu ngoài hai nghiệm phụ thuộc hệ số bậc hai thế nào", "F08": "quy tắc cộng số mũ áp dụng khi nào",
    "F09": "logarit của tổng có bằng tổng các logarit không", "F10": "tìm nghiệm logarit xong có cần kiểm tra điều kiện không",
}


def build_assets():
    canonical, pilot = load_curriculum(revision="v2")
    release, approved, _ = load_source("member2-v2")
    snapshot, drafts, requests, checks, reviews = build_drafts(canonical, pilot)
    assets = {}
    add = lambda path, value: assets.update({path: json_bytes(value)})
    add(DRAFTS + "/registry-snapshot.json", snapshot.model_dump(mode="json"))
    add(DRAFTS + "/draft-bank.json", drafts.model_dump(mode="json"))
    for pack in drafts.packs:
        cid = pack.concept_id
        add(f"{DRAFTS}/{cid}/request.json", requests[cid])
        add(f"{DRAFTS}/{cid}/check.json", checks[cid])
        add(f"{DRAFTS}/{cid}/review-template.json", reviews[cid])
        lines = [f"# {cid} — Bản nháp Chặng 5", "", "Trạng thái: chờ review độc lập; chưa xuất bản KB.",
                 "", pack.explanation, "", "## Bài tập và bước chuẩn", ""]
        for case in [*pack.problems, *pack.examples]:
            lines += [f"- `{case.case_id}`: `{case.task.expression}` → "
                      + " → ".join(f"`{step}`" for step in case.reference_steps)
                      + f"; đáp án `{case.reference_answer}`."]
        lines += ["", "## Mẫu lỗi cần review", ""]
        for error in pack.errors:
            lines += [f"- `{error.error_id}` trên `{error.problem_id}`: "
                      + " → ".join(f"`{step}`" for step in error.response_steps)
                      + f". Bước sai đầu: {error.first_error_step}. {error.hypothesis} {error.diagnostic_question}"]
        lines += ["", "## Thang gợi ý", "", *[f"{h.level}. {h.text}" for h in pack.hints], "",
                  "Checker chỉ xác minh tính tương đương số học. Người review kiểm thêm mục tiêu đo, thứ tự thao tác, "
                  "tiếng Việt, nguồn và tiết lộ; đúng đáp án cuối chưa đủ xác minh quá trình làm bài.", ""]
        assets[f"{DRAFTS}/{cid}/review.md"] = "\n".join(lines).encode("utf-8")
    add(DRAFTS + "/manifest.json", {
        "schema_version": "1.0.0", "status": "draft_pending_independent_review", "runtime_publication": False,
        "content_version": drafts.content_version, "concept_ids": [p.concept_id for p in drafts.packs],
        "generation": {"method": "offline_original_ai_assisted", "model_api_calls": 0},
        "source_sha256": {name: sha256((ROOT / name).read_bytes()) for name in (
            "content/curriculum/registry.v2.json", "content/curriculum/pilot.v2.json", "backend/app/stage5_content.py")},
        "files_sha256": {name.removeprefix(DRAFTS + "/"): sha256(content) for name, content in assets.items()},
    })

    source_names = ["content/curriculum/registry.v2.json", "content/curriculum/pilot.v2.json",
                    "content/curriculum/member2-workboard.v1.json",
                    "content/authoring/batches/member2-original.v2/registry-snapshot.json",
                    "content/authoring/batches/member2-original.v2/approved-bank.json",
                    "content/authoring/batches/member2-original.v2/manifest.json",
                    "backend/app/stage5_content.py", "research/retrieval/dataset.py",
                    "scripts/retrieval/prepare_stage5.py",
                    *[f"{BENCHMARK}/{name}.json" for name in ("manifest", "corpus", "queries", "qrels")]]
    sources = {name: sha256((ROOT / name).read_bytes()) for name in source_names}
    sources.update({name: sha256(content) for name, content in assets.items()})
    corpus = json.loads((ROOT / BENCHMARK / "corpus.json").read_text(encoding="utf-8"))
    old_manifest = json.loads((ROOT / BENCHMARK / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in old_manifest["output_file_sha256"].items():
        if sha256((ROOT / BENCHMARK / name).read_bytes()) != expected:
            raise ValueError("Existing development corpus is stale: " + name)
    for name, expected in old_manifest["source_file_sha256"].items():
        if sha256((ROOT / name).read_bytes()) != expected:
            raise ValueError("Existing development source is stale: " + name)
        sources[name] = expected
    approved_packs = {p.concept_id: p for p in approved.packs}
    packs = {p.concept_id: p for bank in (pilot, approved, drafts) for p in bank.packs}
    # Every concept already used for authoring/development, including the two new
    # arithmetic drafts, is reserved for dev. This is a proposed concept holdout,
    # not a claim of an independently authored or frozen final test.
    dev_concepts = set(packs) | set(old_manifest["concept_ids"])
    assignments = {cid: row for row in load_workboard().assignments for cid in row.concept_ids}
    concepts = {c.concept_id: c for c in canonical.concepts}
    concepts.update({c.concept_id: c for c in release.concepts if c.concept_id in approved_packs})
    concepts.update({c.concept_id: c for c in snapshot.concepts if c.concept_id in requests})
    # Fill the next content batches in prerequisite order, with deterministic
    # ID order only for ties. Existing content remains ahead of fresh drafting.
    pending = set(concepts) - set(packs)
    incoming = {cid: {edge.source_concept_id for edge in canonical.edges
                      if edge.relation == "PREREQUISITE_OF" and edge.target_concept_id == cid}
                for cid in concepts}
    expansion_order = []
    while pending:
        ready = sorted(cid for cid in pending if not incoming[cid].intersection(pending))
        if not ready:
            raise ValueError("Expansion dependencies contain a cycle")
        expansion_order.extend(ready)
        pending.difference_update(ready)
    next_eight = set(expansion_order[:8])
    rows, queries = [], []
    for index, (cid, concept) in enumerate(sorted(concepts.items())):
        pack = packs.get(cid)
        serving = approved_packs.get(cid)
        active = pack.problems[0] if pack else None
        assignment = assignments[cid]
        blockers = []
        if pack is None:
            blockers.append("missing_pack")
        elif pack.review.status != "human_approved":
            blockers.append("pack_review_pending")
        if not concept.authoring_task_kinds:
            blockers.append("authoring_scope_undefined")
        if not serving:
            blockers.append("not_in_serving_release")
        if cid in requests:
            blockers.append("proposed_checker_binding_needs_review")
        if cid == "N04":
            blockers.append("reduced_fraction_form_not_measured_by_numeric_equivalence")
        row = {"concept_id": cid, "title": concept.title, "owner": assignment.owner,
               "reviewer": assignment.reviewer, "authoring_task_kinds": concept.authoring_task_kinds,
               "objective": concept.objective, "skills": [s.model_dump(mode="json") for s in concept.skills],
               "supported_forms": concept.supported_forms, "excluded_forms": concept.excluded_forms,
               "alignment": concept.alignment.model_dump(mode="json"),
               "has_pack": pack is not None, "pack_review_status": pack.review.status if pack else None,
               "pack_version": pack.content_version if pack else None,
               "pack_sha256": digest(pack.model_dump(mode="json")) if pack else None,
               "pack_source": (DRAFTS + "/draft-bank.json" if cid in requests else
                               "content/authoring/batches/member2-original.v2/approved-bank.json" if serving else
                               "content/curriculum/pilot.v2.json") if pack else None,
               "last_human_review_at": pack.review.reviewed_at.isoformat() if pack and pack.review.reviewed_at else None,
               "serving": serving is not None, "problems": len(pack.problems) if pack else 0,
               "families": len({p.family_id for p in pack.problems}) if pack else 0,
               "examples": len(pack.examples) if pack else 0, "errors": len(pack.errors) if pack else 0,
               "missing_approved_problems": 0 if serving else 6, "missing_approved_examples": 0 if serving else 3,
               "prerequisite_concept_ids": sorted(incoming[cid]),
               "blockers": blockers, "proposed_batch": "serving-13" if serving else
                    "complete-22" if pack else "expand-30" if cid in next_eight else "expand-40"}
        rows.append(row)
        # Balance difficulty of review/control cases over the usable 13-concept
        # pilot too, rather than letting workboard ID patterns select one level.
        variant_index = sum(r["serving"] for r in rows) - 1 if serving else index
        base = {"concept_id": cid, "target_skill_id": concept.skills[0].skill_id,
                "grade_levels": concept.alignment.grade_levels, "difficulty": active.difficulty if active else None,
                "active_problem_id": active.case_id if active else None,
                "excluded_source_groups": [active.source_group] if active else [],
                "excluded_family_ids": [active.family_id] if active else [],
                "excluded_lineage_ids": [active.source_group, active.family_id] if active else [],
                "split": "dev" if cid in dev_concepts else "test_candidate",
                "content_status": "ready" if serving else "awaiting_reviewed_content",
                "snapshot_id": corpus["snapshot_id"], "top_k": 5}
        title, misconception = concept.title.lower(), MISCONCEPTIONS[cid]
        specs = [
            ("EXPLAIN", f"Khi học {title}, em phân vân: {misconception}? Giải thích giúp em nguyên tắc áp dụng.", "explanation", 0, "misconception", "retrieve"),
            ("HINT", f"Với {title}, em bị vướng ở chỗ {misconception}. Hãy gợi ý cách tự kiểm tra bước tiếp theo.", "hint", variant_index % 3 + 1, "paraphrase", "retrieve"),
            ("EXAMPLE", f"Cho em một vi du khác về {title}, thuộc họ bài khác bài đang làm, kèm các bước để đối chiếu.", "example", 3, "typo", "retrieve"),
        ]
        control = variant_index % 3
        specs.append(("CONTROL", f"Cho em ví dụ về {title}, nhưng loại toàn bộ các họ ví dụ đang có.", "example", 3, "no_eligible_content", "empty") if control == 0 else
                     ("CONTROL", f"Đoạn đó của {title} làm sao vậy, em chưa rõ đang hỏi bước nào.", "explanation", 0, "ambiguous", "clarify") if control == 1 else
                     ("CONTROL", f"Em đang ở mục {title} nhưng muốn hướng dẫn chứng minh hình học không gian bằng hình vẽ.", "explanation", 0, "out_of_scope", "out_of_scope"))
        for suffix, text, purpose, level, query_class, route in specs:
            query = {**base, "query_id": f"S5-{cid}-{suffix}", "intent_group": f"S5-{cid}-{suffix}",
                     "query": text, "purpose": purpose, "allowed_hint_level": level,
                     "query_class": query_class, "expected_route": route, "review_status": "pending"}
            if route == "empty":
                examples = [doc for doc in corpus["documents"] if doc["concept_id"] == cid and doc["kind"] == "example"]
                query.update(excluded_source_groups=sorted({doc["source_group"] for doc in examples}),
                             excluded_family_ids=sorted({doc["family_id"] for doc in examples}),
                             excluded_lineage_ids=sorted({value for doc in examples for value in doc["lineage_ids"]}))
            queries.append(query)
    qrels = make_workset(corpus, queries)
    split_counts = audit_splits(queries, dev_concepts)
    pilot_ids = [q["query_id"] for q in queries if q["content_status"] == "ready" and q["purpose"] in ("explanation", "hint")
                 and q["expected_route"] == "retrieve"]
    add(DATASET + "/corpus.json", corpus)
    add(DATASET + "/queries.json", queries)
    add(DATASET + "/qrels.unjudged.json", qrels)
    for row in rows:
        selected = [q for q in queries if q["concept_id"] == row["concept_id"]]
        row["query_split"] = selected[0]["split"]
        row["query_ids"] = [q["query_id"] for q in selected]
        row["query_purposes"] = sorted({q["purpose"] for q in selected})
        row["query_classes"] = sorted({q["query_class"] for q in selected})
    add(DATASET + "/coverage.json", {"concepts": rows, "summary": {
        "registry_concepts": len(rows), "concepts_with_pack": sum(r["has_pack"] for r in rows),
        "approved_serving_concepts": len(approved_packs), "new_draft_concepts": len(drafts.packs),
        "problems_in_distinct_concept_packs": sum(r["problems"] for r in rows),
        "examples_in_distinct_concept_packs": sum(r["examples"] for r in rows),
        "missing_approved_problems": sum(r["missing_approved_problems"] for r in rows),
        "missing_approved_examples": sum(r["missing_approved_examples"] for r in rows)}})
    lines = ["# Ma trận Chặng 5 — 40 concept", "", "Đếm riêng pack, duyệt và release đang phục vụ. "
             "Các batch dưới đây là đề xuất theo phụ thuộc; chưa mở thêm chủ đề trong sản phẩm.", "",
             "| Concept | Chủ đề | Owner / reviewer | Bài / ví dụ | Pack | Batch đề xuất | Vướng mắc |",
             "|---|---|---|---:|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['concept_id']} | {row['title']} | {row['owner']} / {row['reviewer']} | "
                     f"{row['problems']} / {row['examples']} | {row['pack_review_status'] or 'chưa có'} | "
                     f"{row['proposed_batch']} | {', '.join(row['blockers']) or 'đang phục vụ'} |")
    lines += ["", "[coverage.json](coverage.json) giữ skill, scope, nguồn, hash/version, phụ thuộc và query từng concept.", ""]
    assets[DATASET + "/coverage.md"] = "\n".join(lines).encode("utf-8")
    for slot in ("A", "B"):
        add(f"{DATASET}/pilot-review-{slot}.template.json", review_template(
            DATASET_ID, sha256(assets[DATASET + "/corpus.json"]), sha256(assets[DATASET + "/queries.json"]),
            queries, qrels, pilot_ids, slot))
    add(DATASET + "/manifest.json", {
        "schema_version": "1.0.0", "dataset_id": DATASET_ID,
        "status": "candidate_pending_content_and_independent_review", "snapshot_id": corpus["snapshot_id"],
        "query_count": len(queries), "concept_count": len(rows), "document_count": len(corpus["documents"]),
        "judgment_count": len(qrels), "human_reviewed_judgments": 0, "pilot_query_ids": pilot_ids,
        "split_counts": split_counts, "reserved_dev_concepts": sorted(dev_concepts),
        "test_policy": "Proposed holdout by concept; all historical/current authoring concepts reserved for dev. "
                       "Test candidates lack serving content; not locked and not usable as final RQ3 evidence.",
        "missing_content_queries": sum(q["content_status"] != "ready" for q in queries),
        "relevance_threshold": 2, "ndcg_gain_by_grade": {"0": 0, "1": 1, "2": 3},
        "source_sha256": sources,
        "files_sha256": {name.removeprefix(DATASET + "/"): sha256(content)
                         for name, content in assets.items() if name.startswith(DATASET + "/")},
    })
    return assets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Read-only reproducibility check")
    parser.add_argument("--output-root", type=Path, default=ROOT, help="New destination; existing files are never replaced")
    args = parser.parse_args()
    try:
        assets = build_assets()
        if args.check:
            stale = [name for name, content in assets.items()
                     if not (args.output_root / name).is_file() or (args.output_root / name).read_bytes() != content]
            if stale:
                raise ValueError("Missing/stale generated assets: " + ", ".join(stale))
        else:
            write_new_bundle(args.output_root, assets)
        print(json.dumps({"status": "passed", "generated_files": len(assets), "model_api_calls": 0}))
        return 0
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
