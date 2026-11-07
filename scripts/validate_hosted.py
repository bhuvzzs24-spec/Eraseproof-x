"""Actual hosted-stack qualification on isolated CI; no fabricated observations or public deployment."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import statistics
import subprocess
import sys
import time
from uuid import uuid4
import httpx
from eraseproof.hosted_security import password_hash
from hosted_ops import command, values

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / "work/hosted-ci"
ENV = PRIVATE / "hosted.env"
ORIGIN = "https://demo.example.invalid"


def prepare():
    subprocess.run(
        [
            sys.executable,
            "scripts/configure_hosted.py",
            "--domain",
            "demo.example.invalid",
            "--email",
            "ci@example.invalid",
            "--directory",
            str(PRIVATE),
        ],
        check=True,
        cwd=ROOT,
    )
    password = secrets.token_urlsafe(32)
    salt = secrets.token_hex(16)
    (PRIVATE / "users.json").write_text(
        json.dumps(
            {"owner": {"role": "operator", "salt": salt, "hash": password_hash(password, salt)}}
        )
    )
    (PRIVATE / "test-credentials.json").write_text(
        json.dumps({"username": "owner", "password": password})
    )
    for name in ("users.json", "test-credentials.json"):
        (PRIVATE / name).chmod(0o600)
    if os.geteuid() == 0:
        os.chown(PRIVATE / "users.json", 10001, 10001)
    # The public demo is read-only; all binds remain loopback through the CI override.
    with ENV.open("a") as file:
        file.write("DASHBOARD_PUBLIC_DEMO=1\n")
    if os.getenv("GITHUB_ACTIONS") == "true":
        for key, value in values(ENV).items():
            if key.endswith(("_PASSWORD", "_TOKEN")):
                print("::add-mask::" + value)
        print("::add-mask::" + password)
    print("Private CI configuration prepared; no credentials printed")


def wait(function, predicate, seconds=120):
    end = time.monotonic() + seconds
    last = None
    while time.monotonic() < end:
        try:
            last = function()
            if predicate(last):
                return last
        except (httpx.HTTPError, ValueError, KeyError):
            pass
        time.sleep(1)
    raise AssertionError("actual state did not converge within the declared budget")


def run(args):
    opts = argparse.Namespace(env_file=ENV, project="eraseproof-hosted-ci", ci=True)
    cmd = command(opts)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "publication": "not performed; local CI certificate and loopback bindings only",
        "checks": [],
        "api_samples_seconds": [],
    }
    if args.start:
        started = time.monotonic()
        subprocess.run(
            cmd + ["--profile", "publish", "up", "-d", "--wait", "--wait-timeout", "240"],
            check=True,
            timeout=300,
        )
        (PRIVATE / "startup.json").write_text(
            json.dumps(
                {
                    "compose_start_to_all_ready_seconds": time.monotonic() - started,
                    "includes": "container creation, dependency ordering and readiness; images built/pulled separately",
                }
            )
        )
        return
    if not args.ca:
        raise ValueError(
            "explicit local CA certificate required; TLS verification is never disabled"
        )
    credentials = json.loads((PRIVATE / "test-credentials.json").read_text())
    with httpx.Client(base_url=ORIGIN, verify=str(args.ca), timeout=20) as client:

        def request(method, path, body=None, csrf=None):
            headers = {"Origin": ORIGIN}
            if csrf:
                headers["X-CSRF-Token"] = csrf
            started = time.monotonic()
            result = client.request(method, path, json=body, headers=headers)
            elapsed = time.monotonic() - started
            report["api_samples_seconds"].append(
                {
                    "path": path.split("?")[0],
                    "status": result.status_code,
                    "elapsed_seconds": elapsed,
                }
            )
            return result

        assert request("GET", "/health/ready").status_code == 200
        assert request("GET", "/api/history").status_code == 401
        guest = request("POST", "/api/session/guest").json()
        assert guest["role"] == "readonly"
        assert request("GET", "/api/history/phase4-final").status_code == 200
        assert (
            request("POST", "/api/live/deletion/v1/deletions", {}, guest["csrf"]).status_code == 403
        )
        assert (
            request(
                "POST",
                "/api/research/jobs",
                {"scenario": "false_ack_cache", "seed": 101, "acknowledge_isolated": True},
                guest["csrf"],
            ).status_code
            == 403
        )
        report["checks"].append(
            "anonymous cannot read protected data; explicit guest session cannot delete or inject faults"
        )
        client.cookies.clear()
        response = request("POST", "/api/session", {**credentials, "role": "operator"})
        assert response.status_code == 200 and "Secure" in response.headers["set-cookie"]
        csrf = response.json()["csrf"]
        ready = request("GET", "/api/health").json()
        assert sum(x["state"] == "ready" for x in ready["items"]) == 7
        customer = request(
            "POST",
            "/api/live/customer/v1/customers",
            {
                "name": "Synthetic Hosted Qualification",
                "email": f"qualification-{uuid4()}@example.invalid",
            },
            csrf,
        )
        assert customer.status_code == 201
        identifier = customer.json()["id"]
        wait(
            lambda: request(
                "GET", f"/api/live/customer/v1/customers/{identifier}/propagation"
            ).json(),
            lambda x: x["source_present"]
            and all(v["state"] == "present" for v in x["stores"].values()),
        )
        assert (
            request(
                "POST",
                "/api/live/order/v1/orders",
                {"customer_id": identifier, "amount_cents": 1234, "currency": "USD"},
                csrf,
            ).status_code
            == 201
        )
        footprint = request(
            "GET", f"/api/live/customer/v1/dashboard/customers/{identifier}/footprint"
        ).json()
        assert footprint["orders"]["total"] == 1
        deletion = request(
            "POST",
            "/api/live/deletion/v1/deletions",
            {"customer_id": identifier, "idempotency_key": "hosted-qualification:" + identifier},
            csrf,
        )
        assert deletion.status_code == 202
        deletion_id = deletion.json()["id"]
        wait(
            lambda: request("GET", f"/api/live/deletion/v1/deletions/{deletion_id}").json(),
            lambda x: x["state"] == "COMPLETED_REPORTED",
        )

        def verify():
            started = request(
                "POST",
                f"/api/live/verification/v1/deletions/{deletion_id}/verifications",
                {"idempotency_key": str(uuid4()), "consistency_profile": "default"},
                csrf,
            )
            assert started.status_code == 202
            run_id = started.json()["id"]
            body = wait(
                lambda: request(
                    "GET", f"/api/live/verification/v1/verifications/{run_id}/report"
                ).json(),
                lambda x: x["verification"]["state"] == "FINISHED",
            )
            assert body["verification"]["result"] == "VERIFIED_ABSENT", body["verification"][
                "result"
            ]
            assert len(body["verification"]["targets"]) == 6 and all(
                t["result"] == "VERIFIED_ABSENT" for t in body["verification"]["targets"]
            )
            assert "@example.invalid" not in json.dumps(body)
            return body

        report["before_restart_verification"] = verify()
        report["checks"].append(
            "real customer/order propagation, deletion, six-target independent absence and sanitized export"
        )
        backup_customer = request(
            "POST",
            "/api/live/customer/v1/customers",
            {
                "name": "Synthetic Backup Qualification",
                "email": f"backup-{uuid4()}@example.invalid",
            },
            csrf,
        ).json()["id"]
        backup = PRIVATE / "qualification.dump"
        ops = [sys.executable, "scripts/hosted_ops.py"]
        shared = ["--env-file", str(ENV), "--project", opts.project, "--ci"]
        subprocess.run(
            ops
            + ["backup", *shared, "--backup", str(backup), "--output", "work/phase6-backup.json"],
            check=True,
            cwd=ROOT,
        )
        subprocess.run(
            ops
            + [
                "restore-test",
                *shared,
                "--backup",
                str(backup),
                "--expected-customer",
                backup_customer,
                "--output",
                "work/phase6-restore.json",
            ],
            check=True,
            cwd=ROOT,
        )
        report["checks"].append(
            "real PostgreSQL custom backup restored into a separate scratch database; four migrations and expected synthetic fixture verified; scratch removed"
        )
        restarted = [
            "customer",
            "cache-consumer",
            "verification-worker",
            "redis",
            "rabbitmq",
            "postgres",
            "gateway",
        ]
        started = time.monotonic()
        subprocess.run(cmd + ["restart", *restarted], check=True, timeout=120)
        wait(
            lambda: request("GET", "/api/health").json(),
            lambda x: len(x.get("items", [])) == 7
            and all(i["state"] == "ready" for i in x["items"]),
            seconds=180,
        )
        assert request("GET", "/api/session").status_code == 200
        report["restart_to_api_ready_seconds"] = time.monotonic() - started
        report["after_restart_verification"] = verify()
        report["checks"].append(
            "API, worker, PostgreSQL, Redis, broker and gateway restart/reconnect; persisted session and fresh six-target verification passed"
        )
        # Independent probe identity must have no write capability.
        code = "import httpx,os; from urllib.parse import urlsplit; secret=urlsplit(os.environ['VERIFIER_SEARCH_URL']).password; r=httpx.delete('http://search-reader:9200/customers',auth=('verification',secret)); assert r.status_code==403"
        subprocess.run(
            cmd
            + [
                "exec",
                "-T",
                "verification-worker",
                "python",
                "-c",
                code,
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        dbcode = "from eraseproof.db import connection\nwith connection() as d:\n r=d.execute('SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user').fetchone();assert not any(r.values())\n try:d.execute('CREATE TABLE public.forbidden(x int)')\n except __import__('psycopg').errors.InsufficientPrivilege:pass\n else:raise AssertionError('DDL permission leaked')"
        subprocess.run(
            cmd + ["exec", "-T", "customer", "python", "-c", dbcode],
            check=True,
            capture_output=True,
            timeout=30,
        )
        report["checks"].append(
            "runtime database role has no superuser/role/database/DDL privilege; OpenSearch read credential cannot delete an index"
        )
        for _ in range(10):
            response = request("GET", "/api/live/customer/v1/dashboard/verifications?limit=100")
            assert response.status_code == 200 and response.json()["total"] >= 2
        response = request("DELETE", "/api/session", csrf=csrf)
        assert response.status_code == 200 and request("GET", "/api/session").status_code == 401
        report["checks"].append("logout revokes session server-side")
    samples = [r["elapsed_seconds"] for r in report["api_samples_seconds"]]
    report["api_latency"] = {
        "n": len(samples),
        "median_seconds": statistics.median(samples),
        "max_seconds": max(samples),
        "basis": "CI client wall time over mixed gateway, polling and mutation requests; not a production throughput estimate",
    }
    report["resource_snapshot"] = [
        json.loads(line)
        for line in subprocess.check_output(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}"], text=True, timeout=30
        ).splitlines()
        if line
    ]
    report["startup"] = json.loads((PRIVATE / "startup.json").read_text())
    Path("work/phase6-hosted-validation.json").write_text(json.dumps(report, indent=2))
    print(
        "Actual hosted qualification passed:",
        len(report["checks"]),
        "check groups; private local TLS certificate verified",
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--prepare", action="store_true")
    p.add_argument("--start", action="store_true")
    p.add_argument("--ca", type=Path)
    args = p.parse_args()
    prepare() if args.prepare else run(args)
