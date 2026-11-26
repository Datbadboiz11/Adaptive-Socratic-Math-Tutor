"""Đọc phiếu chấm, tính độ đồng thuận và tổng hợp điểm theo hệ thống (plan §19.1–§19.3; PRD §9.4).

    python research/evaluation/score_ratings.py --packet data/rating/pilot-01

Đọc ``key.json``, ``raters/<id>/ratings.csv`` (và ``pairs.csv`` nếu có) của bộ bài do
``build_rating_packet.py`` tạo, cùng ``reconciled/ratings.csv`` / ``reconciled/pairs.csv`` nếu đã hòa giải.

1. Độ đồng thuận trên điểm **trước hòa giải**: weighted kappa cho từng chiều, Cohen's kappa cho từng
   cờ nghiêm trọng, cho "không chấm được" và cho lựa chọn ghép cặp.
2. Điểm cuối của mỗi câu: bản hòa giải nếu có; nếu không, điểm mà mọi người chấm trùng nhau; một người
   chấm thì lấy điểm đó (đánh dấu ``single``); còn lại là ``unresolved`` và được ghi vào
   ``reconciled/ratings.todo.csv`` để hòa giải.
3. Tổng hợp theo hệ thống: từng chiều (không chỉ tổng), tỷ lệ thất bại do cờ nghiêm trọng, khoảng tin
   cậy bootstrap theo tình huống, tỷ lệ action thuộc tập chấp nhận/bị cấm, thắng/hòa/thua ghép cặp.

Dữ liệu lỗi (ô sai định dạng, mã không có trong key, điểm mâu thuẫn với cờ) làm script dừng, không bỏ qua.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass, field
import io
from itertools import combinations
import json
from pathlib import Path
import sys

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from research.evaluation.agreement import Weights, bootstrap_mean_ci, cohen_kappa, weighted_kappa  # noqa: E402
from research.evaluation.build_rating_packet import (  # noqa: E402
    PAIR_COLUMNS, PAIR_FIELDS, RATING_COLUMNS, RATING_FIELDS,
)
from research.evaluation.rubric import (  # noqa: E402
    DIMENSION_LABELS, RECONCILED_RATER, RUBRIC_VERSION, Dimension, PacketKey, PairJudgment, PairKey, Rating,
    SevereFlag,
)

SCORES = (0, 1, 2)
TRUE_CELLS, FALSE_CELLS = {"1", "x"}, {"", "0"}
NOT_APPLICABLE = "na"
DELIMITERS = (",", ";", "\t")


class RatingFileError(ValueError):
    pass


# --------------------------------------------------------------------------- đọc phiếu

def _rows(path: Path, required: list[str]) -> list[dict[str, str]]:
    """Kiểm tra dòng tiêu đề trước khi đọc điểm. File lưu lại bằng dấu phân cách khác (Excel dùng ``;``
    hoặc tab tùy máy) vẫn đọc được; file thiếu cột hay sai mã hóa là lỗi, không phải phiếu chưa chấm.
    Cột ngoài ``required`` (order, message, independent) được giữ nguyên và không bắt buộc."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise RatingFileError(f"{path.as_posix()}: not UTF-8, save it as 'CSV UTF-8' ({error})") from error
    for delimiter in DELIMITERS:
        reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)
        if set(required) <= {(name or "").strip() for name in reader.fieldnames or []}:
            return [{k.strip(): (v or "").strip() for k, v in row.items() if k is not None} for row in reader]
    raise RatingFileError(f"{path.as_posix()}: the header needs the columns {required} separated by a comma, "
                          f"semicolon or tab; got {text.splitlines()[0] if text.strip() else ''!r}")


def _flag(cell: str) -> bool:
    if cell.lower() in TRUE_CELLS:
        return True
    if cell in FALSE_CELLS:
        return False
    raise ValueError(f"expected 1/x or empty, got {cell!r}")


def _score(cell: str) -> int | None:
    if cell.lower() == NOT_APPLICABLE:
        return None
    if cell in {str(s) for s in SCORES}:
        return int(cell)
    raise ValueError(f"expected 0, 1, 2 or na, got {cell!r}")


