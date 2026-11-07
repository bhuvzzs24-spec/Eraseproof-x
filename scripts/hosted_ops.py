"""Explicit, bounded operational commands. No cloud creation, shell injection or implicit publication."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parent.parent


def values(path):
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if line and not line.startswith("#") and "=" in line
    )


def command(args):
    files = [str(ROOT / "deploy/compose.hosted.yaml")]
    if args.ci:
        files.append(str(ROOT / "deploy/compose.ci.yaml"))
    result = [
        "docker",
        "compose",
        "--env-file",
        str(args.env_file.resolve()),
        "--project-name",
        args.project,
    ]
    for f in files:
        result += ["-f", f]
    return result


def validate(config, ci=False, publish=False, approval=None):
    services = config["services"]
    for name, service in services.items():
        for port in service.get("ports", []):
            if name != "caddy" or (ci and port.get("host_ip") != "127.0.0.1"):
                raise ValueError("only the approved reverse proxy can bind ports")
        for volume in service.get("volumes", []):
            if "docker.sock" in str(volume):
                raise ValueError("Docker socket mount forbidden")
        env = service.get("environment", {})
        if any(
            env.get(k) == "1"
            for k in (
                "ENABLE_TEST_FAULTS",
                "ERASEPROOF_RESEARCH_FAULTS",
                "DASHBOARD_ENABLE_RESEARCH",
            )
        ):
            raise ValueError("hosted fault controls forbidden")
    if publish:
        if (
            not approval
            or not approval.get("publication_authorized")
            or approval.get("owner") != "bhuvzzs24-spec"
        ):
            raise ValueError("explicit repository owner publication approval required")
        domain = services["caddy"]["environment"]["DOMAIN"]
        if approval.get("origin") != "https://" + domain or domain.endswith(
            (".invalid", ".test", ".localhost")
        ):
            raise ValueError("approval must bind the actual owned domain")
        if not approval.get("spending_authorized") or not isinstance(
            approval.get("monthly_ceiling_eur"), (int, float)
        ):
            raise ValueError("separate spending approval with a cost ceiling required")


def dump(args, target):
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output:
            subprocess.run(
                command(args)
                + [
                    "exec",
                    "-T",
                    "postgres",
                    "pg_dump",
                    "-U",
                    "lab",
                    "-d",
                    "eraseproof",
                    "--format=custom",
                    "--no-owner",
                ],
                stdout=output,
                stderr=subprocess.PIPE,
                check=True,
                timeout=180,
            )
    except Exception:
        target.unlink(missing_ok=True)
        raise
    raw = target.read_bytes()
    if not raw.startswith(b"PGDMP"):
        target.unlink()
        raise ValueError("invalid PostgreSQL backup")
    return {
        "format": "PostgreSQL custom dump",
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "created_at_unix": time.time(),
        "scope": "PostgreSQL only; no backup-deletion verification or cross-store snapshot guarantee",
    }


def restore_test(args):
    if not args.backup or not args.backup.is_file():
        raise ValueError("existing scoped backup required")
    scratch = "ep_restore_" + uuid4().hex[:12]
    base = command(args) + ["exec", "-T", "postgres"]
    subprocess.run(
        base + ["createdb", "-U", "lab", "-T", "template0", scratch],
        check=True,
        capture_output=True,
        timeout=30,
    )
    try:
        with args.backup.open("rb") as file:
            subprocess.run(
                base
                + ["pg_restore", "-U", "lab", "--exit-on-error", "--no-owner", "--dbname", scratch],
                stdin=file,
                check=True,
                capture_output=True,
                timeout=180,
            )
        count = subprocess.check_output(
            base
            + [
                "psql",
                "-U",
                "lab",
                "-d",
                scratch,
                "-Atc",
                "SELECT count(*) FROM public.schema_migrations",
            ],
            text=True,
            timeout=30,
        ).strip()
        if count != "4":
            raise ValueError("restored schema ledger mismatch")
        if args.expected_customer:
            identifier = str(UUID(args.expected_customer))
            found = subprocess.check_output(
                base
                + [
                    "psql",
                    "-U",
                    "lab",
                    "-d",
                    scratch,
                    "-Atc",
                    f"SELECT count(*) FROM customer.customers WHERE id='{identifier}'::uuid",
                ],
                text=True,
                timeout=30,
            ).strip()
            if found != "1":
                raise ValueError("expected synthetic backup fixture missing")
        return {
            "restored": True,
            "schema_versions": int(count),
            "expected_fixture_found": bool(args.expected_customer),
            "scope": "scratch PostgreSQL database, removed after validation",
        }
    finally:
        subprocess.run(
            base + ["dropdb", "-U", "lab", "--if-exists", scratch],
            check=True,
            capture_output=True,
            timeout=30,
        )


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "action", choices=("validate", "up-private", "publish", "backup", "restore-test")
    )
    p.add_argument("--env-file", type=Path, required=True)
    p.add_argument("--project", default="eraseproof-hosted")
    p.add_argument("--ci", action="store_true")
    p.add_argument("--approval", type=Path)
    p.add_argument("--backup", type=Path)
    p.add_argument("--expected-customer")
    p.add_argument("--output", type=Path)
    p.add_argument("--existing-images", action="store_true")
    a = p.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,50}", a.project):
        p.error("invalid project name")
    result = json.loads(
        subprocess.check_output(
            command(a) + ["--profile", "publish", "config", "--format", "json"],
            text=True,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    )
    approval = json.loads(a.approval.read_text()) if a.approval else None
    validate(result, a.ci, a.action == "publish", approval)
    if a.action in ("up-private", "publish"):
        if a.action == "publish" and a.ci:
            p.error("CI cannot authorize public publication")
        cmd = command(a) + (["--profile", "publish"] if a.action == "publish" else [])
        subprocess.run(
            cmd
            + [
                "up",
                "--no-build" if a.existing_images else "--build",
                "-d",
                "--wait",
                "--wait-timeout",
                "240",
            ],
            check=True,
            timeout=600,
        )
        body = {"started": a.action, "public": a.action == "publish"}
    elif a.action == "backup":
        if not a.backup:
            p.error("--backup required")
        body = dump(a, a.backup)
    elif a.action == "restore-test":
        body = restore_test(a)
    else:
        body = {"configuration_validated": True, "publication_performed": False}
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(body, indent=2))
    print(json.dumps(body))


if __name__ == "__main__":
    main()
