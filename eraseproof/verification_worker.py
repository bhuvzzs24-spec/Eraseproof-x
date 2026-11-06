import logging
import os
import time
from eraseproof.broker import connect, topology
from eraseproof.worker import heartbeat
from eraseproof.logging import configure
from eraseproof.verification_models import VerificationCommand
from eraseproof.verification import schedule_once, execute


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
                command = VerificationCommand.model_validate_json(body)
            except ValueError:
                ch.basic_nack(method.delivery_tag, requeue=False)
                return
            execute(command)
            ch.basic_ack(method.delivery_tag)

        channel.basic_consume(queue="verification", on_message_callback=callback, auto_ack=False)
        channel.start_consuming()
    finally:
        if broker.is_open:
            broker.close()


def main() -> None:
    configure()
    while True:
        heartbeat()
        try:
            if os.getenv("WORKER") == "verification-scheduler":
                schedule_once()
                time.sleep(0.5)
            else:
                consume()
        except Exception:
            logging.getLogger("verification.worker").exception("verification.reconnecting")
            time.sleep(2)


if __name__ == "__main__":
    main()
