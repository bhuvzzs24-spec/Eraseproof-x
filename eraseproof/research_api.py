"""Read-only Phase 5 contracts. No route starts a trial or activates a fault."""

import os
import secrets
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from eraseproof.db import connection
from eraseproof.research_models import catalog
from eraseproof.research_metrics import summarize


def authorize(x_research_token: str = Header(default="")) -> None:
    expected = os.getenv("RESEARCH_TOKEN", "")
    if (
        os.getenv("APP_ENV") != "demo"
        or len(expected) < 24
        or not secrets.compare_digest(expected, x_research_token)
    ):
        raise HTTPException(403, "read-only research access disabled or unauthorized")


router = APIRouter(
    prefix="/v1/research", tags=["read-only research results"], dependencies=[Depends(authorize)]
)


@router.get("/scenarios")
def scenarios() -> dict:
    version, registry = catalog()
    return {"version": version, "items": [s.model_dump() for s in registry.values()]}


@router.get("/experiments")
def experiments(
    limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0, le=10000)
) -> dict:
    with connection() as db:
        return {
            "items": db.execute(
                "SELECT * FROM research.experiments ORDER BY created_at DESC,id LIMIT %s OFFSET %s",
                (limit, offset),
            ).fetchall()
        }


@router.get("/experiments/{experiment_id}")
def experiment(experiment_id: UUID) -> dict:
    with connection() as db:
        row = db.execute(
            "SELECT * FROM research.experiments WHERE id=%s", (experiment_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "experiment not found")
        return row


@router.get("/experiments/{experiment_id}/trials")
def trials(
    experiment_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10000),
) -> dict:
    with connection() as db:
        return {
            "items": db.execute(
                "SELECT body FROM research.trials WHERE experiment_id=%s ORDER BY logical_key,attempt LIMIT %s OFFSET %s",
                (experiment_id, limit, offset),
            ).fetchall()
        }


@router.get("/experiments/{experiment_id}/summary")
def summary(experiment_id: UUID) -> dict:
    with connection() as db:
        rows = db.execute(
            "SELECT body FROM research.trials WHERE experiment_id=%s ORDER BY logical_key,attempt LIMIT 1001",
            (experiment_id,),
        ).fetchall()
        if len(rows) > 1000:
            raise HTTPException(413, "export offline for larger experiments")
        return summarize([row["body"] for row in rows])
