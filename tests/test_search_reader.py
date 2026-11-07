"""Read gateway rejects administration/writes, scripts, excessive reads and missing credentials."""

import base64
from fastapi.testclient import TestClient
from eraseproof import search_reader


def test_read_boundary_blocks_writes_and_arbitrary_search(monkeypatch):
    password = "synthetic-search-credential-" + "x" * 32
    monkeypatch.setenv("VERIFIER_SEARCH_PASSWORD", password)
    client = TestClient(search_reader.app)
    headers = {
        "Authorization": "Basic " + base64.b64encode(("verification:" + password).encode()).decode()
    }
    identifier = "11111111-1111-4111-8111-111111111111"
    assert client.get("/customers/_doc/" + identifier).status_code == 403
    for method, path in (
        ("DELETE", "/customers"),
        ("PUT", "/customers/_doc/" + identifier),
        ("POST", "/_scripts/a"),
        ("GET", "/_cluster/settings"),
    ):
        assert client.request(method, path, headers=headers).status_code == 403
    assert (
        client.post(
            "/customers/_search", headers=headers, json={"query": {"script": "malicious"}}
        ).status_code
        == 422
    )
    assert (
        client.post("/customers/_search", headers=headers, content=b"x" * 8193).status_code == 413
    )
