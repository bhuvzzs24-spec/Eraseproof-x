from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class RequestState(StrEnum):
    REQUESTED = "REQUESTED"
    IN_PROGRESS = "IN_PROGRESS"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED_REPORTED"
    PARTIAL = "PARTIALLY_FAILED"
    FAILED = "FAILED"


class TaskState(StrEnum):
    PENDING = "PENDING"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED_REPORTED"
    RETRY_WAIT = "RETRY_WAIT"
    FAILED = "FAILED_TERMINAL"


TARGETS = ("customer", "orders", "cache", "search", "analytics", "event_history")
DEPENDENCIES = {"customer": ("orders", "event_history")}
REQUEST_TRANSITIONS = {
    RequestState.REQUESTED: {RequestState.IN_PROGRESS},
    RequestState.IN_PROGRESS: {
        RequestState.RETRYING,
        RequestState.COMPLETED,
        RequestState.PARTIAL,
        RequestState.FAILED,
    },
    RequestState.RETRYING: {RequestState.COMPLETED, RequestState.PARTIAL, RequestState.FAILED},
    RequestState.PARTIAL: {RequestState.RETRYING},
    RequestState.FAILED: {RequestState.RETRYING},
    RequestState.COMPLETED: set(),
}
TASK_TRANSITIONS = {
    TaskState.PENDING: {TaskState.DISPATCHED, TaskState.FAILED},
    TaskState.DISPATCHED: {TaskState.RUNNING, TaskState.RETRY_WAIT, TaskState.FAILED},
    TaskState.RUNNING: {TaskState.SUCCEEDED, TaskState.RETRY_WAIT, TaskState.FAILED},
    TaskState.RETRY_WAIT: {TaskState.DISPATCHED, TaskState.FAILED},
    TaskState.FAILED: {TaskState.PENDING},
    TaskState.SUCCEEDED: set(),
}


def validate_transition(old: str, new: str, *, task: bool = False) -> None:
    transitions = TASK_TRANSITIONS if task else REQUEST_TRANSITIONS
    if old != new and new not in transitions.get(old, set()):
        raise ValueError(f"invalid state transition: {old} -> {new}")


def aggregate(states: list[str], current: str) -> str:
    if len(states) != len(TARGETS):
        raise ValueError("incomplete target inventory")
    if all(s == TaskState.SUCCEEDED for s in states):
        return RequestState.COMPLETED
    if all(s in (TaskState.SUCCEEDED, TaskState.FAILED) for s in states):
        return RequestState.PARTIAL if TaskState.SUCCEEDED in states else RequestState.FAILED
    if TaskState.RETRY_WAIT in states or current == RequestState.RETRYING:
        return RequestState.RETRYING
    return RequestState.IN_PROGRESS


def retry_seconds(attempt: int, base: int = 2) -> int:
    return min(30, base * 2 ** min(max(attempt - 1, 0), 5))


class SubmitDeletion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")


class DeletionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    event_type: Literal["deletion.command"] = "deletion.command"
    event_id: UUID
    request_id: UUID
    task_id: UUID
    customer_id: UUID
    correlation_id: UUID
    target: Literal["customer", "orders", "cache", "search", "analytics", "event_history"]


class AttemptView(BaseModel):
    id: UUID
    attempt_no: int
    outcome: str
    worker_id: str | None
    failure_code: str | None
    dispatched_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None


class TaskView(BaseModel):
    id: UUID
    target: str
    state: TaskState
    attempt_count: int
    cycle_attempts: int
    max_attempts: int
    next_attempt_at: datetime
    lease_until: datetime | None
    last_failure_code: str | None
    attempts: list[AttemptView]


class DeletionView(BaseModel):
    id: UUID
    customer_id: UUID
    correlation_id: UUID
    state: RequestState
    schema_version: int
    actor: str
    retry_round: int
    created_at: datetime
    updated_at: datetime
    tasks: list[TaskView]
    independent_verification: Literal[False] = False


class DeletionList(BaseModel):
    items: list[DeletionView]
    limit: int
    offset: int


class AuditView(BaseModel):
    sequence: int
    request_id: UUID
    task_id: UUID | None
    kind: str
    from_state: str | None
    to_state: str | None
    code: str | None
    correlation_id: UUID
    actor: str
    occurred_at: datetime
