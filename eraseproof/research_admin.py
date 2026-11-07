"""Fixed local-harness commands over stdin; never exposed by an HTTP router."""

import json
import os
import sys
from datetime import datetime, timezone
from uuid import UUID
import httpx
import redis
from psycopg.types.json import Jsonb
from eraseproof.config import REDIS_URL, SEARCH_URL
from eraseproof.db import connection


def require_gate() -> None:
    if not (
        os.getenv("APP_ENV") == "demo"
        and os.getenv("ENABLE_TEST_FAULTS") == "1"
        and os.getenv("RESEARCH_ISOLATION_ID", "").startswith("eraseproof-research")
    ):
        raise PermissionError("isolated synthetic harness required")


def command(data: dict) -> dict:
    require_gate()
    operation = data["operation"]
    if operation == "store":
        with connection() as db:
            kind = data["kind"]
            body = data["body"]
            if kind == "experiment":
                db.execute(
                    "INSERT INTO research.experiments(id,state,code_commit,configuration,configuration_digest,environment) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET state=excluded.state,finished_at=%s",
                    (
                        UUID(body["id"]),
                        body["state"],
                        body["code_commit"],
                        Jsonb(body["configuration"]),
                        body["configuration_digest"],
                        Jsonb(body["environment"]),
                        datetime.now(timezone.utc) if body["state"] != "RUNNING" else None,
                    ),
                )
            elif kind == "trial":
                db.execute(
                    "INSERT INTO research.trials(id,experiment_id,logical_key,attempt,scenario_id,seed,state,body) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET state=excluded.state,body=excluded.body,updated_at=now()",
                    (
                        UUID(body["id"]),
                        UUID(body["experiment_id"]),
                        body["logical_key"],
                        body["attempt"],
                        body["scenario_id"],
                        body["seed"],
                        body["status"],
                        Jsonb(body),
                    ),
                )
            else:
                raise ValueError("unknown storage command")
        return {"stored": True}
    if operation == "lease":
        with connection() as db:
            if data["release"]:
                db.execute(
                    "DELETE FROM research.leases WHERE project=%s AND executor_id=%s",
                    (data["project"], UUID(data["executor_id"])),
                )
                return {"released": True}
            row = db.execute(
                "INSERT INTO research.leases(project,experiment_id,executor_id,expires_at) VALUES (%s,%s,%s,now()+interval '300 seconds') ON CONFLICT(project) DO UPDATE SET executor_id=excluded.executor_id,experiment_id=excluded.experiment_id,expires_at=excluded.expires_at WHERE research.leases.expires_at<now() OR research.leases.executor_id=excluded.executor_id RETURNING project",
                (data["project"], UUID(data["experiment_id"]), UUID(data["executor_id"])),
            ).fetchone()
            if not row:
                raise RuntimeError("another experiment owns the project lease")
        return {"acquired": True}
    if operation == "watchdog":
        with connection() as db:
            if data["mode"] == "register":
                db.execute(
                    "INSERT INTO research.fault_leases(project,service,token) VALUES (%s,%s,%s) ON CONFLICT(project,service) DO UPDATE SET token=excluded.token",
                    (data["project"], data["service"], UUID(data["token"])),
                )
                return {"registered": True}
            row = db.execute(
                "DELETE FROM research.fault_leases WHERE project=%s AND service=%s AND token=%s RETURNING token",
                (data["project"], data["service"], UUID(data["token"])),
            ).fetchone()
            return {"owned": bool(row)}
    if operation == "inspect_versions":
        with connection() as db:
            pg = db.execute("SHOW server_version").fetchone()["server_version"]
        with redis.Redis.from_url(REDIS_URL, socket_timeout=2) as r:
            rv = r.info("server")["redis_version"]
        sv = httpx.get(SEARCH_URL, timeout=3).json()["version"]["number"]
        return {"postgres": pg, "redis": rv, "opensearch": sv}
    if operation in ("lock_status", "release_lock"):
        import re

        application = data["application"]
        if not re.fullmatch(r"research-lock-[a-f0-9-]{12}", application):
            raise ValueError("invalid owned lock tag")
        with connection() as db:
            if operation == "lock_status":
                return {
                    "held": db.execute(
                        "SELECT EXISTS(SELECT 1 FROM pg_locks l JOIN pg_stat_activity a ON l.pid=a.pid WHERE a.application_name=%s AND l.relation='customer.customers'::regclass AND l.mode='AccessExclusiveLock' AND l.granted) AS held",
                        (application,),
                    ).fetchone()["held"]
                }
            db.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name=%s",
                (application,),
            )
        return {"released": True}
    if operation == "mutate":
        return mutate(data)
    if operation == "cleanup":
        return cleanup(data)
    if operation == "publish_stale":
        from eraseproof.broker import connect, topology
        import pika

        broker = connect()
        try:
            channel = broker.channel()
            topology(channel)
            for fixture in data["fixtures"]:
                event = {
                    "version": 1,
                    "event_type": "customer.created",
                    "event_id": fixture["stale_event_id"],
                    "occurred_at": "2020-01-01T00:00:00Z",
                    "correlation_id": fixture["correlation_id"],
                    "customer_id": fixture["customer_id"],
                    "data": {
                        "id": fixture["customer_id"],
                        "name": "Synthetic Delayed Event",
                        "email": "stale@example.invalid",
                    },
                }
                for _ in range(2):
                    channel.basic_publish(
                        exchange="events",
                        routing_key="customer.created",
                        body=json.dumps(event),
                        mandatory=True,
                        properties=pika.BasicProperties(delivery_mode=2),
                    )
        finally:
            broker.close()
        return {"confirmed_messages": len(data["fixtures"]) * 2}
    if operation == "transaction_failure":
        import psycopg

        with connection() as db:
            try:
                with db.transaction():
                    db.execute(
                        "INSERT INTO orders.orders(id,customer_id,amount_cents,currency) VALUES (%s,%s,-1,'USD')",
                        (UUID(data["order_id"]), UUID(data["customer_id"])),
                    )
            except psycopg.IntegrityError:
                pass
            else:
                raise AssertionError("constraint failed to reject transaction")
            count = db.execute(
                "SELECT count(*) AS n FROM orders.orders WHERE id=%s", (UUID(data["order_id"]),)
            ).fetchone()["n"]
            assert count == 0
        return {"transaction_rejected": True, "rows_persisted": count}
    raise ValueError("unsupported harness operation")


