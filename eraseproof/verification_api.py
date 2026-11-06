import os
import secrets
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from eraseproof.db import connection
from eraseproof import verification
from eraseproof.verification_models import (
    StartVerification,
    VerificationView,
    EvidencePage,
    VerificationReport,
)


def authorize(x_verification_token: str = Header(default="")) -> None:
    expected = os.getenv("VERIFICATION_TOKEN", "")
    if (
        os.getenv("APP_ENV") != "demo"
        or len(expected) < 24
        or not secrets.compare_digest(expected, x_verification_token)
    ):
        raise HTTPException(403, "verification access disabled or unauthorized")


router = APIRouter(
    prefix="/v1", tags=["independent verification"], dependencies=[Depends(authorize)]
)


@router.post(
    "/deletions/{request_id}/verifications", status_code=202, response_model=VerificationView
)
def start(request_id: UUID, body: StartVerification, request: Request) -> dict:
    return verification.start(request_id, body, request.state.correlation_id)


@router.get("/deletions/{request_id}/verifications", response_model=list[VerificationView])
def history(
    request_id: UUID, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0, le=10000)
) -> list[dict]:
    with connection() as db:
        if not db.execute("SELECT 1 FROM deletion.requests WHERE id=%s", (request_id,)).fetchone():
            raise HTTPException(404, "deletion request not found")
        rows = db.execute(
            "SELECT id FROM verification.runs WHERE deletion_request_id=%s ORDER BY created_at,id LIMIT %s OFFSET %s",
            (request_id, limit, offset),
        ).fetchall()
        return [verification.view(db, row["id"]) for row in rows]


@router.get("/verifications/{run_id}", response_model=VerificationView)
def status(run_id: UUID) -> dict:
    with connection() as db:
        return verification.view(db, run_id)


@router.get("/verifications/{run_id}/evidence", response_model=EvidencePage)
def evidence(
    run_id: UUID, after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)
) -> dict:
    with connection() as db:
        verification.view(db, run_id)
        rows = db.execute(
            "SELECT * FROM verification.evidence WHERE run_id=%s AND sequence>%s ORDER BY sequence LIMIT %s",
            (run_id, after, limit),
        ).fetchall()
        return {"items": rows, "after": after, "limit": limit}


@router.get("/verifications/{run_id}/report", response_model=VerificationReport)
def report(run_id: UUID) -> dict:
    with connection() as db:
        return verification.report(db, run_id)


@router.get("/verifications/{run_id}/timeline")
def timeline(
    run_id: UUID, after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)
) -> dict:
    with connection() as db:
        verification.view(db, run_id)
        return {
            "items": db.execute(
                "SELECT * FROM verification.timeline WHERE run_id=%s AND sequence>%s ORDER BY sequence LIMIT %s",
                (run_id, after, limit),
            ).fetchall()
        }
