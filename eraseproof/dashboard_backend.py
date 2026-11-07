"""Authorized, bounded read models for the engineering dashboard; no fault controls."""

import os
import secrets
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from eraseproof.db import connection
from eraseproof import verification


def authorize(x_inspection_token: str = Header(default="")):
    token = os.getenv("INSPECTION_TOKEN", "")
    if (
        os.getenv("APP_ENV") != "demo"
        or len(token) < 24
        or not secrets.compare_digest(token, x_inspection_token)
    ):
        raise HTTPException(403, "dashboard inspection unauthorized")


router = APIRouter(
    prefix="/v1/dashboard", dependencies=[Depends(authorize)], tags=["dashboard read models"]
)


@router.get("/snapshot")
def snapshot():
    with connection() as db:
        db.execute("SET LOCAL statement_timeout='3000ms'")
        return {
            "customer_count": db.execute("SELECT count(*) AS n FROM customer.customers").fetchone()[
                "n"
            ],
            "deletions": db.execute(
                "SELECT state,count(*)::int AS count FROM deletion.requests GROUP BY state ORDER BY state"
            ).fetchall(),
            "verifications": db.execute(
                "SELECT result,count(*)::int AS count FROM verification.runs GROUP BY result ORDER BY result"
            ).fetchall(),
            "recent_findings": db.execute(
                "SELECT id,customer_id,deletion_request_id,result,created_at,finished_at FROM verification.runs WHERE result IN ('FALSE_SUCCESS_DETECTED','RESIDUAL_DATA_DETECTED') ORDER BY created_at DESC,id LIMIT 12"
            ).fetchall(),
            "activity": db.execute(
                "SELECT 'deletion' AS source,request_id AS entity_id,kind,to_state AS state,occurred_at FROM deletion.events UNION ALL SELECT 'verification',run_id,kind,code,occurred_at FROM verification.timeline ORDER BY occurred_at DESC LIMIT 30"
            ).fetchall(),
            "observed_at": db.execute("SELECT now() AS time").fetchone()["time"],
            "probe_failures": db.execute(
                "SELECT coalesce(sum(probe_failures),0)::int AS n FROM verification.targets"
            ).fetchone()["n"],
            "inconclusive_targets": db.execute(
                "SELECT count(*)::int AS n FROM verification.targets WHERE result='INCONCLUSIVE'"
            ).fetchone()["n"],
            "basis": "live database read model; operational completion is not independent proof",
        }


@router.get("/customers")
def customers(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    search: str = Query("", max_length=100),
):
    with connection() as db:
        db.execute("SET LOCAL statement_timeout='3000ms'")
        args = (f"%{search}%", f"%{search}%")
        query = """FROM (SELECT c.id,c.name,c.created_at,coalesce(t.lifecycle,'ACTIVE') AS lifecycle,t.request_id FROM customer.customers c LEFT JOIN deletion.tombstones t ON t.customer_id=c.id UNION ALL SELECT t.customer_id,NULL,t.created_at,t.lifecycle,t.request_id FROM deletion.tombstones t WHERE NOT EXISTS(SELECT 1 FROM customer.customers c WHERE c.id=t.customer_id)) c WHERE (c.id::text ILIKE %s OR c.name ILIKE %s)"""
        total = db.execute("SELECT count(*) AS n " + query, args).fetchone()["n"]
        items = db.execute(
            "SELECT * " + query + " ORDER BY created_at DESC,id LIMIT %s OFFSET %s",
            (*args, limit, offset),
        ).fetchall()
        return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/verifications")
def runs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    result: str | None = Query(None, max_length=40),
):
    with connection() as db:
        db.execute("SET LOCAL statement_timeout='3000ms'")
        args = (result, result)
        total = db.execute(
            "SELECT count(*) AS n FROM verification.runs WHERE (%s::text IS NULL OR result=%s)",
            args,
        ).fetchone()["n"]
        ids = db.execute(
            "SELECT id FROM verification.runs WHERE (%s::text IS NULL OR result=%s) ORDER BY created_at DESC,id LIMIT %s OFFSET %s",
            (*args, limit, offset),
        ).fetchall()
        return {
            "items": [verification.view(db, r["id"]) for r in ids],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.get("/deletions")
def deletions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    state: str | None = Query(None, max_length=40),
):
    from eraseproof.deletion import view

    with connection() as db:
        db.execute("SET LOCAL statement_timeout='3000ms'")
        args = (state, state)
        total = db.execute(
            "SELECT count(*) AS n FROM deletion.requests WHERE (%s::text IS NULL OR state=%s)", args
        ).fetchone()["n"]
        ids = db.execute(
            "SELECT id FROM deletion.requests WHERE (%s::text IS NULL OR state=%s) ORDER BY created_at DESC,id LIMIT %s OFFSET %s",
            (*args, limit, offset),
        ).fetchall()
        return {
            "items": [view(db, row["id"]) for row in ids],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.get("/customers/{customer_id}/footprint")
def footprint(customer_id: UUID):
    """Operational inspection only; narrow fact fields never assert complete anonymization."""
    with connection() as db:
        db.execute("SET LOCAL statement_timeout='3000ms'")
        scope = " WHERE o.customer_id=%s OR o.id IN (SELECT m.order_id FROM deletion.order_manifest m JOIN deletion.requests r ON r.id=m.request_id WHERE r.customer_id=%s)"
        args = (customer_id, customer_id)
        total = db.execute("SELECT count(*) AS n FROM orders.orders o" + scope, args).fetchone()[
            "n"
        ]
        items = db.execute(
            "SELECT o.id,o.amount_cents,o.currency,o.created_at,(o.customer_id IS NOT NULL) AS has_customer_link FROM orders.orders o"
            + scope
            + " ORDER BY o.created_at,o.id LIMIT 100",
            args,
        ).fetchall()
        events = db.execute(
            "SELECT count(*) FILTER (WHERE event_type IN ('customer.created','order.created')) AS source_events,count(*) FILTER (WHERE event_type NOT IN ('customer.created','order.created')) AS other_events FROM delivery.outbox WHERE aggregate_id=%s",
            (customer_id,),
        ).fetchone()
        events["consumer_receipts"] = db.execute(
            "SELECT count(*) AS n FROM delivery.processed WHERE customer_id=%s", (customer_id,)
        ).fetchone()["n"]
        events["audit_events"] = db.execute(
            "SELECT count(*) AS n FROM deletion.events e JOIN deletion.requests r ON r.id=e.request_id WHERE r.customer_id=%s",
            (customer_id,),
        ).fetchone()["n"]
        return {
            "customer_id": customer_id,
            "source_present": db.execute(
                "SELECT EXISTS(SELECT 1 FROM customer.customers WHERE id=%s) AS found",
                (customer_id,),
            ).fetchone()["found"],
            "tombstone": db.execute(
                "SELECT customer_id,request_id,lifecycle,created_at FROM deletion.tombstones WHERE customer_id=%s",
                (customer_id,),
            ).fetchone(),
            "orders": {"total": total, "items": items},
            "event_history": events,
            "observed_at": db.execute("SELECT now() AS observed").fetchone()["observed"],
            "note": "Known source/manifest rows and metadata only; independent verification is required to evaluate extra personal fields, marker versions and complete declared scope.",
        }
