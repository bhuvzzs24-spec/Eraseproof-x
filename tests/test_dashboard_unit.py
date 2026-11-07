"""Gateway security tests and validation of actual curated historical data, no fake measurements."""

import sqlite3
import pytest
from fastapi.testclient import TestClient
from eraseproof import dashboard_gateway as gateway

ORIGIN = "http://127.0.0.1:3000"
PASSWORD = "synthetic-test-credential-0123456789"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "STATE", tmp_path)
    monkeypatch.setenv("DASHBOARD_ORIGIN", ORIGIN)
    monkeypatch.setenv("APP_ENV", "demo")
    for role in gateway.ROLES:
        monkeypatch.setenv(f"DASHBOARD_{role.upper()}_PASSWORD", PASSWORD)
    gateway.LOGIN_ATTEMPTS.clear()
    return TestClient(gateway.app)


def sign_in(client, role="readonly"):
    response = client.post(
        "/api/session", json={"role": role, "password": PASSWORD}, headers={"Origin": ORIGIN}
    )
    assert response.status_code == 200
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf"]}


def test_anonymous_and_invalid_sessions_cannot_read(client):
    assert client.get("/api/history").status_code == 401
    client.cookies.set("eraseproof_session", "forged-research-role")
    assert client.get("/api/session").status_code == 401
    assert (
        client.post(
            "/api/session",
            json={"role": "research", "password": "wrong"},
            headers={"Origin": ORIGIN},
        ).status_code
        == 401
    )


def test_cookie_credentials_remain_server_side_and_logout_revokes(client):
    headers = sign_in(client)
    response = client.get("/api/session")
    assert response.json()["role"] == "readonly"
    assert PASSWORD not in response.text
    cookie = client.cookies.get("eraseproof_session")
    with sqlite3.connect(gateway.STATE / "sessions.db") as db:
        row = db.execute("SELECT digest FROM sessions").fetchone()
    assert cookie not in row[0] and len(row[0]) == 64
    assert client.delete("/api/session", headers=headers).status_code == 200
    assert client.get("/api/session").status_code == 401


