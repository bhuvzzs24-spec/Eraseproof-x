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
            "GRANT INSERT,UPDATE,DELETE ON customer.customers,orders.orders,delivery.outbox,delivery.processed,analytics.events TO eraseproof_runtime"
        )
        db.execute(
            "GRANT INSERT,UPDATE ON deletion.requests,deletion.tasks,deletion.attempts,deletion.tombstones TO eraseproof_runtime"
        )
        db.execute(
            "GRANT INSERT ON deletion.idempotency_keys,deletion.events,deletion.order_manifest,deletion.scope_captures TO eraseproof_runtime"
        )
        db.execute("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA deletion TO eraseproof_runtime")


if __name__ == "__main__":
    main()
