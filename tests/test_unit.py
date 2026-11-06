import json
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from eraseproof.events import CustomerData, Event
from eraseproof.api import app


def test_event_roundtrip():
    subject = uuid4()
    event = Event(
        event_type="customer.created",
        customer_id=subject,
        correlation_id=uuid4(),
        data=CustomerData(id=subject, name="Synthetic Test", email="test@example.invalid"),
    )
    assert Event.model_validate_json(event.model_dump_json()) == event
    assert json.loads(event.model_dump_json())["version"] == 1


@pytest.mark.parametrize(
    "change",
    [
        {"version": 2},
        {"customer_id": str(uuid4())},
        {"event_type": "order.created"},
        {"unknown": True},
    ],
)
def test_invalid_event(change):
    subject = uuid4()
    data = dict(
        event_type="customer.created",
        customer_id=subject,
        correlation_id=uuid4(),
        data=dict(id=subject, name="Synthetic Test", email="test@example.invalid"),
    )
    with pytest.raises(ValidationError):
        Event.model_validate({**data, **change})


def test_liveness_validation_and_inspection_guard():
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert (
            client.post("/v1/customers", json={"name": "Real", "email": "a@gmail.com"}).status_code
            == 422
        )
        assert client.get(f"/v1/customers/{uuid4()}/propagation").status_code == 403
        assert (
            client.get("/health/live", headers={"X-Correlation-ID": "invalid"}).status_code == 400
        )
        assert "X-Correlation-ID" in client.get("/health/live").headers


def test_compose_boundaries():
    from pathlib import Path
    import yaml

    services = yaml.safe_load(Path("compose.yaml").read_text())["services"]
    for name in ("postgres", "redis", "rabbitmq", "opensearch"):
        assert "ports" not in services[name]
    assert services["migrate"]["command"] == ["python", "-m", "eraseproof.db"]


def test_readiness_reports_unavailable(monkeypatch):
    import eraseproof.api as api
    from contextlib import contextmanager

    @contextmanager
    def unavailable():
        raise OSError("dependency offline")
        yield

    monkeypatch.setattr(api, "connection", unavailable)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"detail": "dependency unavailable"}


def test_customer_api_atomic_intent(monkeypatch):
    """Unit test only: verifies transaction intent, not PostgreSQL durability."""
    from contextlib import contextmanager
    import eraseproof.api as api

    statements = []

    class Transaction:
        def execute(self, query, params):
            statements.append((query, params))

    @contextmanager
    def fake_connection():
        yield Transaction()

    monkeypatch.setattr(api, "connection", fake_connection)
    with TestClient(app) as client:
        response = client.post(
            "/v1/customers", json={"name": "Synthetic Unit", "email": "unit@example.invalid"}
        )
    assert response.status_code == 201
    assert len(statements) == 2
    assert "customer.customers" in statements[0][0]
    assert "delivery.outbox" in statements[1][0]
    assert str(statements[1][1][0]) == response.json()["event_id"]
