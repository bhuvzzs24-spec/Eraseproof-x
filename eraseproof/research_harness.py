"""Bounded local Docker driver; refuses unmarked projects and non-loopback APIs."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid5, NAMESPACE_URL
import json
import os
import platform
import random
import subprocess
import time
import httpx

SERVICES = {
    "postgres",
    "redis",
    "rabbitmq",
    "opensearch",
    "customer",
    "order",
    "cache",
    "search",
    "analytics",
    "deletion",
    "publisher",
    "deletion-consumer",
    "deletion-scheduler",
    "cache-consumer",
    "search-consumer",
    "analytics-consumer",
    "verification",
    "verification-worker",
    "verification-scheduler",
}


class Harness:
    def __init__(self, project: str, concurrency: int = 1, maximum_seconds: int = 900):
        if os.getenv("APP_ENV", "demo") != "demo" or os.getenv("ERASEPROOF_RESEARCH_FAULTS") != "1":
            raise PermissionError("explicit isolated research opt-in required")
        if not project.startswith("eraseproof-research") or not project.replace("-", "").isalnum():
            raise PermissionError("refusing non-research Compose project")
        self.project = project
        self.concurrency = concurrency
        self.deadline = time.monotonic() + maximum_seconds
        self.prefix = [
            "docker",
            "compose",
            "-p",
            project,
            "-f",
            "compose.yaml",
            "-f",
            "compose.research.yaml",
        ]
        self.client = httpx.Client(timeout=15)
        self.tokens = {
            name: os.environ[name]
            for name in ("INSPECTION_TOKEN", "DELETION_TOKEN", "VERIFICATION_TOKEN")
        }
        self.validate_isolation()

    def remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("experiment execution budget exhausted")
        return remaining

    def docker(self, *args, timeout=30, **kwargs):
        return subprocess.run(
            [*self.prefix, *args],
            check=True,
            text=True,
            capture_output=True,
            timeout=max(1, min(timeout, self.remaining())),
            **kwargs,
        )

    def validate_isolation(self):
        endpoint = os.getenv("DOCKER_HOST")
        if endpoint is None:
            endpoint = json.loads(
                subprocess.run(
                    ["docker", "context", "inspect", "--format", "{{json .Endpoints.docker.Host}}"],
                    check=True,
                    text=True,
                    capture_output=True,
                    timeout=10,
                ).stdout
            )
        if not endpoint.startswith("unix://"):
            raise PermissionError("only a local Unix Docker engine is supported")
        config = json.loads(self.docker("config", "--format", "json").stdout)
        for name in SERVICES:
            if (
                config["services"][name].get("labels", {}).get("com.eraseproof.environment")
                != "synthetic-research"
            ):
                raise PermissionError("missing explicit synthetic research label")
        for name in (
            "customer",
            "order",
            "cache",
            "search",
            "analytics",
            "deletion",
            "verification",
            "postgres",
            "redis",
            "opensearch",
            "rabbitmq",
        ):
            ids = self.docker("ps", "-a", "-q", name).stdout.split()
            if len(ids) != 1:
                raise PermissionError("ambiguous or missing research service")
            labels = json.loads(
                subprocess.run(
                    ["docker", "inspect", ids[0], "--format", "{{json .Config.Labels}}"],
                    check=True,
                    text=True,
                    capture_output=True,
                    timeout=10,
                ).stdout
            )
            if (
                labels.get("com.docker.compose.project") != self.project
                or labels.get("com.eraseproof.environment") != "synthetic-research"
            ):
                raise PermissionError("container isolation labels do not match")
            ports = {
                "customer": 8000,
                "order": 8001,
                "cache": 8002,
                "search": 8003,
                "analytics": 8004,
                "deletion": 8005,
                "verification": 8006,
            }
            if name in ports:
                bindings = json.loads(
                    subprocess.run(
                        [
                            "docker",
                            "inspect",
                            ids[0],
                            "--format",
                            "{{json .NetworkSettings.Ports}}",
                        ],
                        check=True,
                        text=True,
                        capture_output=True,
                        timeout=10,
                    ).stdout
                )
                published = [b for values in bindings.values() if values for b in values]
                if not any(
                    b["HostIp"] == "127.0.0.1" and b["HostPort"] == str(ports[name])
                    for b in published
                ):
                    raise PermissionError("research APIs must use the verified local project ports")

    def bridge(self, operation: str, **data):
        request = {"operation": operation, **data}
        output = self.docker(
            "exec",
            "-T",
            "-e",
            "ENABLE_TEST_FAULTS=1",
            "-e",
            f"RESEARCH_ISOLATION_ID={self.project}",
            "customer",
            "python",
            "-m",
            "eraseproof.research_admin",
            input=json.dumps(request),
            timeout=30,
        ).stdout
        return json.loads(output)

    def oracle(self, fixture: dict, eligible: bool):
        output = self.docker(
            "exec",
            "-T",
            "-e",
            "ENABLE_TEST_FAULTS=1",
            "-e",
            f"RESEARCH_ISOLATION_ID={self.project}",
            "customer",
            "python",
            "-m",
            "eraseproof.research_oracle",
            input=json.dumps({"fixture": fixture, "eligible": eligible}),
            timeout=25,
        ).stdout
        return json.loads(output)

    def request(self, method: str, port: int, path: str, kind: str | None = None, **kwargs):
        headers = {f"X-{kind.title()}-Token": self.tokens[f"{kind.upper()}_TOKEN"]} if kind else {}
        if method == "POST" and os.getenv("OPERATOR_TOKEN"):
            headers["X-Operator-Token"] = os.environ["OPERATOR_TOKEN"]
        response = self.client.request(
            method,
            f"http://127.0.0.1:{port}{path}",
            headers=headers,
            timeout=min(15, self.remaining()),
            **kwargs,
        )
        if response.status_code == 429:
            time.sleep(min(3, self.remaining()))
            return self.request(method, port, path, kind, **kwargs)
        response.raise_for_status()
        return response.json()

    def wait(self, function, predicate, seconds=120):
        deadline = time.monotonic() + min(seconds, self.remaining())
        while time.monotonic() < deadline:
            value = function()
            if predicate(value):
                return value
            time.sleep(0.3)
        raise TimeoutError("bounded research phase did not converge")

    def fixture(self, trial_id: str, seed: int, index: int, orders: int, save):
        rng = random.Random(f"{seed}:{index}")
        identity = f"{trial_id[:12]}-{seed}-{index}"
        customer = self.request(
            "POST",
            8000,
            "/v1/customers",
            json={
                "name": f"Synthetic Research {seed} {index}",
                "email": f"research-{identity}@example.invalid",
            },
        )
        fixture = {
            "customer_id": customer["id"],
            "fixture_index": index,
            "synthetic_seed": seed,
            "order_ids": [],
            "order_event_ids": [],
            "fault_id": str(uuid5(NAMESPACE_URL, identity + ":fault")),
            "stale_event_id": str(uuid5(NAMESPACE_URL, identity + ":stale")),
            "correlation_id": str(uuid5(NAMESPACE_URL, identity + ":correlation")),
            "deletion_latency_seconds": None,
        }
        save(fixture)
        self.wait(
            lambda: self.request(
                "GET", 8000, f"/v1/customers/{customer['id']}/propagation", "inspection"
            ),
            lambda r: all(s["state"] == "present" for s in r["stores"].values()),
            seconds=90,
        )
        for _ in range(orders):
            order = self.request(
                "POST",
                8001,
                "/v1/orders",
                json={
                    "customer_id": customer["id"],
                    "fixture_index": index,
                    "synthetic_seed": seed,
                    "amount_cents": rng.randint(100, 20000),
                    "currency": "USD",
                },
            )
            fixture["order_ids"].append(order["id"])
            fixture["order_event_ids"].append(order["event_id"])
            save(fixture)
        self.wait(
            lambda: self.request(
                "GET", 8004, f"/v1/inspect/customers/{customer['id']}", "inspection"
            ),
            lambda r: {e["event_id"] for e in r["data"]} >= set(fixture["order_event_ids"]),
            seconds=90,
        )
        return fixture

    def submit(self, fixture: dict):
        started = time.monotonic()
        request = self.request(
            "POST",
            8005,
            "/v1/deletions",
            "deletion",
            json={"customer_id": fixture["customer_id"], "idempotency_key": fixture["fault_id"]},
        )
        fixture["deletion_request_id"] = request["id"]
        fixture["_deletion_started"] = started
        return request

    def deletion(self, fixture: dict):
        return self.request(
            "GET", 8005, f"/v1/deletions/{fixture['deletion_request_id']}", "deletion"
        )

    def wait_deletion(self, fixture: dict):
        status = self.wait(
            lambda: self.deletion(fixture),
            lambda r: r["state"] in ("COMPLETED_REPORTED", "PARTIALLY_FAILED", "FAILED"),
        )
        fixture["deletion_latency_seconds"] = time.monotonic() - fixture.pop(
            "_deletion_started", time.monotonic()
        )
        fixture["retry_attempts"] = sum(max(0, t["attempt_count"] - 1) for t in status["tasks"])
        return status

    def parallel(self, function, values):
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            return list(pool.map(function, values))

    def resources(self):
        try:
            ids = self.docker("ps", "-q").stdout.split()
            rows = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{json .}}", *ids],
                check=True,
                text=True,
                capture_output=True,
                timeout=15,
            ).stdout.splitlines()
            return {
                "samples": [json.loads(r) for r in rows],
                "kind": "Docker sampled CPU percent and memory usage; not peak or integrated CPU time",
            }
        except Exception as exc:
            return {"unavailable": type(exc).__name__}

    def environment(self):
        return {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "project": self.project,
            "docker": subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                check=True,
                text=True,
                capture_output=True,
                timeout=10,
            ).stdout.strip(),
            "stores": self.bridge("inspect_versions"),
        }
