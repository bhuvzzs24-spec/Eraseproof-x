import pika
from eraseproof.config import BROKER_URL

TARGETS = ("cache", "search", "analytics")


def connect() -> pika.BlockingConnection:
    params = pika.URLParameters(BROKER_URL)
    params.socket_timeout = 3
    params.blocked_connection_timeout = 5
    params.connection_attempts = 1
    return pika.BlockingConnection(params)


def topology(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
    channel.exchange_declare(exchange="events", exchange_type="topic", durable=True)
    channel.exchange_declare(exchange="dead", exchange_type="direct", durable=True)
    for target in TARGETS:
        channel.queue_declare(queue=f"{target}.dead", durable=True)
        channel.queue_bind(queue=f"{target}.dead", exchange="dead", routing_key=target)
        channel.queue_declare(
            queue=target,
            durable=True,
            arguments={"x-dead-letter-exchange": "dead", "x-dead-letter-routing-key": target},
        )
        channel.queue_bind(queue=target, exchange="events", routing_key="customer.created")
        if target == "analytics":
            channel.queue_bind(queue=target, exchange="events", routing_key="order.created")
    channel.queue_declare(queue="deletion.dead", durable=True)
    channel.queue_bind(queue="deletion.dead", exchange="dead", routing_key="deletion")
    channel.queue_declare(
        queue="deletion",
        durable=True,
        arguments={"x-dead-letter-exchange": "dead", "x-dead-letter-routing-key": "deletion"},
    )
    channel.queue_bind(queue="deletion", exchange="events", routing_key="deletion.command")
    channel.confirm_delivery()
