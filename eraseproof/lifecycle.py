"""One database coordination boundary for every supported customer-linked write."""

from uuid import UUID
import psycopg


def subject_lock(db: psycopg.Connection, customer_id: UUID) -> None:
    db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (str(customer_id),))


def is_deleted(db: psycopg.Connection, customer_id: UUID) -> bool:
    return (
        db.execute(
            "SELECT 1 FROM deletion.tombstones WHERE customer_id=%s", (customer_id,)
        ).fetchone()
        is not None
    )
