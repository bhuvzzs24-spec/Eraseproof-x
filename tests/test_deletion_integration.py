"""Destructive synthetic fixtures against actual Compose services, never mocks."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
import time
from uuid import uuid4

import httpx
import pytest

from test_integration import compose, inside, create, wait_for_customer

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1", reason="requires running Docker Compose stack"
    ),
]
BASE = "http://localhost:8005/v1/deletions"
HEADERS = {"X-Deletion-Token": os.getenv("DELETION_TOKEN", "")}
INSPECTION = {"X-Inspection-Token": os.getenv("INSPECTION_TOKEN", "local-inspection-change-me")}
TERMINAL = {"COMPLETED_REPORTED", "PARTIALLY_FAILED", "FAILED"}


def submit(customer, key=None):
    response = httpx.post(
        BASE,
        headers=HEADERS,
        json={"customer_id": customer["id"], "idempotency_key": key or uuid4().hex},
        timeout=15,
    )
    assert response.status_code == 202, response.text
    return response.json()


def status(request):
    response = httpx.get(f"{BASE}/{request['id']}", headers=HEADERS, timeout=15)
    response.raise_for_status()
    return response.json()


def wait(request, predicate=lambda r: r["state"] in TERMINAL, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = status(request)
        if predicate(current):
            return current
        time.sleep(0.4)
    pytest.fail(f"deletion timeout: {current}")


def complete(request):
    result = wait(request)
    assert result["state"] == "COMPLETED_REPORTED", result
    assert len(result["tasks"]) == 6
    assert all(t["state"] == "SUCCEEDED_REPORTED" for t in result["tasks"])
    assert not result["independent_verification"]
    return result


def absent(customer):
    assert (
        httpx.get(f"http://localhost:8000/v1/customers/{customer['id']}", timeout=5).status_code
        == 404
    )
    for port in (8002, 8003, 8004):
        response = httpx.get(
            f"http://localhost:{port}/v1/inspect/customers/{customer['id']}",
            headers=INSPECTION,
            timeout=10,
        )
        response.raise_for_status()
        assert response.json()["state"] == "absent", response.text
    result = inside(f"""
from eraseproof.db import connection
from uuid import UUID
with connection() as db:
    subject=UUID('{customer["id"]}')
    assert db.execute('SELECT 1 FROM orders.orders WHERE customer_id=%s',(subject,)).fetchone() is None
    assert db.execute("SELECT 1 FROM delivery.outbox WHERE aggregate_id=%s AND event_type<>'deletion.command'",(subject,)).fetchone() is None
    assert db.execute('SELECT 1 FROM delivery.processed WHERE customer_id=%s',(subject,)).fetchone() is None
print('source-history-absent')
""")
    assert result == "source-history-absent"


def publish(payload, routing_key):
    # Quoted JSON is serialized by Python; no shell interpolation of user content.
    encoded = json.dumps(payload)
    inside(f"""
from eraseproof.broker import connect,topology
import pika
b=connect()
c=b.channel()
topology(c)
c.basic_publish(exchange='events',routing_key={routing_key!r},body={encoded!r},mandatory=True,
                properties=pika.BasicProperties(delivery_mode=2))
