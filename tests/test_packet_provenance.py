"""Phiếu chấm chỉ ghép câu với đúng tình huống đã sinh ra nó (build_rating_packet.verify_outputs)."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from research.evaluation import build_rating_packet as packet  # noqa: E402
from research.evaluation.build_rating_packet import load_outputs, verify_outputs  # noqa: E402
from research.evaluation.run_ablation import main as run_main  # noqa: E402

DEV_04 = ROOT / "data" / "ablation" / "dev-04"
PILOT_V2_INPUT = ROOT / "data" / "rating" / "dev-04-pilot-v2-input.jsonl"


@pytest.fixture(scope="module")
def default_run(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("run") / "r"
    assert run_main(["--llm", "fake", "--scenarios", "SC-01", "SC-04", "--configs", "full", "rule_policy",
                     "--out", str(out)]) == 0
    return out


def test_runs_on_the_default_set_record_a_fingerprint_per_scenario(default_run):
    run = json.loads((default_run / "summary.json").read_text(encoding="utf-8"))["run"]
    assert set(run["scenario_fingerprints"]) == {"SC-01", "SC-04"}
    verify_outputs(load_outputs(default_run / "outputs.jsonl"), default_run, None)


def test_a_scenario_changed_after_the_run_is_rejected(default_run, tmp_path):
    """Như SC-04 của dev-04: bài làm đổi sau lô chạy thì câu cũ không còn khớp bài làm mới."""
    copy = tmp_path / "r"
    copy.mkdir()
    (copy / "outputs.jsonl").write_bytes((default_run / "outputs.jsonl").read_bytes())
    summary = json.loads((default_run / "summary.json").read_text(encoding="utf-8"))
    summary["run"]["scenario_fingerprints"]["SC-04"] = "0" * 64  # bài làm lúc chạy khác bài làm bây giờ
    (copy / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    outputs = load_outputs(copy / "outputs.jsonl")
    with pytest.raises(ValueError, match="SC-04"):
        verify_outputs(outputs, copy, None)
    verify_outputs([o for o in outputs if o.scenario_id == "SC-01"], copy, None)  # ca không đổi vẫn dùng được


def test_a_filtered_input_must_come_from_the_source_run(default_run, tmp_path):
    outputs = load_outputs(default_run / "outputs.jsonl")
    filtered = tmp_path / "filtered.jsonl"
    filtered.write_text(outputs[0].model_dump_json() + "\n", encoding="utf-8")
    with pytest.raises(SystemExit):  # không có summary.json cạnh file đã lọc
        packet.main(["--outputs", str(filtered), "--raters", "r1", "--out", str(tmp_path / "a")])
    assert packet.main(["--outputs", str(filtered), "--source-run", str(default_run), "--raters", "r1",
                        "--out", str(tmp_path / "b")]) == 0
    edited = outputs[0].model_copy(update={"message": "Một câu không có trong lô."})
    with pytest.raises(ValueError, match="not in"):
        verify_outputs([edited], default_run, None)


def _legacy_run(tmp_path, monkeypatch, default_run, checked=None):
    run = tmp_path / "legacy"
    run.mkdir()
    (run / "outputs.jsonl").write_bytes((default_run / "outputs.jsonl").read_bytes())
    summary = json.loads((default_run / "summary.json").read_text(encoding="utf-8"))
    del summary["run"]["scenario_fingerprints"]
    (run / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    files = ["contracts/agent/fixtures.v1.json", "contracts/agent/scenarios.dev.v1.json"]
    record = {"runs": [{
        "run_id": "old", "outputs_sha256": hashlib.sha256((run / "outputs.jsonl").read_bytes()).hexdigest(),
        "scenario_files_checked": checked or {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files},
        "stale_scenarios": ["SC-04"], "reference": "ghi chép của nhóm"}]}
    path = tmp_path / "legacy-runs.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    monkeypatch.setattr(packet, "LEGACY_RUNS", path)
    return run, load_outputs(run / "outputs.jsonl")


def test_legacy_runs_need_a_record_and_always_drop_stale_scenarios(default_run, tmp_path, monkeypatch):
    run, outputs = _legacy_run(tmp_path, monkeypatch, default_run)
    with pytest.raises(ValueError, match="SC-04"):
        verify_outputs(outputs, run, None)
    verify_outputs([o for o in outputs if o.scenario_id == "SC-01"], run, None)
    monkeypatch.setattr(packet, "LEGACY_RUNS", tmp_path / "none.json")
    (tmp_path / "none.json").write_text('{"runs": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="not a recorded legacy run"):
        verify_outputs([o for o in outputs if o.scenario_id == "SC-01"], run, None)


def test_a_legacy_record_expires_when_scenario_files_change_again(default_run, tmp_path, monkeypatch):
    stale = {"contracts/agent/fixtures.v1.json": "0" * 64, "contracts/agent/scenarios.dev.v1.json": "0" * 64}
    run, outputs = _legacy_run(tmp_path, monkeypatch, default_run, checked=stale)
    with pytest.raises(ValueError, match="recheck"):
        verify_outputs([o for o in outputs if o.scenario_id == "SC-01"], run, None)


@pytest.mark.skipif(not (DEV_04 / "outputs.jsonl").exists() or not PILOT_V2_INPUT.exists(),
                    reason="needs the local dev-04 run (data/ is not in git)")
def test_dev04_pilot_v2_rebuilds_and_the_two_fixed_scenarios_stay_out():
    verify_outputs(load_outputs(PILOT_V2_INPUT), DEV_04, None)
    with pytest.raises(ValueError, match=r"\['SC-04', 'SC-15'\]"):
        verify_outputs(load_outputs(DEV_04 / "outputs.jsonl"), DEV_04, None)
