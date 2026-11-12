"""Trusted query projection shared by grounding and the Kaggle batch catalog."""

POLICY_VERSION = 'objective-authored-diagnostic-v1'


def grounding_query(concept, diagnostic_question=None):
    query = f'{concept.title}. {concept.objective}'
    if diagnostic_question:
        query += ' ' + diagnostic_question
    return query[:600]
