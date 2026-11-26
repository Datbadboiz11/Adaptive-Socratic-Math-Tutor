"""Lô dev lặp lại: đủ cặp, cùng phiên bản, giữ log và từ chối dữ liệu lỗi."""
import json
from pathlib import Path
import socket
import subprocess

import pytest

from research.evaluation import run_dev_repeat as runner


@pytest.fixture
def small_run(tmp_path, monkeypatch):
    scenarios = runner.load_scenarios()[:2]
    monkeypatch.setattr(runner, "load_scenarios", lambda: scenarios)
    out = tmp_path / "repeat"
    assert runner.main(["--out", str(out)]) == 0
    return out


def test_partitioned_run_preserves_repeats_and_rating_outputs(small_run):
    rows = runner.read_rows(small_run / "runs.jsonl")
    assert len(rows) == 28  # 2 tình huống × 7 cấu hình × 2 lần
    assert len({(r["scenario"], r["configuration"], r["attempt"]) for r in rows}) == 28
    assert {r["attempt"] for r in rows} == {1, 2}
    assert len(runner.read_rows(small_run / "outputs.jsonl")) == 14
    summary = json.loads((small_run / "summary.json").read_text(encoding="utf-8"))
    assert summary["run"]["repeat"] == 2 and summary["run"]["llm"] == "fake"
    configurations = summary["configurations"]
    assert list(configurations) == summary["run"]["configurations"] == list(runner.CONFIGURATIONS)
    assert all(s["action"]["unstable"] == [] for name, s in configurations.items() if name != "socratic_llm")
    assert configurations["socratic_llm"]["action"]["unstable"] is None  # không có quyết định để so
    with pytest.raises(SystemExit):
        runner.main(["--out", str(small_run)])


def test_merge_rejects_duplicate_runs_and_mixed_versions(small_run):
    manifest = json.loads((small_run / "manifest.json").read_text(encoding="utf-8"))
    part = small_run / "part-1"
    with pytest.raises(ValueError, match="Missing, duplicate"):
        runner.merge_parts(small_run, manifest, [part, part])
    info_path = part / "summary.json"
    info = json.loads(info_path.read_text(encoding="utf-8"))
    info["run"]["versions"]["verifier"] = "other"
    runner.write_json(info_path, info)
    with pytest.raises(ValueError, match="inconsistent versions"):
        runner.merge_parts(small_run, manifest, [part])


def test_failed_dns_stops_before_creating_output_or_calling_model(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "read_env", lambda: {"LLM_ENABLED": "true", "OPENAI_API_KEY": "sk-test"})

    def unavailable(*args):
        raise socket.gaierror("DNS unavailable")

    monkeypatch.setattr(runner.socket, "getaddrinfo", unavailable)
    out = tmp_path / "real"
    assert runner.main(["--llm", "openai", "--yes", "--out", str(out)]) == 2
    assert not out.exists()


def test_diagnostics_distinguish_raw_proposals_and_fixed_question_failures(small_run):
    rows = runner.read_rows(small_run / "runs.jsonl")
    row = rows[0]
    row["decision"]["proposed"]["intent"] = "probe_prerequisite"
    row["gate"] = "rejected"
    row["final_intent"] = "elicit_reasoning"
    row["attempts"] = [
        {"source": "llm", "message": "Hai câu? Thật không?", "violations": ["too_many_questions"], "accepted": False},
        {"source": "llm", "message": "Một câu?", "violations": [], "accepted": True},
    ]
    report = runner.diagnostics([row])[row["configuration"]]
    assert report["proposed_probe"] == report["rejected_probe"] == 1
    assert report["final_probe"] == 0
    assert report["first_too_many_questions"] == report["question_failures_fixed_on_retry"] == 1
    assert report["question_failures_sent_template"] == 0


def test_interrupted_run_resumes_without_repeating_finished_parts(tmp_path, monkeypatch):
    scenarios = runner.load_scenarios()[:2]
    monkeypatch.setattr(runner, "load_scenarios", lambda: scenarios)
    monkeypatch.setattr(runner, "PART_SIZE", 1)
    real_run, commands = runner.subprocess.run, []

    def interrupted_on_second_part(command, **options):
        commands.append(command)
        if len(commands) == 2:  # tiến trình bị ngắt: mới ghi dở runs.jsonl, chưa có summary.json
            part = Path(command[command.index("--out") + 1])
            part.mkdir()
            (part / "runs.jsonl").write_text("", encoding="utf-8")
            return subprocess.CompletedProcess(command, 1)
        return real_run(command, **options)

    monkeypatch.setattr(runner.subprocess, "run", interrupted_on_second_part)
    out = tmp_path / "repeat"
    assert runner.main(["--out", str(out)]) == 1
    assert not (out / "summary.json").exists()
    first_part = (out / "part-1" / "runs.jsonl").read_bytes()

    with pytest.raises(SystemExit):  # không có --resume thì không đụng vào lô đang dở
        runner.main(["--out", str(out)])
    assert runner.main(["--out", str(out), "--resume"]) == 0
    assert len(commands) == 3 and (out / "part-1" / "runs.jsonl").read_bytes() == first_part
    assert (out / "part-2" / "runs.jsonl").read_text(encoding="utf-8") == ""  # lần chạy dở được giữ lại
    rows = runner.read_rows(out / "runs.jsonl")
    assert len({(r["scenario"], r["configuration"], r["attempt"]) for r in rows}) == len(rows) == 28
    assert {r["scenario"] for r in runner.read_rows(out / "part-2-retry1" / "runs.jsonl")} == {scenarios[1].id}

    # Mã nguồn đổi sau khi lô bắt đầu thì không chạy tiếp: hai nửa sẽ không so được với nhau.
    monkeypatch.setattr(runner, "source_hashes", lambda: {"changed": "yes"})
    assert runner.main(["--out", str(out), "--resume"]) == 1
