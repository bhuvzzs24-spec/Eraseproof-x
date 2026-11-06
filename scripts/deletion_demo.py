"""A real local-stack creation/propagation/deletion demonstration; no mocks."""

import json
import os
import time
from uuid import uuid4
import httpx

headers = {"X-Deletion-Token": os.environ["DELETION_TOKEN"]}
inspection = {"X-Inspection-Token": os.environ["INSPECTION_TOKEN"]}
base = "http://localhost:8005/v1/deletions"
suffix = uuid4().hex
with httpx.Client(timeout=20) as client:
    response = client.post(
        "http://localhost:8000/v1/customers",
        json={
            "name": f"Synthetic Deletion Demo {suffix[:8]}",
            "email": f"{suffix}@example.invalid",
        },
    )
    response.raise_for_status()
    customer = response.json()
    print("Customer:", customer["id"])
    for _ in range(90):
        response = client.get(
            f"http://localhost:8000/v1/customers/{customer['id']}/propagation", headers=inspection
        )
        response.raise_for_status()
        propagation = response.json()
        if all(s["state"] == "present" for s in propagation["stores"].values()):
            break
        time.sleep(1)
    else:
        raise SystemExit("Propagation did not complete; deletion not submitted.")
    response = client.post(
        base, headers=headers, json={"customer_id": customer["id"], "idempotency_key": suffix}
    )
    response.raise_for_status()
    request = response.json()
    print("Request:", request["id"])
    last = None
    for _ in range(180):
        response = client.get(f"{base}/{request['id']}", headers=headers)
        response.raise_for_status()
        state = response.json()
        if state["state"] != last:
            print("State:", state["state"])
            last = state["state"]
        if state["state"] in ("COMPLETED_REPORTED", "PARTIALLY_FAILED", "FAILED"):
            break
        time.sleep(1)
    else:
        raise SystemExit("Deletion remains in progress; inspect the durable request.")
    print(json.dumps(state, indent=2))
    response = client.get(f"{base}/{request['id']}/events", headers=headers)
    response.raise_for_status()
    print("Audit timeline:", json.dumps(response.json(), indent=2))
    print("Read-only observations (not independent proof):")
    for port in (8002, 8003, 8004):
        response = client.get(
            f"http://localhost:{port}/v1/inspect/customers/{customer['id']}", headers=inspection
        )
        print(port, response.status_code, response.text)
    if state["state"] != "COMPLETED_REPORTED":
        raise SystemExit(
            "Not all configured targets reported success. See task attempts and retry policy."
        )
    print("All configured workers reported success; independent verification belongs to Phase 3.")
