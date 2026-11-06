import json
import logging
import os
import time
import httpx
import pika
import redis
from psycopg.types.json import Jsonb
from eraseproof.broker import connect, topology
from eraseproof.config import REDIS_URL, SEARCH_URL
from eraseproof.db import connection
from eraseproof.events import Event

log = logging.getLogger("worker")


def publish_once() -> bool:
    # Row lock is held across broker confirmation. A crash before commit can duplicate, never lose.
    broker = connect()
    try:
        channel = broker.channel()
        topology(channel)
        with connection() as db:
            row = db.execute(
                "SELECT * FROM delivery.outbox WHERE published_at IS NULL "
                "AND next_attempt_at <= now() ORDER BY created_at "
                "FOR UPDATE SKIP LOCKED LIMIT 1"
            ).fetchone()
            if row is None:
                return False
            try:
                channel.basic_publish(
                    exchange="events",
                    routing_key=row["event_type"],
                    body=json.dumps(row["payload"]),
                    mandatory=True,
                    properties=pika.BasicProperties(
                        delivery_mode=2, message_id=str(row["id"]), content_type="application/json"
                    ),
                )
            except Exception as exc:
                db.execute(
                    "UPDATE delivery.outbox SET attempts=attempts+1,last_error=%s, "
                    "next_attempt_at=now()+ interval '10 seconds' WHERE id=%s",
                    (type(exc).__name__, row["id"]),
                )
                return False
            db.execute(
                "UPDATE delivery.outbox SET published_at=now(),attempts=attempts+1, "
                "last_error=NULL WHERE id=%s",
                (row["id"],),
            )
            return True
    finally:
        broker.close()


def apply_event(target: str, event: Event) -> bool:
    if target not in ("cache", "search", "analytics"):
        raise ValueError("unknown consumer")
    with connection() as db:
        # Per-event advisory lock serializes concurrent duplicates including external writes.
        db.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (target + str(event.event_id),)
        )
        if db.execute(
            "SELECT 1 FROM delivery.processed WHERE consumer=%s AND event_id=%s",
            (target, event.event_id),
        ).fetchone():
            return False
        data = event.data.model_dump(mode="json")
        if target != "analytics" and event.event_type != "customer.created":
            raise ValueError("unsupported target event")
        if target == "cache":
            client = redis.Redis.from_url(REDIS_URL, socket_timeout=3, socket_connect_timeout=3)
            try:
                client.set(f"customer:{event.customer_id}", json.dumps(data))
            finally:
                client.close()
        elif target == "search":
            with httpx.Client(timeout=5) as client:
                response = client.put(
                    f"{SEARCH_URL}/customers/_doc/{event.customer_id}",
                    params={"refresh": "wait_for"},
                    json=data,
                )
                response.raise_for_status()
        else:
            db.execute(
                "INSERT INTO analytics.events(event_id,customer_id,event_type,payload) "
                "VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (
                    event.event_id,
                    event.customer_id,
                    event.event_type,
                    Jsonb(event.model_dump(mode="json")),
                ),
            )
        db.execute(
            "INSERT INTO delivery.processed(consumer,event_id,customer_id) VALUES (%s,%s,%s)",
            (target, event.event_id, event.customer_id),
        )
        return True


def consume(target: str) -> None:
    broker = connect()
    try:
        channel = broker.channel()
        topology(channel)
        channel.basic_qos(prefetch_count=1)

        def callback(ch, method, properties, body):
            try:
                event = Event.model_validate_json(body)
            except ValueError:
                ch.basic_nack(method.delivery_tag, requeue=False)
                return
            try:
                apply_event(target, event)
            except Exception:
                log.exception("consumer_failed", extra={"event_id": str(event.event_id)})
                attempt = int((properties.headers or {}).get("attempt", 0)) + 1
                if attempt >= 5:
                    ch.basic_nack(method.delivery_tag, requeue=False)
                    return
                # Bounded backoff; connection processes heartbeats during delay.
                broker.sleep(min(2**attempt, 16))
                ch.basic_publish(
                    exchange="",
                    routing_key=target,
                    body=body,
                    mandatory=True,
                    properties=pika.BasicProperties(
                        delivery_mode=2,
                        message_id=str(event.event_id),
                        content_type="application/json",
                        headers={"attempt": attempt},
                    ),
                )
                # Ack original only after retry copy is confirmed.
            ch.basic_ack(method.delivery_tag)

        channel.basic_consume(queue=target, on_message_callback=callback, auto_ack=False)
        channel.start_consuming()
    finally:
        if broker.is_open:
            broker.close()


def main() -> None:
    from eraseproof.logging import configure

    configure()
    target = os.environ.get("WORKER", "publisher")
    while True:
        try:
            if target == "publisher":
                if not publish_once():
                    time.sleep(1)
            else:
                consume(target)
        except Exception:
            log.exception("worker_reconnecting")
            time.sleep(3)


if __name__ == "__main__":
    main()
