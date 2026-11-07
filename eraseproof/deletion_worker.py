"""Dedicated deletion queue; PostgreSQL, not broker headers, owns retry budgets."""

import logging
import os
import time
from eraseproof.broker import connect, topology
from eraseproof.worker import heartbeat
from eraseproof.deletion import execute_command, schedule_once
from eraseproof.deletion_models import DeletionCommand
from eraseproof.logging import configure

log = logging.getLogger("deletion.worker")


def consume() -> None:
    broker = connect()
    try:
        channel = broker.channel()
        topology(channel)
        channel.basic_qos(prefetch_count=1)

        def tick():
            heartbeat()
            broker.call_later(5, tick)

        tick()

        def callback(ch, method, properties, body):
            try:
                command = DeletionCommand.model_validate_json(body)
            except ValueError:
                ch.basic_nack(method.delivery_tag, requeue=False)
                return
            # Unexpected DB/commit failures propagate: connection closes, message is unacked.
            changed = execute_command(command)
            log.info(
                "deletion.command.recorded" if changed else "deletion.command.duplicate_or_stale",
                extra={
                    "event_id": str(command.event_id),
                    "correlation_id": str(command.correlation_id),
                    "target": command.target,
                    "request_id": str(command.request_id),
                },
            )
            ch.basic_ack(method.delivery_tag)

        channel.basic_consume(queue="deletion", on_message_callback=callback, auto_ack=False)
        channel.start_consuming()
    finally:
        if broker.is_open:
            broker.close()


def main() -> None:
    configure()
    scheduler = os.environ.get("WORKER") == "deletion-scheduler"
    while True:
        heartbeat()
        try:
            if scheduler:
                schedule_once()
                time.sleep(0.5)
            else:
                consume()
        except Exception:
            log.exception("deletion.worker.reconnecting")
            time.sleep(2)


if __name__ == "__main__":
    from eraseproof.hosted_security import validate_hosted

    validate_hosted()
    main()
