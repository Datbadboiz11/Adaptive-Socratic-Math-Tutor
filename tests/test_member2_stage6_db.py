"""Product-graph pairs on isolated PostgreSQL. Vectors are fixtures; serving uses direct/metadata only."""
import os
from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT, ROOT / "backend", ROOT / "tests"):
    sys.path.insert(0, str(folder))

from app.kb_projection import load_example_publications, load_profile, load_source, project
from app.kb_sync import sync_projection
from kb_support import FakeEmbedder
from research.retrieval.stage6.paired_outputs import assessment_signature, run_pairs, summarize_pairs
from scripts.checks.check_stage3_kb import isolated_acceptance_schema


@pytest.mark.skipif(not os.getenv("RUN_DB_TESTS"), reason="Stage 6 product pairs require PostgreSQL/pgvector")
def test_all_104_product_pairs_preserve_grading_and_policy_without_session_writes():
    registry, bank, origin = load_source("member2-v2")
    projection = project(registry, bank, load_profile(), origin=origin,
                         examples=load_example_publications("member2-v2"))
    with isolated_acceptance_schema(uuid4().hex[:12]) as isolation:
        sync_projection(projection, FakeEmbedder(projection.profile), activate=True)
        pairs = run_pairs(bank, projection.snapshot_id)
    assert isolation["schema_removed"] and isolation["serving_before"] == isolation["serving_after"]
    assert len(pairs) == 104 and len({pair["concept_id"] for pair in pairs}) == 13
    for pair in pairs:
        full, no_rag = pair["variants"]["full"], pair["variants"]["no_rag"]
        assert assessment_signature(full["assessment"]) == assessment_signature(no_rag["assessment"])
        assert full["policy"] == no_rag["policy"]
        assert full["response"]["content_refs"] and not no_rag["response"]["content_refs"]
        if pair["scenario_class"] == "wrong_submission":
            assert full["assessment"]["assessment_status"] == "verified_incorrect"
    summary = summarize_pairs(pairs)
    assert summary["identical_messages"] == 78 and summary["different_messages"] == 26
    assert summary["quality_ratings"] is None and summary["session_writes"] == 0
