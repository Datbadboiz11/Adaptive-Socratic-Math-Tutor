"""Authoring coverage, graph direction, publication boundaries and exact math."""
import copy
from fractions import Fraction
import json
from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts/checks'))
from app.curriculum import CurriculumRegistry, PilotBank, MathTask, load_curriculum, prerequisite_candidates, safe_chunks
from app.authoring_math import polynomial, expected, response_value, audit_case, first_error
from check_curriculum import audit


def source_registry():
    return json.loads((ROOT / 'content/curriculum/registry.v1.json').read_text(encoding='utf-8'))


def source_bank():
    return json.loads((ROOT / 'content/curriculum/pilot.v1.json').read_text(encoding='utf-8'))


def approve(review):
    review.update(status='human_approved', human_reviewer='synthetic-test-reviewer', reviewed_at='2026-10-04T09:00:00+07:00')


def test_real_pilot_math_and_coverage_without_inventing_review():
    result = audit()
    assert result['registry_concepts'] == 40 and result['pilot_concepts'] == 10
    assert result['concept_review_counts'] == {'draft': 40}
    assert sum(c['problems'] for c in result['coverage']) == 60
    assert sum(c['examples'] for c in result['coverage']) == 30
    assert all(c['families'] >= 3 and c['public_chunks'] == 0 for c in result['coverage'])


@pytest.mark.parametrize('change', ['duplicate', 'missing_source', 'missing_endpoint', 'self_edge', 'duplicate_edge', 'cycle', 'strand', 'skill'])
def test_registry_rejects_broken_integrity(change):
    data = source_registry()
    if change == 'duplicate': data['concepts'][1] = copy.deepcopy(data['concepts'][0])
    elif change == 'missing_source': data['concepts'][0]['alignment']['source_id'] = 'missing'
    elif change == 'missing_endpoint': data['edges'][0]['source_concept_id'] = 'missing'
    elif change == 'self_edge': data['edges'][0]['target_concept_id'] = data['edges'][0]['source_concept_id']
    elif change == 'duplicate_edge': data['edges'].append(copy.deepcopy(data['edges'][0]))
    elif change == 'cycle':
        edge = copy.deepcopy(data['edges'][0]); edge.update(edge_id='REVERSE', source_concept_id='N02', target_concept_id='N01')
        data['edges'].append(edge)
    elif change == 'strand': data['concepts'][0]['strand'] = 'functions'
    elif change == 'skill': data['concepts'][1]['skills'] = copy.deepcopy(data['concepts'][0]['skills'])
    with pytest.raises(ValidationError): CurriculumRegistry.model_validate(data)


def test_related_edge_does_not_change_prerequisite_dag():
    data = source_registry()
    edge = copy.deepcopy(data['edges'][0]); edge.update(edge_id='RELATED', source_concept_id='N02', target_concept_id='N01', relation='RELATED_TO')
    data['edges'].append(edge)
    registry = CurriculumRegistry.model_validate(data)
    assert prerequisite_candidates(registry, 'N01', authoring=True) == []


def test_prerequisites_follow_incoming_edges_and_stop_after_two_levels():
    registry, _ = load_curriculum()
    assert prerequisite_candidates(registry, 'E02') == []
    direct = prerequisite_candidates(registry, 'E02', 1, authoring=True)
    assert {r['concept_id'] for r in direct} == {'E01', 'A02', 'A03'}
    second = prerequisite_candidates(registry, 'E02', 2, authoring=True)
    assert 'N01' in {r['concept_id'] for r in second}
    assert 'E02' not in {r['concept_id'] for r in second}
    assert all(r['depth'] <= 2 and r['edge_id'].startswith('PRE-') for r in second)
    with pytest.raises(ValueError): prerequisite_candidates(registry, 'E02', 3)


def test_partial_approval_cannot_publish_drafts_or_private_references():
    data, bank_data = source_registry(), source_bank()
    concept = next(c for c in data['concepts'] if c['concept_id'] == 'A02')
    pack = next(p for p in bank_data['packs'] if p['concept_id'] == 'A02')
    approve(pack['review'])
    registry, bank = CurriculumRegistry.model_validate(data), PilotBank.model_validate(bank_data)
    assert safe_chunks(registry, bank, 'A02') == []
    concept['alignment'].update(status='human_approved', reviewer='synthetic-test-reviewer')
    approve(concept['review'])
    registry = CurriculumRegistry.model_validate(data)
    chunks = safe_chunks(registry, bank, 'A02', 1)
    assert len(chunks) == 2 and {c['kind'] for c in chunks} == {'explanation', 'hint'}
    assert len(safe_chunks(registry, bank, 'A02', 3)) == 4
    text = json.dumps(chunks)
    assert 'reference_answer' not in text and 'reference_steps' not in text and 'P-A02' not in text
    assert safe_chunks(registry, bank, 'missing') == []
    with pytest.raises(ValueError): safe_chunks(registry, bank, 'A02', 4)


