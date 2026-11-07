"""Fail-closed hosted synthetic-demo configuration and per-account credentials."""

import hashlib
import json
import os
import re
import secrets
from pathlib import Path
from urllib.parse import urlsplit


def hosted():
    return os.getenv("DEPLOYMENT_MODE") == "hosted"


def accounts():
    path = os.getenv("DASHBOARD_USERS_FILE", "")
    if not path:
        return {}
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict) or not value:
        raise ValueError("account file must contain accounts")
    for name, user in value.items():
        if (
            name == "public-demo"
            or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}", name)
            or user.get("role")
            not in (
                "readonly",
                "operator",
                "research",
            )
        ):
            raise ValueError("invalid account record")
        if not re.fullmatch(r"[a-f0-9]{32}", user.get("salt", "")) or not re.fullmatch(
            r"[a-f0-9]{128}", user.get("hash", "")
        ):
            raise ValueError("invalid account hash")
    return value


def password_hash(password, salt):
    return hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=65536, r=8, p=2, maxmem=128 * 1024 * 1024
    ).hex()


def verify_account(username, password, role):
    user = accounts().get(username)
    salt = user["salt"] if user else "0" * 32
    actual = password_hash(password, salt)
    if not user or user["role"] != role or not secrets.compare_digest(actual, user["hash"]):
        return None
    return user


def version(user):
    return hashlib.sha256(json.dumps(user, sort_keys=True).encode()).hexdigest()


def validate_hosted(gateway=False):
    if not hosted():
        return
    if os.getenv("APP_ENV") != "demo":
        raise ValueError("hosted deployment supports synthetic demo data only")
    for key in (
        "DASHBOARD_ENABLE_RESEARCH",
        "ERASEPROOF_RESEARCH_FAULTS",
        "ENABLE_TEST_FAULTS",
        "ERASEPROOF_TEST_FAULTS",
    ):
        if os.getenv(key) == "1":
            raise ValueError("fault execution is forbidden on hosted infrastructure")
    for key in ("INSPECTION_TOKEN", "DELETION_TOKEN", "VERIFICATION_TOKEN", "OPERATOR_TOKEN"):
        if len(os.getenv(key, "")) < 32:
            raise ValueError("hosted credentials must be explicitly configured")
    if not gateway:
        for key in ("DATABASE_URL", "BROKER_URL", "REDIS_URL", "SEARCH_URL"):
            value = urlsplit(os.getenv(key, ""))
            if not value.hostname or value.hostname in ("localhost", "127.0.0.1"):
                raise ValueError("explicit private datastore connections are required")
    if gateway:
        origin = urlsplit(os.getenv("DASHBOARD_ORIGIN", ""))
        if (
            origin.scheme != "https"
            or not origin.hostname
            or origin.path
            or origin.query
            or origin.fragment
            or origin.username
            or origin.port not in (None, 443)
        ):
            raise ValueError("hosted gateway requires an exact HTTPS origin")
        if (
            origin.hostname in ("localhost", "127.0.0.1")
            or os.getenv("DASHBOARD_SECURE_COOKIE") != "1"
        ):
            raise ValueError("hosted gateway requires secure cookies and a public hostname")
        if any(os.getenv(f"DASHBOARD_{r}_PASSWORD") for r in ("READONLY", "OPERATOR", "RESEARCH")):
            raise ValueError("shared role passwords are disabled in hosted mode")
        accounts()
        if not os.getenv("DASHBOARD_USERS_FILE"):
            raise ValueError("hosted gateway requires per-account password hashes")
        for service in (
            "CUSTOMER",
            "ORDER",
            "CACHE",
            "SEARCH",
            "ANALYTICS",
            "DELETION",
            "VERIFICATION",
        ):
            value = urlsplit(os.getenv(f"DASHBOARD_{service}_ORIGIN", ""))
            if (
                value.scheme not in ("http", "https")
                or not value.hostname
                or value.hostname in ("localhost", "127.0.0.1")
                or value.username
            ):
                raise ValueError("explicit private API origins are required")
