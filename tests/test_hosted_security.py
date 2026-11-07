"""Hosted account/session/privacy boundaries using real gateway sessions and credential files."""

import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from eraseproof import dashboard_gateway as gateway
from eraseproof import hosted_security as hs

ORIGIN = "https://demo.example.invalid"
PASSWORD = "Synthetic account test secret 2026"


@pytest.fixture
def hosted(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "STATE", tmp_path / "state")
    monkeypatch.setenv("DEPLOYMENT_MODE", "hosted")
    monkeypatch.setenv("APP_ENV", "demo")
    monkeypatch.setenv("DASHBOARD_ORIGIN", ORIGIN)
    monkeypatch.setenv("DASHBOARD_SECURE_COOKIE", "1")
    monkeypatch.setenv("DASHBOARD_PUBLIC_DEMO", "1")
    for k in (
        "DASHBOARD_ENABLE_RESEARCH",
        "ERASEPROOF_RESEARCH_FAULTS",
        "ENABLE_TEST_FAULTS",
        "ERASEPROOF_TEST_FAULTS",
    ):
        monkeypatch.setenv(k, "0")
    for k in ("INSPECTION_TOKEN", "DELETION_TOKEN", "VERIFICATION_TOKEN", "OPERATOR_TOKEN"):
        monkeypatch.setenv(k, "synthetic-test-" + k + "-" * 32)
    for role in gateway.ROLES:
        monkeypatch.delenv(f"DASHBOARD_{role.upper()}_PASSWORD", raising=False)
    for service in gateway.SERVICES:
        monkeypatch.setenv(f"DASHBOARD_{service.upper()}_ORIGIN", f"http://{service}:8000")
    users = tmp_path / "users.json"
    salt = "12" * 16
    users.write_text(
        json.dumps(
            {"owner": {"role": "operator", "salt": salt, "hash": hs.password_hash(PASSWORD, salt)}}
        )
    )
    monkeypatch.setenv("DASHBOARD_USERS_FILE", str(users))
    gateway.LOGIN_ATTEMPTS.clear()
    with TestClient(gateway.app, base_url=ORIGIN) as client:
        yield client, users


def login(client):
    response = client.post(
        "/api/session",
        headers={"Origin": ORIGIN},
        json={"username": "owner", "role": "operator", "password": PASSWORD},
    )
    assert response.status_code == 200
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf"]}, response


def test_hashed_account_secure_cookie_logout_and_revocation(hosted):
    client, users = hosted
    headers, response = login(client)
    cookie = response.headers["set-cookie"]
    assert (
        "__Host-eraseproof_session=" in cookie
        and "Secure" in cookie
        and "HttpOnly" in cookie
        and "SameSite=strict" in cookie
    )
    assert PASSWORD not in response.text and "Max-Age=3600" in cookie
    token = client.cookies.get("__Host-eraseproof_session")
    assert client.get("/api/session").json()["role"] == "operator"
    assert client.delete("/api/session", headers=headers).status_code == 200
    client.cookies.set("__Host-eraseproof_session", token)
    assert client.get("/api/session").status_code == 401
    client.cookies.clear()
    login(client)
    accounts = json.loads(users.read_text())
    accounts["owner"]["hash"] = "0" * 128
    users.write_text(json.dumps(accounts))
    assert client.get("/api/session").status_code == 401


def test_public_demo_is_real_read_only_and_cannot_choose_a_role(hosted):
    client, _ = hosted
    response = client.post(
        "/api/session/guest", json={"role": "research"}, headers={"Origin": ORIGIN}
    )
    assert (
        response.status_code == 200
        and response.json()["role"] == "readonly"
        and not response.json()["research_enabled"]
    )
    assert "Max-Age=900" in response.headers["set-cookie"]
    headers = {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf"]}
    assert client.get("/api/history/phase4-final").status_code == 200
    assert (
        client.post(
            "/api/live/customer/v1/customers",
            headers=headers,
            json={"name": "Synthetic Denied", "email": "denied@example.invalid"},
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
    assert client.get("/api/research/jobs").json() == {"items": []}


def test_server_rejects_role_escalation_bad_origin_host_and_csrf(hosted):
    client, _ = hosted
    assert (
        client.post(
            "/api/session",
            headers={"Origin": ORIGIN},
            json={"username": "owner", "role": "research", "password": PASSWORD},
        ).status_code
        == 401
    )
    headers, _ = login(client)
    assert (
        client.post(
            "/api/live/customer/v1/customers",
            headers={**headers, "Origin": "https://evil.invalid"},
            json={},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/live/customer/v1/customers", headers={"Origin": ORIGIN}, json={}
        ).status_code
        == 403
    )
    assert client.get("/api/access", headers={"Host": "evil.invalid"}).status_code == 400


def test_oversized_chunked_body_and_validation_never_echo_password(hosted):
    client, _ = hosted
    assert (
        client.post(
            "/api/session", content=iter([b"x" * 4096, b"x" * 4097]), headers={"Origin": ORIGIN}
        ).status_code
        == 413
    )
    response = client.post(
        "/api/session",
        json={"role": "operator", "username": "owner", "password": "secret-value-" * 30},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 422 and "secret-value" not in response.text


def test_login_limit_survives_process_local_counter_reset(hosted):
    client, _ = hosted
    for _ in range(10):
        gateway.LOGIN_ATTEMPTS.clear()
        assert (
            client.post(
                "/api/session",
                headers={"Origin": ORIGIN},
                json={"role": "operator", "username": "owner", "password": "wrong"},
            ).status_code
            == 401
        )
    gateway.LOGIN_ATTEMPTS.clear()
    assert (
        client.post(
            "/api/session",
            headers={"Origin": ORIGIN},
            json={"role": "operator", "username": "owner", "password": PASSWORD},
        ).status_code
        == 429
    )


def test_headers_and_audit_exclude_credentials(hosted):
    client, _ = hosted
    _, response = login(client)
    assert response.headers["strict-transport-security"] == "max-age=31536000"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "camera=()" in response.headers["permissions-policy"]
    with sqlite3.connect(gateway.STATE / "sessions.db") as db:
        text = repr(db.execute("SELECT * FROM access_audit").fetchall())
    assert PASSWORD not in text and "csrf" not in text and "POST" in text


def test_hosted_startup_rejects_faults_shared_passwords_and_missing_origins(hosted, monkeypatch):
    monkeypatch.setenv("ENABLE_TEST_FAULTS", "1")
    with pytest.raises(ValueError, match="fault execution"):
        hs.validate_hosted(True)
    monkeypatch.setenv("ENABLE_TEST_FAULTS", "0")
    monkeypatch.setenv("DASHBOARD_OPERATOR_PASSWORD", PASSWORD)
    with pytest.raises(ValueError, match="shared role"):
        hs.validate_hosted(True)
    monkeypatch.delenv("DASHBOARD_OPERATOR_PASSWORD")
    monkeypatch.delenv("DASHBOARD_CUSTOMER_ORIGIN")
    with pytest.raises(ValueError, match="private API"):
        hs.validate_hosted(True)


def test_disabled_public_access_and_removed_account_revoke_sessions(hosted, monkeypatch):
    client, users = hosted
    monkeypatch.setenv("DASHBOARD_PUBLIC_DEMO", "0")
    assert client.post("/api/session/guest", headers={"Origin": ORIGIN}).status_code == 403
    login(client)
    users.write_text(
        json.dumps({"another": {"role": "readonly", "salt": "12" * 16, "hash": "0" * 128}})
    )
    assert client.get("/api/session").status_code == 401
