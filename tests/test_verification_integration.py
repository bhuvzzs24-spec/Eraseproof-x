"""Real reads and gated administrative synthetic faults. No verification outcomes are mocked."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import httpx
import pytest

from eraseproof.evaluation import summarize
from eraseproof.evidence import validate_chain
from test_integration import compose, inside, create, wait_for_customer
from test_deletion_integration import submit, complete, status as deletion_status, publish

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1" or os.getenv("ERASEPROOF_TEST_FAULTS") != "1",
        reason="requires actual Compose services and explicit synthetic-fault opt-in",
    ),
]
BASE = "http://localhost:8006/v1"
HEADERS = {"X-Verification-Token": os.getenv("VERIFICATION_TOKEN", "")}
CASES = []


def verified_request(with_order=False):
    customer = create()
    wait_for_customer(customer)
    order = None
    if with_order:
        response = httpx.post(
            "http://localhost:8001/v1/orders",
            json={"customer_id": customer["id"], "amount_cents": 2222},
            timeout=10,
        )
        response.raise_for_status()
        order = response.json()
    request = submit(customer)
    complete(request)
    return customer, request, order


def start(request, key=None):
    response = httpx.post(
        f"{BASE}/deletions/{request['id']}/verifications",
        headers=HEADERS,
        json={"idempotency_key": key or uuid4().hex},
        timeout=15,
    )
    assert response.status_code == 202, response.text
    return response.json()


def get(run):
    response = httpx.get(f"{BASE}/verifications/{run['id']}", headers=HEADERS, timeout=15)
    response.raise_for_status()
    return response.json()


def wait(run, predicate=lambda r: r["state"] == "FINISHED", timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = get(run)
        if predicate(value):
            return value
        time.sleep(0.3)
    pytest.fail(f"verification did not reach expected state: {value}")


def report(run):
    response = httpx.get(f"{BASE}/verifications/{run['id']}/report", headers=HEADERS, timeout=15)
    response.raise_for_status()
    value = response.json()
    assert value["evidence_integrity"]["valid"] and validate_chain(value["evidence"])
    assert "@example.invalid" not in json.dumps(value)
    return value


def record(name, run, truth, reported="COMPLETED_REPORTED"):
    value = report(run)
    current = value["verification"]
    observations = [r["body"] for r in value["evidence"]]
    case = {
        "scenario": name,
        "run_id": run["id"],
        "ground_truth_residual": truth,
        "reported_state": reported,
        "result": current["result"],
        "time_to_verification_seconds": (
            datetime.fromisoformat(current["finished_at"])
            - datetime.fromisoformat(current["created_at"])
        ).total_seconds(),
        "checked_targets": sorted(
            {
                o["target"]
                for o in observations
                if o["adapter"].startswith("independent.") and o["query_count"] > 0
            }
        ),
        "probe_queries": sum(o["query_count"] for o in observations),
        "probe_duration_ms": sum(o["duration_ms"] for o in observations),
    }
    CASES.append(case)
    Path("work/reports").mkdir(parents=True, exist_ok=True)
    Path(f"work/reports/{name}.json").write_text(json.dumps(value, indent=2) + "\n")
    Path("work/phase3-evaluation.json").write_text(
        json.dumps(
            {
                "configuration": {
                    "scope_policy": "policies/scope-v1.json",
                    "faults": "administrative synthetic fixtures explicitly enabled",
                    "infrastructure": "Docker Compose actual PostgreSQL Redis OpenSearch RabbitMQ",
                    "random_fixture_seed": "UUIDs recorded per run; fault schedule is deterministic",
                },
                "summary": summarize(CASES),
                "cases": CASES,
            },
            indent=2,
        )
        + "\n"
    )
    return value


def test_normal_deletion_safe_markers_and_read_only_permissions():
    customer, request, order = verified_request(with_order=True)
    run = start(request)
    final = wait(run)
    assert final["result"] == "VERIFIED_ABSENT"
    assert all(t["result"] == "VERIFIED_ABSENT" for t in final["targets"])
    value = record("normal-and-permitted-markers", run, False)
    assert any(
        r["body"]["summary"].get("permitted_markers") == 1
        for r in value["evidence"]
        if r["target"] == "search"
    )
    # The probe's credentials genuinely cannot write; coordinator cannot read profile rows or publish deletion work.
    result = compose(
        "exec",
        "-T",
        "verification-worker",
        "python",
        "-c",
        """
from eraseproof.verification_adapters import read_db
from eraseproof.db import connection
from uuid import uuid4
import os,redis,psycopg
with read_db() as db:
    try: db.execute('DELETE FROM customer.customers WHERE false')
    except psycopg.Error: pass
    else: raise AssertionError('probe write allowed')