def parse_ratings(path: Path, rater_id: str, stage: str) -> list[Rating]:
    """Dòng chưa điền gì được bỏ qua (chưa chấm); dòng điền dở là lỗi."""
    out, errors = [], []
    for n, row in enumerate(_rows(path, ["item_id", *RATING_FIELDS]), 2):
        if not any(row[c] for c in RATING_FIELDS):
            continue
        try:
            unratable = _flag(row["unratable"])
            given = {d: row[d.value] for d in Dimension}
            if unratable and any(given.values()):
                raise ValueError("an unratable row leaves the scores empty")
            if not unratable and not all(given.values()):
                raise ValueError(f"missing scores: {[d.value for d, v in given.items() if not v]}")
            out.append(Rating(
                item_id=row["item_id"], rater_id=rater_id, stage=stage, unratable=unratable,
                scores={} if unratable else {d: _score(v) for d, v in given.items()},
                severe=[f for f in SevereFlag if _flag(row[f.value])], note=row["note"] or None))
        except (ValueError, ValidationError) as error:
            errors.append(f"{path.as_posix()} line {n} ({row['item_id'] or '?'}): {error}")
    if errors:
        raise RatingFileError("\n".join(errors))
    return out


def parse_pairs(path: Path, rater_id: str, stage: str) -> list[PairJudgment]:
    out, errors = [], []
    for n, row in enumerate(_rows(path, ["pair_id", *PAIR_FIELDS]), 2):
        if not any(row[c] for c in PAIR_FIELDS):
            continue
        choice = row["choice"]
        try:
            out.append(PairJudgment(pair_id=row["pair_id"], rater_id=rater_id, stage=stage,
                                    choice=choice.upper() if choice.lower() in {"a", "b"} else choice.lower(),
                                    note=row["note"] or None))
        except ValidationError as error:
            errors.append(f"{path.as_posix()} line {n} ({row['pair_id'] or '?'}): {error}")
    if errors:
        raise RatingFileError("\n".join(errors))
    return out


@dataclass
class Collected:
    independent: dict[str, dict[str, Rating]] = field(default_factory=dict)  # item_id → rater → rating
    reconciled: dict[str, Rating] = field(default_factory=dict)
    pair_independent: dict[str, dict[str, PairJudgment]] = field(default_factory=dict)
    pair_reconciled: dict[str, PairJudgment] = field(default_factory=dict)


def _index(records, known: set[str], what: str, attr: str) -> dict:
    out = {}
    for r in records:
        rid = getattr(r, attr)
        if rid not in known:
            raise RatingFileError(f"{r.rater_id}: {what} {rid} is not in key.json")
        if rid in out:
            raise RatingFileError(f"{r.rater_id}: {what} {rid} appears twice")
        out[rid] = r
    return out


def collect(packet: Path, key: PacketKey) -> Collected:
    items, pairs = {i.item_id for i in key.items}, {p.pair_id for p in key.pairs}
    c = Collected()
    sources = [(packet / "raters" / r, r, "independent") for r in key.raters]
    sources.append((packet / "reconciled", RECONCILED_RATER, "reconciled"))
    for folder, rater, stage in sources:
        ratings_file, pairs_file = folder / "ratings.csv", folder / "pairs.csv"
        if ratings_file.exists():
            for item_id, r in _index(parse_ratings(ratings_file, rater, stage), items, "item", "item_id").items():
                if stage == "reconciled":
                    c.reconciled[item_id] = r
                else:
                    c.independent.setdefault(item_id, {})[rater] = r
        if pairs_file.exists():
            for pair_id, j in _index(parse_pairs(pairs_file, rater, stage), pairs, "pair", "pair_id").items():
                if stage == "reconciled":
                    c.pair_reconciled[pair_id] = j
                else:
                    c.pair_independent.setdefault(pair_id, {})[rater] = j
    return c


# --------------------------------------------------------------------------- đồng thuận

def _viewer(key: PacketKey, rater_id: str) -> str:
    """Bản hòa giải ghi A/B theo đúng thứ tự mà người chấm đầu tiên trong key đã thấy."""
    return key.raters[0] if rater_id == RECONCILED_RATER else rater_id


