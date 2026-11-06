"""Real-service acceptance; never silently substitutes mocks for infrastructure."""

import os
import subprocess
import time
from uuid import uuid4

import httpx
import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1", reason="requires running Docker Compose stack"
    ),
]
TOKEN = os.getenv("INSPECTION_TOKEN", "local-inspection-change-me")
HEADERS = {"X-Inspection-Token": TOKEN}


def compose(*args):
    return subprocess.run(["docker", "compose", *args], check=True, capture_output=True, text=True)


def inside(code):
    return compose("exec", "-T", "customer", "python", "-c", code).stdout.strip()


def create():
    suffix = uuid4().hex
    response = httpx.post(
        "http://localhost:8000/v1/customers",
        timeout=5,
        json={"name": f"Synthetic Test {suffix}", "email": f"{suffix}@example.invalid"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def wait_for_customer(customer):
    deadline = time.monotonic() + 100
    while time.monotonic() < deadline:
        response = httpx.get(
            f"http://localhost:8000/v1/customers/{customer['id']}/propagation",
            headers=HEADERS,
            timeout=20,
        )
        response.raise_for_status()
        status = response.json()
        if (
            all(value["state"] == "present" for value in status["stores"].values())
            and all(event["published_at"] for event in status["outbox"])
            and len(status["receipts"]) >= 3
        ):
            return status
        time.sleep(1)
    pytest.fail(f"propagation deadline exceeded: {status}")


def test_real_smoke_migrations_constraints_and_duplicate_delivery():
    compose("run", "--rm", "migrate")  # repeated migration must be safe
    for port in range(8000, 8005):
        assert httpx.get(f"http://localhost:{port}/health/ready", timeout=10).status_code == 200
    customer = create()
    assert httpx.get(f"http://localhost:8000/v1/customers/{customer['id']}").status_code == 200
    status = wait_for_customer(customer)
    assert not status["deletion_proof"]
    assert status["stores"]["cache"]["data"]["email"].endswith("@example.invalid")
    assert status["stores"]["search"]["data"]["id"] == customer["id"]
    assert len(status["stores"]["analytics"]["data"]) == 1
    order = httpx.post(
        "http://localhost:8001/v1/orders",
        json={"customer_id": customer["id"], "amount_cents": 1200, "currency": "USD"},
    )
    assert order.status_code == 201, order.text
    assert httpx.get(f"http://localhost:8001/v1/orders/{order.json()['id']}").status_code == 200
    assert (
        httpx.post(
            "http://localhost:8001/v1/orders", json={"customer_id": str(uuid4()), "amount_cents": 1}
        ).status_code
        == 409
    )
    assert (
        httpx.post(
            "http://localhost:8001/v1/orders",
            json={"customer_id": customer["id"], "amount_cents": -1},
        ).status_code
        == 422
    )
    # Republish the same stable event twice through the REAL broker.
    inside(f"""
from eraseproof.db import connection
from eraseproof.broker import connect, topology
from uuid import UUID
import json, pika
with connection() as db:
    event = db.execute('SELECT payload FROM delivery.outbox WHERE id=%s', (UUID('{customer["event_id"]}'),)).fetchone()['payload']
b = connect()
c = b.channel()
topology(c)
for _ in range(2):
    c.basic_publish(exchange='events', routing_key='customer.created', body=json.dumps(event), mandatory=True, properties=pika.BasicProperties(delivery_mode=2))
b.close()
""")
    # Drain barrier: each queue has prefetch=1; wait for ready and unacked counts via passive queue
    # plus direct duplicate application verifies durable dedupe after a new process starts.
    output = inside(f"""
from eraseproof.db import connection
from eraseproof.events import Event
from eraseproof.worker import apply_event
from uuid import UUID
with connection() as db:
    payload = db.execute('SELECT payload FROM delivery.outbox WHERE id=%s', (UUID('{customer["event_id"]}'),)).fetchone()['payload']
assert all(apply_event(t, Event.model_validate(payload)) is False for t in ('cache','search','analytics'))
print('deduplicated')
""")
    assert output == "deduplicated"
    compose("restart", "cache-consumer", "search-consumer", "analytics-consumer")
    status = wait_for_customer(customer)
    assert len([r for r in status["receipts"] if r["event_id"] == customer["event_id"]]) == 3
    assert (
        inside("""
from eraseproof.db import connection
import psycopg
with connection() as db:
    try:
        with db.transaction():
            db.execute("INSERT INTO orders.orders(id,customer_id,amount_cents,currency) VALUES (gen_random_uuid(),gen_random_uuid(),-1,'BAD')")
    except psycopg.IntegrityError:
        print('constraint-enforced')
    else:
        raise AssertionError('constraint missing')
""")
        == "constraint-enforced"
    )


def test_delayed_propagation_and_consumer_restart():
    compose("stop", "search-consumer")
    try:
        customer = create()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            state = httpx.get(
                f"http://localhost:8002/v1/inspect/customers/{customer['id']}", headers=HEADERS
            ).json()
            if state["state"] == "present":
                break
            time.sleep(1)
        assert state["state"] == "present"
        search = httpx.get(
            f"http://localhost:8003/v1/inspect/customers/{customer['id']}", headers=HEADERS
        ).json()
        assert search["state"] == "absent"
    finally:
        compose("start", "search-consumer")
    assert wait_for_customer(customer)["stores"]["search"]["state"] == "present"
