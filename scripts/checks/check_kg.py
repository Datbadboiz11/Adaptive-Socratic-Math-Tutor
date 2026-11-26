"""Kiểm tra Knowledge Graph trong registry (PRD FR08-AC1). Không cần Neo4j.

    python scripts/checks/check_kg.py                      # báo cáo; thoát 1 nếu có lỗi
    python scripts/checks/check_kg.py --worksheet out.csv  # xuất bảng rà soát cạnh cho người duyệt
                                                           # (chạy lại vẫn giữ các cột người duyệt đã điền)

Lỗi (ID trùng/thiếu, tự trỏ, cạnh đảo chiều, chu trình) chặn việc dùng và đồng bộ đồ thị.
Cảnh báo là việc cho người duyệt; script không tự đổi trạng thái duyệt.
"""
import argparse
from collections import Counter
import csv
import io
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.kg.graph import PREREQUISITE, REGISTRY_PATH, check_registry, read_registry  # noqa: E402

# Chỉ đưa cảnh báo riêng của từng cạnh vào bảng; cảnh báo áp cho mọi cạnh đã có cột riêng.
FLAG_CODES = ("grade_order", "transitive_redundant")


REVIEW_COLUMNS = ("quyet_dinh (giu/sua/bo)", "can_cu_chuong_trinh (van ban, trang)", "nguoi_duyet",
                  "ngay_duyet", "ghi_chu")
INFO_COLUMNS = ("edge_id", "kien_thuc_nen", "lop_nen", "kien_thuc_can_nen", "lop_can_nen", "canh_bao_tu_dong",
                "can_cu_hien_tai", "trang_thai_hien_tai")


class WorksheetUnreadable(ValueError):
    """File rà soát đã có nhưng không đọc lại được: không ghi đè để khỏi mất nội dung người duyệt."""


def read_review(target: Path) -> dict[str, dict[str, str]]:
    """Nội dung người duyệt đã điền trong bảng hiện có, theo edge_id."""
    if not target.exists():
        return {}
    try:
        text = target.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise WorksheetUnreadable(f"{target} không phải UTF-8; trong Excel hãy lưu dạng 'CSV UTF-8'") from error
    if not text.strip():
        return {}
    header = text.splitlines()[0]
    delimiter = max(",;\t", key=header.count)  # Excel có thể lưu lại bằng dấu chấm phẩy
    rows = list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter))
    columns = set(rows[0]) if rows else set(next(csv.reader([header], delimiter=delimiter)))
    missing = [c for c in ("edge_id", *REVIEW_COLUMNS) if c not in columns]
    if missing:
        raise WorksheetUnreadable(f"{target} thiếu cột {', '.join(missing)}")
    kept: dict[str, dict[str, str]] = {}
    for row in rows:
        edge_id = (row.get("edge_id") or "").strip()
        if not edge_id:
            continue
        if edge_id in kept:
            raise WorksheetUnreadable(f"{target} có hai dòng cùng edge_id {edge_id}")
        kept[edge_id] = {c: (row.get(c) or "").strip() for c in REVIEW_COLUMNS}
    return kept


def write_worksheet(registry, issues, target: Path) -> dict:
    """Xuất bảng rà soát. Nếu file đã có, giữ nguyên các cột người duyệt đã điền theo edge_id; cạnh
    đã bị gỡ khỏi registry mà có nội dung duyệt thì giữ lại ở cuối bảng thay vì xóa."""
    kept = read_review(target)
    concepts = {c.concept_id: c for c in registry.concepts}
    flags = {}
    for issue in issues:
        if issue.code not in FLAG_CODES:
            continue
        for edge_id in issue.ids:
            note = issue.message.split(": ", 1)[-1] if len(issue.ids) == 1 else ""
            flags.setdefault(edge_id, []).append(f"{issue.code}: {note}" if note else issue.code)

    def label(concept_id):
        c = concepts[concept_id]
        return f"{c.concept_id} {c.title}", ", ".join(map(str, c.alignment.grade_levels))

    blank = dict.fromkeys(REVIEW_COLUMNS, "")
    rows, preserved = [], 0
    for e in sorted((e for e in registry.edges if e.relation == PREREQUISITE), key=lambda e: e.edge_id):
        (source, source_grades), (target_label, target_grades) = label(e.source_concept_id), label(e.target_concept_id)
        review = kept.pop(e.edge_id, blank)
        preserved += any(review.values())
        rows.append({
            "edge_id": e.edge_id, "kien_thuc_nen": source, "lop_nen": source_grades,
            "kien_thuc_can_nen": target_label, "lop_can_nen": target_grades,
            "canh_bao_tu_dong": " | ".join(flags.get(e.edge_id, [])), "can_cu_hien_tai": e.rationale,
            "trang_thai_hien_tai": e.review.status, **review})
    orphans = {edge_id: review for edge_id, review in kept.items() if any(review.values())}
    for edge_id, review in sorted(orphans.items()):
        rows.append({**dict.fromkeys(INFO_COLUMNS, ""), "edge_id": edge_id,
                     "trang_thai_hien_tai": "removed_from_registry", **review})
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:  # BOM để Excel đọc đúng tiếng Việt
        writer = csv.DictWriter(handle, fieldnames=[*INFO_COLUMNS, *REVIEW_COLUMNS])
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, target)  # chỉ thay file cũ khi bản mới đã ghi xong
    return {"edges": len(rows) - len(orphans), "preserved": preserved, "orphans": len(orphans)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--worksheet", type=Path, help="Xuất CSV rà soát cạnh prerequisite")
    parser.add_argument("--verbose", action="store_true", help="In từng cảnh báo")
    args = parser.parse_args()

    registry = read_registry(args.registry)
    issues = check_registry(registry)
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    prerequisite = [e for e in registry.edges if e.relation == PREREQUISITE]
    targets = {e.target_concept_id for e in prerequisite}
    sources = {e.source_concept_id for e in prerequisite}
    ids = [c.concept_id for c in registry.concepts]
    print(f"Registry {registry.content_version}: {len(ids)} concept, {len(prerequisite)} cạnh prerequisite")
    print(f"Concept gốc (không cần gì trước): {', '.join(i for i in ids if i not in targets)}")
    print(f"Concept cuối (chưa là nền của concept nào): {', '.join(i for i in ids if i not in sources)}")
    for issue in errors:
        print(f"LỖI {issue.code}: {issue.message}")
    for code, n in sorted(Counter(i.code for i in warnings).items()):
        print(f"Cảnh báo {code}: {n}")
    if args.verbose:
        for issue in warnings:
            print(f"  - {issue.code}: {issue.message}")
    if args.worksheet:
        if errors:
            print("Chưa xuất bảng rà soát: sửa lỗi trước.")
        else:
            try:
                done = write_worksheet(registry, issues, args.worksheet)
            except WorksheetUnreadable as error:
                print(f"KHÔNG GHI ĐÈ bảng rà soát: {error}")
                return 1
            print(f"Đã xuất {done['edges']} cạnh vào {args.worksheet}; giữ nội dung duyệt của "
                  f"{done['preserved']} cạnh, {done['orphans']} dòng của cạnh đã gỡ khỏi registry")
    print("FAIL" if errors else "PASS: đồ thị prerequisite là DAG, không có ID thiếu hoặc cạnh đảo chiều")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