b.close()
""")


def test_success_idempotency_audit_and_database_guards():
    compose("run", "--rm", "migrate")
    compose("run", "--rm", "migrate")
    customer = create()
    unrelated = create()
    wait_for_customer(customer)
    order = httpx.post(
        "http://localhost:8001/v1/orders",
        json={"customer_id": customer["id"], "amount_cents": 5500},
        timeout=5,
    )
    assert order.status_code == 201
    key = uuid4().hex
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(lambda _: submit(customer, key), range(6)))
    assert len({r["id"] for r in responses}) == 1
    request = responses[0]
    assert submit(customer)["id"] == request["id"]
    conflict = httpx.post(
        BASE, headers=HEADERS, json={"customer_id": unrelated["id"], "idempotency_key": key}
    )
    assert conflict.status_code == 409
    result = complete(request)
    absent(customer)
    retained = httpx.get(f"http://localhost:8001/v1/orders/{order.json()['id']}").json()
    assert retained["customer_id"] is None and retained["amount_cents"] == 5500
    assert httpx.get(f"http://localhost:8000/v1/customers/{unrelated['id']}").status_code == 200
    assert submit(customer, key)["id"] == request["id"]  # source is gone; replay still works
    assert httpx.post(f"{BASE}/{request['id']}/retry", headers=HEADERS).status_code == 409
    assert (
        httpx.post(
            BASE, json={"customer_id": unrelated["id"], "idempotency_key": uuid4().hex}
        ).status_code
        == 403
    )
    assert (
        httpx.post(
            BASE,
            headers=HEADERS,
            json={"customer_id": str(uuid4()), "idempotency_key": uuid4().hex},
        ).status_code
        == 404
    )
    events = httpx.get(f"{BASE}/{request['id']}/events", headers=HEADERS).json()
    assert [e["sequence"] for e in events] == sorted(e["sequence"] for e in events)
    assert events[0]["to_state"] == "REQUESTED"
    assert any(e["to_state"] == "RUNNING" for e in events)
    assert events[-1]["to_state"] == "COMPLETED_REPORTED"
    assert "@example.invalid" not in json.dumps(events)
    assert (
        httpx.get(
            BASE, headers=HEADERS, params={"state": "COMPLETED_REPORTED", "limit": 1}
        ).status_code
        == 200
    )
    assert httpx.get(BASE + "/metrics", headers=HEADERS).status_code == 200
    # Duplicate success commands traverse the broker but must not add attempts.
    command = json.loads(
        inside(f"""
import json
from eraseproof.db import connection
from uuid import UUID
with connection() as db:
    row=db.execute("SELECT payload FROM delivery.outbox WHERE aggregate_id=%s AND event_type='deletion.command' LIMIT 1",(UUID('{customer["id"]}'),)).fetchone()
print(json.dumps(row['payload']))
""")
    )
    publish(command, "deletion.command")
    publish(command, "deletion.command")
    time.sleep(1)
    assert [t["attempt_count"] for t in status(request)["tasks"]] == [
        t["attempt_count"] for t in result["tasks"]
    ]
    assert (
        inside(f"""
from eraseproof.db import connection
from uuid import UUID
import psycopg
with connection() as db:
    statements=[
      ("UPDATE deletion.tasks SET state='PENDING' WHERE request_id=%s",(UUID('{request["id"]}'),)),
      ("DELETE FROM deletion.events WHERE request_id=%s",(UUID('{request["id"]}'),)),
      ("DELETE FROM deletion.tombstones WHERE customer_id=%s",(UUID('{customer["id"]}'),)),
      ("UPDATE deletion.tombstones SET lifecycle='DELETING' WHERE customer_id=%s",(UUID('{customer["id"]}'),)),
      ("UPDATE deletion.tasks SET attempt_count=-1 WHERE request_id=%s",(UUID('{request["id"]}'),)),
    ]
    for query,args in statements:
        try:
            with db.transaction(): db.execute(query,args)
        except psycopg.IntegrityError: pass
        else: raise AssertionError('database guard missing')
print('guards-enforced')
""")
        == "guards-enforced"
    )


@pytest.mark.parametrize(
    "dependency,target,code",
    [("redis", "cache", "REDIS_UNAVAILABLE"), ("opensearch", "search", "SEARCH_UNAVAILABLE")],
)
def test_temporary_store_outage_recovers_automatically(dependency, target, code):
    customer = create()
    wait_for_customer(customer)
    compose("pause", dependency)
    try:
        request = submit(customer)
        failed = wait(
            request,
            lambda r: any(
                t["target"] == target and t["last_failure_code"] == code for t in r["tasks"]
            ),
        )
        assert failed["state"] != "COMPLETED_REPORTED"
    finally:
        compose("unpause", dependency)
    result = complete(request)
    assert next(t for t in result["tasks"] if t["target"] == target)["attempt_count"] >= 2
    absent(customer)


def test_retry_exhaustion_cannot_report_success_and_manual_recovery():
    customer = create()
    wait_for_customer(customer)
    compose("pause", "redis")
    try:
        request = submit(customer)
        failed = wait(request)
        assert failed["state"] == "PARTIALLY_FAILED"
        task = next(t for t in failed["tasks"] if t["target"] == "cache")
        assert task["state"] == "FAILED_TERMINAL" and task["cycle_attempts"] == 3
        assert all(a["failure_code"] == "REDIS_UNAVAILABLE" for a in task["attempts"])
        assert (
            inside(f"""
