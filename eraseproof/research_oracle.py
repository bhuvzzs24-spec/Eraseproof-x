"""Independent fixture oracle: no evaluated adapters, verdicts, reports or fault labels imported."""

import json
import sys
import time
from uuid import UUID
import httpx
import redis
from redis.retry import Retry
from redis.backoff import NoBackoff
from eraseproof.config import REDIS_URL, SEARCH_URL
from eraseproof.db import connection
from eraseproof.research_admin import require_gate

STORES = ("customer", "orders", "cache", "search", "analytics", "event_history")


def inspect_target(target: str, fixture: dict) -> dict:
    subject = UUID(fixture["customer_id"])
    fault = UUID(fixture["fault_id"])
    found = 0
    retained = 0
    if target == "cache":
        with redis.Redis.from_url(
            REDIS_URL, socket_timeout=1, socket_connect_timeout=1, retry=Retry(NoBackoff(), 0)
        ) as client:
            for key in (f"customer:{subject}", f"customer:{subject}:summary"):
                if client.exists(key):
                    found += 1
            marker = client.get(f"deletion:customer:{subject}")
            retained = int(marker == b"1")
            if marker not in (None, b"1"):
                found += 1
    elif target == "search":
        for identifier in (str(subject), f"research-{fault}"):
            response = httpx.get(f"{SEARCH_URL}/customers/_doc/{identifier}", timeout=2)
            if response.status_code == 404:
                continue
            response.raise_for_status()
            doc = response.json()
            value = doc.get("_source", {})
            marker = (
                identifier == str(subject)
                and list(value) == ["erased"]
                and value["erased"] is True
                and doc.get("_version", 0) >= 2
            )
            if marker:
                retained += 1
            else:
                found += 1
    else:
        with connection() as db:
            db.execute("SET LOCAL statement_timeout='2500ms'")
            if target == "customer":
                found = db.execute(
                    "SELECT count(*) AS n FROM customer.customers WHERE id=%s", (subject,)
                ).fetchone()["n"]
            elif target == "orders":
                rows = db.execute(
                    "SELECT to_jsonb(o) AS row FROM orders.orders o WHERE customer_id=%s OR id=ANY(%s)",
                    (subject, [UUID(i) for i in fixture["order_ids"]]),
                ).fetchall()
                for item in rows:
                    row = item["row"]
                    forbidden = row.get("customer_id") is not None
                    forbidden |= any(
                        v is not None
                        for k, v in row.items()
                        if k not in ("id", "customer_id", "amount_cents", "currency", "created_at")
                    )
                    found += int(forbidden)
                    retained += int(not forbidden)
            elif target == "analytics":
                found = db.execute(
                    "SELECT count(*) AS n FROM analytics.events WHERE customer_id=%s OR event_id=%s",
                    (subject, fault),
                ).fetchone()["n"]
            elif target == "event_history":
                rows = db.execute(
                    "SELECT event_type,payload FROM delivery.outbox WHERE aggregate_id=%s",
                    (subject,),
                ).fetchall()
                keys = {
                    "deletion.command": {
                        "version",
                        "event_type",
                        "event_id",
                        "request_id",
                        "task_id",
                        "customer_id",
                        "correlation_id",
                        "target",
                    },
                    "verification.command": {
                        "version",
                        "event_type",
                        "event_id",
                        "run_id",
                        "round_no",
                    },
                }
                for row in rows:
                    body = row["payload"]
                    kind = row["event_type"]
                    safe = kind in keys and set(body) == keys.get(kind, set())
                    if safe:
                        try:
                            for key, value in body.items():
                                if key.endswith("_id"):
                                    UUID(value)
                            safe = body["version"] == 1 and body["event_type"] == kind
                        except (ValueError, TypeError):
                            safe = False
                    found += int(not safe)
                    retained += int(safe)
                rows = db.execute(
                    "SELECT to_jsonb(p) AS row FROM delivery.processed p WHERE customer_id=%s",
                    (subject,),
                ).fetchall()
                for item in rows:
                    row = item["row"]
                    safe = row["consumer"] in ("cache", "search", "analytics") and not any(
                        v is not None
                        for k, v in row.items()
                        if k not in ("consumer", "customer_id", "event_id", "processed_at")
                    )
                    found += int(not safe)
                    retained += int(safe)
            else:
                return {"state": "UNSUPPORTED", "eligible_records": None}
    return {
        "state": "RESIDUAL" if found else "ABSENT",
        "eligible_records": found,
        "permitted_records": retained,
    }


def combine(observations: dict, eligible: bool) -> str:
    states = [v["state"] for v in observations.values()]
    if not eligible:
        return "PENDING"
    if "RESIDUAL" in states:
        return "RESIDUAL"
    if "UNSUPPORTED" in states:
        return "UNSUPPORTED"
    if "UNAVAILABLE" in states:
        return "UNAVAILABLE"
    return (
        "ABSENT"
        if len(states) == len(STORES) and all(s == "ABSENT" for s in states)
        else "UNSUPPORTED"
    )


def observe(fixture: dict, eligible: bool) -> dict:
    started = time.monotonic()
    observations = {}
    for target in STORES:
        try:
            observations[target] = inspect_target(target, fixture)
        except Exception as exc:
            observations[target] = {
                "state": "UNAVAILABLE",
                "eligible_records": None,
                "error_class": type(exc).__name__,
            }
    return {
        "state": combine(observations, eligible),
        "targets": observations,
        "elapsed_seconds": time.monotonic() - started,
        "basis": "fresh privileged fixture reads, independent of method predictions; no raw values retained",
    }


if __name__ == "__main__":
    require_gate()
    request = json.load(sys.stdin)
    print(json.dumps(observe(request["fixture"], request["eligible"])))
