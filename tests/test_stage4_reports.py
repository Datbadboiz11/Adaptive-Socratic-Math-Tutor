"""Evidence semantics independent of retrieval and immutable legacy reports."""
from copy import deepcopy
from uuid import uuid4
import pytest
from app.report_diagnoses import diagnoses, parameter_source
from app.knowledge import PARAMETERS
from app.session_contracts import Report


def sample(status='verified_incorrect', *, op=None, candidate='Phân phối thiếu', facts=None):
    return dict(turn_id=uuid4(), opportunity_id=op or uuid4(), action='submit',
        response={'counts_as_assistance': True},
        assessment=dict(assessment_status=status, first_error_step=1,
                        misconception_candidate=candidate, error_family='DISTRIBUTION',
                        diagnosis_status='suspected', evidence=['step:1:not_equivalent'] if facts is None else facts))


def opportunity(turn, family='F1', relation='initial'):
    return dict(opportunity_id=turn['opportunity_id'], family_id=family, relation=relation,
                assistance_received=True, assistance_level=1)


def test_single_trace_is_suspected_and_original_evidence_is_unchanged():
    turn=sample(); original=deepcopy(turn)
    result=diagnoses([turn],[opportunity(turn)])
    assert result[0]['status']=='suspected'
    assert result[0]['evidence'][0]['turn_id']==turn['turn_id']
    assert turn==original


def test_repeated_first_independent_error_across_families_is_supported():
    first,second=sample(),sample()
    result=diagnoses([first,second],[opportunity(first),opportunity(second,'F2','cross_family')])
    assert result[0]['status']=='supported'
    assert result[0]['scope']=='observed_error_trace'


@pytest.mark.parametrize('relation,family',[('repeat','F2'),('near_practice','F2'),('cross_family','F1')])
def test_related_or_same_family_does_not_establish_recurrence(relation,family):
    first,second=sample(),sample()
    assert diagnoses([first,second],[opportunity(first),opportunity(second,family,relation)])[0]['status']=='suspected'


def test_prior_help_and_retries_are_not_independent_support():
    first,second=sample(),sample()
    help_turn={**deepcopy(second),'turn_id':uuid4(),'action':'request_hint'}
    assert diagnoses([first,help_turn,second],[opportunity(first),opportunity(second,'F2','cross_family')])[0]['status']=='suspected'
    retry={**deepcopy(first),'turn_id':uuid4()}
    assert diagnoses([first,retry],[opportunity(first)])[0]['status']=='suspected'


def test_correction_rejects_only_latest_submission_claim():
    wrong=sample(); correct=sample('verified_correct',op=wrong['opportunity_id'])
    correct['assessment']['evidence']=['task:verified_solution']
    result=diagnoses([wrong,correct],[opportunity(wrong)])
    assert [r['status'] for r in result]==['suspected','rejected']
    assert result[1]['scope']=='latest_submission'
    assert [e['turn_id'] for e in result[1]['evidence']]==[wrong['turn_id'],correct['turn_id']]
    later_wrong=sample(op=wrong['opportunity_id'])
    assert len(diagnoses([wrong,correct,later_wrong],[opportunity(wrong)]))==1


@pytest.mark.parametrize('turn',[sample('unverified'),sample(candidate=None),sample(facts=[])])
def test_missing_verified_trace_never_fabricates_diagnosis(turn):
    assert diagnoses([turn],[opportunity(turn)])==[]


def test_parameter_provenance_does_not_borrow_current_source_for_old_version():
    assert parameter_source(PARAMETERS['parameter_version'],PARAMETERS)==PARAMETERS['source']
    assert PARAMETERS['source'] not in parameter_source('unknown-previous',PARAMETERS)


def test_rejection_does_not_include_another_opportunity_that_is_still_wrong():
    first,second=sample(),sample()
    correct=sample('verified_correct',op=first['opportunity_id'])
    result=diagnoses([first,second,correct],[opportunity(first),opportunity(second,'F2','cross_family')])
    rejection=next(d for d in result if d['status']=='rejected')
    assert {e['turn_id'] for e in rejection['evidence']}=={first['turn_id'],correct['turn_id']}


def test_correction_without_verifier_facts_does_not_reject_hypothesis():
    wrong=sample(); correct=sample('verified_correct',op=wrong['opportunity_id'],facts=[])
    assert len(diagnoses([wrong,correct],[opportunity(wrong)]))==1


def test_frozen_v2_report_remains_readable_without_invented_diagnoses():
    old=dict(session_id=uuid4(),status='completed',independent_correct=0,assisted_correct=0,
        valid_observations=0,unverified_submissions=0,submitted_turns=0,problems_viewed=1,
        requested_hints=0,completed_at=None,timeline=[],limitations=[],report_version='learning-report-2.0.0')
    original=deepcopy(old)
    assert Report.model_validate(old).report_version=='learning-report-2.0.0'
    assert old==original
