"""Reversible administrative controls with durable intent records and bounded watchdogs."""

from contextlib import contextmanager
from uuid import uuid4
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import time


@contextmanager
def control_lock(project: str, service: str):
    folder = (
        Path("/private/tmp" if sys.platform == "darwin" else "/tmp") / "eraseproof-research-locks"
    )
    folder.mkdir(mode=0o700, exist_ok=True)
    with (folder / (project + "-" + service + ".lock")).open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


class Faults:
    def __init__(self, harness, trial: dict, save):
        self.h = harness
        self.trial = trial
        self.save = save
        self.processes = []
        trial.setdefault("faults", [])
        trial.setdefault("paused", [])
        trial.setdefault("stopped", [])
        trial.setdefault("oneoffs", [])

    def event(self, event_action: str, state: str, **details):
        self.trial["faults"].append(
            {"action": event_action, "state": state, "at_unix": time.time(), **details}
        )
        self.save()

    def watchdog(self, service: str, container: str | None = None):
        token = str(uuid4())
        self.h.bridge(
            "watchdog", mode="register", project=self.h.project, service=service, token=token
        )
        self.trial.setdefault("watchdogs", []).append({"service": service, "token": token})
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "eraseproof.research_watchdog",
                self.h.project,
                service,
                container or "",
                str(90),
                token,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self.processes.append(process)
        self.event("watchdog", "STARTED", service=service, pid=process.pid, maximum_seconds=90)

    def pause(self, service: str):
        if service not in ("redis", "opensearch"):
            raise ValueError("unsupported pause target")
        if service not in self.trial["paused"]:
            self.trial["paused"].append(service)
        self.event("pause", "INTENDED", service=service)
        with control_lock(self.h.project, service):
            self.watchdog(service)
            self.h.docker("pause", service)
        self.event("pause", "ACTIVATED", service=service)

    def stop(self, service: str):
        if service not in (
            "deletion-consumer",
            "verification-worker",
            "search-consumer",
            "analytics-consumer",
        ):
            raise ValueError("unsupported stop target")
        if service not in self.trial["stopped"]:
            self.trial["stopped"].append(service)
        self.event("stop", "INTENDED", service=service)
        with control_lock(self.h.project, service):
            self.watchdog(service)
            self.h.docker("stop", "-t", "3", service)
        self.event("stop", "ACTIVATED", service=service)

    def restore(self):
        errors = []
        # Cleanup has its own bounded allowance even after the experiment budget expires.
        old = self.h.deadline
        self.h.deadline = max(old, time.monotonic() + 45)
        try:
            for process in self.processes:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=3)
            for watch in self.trial.get("watchdogs", []):
                with control_lock(self.h.project, watch["service"]):
                    self.h.bridge(
                        "watchdog",
                        mode="claim",
                        project=self.h.project,
                        service=watch["service"],
                        token=watch["token"],
                    )
            for service in list(self.trial.get("paused", [])):
                try:
                    self.h.docker("unpause", service)
                    self.trial["paused"].remove(service)
                    self.event("unpause", "RESTORED", service=service)
                except Exception as exc:
                    errors.append(type(exc).__name__)
            for container in list(self.trial.get("oneoffs", [])):
                try:
                    subprocess.run(
                        ["docker", "rm", "-f", container],
                        check=True,
                        text=True,
                        capture_output=True,
                        timeout=10,
                    )
                    self.trial["oneoffs"].remove(container)
                except Exception as exc:
                    errors.append(type(exc).__name__)
            for service in list(self.trial.get("stopped", [])):
                try:
                    self.h.docker("start", service)
                    self.trial["stopped"].remove(service)
                    self.event("start", "RESTORED", service=service)
                except Exception as exc:
                    errors.append(type(exc).__name__)
        finally:
            self.h.deadline = old
            self.save()
        if errors:
            self.event("cleanup", "ERROR", error_classes=errors)
        return errors

    def ephemeral(self, action: str, targets: list[str], point: str):
        self.stop("deletion-consumer")
        name = self.h.project + "-fault-" + self.trial["id"][:12]
        self.trial["oneoffs"].append(name)
        self.event(action, "INTENDED", container=name, targets=targets, point=point)
        subjects = ",".join(f["customer_id"] for f in self.trial["fixtures"])
        self.h.docker(
            "run",
            "--no-deps",
            "-d",
            "--name",
            name,
            "-e",
            "ENABLE_TEST_FAULTS=1",
            "-e",
            f"RESEARCH_ISOLATION_ID={self.h.project}",
            "-e",
            f"RESEARCH_HOOK_ACTION={action}",
            "-e",
            f"RESEARCH_HOOK_TARGETS={','.join(targets)}",
            "-e",
            f"RESEARCH_HOOK_POINT={point}",
            "-e",
            f"RESEARCH_FAULT_SUBJECTS={subjects}",
            "deletion-consumer",
            timeout=30,
        )
        self.watchdog("deletion-consumer", name)
        return name

    def attest(self, container: str):
        output = subprocess.run(
            ["docker", "logs", container], check=True, text=True, capture_output=True, timeout=10
        )
        records = []
        for line in (output.stdout + "\n" + output.stderr).splitlines():
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if value.get("message") == "research.fault.activated":
                records.append(value)
        if not records:
            raise AssertionError("configured fault did not actually activate")
        self.event("hook", "OBSERVED", records=records)

    def wait_crash(self, container: str):
        value = self.h.wait(
            lambda: json.loads(
                subprocess.run(
                    ["docker", "inspect", container, "--format", "{{json .State}}"],
                    check=True,
                    text=True,
                    capture_output=True,
                    timeout=10,
                ).stdout
            ),
            lambda state: not state["Running"],
            seconds=45,
        )
        if value["ExitCode"] != 86:
            raise AssertionError("worker did not exit at the configured mutation boundary")
        self.attest(container)
        self.event("consumer_crash", "OBSERVED", exit_code=86)
        self.restore()
