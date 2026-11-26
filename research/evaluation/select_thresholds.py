"""Công cụ chọn ngưỡng mastery trên dev và đo độ nhạy của quyết định (plan §18.2, §10). Không gọi API.

Plan §18.2: ngưỡng của Heuristic được chọn trên dev theo cùng ngân sách với BKT, không áp nguyên ngưỡng
xác suất của BKT. Đây là bước sàng lọc bằng Rule-policy; nó không chốt ngưỡng chính thức:

- Mỗi bộ ngưỡng được tính lại từ đầu như node ``readiness`` → ``decide`` của graph: chiếu state theo
  cấu hình (Full cho BKT, Heuristic cho tỷ lệ đúng gần nhất), tính lại readiness, rồi Rule-policy đề
  xuất, gate kiểm tra và fallback như ``run_decision``. Không dùng readiness đã lưu trong tình huống.
- Chỉ thử ba ngưỡng ``low`` / ``good`` / ``ready``. Điều kiện về số bằng chứng (``MIN_OBSERVATIONS_FOR_ESTIMATE``,
  ``READY_MIN_OBSERVATIONS``) giữ cố định ở đợt này.
- Heuristic: tỷ lệ đúng của 2–5 observation chỉ nhận các giá trị k/n (0, 1/5, 1/4, 1/3, 2/5, 1/2, ...).
  Ứng viên là mọi bộ low ≤ good ≤ ready lấy từ các giá trị đó; hai bộ cho cùng cách phân loại trên MỌI
  cửa sổ observation có thể có (theo đúng cách so của code: < low, >= good, >= ready và điều kiện bằng
  chứng đi kèm) chỉ giữ một bộ. Bộ khởi đầu được giữ làm đại diện của nhóm của nó.
- BKT: cùng số ứng viên với Heuristic (cùng ngân sách), lấy từ lưới 0,05–0,95 bước 0,05 theo thứ tự
  khai báo trước: gần bộ khởi đầu nhất (khoảng cách L1), rồi giá trị nhỏ hơn.
- Cùng tiêu chí chọn cho hai bên, khai báo trước ở ``SELECTION``, kể cả cách xử lý hòa điểm.

Kết quả là bằng chứng sàng lọc: Agent LLM còn nhận giá trị mastery và tự đề xuất action, nên bộ ngưỡng
chọn ra vẫn phải chạy lại qua ``run_ablation.py`` với cấu hình Agent. Bộ dev hiện có (16 tình huống mastery
soạn tay; bộ replay nhãn nháp) chưa đủ để khóa ngưỡng chính thức. Không chạy trên split test (plan §11.5).
Tài liệu: docs/implementation/evaluation/threshold-selection.v1.md.

    python research/evaluation/select_thresholds.py --out data/thresholds/dev-01
    python research/evaluation/select_thresholds.py --scenario-set data/scenarios/<bản>/dev.json --out ...
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
from itertools import combinations_with_replacement, product
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.agent.decide import RulePolicyProposer, run_decision  # noqa: E402
from app.agent.decision import (  # noqa: E402
    RECENT_INDEPENDENT_WINDOW, DecisionConfig, ExperimentConfiguration as E,
)
from app.agent.gate import GATE_VERSION  # noqa: E402
from app.agent.graph import project_state  # noqa: E402
from app.agent.mastery import MIN_OBSERVATIONS_FOR_ESTIMATE, THRESHOLDS, thresholds_override  # noqa: E402
from app.agent.rule_policy import (  # noqa: E402
    POLICY_VERSION, READINESS_VERSION, READY_MIN_OBSERVATIONS, compute_readiness,
)
from research.agent.scenarios import CONTRACTS, Scenario, load_scenarios  # noqa: E402
from research.evaluation.run_ablation import COMPARISONS, DECISION_FIELDS, project_context  # noqa: E402

TOOL_VERSION = "select-thresholds-0.3.0"
NAMES = ("low", "good", "ready")
# Loại ước lượng → cấu hình ablation dùng nó.
VIEWS = {"bkt": E.FULL, "recent_ratio": E.HEURISTIC}
START = {view: tuple(THRESHOLDS[view][n] for n in NAMES) for view in VIEWS}
BKT_GRID = tuple(round(0.05 * i, 2) for i in range(1, 20))
# Khai báo trước khi xem kết quả; giống nhau cho BKT và Heuristic. Hòa ở mọi chỉ số thì chọn bộ gần
# bộ khởi đầu nhất (L1), rồi bộ có giá trị nhỏ hơn. Số bộ hòa được báo cáo, không giấu.
SELECTION = ("fewest errors", "most final_acceptable", "most final_detail_acceptable (intent/skill labels)",
             "fewest final_forbidden", "fewest gate_rejected",
             "closest to the starting thresholds (L1)", "smallest thresholds")
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- ứng viên

def ratio_values() -> list[Fraction]:
    """Mọi giá trị tỷ lệ đúng mà policy có thể dùng: k/n với n từ số bằng chứng tối thiểu tới cửa sổ."""
    return sorted({Fraction(k, n) for n in range(MIN_OBSERVATIONS_FOR_ESTIMATE, RECENT_INDEPENDENT_WINDOW + 1)
                   for k in range(n + 1)})


def windows() -> list[tuple[bool, ...]]:
    return [w for n in range(1, RECENT_INDEPENDENT_WINDOW + 1) for w in product((False, True), repeat=n)]


def classification(values: tuple[float, float, float], window: tuple[bool, ...]) -> tuple[bool, ...]:
    """Các phép so ngưỡng mà policy làm với một cửa sổ, kèm điều kiện bằng chứng đi cùng mỗi phép so:
    ``standing`` và luật lỗi thao tác (n >= MIN_OBSERVATIONS_FOR_ESTIMATE), ``compute_readiness`` (đủ
    READY_MIN_OBSERVATIONS và hai lần gần nhất đúng). Test đối chiếu hàm này với code thật."""
    low, good, ready = values
    n = len(window)
    value = sum(window) / n  # như mastery.estimate
    out: tuple[bool, ...] = ()
    if n >= MIN_OBSERVATIONS_FOR_ESTIMATE:
        out += (value < low, value >= good)
    if n >= READY_MIN_OBSERVATIONS and window[-2:] == (True, True):
        out += (value >= ready,)
    return out


def ratio_candidates() -> list[tuple[float, float, float]]:
    """Bộ low ≤ good ≤ ready từ ``ratio_values``, mỗi cách phân loại giữ một bộ (bộ khởi đầu trước)."""
    every = windows()
    triples = [tuple(float(v) for v in t) for t in combinations_with_replacement(ratio_values(), 3)]
    seen: dict[tuple, tuple[float, float, float]] = {}
    for triple in [START["recent_ratio"], *triples]:
        seen.setdefault(tuple(classification(triple, w) for w in every), triple)
    return list(seen.values())


def distance(values: tuple[float, ...], view: str) -> float:
    return round(sum(abs(a - b) for a, b in zip(values, START[view])), 6)


def bkt_candidates(budget: int) -> list[tuple[float, float, float]]:
    """``budget`` bộ từ lưới BKT, gần bộ khởi đầu nhất trước (bộ khởi đầu nằm trên lưới)."""
    triples = list(combinations_with_replacement(BKT_GRID, 3))
    return sorted(triples, key=lambda t: (distance(t, "bkt"), t))[:budget]


def candidates() -> dict[str, list[tuple[float, float, float]]]:
    ratio = ratio_candidates()
    return {"bkt": bkt_candidates(len(ratio)), "recent_ratio": ratio}


def label(values: tuple[float, ...], view: str) -> list[str]:
    """Heuristic ghi dạng phân số (2/5), BKT ghi số thập phân."""
    if view == "recent_ratio":
        return [str(Fraction(v).limit_denominator(RECENT_INDEPENDENT_WINDOW)) for v in values]
    return [f"{v:.2f}" for v in values]


# --------------------------------------------------------------------------- đánh giá

def decide(sc: Scenario, view: str, values: tuple[float, float, float]) -> dict:
    """Một quyết định như node readiness → decide của graph, với bộ ngưỡng ``values``."""
    configuration = VIEWS[view]
    config = DecisionConfig(configuration=configuration, policy_version=POLICY_VERSION)
    with thresholds_override(view, dict(zip(NAMES, values))):
        try:
            s = project_state(sc.state, config)
            s = s.model_copy(update={"readiness": compute_readiness(s)})
            record = run_decision(s, project_context(sc.context, sc.state, configuration), RulePolicyProposer(),
                                  config, decision_id=uuid4(), created_at=NOW)
        except Exception as failure:  # noqa: BLE001 - một bộ ngưỡng lỗi không dừng cả lượt quét
            return {"scenario": sc.id, "error": f"{type(failure).__name__}: {failure}"[:300]}
    final = record.final.model_dump(mode="json")
    return {"scenario": sc.id, "error": None, **{f: final[f] for f in DECISION_FIELDS},
            "ready_to_advance": s.readiness.ready_to_advance,
            "gate": record.gate.status if record.gate else None,
            "violated_rules": record.gate.violated_rules if record.gate else [],
            "final_source": record.final_source.value,
            "final_acceptable": final["action"] in sc.acceptable_actions,
            "final_detail_acceptable": sc.detail_acceptable(final["action"], final["intent"],
                                                            final["target_skill_id"]),
            "final_forbidden": final["action"] in sc.forbidden_actions}


def metrics(decisions: list[dict]) -> dict:
    ok = [d for d in decisions if d["error"] is None]
    return {"scenarios": len(decisions), "errors": len(decisions) - len(ok),
            "final_acceptable": sum(d["final_acceptable"] for d in ok),
            # Khớp nhãn intent/skill, chỉ tính trên tình huống có nhãn chi tiết (``detail_labeled``).
            "final_detail_acceptable": sum(d["final_detail_acceptable"] is True for d in ok),
            "detail_labeled": sum(d["final_detail_acceptable"] is not None for d in ok),
            "final_forbidden": sum(d["final_forbidden"] for d in ok),
            "gate_rejected": sum(d["gate"] == "rejected" for d in ok),
            "ready_to_advance": sum(d["ready_to_advance"] for d in ok)}


def _choice(d: dict, fields: tuple[str, ...]) -> tuple | None:
    """Quyết định rút gọn về ``fields``; danh sách (content_ids, edge_ids) đổi thành tuple để so được."""
    if d["error"]:
        return None
    return tuple(tuple(d[f]) if isinstance(d[f], list) else d[f] for f in fields)


def evaluate(scenarios: list[Scenario], view: str, values_list: list[tuple[float, float, float]]) -> list[dict]:
    start = [decide(sc, view, START[view]) for sc in scenarios]
    rows = []
    for values in values_list:
        decisions = start if values == START[view] else [decide(sc, view, values) for sc in scenarios]
        changed = {level: sum(_choice(a, fields) != _choice(b, fields) for a, b in zip(decisions, start))
                   for level, fields in COMPARISONS.items()}
        row = {"view": view, "configuration": VIEWS[view].value, "thresholds": dict(zip(NAMES, values)),
               "label": dict(zip(NAMES, label(values, view))), "distance_from_start": distance(values, view),
               "is_start": values == START[view], **metrics(decisions), "changed_from_start": changed,
               "decisions": decisions}
        rows.append(row)
    return rows


def score(row: dict) -> tuple:
    return (row["errors"], -row["final_acceptable"], -row["final_detail_acceptable"], row["final_forbidden"],
            row["gate_rejected"])


def select(rows: list[dict]) -> dict:
    """Bộ được chọn theo ``SELECTION`` cùng các bộ hòa điểm với nó và độ nhạy của từng tình huống."""
    best = min(rows, key=lambda r: (score(r), r["distance_from_start"], tuple(r["thresholds"].values())))
    tied = [r for r in rows if score(r) == score(best)]
    start = next(r for r in rows if r["is_start"])
    # Hai mức so như run_ablation: "action" (action, intent) và "decision" (cả skill, mức hint, bài,
    # nội dung, cạnh KG được chọn). Đổi skill nền được kiểm tra mà giữ action vẫn là đổi quyết định.
    per_scenario: dict[str, dict] = {}
    for i, d in enumerate(start["decisions"]):
        entry: dict = {"actions": sorted({r["decisions"][i]["action"] for r in rows if not r["decisions"][i]["error"]})}
        for level, fields in COMPARISONS.items():
            choices = Counter(_choice(r["decisions"][i], fields) for r in rows)
            entry[level] = {"distinct": len(choices),
                            "candidates_changing_it": sum(_choice(r["decisions"][i], fields) != _choice(d, fields)
                                                          for r in rows)}
        if len(Counter(_choice(r["decisions"][i], ("target_skill_id",)) for r in rows)) > 1:
            entry["target_skills"] = sorted({str(r["decisions"][i].get("target_skill_id")) for r in rows})
        per_scenario[d["scenario"]] = entry
    return {
        "candidates": len(rows), "selected": _brief(best), "start": _brief(start),
        "tied_with_selected": len(tied),
        "tied_ranges": {n: [min(r["thresholds"][n] for r in tied), max(r["thresholds"][n] for r in tied)]
                        for n in NAMES},
        "distinct_decision_sets": {level: len({tuple(_choice(d, fields) for d in r["decisions"]) for r in rows})
                                   for level, fields in COMPARISONS.items()},
        "sensitive_scenarios": {level: sorted(k for k, v in per_scenario.items() if v[level]["distinct"] > 1)
                                for level in COMPARISONS},
        "per_scenario": per_scenario,
    }


def _brief(row: dict) -> dict:
    keep = ("thresholds", "label", "distance_from_start", "scenarios", "errors", "final_acceptable",
            "final_detail_acceptable", "detail_labeled", "final_forbidden", "gate_rejected", "ready_to_advance",
            "changed_from_start")
    return {k: row[k] for k in keep}


def run(scenarios: list[Scenario]) -> tuple[list[dict], dict]:
    if leaked := sorted({sc.split for sc in scenarios} - {"dev"}):
        raise ValueError(f"thresholds are chosen on dev only (plan §11.5); got split {leaked}")
    pool = candidates()
    rows = [row for view in VIEWS for row in evaluate(scenarios, view, pool[view])]
    selection = {view: select([r for r in rows if r["view"] == view]) for view in VIEWS}
    return rows, selection


# --------------------------------------------------------------------------- báo cáo

def _fmt(b: dict) -> str:
    changed = b["changed_from_start"]
    return (f"{' | '.join(b['label'].values()):<18} chấp nhận {b['final_acceptable']}/{b['scenarios']}  "
            f"khớp intent/skill {b['final_detail_acceptable']}/{b['detail_labeled']}  cấm {b['final_forbidden']}  gate từ chối {b['gate_rejected']}  lỗi {b['errors']}  "
            f"ready {b['ready_to_advance']}  đổi so với bộ đầu: action/intent {changed['action']}, "
            f"quyết định {changed['decision']}")


def print_report(selection: dict) -> None:
    print("Sàng lọc ngưỡng bằng Rule-policy trên dev (low/good/ready). Chưa phải ngưỡng chính thức.")
    for view, s in selection.items():
        sets = s["distinct_decision_sets"]
        print(f"\n{view} ({VIEWS[view].value}): {s['candidates']} bộ ngưỡng; cách quyết định khác nhau trên bộ dev: "
              f"{sets['action']} theo action/intent, {sets['decision']} theo quyết định đầy đủ")
        print(f"  bộ khởi đầu  {_fmt(s['start'])}")
        print(f"  bộ được chọn {_fmt(s['selected'])}")
        if s["tied_with_selected"] > 1:
            ranges = ", ".join(f"{n} {a:.2f}–{b:.2f}" for n, (a, b) in s["tied_ranges"].items())
            print(f"  {s['tied_with_selected']} bộ hòa điểm ({ranges}): bộ dev chưa phân biệt được các bộ này")
        for level, title in (("action", "action/intent"), ("decision", "quyết định đầy đủ")):
            names = ", ".join(s["sensitive_scenarios"][level]) or "không có"
            print(f"  tình huống đổi {title} theo ngưỡng: {names}")


def input_fingerprint(scenarios: list[Scenario], sources: list[Path]) -> dict:
    """Dấu vân tay của dữ liệu đầu vào: hash của mọi state, context và nhãn đã nạp (đúng thứ công cụ
    đánh giá), và hash từng file nguồn tạo ra chúng. Sửa fixture hay tình huống đều đổi hash."""
    loaded = [{"id": sc.id, "split": sc.split, "dataset_version": sc.dataset_version,
               "acceptable_actions": list(sc.acceptable_actions), "forbidden_actions": list(sc.forbidden_actions),
               "expected_rule_action": sc.expected_rule_action, "expected_rule_intent": sc.expected_rule_intent,
               "labels": sc.labels.model_dump(mode="json") if sc.labels else None,
               "state": sc.state.model_dump(mode="json"), "context": sc.context.model_dump(mode="json"),
               "problem_refs": {k: v.model_dump(mode="json") for k, v in sorted(sc.problem_refs.items())},
               "problem_prompts": dict(sorted(sc.problem_prompts.items()))} for sc in scenarios]
    canonical = json.dumps(loaded, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"loaded_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "source_files": {_shown(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
            "dataset_version": scenarios[0].dataset_version, "split": scenarios[0].split,
            "scenario_ids": [sc.id for sc in scenarios]}


def _shown(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario-set", type=Path,
                        help="dev.json từ research.scenarios.build; mặc định bộ 16 tình huống")
    parser.add_argument("--out", type=Path, help="thư mục mới, ví dụ data/thresholds/dev-01")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    if args.out and args.out.exists() and any(args.out.iterdir()):
        parser.error(f"{args.out} already has files; results are never overwritten")
    scenarios = load_scenarios(path=args.scenario_set) if args.scenario_set else load_scenarios()
    # Bộ mặc định ghép state từ fixtures và tình huống: hash cả hai file.
    sources = [args.scenario_set] if args.scenario_set else [CONTRACTS / "fixtures.v1.json",
                                                              CONTRACTS / "scenarios.dev.v1.json"]
    try:
        rows, selection = run(scenarios)
    except ValueError as error:
        parser.error(str(error))
    print_report(selection)
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "candidates.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        summary = {
            "tool_version": TOOL_VERSION, "status": "screening_only",
            "versions": {"policy": POLICY_VERSION, "readiness": READINESS_VERSION, "gate": GATE_VERSION},
            "inputs": input_fingerprint(scenarios, sources),
            "fixed_evidence_conditions": {"MIN_OBSERVATIONS_FOR_ESTIMATE": MIN_OBSERVATIONS_FOR_ESTIMATE,
                                          "READY_MIN_OBSERVATIONS": READY_MIN_OBSERVATIONS,
                                          "RECENT_INDEPENDENT_WINDOW": RECENT_INDEPENDENT_WINDOW},
            "start": {view: dict(zip(NAMES, START[view])) for view in VIEWS},
            "selection_rule": list(SELECTION), "selection": selection,
        }
        (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
        print(f"\nĐã ghi {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