def test_origin_csrf_and_role_authorization_are_enforced(client):
    headers = sign_in(client)
    assert (
        client.post(
            "/api/live/customer/v1/customers",
            headers=headers,
            json={"name": "Synthetic Test", "email": "test@example.invalid"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/research/jobs",
            headers=headers,
            json={"scenario": "false_ack_cache", "seed": 101, "acknowledge_isolated": True},
        ).status_code
        == 403
    )
    sign_in(client, "operator")
    assert (
        client.post(
            "/api/live/customer/v1/customers", headers={"Origin": ORIGIN}, json={}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/live/customer/v1/customers",
            headers={**headers, "Origin": "https://untrusted.invalid"},
            json={},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/session",
            headers={"Origin": "https://untrusted.invalid"},
            json={"role": "readonly", "password": PASSWORD},
        ).status_code
        == 403
    )


def test_fixed_proxy_rejects_arbitrary_paths_and_invalid_inputs(client, monkeypatch):
    headers = sign_in(client, "operator")
    assert client.get("/api/live/customer/v1/admin/secrets").status_code == 404
    assert client.get("/api/live/http://evil.invalid/").status_code == 404
    assert (
        client.post(
            "/api/live/customer/v1/customers",
            headers=headers,
            json={"name": "Real person", "email": "person@outside.invalid"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/live/customer/v1/customers",
            headers=headers,
            json={"name": "Synthetic Test", "email": "test@example.invalid", "unexpected": 1},
        ).status_code
        == 422
    )
    seen = []

    async def actual_shape(service, method, path, **kwargs):
        seen.append((service, method, path, kwargs["body"]))
        return {"id": "11111111-1111-4111-8111-111111111111"}

    monkeypatch.setattr(gateway, "upstream", actual_shape)
    response = client.post(
        "/api/live/customer/v1/customers",
        headers=headers,
        json={"name": "Synthetic Test", "email": "test@example.invalid"},
    )
    assert response.status_code == 201 and seen[0][:3] == ("customer", "POST", "/v1/customers")


def test_historical_aggregates_and_evidence_use_actual_validated_artifacts(client):
    sign_in(client)
    response = client.get("/api/history/phase4-final")
    assert response.status_code == 200
    data = response.json()
    assert (
        data["historical"]
        and data["experiment"]["code_commit"] == "61dd8e83c8a32d480dd7dc85d1a940ee8a879e46"
    )
    # Derive assertions from retained rows, not fabricated benchmark samples.
    positives = sum(p["oracle"]["state"] == "RESIDUAL" for t in data["trials"] for p in t["phases"])
    assert data["summary"]["methods"]["eraseproof"]["tp"] == positives
    run = data["trials"][0]["phases"][0]["verification_id"]
    report = client.get(f"/api/history/phase4-final/evidence/{run}")
    assert report.status_code == 200 and report.json()["verification"]["id"] == run
    assert "@example.invalid" not in report.text
    assert (
        client.get(
            "/api/history/phase4-final/evidence/11111111-1111-4111-8111-111111111111"
        ).status_code
        == 404
    )
    assert client.get("/api/history/arbitrary-file").status_code == 404
    initial = client.get("/api/history/phase4-initial").json()
    assert initial["summary"]["failed_trials"] > 0


def test_research_execution_requires_host_opt_in_and_real_isolation(client, monkeypatch):
    headers = sign_in(client, "research")
    body = {"scenario": "false_ack_cache", "seed": 101, "acknowledge_isolated": True}
    monkeypatch.setenv("DASHBOARD_ENABLE_RESEARCH", "0")
    assert client.post("/api/research/jobs", headers=headers, json=body).status_code == 403
    monkeypatch.setenv("DASHBOARD_ENABLE_RESEARCH", "1")
    monkeypatch.delenv("ERASEPROOF_RESEARCH_FAULTS", raising=False)
    assert client.post("/api/research/jobs", headers=headers, json=body).status_code == 409
    assert client.get("/api/research/jobs").json()["items"] == []
    assert (
        client.post(
            "/api/research/jobs", headers=headers, json={**body, "scenario": "run-any-shell"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/research/jobs", headers=headers, json={**body, "acknowledge_isolated": False}
        ).status_code
        == 422
    )


def test_login_rate_limit_and_cookie_flags(client):
    for _ in range(10):
        response = client.post(
            "/api/session",
            headers={"Origin": ORIGIN},
            json={"role": "readonly", "password": "invalid"},
        )
        assert response.status_code == 401
    assert (
        client.post(
            "/api/session",
            headers={"Origin": ORIGIN},
            json={"role": "readonly", "password": PASSWORD},
        ).status_code
        == 429
    )
    gateway.LOGIN_ATTEMPTS.clear()
    response = client.post(
        "/api/session", headers={"Origin": ORIGIN}, json={"role": "readonly", "password": PASSWORD}
    )
    assert (
        "HttpOnly" in response.headers["set-cookie"]
        and "SameSite=strict" in response.headers["set-cookie"]
    )


def test_no_raw_repository_files_are_served(client):
    sign_in(client)
    response = client.get("/.env")
    assert response.status_code in (200, 503)
    assert "POSTGRES_PASSWORD=" not in response.text
    assert client.get("/api/not-a-route").status_code == 404


def test_direct_source_writes_require_the_dashboard_operator_token(monkeypatch):
    from eraseproof.api import authorize_operator
    from fastapi import HTTPException

    monkeypatch.setenv("OPERATOR_TOKEN", PASSWORD)
    with pytest.raises(HTTPException):
        authorize_operator("")
    with pytest.raises(HTTPException):
        authorize_operator("readonly")
    authorize_operator(PASSWORD)
    monkeypatch.delenv("OPERATOR_TOKEN")
    authorize_operator("")  # existing trusted-lab scripts retain their documented mode


def test_upstream_timeout_remains_an_explicit_unknown_error(client, monkeypatch):
    import httpx

    sign_in(client)

    class TimeoutClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, *args, **kwargs):
            raise httpx.ReadTimeout("controlled transport timeout")

    monkeypatch.setattr(gateway.httpx, "AsyncClient", TimeoutClient)
    response = client.get("/api/live/customer/v1/dashboard/snapshot")
    assert response.status_code == 504
    assert "outcome is unknown" in response.json()["detail"]


def test_unknown_persisted_role_is_denied_by_default(client):
    sign_in(client)
    with sqlite3.connect(gateway.STATE / "sessions.db") as db:
        db.execute("UPDATE sessions SET role='unknown-role'")
    assert client.get("/api/session").status_code == 401
    assert client.get("/api/history").status_code == 401
