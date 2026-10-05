"""Deterministic eligibility and two-state BKT; the LLM cannot write these values."""
import json
import math
from pathlib import Path

PARAMETERS = json.loads((Path(__file__).resolve().parents[2] / 'content/bkt.bootstrap.v1.json').read_text(encoding='utf-8'))
VERSION = PARAMETERS['parameter_version']


def update(prior, correct, params=PARAMETERS):
    if not isinstance(correct, bool): raise ValueError('correct must be boolean')
    values = [prior, params['learn'], params['guess'], params['slip']]
    if any(not math.isfinite(v) or not 0 <= v <= 1 for v in values): raise ValueError('Invalid BKT probability')
    guess, slip, learn = params['guess'], params['slip'], params['learn']
    prediction = prior*(1-slip)+(1-prior)*guess
    denominator = prediction if correct else 1-prediction
    if denominator <= 0: raise ValueError('Impossible observation under parameters')
    posterior = prior*((1-slip) if correct else slip)/denominator
    return {'prediction_before':prediction,'mastery_before':prior,'mastery_after':posterior+(1-posterior)*learn}


def eligibility(assessment, opportunity, observed=False, near=False):
    if observed: reason='already_observed'
    elif opportunity['assistance_level'] > 0: reason='assisted'
    elif opportunity['relation'] == 'repeat': reason='repeat'
    elif near or opportunity['relation'] == 'near_practice': reason='near_practice'
    elif assessment['assessment_status'] not in ('verified_correct','verified_incorrect'): reason='not_verified'
    elif assessment['primary_skill_id'] != opportunity['target_skill_id']: reason='not_target_evidence'
    else: reason='first_independent_verified'
    return {'eligible':reason=='first_independent_verified','reason':reason}