from eraseproof.db import connection
from uuid import UUID
import psycopg
with connection() as db:
    try:
        with db.transaction():
            db.execute("UPDATE deletion.requests SET state='COMPLETED_REPORTED' WHERE id=%s",(UUID('{request["id"]}'),))
    except psycopg.IntegrityError: print('premature-success-rejected')
    else: raise AssertionError('premature completion allowed')
""")
            == "premature-success-rejected"
        )
    finally:
        compose("unpause", "redis")
    response = httpx.post(f"{BASE}/{request['id']}/retry", headers=HEADERS)
    assert response.status_code == 202, response.text
    repeated = httpx.post(f"{BASE}/{request['id']}/retry", headers=HEADERS)
    assert repeated.status_code == 202
    result = complete(request)
    assert result["retry_round"] == 1
    assert next(t for t in result["tasks"] if t["target"] == "cache")["attempt_count"] == 4
    absent(customer)


def test_delayed_consumers_and_old_events_cannot_resurrect_data():
    workers = ("cache-consumer", "search-consumer", "analytics-consumer")
    compose("stop", *workers)
    try:
        customer = create()
        original = json.loads(
            inside(f"""
import json
from uuid import UUID
from eraseproof.db import connection
with connection() as db:
    row=db.execute('SELECT payload FROM delivery.outbox WHERE id=%s',(UUID('{customer["event_id"]}'),)).fetchone()
print(json.dumps(row['payload']))
""")
        )
        request = submit(customer)
        complete(request)
        # A new event UUID bypasses receipt deduplication: the tombstone itself must reject it.
        original["event_id"] = str(uuid4())
        publish(original, "customer.created")
        # Future/unsupported updates and revisions fail closed to DLQ; no update API is shipped.
        unsupported = {
            **original,
            "event_type": "customer.updated",
            "event_id": str(uuid4()),
            "version": 2,
        }
        publish(unsupported, "customer.created")
    finally:
        compose("start", *workers)
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        counts = inside("""
import json
from eraseproof.broker import connect,topology
b=connect(); c=b.channel(); topology(c)
print(json.dumps({t:c.queue_declare(queue=t,passive=True).method.message_count for t in ('cache','search','analytics')}))
b.close()
""")
        if all(n == 0 for n in json.loads(counts).values()):
            break
        time.sleep(0.5)
    else:
        pytest.fail("projection queues did not drain")
    # Execute same fresh stale payload directly too, against real stores and DB locks.
    assert (
        inside(f"""
from eraseproof.events import Event
from eraseproof.worker import apply_event
import json
payload=json.loads({json.dumps(original)!r})
assert all(apply_event(t,Event.model_validate(payload)) is False for t in ('cache','search','analytics'))
print('tombstone-rejected')
""")
        == "tombstone-rejected"
    )
    # Test the remote fences themselves, bypassing the SQL check: a request that arrives late
    # cannot restore the profile even after its sender has timed out/restarted.
    assert (
        inside(f"""
from eraseproof.config import REDIS_URL, SEARCH_URL
import redis,httpx
with redis.Redis.from_url(REDIS_URL) as client:
    assert client.eval("if redis.call('EXISTS',KEYS[2])==1 then return 0 end; redis.call('SET',KEYS[1],ARGV[1]); return 1",2,'customer:{customer["id"]}','deletion:customer:{customer["id"]}','stale-profile')==0
