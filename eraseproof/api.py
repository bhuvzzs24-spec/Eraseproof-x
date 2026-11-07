import json
import os
import logging
import secrets
from uuid import UUID, uuid4
from typing import Literal
import httpx
import psycopg
import redis
from fastapi import FastAPI, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb
from eraseproof import config
from eraseproof.db import connection
from eraseproof.events import CustomerData, OrderData, Event
from eraseproof.logging import configure
from eraseproof.lifecycle import subject_lock, is_deleted

configure()
app = FastAPI(title=f"EraseProof X {config.SERVICE}", version="0.1.0")
log = logging.getLogger("api")


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^Synthetic [A-Za-z0-9 -]+$")
    email: str = Field(pattern=r"^[a-zA-Z0-9._+-]+@example\.invalid$")


class OrderCreate(BaseModel):
    customer_id: UUID
    amount_cents: int = Field(gt=0, le=100000000)
    currency: Literal["USD", "INR", "EUR"] = "USD"


class CustomerResponse(CustomerData):
    event_id: UUID | None = None


class OrderResponse(OrderData):
    customer_id: UUID | None
    event_id: UUID | None = None


def authorized(x_inspection_token: str = Header(default="")):
    if not config.INSPECTION_TOKEN or not secrets.compare_digest(
        x_inspection_token, config.INSPECTION_TOKEN
    ):
        raise HTTPException(403, "development inspection disabled or unauthorized")


def authorize_operator(x_operator_token: str = Header(default="")):
    # Backward-compatible trusted-lab mode; the dashboard overlay always configures this token.
    expected = os.getenv("OPERATOR_TOKEN", "")
    if expected and (len(expected) < 24 or not secrets.compare_digest(expected, x_operator_token)):
        raise HTTPException(403, "authorized operator credential required")


@app.middleware("http")
async def trace(request: Request, call_next):
    try:
        correlation = UUID(request.headers.get("X-Correlation-ID", str(uuid4())))
    except ValueError:
        return JSONResponse(status_code=400, content={"detail": "invalid correlation UUID"})
    request.state.correlation_id = correlation
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = str(correlation)
    log.info(
        "request",
        extra={
            "path": request.url.path,
            "status": response.status_code,
            "correlation_id": str(correlation),
        },
    )
    return response


@app.exception_handler(psycopg.IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse(
        status_code=409, content={"detail": "constraint conflict or missing customer"}
    )


@app.exception_handler(Exception)
async def service_error(request, exc):
    log.error("dependency_failed", extra={"correlation_id": str(request.state.correlation_id)})
    return JSONResponse(status_code=503, content={"detail": "dependency unavailable"})


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "alive", "service": config.SERVICE}


def cache_client() -> redis.Redis:
    return redis.Redis.from_url(config.REDIS_URL, socket_timeout=3, socket_connect_timeout=3)


@app.get("/health/ready")
def ready() -> dict[str, str]:
    with connection() as db:
        migration = db.execute(
            "SELECT 1 FROM schema_migrations WHERE version='004_research.sql'"
        ).fetchone()
        if migration is None:
            raise RuntimeError("migration missing")
    if config.SERVICE == "cache":
        with cache_client() as client:
            client.ping()
    if config.SERVICE == "search":
        httpx.get(f"{config.SEARCH_URL}/_cluster/health", timeout=3).raise_for_status()
    return {"status": "ready"}


def record(db: psycopg.Connection, event: Event) -> None:
    db.execute(
        "INSERT INTO delivery.outbox(id,aggregate_id,event_type,payload) VALUES (%s,%s,%s,%s)",
        (event.event_id, event.customer_id, event.event_type, Jsonb(event.model_dump(mode="json"))),
    )


