"""Fixed SQL/keys only; never accept a table, index or key name from a caller."""

from uuid import UUID
import httpx
import psycopg
import redis
from redis.retry import Retry
from redis.backoff import NoBackoff
from eraseproof.config import REDIS_URL, SEARCH_URL


class ConnectorFailure(Exception):
    def __init__(self, code: str, retryable: bool = True):
        self.code = code
        self.retryable = retryable


def delete_target(db: psycopg.Connection, target: str, subject: UUID) -> None:
    if target == "orders":
        # Retain non-personal transaction facts without the customer linkage.
        db.execute("UPDATE orders.orders SET customer_id=NULL WHERE customer_id=%s", (subject,))
    elif target == "customer":
        db.execute("DELETE FROM customer.customers WHERE id=%s", (subject,))
    elif target == "analytics":
        db.execute("DELETE FROM analytics.events WHERE customer_id=%s", (subject,))
    elif target == "event_history":
        db.execute(
            "DELETE FROM delivery.outbox WHERE aggregate_id=%s AND event_type IN ('customer.created','order.created')",
            (subject,),
        )
        db.execute("DELETE FROM delivery.processed WHERE customer_id=%s", (subject,))
    elif target == "cache":
        try:
            with redis.Redis.from_url(
                REDIS_URL, socket_timeout=3, socket_connect_timeout=3, retry=Retry(NoBackoff(), 0)
            ) as client:
                client.eval(
                    "redis.call('SET',KEYS[2],'1'); return redis.call('DEL',KEYS[1])",
                    2,
                    f"customer:{subject}",
                    f"deletion:customer:{subject}",
                )
        except redis.RedisError as exc:
            raise ConnectorFailure("REDIS_UNAVAILABLE") from exc
    elif target == "search":
        try:
            # Persistent version-2 marker scrubs all profile fields and fences delayed v1 writes.
            response = httpx.put(
                f"{SEARCH_URL}/customers/_doc/{subject}",
                params={"refresh": "wait_for", "version": 2, "version_type": "external_gte"},
                json={"erased": True},
                timeout=5,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorFailure("SEARCH_UNAVAILABLE") from exc
    else:
        raise ConnectorFailure("UNSUPPORTED_TARGET", retryable=False)
