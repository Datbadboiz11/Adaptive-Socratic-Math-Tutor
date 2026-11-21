"""Tests for trace-only, one-off misconception diagnosis."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.math_validator import validate, validate_bounded  # type: ignore[reportMissingImports]
from app.misconceptions import CONCEPT_IDS, MISCONCEPTION_CATALOG, TraceContext


class MisconceptionCatalogTests(unittest.TestCase):
    def test_catalog_covers_all_fourteen_concepts_with_callable_detectors(self):
        self.assertEqual(set(MISCONCEPTION_CATALOG), CONCEPT_IDS)
        identifiers = []
        for concept_id, entries in MISCONCEPTION_CATALOG.items():
            self.assertGreaterEqual(len(entries), 2, concept_id)
            for entry in entries:
                identifiers.append(entry['error_id'])
                self.assertTrue(entry['description'])
                self.assertTrue(callable(entry['pattern_detector']))
                self.assertTrue(entry['trace_examples'])
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_each_detector_matches_its_trace_and_rejects_a_near_miss(self):
        for concept_id, entries in MISCONCEPTION_CATALOG.items():
            for entry in entries:
                for before, after in entry['trace_examples']:
                    with self.subTest(concept=concept_id, error_id=entry['error_id']):
                        detector = entry['pattern_detector']
                        trace = TraceContext({}, concept_id, 1, before, after, ())
                        self.assertTrue(detector(trace))
                        near_miss = TraceContext({}, concept_id, 1, before, after + '+1', ())
                        self.assertFalse(detector(near_miss))

    def test_verified_incorrect_known_trace_is_only_suspected(self):
        problem = {
            'concept_id': 'A02',
            'expression': '3*(x+2)',
            'llm_explanation': 'The student applied the rule correctly.',
        }
        assessment = validate(problem, ['3x+2'])['assessment']
        self.assertEqual(assessment['assessment_status'], 'verified_incorrect')
        self.assertEqual(assessment['misconception_candidate'], 'M_DIST_01')
        self.assertEqual(assessment['diagnosis_status'], 'suspected')

    def test_symbolic_rules_generalize_beyond_literal_trace_examples(self):
        cases = [
            ({'concept_id': 'A02', 'expression': '2*(x+5)'}, ['2x+5'], 'M_DIST_01'),
            ({'concept_id': 'A02', 'expression': '4(x-1)'}, ['4x-1'], 'M_DIST_01'),
            ({'concept_id': 'A02', 'expression': '3(x+2)'}, ['3*x+2'], 'M_DIST_01'),
            ({'concept_id': 'E02', 'equation': '-3*(x-2)=12'}, ['-3x-6=12'], 'M_EQ_DIST_02'),
            ({'concept_id': 'A05', 'expression': '(x+5)^2'}, ['x^2+25'], 'M_SQUARE_01'),
            ({'concept_id': 'E04', 'equation': '(x-2)(x+3)=0'}, ['x-2=0'], 'M_ZERO_01'),
            ({'concept_id': 'E04', 'equation': 'x*(x-4)=0'}, ['x-4=0'], 'M_ZERO_02'),
            ({'concept_id': 'E05', 'equation': '(x-1)/(x+2)=0'}, ['x=-2'], 'M_DOMAIN_02'),
            ({'concept_id': 'E06', 'equation': 'x^2=16'}, ['x=4'], 'M_QUAD_01'),
        ]
        for problem, steps, expected_id in cases:
            with self.subTest(concept=problem['concept_id'], steps=steps):
                assessment = validate(problem, steps)['assessment']
                self.assertEqual(assessment['assessment_status'], 'verified_incorrect')
                self.assertEqual(assessment['misconception_candidate'], expected_id)
                self.assertEqual(assessment['diagnosis_status'], 'suspected')

    def test_symbolic_rules_cover_each_algebra_and_equation_concept(self):
        cases = [
            ({'concept_id': 'A01', 'expression': '5*(-7)+4'}, ['5*7+4'], 'M_SUB_01'),
            ({'concept_id': 'A01', 'expression': '4*x*x+9'}, ['4*x+9'], 'M_SUB_02'),
            ({'concept_id': 'A02', 'expression': '5*(x+7)'}, ['5x+7'], 'M_DIST_01'),
            ({'concept_id': 'A02', 'expression': '-4*(x-3)'}, ['-4x-12'], 'M_DIST_02'),
            ({'concept_id': 'A03', 'expression': '3x+4x'}, ['12x^2'], 'M_LIKE_01'),
            ({'concept_id': 'A03', 'expression': '12+(-5)'}, ['17'], 'M_LIKE_02'),
            ({'concept_id': 'A04', 'expression': '(x+4)(x+7)'}, ['x^2+28'], 'M_POLY_01'),
            ({'concept_id': 'A04', 'expression': '(x-4)(x+2)'}, ['x^2-2x+8'], 'M_POLY_02'),
            ({'concept_id': 'A05', 'expression': '(x+6)^2'}, ['x^2+36'], 'M_SQUARE_01'),
            ({'concept_id': 'A06', 'expression': '(x+5)(x-5)'}, ['x^2+25'], 'M_DIFFSQ_01'),
            ({'concept_id': 'A06', 'expression': 'x^2-49'}, ['(x-7)^2'], 'M_DIFFSQ_02'),
            ({'concept_id': 'A07', 'expression': '8x+12'}, ['8(x+12)'], 'M_FACTOR_01'),
            ({'concept_id': 'A07', 'expression': '6x^2+10x'}, ['2(3x^2+5)'], 'M_FACTOR_02'),
            ({'concept_id': 'A08', 'expression': 'x^2+7x+10'}, ['(x+3)(x+4)'], 'M_GROUP_01'),
            ({'concept_id': 'A08', 'expression': 'x^2-x-12'}, ['(x-4)(x-3)'], 'M_GROUP_02'),
            ({'concept_id': 'E01', 'equation': '4x+5=9'}, ['4x=14'], 'M_EQ_01'),
            ({'concept_id': 'E01', 'equation': '-3x=12'}, ['x=4'], 'M_EQ_02'),
            ({'concept_id': 'E02', 'equation': '5x+4=19'}, ['5x=23'], 'M_INV_01'),
            ({'concept_id': 'E02', 'equation': '-4x=20'}, ['x=5'], 'M_SIGN_01'),
            ({'concept_id': 'E03', 'equation': 'x+6=15'}, ['x-6=15'], 'M_MODEL_01'),
            ({'concept_id': 'E03', 'equation': '4x=28'}, ['x=28+4'], 'M_MODEL_02'),
            ({'concept_id': 'E06', 'equation': 'x^2-5x+6=0'},
             ['x=-2 or x=-3'], 'M_QUAD_02'),
        ]
        for problem, steps, expected_id in cases:
            with self.subTest(concept=problem['concept_id'], expected=expected_id):
                assessment = validate(problem, steps)['assessment']
                self.assertEqual(assessment['assessment_status'], 'verified_incorrect')
                self.assertEqual(assessment['misconception_candidate'], expected_id)
                self.assertEqual(assessment['diagnosis_status'], 'suspected')

    def test_negative_distribution_reference_step_is_mathematically_correct(self):
        result = validate(
            {'concept_id': 'E02', 'equation': '-3*(x-2)=12'},
            ['-3x+6=12'],
        )['assessment']
        self.assertEqual(result['assessment_status'], 'unverified')
        self.assertEqual(result['reason_code'], 'valid_partial')
        self.assertIsNone(result['first_error_step'])

    def test_unrecognized_error_returns_unknown_and_unverified_diagnosis(self):
        problem = {'concept_id': 'A02', 'expression': '2*(x+3)'}
        assessment = validate(problem, ['2x+7'])['assessment']
        self.assertEqual(assessment['assessment_status'], 'verified_incorrect')
        self.assertEqual(assessment['misconception_candidate'], 'unknown')
        self.assertEqual(assessment['diagnosis_status'], 'unverified')
        schema_path = ROOT / 'contracts' / 'v1' / 'Assessment.schema.json'
        schema = json.loads(schema_path.read_text(encoding='utf-8'))
        self.assertIn('unverified', schema['properties']['diagnosis_status']['enum'])

    def test_llm_explanation_cannot_change_symbolic_status_or_candidate(self):
        base = {'concept_id': 'A02', 'expression': '3*(x+2)'}
        wrong = validate(base, ['3x+2'])['assessment']
        with_llm = validate({**base, 'llm_explanation': 'This is equivalent.'},
                            ['3x+2'])['assessment']
        correct = validate({**base, 'llm_explanation': 'This is incorrect.'},
                           ['3x+6'])['assessment']
        self.assertEqual((wrong['assessment_status'], wrong['misconception_candidate'],
                          wrong['diagnosis_status']),
                         (with_llm['assessment_status'], with_llm['misconception_candidate'],
                          with_llm['diagnosis_status']))
        self.assertEqual(correct['assessment_status'], 'verified_correct')

    def test_worker_returns_the_same_trace_diagnosis(self):
        problem = {'concept_id': 'A02', 'expression': '3*(x+2)'}
        assessment = validate_bounded(problem, ['3x+2'], timeout=2.75)['assessment']
        self.assertEqual(assessment['assessment_status'], 'verified_incorrect')
        self.assertEqual(assessment['misconception_candidate'], 'M_DIST_01')
        self.assertEqual(assessment['diagnosis_status'], 'suspected')

    def test_authored_linear_error_traces_map_to_catalog_ids(self):
        problem = {
            'equation': '2*(x-3)=10',
            'primary_skill_id': 'SK-LIN-SOLVE',
            'common_errors': [{
                'error_id': 'ERR-LIN-003',
                'steps': ['2x-3=10', '2x=13', 'x=6.5'],
                'first_error_step': 1,
                'hypothesis': 'Text is not used as a detector signal.',
            }],
        }
        assessment = validate(problem, ['2x-3=10', '2x=13', 'x=6.5'])['assessment']
        self.assertEqual(assessment['first_error_step'], 1)
        self.assertEqual(assessment['misconception_candidate'], 'M_EQ_DIST_01')
        self.assertEqual(assessment['diagnosis_status'], 'suspected')

    def test_unknown_problem_concept_never_gets_a_guessed_misconception(self):
        assessment = validate({'equation': 'x+1=3'}, ['x=5'])['assessment']
        self.assertEqual(assessment['assessment_status'], 'verified_incorrect')
        self.assertEqual(assessment['misconception_candidate'], 'unknown')
        self.assertEqual(assessment['diagnosis_status'], 'unverified')


if __name__ == '__main__':
    unittest.main()
