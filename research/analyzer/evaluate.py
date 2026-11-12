"""Reproducible authoring/dev regression corpus, NOT a held-out quality benchmark.

Labels derive from authored references/error fixtures and explicit negative cases.
They are draft machine-audited expectations, never human approval or learner data.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

from pydantic import Field, model_validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.contracts import AssessmentStatus, Contract, Identifier
from app.curriculum import load_curriculum
from app.pilot_analyzer import analyze, analyze_bounded
from app.pilot_contracts import PilotSubmission

DATASET = ROOT / 'content/curriculum/analyzer.dev.v1.json'


class Labels(Contract):
    status: AssessmentStatus
    first_error_step: int | None = None
    error_family: str | None = None
    completed: bool


class Record(Contract):
    record_id: Identifier
    problem_id: Identifier
    concept_id: Identifier
    source_group: Identifier
    family_id: Identifier
    origin: str
    submission: PilotSubmission
    expected: Labels


class DevBank(Contract):
    schema_version: str
    content_version: str
    split: str
    label_status: str
    purpose: str
    records: list[Record] = Field(min_length=1)

    @model_validator(mode='after')
    def regression_only(self):
        if self.split != 'authoring_dev' or self.label_status != 'draft_machine_audited':
            raise ValueError('Only draft authoring/dev records are accepted here')
        if len({r.record_id for r in self.records}) != len(self.records):
            raise ValueError('Duplicate record ID')
        return self


def build():
    _, bank = load_curriculum()
    records = []

    def add(problem, suffix, steps, kind, status, completed, first=None, family=None, origin='authored_reference'):
        records.append(Record(record_id=f'{problem.case_id}-{suffix}', problem_id=problem.case_id,
            concept_id=problem.concept_id, source_group=problem.source_group, family_id=problem.family_id,
            origin=origin, submission=PilotSubmission(submission_kind=kind, steps=steps),
            expected=Labels(status=status, first_error_step=first, error_family=family, completed=completed)))

    for pack in bank.packs:
        for problem in pack.problems:
            add(problem, 'reference', problem.reference_steps, 'steps', 'verified_correct', True)
            # E01 deliberately requires transformation evidence.
            e01 = problem.concept_id == 'E01'
            add(problem, 'final', [problem.reference_answer], 'final_answer',
                'unverified' if e01 else 'verified_correct', not e01)
        by_id = {p.case_id: p for p in pack.problems}
        for error in pack.errors:
            problem = by_id[error.problem_id]
            add(problem, error.error_id, error.response_steps, 'steps', 'verified_incorrect', False,
                error.first_error_step, error.family, 'authored_error_fixture')
            add(problem, error.error_id+'-final', [error.response_steps[-1]], 'final_answer',
                'verified_incorrect', False, origin='final_answer_diagnosis_boundary')
        problem = pack.problems[0]
        add(problem, 'ambiguous', ['Em chưa biết làm'], 'steps', 'needs_clarification', False, origin='explicit_negative_case')
        add(problem, 'unsafe', ['__import__("os")'], 'steps', 'needs_clarification', False, origin='explicit_negative_case')
    return DevBank(schema_version='1.0.0', content_version=bank.content_version, split='authoring_dev',
        label_status='draft_machine_audited', purpose='Development regression, not independent evaluation', records=records)


def evaluate(dataset=DATASET):
    dev = DevBank.model_validate_json(dataset.read_text(encoding='utf-8'))
    _, bank = load_curriculum()
    if dev.content_version != bank.content_version:
        raise ValueError('Dev/pilot version mismatch')
    problems = {p.case_id: (pack, p) for pack in bank.packs for p in pack.problems}
    counts, confusion, failures = defaultdict(Counter), Counter(), []
    predictions = []
    for record in dev.records:
        if record.problem_id not in problems:
            raise ValueError('Unknown problem in dev corpus')
        pack, problem = problems[record.problem_id]
        if (record.concept_id, record.source_group, record.family_id) != (problem.concept_id, problem.source_group, problem.family_id):
            raise ValueError('Incorrect source grouping')
        outcome = analyze(problem, record.submission, pack.errors, content_version=pack.content_version)
        actual = Labels(status=outcome.assessment.assessment_status,
            first_error_step=outcome.assessment.first_error_step,
            error_family=outcome.assessment.error_family, completed=outcome.completed)
        match = actual == record.expected
        confusion[(record.expected.status.value, actual.status.value)] += 1
        for key in (record.concept_id, problem.task.kind):
            counts[key].update(total=1, exact_match=int(match))
        if not match:
            failures.append(record.record_id)
        predictions.append({'record_id': record.record_id, 'expected': record.expected.model_dump(mode='json'),
                            'actual': actual.model_dump(mode='json'), 'exact_match': match})
    result = {'scope': dev.purpose, 'label_status': dev.label_status, 'split': dev.split,
        'records': len(dev.records), 'exact_matches': len(dev.records)-len(failures),
        'failures': failures, 'by_concept_or_task': dict(counts),
        'status_confusion': [{'expected': a, 'actual': b, 'count': n} for (a,b),n in sorted(confusion.items())],
        'diagnosis_labels': dict(Counter(r.expected.error_family or 'unknown' for r in dev.records)),
        'limitations': ['Authored reference traces and error patterns overlap development knowledge.',
                         'No held-out accuracy/F1, real-learner efficacy or human review is claimed.',
                         'Sealed test must be authored/reviewed separately and grouped by source/family.'],
        'sha256': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                   [dataset, ROOT/'content/curriculum/pilot.v1.json', ROOT/'backend/app/learner_math.py',
                    ROOT/'backend/app/pilot_analyzer.py', Path(__file__)]}}
    return result, predictions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-dev', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--problem', help='Grade one internal pilot problem offline')
    parser.add_argument('--kind', choices=['steps', 'final_answer'], default='steps')
    parser.add_argument('--step', action='append', help='Repeat for successive full expression snapshots')
    args = parser.parse_args()
    if args.problem:
        if not args.step or args.build_dev or args.output:
            parser.error('--problem requires --step and cannot combine with --build-dev/--output')
        _, bank = load_curriculum()
        for pack in bank.packs:
            for problem in pack.problems:
                if problem.case_id == args.problem:
                    outcome = analyze_bounded(problem, PilotSubmission(submission_kind=args.kind, steps=args.step),
                                              pack.errors, content_version=pack.content_version)
                    print(outcome.model_dump_json(indent=2))
                    return
        parser.error('Unknown pilot problem ID')
    if args.step:
        parser.error('--step requires --problem')
    if args.build_dev:
        # Explicit deterministic rebuild; keep the original raw/public KT data untouched.
        DATASET.write_text(build().model_dump_json(indent=2)+'\n', encoding='utf-8')
    report, predictions = evaluate()
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        (args.output/'predictions.json').write_text(json.dumps(predictions, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report['failures']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
