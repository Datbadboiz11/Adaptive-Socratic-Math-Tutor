"""Thống kê nhãn chiến lược của Bridge và MathDial để thiết kế bộ action của Agent.

Dữ liệu tải vào data/external/ (xem data/external/README.md). Script chỉ đọc file JSON,
không chạy code từ dữ liệu ngoài.

    python research/agent/external_moves.py --data-dir data/external
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]

BRIDGE_ERRORS = ["guess", "right-idea", "diagnose", "careless", "imprecise", "misinterpret"]
BRIDGE_STRATEGIES = [
    "ask_question", "explain_concept", "provide_hint", "provide_strategy", "provide_correction",
    "provide_similar_problem", "simplify_question", "affirm_correct_answer", "encourage_student",
    "provide_example",
]
MATHDIAL_MOVES = ["focus", "probing", "telling", "generic"]
TEACHER_MOVE = re.compile(r"^\s*Teacher:\s*\((\w+)\)")


def bridge_stats(folder):
    rows = []
    for split in ("train", "validation", "test"):
        rows += json.loads((folder / f"{split}.json").read_text(encoding="utf-8"))
    strategy = Counter(r["z_what"] if r["z_what"] in BRIDGE_STRATEGIES else "other" for r in rows)
    error = Counter(r["e"] if r["e"] in BRIDGE_ERRORS else "other" for r in rows)
    cross = defaultdict(Counter)
    for r in rows:
        if r["e"] in BRIDGE_ERRORS:
            cross[r["e"]][r["z_what"] if r["z_what"] in BRIDGE_STRATEGIES else "other"] += 1
    return {"rows": len(rows), "strategy": dict(strategy.most_common()),
            "error": dict(error.most_common()),
            "error_x_strategy": {e: dict(cross[e].most_common(4)) for e in BRIDGE_ERRORS}}


def mathdial_stats(folder):
    rows = [json.loads(line) for split in ("train", "test")
            for line in (folder / f"{split}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    moves, first = Counter(), Counter()
    for r in rows:
        found = [m for turn in r["conversation"].split("|EOM|") for m in TEACHER_MOVE.findall(turn)]
        moves.update(m for m in found if m in MATHDIAL_MOVES)
        if found:
            first[found[0]] += 1
    total = sum(moves.values())
    return {"conversations": len(rows), "teacher_moves": dict(moves.most_common()),
            "move_share": {m: round(moves[m] / total, 3) for m in MATHDIAL_MOVES},
            "first_move": dict(first.most_common()),
            "self_correctness": dict(Counter(str(r["self-correctness"]) for r in rows).most_common())}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/external")
    args = parser.parse_args()
    summary = {"bridge": bridge_stats(args.data_dir / "bridge"),
               "mathdial": mathdial_stats(args.data_dir / "mathdial")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