def canonical_choice(pair: PairKey, choice: str, viewer: str) -> str:
    """Lựa chọn theo hệ thống thay vì vị trí A/B mà ``viewer`` thấy: reference / other / tie."""
    if choice == "tie":
        return "tie"
    a = pair.shown_as_a[viewer]
    chosen = a if choice == "A" else next(s for s in pair.systems if s != a)
    return "reference" if chosen == pair.systems[0] else "other"


def shown_choice(pair: PairKey, canonical: str, viewer: str) -> str:
    """Ngược lại ``canonical_choice``: lựa chọn đó là A hay B trong bản ``viewer`` thấy."""
    if canonical == "tie":
        return "tie"
    chosen = pair.systems[0] if canonical == "reference" else pair.systems[1]
    return "A" if chosen == pair.shown_as_a[viewer] else "B"


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


def agreement(key: PacketKey, c: Collected, weights: Weights = "quadratic") -> dict:
    out = {}
    pairs = {p.pair_id: p for p in key.pairs}
    for r1, r2 in combinations(key.raters, 2):
        both = [(v[r1], v[r2]) for v in c.independent.values() if r1 in v and r2 in v]
        ratable = [(a, b) for a, b in both if not a.unratable and not b.unratable]
        report = {"items_rated_by_both": len(both), "dimensions": {}, "severe": {}}
        for d in Dimension:
            scored = [(a.scores[d], b.scores[d]) for a, b in ratable if a.scores[d] is not None
                      and b.scores[d] is not None]
            x, y = [a for a, _ in scored], [b for _, b in scored]
            report["dimensions"][d.value] = {
                "n": len(scored), "exact": _rounded(sum(a == b for a, b in scored) / len(scored)) if scored else None,
                "weighted_kappa": _rounded(weighted_kappa(x, y, SCORES, weights)),
                # Câu một người ghi na, người kia cho điểm: không vào kappa nên phải báo riêng.
                "na_mismatch": sum((a.scores[d] is None) != (b.scores[d] is None) for a, b in ratable)}
        for f in SevereFlag:
            x, y = [f in a.severe for a, _ in ratable], [f in b.severe for _, b in ratable]
            report["severe"][f.value] = {"n": len(ratable), "positives": [sum(x), sum(y)],
                                         "kappa": _rounded(cohen_kappa(x, y, (False, True)))}
        report["unratable"] = {"n": len(both), "kappa": _rounded(cohen_kappa(
            [a.unratable for a, _ in both], [b.unratable for _, b in both], (False, True)))}
        judged = [(pairs[pid], v[r1], v[r2]) for pid, v in c.pair_independent.items() if r1 in v and r2 in v]
        x = [canonical_choice(p, a.choice, r1) for p, a, _ in judged]
        y = [canonical_choice(p, b.choice, r2) for p, _, b in judged]
        report["pairs"] = {"n": len(judged), "kappa": _rounded(cohen_kappa(x, y, ("reference", "other", "tie")))}
        out[f"{r1}~{r2}"] = report
    return {"weights": weights, "raters": out}


# --------------------------------------------------------------------------- điểm cuối

def _same(a: Rating, b: Rating) -> bool:
    return (a.unratable, a.scores, sorted(a.severe)) == (b.unratable, b.scores, sorted(b.severe))


def resolve(key: PacketKey, c: Collected) -> dict[str, tuple[Rating | None, str]]:
    """item_id → (điểm cuối, cách có): reconciled | agreed | single | unresolved | unrated."""
    out = {}
    for item in key.items:
        given = list(c.independent.get(item.item_id, {}).values())
        if item.item_id in c.reconciled:
            out[item.item_id] = (c.reconciled[item.item_id], "reconciled")
        elif not given:
            out[item.item_id] = (None, "unrated")
        elif len(given) == 1:
            out[item.item_id] = (given[0], "single")
        elif all(_same(given[0], r) for r in given[1:]):
            out[item.item_id] = (given[0], "agreed")
        else:
            out[item.item_id] = (None, "unresolved")
    return out


