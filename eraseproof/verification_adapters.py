"""Independent fixed read-only probes. Never import or invoke deletion connectors."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from uuid import UUID
import os
import time
import httpx
import psycopg
from psycopg.rows import dict_row
import redis
from redis.retry import Retry
from redis.backoff import NoBackoff
from eraseproof.verification_models import Probe, Outcome, VerificationCommand
from eraseproof.deletion_models import DeletionCommand


queries = ContextVar("verification_queries", default=0)


def counted(function, *args, **kwargs):
    queries.set(queries.get() + 1)
    return function(*args, **kwargs)


class ReadSession:
    def __init__(self, db):
        self.db = db

    def execute(self, *args, **kwargs):
        return counted(self.db.execute, *args, **kwargs)


@contextmanager
def read_db():
    url = os.environ.get("VERIFIER_READ_DATABASE_URL", "")
    if not url:
        raise RuntimeError("read credentials unavailable")
    with psycopg.connect(
        url,
        row_factory=dict_row,
        connect_timeout=3,
        options="-c default_transaction_read_only=on -c statement_timeout=3000 -c lock_timeout=2500",
    ) as db:
        yield ReadSession(db)


def safe_control(event_type: str, payload: object) -> bool:
    model = {"deletion.command": DeletionCommand, "verification.command": VerificationCommand}.get(
        event_type
    )
    if model is None:
        return False
    try:
        model.model_validate(payload)
    except ValueError:
        return False
    return True


def safe_receipt(data: dict) -> bool:
    allowed = {"consumer", "event_id", "customer_id", "processed_at"}
    return data.get("consumer") in ("cache", "search", "analytics") and not any(
        value is not None for key, value in data.items() if key not in allowed
    )


def sql_probe(target: str, subject: UUID, request_id: UUID, scope: dict) -> tuple[dict, int, bool]:
    with read_db() as db:
        if target == "customer":
            n = db.execute(
                "SELECT count(*) AS n FROM customer.customers WHERE id=%s", (subject,)
            ).fetchone()["n"]
            return {"eligible_rows": n}, 1, True
        if target == "orders":
            capture = db.execute(
                "SELECT 1 FROM deletion.scope_captures WHERE request_id=%s AND version=%s",
                (request_id, "scope-v1"),
            ).fetchone()
            rows = db.execute(
                "SELECT to_jsonb(o) AS data FROM orders.orders o WHERE customer_id=%s "
                "OR id IN (SELECT order_id FROM deletion.order_manifest WHERE request_id=%s) LIMIT 1001",
                (subject, request_id),
            ).fetchall()
            prohibited = 0
            for row in rows:
                data = row["data"]
                if data.get("customer_id") is not None or any(
                    v is not None for k, v in data.items() if k not in scope["allowed_fact_fields"]
                ):
                    prohibited += 1
            return (
                {
                    "eligible_rows": prohibited,
                    "permitted_fact_rows": len(rows) - prohibited,
                    "manifest_captured": bool(capture),
                },
                2,
                bool(capture) and len(rows) <= 1000,
            )
        if target == "analytics":
            n = db.execute(
                "SELECT count(*) AS n FROM analytics.events WHERE customer_id=%s OR "
                "jsonb_path_exists(payload,'$.** ? (@ == $subject)',jsonb_build_object('subject',%s::text))",
                (subject, str(subject)),
            ).fetchone()["n"]
            return {"eligible_rows": n}, 1, True
        if target == "event_history":
            rows = db.execute(
                "SELECT event_type,payload FROM delivery.outbox WHERE aggregate_id=%s OR "
                "jsonb_path_exists(payload,'$.** ? (@ == $subject)',jsonb_build_object('subject',%s::text)) LIMIT 1001",
                (subject, str(subject)),
            ).fetchall()
            bad = sum(1 for row in rows if not safe_control(row["event_type"], row["payload"]))
            receipts = db.execute(
                "SELECT to_jsonb(p) AS data FROM delivery.processed p WHERE customer_id=%s LIMIT 1001",
                (subject,),
            ).fetchall()
            bad += sum(1 for row in receipts if not safe_receipt(row["data"]))
            return (
                {"eligible_rows": bad, "permitted_metadata_rows": len(rows) + len(receipts) - bad},
                2,
                len(rows) <= 1000 and len(receipts) <= 1000,
            )
    raise ValueError("unsupported SQL adapter")


def cache_probe(subject: UUID) -> tuple[dict, int, bool]:
    url = os.environ.get("VERIFIER_REDIS_URL", "")
    if not url:
        raise RuntimeError("Redis read credentials unavailable")
    count = 0
    bad = 0
    markers = 0
    calls = 0
    deadline = time.monotonic() + 3
    with redis.Redis.from_url(
        url, socket_timeout=2, socket_connect_timeout=2, retry=Retry(NoBackoff(), 0)
    ) as client:
        for pattern in (f"customer:{subject}*", f"deletion:customer:{subject}*"):
            cursor = 0
            while True:
                cursor, keys = counted(client.scan, cursor, match=pattern, count=100)
                calls += 1
                for key in keys:
                    count += 1
                    if count > 1000 or time.monotonic() > deadline:
                        return {"eligible_rows": bad, "permitted_markers": markers}, calls, False
                    kind = counted(client.type, key)
                    calls += 1
                    if kind == b"none":
                        continue
                    if kind != b"string":
                        return {"eligible_rows": bad, "permitted_markers": markers}, calls, False
                    value = counted(client.get, key)
                    calls += 1
                    if value is None:
                        continue
                    if key == f"deletion:customer:{subject}".encode() and value == b"1":
                        markers += 1
                    else:
                        bad += 1
                if not cursor:
                    break
                if time.monotonic() > deadline:
                    return {"eligible_rows": bad, "permitted_markers": markers}, calls, False
    return {"eligible_rows": bad, "permitted_markers": markers}, calls, True


def search_probe(subject: UUID, scope: dict) -> tuple[dict, int, bool]:
    base = os.getenv("VERIFIER_SEARCH_URL", "http://opensearch:9200")
    documents = {}
    calls = 0
    with httpx.Client(timeout=3) as client:
        response = counted(client.get, f"{base}/customers/_doc/{subject}")
        calls += 1
        if response.status_code != 404:
            response.raise_for_status()
            doc = response.json()
            if doc.get("found"):
                documents[doc["_id"]] = doc
        should = [{"ids": {"values": [str(subject)]}}]
        for field in scope["identifier_fields"]:
            should.extend(
                [{"term": {field: str(subject)}}, {"term": {field + ".keyword": str(subject)}}]
            )
        response = counted(
            client.post,
            f"{base}/customers/_search",
            json={
                "size": 200,
                "track_total_hits": True,
                "version": True,
                "query": {"bool": {"should": should, "minimum_should_match": 1}},
            },
        )
        calls += 1
        if (
            response.status_code == 404
            and response.json().get("error", {}).get("type") == "index_not_found_exception"
        ):
            return {"eligible_rows": 0, "permitted_markers": 0}, calls, True
        response.raise_for_status()
        found = response.json()
        hits = found["hits"]["hits"]
        total = found["hits"]["total"]
        complete = (
            not found.get("timed_out", False)
            and found.get("_shards", {}).get("failed", 0) == 0
            and total["relation"] == "eq"
            and total["value"] <= len(hits)
        )
        documents.update({doc["_id"]: doc for doc in hits})
    markers = 0
    bad = 0
    for identifier, doc in documents.items():
        if (
            identifier == str(subject)
            and isinstance(doc.get("_source"), dict)
            and set(doc["_source"]) == {"erased"}
            and doc["_source"]["erased"] is True
            and doc.get("_version", 0) >= 2
        ):
            markers += 1
        else:
            bad += 1
    return {"eligible_rows": bad, "permitted_markers": markers}, calls, complete


def probe(target: str, subject: UUID, request_id: UUID, scope: dict) -> Probe:
    started = time.monotonic()
    started_at = datetime.now(timezone.utc)
    queries.set(0)
    adapter = "independent." + target

    def result(state, summary, calls=0, complete=True, error=None):
        return Probe(
            started_at=started_at,
            outcome=state,
            adapter=adapter,
            category=scope.get("category", "unknown"),
            summary=summary,
            query_count=queries.get(),
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
            error_code=error,
            scope_complete=complete,
        )

    # Only ephemeral, explicitly opted-in test workers may omit a capability.
    omitted = (
        os.getenv("VERIFICATION_TEST_DISABLE_ADAPTERS", "").split(",")
        if os.getenv("ENABLE_TEST_FAULTS") == "1"
        else []
    )
    if target in omitted or target not in (
        "customer",
        "orders",
        "cache",
        "search",
        "analytics",
        "event_history",
    ):
        return result(Outcome.UNSUPPORTED, {}, complete=False, error="MISSING_ADAPTER")
    try:
        if target == "cache":
            summary, calls, complete = cache_probe(subject)
        elif target == "search":
            summary, calls, complete = search_probe(subject, scope)
        else:
            summary, calls, complete = sql_probe(target, subject, request_id, scope)
        state = (
            Outcome.RESIDUAL
            if summary["eligible_rows"]
            else Outcome.ABSENT
            if complete
            else Outcome.INCONCLUSIVE
        )
        return result(state, summary, calls, complete, None if complete else "INCOMPLETE_SCOPE")
    except (
        psycopg.Error,
        redis.RedisError,
        httpx.HTTPError,
        RuntimeError,
        ValueError,
        KeyError,
        TypeError,
    ):
        # No raw exception messages, response bodies or values enter evidence.
        return result(
            Outcome.INCONCLUSIVE, {}, calls=1, complete=False, error="PROBE_UNAVAILABLE_OR_INVALID"
        )
