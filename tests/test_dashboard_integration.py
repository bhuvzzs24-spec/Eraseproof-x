"""Actual Docker-backed dashboard read-model authorization and query contracts."""

import os
from uuid import uuid4
import httpx
import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="requires actual Docker stack"),
]
BASE = "http://127.0.0.1:8000/v1/dashboard"


def test_dashboard_read_models_are_authorized_bounded_and_actual():
    assert httpx.get(BASE + "/snapshot").status_code == 403
    headers = {"X-Inspection-Token": os.environ["INSPECTION_TOKEN"]}
    snapshot = httpx.get(BASE + "/snapshot", headers=headers, timeout=15)
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert isinstance(body["customer_count"], int) and body["customer_count"] >= 0
    assert all(row["count"] >= 0 for row in body["deletions"] + body["verifications"])
    assert "independent proof" in body["basis"]
    for name in ("customers", "deletions", "verifications"):
        response = httpx.get(
            BASE + "/" + name, headers=headers, params={"limit": 2, "offset": 0}, timeout=15
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) <= 2 and response.json()["total"] >= len(
            response.json()["items"]
        )
        assert (
            httpx.get(BASE + "/" + name, headers=headers, params={"limit": 101}).status_code == 422
        )


def test_dashboard_customer_search_reads_actual_synthetic_source():
    headers = {"X-Inspection-Token": os.environ["INSPECTION_TOKEN"]}
    response = httpx.post(
        "http://127.0.0.1:8000/v1/customers",
        json={
            "name": "Synthetic Dashboard Contract",
            "email": f"dashboard-contract-{uuid4()}@example.invalid",
        },
        timeout=15,
    )
    assert response.status_code == 201
    identifier = response.json()["id"]
    page = httpx.get(
        BASE + "/customers", headers=headers, params={"search": identifier}, timeout=15
    ).json()
    assert page["total"] == 1 and page["items"][0]["id"] == identifier
    assert page["items"][0]["lifecycle"] == "ACTIVE"
    assert "email" not in page["items"][0]