with connection() as db:
    for query in ('SELECT * FROM customer.customers LIMIT 1', 'DELETE FROM analytics.events WHERE false'):
        try:
            with db.transaction():db.execute(query)
        except psycopg.Error:pass
        else:raise AssertionError('coordinator crossed store boundary')
    try:
        with db.transaction():
            db.execute("INSERT INTO delivery.outbox(id,aggregate_id,event_type,payload) VALUES (%s,%s,'deletion.command','{}')",(uuid4(),uuid4()))
    except psycopg.Error:pass
    else:raise AssertionError('destructive publication allowed')
with redis.Redis.from_url(os.environ['VERIFIER_REDIS_URL']) as client:
    try:client.set('customer:permission-test','forbidden')
    except redis.exceptions.NoPermissionError:pass
    else:raise AssertionError('Redis write allowed')
print('read-only-enforced')
""",
    ).stdout.strip()
    assert result == "read-only-enforced"
    retained = httpx.get(f"http://localhost:8001/v1/orders/{order['id']}").json()
    assert retained["customer_id"] is None and retained["amount_cents"] == 2222
    assert (
        httpx.get(
            f"{BASE}/verifications/{run['id']}",
            headers={"X-Deletion-Token": os.getenv("DELETION_TOKEN", "")},
        ).status_code
        == 403
    )
    assert (
        httpx.get(f"{BASE}/deletions/{request['id']}/verifications", headers=HEADERS).status_code
        == 200
    )
    assert (
        httpx.get(f"{BASE}/verifications/{run['id']}/timeline", headers=HEADERS).status_code == 200
    )
    assert (
        inside(f"""
from eraseproof.db import connection
from uuid import UUID
import psycopg
with connection() as db:
    for query in ("UPDATE verification.evidence SET digest=repeat('0',64) WHERE run_id=%s", "DELETE FROM verification.timeline WHERE run_id=%s"):
        try:
            with db.transaction():db.execute(query,(UUID('{run["id"]}'),))
        except psycopg.IntegrityError:pass
        else:raise AssertionError('evidence mutation allowed')
print('append-only-enforced')
""")
        == "append-only-enforced"
    )


@pytest.mark.parametrize(
    "target", ["search", "cache", "analytics", "orders", "customer", "event_history"]
)
def test_real_residue_after_reported_success(target):
    customer, request, order = verified_request(with_order=target == "orders")
    fault_id = uuid4()
    subject = customer["id"]
    try:
        inside(f"""
from eraseproof.db import connection
from eraseproof.config import REDIS_URL,SEARCH_URL
from psycopg.types.json import Jsonb
from uuid import UUID
import httpx,redis,json
subject=UUID('{subject}');fault=UUID('{fault_id}');target={target!r}
if target=='search':
    r=httpx.put(SEARCH_URL+'/customers/_doc/fault-'+str(fault),params={{'refresh':'wait_for'}},json={{'customer_id':str(subject),'name':'Synthetic Residue','email':'residue@example.invalid'}},timeout=5);r.raise_for_status()
elif target=='cache':
    with redis.Redis.from_url(REDIS_URL) as client:client.set('customer:'+str(subject)+':summary',json.dumps({{'email':'residue@example.invalid'}}))
else:
    with connection() as db:
        if target=='analytics':db.execute("INSERT INTO analytics.events(event_id,customer_id,event_type,payload) VALUES (%s,%s,'customer.created',%s)",(fault,subject,Jsonb({{'email':'residue@example.invalid'}})))
        elif target=='orders':
            db.execute('ALTER TABLE orders.orders ADD COLUMN customer_email text')
            db.execute('UPDATE orders.orders SET customer_email=%s WHERE id=%s',('residue@example.invalid',UUID('{order["id"] if order else uuid4()}')))
        elif target=='customer':db.execute('INSERT INTO customer.customers(id,name,email) VALUES (%s,%s,%s)',(subject,'Synthetic Residue','residue@example.invalid'))
        elif target=='event_history':db.execute("INSERT INTO delivery.outbox(id,aggregate_id,event_type,payload) VALUES (%s,%s,'customer.created',%s)",(fault,subject,Jsonb({{'customer_id':str(subject),'data':{{'email':'residue@example.invalid'}}}})))
""")
        run = start(request)
        final = wait(run)
        assert final["result"] == "FALSE_SUCCESS_DETECTED", final
        assert (
            next(t for t in final["targets"] if t["target"] == target)["result"]
            == "RESIDUAL_DATA_DETECTED"
        )
        value = record("residual-" + target, run, True)
        assert any(
            f["target"] == target
            and f["false_success"]
            and f["task_metadata"]["state"] == "SUCCEEDED_REPORTED"
            for f in value["findings"]
        )
        # Probe-only execution leaves the actual fault in place (repeat run still detects it).
        assert deletion_status(request)["state"] == "COMPLETED_REPORTED"
        assert (
            inside(f"""
