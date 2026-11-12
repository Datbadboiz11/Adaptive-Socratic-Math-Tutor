"""Real Neo4j Query API parity; opt in on localhost/CI, no graph deletions."""
import os
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.curriculum import load_curriculum
from app.curriculum_graph import Neo4jGraph, snapshot_id, paths

pytestmark=pytest.mark.skipif(os.getenv('RUN_GRAPH_TESTS')!='1',reason='Set RUN_GRAPH_TESTS=1 with a real Neo4j instance')


def test_real_neo4j_import_is_idempotent_and_complete():
    registry,_=load_curriculum(); driver=Neo4jGraph()
    first=driver.import_registry(registry)
    assert first==driver.import_registry(registry)
    sid=snapshot_id(registry)
    assert driver.query('MATCH (c:CurriculumConcept {snapshot_id:$sid}) RETURN count(c) AS n',{'sid':sid})==[{'n':40}]
    assert driver.query('MATCH (a:CurriculumConcept {snapshot_id:$sid})-[r]->(b:CurriculumConcept {snapshot_id:$sid}) RETURN count(r) AS n',{'sid':sid})==[{'n':68}]


def test_real_neo4j_prerequisite_parity_and_draft_boundary():
    registry,bank=load_curriculum(); driver=Neo4jGraph(); driver.import_registry(registry)
    for pack in bank.packs:
        assert driver.prerequisites(registry,pack.concept_id,authoring=True)==paths(registry,pack.concept_id,authoring=True)
        assert driver.prerequisites(registry,pack.concept_id)==[]
