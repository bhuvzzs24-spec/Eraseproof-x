"""Bounded recovery helper for a killed harness. No public endpoint or arbitrary Docker command."""

import os
import subprocess
import sys
import time
from eraseproof.research_harness import Harness
from eraseproof.research_faults import control_lock


def main():
    project, service, container, ttl, token = sys.argv[1:]
    if service not in (
        "redis",
        "opensearch",
        "deletion-consumer",
        "verification-worker",
        "search-consumer",
        "analytics-consumer",
    ):
        raise ValueError("unsupported watchdog target")
    if container and not container.startswith(project + "-fault-"):
        raise ValueError("container is not an owned fault worker")
    time.sleep(min(90, max(1, int(ttl))))
    h = Harness(project, maximum_seconds=60)
    with control_lock(project, service):
        if not h.bridge("watchdog", mode="claim", project=project, service=service, token=token)[
            "owned"
        ]:
            return
        if container:
            result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    container,
                    "--format",
                    '{{index .Config.Labels "com.docker.compose.project"}}',
                ],
                text=True,
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip() == project:
                subprocess.run(
                    ["docker", "rm", "-f", container], check=True, capture_output=True, timeout=10
                )
        if service in ("redis", "opensearch"):
            # Docker returns a failure for an already unpaused container; that is harmless recovery.
            subprocess.run([*h.prefix, "unpause", service], capture_output=True, timeout=10)
        else:
            h.docker("start", service)


if __name__ == "__main__":
    if os.getenv("ERASEPROOF_RESEARCH_FAULTS") != "1":
        raise SystemExit("watchdog requires explicit research gate")
    main()