def mutate(data: dict) -> dict:
    action = data["action"]
    fixtures = data["fixtures"]
    activated = 0
    with connection() as db:
        if action == "order_field":
            db.execute(
                "ALTER TABLE orders.orders ADD COLUMN IF NOT EXISTS benchmark_personal_email text"
            )
        for f in fixtures:
            subject = UUID(f["customer_id"])
            fault = UUID(f["fault_id"])
            if action == "analytics_residue":
                db.execute(
                    "INSERT INTO analytics.events(event_id,customer_id,event_type,payload) VALUES (%s,%s,'customer.created',%s) ON CONFLICT DO NOTHING",
                    (fault, subject, Jsonb({"email": "research@example.invalid"})),
                )
                activated += 1
            elif action == "order_field":
                db.execute(
                    "UPDATE orders.orders SET benchmark_personal_email=%s WHERE id=%s",
                    ("research@example.invalid", UUID(f["order_ids"][0])),
                )
                activated += 1
            elif action == "late_index":
                response = httpx.put(
                    f"{SEARCH_URL}/customers/_doc/research-{fault}",
                    params={"refresh": "wait_for"},
                    json={
                        "customer_id": str(subject),
                        "name": "Synthetic Delayed Legacy Writer",
                        "email": "research@example.invalid",
                    },
                    timeout=5,
                )
                response.raise_for_status()
                activated += 1
            else:
                raise ValueError("unknown mutation")
    return {"activated": activated, "action": action}


def cleanup(data: dict) -> dict:
    fixtures = data["fixtures"]
    with connection() as db, redis.Redis.from_url(REDIS_URL, socket_timeout=3) as cache:
        for f in fixtures:
            subject = UUID(f["customer_id"])
            fault = UUID(f["fault_id"])
            cache.delete(f"customer:{subject}")
            cache.set(f"deletion:customer:{subject}", "1")
            r = httpx.delete(
                f"{SEARCH_URL}/customers/_doc/research-{fault}",
                params={"refresh": "wait_for"},
                timeout=5,
            )
            if r.status_code != 404:
                r.raise_for_status()
            r = httpx.put(
                f"{SEARCH_URL}/customers/_doc/{subject}",
                params={"refresh": "wait_for", "version": 100, "version_type": "external_gte"},
                json={"erased": True},
                timeout=5,
            )
            r.raise_for_status()
            db.execute(
                "DELETE FROM analytics.events WHERE customer_id=%s OR event_id=%s", (subject, fault)
            )
            db.execute(
                "DELETE FROM delivery.outbox WHERE aggregate_id=%s AND event_type IN ('customer.created','order.created')",
                (subject,),
            )
            db.execute("DELETE FROM delivery.processed WHERE customer_id=%s", (subject,))
            db.execute(
                "DELETE FROM orders.orders WHERE customer_id=%s OR id=ANY(%s) OR id IN (SELECT m.order_id FROM deletion.order_manifest m JOIN deletion.requests r ON r.id=m.request_id WHERE r.customer_id=%s)",
                (subject, [UUID(i) for i in f["order_ids"]], subject),
            )
            db.execute("DELETE FROM customer.customers WHERE id=%s", (subject,))
        # This reserved column is created only by the isolated harness. Do not drop unrelated values.
        exists = db.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema='orders' AND table_name='orders' AND column_name='benchmark_personal_email'"
        ).fetchone()
        if exists:
            remaining = db.execute(
                "SELECT count(*) AS n FROM orders.orders WHERE benchmark_personal_email IS NOT NULL"
            ).fetchone()["n"]
            if remaining == 0:
                db.execute("ALTER TABLE orders.orders DROP COLUMN benchmark_personal_email")
    return {"cleaned_fixture_count": len(fixtures)}


if __name__ == "__main__":
    try:
        value = command(json.load(sys.stdin))
        print(json.dumps(value, default=str))
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(1)
