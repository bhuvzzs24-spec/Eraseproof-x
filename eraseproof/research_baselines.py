"""Internal architectural monitors. These functions receive no oracle or store observations."""

REQUIRED = {"customer", "orders", "cache", "search", "analytics", "event_history"}


def api_acknowledgment(metadata: dict) -> dict:
    state = metadata.get("state", "UNKNOWN")
    prediction = (
        "ABSENT"
        if state == "COMPLETED_REPORTED"
        else "RESIDUAL"
        if state in ("PARTIALLY_FAILED", "FAILED")
        else "ABSTAIN"
    )
    return {
        "prediction": prediction,
        "outcome": state,
        "data_queries": 0,
        "basis": "final request API status; terminal failure is an operational incompleteness alarm, not direct residue evidence",
    }


def workflow_monitor(metadata: dict) -> dict:
    tasks = metadata.get("tasks", [])
    if {t.get("target") for t in tasks} != REQUIRED or len(tasks) != len(REQUIRED):
        return {"prediction": "ABSTAIN", "outcome": "INCOMPLETE_INVENTORY", "data_queries": 0}
    if any(t.get("state") == "FAILED_TERMINAL" for t in tasks):
        return {"prediction": "RESIDUAL", "outcome": "WORKFLOW_FAILURE_ALARM", "data_queries": 0}
    complete = metadata.get("state") == "COMPLETED_REPORTED" and all(
        t.get("state") == "SUCCEEDED_REPORTED" for t in tasks
    )
    for task in tasks:
        attempts = task.get("attempts", [])
        if not attempts or attempts[-1].get("outcome") != "SUCCEEDED_REPORTED":
            complete = False
    return {
        "prediction": "ABSENT" if complete else "ABSTAIN",
        "outcome": "WORKFLOW_COMPLETED" if complete else "WORKFLOW_PENDING",
        "data_queries": 0,
        "basis": "all required terminal task states and latest durable attempt outcome; recovered retries are accepted",
    }


def independent_prediction(report: dict) -> dict:
    verdict = report["verification"]["result"]
    prediction = (
        "ABSENT"
        if verdict == "VERIFIED_ABSENT"
        else "RESIDUAL"
        if verdict in ("RESIDUAL_DATA_DETECTED", "FALSE_SUCCESS_DETECTED")
        else "ABSTAIN"
    )
    observations = [r["body"] for r in report["evidence"]]
    return {
        "prediction": prediction,
        "outcome": verdict,
        "data_queries": sum(o["query_count"] for o in observations),
        "probe_duration_ms": sum(o["duration_ms"] for o in observations),
        "targets": {t["target"]: t["result"] for t in report["verification"]["targets"]},
        "evidence_digests": [r["digest"] for r in report["evidence"]],
        "false_success": verdict == "FALSE_SUCCESS_DETECTED",
    }