from eraseproof.db import connection
from eraseproof.config import REDIS_URL,SEARCH_URL
from uuid import UUID
import redis,httpx
subject=UUID('{subject}');fault=UUID('{fault_id}');target={target!r}
if target=='search':
    response=httpx.get(SEARCH_URL+'/customers/_doc/fault-'+str(fault),timeout=5)
    assert response.status_code==200 and 'email' in response.json()['_source']
elif target=='cache':
    with redis.Redis.from_url(REDIS_URL) as client:assert client.exists('customer:'+str(subject)+':summary')==1
else:
    with connection() as db:
        if target=='analytics':row=db.execute('SELECT 1 FROM analytics.events WHERE event_id=%s',(fault,)).fetchone()
        elif target=='orders':row=db.execute('SELECT 1 FROM orders.orders WHERE id=%s AND customer_email IS NOT NULL',(UUID('{order["id"] if order else uuid4()}'),)).fetchone()
        elif target=='customer':row=db.execute('SELECT 1 FROM customer.customers WHERE id=%s',(subject,)).fetchone()
        else:row=db.execute('SELECT 1 FROM delivery.outbox WHERE id=%s',(fault,)).fetchone()
        assert row is not None
print('residual-preserved')
""")
            == "residual-preserved"
        )
    finally:
        inside(f"""
from eraseproof.db import connection
from eraseproof.config import REDIS_URL,SEARCH_URL
from uuid import UUID
import redis,httpx
subject=UUID('{subject}');fault=UUID('{fault_id}');target={target!r}
if target=='search':httpx.delete(SEARCH_URL+'/customers/_doc/fault-'+str(fault),params={{'refresh':'wait_for'}},timeout=5).raise_for_status()
elif target=='cache':
    with redis.Redis.from_url(REDIS_URL) as client:client.delete('customer:'+str(subject)+':summary')
else:
    with connection() as db:
        if target=='analytics':db.execute('DELETE FROM analytics.events WHERE event_id=%s',(fault,))
        elif target=='orders':db.execute('ALTER TABLE orders.orders DROP COLUMN IF EXISTS customer_email')
        elif target=='customer':db.execute('DELETE FROM customer.customers WHERE id=%s',(subject,))
        elif target=='event_history':db.execute('DELETE FROM delivery.outbox WHERE id=%s',(fault,))
""")


def test_verification_outage_is_inconclusive_and_rerun_recovers():
    customer, request, _ = verified_request()
    compose("pause", "redis")
    try:
        run = start(request)
        final = wait(run)
        assert final["result"] == "INCONCLUSIVE"
        assert (
            next(t for t in final["targets"] if t["target"] == "cache")["result"] == "INCONCLUSIVE"
        )
        record("verification-outage", run, False)
    finally:
        compose("unpause", "redis")
    recovered = start(request)
    assert wait(recovered)["result"] == "VERIFIED_ABSENT"
    record("verification-outage-recovered", recovered, False)


def test_pending_consistency_then_actual_absence():
    customer = create()
    wait_for_customer(customer)
    compose("stop", "deletion-consumer")
    try:
        request = submit(customer)
        run = start(request)
        observed = wait(run, lambda r: r["state"] == "WAITING" and r["round_no"] >= 1)
        assert observed["result"] == "PENDING_CONSISTENCY"
    finally:
        compose("start", "deletion-consumer")
    complete(request)
    assert wait(run)["result"] == "VERIFIED_ABSENT"
    record("pending-then-converged", run, False)


def test_later_run_detects_reappearance_and_preserves_prior_report():
    customer, request, _ = verified_request()
    first = start(request)
    assert wait(first)["result"] == "VERIFIED_ABSENT"
    initial = record("before-reappearance", first, False)
    try:
        inside(f"""
import redis
from eraseproof.config import REDIS_URL
with redis.Redis.from_url(REDIS_URL) as client:client.set('customer:{customer["id"]}','synthetic-residual-value')
""")
        later = start(request)
        assert wait(later)["result"] == "FALSE_SUCCESS_DETECTED"
        record("late-reappearance", later, True)
        assert report(first)["evidence"] == initial["evidence"]
    finally:
        inside(f"""
import redis
from eraseproof.config import REDIS_URL
with redis.Redis.from_url(REDIS_URL) as client:client.delete('customer:{customer["id"]}')
""")
    last = start(request)
    assert wait(last)["result"] == "VERIFIED_ABSENT"
    record("after-separate-remediation", last, False)


def test_required_missing_adapter_is_unsupported_with_real_remaining_probes():
    customer, request, _ = verified_request()
    compose("stop", "verification-worker")
    try:
        run = start(request)
        compose(
            "run",
            "--rm",
            "--no-deps",
            "-e",
            "ENABLE_TEST_FAULTS=1",
            "-e",
            "VERIFICATION_TEST_DISABLE_ADAPTERS=search",
            "verification-worker",
            "python",
            "-c",
            f"""