def test_approval_requires_provenance_and_curriculum_alignment():
    data = source_registry()
    data['concepts'][0]['review']['status'] = 'human_approved'
    with pytest.raises(ValidationError): CurriculumRegistry.model_validate(data)
    approve(data['concepts'][0]['review'])
    with pytest.raises(ValidationError): CurriculumRegistry.model_validate(data)


@pytest.mark.parametrize('change', ['duplicate', 'family', 'hint', 'error', 'version'])
def test_pilot_rejects_broken_coverage_and_references(change):
    data = source_bank(); pack = data['packs'][0]
    if change == 'duplicate': pack['problems'][1]['case_id'] = pack['problems'][0]['case_id']
    elif change == 'family':
        for problem in pack['problems']: problem['family_id'] = 'ONE-FAMILY'
    elif change == 'hint': pack['hints'][1]['level'] = 1
    elif change == 'error': pack['errors'][0]['problem_id'] = 'missing'
    elif change == 'version': pack['content_version'] = 'different'
    with pytest.raises(ValidationError): PilotBank.model_validate(data)


def test_loader_rejects_cross_file_skill_and_pilot_mismatch(tmp_path):
    data, bank = source_registry(), source_bank()
    (tmp_path / 'registry.v1.json').write_text(json.dumps(data), encoding='utf-8')
    bank['packs'][0]['problems'][0]['primary_skill_id'] = 'SK-missing'
    (tmp_path / 'pilot.v1.json').write_text(json.dumps(bank), encoding='utf-8')
    with pytest.raises(ValueError, match='unknown skill'): load_curriculum(tmp_path)
    data['concepts'][0]['pilot'] = False
    (tmp_path / 'registry.v1.json').write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='coverage'): load_curriculum(tmp_path)


@pytest.mark.parametrize('expression', ["__import__('os')", 'x**99999', '1/x', '1/0', 'x*x*x', '1e9', 'x.__class__', '2^3', 'x' * 161])
def test_authoring_grammar_rejects_unsafe_or_unsupported_input(expression):
    with pytest.raises((ValueError, SyntaxError)): polynomial(expression)


def test_exact_rationals_polynomial_identity_and_vertex():
    assert polynomial('3*(x+2)') == polynomial('3*x+6')
    assert polynomial('x+x') != polynomial('x*x')
    assert expected(MathTask(kind='evaluate', expression='(x+1)/2', variable_value='1/3')) == Fraction(2, 3)
    assert expected(MathTask(kind='quadratic_vertex', expression='2*x*x+4*x-1')) == (-1, -3)
    with pytest.raises(ValueError): expected(MathTask(kind='quadratic_vertex', expression='2*x+1'))
    with pytest.raises(ValueError): expected(MathTask(kind='linear_equation', expression='x=x'))


def test_substitution_requires_matching_task_type():
    with pytest.raises(ValidationError): MathTask(kind='evaluate', expression='x+1')
    with pytest.raises(ValidationError): MathTask(kind='polynomial', expression='x+1', variable_value='2')


def test_loader_rejects_wrong_task_type_for_the_measured_skill(tmp_path):
    registry, bank = source_registry(), source_bank()
    registry['concepts'][0]['authoring_task_kinds'] = ['linear_equation']
    (tmp_path / 'registry.v1.json').write_text(json.dumps(registry), encoding='utf-8')
    (tmp_path / 'pilot.v1.json').write_text(json.dumps(bank), encoding='utf-8')
    with pytest.raises(ValueError, match='authoring scope'): load_curriculum(tmp_path)


def test_wrong_answer_and_carried_forward_first_error_are_detected():
    _, bank = load_curriculum()
    problem = next(p for p in bank.packs if p.concept_id == 'E02').problems[2]
    assert first_error(problem, ['2*x-3=10', '2*x=13', 'x=13/2']) == 1
    assert first_error(problem, ['x-3=5', 'x=8']) is None
    bad = problem.model_copy(update={'reference_answer': '13/2'})
    with pytest.raises(ValueError, match='Wrong reference'): audit_case(bad)


def test_pilot_does_not_change_legacy_ids_or_research_parameters():
    registry, _ = load_curriculum()
    legacy = json.loads((ROOT / 'content/linear_equations.v1.json').read_text(encoding='utf-8'))
    parameters = json.loads((ROOT / 'content/bkt.bootstrap.v1.json').read_text(encoding='utf-8'))
    assert all(p['concept_id'] == 'CON-LINEAR-01' and p['primary_skill_id'] == 'SK-LIN-SOLVE' for p in legacy['problems'])
    assert parameters['skill_id'] == 'SK-LIN-SOLVE'
    assert registry.legacy_mappings[0].status == 'proposed'
