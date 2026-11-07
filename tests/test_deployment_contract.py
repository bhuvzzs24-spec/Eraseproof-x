"""Safety regression checks for deployment boundaries, immutable image pins and publication guard."""

from pathlib import Path
from ipaddress import ip_address, ip_network
import pytest
import yaml
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "hosted_ops", Path(__file__).resolve().parent.parent / "scripts/hosted_ops.py"
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
validate = _module.validate

ROOT = Path(__file__).resolve().parent.parent


def test_standalone_hosted_stack_has_only_explicit_proxy_ports_and_no_faults():
    config = yaml.safe_load((ROOT / "deploy/compose.hosted.yaml").read_text())
    for name, service in config["services"].items():
        assert "docker.sock" not in repr(service)
        if service.get("ports"):
            assert name == "caddy" and service["profiles"] == ["publish"]
        if "image" in service:
            assert "@sha256:" in service["image"]
        env = service.get("environment", {})
        assert all(
            env.get(k) != "1"
            for k in (
                "DASHBOARD_ENABLE_RESEARCH",
                "ERASEPROOF_RESEARCH_FAULTS",
                "ENABLE_TEST_FAULTS",
            )
        )
    assert all(
        config["networks"][n]["internal"] for n in ("private", "api", "ingress", "search-private")
    )
    assert config["services"]["gateway"]["networks"] == ["api", "ingress"]
    assert config["services"]["opensearch"]["networks"] == ["search-private"]
    assert "search-private" not in config["services"]["verification-worker"]["networks"]
    assert "search-reader" in config["services"]
    addresses = config["networks"]["ingress"]["ipam"]["config"][0]
    assert ip_address(
        config["services"]["caddy"]["networks"]["ingress"]["ipv4_address"]
    ) not in ip_network(addresses["ip_range"])


def test_publication_requires_owner_cost_and_exact_origin():
    config = {
        "services": {
            "caddy": {
                "ports": [{"host_ip": "0.0.0.0", "published": "443"}],
                "environment": {"DOMAIN": "demo.example.org"},
            }
        }
    }
    validate(config)
    with pytest.raises(ValueError, match="owner publication"):
        validate(config, publish=True)
    record = {
        "owner": "bhuvzzs24-spec",
        "publication_authorized": True,
        "spending_authorized": True,
        "monthly_ceiling_eur": 11,
        "origin": "https://demo.example.org",
    }
    validate(config, publish=True, approval=record)
    for key, value in (
        ("owner", "someone-else"),
        ("publication_authorized", False),
        ("spending_authorized", False),
        ("origin", "https://wrong.example.org"),
    ):
        altered = {**record, key: value}
        with pytest.raises(ValueError):
            validate(config, publish=True, approval=altered)
    with pytest.raises(ValueError, match="reverse proxy"):
        validate(config, ci=True)


def test_gate_rejects_direct_store_ports_and_docker_socket():
    config = {"services": {"postgres": {"ports": [{"published": "5432"}]}}}
    with pytest.raises(ValueError, match="reverse proxy"):
        validate(config)
    config = {"services": {"gateway": {"volumes": [{"source": "/var/run/docker.sock"}]}}}
    with pytest.raises(ValueError, match="socket"):
        validate(config)
