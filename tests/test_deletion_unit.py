from contextlib import contextmanager
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from eraseproof import deletion, deletion_connectors as connectors
from eraseproof.deletion_api import router
from eraseproof.deletion_models import (
    REQUEST_TRANSITIONS,
    TASK_TRANSITIONS,
    TARGETS,
    DeletionCommand,
    SubmitDeletion,
    RequestState as R,
    TaskState as T,
    aggregate,
    retry_seconds,
    validate_transition,
)


@pytest.mark.parametrize(
    "task,transitions", [(False, REQUEST_TRANSITIONS), (True, TASK_TRANSITIONS)]
)
def test_all_state_edges(task, transitions):
    for old in transitions:
        for new in transitions:
            if old == new or new in transitions[old]:
                validate_transition(old, new, task=task)
            else:
                with pytest.raises(ValueError):
                    validate_transition(old, new, task=task)


@pytest.mark.parametrize(
    "states,current,expected",
    [
        ([T.SUCCEEDED] * 6, R.IN_PROGRESS, R.COMPLETED),
        ([T.SUCCEEDED] * 5 + [T.FAILED], R.RETRYING, R.PARTIAL),
        ([T.FAILED] * 6, R.RETRYING, R.FAILED),
        ([T.SUCCEEDED] * 5 + [T.PENDING], R.IN_PROGRESS, R.IN_PROGRESS),
        ([T.SUCCEEDED] * 5 + [T.RETRY_WAIT], R.IN_PROGRESS, R.RETRYING),
        ([T.PENDING] * 6, R.RETRYING, R.RETRYING),
    ],
)
def test_aggregate_never_prematurely_completes(states, current, expected):
    assert aggregate(states, current) == expected
    with pytest.raises(ValueError):
        aggregate(states[:-1], current)


def test_backoff_and_idempotency_scope():
    assert [retry_seconds(i) for i in range(1, 8)] == [2, 4, 8, 16, 30, 30, 30]
    assert retry_seconds(10000) == 30
    assert deletion.key_hash("request-one") == deletion.key_hash("request-one")
    assert deletion.key_hash("request-one") != deletion.key_hash("request-two")
    assert "request-one" not in deletion.key_hash("request-one")


@pytest.mark.parametrize(
    "change",
    [
        {"customer_id": "invalid"},
        {"idempotency_key": "short"},
        {"idempotency_key": "contains whitespace"},
        {"unknown": "bad"},
    ],
)
def test_request_validation(change):
    with pytest.raises(ValidationError):
        SubmitDeletion.model_validate(
            {"customer_id": str(uuid4()), "idempotency_key": "test-request-123", **change}
        )


def test_authentication_denied_by_default_and_environment(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("DELETION_TOKEN", raising=False)
        assert client.get("/v1/deletions").status_code == 403
        monkeypatch.setenv("DELETION_TOKEN", "a" * 32)
        monkeypatch.setenv("APP_ENV", "production")
        assert (
            client.get("/v1/deletions", headers={"X-Deletion-Token": "a" * 32}).status_code == 403
        )
        monkeypatch.setenv("APP_ENV", "demo")
        assert (
            client.get("/v1/deletions", headers={"X-Deletion-Token": "b" * 32}).status_code == 403
        )
        assert (
            client.post(
                "/v1/deletions", headers={"X-Deletion-Token": "a" * 32}, json={}
            ).status_code
            == 422
        )
        monkeypatch.setenv("DELETION_TOKEN", "short")
        assert client.get("/v1/deletions", headers={"X-Deletion-Token": "short"}).status_code == 403


def test_idempotency_key_conflict_and_existing_result(monkeypatch):
    subject, request_id = uuid4(), uuid4()

    class Result:
        def fetchone(self):
            return {"id": request_id, "customer_id": subject}

    class Database:
        def execute(self, *args):
            return Result()

    @contextmanager
    def fake():
        yield Database()

    monkeypatch.setattr(deletion, "connection", fake)
    monkeypatch.setattr(deletion, "view", lambda db, request_id: {"id": request_id})
    assert deletion.submit(
        SubmitDeletion(customer_id=subject, idempotency_key="same-key-123"), uuid4()
    ) == {"id": request_id}
    with pytest.raises(HTTPException) as exc:
        deletion.submit(
            SubmitDeletion(customer_id=uuid4(), idempotency_key="same-key-123"), uuid4()
        )
    assert exc.value.status_code == 409


def test_stale_generation_or_mismatched_subject_cannot_execute():
    command = DeletionCommand(
        event_id=uuid4(),
        request_id=uuid4(),
        task_id=uuid4(),
        customer_id=uuid4(),
        correlation_id=uuid4(),
        target="cache",
    )
    request = {
        "id": command.request_id,
        "customer_id": command.customer_id,
        "correlation_id": command.correlation_id,
    }
    task = {"request_id": command.request_id, "target": "cache", "active_attempt": command.event_id}
    assert deletion.command_matches(command, request, task)
    assert not deletion.command_matches(command, request, {**task, "active_attempt": uuid4()})
    assert not deletion.command_matches(command, {**request, "customer_id": uuid4()}, task)


@pytest.mark.parametrize("target", TARGETS)
def test_connector_performs_real_operation_interface(monkeypatch, target):
    calls = []

    class Database:
        def execute(self, query, params):
            calls.append((query, params))

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def eval(self, script, count, key, barrier):
            calls.append(("redis.eval", (key, barrier)))

    monkeypatch.setattr(connectors.redis.Redis, "from_url", lambda *a, **k: Client())

    def search(url, **kwargs):
        calls.append(("http.put", url))
        return httpx.Response(200, request=httpx.Request("PUT", url))

    monkeypatch.setattr(connectors.httpx, "put", search)
    subject = uuid4()
    connectors.delete_target(Database(), target, subject)
    assert calls
    assert all(str(subject) in str(params) for _, params in calls)


def test_connector_errors_never_become_success(monkeypatch):
    def unavailable(*args, **kwargs):
        raise connectors.redis.ConnectionError()

    monkeypatch.setattr(connectors.redis.Redis, "from_url", unavailable)
    with pytest.raises(connectors.ConnectorFailure) as exc:
        connectors.delete_target(None, "cache", uuid4())
    assert exc.value.code == "REDIS_UNAVAILABLE" and exc.value.retryable
    with pytest.raises(connectors.ConnectorFailure) as exc:
        connectors.delete_target(None, "arbitrary-object", uuid4())
    assert exc.value.code == "UNSUPPORTED_TARGET" and not exc.value.retryable


def test_failed_attempt_exhaustion_and_due_time(monkeypatch):
    calls = []

    class Database:
        def execute(self, *args):
            calls.append(args)

    task = {
        "id": uuid4(),
        "target": "cache",
        "state": T.RUNNING,
        "cycle_attempts": 3,
        "max_attempts": 3,
        "active_attempt": uuid4(),
    }
    request = {"id": uuid4(), "correlation_id": uuid4()}
    before = deletion.now()
    deletion.fail_attempt(Database(), request, task, "REDIS_UNAVAILABLE")
    assert task["state"] == T.FAILED
    assert task["next_attempt_at"] > before
    assert any("UPDATE deletion.attempts" in call[0] for call in calls)
