"""Disposable, deadline-bounded worker for internal pilot submissions."""
import json
import sys

from app.curriculum import AuthoredProblem, ErrorFixture
from app.pilot_analyzer import analyze
from app.pilot_contracts import PilotSubmission


def main():
    payload = json.loads(sys.stdin.read(32000))
    problem = AuthoredProblem.model_validate(payload['problem'])
    submission = PilotSubmission.model_validate(payload['submission'])
    errors = [ErrorFixture.model_validate(e) for e in payload['errors']]
    print(analyze(problem, submission, errors, content_version=payload['content_version']).model_dump_json())


if __name__ == '__main__':
    main()
