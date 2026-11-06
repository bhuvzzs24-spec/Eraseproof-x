"""Real creation -> deletion -> independent report. Optional explicitly gated residue/recovery."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4
import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--inject-synthetic-fault", action="store_true")
parser.add_argument("--output", default="work/verification-demo-report.json")
args = parser.parse_args()
if args.inject_synthetic_fault and (
    os.getenv("ERASEPROOF_TEST_FAULTS") != "1" or os.getenv("APP_ENV", "demo") != "demo"
):
    raise SystemExit("Synthetic fault requires ERASEPROOF_TEST_FAULTS=1 in demo environment.")
client = httpx.Client(timeout=20)
inspection = {"X-Inspection-Token": os.environ["INSPECTION_TOKEN"]}
deletion = {"X-Deletion-Token": os.environ["DELETION_TOKEN"]}
verification = {"X-Verification-Token": os.environ["VERIFICATION_TOKEN"]}
base = "http://localhost:8006/v1"


def checked(response):
    response.raise_for_status()
    return response.json()


def wait_for(url, headers, predicate, limit=180):
    for _ in range(limit):
        value = checked(client.get(url, headers=headers))
        if predicate(value):
            return value
        time.sleep(0.5)
    raise RuntimeError("bounded demo wait expired")


def verify(request):
    run = checked(
        client.post(
            f"{base}/deletions/{request['id']}/verifications",
            headers=verification,
            json={"idempotency_key": uuid4().hex},
        )
    )
    final = wait_for(
        f"{base}/verifications/{run['id']}", verification, lambda r: r["state"] == "FINISHED"
    )
    result = checked(client.get(f"{base}/verifications/{run['id']}/report", headers=verification))
    print("Verification:", run["id"], final["result"])
    for target in final["targets"]:
        print(target["target"], target["result"])
    return result


suffix = uuid4().hex
customer = checked(
    client.post(
        "http://localhost:8000/v1/customers",
        json={
            "name": f"Synthetic Verification Demo {suffix[:8]}",
            "email": f"{suffix}@example.invalid",
        },
    )
)
wait_for(
    f"http://localhost:8000/v1/customers/{customer['id']}/propagation",
    inspection,
    lambda r: all(s["state"] == "present" for s in r["stores"].values()),
)
request = checked(
    client.post(
        "http://localhost:8005/v1/deletions",
        headers=deletion,
        json={"customer_id": customer["id"], "idempotency_key": suffix},
    )
)
wait_for(
    f"http://localhost:8005/v1/deletions/{request['id']}",
    deletion,
    lambda r: r["state"] in ("COMPLETED_REPORTED", "PARTIALLY_FAILED", "FAILED"),
)
initial = verify(request)
reports = {"normal": initial}
if args.inject_synthetic_fault:
    # No fault endpoint or production bypass: the explicitly opted-in local driver uses admin access.
    def fault(enable):
        method = "set" if enable else "delete"
        code = f"""
import redis
from eraseproof.config import REDIS_URL
with redis.Redis.from_url(REDIS_URL) as c:
    c.{method}('customer:{customer["id"]}:demo-residual'{",'synthetic-residual'" if enable else ""})
"""
        subprocess.run(
            ["docker", "compose", "exec", "-T", "customer", "python", "-c", code], check=True
        )

    try:
        fault(True)
        reports["false_success"] = verify(request)
        if reports["false_success"]["verification"]["result"] != "FALSE_SUCCESS_DETECTED":
            raise RuntimeError("real residual was not classified as false success")
    finally:
        fault(False)
    reports["after_separate_remediation"] = verify(request)
output = Path(args.output)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(reports, indent=2) + "\n")
print("Sanitized evidence reports:", output.resolve())
print("Logical observations only; excluded backups/transport/media are not verified.")
