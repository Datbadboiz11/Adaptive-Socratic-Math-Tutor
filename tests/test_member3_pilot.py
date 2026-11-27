"""Nháp nội dung tự soạn của Member 3 (content/authoring/member3-original-pilot.v1.json)."""
import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts/authoring"))
from app.authoring_runs import load_authoring_source  # noqa: E402
from app.member2_foundation import load_workboard  # noqa: E402
from prepare_member3_pilot import SOURCE, rendered_pilot  # noqa: E402

SPEC = json.loads(SOURCE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rendered():
    return rendered_pilot()


def write(tmp_path, spec):
    path = tmp_path / "member3.json"
    path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return path


def test_every_member3_concept_is_authored_or_waiting_for_a_checker(rendered):
    _, summary = rendered
    assigned = next(a.concept_ids for a in load_workboard().assignments if a.owner == "Member 3")
    assert set(summary["packs"]) | set(summary["pending_checker"]) == set(assigned)
    assert not set(summary["packs"]) & set(summary["pending_checker"])
    assert len(summary["packs"]) == 14 and not summary["pending_checker"]  # cả 14 concept đã có nháp
    assert summary["model_api_calls_for_this_batch"] == 0 and not summary["runtime_publication"]


def test_each_pack_meets_the_plan_minimum_and_stays_a_draft(rendered):
    _, summary = rendered
    for report in summary["packs"].values():
        assert (report["problems"], report["examples"], report["error_fixtures"], report["hint_levels"]) == (6, 3, 3, 3)
        assert report["review"] == "draft"


def test_review_material_has_a_worked_solution_for_every_example(rendered):
    artifacts, summary = rendered
    for concept_id in summary["packs"]:
        material = artifacts[f"{concept_id}/review.md"]
        assert material.count("**Ví dụ**") == 3
        for family in SPEC["packs"][concept_id]["families"]:
            assert family["worked"] in material


def test_a_wrong_reference_answer_is_rejected(tmp_path):
    spec = copy.deepcopy(SPEC)
    spec["packs"]["N06"]["families"][0]["problems"][0][1] = "12/30"
    with pytest.raises(ValueError, match="N06 authoring checks failed"):
        rendered_pilot(write(tmp_path, spec))


def test_a_wrong_error_label_is_rejected(tmp_path):
    """Mẫu lỗi phải thật sự sai ở bước 1: lấy đáp án đúng làm ``wrong`` thì checker phải bắt."""
    spec = copy.deepcopy(SPEC)
    spec["packs"]["A05"]["families"][0]["wrong"] = "x*x+12*x+36"
    with pytest.raises(ValueError, match="A05 authoring checks failed"):
        rendered_pilot(write(tmp_path, spec))


def test_a_task_already_in_member2_bank_is_rejected(tmp_path):
    _, member2 = load_authoring_source("member2-v2")
    taken = next(c for pack in member2.packs for c in pack.problems if c.task.kind == "numeric")
    spec = copy.deepcopy(SPEC)
    spec["packs"]["N03"]["families"][0]["problems"][0][:2] = [taken.task.expression, taken.reference_answer]
    with pytest.raises(ValueError, match="Exact task duplicate"):
        rendered_pilot(write(tmp_path, spec))


def test_a_concept_cannot_be_both_authored_and_pending(tmp_path):
    spec = copy.deepcopy(SPEC)
    spec["pending_checker"]["N03"] = "x"
    with pytest.raises(ValueError, match="pending"):
        rendered_pilot(write(tmp_path, spec))
