"""Regression coverage for the approved release, publication versions and admin CLI."""
import json
from pathlib import Path
import shutil
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "backend", ROOT / "tests", ROOT / "scripts/kb"):
    sys.path.insert(0,str(path))

from app import kb_cli, kb_projection
from app.kb_projection import load_example_publications,load_profile,load_source,project
from build_member2_stage3_assets import build_examples
from kb_support import approved_source,fake_profile


def test_default_cli_selects_complete_approved_source_without_loading_model(monkeypatch,capsys):
    def plan(projection):
        assert len(projection.chunks)==91 and not projection.blocked
        assert projection.registry.content_version=="0.4.0-member2-review"
        assert len({chunk.concept_id for chunk in projection.chunks})==13
        return projection,{"snapshot_id":projection.snapshot_id,"chunks":91}
    def no_model(*args,**kwargs):
        raise AssertionError("Dry-run instantiated an embedding model")
    monkeypatch.setattr(kb_cli,"plan_sync",plan)
    monkeypatch.setattr(kb_cli,"LocalEmbedder",no_model)
    monkeypatch.setattr(sys,"argv",["sync_kb","sync","--dry-run"])
    kb_cli.main()
    result = json.loads(capsys.readouterr().out)
    assert result["chunks"]==91 and result["embedding_calls"]==result["database_writes"]==0
    assert not result["activated"]


def test_worked_example_publications_use_approved_prose_instead_of_private_answers():
    _,bank,_ = load_source("member2-v2")
    # A malicious/accidental private answer change must never become teaching prose.
    bank.packs[0].examples[0].reference_answer="PRIVATE-ANSWER-SENTINEL"
    publications = build_examples(bank)
    first = publications[0]
    assert "PRIVATE-ANSWER-SENTINEL" not in first.teaching_text
    assert "Tích (−8)(−5) bằng 40" in first.teaching_text
    assert first.content_version=="0.4.1-member2-kb-examples"


def test_example_publication_revision_does_not_relabel_approved_source_pack():
    registry,bank,origin = load_source("member2-v2")
    projection = project(registry,bank,load_profile(),origin=origin,
                         examples=load_example_publications("member2-v2"))
    examples = [chunk for chunk in projection.chunks if chunk.kind=="example"]
    assert len(examples)==39
    assert all(chunk.content_version=="0.4.1-member2-kb-examples" for chunk in examples)
    assert all(chunk.provenance.pack_version=="0.4.0-member2-review" for chunk in examples)
    assert all(chunk.content_version=="0.4.0-member2-review"
               for chunk in projection.chunks if chunk.kind!="example")


@pytest.mark.parametrize("tamper",["missing_hash","edited_bank","edited_pack_hash"])
def test_approved_source_refuses_missing_or_changed_approval_hashes(tmp_path,monkeypatch,tamper):
    source = tmp_path / "approved"
    shutil.copytree(kb_projection.MEMBER2_SOURCE,source)
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if tamper=="missing_hash":
        manifest["files_sha256"]={}
    elif tamper=="edited_pack_hash":
        manifest["packs"]["A01"]["approved_pack_sha256"]="0"*64
    else:
        bank_path = source / "approved-bank.json"
        bank = json.loads(bank_path.read_text(encoding="utf-8"))
        bank["packs"][0]["explanation"]="Tampered teaching text"
        bank_path.write_text(json.dumps(bank),encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest),encoding="utf-8")
    monkeypatch.setattr(kb_projection,"MEMBER2_SOURCE",source)
    with pytest.raises(ValueError,match="hash|pin"):
        load_source("member2-v2")


def test_edited_example_publication_is_rejected_before_projection(tmp_path,monkeypatch):
    publication = tmp_path / "publication"
    shutil.copytree(kb_projection.MEMBER2_PUBLICATION,publication)
    path = publication / "example-publications.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[0]["teaching_text"]="Edited without a reviewed publication manifest"
    path.write_text(json.dumps(data),encoding="utf-8")
    monkeypatch.setattr(kb_projection,"MEMBER2_PUBLICATION",publication)
    with pytest.raises(ValueError,match="stale"):
        load_example_publications("member2-v2")
