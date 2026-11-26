"""PostgreSQL integration tests for session idempotency and checkpoints.

Set RUN_DB_TESTS=1 and DATABASE_URL to run against an isolated temporary schema.
Only synthetic demo profiles and seeded curriculum content are used.
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.db import connect  # noqa: E402
from app.main import app  # noqa: E402
from app.manage import migrate, seed  # noqa: E402

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="PostgreSQL integration requires RUN_DB_TESTS=1",
)


@pytest.fixture(scope="module", autouse=True)
def isolated_database():
    schema = "test_backend_" + uuid4().hex
    environment_keys = (
        "PGOPTIONS", "DEMO_MODE", "TUTOR_ENABLED", "LLM_ENABLED",
        "VALIDATOR_TIMEOUT_SECONDS",
    )
    previous = {key: os.getenv(key) for key in environment_keys}
    with connect() as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    os.environ.update(
        PGOPTIONS=f"-c search_path={schema}",
        DEMO_MODE="true",
        TUTOR_ENABLED="true",
        LLM_ENABLED="false",
        VALIDATOR_TIMEOUT_SECONDS="2.75",
    )
    try:
        with connect() as connection:
            migrate(connection)
            seed(connection)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        with connect() as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def learner():
    student = "TEST-" + uuid4().hex
    with connect() as connection:
        connection.execute(
            "INSERT INTO profiles(student_id,display_name) VALUES (%s,%s)",
            (student, "Synthetic concurrency test"),
        )
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/demo/login", json={"demo_profile_id": student}
        )
        assert login.status_code == 200, login.text
        yield client, {"Authorization": "Bearer " + login.json()["access_token"]}, student


def create_session(client, headers, student):
    response = client.post(
        "/api/v1/sessions",
        headers=headers,
        json={
            "request_id": str(uuid4()),
            "demo_profile_id": student,
            "topic_id": "TOPIC-LINEAR-01",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_simultaneous_replay_commits_one_turn_and_one_bkt_observation(learner, monkeypatch):
    client, headers, student = learner
    session = create_session(client, headers, student)
    request_id = str(uuid4())
    body = {
        "request_id": request_id,
        "opportunity_id": session["current_opportunity_id"],
        "expected_state_version": session["state_version"],
        "action": "submit",
        "steps": ["x=5"],
    }
    url = f"/api/v1/sessions/{session['session_id']}/turns"

    def send(_):
        with TestClient(app) as concurrent_client:
            return concurrent_client.post(url, headers=headers, json=body)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(send, range(2)))

    successful = [response for response in responses if response.status_code == 200]
    assert successful, [response.text for response in responses]
    assert all(response.status_code in (200, 503) for response in responses)
    from app import tutor

    def validator_must_not_run(*args, **kwargs):
        raise AssertionError("Committed idempotent replay must use its saved response")

    monkeypatch.setattr(tutor, "run_graph", validator_must_not_run)
    replay = client.post(url, headers=headers, json=body)
    assert replay.status_code == 200, replay.text
    assert replay.json() == successful[0].json()
    assert len(replay.json()["session"]["turns"]) == 1

    with connect() as connection:
        assert connection.execute(
            "SELECT count(*) AS n FROM turns WHERE session_id=%s AND request_id=%s",
            (session["session_id"], request_id),
        ).fetchone()["n"] == 1
        assert connection.execute(
            "SELECT count(*) AS n FROM observations WHERE opportunity_id=%s",
            (session["current_opportunity_id"],),
        ).fetchone()["n"] == 1
        assert connection.execute(
            "SELECT count(*) AS n FROM mastery_history h JOIN observations o USING(observation_id) "
            "WHERE o.opportunity_id=%s",
            (session["current_opportunity_id"],),
        ).fetchone()["n"] == 1
        state = connection.execute(
            "SELECT evidence_count FROM knowledge_states WHERE student_id=%s",
            (student,),
        ).fetchone()
        assert state["evidence_count"] == 1

    report = client.get(f"/api/v1/sessions/{session['session_id']}/report", headers=headers)
    assert report.status_code == 200, report.text
    skill = report.json()["mastery"][0]
    assert skill["evidence_count"] == 1
    assert skill["status"] == "insufficient_data"


def test_distinct_concurrent_mutations_cannot_overwrite_one_session_version(learner):
    client, headers, student = learner
    session = create_session(client, headers, student)
    url = f"/api/v1/sessions/{session['session_id']}/turns"
    payloads = [
        {
            "request_id": str(uuid4()),
            "opportunity_id": session["current_opportunity_id"],
            "expected_state_version": session["state_version"],
            "action": "submit",
            "steps": [step],
        }
        for step in ("x=5", "x=9")
    ]

    def send(payload):
        with TestClient(app) as concurrent_client:
            return concurrent_client.post(url, headers=headers, json=payload)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(send, payloads))
    assert sorted(response.status_code for response in responses) == [200, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert conflict.json()["code"] == "state_conflict"
    with connect() as connection:
        assert connection.execute(
            "SELECT count(*) AS n FROM turns WHERE session_id=%s",
            (session["session_id"],),
        ).fetchone()["n"] == 1
        assert connection.execute(
            "SELECT count(*) AS n FROM observations WHERE opportunity_id=%s",
            (session["current_opportunity_id"],),
        ).fetchone()["n"] == 1
        assert connection.execute(
            "SELECT evidence_count FROM knowledge_states WHERE student_id=%s",
            (student,),
        ).fetchone()["evidence_count"] == 1
        assert connection.execute(
            "SELECT state_version FROM sessions WHERE session_id=%s",
            (session["session_id"],),
        ).fetchone()["state_version"] == session["state_version"] + 1


def test_header_request_id_and_pause_resume_checkpoint_restore(learner):
    client, headers, student = learner
    session = create_session(client, headers, student)
    turn_id = str(uuid4())
    turn_body = {
        "opportunity_id": session["current_opportunity_id"],
        "expected_state_version": session["state_version"],
        "action": "request_hint",
        "steps": [],
    }
    url = f"/api/v1/sessions/{session['session_id']}/turns"
    conflict = client.post(
        url,
        headers={**headers, "Idempotency-Key": turn_id},
        json={**turn_body, "request_id": str(uuid4())},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_conflict"
    result = client.post(url, headers={**headers, "Idempotency-Key": turn_id}, json=turn_body)
    assert result.status_code == 200, result.text
    assert result.json()["session"]["hint_level"] == 1
    replay = client.post(url, headers={**headers, "Idempotency-Key": turn_id}, json=turn_body)
    assert replay.status_code == 200 and replay.json() == result.json()

    current = result.json()["session"]
    draft = "  progress is durable  "
    saved = client.put(
        f"/api/v1/sessions/{session['session_id']}/draft",
        headers=headers,
        json={
            "request_id": str(uuid4()),
            "expected_state_version": current["state_version"],
            "draft": draft,
        },
    )
    assert saved.status_code == 200, saved.text
    current = saved.json()
    turn_count = len(current["turns"])
    paused = client.post(
        f"/api/v1/sessions/{session['session_id']}/pause",
        headers=headers,
        json={"request_id": str(uuid4()), "expected_state_version": current["state_version"]},
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "paused"

    with connect() as connection:
        checkpoint = connection.execute(
            "SELECT state_version,snapshot FROM session_checkpoints WHERE session_id=%s",
            (session["session_id"],),
        ).fetchone()
        assert checkpoint["state_version"] == paused.json()["state_version"]
        assert checkpoint["snapshot"]["draft"] == draft
        assert checkpoint["snapshot"]["assistance_level"] == 1
        connection.execute(
            "UPDATE opportunities SET draft='',assistance_level=0 WHERE opportunity_id=%s",
            (session["current_opportunity_id"],),
        )

    resumed = client.post(
        f"/api/v1/sessions/{session['session_id']}/resume",
        headers=headers,
        json={"request_id": str(uuid4()), "expected_state_version": paused.json()["state_version"]},
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == "active"
    assert resumed.json()["draft"] == draft
    assert resumed.json()["hint_level"] == 1
    assert len(resumed.json()["turns"]) == turn_count
