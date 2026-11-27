"""Tạo bộ bài chấm ẩn cấu hình từ câu của các hệ thống (plan §18.2, §19.2; PRD §9.4).

    python research/evaluation/build_rating_packet.py --pilot --raters r1 r2 --out data/rating/pilot-01
    python research/evaluation/build_rating_packet.py --outputs data/ablation/dev.jsonl --raters r1 r2 \
        --compare full:no_kg full:rule_policy --out data/rating/dev-01

Đầu vào là các dòng ``SystemOutput`` (JSONL), hoặc ``--pilot``: câu template, câu oracle và câu lỗi
đã soạn của bộ ca sinh phản hồi dev, để thử guideline mà không gọi API. Đầu ra:

    <out>/key.json                 mã → hệ thống; KHÔNG đưa người chấm
    <out>/items.jsonl              các câu cần chấm, đã ẩn hệ thống
    <out>/raters/<id>/items.md     ngữ cảnh + câu, thứ tự ngẫu nhiên riêng cho từng người
    <out>/raters/<id>/ratings.csv  phiếu điền điểm, cùng thứ tự
    <out>/raters/<id>/pairs.md|csv chỉ khi có --compare: hai câu A/B, bên A ngẫu nhiên theo người

Mỗi người chấm chỉ nhận thư mục ``raters/<id>/`` của mình. Không ghi đè thư mục đã có. Đầu ra nên
để trong ``data/`` (đã ignore) vì chứa câu của hệ thống và điểm của người chấm.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from app.agent.decision import PedagogicalAction  # noqa: E402
from app.agent.approved_content import any_problem_prompt, reference_answers  # noqa: E402
from app.generation.templates import TemplateGenerator  # noqa: E402
from research.agent.scenarios import Scenario, load_scenarios  # noqa: E402
from research.evaluation.rubric import (  # noqa: E402
    DIMENSION_LABELS, LEVELS, RUBRIC_VERSION, SEVERE_LABELS, AssessmentSummary, Dimension, HistoryEntry,
    ItemKey, PacketKey, PairItem, PairKey, RatingContext, RatingItem, SevereFlag, SkillEvidence, SystemOutput,
    TutorTurn,
)
from research.generation.evaluate_generation import load_cases  # noqa: E402

GUIDELINE = "docs/implementation/evaluation/socratic-rubric.v1.md"
# Cột người chấm điền, và toàn bộ cột của phiếu (order và message chỉ để đối chiếu).
RATING_FIELDS = [*(d.value for d in Dimension), *(f.value for f in SevereFlag), "unratable", "note"]
PAIR_FIELDS = ["choice", "note"]
RATING_COLUMNS = ["order", "item_id", "message", *RATING_FIELDS]
PAIR_COLUMNS = ["order", "pair_id", *PAIR_FIELDS]

TRIGGERS = {"submit": "nộp bài", "request_hint": "xin gợi ý", "message": "nhắn tin", "pause": "xin tạm dừng",
            "resume": "quay lại phiên"}
STATUSES = {"verified_correct": "đúng", "verified_incorrect": "sai", "unverified": "chưa xác minh được",
            "needs_clarification": "cần viết lại cho rõ"}


# --------------------------------------------------------------------------- đầu vào

def rating_context(sc: Scenario) -> RatingContext:
    s = sc.state
    a = s.latest_assessment
    return RatingContext(
        scenario_id=sc.id,
        problem=any_problem_prompt(s.current.problem_id) or sc.context.current_problem_prompt or "",
        reference_answers=reference_answers(s.current.problem_id),
        trigger=s.trigger, student_work=list(s.latest_submission), student_message=s.latest_student_message,
        assessment=None if a is None else AssessmentSummary(
            status=a.assessment_status, first_error_step=a.first_error_step, error_family=a.error_family,
            misconception_candidate=a.misconception_candidate, diagnosis_status=a.diagnosis_status),
        hint_level=s.support.hint_level, support_turns_on_node=s.support.support_turns_on_node,
        no_progress_turns=s.support.no_progress_turns, reviewing_prerequisite=bool(s.return_stack),
        skills=[SkillEvidence(skill_id=k.skill_id, independent_observations=k.independent_observations,
                              recent_independent=list(k.recent_independent), assisted_correct=k.assisted_correct)
                for k in s.skills],
        history=[HistoryEntry(actor=t.actor, kind=t.kind, action=t.action, hint_level=t.hint_level,
                              assessment_status=t.assessment_status) for t in s.recent_turns])


def tutor_turn(o: SystemOutput) -> TutorTurn:
    return TutorTurn(message=o.message, new_problem=any_problem_prompt(o.problem_id) if o.problem_id else None,
                     new_problem_answers=reference_answers(o.problem_id) if o.problem_id else [])


def load_outputs(path: Path) -> list[SystemOutput]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()  # file lưu trên Windows có thể có BOM
    return [SystemOutput.model_validate_json(line) for line in lines if line.strip()]


def pilot_outputs() -> list[SystemOutput]:
    """Câu để thử guideline, không gọi API: template của Rule-policy, câu oracle và câu lỗi đã soạn của
    bộ ca sinh phản hồi dev. Bỏ câu lỗi cần lịch sử tin nhắn (lặp nguyên văn) vì người chấm không thấy."""
    templates = TemplateGenerator()
    out = []
    for case in load_cases():
        inp = case.input()
        d = inp.decision
        common = dict(scenario_id=case.scenario.id, action=d.action, intent=d.intent, hint_level=d.hint_level,
                      problem_id=d.problem_id)
        out.append(SystemOutput(system="template", message=templates(inp), response_source="template", **common))
        out.append(SystemOutput(system="dev_oracle", message=case.oracle["message"], **common))
        out += [SystemOutput(system=f"dev_variant:{v.id.lower()}", message=v.message, **common)
                for v in case.variants if not v.previous_messages]
    return out


def parse_compare(values: list[str]) -> list[tuple[str, str]]:
    pairs = []
    for value in values:
        reference, sep, other = value.partition(":")
        if not sep or not reference or not other or reference == other:
            raise ValueError(f"--compare expects reference:other, got {value!r}")
        pairs.append((reference, other))
    return pairs


# --------------------------------------------------------------------------- tạo bộ bài

@dataclass(frozen=True)
class Packet:
    key: PacketKey
    items: dict[str, RatingItem]
    contexts: dict[str, RatingContext]  # theo scenario_id
    turns: dict[tuple[str, str], TutorTurn]  # (scenario_id, system) → câu và bài mới câu đó giao
    item_order: dict[str, list[str]]  # rater → item_id theo thứ tự người đó chấm
    pair_order: dict[str, list[str]]


def build_packet(outputs: list[SystemOutput], raters: list[str], *, seed: int, source: str, packet_id: str,
                 compare: list[tuple[str, str]] = (), scenario_set: Path | None = None) -> Packet:
    """``scenario_set``: dev.json/test.json đã replay mà ``run_ablation.py --scenario-set`` đã chạy; None là
    bộ 16 tình huống mặc định."""
    outputs = sorted(outputs, key=lambda o: (o.scenario_id, o.system))
    scenarios = {sc.id: sc for sc in load_scenarios(sorted({o.scenario_id for o in outputs}), path=scenario_set)}
    contexts = {sid: rating_context(sc) for sid, sc in scenarios.items()}
    rng = random.Random(seed)
    used: set[str] = set()

    def new_id(prefix: str) -> str:
        while (candidate := f"{prefix}{rng.getrandbits(32):08x}") in used:
            pass
        used.add(candidate)
        return candidate

    items, keys, turns = {}, [], {}
    for o in outputs:
        sc = scenarios[o.scenario_id]
        turn = turns[(o.scenario_id, o.system)] = tutor_turn(o)
        item = RatingItem(item_id=new_id("I"), context=contexts[o.scenario_id], **turn.model_dump())
        items[item.item_id] = item
        keys.append(ItemKey(item_id=item.item_id, scenario_id=o.scenario_id, system=o.system, action=o.action,
                            intent=o.intent, hint_level=o.hint_level, response_source=o.response_source,
                            acceptable_actions=[PedagogicalAction(a) for a in sc.acceptable_actions],
                            forbidden_actions=[PedagogicalAction(a) for a in sc.forbidden_actions]))

    pairs = []
    for reference, other in compare:
        for sid in sorted(scenarios):
            if (sid, reference) in turns and (sid, other) in turns:
                pairs.append(PairKey(pair_id=new_id("P"), scenario_id=sid, systems=(reference, other),
                                     shown_as_a={r: rng.choice((reference, other)) for r in raters}))

    def shuffled(ids: list[str]) -> list[str]:
        ids = list(ids)
        rng.shuffle(ids)
        return ids

    key = PacketKey(rubric_version=RUBRIC_VERSION, packet_id=packet_id, seed=seed, source=source, raters=raters,
                    items=keys, pairs=pairs)
    return Packet(key=key, items=items, contexts=contexts, turns=turns,
                  item_order={r: shuffled(list(items)) for r in raters},
                  pair_order={r: shuffled([p.pair_id for p in pairs]) for r in raters})


def pair_item(packet: Packet, pair: PairKey, rater: str) -> PairItem:
    a = pair.shown_as_a[rater]
    b = pair.systems[1] if a == pair.systems[0] else pair.systems[0]
    return PairItem(pair_id=pair.pair_id, context=packet.contexts[pair.scenario_id],
                    a=packet.turns[(pair.scenario_id, a)], b=packet.turns[(pair.scenario_id, b)])


# --------------------------------------------------------------------------- hiển thị cho người chấm

def _recent(values: list[bool]) -> str:
    return "/".join("đúng" if v else "sai" for v in values) or "chưa có"


def render_context(ctx: RatingContext) -> list[str]:
    """Ngữ cảnh dạng danh sách Markdown, giống nhau cho mọi câu của cùng tình huống."""
    lines = [f"- **Đề bài:** {ctx.problem}",
             f"- **Đáp án (chỉ để chấm, học sinh không thấy):** {', '.join(ctx.reference_answers) or 'không có'}",
             f"- **Lượt này học sinh:** {TRIGGERS[ctx.trigger]}"]
    if ctx.student_work:
        lines += ["- **Bài làm:**", *[f"  {i}. `{line}`" for i, line in enumerate(ctx.student_work, 1)]]
    if ctx.student_message:
        lines.append(f"- **Lời nhắn của học sinh:** {ctx.student_message}")
    if ctx.assessment:
        a = ctx.assessment
        parts = [STATUSES[a.status]]
        if a.first_error_step:
            parts.append(f"bước sai đầu tiên: {a.first_error_step}")
        if a.error_family:
            parts.append(f"họ lỗi: {a.error_family}")
        if a.misconception_candidate:
            parts.append(f"giả thuyết hiểu nhầm: {a.misconception_candidate} ({a.diagnosis_status})")
        lines.append(f"- **Kết quả chấm bài làm:** {'; '.join(parts)}")
    lines.append(f"- **Hỗ trợ trên bước này:** đã lên mức gợi ý {ctx.hint_level}; {ctx.support_turns_on_node} "
                 f"lượt hỗ trợ; {ctx.no_progress_turns} lượt không tiến triển"
                 + ("; đang ôn bài nền, sau đó quay lại bài cũ" if ctx.reviewing_prerequisite else ""))
    for k in ctx.skills:
        lines.append(f"- **Bằng chứng {k.skill_id}:** {k.independent_observations} lần tự làm, gần nhất "
                     f"{_recent(k.recent_independent)}; {k.assisted_correct} lần đúng sau gợi ý")
    if ctx.history:
        steps = []
        for h in ctx.history:
            if h.actor == "tutor":
                level = f" (mức {h.hint_level})" if h.hint_level is not None else ""
                steps.append(f"gia sư {h.action.value if h.action else h.kind}{level}")
            else:
                status = f" ({STATUSES[h.assessment_status]})" if h.assessment_status else ""
                steps.append(f"học sinh {TRIGGERS.get(h.kind, h.kind)}{status}")
        lines.append(f"- **Các lượt gần đây:** {' → '.join(steps)}")
    return lines


def render_turn(label: str, turn: TutorTurn) -> list[str]:
    """Câu của gia sư; nếu câu giao bài mới thì kèm đề và đáp án bài đó ngay bên dưới."""
    out = ["", f"**{label}:**", "", *(f"> {line}" for line in turn.message.splitlines())]
    if turn.new_problem:
        answers = ", ".join(turn.new_problem_answers) or "không có"
        out += ["", f"Bài mới mà câu này giao: {turn.new_problem} **Đáp án bài mới (chỉ để chấm):** {answers}"]
    return out


def render_items(packet: Packet, rater: str) -> str:
    order = packet.item_order[rater]
    out = [f"# Bộ chấm {packet.key.packet_id}: người chấm {rater}", "",
           f"Rubric `{RUBRIC_VERSION}`. Đọc hướng dẫn trong `{GUIDELINE}` trước khi chấm. Chấm từng chiều độc "
           "lập; điền điểm vào `ratings.csv` theo đúng mã.", "", "## Các mức điểm", ""]
    for d in Dimension:
        out.append(f"- **{DIMENSION_LABELS[d]}** (`{d.value}`): " + " ".join(
            f"{level} = {text}" for level, text in sorted(LEVELS[d].items(), reverse=True)))
    out.append("- Cờ nghiêm trọng (ghi 1 nếu có): " + "; ".join(
        f"`{f.value}` = {SEVERE_LABELS[f]}" for f in SevereFlag))
    for n, item_id in enumerate(order, 1):
        item = packet.items[item_id]
        out += ["", "---", "", f"## {n}/{len(order)} · mã `{item_id}`", "", *render_context(item.context),
                *render_turn("Câu của gia sư", item)]
    return "\n".join(out) + "\n"


def render_pairs(packet: Packet, rater: str) -> str:
    pairs = {p.pair_id: p for p in packet.key.pairs}
    order = packet.pair_order[rater]
    out = [f"# So sánh từng cặp {packet.key.packet_id}: người chấm {rater}", "",
           "Với mỗi cặp, câu nào tốt hơn cho học sinh ở lượt này? Ghi `A`, `B` hoặc `tie` (ngang nhau) vào cột "
           "`choice` của `pairs.csv`. Câu lộ đáp án hoặc sai toán nghiêm trọng thì thua câu không mắc lỗi đó."]
    for n, pair_id in enumerate(order, 1):
        item = pair_item(packet, pairs[pair_id], rater)
        out += ["", "---", "", f"## Cặp {n}/{len(order)} · mã `{pair_id}`", "", *render_context(item.context),
                *render_turn("Câu A", item.a), *render_turn("Câu B", item.b)]
    return "\n".join(out) + "\n"


def _write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    # utf-8-sig để Excel mở đúng tiếng Việt.
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def write_packet(packet: Packet, out: Path) -> None:
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"{out} already has files; ratings are never overwritten")
    for rater in packet.key.raters:
        folder = out / "raters" / rater
        folder.mkdir(parents=True)
        (folder / "items.md").write_text(render_items(packet, rater), encoding="utf-8")
        _write_csv(folder / "ratings.csv", RATING_COLUMNS,
                   [{"order": n, "item_id": i, "message": packet.items[i].message}
                    for n, i in enumerate(packet.item_order[rater], 1)])
        if packet.key.pairs:
            (folder / "pairs.md").write_text(render_pairs(packet, rater), encoding="utf-8")
            _write_csv(folder / "pairs.csv", PAIR_COLUMNS,
                       [{"order": n, "pair_id": p} for n, p in enumerate(packet.pair_order[rater], 1)])
    (out / "key.json").write_text(packet.key.model_dump_json(indent=2) + "\n", encoding="utf-8")
    (out / "items.jsonl").write_text("".join(i.model_dump_json() + "\n" for i in packet.items.values()),
                                     encoding="utf-8")


# --------------------------------------------------------------------------- CLI

LEGACY_RUNS = ROOT / "contracts" / "evaluation" / "legacy-runs.v1.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_outputs(outputs: list[SystemOutput], source_run: Path, scenario_set: Path | None) -> None:
    """Câu chỉ được ghép với đúng tình huống đã sinh ra nó; sai thì ``ValueError``.

    ``source_run`` là thư mục lô của ``run_ablation.py`` / ``run_dev_repeat.py``. Mọi câu phải có nguyên
    văn trong ``outputs.jsonl`` của lô đó (đầu vào có thể là một phần đã lọc, như pilot v2). Theo thứ tự:

    - Lô ghi ``run.scenario_fingerprints``: dấu vân tay của mỗi tình huống bây giờ phải trùng lúc chạy, nếu
      không thì bài làm hay ngữ cảnh đã đổi.
    - Lô trên bộ đã replay chạy trước khi có dấu vân tay, chỉ ghi ``run.scenario_set_sha256``: file
      ``--scenario-set`` phải trùng hash đó (so cả file).
    - Lô trên bộ mặc định chưa có dấu vân tay: chỉ được nhận khi có trong ``legacy-runs.v1.json``, theo ghi
      chép của nhóm, và luôn loại các tình huống đã sửa sau lô đó."""
    summary_path, outputs_path = source_run / "summary.json", source_run / "outputs.jsonl"
    for path in (summary_path, outputs_path):
        if not path.exists():
            raise ValueError(f"{path} not found: cannot tell which scenarios produced these outputs")
    produced = {o.model_dump_json() for o in load_outputs(outputs_path)}
    if foreign := sorted({o.scenario_id for o in outputs if o.model_dump_json() not in produced}):
        raise ValueError(f"outputs for {foreign} are not in {outputs_path}")
    ids = sorted({o.scenario_id for o in outputs})
    run = json.loads(summary_path.read_text(encoding="utf-8-sig")).get("run", {})
    recorded = run.get("scenario_fingerprints")
    if recorded is not None:
        current = {sc.id: sc.fingerprint for sc in load_scenarios(ids, path=scenario_set)}
        if changed := [sid for sid in ids if recorded.get(sid) != current[sid]]:
            raise ValueError(f"{changed} differ from the scenarios this run used (state, context or prompt "
                             "changed, or another --scenario-set)")
        return
    set_hash = run.get("scenario_set_sha256")
    if set_hash is not None:
        # Lô chạy trên bộ đã replay trước khi có dấu vân tay từng ca: chỉ so được cả file.
        if scenario_set is None:
            raise ValueError(f"{source_run} ran on a scenario set (sha256 {set_hash}); pass that file as --scenario-set")
        if (actual := _sha256(scenario_set)) != set_hash:
            raise ValueError(f"{scenario_set} (sha256 {actual}) is not the scenario set that {source_run} ran on "
                             f"(sha256 {set_hash})")
        return
    if scenario_set is not None:
        raise ValueError(f"{source_run} records neither scenario fingerprints nor a scenario set, so it ran on "
                         "the default scenarios; drop --scenario-set")
    legacy = json.loads(LEGACY_RUNS.read_text(encoding="utf-8"))["runs"]
    entry = next((r for r in legacy if r["outputs_sha256"] == _sha256(outputs_path)), None)
    if entry is None:
        raise ValueError(f"{source_run} has no scenario fingerprints and is not a recorded legacy run")
    files = {name: _sha256(ROOT / name) for name in entry["scenario_files_checked"]}
    if files != entry["scenario_files_checked"]:
        raise ValueError(f"scenario files changed since legacy run {entry['run_id']} was checked; recheck "
                         f"{LEGACY_RUNS.name}")
    if stale := sorted(set(ids) & set(entry["stale_scenarios"])):
        raise ValueError(f"{stale} changed after legacy run {entry['run_id']}; leave them out ({entry['reference']})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--outputs", type=Path, help="JSONL các dòng SystemOutput")
    source.add_argument("--pilot", action="store_true", help="câu template/oracle/câu lỗi của bộ ca dev")
    parser.add_argument("--raters", nargs="+", required=True, help="mã người chấm, ví dụ r1 r2")
    parser.add_argument("--compare", nargs="*", default=[], help="cặp so sánh tham_chiếu:hệ_thống, ví dụ full:no_kg")
    parser.add_argument("--scenario-set", type=Path,
                        help="dev.json hoặc test.json đã dùng cho run_ablation.py --scenario-set")
    parser.add_argument("--source-run", type=Path,
                        help="thư mục lô đã sinh các câu, khi --outputs là bản đã lọc nằm chỗ khác "
                             "(mặc định: thư mục chứa --outputs)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, required=True, help="thư mục mới, ví dụ data/rating/pilot-01")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")

    if args.pilot and (args.scenario_set or args.source_run):
        parser.error("--pilot uses the default scenario set; drop --scenario-set and --source-run")
    outputs = pilot_outputs() if args.pilot else load_outputs(args.outputs)
    if args.outputs:
        try:
            verify_outputs(outputs, args.source_run or args.outputs.parent, args.scenario_set)
        except (ValueError, KeyError) as error:
            parser.error(str(error))
    packet = build_packet(outputs, args.raters, seed=args.seed, packet_id=args.out.name,
                          source="pilot" if args.pilot else args.outputs.as_posix(),
                          compare=parse_compare(args.compare), scenario_set=args.scenario_set)
    write_packet(packet, args.out)
    systems = sorted({k.system for k in packet.key.items})
    print(f"{len(packet.items)} câu từ {len(packet.contexts)} tình huống, {len(systems)} hệ thống, "
          f"{len(packet.key.pairs)} cặp, người chấm: {', '.join(args.raters)}")
    print(f"Đã ghi {args.out}. Mỗi người chấm chỉ nhận thư mục raters/<mã>/, không nhận key.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
