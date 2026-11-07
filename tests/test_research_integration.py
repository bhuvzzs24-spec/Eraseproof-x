"""Research control-plane integration; the actual multi-scenario benchmark runs as a CI step."""

import os
from uuid import uuid4
import httpx
import pytest
from test_integration import compose

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="requires actual Docker stack"),
]


def test_research_migration_and_read_only_dashboard():
    compose("run", "--rm", "migrate")
    assert httpx.get("http://localhost:8006/health/ready").status_code == 200
    base = "http://localhost:8006/v1/research"
    assert httpx.get(base + "/scenarios").status_code == 403
    headers = {"X-Research-Token": os.environ["RESEARCH_TOKEN"]}
    response = httpx.get(base + "/scenarios", headers=headers)
    assert response.status_code == 200 and len(response.json()["items"]) >= 12
    assert httpx.post(base + "/experiments", headers=headers, json={}).status_code == 405
    response = httpx.get(base + "/experiments", headers=headers)
    assert response.status_code == 200 and "items" in response.json()
    assert httpx.get(base + "/experiments/" + str(uuid4()), headers=headers).status_code == 404


def test_research_project_lease_prevents_concurrent_execution():
    from eraseproof.research_harness import Harness

    # No service sabotage occurs; only the separately marked research project's lease is exercised.
    old = os.environ.get("ERASEPROOF_RESEARCH_FAULTS")
    os.environ["ERASEPROOF_RESEARCH_FAULTS"] = "1"
    try:
        h = Harness(
            os.environ.get("COMPOSE_PROJECT_NAME", "ordinary-unmarked-project"), maximum_seconds=90
        )
        first, second, experiment = str(uuid4()), str(uuid4()), str(uuid4())
        h.bridge(
            "lease", project=h.project, executor_id=first, experiment_id=experiment, release=False
        )
        try:
            with pytest.raises(Exception):
                h.bridge(
                    "lease",
                    project=h.project,
                    executor_id=second,
                    experiment_id=experiment,
                    release=False,
                )
        finally:
            h.bridge(
                "lease",
                project=h.project,
                executor_id=first,
                experiment_id=experiment,
                release=True,
            )
        assert h.bridge(
            "lease", project=h.project, executor_id=second, experiment_id=experiment, release=False
        )["acquired"]
        h.bridge(
            "lease", project=h.project, executor_id=second, experiment_id=experiment, release=True
        )
    finally:
        if old is None:
            os.environ.pop("ERASEPROOF_RESEARCH_FAULTS", None)
        else:
            os.environ["ERASEPROOF_RESEARCH_FAULTS"] = old
