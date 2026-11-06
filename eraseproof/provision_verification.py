"""Run as the existing local DB owner before verifier services start. No credentials printed."""

import os
from psycopg import sql
import redis
from eraseproof.db import connection
from eraseproof.config import REDIS_URL


def provision() -> None:
    with connection() as db:
        for role, variable in (
            ("verification_probe", "VERIFIER_DB_PASSWORD"),
            ("verification_coordinator", "VERIFIER_CONTROL_PASSWORD"),
        ):
            secret = os.environ[variable]
            if len(secret) < 24:
                raise ValueError("verification database credential too short")
            if not db.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                db.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
            db.execute(
                sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(secret)
                )
            )
        db.execute("ALTER ROLE verification_probe SET default_transaction_read_only=on")
        db.execute(
            "GRANT USAGE ON SCHEMA customer,orders,analytics,delivery,deletion TO verification_probe"
        )
        db.execute(
            "GRANT SELECT ON customer.customers,orders.orders,analytics.events,delivery.outbox,delivery.processed,deletion.order_manifest,deletion.scope_captures TO verification_probe"
        )
        db.execute(
            "GRANT USAGE ON SCHEMA verification,deletion,delivery,public TO verification_coordinator"
        )
        db.execute(
            "GRANT SELECT ON deletion.requests,deletion.tasks,deletion.attempts,public.schema_migrations TO verification_coordinator"
        )
        db.execute(
            "GRANT SELECT,INSERT,UPDATE ON verification.runs,verification.targets TO verification_coordinator"
        )
        db.execute(
            "GRANT SELECT,INSERT ON verification.evidence,verification.timeline TO verification_coordinator"
        )
        db.execute(
            "GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA verification TO verification_coordinator"
        )
        db.execute(
            "GRANT INSERT(id,aggregate_id,event_type,payload) ON delivery.outbox TO verification_coordinator"
        )
    secret = os.environ["VERIFIER_REDIS_PASSWORD"]
    if len(secret) < 24:
        raise ValueError("verification Redis credential too short")
    with redis.Redis.from_url(REDIS_URL, socket_timeout=3) as client:
        client.execute_command(
            "ACL",
            "SETUSER",
            "verification",
            "reset",
            "on",
            ">" + secret,
            "~customer:*",
            "~deletion:customer:*",
            "+scan",
            "+get",
            "+exists",
            "+type",
            "+ping",
        )


if __name__ == "__main__":
    provision()