response=httpx.put(SEARCH_URL+'/customers/_doc/{customer["id"]}',params={{'version':1,'version_type':'external_gte'}},json={{'name':'Synthetic Stale','email':'late@example.invalid'}},timeout=5)
assert response.status_code==409
raw=httpx.get(SEARCH_URL+'/customers/_doc/{customer["id"]}',timeout=5).json()
assert raw['_source']=={{'erased':True}} and raw['_version']==2
print('remote-fences-enforced')
""")
        == "remote-fences-enforced"
    )
    absent(customer)


def test_outbox_persistence_and_scheduler_restart():
    customer = create()
    wait_for_customer(customer)
    compose("stop", "publisher", "deletion-consumer")
    try:
        request = submit(customer)
        wait(request, lambda r: any(t["state"] == "DISPATCHED" for t in r["tasks"]))
        assert (
            inside(f"""
from eraseproof.db import connection
from uuid import UUID
with connection() as db:
    rows=db.execute("SELECT payload,published_at FROM delivery.outbox WHERE aggregate_id=%s AND event_type='deletion.command'",(UUID('{customer["id"]}'),)).fetchall()
    assert rows and all(r['published_at'] is None for r in rows)
    assert all('data' not in r['payload'] for r in rows)
print('durable-unpublished')
""")
            == "durable-unpublished"
        )
        compose("restart", "deletion-scheduler", "deletion")
    finally:
        compose("start", "publisher", "deletion-consumer")
    complete(request)
    absent(customer)


def test_broker_redelivery_and_worker_crash_recover_leased_attempt():
    customer = create()
    wait_for_customer(customer)
    compose("stop", "deletion-consumer")
    try:
        request = submit(customer)
        wait(request, lambda r: any(t["state"] == "DISPATCHED" for t in r["tasks"]))
        # A real basic_get with manual ack is closed unfinished; the next delivery is redelivered.
        assert (
            inside("""
from eraseproof.broker import connect,topology
import time
b=connect(); c=b.channel(); topology(c)
for _ in range(40):
    method,properties,body=c.basic_get('deletion',auto_ack=False)
    if method: break
    time.sleep(.2)
assert method
b.close()
b=connect(); c=b.channel()
method,properties,body=c.basic_get('deletion',auto_ack=False)
assert method and method.redelivered
b.close()
print('broker-redelivered')
""")
            == "broker-redelivered"
        )
        # Hold the same real DB barrier used by connectors. RUNNING commits before waiting on it.
        compose(
            "exec",
            "-d",
            "customer",
            "python",
            "-c",
            f"""
import time
from uuid import UUID
from eraseproof.db import connection
from eraseproof.lifecycle import subject_lock
with connection() as db:
    subject_lock(db,UUID('{customer["id"]}'))
    time.sleep(15)
""",
        )
        # Confirm lock acquisition rather than depending on an arbitrary startup sleep.
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            held = inside(f"""
from eraseproof.db import connection
with connection() as db:
    print(not db.execute('SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0)) AS held',('{customer["id"]}',)).fetchone()['held'])
""")
            if held == "True":
                break
            time.sleep(0.1)
        assert held == "True"
        compose("start", "deletion-consumer")
        running = wait(
            request, lambda r: any(t["state"] == "RUNNING" for t in r["tasks"]), timeout=15
        )
        assert running["state"] != "COMPLETED_REPORTED"
        compose("kill", "-s", "SIGKILL", "deletion-consumer")
        compose("restart", "deletion-consumer", "deletion-scheduler")
    finally:
        compose("start", "deletion-consumer")
    result = complete(request)
    assert any(a["failure_code"] == "LEASE_EXPIRED" for t in result["tasks"] for a in t["attempts"])
    absent(customer)


def test_concurrent_supported_writes_and_delete_are_serialized():
    customer = create()
    wait_for_customer(customer)

    def write(_):
        return httpx.post(
            "http://localhost:8001/v1/orders",
            timeout=15,
            json={"customer_id": customer["id"], "amount_cents": 100},
        ).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(write, i) for i in range(12)]
        request = submit(customer)
        outcomes = [f.result() for f in futures]
    assert set(outcomes) <= {201, 409}
    complete(request)
    assert write(0) == 409
    # Phase 1 has no profile updates: unsupported writes fail closed, not silently accepted.
    assert (
        httpx.patch(
            f"http://localhost:8000/v1/customers/{customer['id']}",
            json={"name": "Synthetic Changed"},
        ).status_code
        == 405
    )
    absent(customer)
