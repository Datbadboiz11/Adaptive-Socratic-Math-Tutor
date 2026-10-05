"""Audit drafts, coverage, graph and exact math; never assign human approval."""
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.curriculum import load_curriculum, safe_chunks
from app.authoring_math import audit_case, first_error, scalar


def audit():
    registry, bank = load_curriculum()
    if {c.concept_id for c in registry.concepts} != {f'{prefix}{i:02}' for prefix in 'NAEF' for i in range(1, 11)}:
        raise ValueError('Registry differs from the declared 40-concept plan')
    results = []
    for pack in bank.packs:
        for case in [*pack.problems, *pack.examples]:
            audit_case(case)
            if pack.concept_id == 'N04' and case.reference_answer != str(scalar(case.reference_answer)):
                raise ValueError('Fraction reference must be reduced with positive denominator')
        problems = {p.case_id: p for p in pack.problems}
        for error in pack.errors:
            if first_error(problems[error.problem_id], error.response_steps) != error.first_error_step:
                raise ValueError(f'Wrong first error label: {error.error_id}')
        results.append({'concept_id': pack.concept_id, 'problems': len(pack.problems),
                        'families': len({p.family_id for p in pack.problems}),
                        'examples': len(pack.examples), 'error_fixtures': len(pack.errors),
                        'math_audit': 'pass', 'human_review': pack.review.status,
                        'public_chunks': len(safe_chunks(registry, bank, pack.concept_id))})
    return {'content_version': bank.content_version, 'registry_concepts': len(registry.concepts),
            'pilot_concepts': len(bank.packs), 'edges': len(registry.edges),
            'concept_review_counts': dict(Counter(c.review.status for c in registry.concepts)),
            'coverage': results,
            'note': 'Authoring checks only. Drafts are not seeded into the MVP or published to learners.'}


if __name__ == '__main__':
    print(json.dumps(audit(), ensure_ascii=True, indent=2))