def resolve_pairs(key: PacketKey, c: Collected) -> dict[str, tuple[str | None, str]]:
    out = {}
    for pair in key.pairs:
        given = [canonical_choice(pair, j.choice, r) for r, j in c.pair_independent.get(pair.pair_id, {}).items()]
        if pair.pair_id in c.pair_reconciled:
            choice = c.pair_reconciled[pair.pair_id].choice
            out[pair.pair_id] = (canonical_choice(pair, choice, _viewer(key, RECONCILED_RATER)), "reconciled")
        elif not given:
            out[pair.pair_id] = (None, "unrated")
        elif len(set(given)) == 1:
            out[pair.pair_id] = (given[0], "single" if len(given) == 1 else "agreed")
        else:
            out[pair.pair_id] = (None, "unresolved")
    return out


# --------------------------------------------------------------------------- tổng hợp

def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _ci(groups: dict[str, list[float]], seed: int) -> list[float] | None:
    ci = bootstrap_mean_ci(groups, seed=seed)
    return None if ci is None else [round(ci[0], 3), round(ci[1], 3)]


def summarize(key: PacketKey, final: dict[str, tuple[Rating | None, str]],
              pair_final: dict[str, tuple[str | None, str]]) -> dict:
    systems = {}
    by_system = defaultdict(list)
    for item in key.items:
        by_system[item.system].append(item)
    for system, items in sorted(by_system.items()):
        status = Counter(final[i.item_id][1] for i in items)
        rated = [(i, final[i.item_id][0]) for i in items if final[i.item_id][0] is not None]
        ratable = [(i, r) for i, r in rated if not r.unratable]
        dims = {}
        for d in Dimension:
            groups = defaultdict(list)
            for i, r in ratable:
                if r.scores[d] is not None:
                    groups[i.scenario_id].append(r.scores[d])
            values = [v for vs in groups.values() for v in vs]
            dims[d.value] = {"mean": _mean(values), "ci95": _ci(groups, key.seed), "n": len(values),
                             "not_applicable": sum(r.scores[d] is None for _, r in ratable),
                             "distribution": {str(s): values.count(s) for s in SCORES}}
        fail_groups = defaultdict(list)
        for i, r in ratable:
            fail_groups[i.scenario_id].append(float(r.fails))
        with_action = [i for i in items if i.action is not None]
        systems[system] = {
            "items": len(items), "resolution": dict(sorted(status.items())),
            "unratable": sum(r.unratable for _, r in rated), "dimensions": dims,
            "failure": {"rate": _mean([v for vs in fail_groups.values() for v in vs]),
                        "ci95": _ci(fail_groups, key.seed), "n": len(ratable),
                        **{f.value: sum(f in r.severe for _, r in ratable) for f in SevereFlag}},
            "actions": {"n": len(with_action),
                        "acceptable_rate": _mean([float(i.action in i.acceptable_actions) for i in with_action]),
                        "forbidden_rate": _mean([float(i.action in i.forbidden_actions) for i in with_action])},
        }
    comparisons = {}
    for pair in key.pairs:
        name = f"{pair.systems[0]} vs {pair.systems[1]}"
        tally = comparisons.setdefault(name, Counter())
        choice, how = pair_final[pair.pair_id]
        tally[choice if choice is not None else how] += 1
    return {"systems": systems,
            "pairs": {name: {k: t.get(k, 0) for k in ("reference", "other", "tie", "unresolved", "unrated")}
                      for name, t in comparisons.items()}}


# --------------------------------------------------------------------------- hòa giải

def _cells(r: Rating) -> str:
    if r.unratable:
        return "unratable"
    scores = ",".join(NOT_APPLICABLE if r.scores[d] is None else str(r.scores[d]) for d in Dimension)
    return scores + ("".join(f" +{f.value}" for f in r.severe))


