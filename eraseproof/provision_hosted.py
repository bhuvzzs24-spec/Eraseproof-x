"""Owner-only, one-shot grants. Runtime services never receive owner credentials."""

import os
from psycopg import sql
from eraseproof.db import connection
from eraseproof.provision_verification import provision


def main():
    provision()
    secret = os.environ["RUNTIME_DB_PASSWORD"]
    if len(secret) < 32:
        raise ValueError("runtime database password too short")
    with connection() as db:
        if not db.execute("SELECT 1 FROM pg_roles WHERE rolname='eraseproof_runtime'").fetchone():
            db.execute(
                "CREATE ROLE eraseproof_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION"
            )
        db.execute(sql.SQL("ALTER ROLE eraseproof_runtime PASSWORD {}").format(sql.Literal(secret)))
        db.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        db.execute(
            "GRANT USAGE ON SCHEMA public,customer,orders,delivery,analytics,deletion,verification,research TO eraseproof_runtime"
        )
        db.execute(
            "GRANT SELECT ON ALL TABLES IN SCHEMA public,customer,orders,delivery,analytics,deletion,verification,research TO eraseproof_runtime"
        )
        db.execute(
            "GRANT INSERT,UPDATE,DELETE ON customer.customers,orders.orders,delivery.processed,analytics.events TO eraseproof_runtime"
        )
        db.execute(
            "GRANT INSERT,UPDATE ON deletion.requests,deletion.tasks,deletion.attempts,deletion.tombstones TO eraseproof_runtime"
        )
        db.execute(
            "GRANT INSERT ON deletion.idempotency_keys,deletion.events,deletion.order_manifest,deletion.scope_captures TO eraseproof_runtime"
        )
        db.execute(
            "ALTER ROLE eraseproof_runtime NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
        )
        db.execute("REVOKE INSERT,UPDATE,DELETE ON delivery.outbox FROM eraseproof_runtime")
        db.execute(
            "GRANT INSERT(id,aggregate_id,event_type,payload) ON delivery.outbox TO eraseproof_runtime"
        )
        db.execute(
            "GRANT UPDATE(published_at,attempts,last_error,next_attempt_at,cancelled_at),DELETE ON delivery.outbox TO eraseproof_runtime"
        )
        for name in (
            "runtime_outbox_read",
            "runtime_outbox_insert",
            "runtime_outbox_update",
            "runtime_outbox_delete",
        ):
            db.execute(
                sql.SQL("DROP POLICY IF EXISTS {} ON delivery.outbox").format(sql.Identifier(name))
            )
        db.execute(
            "CREATE POLICY runtime_outbox_read ON delivery.outbox FOR SELECT TO eraseproof_runtime USING (true)"
        )
        db.execute(
            "CREATE POLICY runtime_outbox_insert ON delivery.outbox FOR INSERT TO eraseproof_runtime WITH CHECK (event_type IN ('customer.created','order.created','deletion.command'))"
        )
        db.execute(
            "CREATE POLICY runtime_outbox_update ON delivery.outbox FOR UPDATE TO eraseproof_runtime USING (true) WITH CHECK (true)"
        )
        db.execute(
            "CREATE POLICY runtime_outbox_delete ON delivery.outbox FOR DELETE TO eraseproof_runtime USING (event_type IN ('customer.created','order.created'))"
        )
        db.execute("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA deletion TO eraseproof_runtime")


if __name__ == "__main__":
    main()