if config.SERVICE == "customer":
    from eraseproof.dashboard_backend import router as dashboard_router

    app.include_router(dashboard_router)

    @app.post(
        "/v1/customers",
        response_model=CustomerResponse,
        status_code=201,
        dependencies=[Depends(authorize_operator)],
    )
    def create_customer(body: CustomerCreate, request: Request):
        data = CustomerData(id=uuid4(), **body.model_dump())
        event = Event(
            event_type="customer.created",
            customer_id=data.id,
            data=data,
            correlation_id=request.state.correlation_id,
        )
        with connection() as db:
            db.execute(
                "INSERT INTO customer.customers(id,name,email) VALUES (%s,%s,%s)",
                (data.id, data.name, data.email),
            )
            record(db, event)
        return {**data.model_dump(), "event_id": event.event_id}

    @app.get("/v1/customers/{customer_id}", response_model=CustomerResponse)
    def get_customer(customer_id: UUID):
        with connection() as db:
            row = db.execute(
                "SELECT id,name,email FROM customer.customers WHERE id=%s", (customer_id,)
            ).fetchone()
        if row is None:
            raise HTTPException(404, "customer not found")
        return row

    @app.get("/v1/customers/{customer_id}/propagation", dependencies=[Depends(authorized)])
    def propagation(customer_id: UUID):
        # Operational receipts only: never a deletion proof or an atomic distributed snapshot.
        with connection() as db:
            source = (
                db.execute(
                    "SELECT 1 FROM customer.customers WHERE id=%s", (customer_id,)
                ).fetchone()
                is not None
            )
            outbox = db.execute(
                "SELECT id,event_type,published_at,attempts,last_error "
                "FROM delivery.outbox WHERE aggregate_id=%s",
                (customer_id,),
            ).fetchall()
            receipts = db.execute(
                "SELECT consumer,event_id,processed_at FROM delivery.processed "
                "WHERE customer_id=%s",
                (customer_id,),
            ).fetchall()
        states = {}
        for service, port in (("cache", 8002), ("search", 8003), ("analytics", 8004)):
            url = f"http://{service}:{port}/v1/inspect/customers/{customer_id}"
            try:
                response = httpx.get(
                    url, timeout=4, headers={"X-Inspection-Token": config.INSPECTION_TOKEN}
                )
                response.raise_for_status()
                states[service] = response.json()
            except httpx.HTTPError:
                states[service] = {"state": "unknown", "reason": "unavailable"}
        return {
            "customer_id": customer_id,
            "source_present": source,
            "outbox": outbox,
            "receipts": receipts,
            "stores": states,
            "deletion_proof": False,
        }


if config.SERVICE == "order":

    @app.post(
        "/v1/orders",
        response_model=OrderResponse,
        status_code=201,
        dependencies=[Depends(authorize_operator)],
    )
    def create_order(body: OrderCreate, request: Request):
        data = OrderData(id=uuid4(), **body.model_dump())
        event = Event(
            event_type="order.created",
            customer_id=data.customer_id,
            data=data,
            correlation_id=request.state.correlation_id,
        )
        with connection() as db:
            subject_lock(db, data.customer_id)
            if is_deleted(db, data.customer_id):
                raise HTTPException(409, "customer deletion barrier rejects new orders")
            db.execute(
                "INSERT INTO orders.orders(id,customer_id,amount_cents,currency) "
                "VALUES (%s,%s,%s,%s)",
                (data.id, data.customer_id, data.amount_cents, data.currency),
            )
            record(db, event)
        return {**data.model_dump(), "event_id": event.event_id}

    @app.get("/v1/orders/{order_id}", response_model=OrderResponse)
    def get_order(order_id: UUID):
        with connection() as db:
            row = db.execute(
                "SELECT id,customer_id,amount_cents,currency FROM orders.orders WHERE id=%s",
                (order_id,),
            ).fetchone()
        if row is None:
            raise HTTPException(404, "order not found")
        return row


if config.SERVICE in ("cache", "search", "analytics"):

    @app.get("/v1/inspect/customers/{customer_id}", dependencies=[Depends(authorized)])
    def inspect_customer(customer_id: UUID):
        if config.SERVICE == "cache":
            with cache_client() as client:
                raw = client.get(f"customer:{customer_id}")
            data = json.loads(raw) if raw else None
        elif config.SERVICE == "search":
            response = httpx.get(f"{config.SEARCH_URL}/customers/_doc/{customer_id}", timeout=3)
            if response.status_code != 404:
                response.raise_for_status()
            data = response.json().get("_source")
            if data == {"erased": True}:
                return {
                    "state": "absent",
                    "data": None,
                    "document_present": True,
                    "erasure_marker": True,
                    "scope": "profile_fields",
                }
        else:
            with connection() as db:
                data = db.execute(
                    "SELECT event_id,event_type,payload FROM analytics.events WHERE customer_id=%s",
                    (customer_id,),
                ).fetchall()
        return {"state": "present" if data else "absent", "data": data}


if config.SERVICE == "deletion":
    from eraseproof.deletion_api import router

    app.include_router(router)


if config.SERVICE == "verification":
    from eraseproof.verification_api import router

    app.include_router(router)


if config.SERVICE == "verification":
    from eraseproof.research_api import router as research_router

    app.include_router(research_router)