def write_reconcile_todo(packet: Path, key: PacketKey, c: Collected, final, pair_final) -> list[Path]:
    """Phiếu cho buổi hòa giải: các câu/cặp người chấm khác nhau, kèm điểm từng người. Trả về các phiếu
    còn việc phải làm."""
    ratings = [
        {"order": n, "item_id": item.item_id, "independent": " | ".join(
            f"{r}: {_cells(v)}" for r, v in sorted(c.independent[item.item_id].items()))}
        for n, item in enumerate((i for i in key.items if final[i.item_id][1] == "unresolved"), 1)]
    # A/B theo bản của người chấm đầu tiên: buổi hòa giải đọc pairs.md của người đó.
    viewer = _viewer(key, RECONCILED_RATER)
    pairs = [
        {"order": n, "pair_id": pair.pair_id, "independent": " | ".join(
            f"{r}: {shown_choice(pair, canonical_choice(pair, j.choice, r), viewer)}"
            for r, j in sorted(c.pair_independent[pair.pair_id].items()))}
        for n, pair in enumerate((p for p in key.pairs if pair_final[p.pair_id][1] == "unresolved"), 1)]
    folder = packet / "reconciled"
    sheets = [(folder / "ratings.todo.csv", RATING_COLUMNS, ratings), (folder / "pairs.todo.csv", PAIR_COLUMNS, pairs)]
    return [path for path, columns, rows in sheets if _write_todo(path, columns, rows)]


def _write_todo(path: Path, columns: list[str], rows: list[dict]) -> bool:
    """Ghi phiếu hòa giải, trả về còn việc hay không. Phiếu của lần chạy trước cũng được ghi lại (chỉ còn
    dòng tiêu đề khi đã hòa giải hết), để không liệt kê câu đã xong."""
    if rows or path.exists():
        path.parent.mkdir(exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[*columns, "independent"])
            writer.writeheader()
            writer.writerows(rows)
    return bool(rows)


# --------------------------------------------------------------------------- CLI

def score(packet: Path, weights: Weights = "quadratic") -> tuple[dict, list[Path]]:
    key = PacketKey.model_validate_json((packet / "key.json").read_text(encoding="utf-8"))
    if key.rubric_version != RUBRIC_VERSION:
        # Mức điểm và luật cờ có thể đã đổi: không kiểm tra phiếu của bản này bằng luật của bản khác.
        raise RatingFileError(f"{packet.as_posix()} was built for {key.rubric_version}, this code is "
                              f"{RUBRIC_VERSION}; score it with the matching version of the code")
    c = collect(packet, key)
    final, pair_final = resolve(key, c), resolve_pairs(key, c)
    report = {"packet_id": key.packet_id, "rubric_version": key.rubric_version, "source": key.source,
              "agreement": agreement(key, c, weights), **summarize(key, final, pair_final)}
    return report, write_reconcile_todo(packet, key, c, final, pair_final)


def print_report(report: dict) -> None:
    print("Trung bình từng chiều: " + ", ".join(f"{d.value} = {DIMENSION_LABELS[d]}" for d in Dimension))
    labels = " ".join(f"{d.value:>12}" for d in Dimension)
    print(f"{'system':24} {'n':>3} {labels} {'fail':>6} {'accept':>6}")
    for system, s in report["systems"].items():
        means = " ".join(f"{'-' if v['mean'] is None else v['mean']:>12}" for v in s["dimensions"].values())
        fail, accept = s["failure"]["rate"], s["actions"]["acceptable_rate"]
        print(f"{system[:24]:24} {s['failure']['n']:>3} {means} {'-' if fail is None else fail:>6} "
              f"{'-' if accept is None else accept:>6}")
    for name, a in report["agreement"]["raters"].items():
        kappas = ", ".join(f"{d}={v['weighted_kappa']}" for d, v in a["dimensions"].items())
        print(f"\n[{name}] {a['items_rated_by_both']} câu chấm chung; weighted kappa "
              f"({report['agreement']['weights']}): {kappas}")
    for name, t in report["pairs"].items():
        print(f"[cặp] {name}: {t}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--packet", type=Path, required=True, help="thư mục do build_rating_packet.py tạo")
    parser.add_argument("--weights", choices=["quadratic", "linear"], default="quadratic")
    parser.add_argument("--out", type=Path, help="file JSON kết quả, mặc định <packet>/report.json")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        report, todo = score(args.packet, args.weights)
    except RatingFileError as error:
        print(f"Phiếu chấm có lỗi, chưa tính điểm:\n{error}", file=sys.stderr)
        return 2
    out = args.out or args.packet / "report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print_report(report)
    print(f"\nĐã ghi {out}")
    for path in todo:
        print(f"Cần hòa giải: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
