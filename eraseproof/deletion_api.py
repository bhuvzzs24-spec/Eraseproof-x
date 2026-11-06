import os
import secrets
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel
from eraseproof.db import connection
from eraseproof.deletion import submit, view, retry_request
from eraseproof.deletion_models import (
    SubmitDeletion,
    DeletionView,
    DeletionList,
    AuditView,
    RequestState,
)


def authorize(x_deletion_token: str = Header(default="")) -> None:
    expected = os.environ.get("DELETION_TOKEN", "")
    if (
        os.getenv("APP_ENV", "") != "demo"
        or len(expected) < 24
        or not secrets.compare_digest(expected, x_deletion_token)
    ):
        raise HTTPException(403, "demo deletion access disabled or unauthorized")


router = APIRouter(
    prefix="/v1/deletions", tags=["deletion orchestration"], dependencies=[Depends(authorize)]
)


@router.post("", status_code=202, response_model=DeletionView)
def create(body: SubmitDeletion, request: Request) -> dict:
    return submit(body, request.state.correlation_id)


@router.get("", response_model=DeletionList)
def listing(
    state: RequestState | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
) -> dict:
    with connection() as db:
        rows = db.execute(
            "SELECT id FROM deletion.requests WHERE (%s::text IS NULL OR state=%s) "
            "ORDER BY created_at,id LIMIT %s OFFSET %s",
            (state, state, limit, offset),
        ).fetchall()
        return {"items": [view(db, r["id"]) for r in rows], "limit": limit, "offset": offset}


class MetricRow(BaseModel):
    target: str
    state: str
    count: int
    attempts: int


class Metrics(BaseModel):
    tasks: list[MetricRow]
    retry_attempts: int


@router.get("/metrics", response_model=Metrics)
def metrics() -> dict:
    with connection() as db:
        rows = db.execute(
            "SELECT target,state,count(*) AS count,sum(attempt_count)::int AS attempts "
            "FROM deletion.tasks GROUP BY target,state ORDER BY target,state"
        ).fetchall()
        retries = db.execute(
            "SELECT count(*) AS n FROM deletion.attempts WHERE attempt_no>1"
        ).fetchone()["n"]
    return {"tasks": rows, "retry_attempts": retries}


@router.get("/{request_id}", response_model=DeletionView)
def status(request_id: UUID) -> dict:
    with connection() as db:
        return view(db, request_id)


@router.get("/{request_id}/events", response_model=list[AuditView])
def events(
    request_id: UUID, after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)
) -> list[dict]:
    with connection() as db:
        if not db.execute("SELECT 1 FROM deletion.requests WHERE id=%s", (request_id,)).fetchone():
            raise HTTPException(404, "deletion request not found")
        return db.execute(
            "SELECT * FROM deletion.events WHERE request_id=%s AND sequence>%s "
            "ORDER BY sequence LIMIT %s",
            (request_id, after, limit),
        ).fetchall()


@router.post("/{request_id}/retry", status_code=202, response_model=DeletionView)
def retry(request_id: UUID) -> dict:
    return retry_request(request_id)
