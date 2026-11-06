"""Control-flow tests only. Real durability/acknowledgment tests require Compose."""

from contextlib import contextmanager
from uuid import uuid4

import pytest

from eraseproof.events import CustomerData, Event
from eraseproof import worker


def event():
    subject = uuid4()
    return Event(
        event_type="customer.created",
        customer_id=subject,
        correlation_id=uuid4(),
        data=CustomerData(id=subject, name="Synthetic Delivery", email="delivery@example.invalid"),
    )


@pytest.mark.parametrize("fail", [False, True])
def test_outbox_marks_published_only_after_confirmation(monkeypatch, fail):
    original = event()
    operations = []

    class Result:
        def fetchone(self):
            return {
                "id": original.event_id,
                "event_type": original.event_type,
                "payload": original.model_dump(mode="json"),
            }

    class Database:
        def execute(self, query, params=None):
            operations.append(query)
            return Result()

    @contextmanager
    def database():
        yield Database()

    class Channel:
        def basic_publish(self, **kwargs):
            assert kwargs["mandatory"]
            assert kwargs["properties"].delivery_mode == 2
            assert kwargs["properties"].message_id == str(original.event_id)
            operations.append("confirm")
            if fail:
                raise RuntimeError("broker rejected publication")

    class Broker:
        def channel(self):
            return Channel()

        def close(self):
            operations.append("close")

    monkeypatch.setattr(worker, "connection", database)
    monkeypatch.setattr(worker, "connect", Broker)
    monkeypatch.setattr(worker, "topology", lambda channel: None)
    assert worker.publish_once() is not fail
    updates = [q for q in operations if q.startswith("UPDATE")]
    assert len(updates) == 1
    assert ("published_at=now()" in updates[0]) is not fail
    assert operations.index("confirm") < operations.index(updates[0])


def test_durable_receipt_short_circuits_external_side_effect(monkeypatch):
    operations = []

    class Result:
        def fetchone(self):
            return {"exists": 1}

    class Database:
        def execute(self, query, params=None):
            operations.append(query)
            return Result()

    @contextmanager
    def database():
        yield Database()

    def unexpected(*args, **kwargs):
        raise AssertionError("duplicate must not write external store")

    monkeypatch.setattr(worker, "connection", database)
    monkeypatch.setattr(worker.redis.Redis, "from_url", unexpected)
    assert worker.apply_event("cache", event()) is False
    assert len(operations) == 2