import time
from uuid import UUID
from eraseproof.db import connection
from eraseproof.verification_models import VerificationCommand
from eraseproof.verification import execute
for _ in range(40):
    with connection() as db:r=db.execute('SELECT * FROM verification.runs WHERE id=%s',(UUID('{run["id"]}'),)).fetchone()
    if r['state']=='RUNNING':
        execute(VerificationCommand(event_id=r['active_message'],run_id=r['id'],round_no=r['round_no']));break
    time.sleep(.5)
else:raise AssertionError('verification dispatch missing')
""",
        )
        final = wait(run)
        assert final["result"] == "UNSUPPORTED"
        value = record("missing-required-adapter", run, False)
        assert "search" in value["incomplete_targets"]
    finally:
        compose("start", "verification-worker")


def test_concurrent_runs_idempotent_submission_and_duplicate_delivery():
    customer, request, _ = verified_request()
    key = uuid4().hex
    with ThreadPoolExecutor(max_workers=4) as pool:
        runs = list(pool.map(lambda _: start(request, key), range(4)))
    assert len({r["id"] for r in runs}) == 1
    other = start(request)
    assert other["id"] != runs[0]["id"]
    for run in (runs[0], other):
        assert wait(run)["result"] == "VERIFIED_ABSENT"
    before = record("concurrent-idempotent-runs", runs[0], False)
    payload = json.loads(
        inside(f"""
import json
from eraseproof.db import connection
with connection() as db:r=db.execute("SELECT payload FROM delivery.outbox WHERE event_type='verification.command' AND payload->>'run_id'=%s LIMIT 1",('{runs[0]["id"]}',)).fetchone()
print(json.dumps(r['payload']))
""")
    )
    publish(payload, "verification.command")
    publish(payload, "verification.command")
    time.sleep(1)
    assert report(runs[0])["evidence"] == before["evidence"]


def test_worker_kill_and_restart_does_not_fabricate_results():
    customer, request, _ = verified_request()
    compose(
        "exec",
        "-d",
        "customer",
        "python",
        "-c",
        """
import psycopg,time
from eraseproof.config import DATABASE_URL
with psycopg.connect(DATABASE_URL,application_name='verification-crash-fixture') as db:
    db.execute('LOCK TABLE customer.customers IN ACCESS EXCLUSIVE MODE')
    time.sleep(20)
""",
    )
    lock_deadline = time.monotonic() + 10
    while time.monotonic() < lock_deadline:
        held = inside("""
from eraseproof.db import connection
with connection() as db:
    print(db.execute("SELECT EXISTS(SELECT 1 FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid WHERE a.application_name='verification-crash-fixture' AND l.relation='customer.customers'::regclass AND l.mode='AccessExclusiveLock' AND l.granted) AS held").fetchone()['held'])
""")
        if held == "True":
            break
        time.sleep(0.1)
    assert held == "True"
    run = start(request)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            events = httpx.get(
                f"{BASE}/verifications/{run['id']}/timeline", headers=HEADERS
            ).json()["items"]
            if any(e["kind"] == "verification.probing" for e in events):
                break
            time.sleep(0.1)
        else:
            pytest.fail("worker did not start independent probes")
        assert get(run)["state"] != "FINISHED"
        compose("kill", "-s", "SIGKILL", "verification-worker")
    finally:
        inside("""
from eraseproof.db import connection
with connection() as db:db.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name='verification-crash-fixture'")
""")
        compose("restart", "verification-worker")
    assert wait(run)["result"] == "VERIFIED_ABSENT"
    record("verification-worker-crash", run, False)


def test_partial_failure_residue_is_not_false_total_success():
    customer = create()
    wait_for_customer(customer)
    compose("pause", "redis")
    try:
        request = submit(customer)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            r = deletion_status(request)
            if r["state"] == "PARTIALLY_FAILED":
                break
            time.sleep(0.5)
        else:
            pytest.fail("expected actual deletion target failure")
    finally:
        compose("unpause", "redis")
    try:
        run = start(request)
        assert wait(run)["result"] == "RESIDUAL_DATA_DETECTED"
        value = record("partial-failure-residue", run, True, "PARTIALLY_FAILED")
        assert all(not f["false_success"] for f in value["findings"])
    finally:
        response = httpx.post(
            "http://localhost:8005/v1/deletions/" + request["id"] + "/retry",
            headers={"X-Deletion-Token": os.getenv("DELETION_TOKEN", "")},
        )
        response.raise_for_status()
        complete(request)
