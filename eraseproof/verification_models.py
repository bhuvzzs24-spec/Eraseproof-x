from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class Outcome(StrEnum):
    ABSENT = "VERIFIED_ABSENT"
    RESIDUAL = "RESIDUAL_DATA_DETECTED"
    PENDING = "PENDING_CONSISTENCY"
    INCONCLUSIVE = "INCONCLUSIVE"
    UNSUPPORTED = "UNSUPPORTED"
    FALSE_SUCCESS = "FALSE_SUCCESS_DETECTED"


class StartVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    policy_version: Literal["scope-v1"] = "scope-v1"
    consistency_profile: Literal["default", "extended"] = "default"


class VerificationCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: Literal["verification.command"] = "verification.command"
    version: Literal[1] = 1
    event_id: UUID
    run_id: UUID
    round_no: int = Field(ge=1, le=8)


class Probe(BaseModel):
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    outcome: Outcome
    adapter: str
    adapter_version: str = "1"
    category: str
    summary: dict[str, int | bool | str]
    query_count: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    error_code: str | None = None
    scope_complete: bool = True


class TargetView(BaseModel):
    target: str
    result: Outcome
    absent_streak: int
    probe_failures: int
    last_observed_at: datetime | None


class VerificationView(BaseModel):
    id: UUID
    deletion_request_id: UUID
    customer_id: UUID
    correlation_id: UUID
    state: Literal["QUEUED", "RUNNING", "WAITING", "FINISHED"]
    result: Outcome
    policy_digest: str
    policy: dict
    round_no: int
    created_at: datetime
    deadline_at: datetime
    finished_at: datetime | None
    targets: list[TargetView]
    claim: str


def aggregate(results: dict[str, str], required: set[str], reported_state: str) -> str:
    values = [results.get(t, Outcome.UNSUPPORTED) for t in required]
    if not values:
        return Outcome.INCONCLUSIVE
    if Outcome.RESIDUAL in values:
        return Outcome.FALSE_SUCCESS if reported_state == "COMPLETED_REPORTED" else Outcome.RESIDUAL
    if Outcome.UNSUPPORTED in values:
        return Outcome.UNSUPPORTED
    if Outcome.INCONCLUSIVE in values:
        return Outcome.INCONCLUSIVE
    if Outcome.PENDING in values:
        return Outcome.PENDING
    if all(v == Outcome.ABSENT for v in values):
        return Outcome.ABSENT
    return Outcome.INCONCLUSIVE


class EvidenceRecord(BaseModel):
    id: UUID
    run_id: UUID
    sequence: int
    target: str
    round_no: int
    body: dict
    digest: str
    previous_digest: str
    created_at: datetime


class EvidencePage(BaseModel):
    items: list[EvidenceRecord]
    after: int
    limit: int


class VerificationReport(BaseModel):
    verification: VerificationView
    evidence: list[EvidenceRecord]
    evidence_integrity: dict
    findings: list[dict]
    excluded_targets: list[str]
    incomplete_targets: list[str]
    timeline: list[dict]
    freshness: str


def consistency_result(
    raw: Outcome,
    *,
    reported_state: str,
    anchor: datetime,
    observed_at: datetime,
    created_at: datetime,
    grace_seconds: int,
    prior_streak: int,
    prior_anchor: datetime | None,
    minimum_samples: int,
) -> tuple[Outcome, int, bool]:
    from datetime import timedelta

    eligible = (
        reported_state in ("COMPLETED_REPORTED", "PARTIALLY_FAILED", "FAILED")
        and observed_at >= anchor + timedelta(seconds=grace_seconds)
        and observed_at >= created_at + timedelta(seconds=grace_seconds)
    )
    streak = (
        (prior_streak + 1 if prior_anchor == anchor else 1)
        if raw == Outcome.ABSENT and eligible
        else 0
    )
    if raw in (Outcome.ABSENT, Outcome.RESIDUAL) and (
        not eligible or (raw == Outcome.ABSENT and streak < minimum_samples)
    ):
        return Outcome.PENDING, streak, eligible
    return raw, streak, eligible
