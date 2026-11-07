"""Explicitly gated ephemeral-worker fault points. Normal deployments always return False."""

import hashlib
import json
import logging
import os
from pathlib import Path
from uuid import UUID

POINTS = {"deletion.before_connector", "deletion.after_connector"}
ACTIONS = {"skip", "exit", "error_after"}


def checkpoint(point: str, target: str, subject: UUID) -> bool:
    if not (
        os.getenv("APP_ENV") == "demo"
        and os.getenv("ENABLE_TEST_FAULTS") == "1"
        and os.getenv("RESEARCH_ISOLATION_ID", "").startswith("eraseproof-research")
    ):
        return False
    if point not in POINTS or point != os.getenv("RESEARCH_HOOK_POINT"):
        return False
    if target not in os.getenv("RESEARCH_HOOK_TARGETS", "").split(","):
        return False
    try:
        subjects = {UUID(s) for s in os.getenv("RESEARCH_FAULT_SUBJECTS", "").split(",") if s}
    except ValueError:
        return False
    if not subjects or len(subjects) > 8 or subject not in subjects:
        return False
    action = os.getenv("RESEARCH_HOOK_ACTION", "")
    if action not in ACTIONS:
        return False
    record = {"point": point, "target": target, "subject": str(subject), "action": action}
    logging.getLogger("research.fault").warning(
        "research.fault.activated",
        extra={"target": target, "request_id": str(subject), "status": action},
    )
    stamp = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
    Path("/tmp/research-hook-" + stamp + ".json").write_text(json.dumps(record))
    if action == "exit":
        os._exit(86)
    if action == "error_after":
        from eraseproof.deletion_connectors import ConnectorFailure

        raise ConnectorFailure("REDIS_UNAVAILABLE" if target == "cache" else "SEARCH_UNAVAILABLE")
    return action == "skip"
