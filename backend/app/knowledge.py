"""Deterministic eligibility and two-state BKT; the LLM cannot write these values."""
import json
import math
from pathlib import Path

PARAMETERS = json.loads((Path(__file__).resolve().parents[2] / 'content/bkt.bootstrap.v1.json').read_text(encoding='utf-8'))
VERSION = PARAMETERS['parameter_version']


def update(prior, correct, params=PARAMETERS):
    if not isinstance(correct, bool): raise ValueError('correct must be boolean')
    values = [prior, params['learn'], params['guess'], params['slip']]
    if any(not isinstance(v, (int, float)) or isinstance(v, bool)
           or not math.isfinite(v) or not 0 <= v <= 1 for v in values):
        raise ValueError('Invalid BKT probability')
    guess, slip, learn = params['guess'], params['slip'], params['learn']
    if guess >= 1 - slip:
        raise ValueError('Guess must be less than one minus slip')
    prediction = prior*(1-slip)+(1-prior)*guess
    denominator = prediction if correct else 1-prediction
    if denominator <= 0: raise ValueError('Impossible observation under parameters')
    posterior = prior*((1-slip) if correct else slip)/denominator
    return {'prediction_before':prediction,'mastery_before':prior,'mastery_after':posterior+(1-posterior)*learn}


def eligibility(assessment, opportunity, observed=False, near=False, *, first_attempt=None,
                retry=False, request_id_seen=False, request_id=None, seen_request_ids=()):
    """Decide whether one verified, independent first attempt can update BKT.

    The request layer normally serves a committed request from its idempotency
    cache before reaching this function. The explicit retry/request ID inputs
    also make the no-double-count rule enforceable by other callers.
    """
    repeated_request = request_id_seen or retry or (
        request_id is not None and request_id in seen_request_ids
    ) or opportunity.get('request_id_seen', False)
    has_observation = observed or opportunity.get('has_standard_observation', False)
    assistance_level = opportunity.get('assistance_level', 0)
    relation = opportunity.get('relation', 'initial')
    if has_observation or repeated_request: reason='already_observed'
    elif assistance_level > 0 or opportunity.get('hint_used', False) or opportunity.get('hint_count', 0) > 0: reason='assisted'
    elif (first_attempt is False or opportunity.get('is_first_attempt') is False
          or opportunity.get('first_attempt') is False
          or opportunity.get('attempt_number', 1) > 1
          or opportunity.get('attempt_count', 1) > 1
          or relation == 'repeat'): reason='repeat'
    elif near or relation == 'near_practice': reason='near_practice'
    elif not isinstance(assessment, dict) or assessment.get('assessment_status') not in ('verified_correct','verified_incorrect'): reason='not_verified'
    elif assessment.get('primary_skill_id') != opportunity.get('target_skill_id'): reason='not_target_evidence'
    else: reason='first_independent_verified'
    return {'eligible':reason=='first_independent_verified','reason':reason}
