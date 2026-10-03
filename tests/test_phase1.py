"""Meaningful checks for content, contract boundaries, and health failure behavior."""
import sys
import json
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
from app.contracts import Assessment, Eligibility, ProblemPublic, Review, TurnRequest
from app.main import app
from app import contracts
from check_phase1 import audit, linear_expression, solution


def test_shared_contract_examples():
    examples = json.loads((ROOT / "contracts/examples.v1.json").read_text(encoding="utf-8"))
    for example in examples:
        getattr(contracts, example["schema"]).model_validate(example["payload"])


def test_all_curated_solutions_and_wrong_steps():
    assert len(audit()["problems"]) == 6


@pytest.mark.parametrize("bad", ["__import__('os')", "x*x", "1/x", "x**999999", "2e8", "(x).__class__", "1/0"])
def test_authoring_checker_rejects_unsupported_syntax(bad):
    with pytest.raises((ValueError, SyntaxError)):
        linear_expression(bad)


def test_alternative_method_and_exact_rationals():
    assert solution("2(x - 3) = 10") == solution("x - 3 = 5")
    assert solution("x = 11/2") == solution("x = 5.5")


def test_public_problem_rejects_private_fields():
    with pytest.raises(ValidationError):
        ProblemPublic(problem_id="LIN-003", content_version="0.1.0", concept_id="CON-LINEAR-01", primary_skill_id="SK-LIN-SOLVE", family_id="F-A-XB-C", prompt="Giải phương trình", equation="2(x-3)=10", difficulty="standard", reference_answer="8")


def test_human_approval_cannot_be_invented():
    with pytest.raises(ValidationError):
        Review(status="human_approved", author="author", source="original")


@pytest.mark.parametrize("action,steps", [("submit", []), ("submit", ["   "]), ("request_hint", ["x=8"]), ("submit", ["x" * 161])])
def test_invalid_turn_payloads(action, steps):
    with pytest.raises(ValidationError):
        TurnRequest(request_id=uuid4(), opportunity_id=uuid4(), expected_state_version=1, action=action, steps=steps)


def test_unverified_cannot_claim_wrong_step():
    with pytest.raises(ValidationError):
        Assessment(assessment_id=uuid4(), assessment_status="unverified", first_error_step=1, reason_code="cannot_verify", verification_method="none", validator_version="pending")


def test_eligibility_reason_is_consistent():
    with pytest.raises(ValidationError):
        Eligibility(eligible=True, reason="assisted")


def test_liveness_does_not_require_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    client = TestClient(app)
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 503


def test_database_error_does_not_leak_credentials(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@invalid/db")
    def fail(*args, **kwargs):
        raise psycopg.OperationalError("secret database connection details")
    monkeypatch.setattr("app.main.psycopg.connect", fail)
    response = TestClient(app).get("/health/ready")
    assert response.status_code == 503
    assert "secret" not in response.text
