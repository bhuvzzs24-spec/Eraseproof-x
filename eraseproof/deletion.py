"""Durable orchestration. Requests are serialized; useful work is never kept in memory only."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import UUID, uuid4
import os
import socket
import time
import logging
import psycopg
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from eraseproof.db import connection
from eraseproof.lifecycle import subject_lock, is_deleted
from eraseproof.deletion_models import (
    TARGETS,
    DEPENDENCIES,
    DeletionCommand,
    SubmitDeletion,
    RequestState,
    TaskState,
    aggregate,
    retry_seconds,
    validate_transition,
)
from eraseproof.deletion_connectors import ConnectorFailure, delete_target
from eraseproof.research_hooks import checkpoint

BASE_DELAY = max(1, int(os.getenv("DELETION_RETRY_BASE_SECONDS", "2")))
LEASE_SECONDS = max(10, int(os.getenv("DELETION_LEASE_SECONDS", "30")))
RATE_LIMIT = max(1, int(os.getenv("DELETION_RATE_LIMIT", "30")))
MAX_ATTEMPTS = 3
log = logging.getLogger("deletion.engine")


def now() -> datetime:
    return datetime.now(timezone.utc)


def key_hash(key: str) -> str:
    return sha256(("demo-operator:" + key).encode()).hexdigest()


def audit(
    db: psycopg.Connection,
    request: dict,
    kind: str,
    *,
    task: dict | None = None,
    old: str | None = None,
    new: str | None = None,
    code: str | None = None,
    actor: str = "scheduler",
) -> None:
    db.execute(
        "INSERT INTO deletion.events(request_id,task_id,kind,from_state,to_state,code,correlation_id,actor) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            request["id"],
            task["id"] if task else None,
            kind,
            old,
            new,
            code,
            request["correlation_id"],
            actor,
        ),
    )


def transition(
    db: psycopg.Connection,
    request: dict,
    new: str,
    *,
    task: dict | None = None,
    code: str | None = None,
    actor: str = "scheduler",
) -> None:
    row = task if task is not None else request
    old = row["state"]
    validate_transition(old, new, task=task is not None)
    if old == new:
        return
    if task is not None:
        db.execute(
            "UPDATE deletion.tasks SET state=%s,updated_at=now() WHERE id=%s", (new, row["id"])
        )
    else:
        db.execute(
            "UPDATE deletion.requests SET state=%s,updated_at=now() WHERE id=%s", (new, row["id"])
        )
    audit(
        db,
        request,
        "task.transition" if task else "request.transition",
        task=task,
        old=old,
        new=new,
        code=code,
        actor=actor,
    )
    log.info(
        "deletion.state",
        extra={
            "request_id": str(request["id"]),
            "correlation_id": str(request["correlation_id"]),
            "status": new,
            "target": task["target"] if task else "request",
            "failure_code": code,
        },
    )
    row["state"] = new


def view(db: psycopg.Connection, request_id: UUID) -> dict:
    request = db.execute(
        "SELECT * FROM deletion.requests WHERE id=%s FOR SHARE", (request_id,)
    ).fetchone()
    if request is None:
        raise HTTPException(404, "deletion request not found")
    tasks = db.execute(
        "SELECT * FROM deletion.tasks WHERE request_id=%s ORDER BY target", (request_id,)
    ).fetchall()
    for task in tasks:
        task["attempts"] = db.execute(
            "SELECT * FROM deletion.attempts WHERE task_id=%s ORDER BY attempt_no", (task["id"],)
        ).fetchall()
    return {**request, "tasks": tasks, "independent_verification": False}


def submit(body: SubmitDeletion, correlation_id: UUID) -> dict:
    hashed = key_hash(body.idempotency_key)
    with connection() as db:
        # Shared credential has one durable admission/rate-limit scope.
        db.execute("SELECT pg_advisory_xact_lock(7654322)")
        previous = db.execute(
            "SELECT r.* FROM deletion.idempotency_keys k JOIN deletion.requests r "
            "ON r.id=k.request_id WHERE k.key_hash=%s",
            (hashed,),
        ).fetchone()
        if previous:
            if previous["customer_id"] != body.customer_id:
                raise HTTPException(409, "idempotency key belongs to another customer")
            return view(db, previous["id"])
        subject_lock(db, body.customer_id)
        request = db.execute(
            "SELECT * FROM deletion.requests WHERE customer_id=%s FOR UPDATE", (body.customer_id,)
        ).fetchone()
        if request is None:
            count = db.execute(
                "SELECT count(*) AS n FROM deletion.requests WHERE created_at>now()-interval '1 minute'"
            ).fetchone()["n"]
            if count >= RATE_LIMIT:
                raise HTTPException(
                    429, "deletion admission rate exceeded", headers={"Retry-After": "60"}
                )
            source = db.execute(
                "SELECT name,email FROM customer.customers WHERE id=%s FOR UPDATE",
                (body.customer_id,),
            ).fetchone()
            if source is None:
                raise HTTPException(404, "synthetic customer not found")
            if not source["name"].startswith("Synthetic ") or not source["email"].endswith(
                "@example.invalid"
            ):
                raise HTTPException(409, "customer is outside the synthetic deletion scope")
            request_id = uuid4()
            request = db.execute(
                "INSERT INTO deletion.requests(id,customer_id,correlation_id,state,actor) "
                "VALUES (%s,%s,%s,'REQUESTED','demo-operator') RETURNING *",
                (request_id, body.customer_id, correlation_id),
            ).fetchone()
            db.execute(
                "INSERT INTO deletion.tombstones(customer_id,request_id) VALUES (%s,%s)",
                (body.customer_id, request_id),
            )
            # Capture opaque order IDs before de-identification destroys the association.
            db.execute(
                "INSERT INTO deletion.order_manifest(request_id,order_id) SELECT %s,id FROM orders.orders WHERE customer_id=%s",
                (request_id, body.customer_id),
            )
            db.execute(
                "INSERT INTO deletion.scope_captures(request_id,version) VALUES (%s,'scope-v1')",
                (request_id,),
            )
            for target in TARGETS:
                db.execute(
                    "INSERT INTO deletion.tasks(id,request_id,target,state,max_attempts) VALUES (%s,%s,%s,'PENDING',%s)",
                    (uuid4(), request_id, target, MAX_ATTEMPTS),
                )
            audit(db, request, "request.accepted", new="REQUESTED", actor="demo-operator")
        db.execute(
            "INSERT INTO deletion.idempotency_keys(key_hash,request_id) VALUES (%s,%s)",
            (hashed, request["id"]),
        )
        return view(db, request["id"])


def refresh(db: psycopg.Connection, request: dict, actor: str = "scheduler") -> None:
    states = [
        row["state"]
        for row in db.execute(
            "SELECT state FROM deletion.tasks WHERE request_id=%s", (request["id"],)
        ).fetchall()
    ]
    state = aggregate(states, request["state"])
    transition(db, request, state, actor=actor)
    if state == RequestState.COMPLETED:
        db.execute(
            "UPDATE deletion.tombstones SET lifecycle='DELETED',updated_at=now() WHERE request_id=%s",
            (request["id"],),
        )


def fail_attempt(
    db: psycopg.Connection,
    request: dict,
    task: dict,
    code: str,
    *,
    retryable: bool = True,
    duration_ms: int | None = None,
) -> None:
    state = (
        TaskState.RETRY_WAIT
        if retryable and task["cycle_attempts"] < task["max_attempts"]
        else TaskState.FAILED
    )
    transition(
        db,
        request,
        state,
        task=task,
        code=code,
        actor="worker" if duration_ms is not None else "scheduler",
    )
    due = now() + timedelta(seconds=retry_seconds(task["cycle_attempts"], BASE_DELAY))
    task["next_attempt_at"] = due
    db.execute(
        "UPDATE deletion.tasks SET last_failure_code=%s,lease_until=NULL,next_attempt_at=%s WHERE id=%s",
        (code, due, task["id"]),
    )
    db.execute(
        "UPDATE delivery.outbox SET cancelled_at=now() WHERE id=%s AND published_at IS NULL",
        (task["active_attempt"],),
    )
    db.execute(
        "UPDATE deletion.attempts SET outcome=%s,failure_code=%s,finished_at=now(),duration_ms=%s WHERE id=%s",
        (state, code, duration_ms, task["active_attempt"]),
    )


def schedule_once() -> int:
    dispatched = 0
    with connection() as db:
        requests = db.execute(
            "SELECT * FROM deletion.requests WHERE state IN ('REQUESTED','IN_PROGRESS','RETRYING') "
            "ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 20"
        ).fetchall()
        for request in requests:
            if request["state"] == RequestState.REQUESTED:
                transition(db, request, RequestState.IN_PROGRESS)
            tasks = db.execute(
                "SELECT * FROM deletion.tasks WHERE request_id=%s ORDER BY target FOR UPDATE",
                (request["id"],),
            ).fetchall()
            by_target = {t["target"]: t for t in tasks}
            for task in tasks:
                if (
                    task["state"] in (TaskState.DISPATCHED, TaskState.RUNNING)
                    and task["lease_until"] < now()
                ):
                    fail_attempt(db, request, task, "LEASE_EXPIRED")
                if (
                    task["state"] not in (TaskState.PENDING, TaskState.RETRY_WAIT)
                    or task["next_attempt_at"] > now()
                ):
                    continue
                prerequisites = [by_target[t] for t in DEPENDENCIES.get(task["target"], ())]
                if any(t["state"] == TaskState.FAILED for t in prerequisites):
                    transition(db, request, TaskState.FAILED, task=task, code="DEPENDENCY_FAILED")
                    db.execute(
                        "UPDATE deletion.tasks SET last_failure_code='DEPENDENCY_FAILED' WHERE id=%s",
                        (task["id"],),
                    )
                    continue
                if any(t["state"] != TaskState.SUCCEEDED for t in prerequisites):
                    continue
                attempt_id = uuid4()
                command = DeletionCommand(
                    event_id=attempt_id,
                    request_id=request["id"],
                    task_id=task["id"],
                    customer_id=request["customer_id"],
                    correlation_id=request["correlation_id"],
                    target=task["target"],
                )
                db.execute(
                    "INSERT INTO deletion.attempts(id,task_id,attempt_no,outcome) VALUES (%s,%s,%s,'DISPATCHED')",
                    (attempt_id, task["id"], task["attempt_count"] + 1),
                )
                transition(db, request, TaskState.DISPATCHED, task=task)
                db.execute(
                    "UPDATE deletion.tasks SET attempt_count=attempt_count+1,cycle_attempts=cycle_attempts+1,"
                    "active_attempt=%s,lease_until=%s WHERE id=%s",
                    (attempt_id, now() + timedelta(seconds=LEASE_SECONDS), task["id"]),
                )
                db.execute(
                    "INSERT INTO delivery.outbox(id,aggregate_id,event_type,payload) VALUES (%s,%s,'deletion.command',%s)",
                    (attempt_id, request["customer_id"], Jsonb(command.model_dump(mode="json"))),
                )
                dispatched += 1
            refresh(db, request)
    return dispatched


def command_matches(command: DeletionCommand, request: dict, task: dict | None) -> bool:
    return bool(
        task
        and task["request_id"] == request["id"]
        and task["target"] == command.target
        and request["customer_id"] == command.customer_id
        and request["correlation_id"] == command.correlation_id
        and task["active_attempt"] == command.event_id
    )


def execute_command(command: DeletionCommand) -> bool:
    # First commit RUNNING independently, so crashes leave a recoverable durable attempt.
    with connection() as db:
        request = db.execute(
            "SELECT * FROM deletion.requests WHERE id=%s FOR UPDATE", (command.request_id,)
        ).fetchone()
        if request is None:
            return False
        task = db.execute(
            "SELECT * FROM deletion.tasks WHERE id=%s FOR UPDATE", (command.task_id,)
        ).fetchone()
        if not command_matches(command, request, task) or task["state"] != TaskState.DISPATCHED:
            return False
        transition(db, request, TaskState.RUNNING, task=task, actor="worker")
        db.execute(
            "UPDATE deletion.attempts SET outcome='RUNNING',started_at=now(),worker_id=%s WHERE id=%s",
            (socket.gethostname(), command.event_id),
        )
    started = time.monotonic()
    with connection() as db:
        subject_lock(db, command.customer_id)
        request = db.execute(
            "SELECT * FROM deletion.requests WHERE id=%s FOR UPDATE", (command.request_id,)
        ).fetchone()
        task = db.execute(
            "SELECT * FROM deletion.tasks WHERE id=%s FOR UPDATE", (command.task_id,)
        ).fetchone()
        if not command_matches(command, request, task) or task["state"] != TaskState.RUNNING:
            return False  # stale lease/generation, never perform obsolete work
        if not is_deleted(db, command.customer_id):
            raise RuntimeError("deletion barrier missing")
        failure = None
        try:
            with (
                db.transaction()
            ):  # SQL connector errors roll back to a savepoint before recording failure
                if not checkpoint("deletion.before_connector", task["target"], command.customer_id):
                    delete_target(db, task["target"], command.customer_id)
                checkpoint("deletion.after_connector", task["target"], command.customer_id)
        except ConnectorFailure as exc:
            failure = exc
        except psycopg.Error:
            failure = ConnectorFailure("DATABASE_OPERATION_FAILED")
        duration = max(0, int((time.monotonic() - started) * 1000))
        if failure:
            fail_attempt(
                db, request, task, failure.code, retryable=failure.retryable, duration_ms=duration
            )
        else:
            transition(db, request, TaskState.SUCCEEDED, task=task, actor="worker")
            db.execute(
                "UPDATE deletion.tasks SET lease_until=NULL,last_failure_code=NULL WHERE id=%s",
                (task["id"],),
            )
            db.execute(
                "UPDATE deletion.attempts SET outcome='SUCCEEDED_REPORTED',finished_at=now(),duration_ms=%s WHERE id=%s",
                (duration, command.event_id),
            )
        refresh(db, request, "worker")
    return True  # ACK is allowed only after this transaction commits


def retry_request(request_id: UUID) -> dict:
    with connection() as db:
        request = db.execute(
            "SELECT * FROM deletion.requests WHERE id=%s FOR UPDATE", (request_id,)
        ).fetchone()
        if request is None:
            raise HTTPException(404, "deletion request not found")
        if request["state"] in (
            RequestState.REQUESTED,
            RequestState.IN_PROGRESS,
            RequestState.RETRYING,
        ):
            return view(db, request_id)  # duplicate retry is a bounded no-op
        if request["state"] == RequestState.COMPLETED:
            raise HTTPException(409, "completed orchestration cannot be retried")
        if request["retry_round"] >= 3:
            raise HTTPException(409, "manual retry budget exhausted")
        tasks = db.execute(
            "SELECT * FROM deletion.tasks WHERE request_id=%s AND state='FAILED_TERMINAL' FOR UPDATE",
            (request_id,),
        ).fetchall()
        if any(
            t["last_failure_code"]
            not in (
                "REDIS_UNAVAILABLE",
                "SEARCH_UNAVAILABLE",
                "DATABASE_OPERATION_FAILED",
                "LEASE_EXPIRED",
                "DEPENDENCY_FAILED",
            )
            for t in tasks
        ):
            raise HTTPException(409, "terminal failure is not retry eligible")
        transition(db, request, RequestState.RETRYING, actor="demo-operator")
        db.execute(
            "UPDATE deletion.requests SET retry_round=retry_round+1 WHERE id=%s", (request_id,)
        )
        for task in tasks:
            transition(db, request, TaskState.PENDING, task=task, actor="demo-operator")
            db.execute(
                "UPDATE deletion.tasks SET cycle_attempts=0,next_attempt_at=now(),lease_until=NULL,active_attempt=NULL,last_failure_code=NULL WHERE id=%s",
                (task["id"],),
            )
        return view(db, request_id)
