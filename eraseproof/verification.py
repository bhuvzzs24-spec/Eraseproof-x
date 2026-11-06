"""Verification control plane; data-plane probes are separately credentialed and read-only."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4
import json
import logging
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from eraseproof.db import connection
from eraseproof.evidence import canonical, digest, validate_chain
from eraseproof.verification_models import (
    StartVerification,
    VerificationCommand,
    Outcome,
    aggregate,
    consistency_result,
)
from eraseproof.verification_adapters import probe

log = logging.getLogger("verification")


def now() -> datetime:
    return datetime.now(timezone.utc)


def policy() -> dict:
    return json.loads(Path("policies/scope-v1.json").read_text())


def view(db, run_id: UUID) -> dict:
    run = db.execute("SELECT * FROM verification.runs WHERE id=%s", (run_id,)).fetchone()
    if not run:
        raise HTTPException(404, "verification run not found")
    targets = db.execute(
        "SELECT * FROM verification.targets WHERE run_id=%s ORDER BY target", (run_id,)
    ).fetchall()
    return {**run, "targets": targets, "claim": run["policy"]["claim"]}


def timeline(db, run_id: UUID, kind: str, code: str | None = None) -> None:
    db.execute(
        "INSERT INTO verification.timeline(run_id,kind,code) VALUES (%s,%s,%s)",
        (run_id, kind, code),
    )


def start(request_id: UUID, body: StartVerification, correlation_id: UUID) -> dict:
    hashed = sha256(("demo-verifier:" + body.idempotency_key).encode()).hexdigest()
    with connection() as db:
        db.execute("SELECT pg_advisory_xact_lock(7654323)")
        old = db.execute(
            "SELECT id FROM verification.runs WHERE deletion_request_id=%s AND idempotency_hash=%s",
            (request_id, hashed),
        ).fetchone()
        if old:
            return view(db, old["id"])
        request = db.execute(
            "SELECT customer_id FROM deletion.requests WHERE id=%s", (request_id,)
        ).fetchone()
        if not request:
            raise HTTPException(404, "deletion request not found")
        active = db.execute(
            "SELECT count(*) AS n FROM verification.runs WHERE state<>'FINISHED'"
        ).fetchone()["n"]
        recent = db.execute(
            "SELECT count(*) AS n FROM verification.runs WHERE created_at>now()-interval '1 minute'"
        ).fetchone()["n"]
        if active >= 10 or recent >= 30:
            raise HTTPException(
                429, "bounded verification capacity reached", headers={"Retry-After": "30"}
            )
        scope = policy()
        # Capture the union, not a user-selected subset. Missing/extra required adapters fail closed.
        actual = [
            r["target"]
            for r in db.execute(
                "SELECT target FROM deletion.tasks WHERE request_id=%s", (request_id,)
            ).fetchall()
        ]
        for target in actual:
            if target not in scope["targets"]:
                scope["targets"][target] = {
                    "required": True,
                    "category": "unknown",
                    "strategy": "unsupported",
                }
        run_id = uuid4()
        db.execute(
            "INSERT INTO verification.runs(id,deletion_request_id,customer_id,correlation_id,idempotency_hash,state,result,policy,policy_digest,deadline_at) "
            "VALUES (%s,%s,%s,%s,%s,'QUEUED','PENDING_CONSISTENCY',%s,%s,%s)",
            (
                run_id,
                request_id,
                request["customer_id"],
                correlation_id,
                hashed,
                Jsonb(scope),
                digest(scope),
                now() + timedelta(seconds=scope["deadline_seconds"]),
            ),
        )
        for target in scope["targets"]:
            db.execute(
                "INSERT INTO verification.targets(run_id,target) VALUES (%s,%s)", (run_id, target)
            )
        timeline(db, run_id, "verification.accepted", "demo-verifier")
        return view(db, run_id)


def enqueue(db, run: dict) -> None:
    command = VerificationCommand(event_id=uuid4(), run_id=run["id"], round_no=run["round_no"] + 1)
    db.execute(
        "UPDATE verification.runs SET state='RUNNING',round_no=%s,active_message=%s,lease_until=%s WHERE id=%s",
        (
            command.round_no,
            command.event_id,
            now() + timedelta(seconds=run["policy"]["lease_seconds"]),
            run["id"],
        ),
    )
    db.execute(
        "INSERT INTO delivery.outbox(id,aggregate_id,event_type,payload) VALUES (%s,%s,'verification.command',%s)",
        (command.event_id, run["customer_id"], Jsonb(command.model_dump(mode="json"))),
    )
    timeline(db, run["id"], "verification.dispatched")


def append_observation(db, run: dict, target: str, body: dict) -> None:
    last = db.execute(
        "SELECT sequence,digest FROM verification.evidence WHERE run_id=%s ORDER BY sequence DESC LIMIT 1",
        (run["id"],),
    ).fetchone()
    sequence = last["sequence"] + 1 if last else 1
    previous = last["digest"] if last else ""
    body = {**body, "sequence": sequence, "previous_digest": previous}
    safe = json.loads(canonical(body))
    db.execute(
        "INSERT INTO verification.evidence(id,run_id,sequence,target,round_no,body,digest,previous_digest) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            uuid4(),
            run["id"],
            sequence,
            target,
            run["round_no"],
            Jsonb(safe),
            digest(safe),
            previous,
        ),
    )


def expire(db, run: dict, code: str, terminal: bool) -> None:
    targets = db.execute(
        "SELECT * FROM verification.targets WHERE run_id=%s ORDER BY target", (run["id"],)
    ).fetchall()
    for target in targets:
        body = {
            "run_id": run["id"],
            "deletion_request_id": run["deletion_request_id"],
            "correlation_id": run["correlation_id"],
            "target": target["target"],
            "round_no": run["round_no"],
            "adapter": "coordinator.recovery",
            "adapter_version": "1",
            "policy_version": run["policy"]["version"],
            "policy_digest": run["policy_digest"],
            "query_category": "no_observation",
            "observed_at": now(),
            "raw_outcome": Outcome.INCONCLUSIVE,
            "result": Outcome.INCONCLUSIVE,
            "summary": {},
            "error_code": code,
            "query_count": 0,
            "duration_ms": 0,
            "scope_complete": False,
            "consistency": {"eligible": False, "deadline_at": run["deadline_at"]},
            "orchestration": {"state": "UNKNOWN"},
            "task_metadata": None,
        }
        append_observation(db, run, target["target"], body)
        db.execute(
            "UPDATE verification.targets SET result='INCONCLUSIVE',absent_streak=0,probe_failures=probe_failures+1,last_observed_at=now() WHERE run_id=%s AND target=%s",
            (run["id"], target["target"]),
        )
    db.execute(
        "UPDATE verification.runs SET state=%s,result=%s,next_check_at=%s,lease_until=NULL,finished_at=%s WHERE id=%s",
        (
            "FINISHED" if terminal else "WAITING",
            Outcome.INCONCLUSIVE,
            now() + timedelta(seconds=2),
            now() if terminal else None,
            run["id"],
        ),
    )
    timeline(db, run["id"], "verification.recovered", code)


def schedule_once() -> int:
    count = 0
    with connection() as db:
        runs = db.execute(
            "SELECT * FROM verification.runs WHERE state<>'FINISHED' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 10"
        ).fetchall()
        for run in runs:
            if run["state"] == "RUNNING":
                if run["lease_until"] < now():
                    expire(
                        db,
                        run,
                        "WORKER_LEASE_EXPIRED",
                        run["round_no"] >= run["policy"]["max_rounds"]
                        or now() >= run["deadline_at"],
                    )
                continue
            if run["next_check_at"] > now():
                continue
            if now() >= run["deadline_at"] or run["round_no"] >= run["policy"]["max_rounds"]:
                # A stalled scheduler is insufficient evidence, even if earlier checks were negative.
                db.execute(
                    "UPDATE verification.targets SET result='INCONCLUSIVE' WHERE run_id=%s AND result='PENDING_CONSISTENCY'",
                    (run["id"],),
                )
                results = {
                    t["target"]: t["result"]
                    for t in db.execute(
                        "SELECT target,result FROM verification.targets WHERE run_id=%s",
                        (run["id"],),
                    ).fetchall()
                }
                value = aggregate(results, set(run["policy"]["targets"]), "UNKNOWN")
                db.execute(
                    "UPDATE verification.runs SET state='FINISHED',result=%s,finished_at=now() WHERE id=%s",
                    (value, run["id"]),
                )
                timeline(db, run["id"], "verification.finished", "DEADLINE_OR_ROUND_LIMIT")
                continue
            enqueue(db, run)
            count += 1
    return count


def execute(command: VerificationCommand) -> bool:
    with connection() as db:
        run = db.execute(
            "SELECT * FROM verification.runs WHERE id=%s", (command.run_id,)
        ).fetchone()
        if (
            not run
            or run["state"] != "RUNNING"
            or run["active_message"] != command.event_id
            or run["round_no"] != command.round_no
        ):
            return False
        # Cross-process round lock prevents simultaneous duplicate probes/evidence.
        acquired = db.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s,9)) AS ok", (str(command.run_id),)
        ).fetchone()["ok"]
        if not acquired:
            return False
        # This session remains open for its advisory lock, not a data-store write transaction.
        timeline(db, run["id"], "verification.probing")
        db.commit()
        try:
            if digest(run["policy"]) != run["policy_digest"]:
                raise RuntimeError("scope integrity violation")
            observations = {
                t: probe(t, run["customer_id"], run["deletion_request_id"], s)
                for t, s in run["policy"]["targets"].items()
            }
            # Sample operational state only for consistency cutoff and contradiction classification.
            reported = db.execute(
                "SELECT state,updated_at FROM deletion.requests WHERE id=%s",
                (run["deletion_request_id"],),
            ).fetchone()
            metadata = {
                r["target"]: r
                for r in db.execute(
                    "SELECT id,target,state,attempt_count,active_attempt FROM deletion.tasks WHERE request_id=%s",
                    (run["deletion_request_id"],),
                ).fetchall()
            }
            db.commit()
            locked = db.execute(
                "SELECT * FROM verification.runs WHERE id=%s FOR UPDATE", (run["id"],)
            ).fetchone()
            if locked["state"] != "RUNNING" or locked["active_message"] != command.event_id:
                return False
            observed = now()
            previous = {
                r["target"]: r
                for r in db.execute(
                    "SELECT * FROM verification.targets WHERE run_id=%s", (run["id"],)
                ).fetchall()
            }
            results = {}
            retry_errors = False
            for target, observation in observations.items():
                prior = previous[target]
                result, streak, eligible = consistency_result(
                    observation.outcome,
                    reported_state=reported["state"],
                    anchor=reported["updated_at"],
                    observed_at=observation.observed_at,
                    created_at=run["created_at"],
                    grace_seconds=run["policy"]["grace_seconds"],
                    prior_streak=prior["absent_streak"],
                    prior_anchor=prior["consistency_anchor"],
                    minimum_samples=run["policy"]["absence_samples"],
                )
                failures = (
                    prior["probe_failures"] + 1
                    if observation.outcome == Outcome.INCONCLUSIVE
                    else 0
                )
                if (
                    observation.outcome == Outcome.INCONCLUSIVE
                    and failures < run["policy"]["max_probe_retries"]
                ):
                    retry_errors = True
                if observed > run["deadline_at"] and result in (Outcome.ABSENT, Outcome.PENDING):
                    result = Outcome.INCONCLUSIVE
                    observation.error_code = "DEADLINE_EXCEEDED"
                    retry_errors = False
                results[target] = result
                task = metadata.get(target)
                body = {
                    "run_id": run["id"],
                    "deletion_request_id": run["deletion_request_id"],
                    "correlation_id": run["correlation_id"],
                    "target": target,
                    "round_no": run["round_no"],
                    "adapter": observation.adapter,
                    "adapter_version": observation.adapter_version,
                    "policy_version": run["policy"]["version"],
                    "policy_digest": run["policy_digest"],
                    "query_category": run["policy"]["targets"][target]["strategy"],
                    "observed_at": observation.observed_at,
                    "raw_outcome": observation.outcome,
                    "result": result,
                    "summary": observation.summary,
                    "error_code": observation.error_code,
                    "scope_complete": observation.scope_complete,
                    "query_count": observation.query_count,
                    "duration_ms": observation.duration_ms,
                    "consistency": {
                        "eligible": eligible,
                        "absence_streak": streak,
                        "grace_seconds": run["policy"]["grace_seconds"],
                        "anchor_at": reported["updated_at"],
                        "deadline_at": run["deadline_at"],
                    },
                    "orchestration": {"state": reported["state"], "sampled_at": observed},
                    "task_metadata": task,
                }
                append_observation(db, run, target, body)
                db.execute(
                    "UPDATE verification.targets SET result=%s,absent_streak=%s,probe_failures=%s,last_observed_at=%s,consistency_anchor=%s WHERE run_id=%s AND target=%s",
                    (
                        result,
                        streak,
                        failures,
                        observation.observed_at,
                        reported["updated_at"],
                        run["id"],
                        target,
                    ),
                )
            value = aggregate(results, set(run["policy"]["targets"]), reported["state"])
            terminal = (
                value
                in (Outcome.ABSENT, Outcome.RESIDUAL, Outcome.FALSE_SUCCESS, Outcome.UNSUPPORTED)
                or (value == Outcome.INCONCLUSIVE and not retry_errors)
                or run["round_no"] >= run["policy"]["max_rounds"]
                or observed >= run["deadline_at"]
            )
            db.execute(
                "UPDATE verification.runs SET state=%s,result=%s,lease_until=NULL,next_check_at=%s,finished_at=%s WHERE id=%s",
                (
                    "FINISHED" if terminal else "WAITING",
                    value,
                    observed + timedelta(seconds=run["policy"]["interval_seconds"]),
                    observed if terminal else None,
                    run["id"],
                ),
            )
            timeline(
                db,
                run["id"],
                "verification.finished" if terminal else "verification.observed",
                value,
            )
            db.commit()  # all six observations and aggregate are atomic before ACK
            log.info(
                "verification.observed",
                extra={
                    "request_id": str(run["id"]),
                    "correlation_id": str(run["correlation_id"]),
                    "status": value,
                },
            )
            return True
        finally:
            db.execute("SELECT pg_advisory_unlock(hashtextextended(%s,9))", (str(command.run_id),))


def report(db, run_id: UUID) -> dict:
    run = view(db, run_id)
    records = db.execute(
        "SELECT * FROM verification.evidence WHERE run_id=%s ORDER BY sequence", (run_id,)
    ).fetchall()
    integrity = validate_chain(records)
    findings = []
    for record in records:
        body = record["body"]
        if body.get("result") == Outcome.RESIDUAL:
            findings.append(
                {
                    "target": body["target"],
                    "data_category": run["policy"]["targets"][body["target"]]["category"],
                    "observed_at": body["observed_at"],
                    "evidence_id": record["id"],
                    "evidence_digest": record["digest"],
                    "rule": "eligible personal data must be absent after consistency cutoff",
                    "task_metadata": body.get("task_metadata"),
                    "reported_state": body["orchestration"]["state"],
                    "false_success": body["orchestration"]["state"] == "COMPLETED_REPORTED",
                }
            )
    return {
        "verification": run,
        "evidence": records,
        "evidence_integrity": {
            "valid": integrity,
            "scheme": "sha256-canonical-json-per-run-chain",
            "administrator_rewrite_protection": False,
        },
        "findings": findings,
        "excluded_targets": run["policy"]["excluded"],
        "incomplete_targets": [
            t["target"]
            for t in run["targets"]
            if t["result"] in (Outcome.PENDING, Outcome.INCONCLUSIVE, Outcome.UNSUPPORTED)
        ],
        "timeline": db.execute(
            "SELECT * FROM verification.timeline WHERE run_id=%s ORDER BY sequence", (run_id,)
        ).fetchall(),
        "freshness": "Historical observations only. Rerun to detect subsequent reappearance.",
    }
