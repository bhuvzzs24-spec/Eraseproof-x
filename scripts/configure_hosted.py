"""Generate private hosted configuration without provisioning or publishing anything."""

import argparse
import os
from pathlib import Path
import re
import secrets


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--domain", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--directory", type=Path, default=Path("work/hosted"))
    a = p.parse_args()
    if (
        not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", a.domain)
        or "." not in a.domain
        or "@" not in a.email
        or any(c in a.email for c in "\r\n=$")
    ):
        p.error("valid domain and ACME contact required")
    target = a.directory / "hosted.env"
    if target.exists():
        p.error("existing hosted configuration preserved")
    a.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    values = {
        k: secrets.token_urlsafe(32)
        for k in (
            "POSTGRES_PASSWORD",
            "RUNTIME_DB_PASSWORD",
            "RABBITMQ_PASSWORD",
            "REDIS_PASSWORD",
            "INSPECTION_TOKEN",
            "OPERATOR_TOKEN",
            "DELETION_TOKEN",
            "VERIFICATION_TOKEN",
            "RESEARCH_TOKEN",
            "VERIFIER_DB_PASSWORD",
            "VERIFIER_CONTROL_PASSWORD",
            "VERIFIER_REDIS_PASSWORD",
            "VERIFIER_SEARCH_PASSWORD",
        )
    }
    values.update(
        DOMAIN=a.domain,
        ACME_EMAIL=a.email,
        USERS_FILE=str((a.directory / "users.json").resolve()),
        DASHBOARD_PUBLIC_DEMO="0",
    )
    values.update(
        MIGRATOR_DATABASE_URL=f"postgresql://lab:{values['POSTGRES_PASSWORD']}@postgres:5432/eraseproof",
        RUNTIME_DATABASE_URL=f"postgresql://eraseproof_runtime:{values['RUNTIME_DB_PASSWORD']}@postgres:5432/eraseproof",
        VERIFIER_CONTROL_DATABASE_URL=f"postgresql://verification_coordinator:{values['VERIFIER_CONTROL_PASSWORD']}@postgres:5432/eraseproof",
        VERIFIER_READ_DATABASE_URL=f"postgresql://verification_probe:{values['VERIFIER_DB_PASSWORD']}@postgres:5432/eraseproof",
        BROKER_URL=f"amqp://lab:{values['RABBITMQ_PASSWORD']}@rabbitmq:5672/%2F",
        REDIS_URL=f"redis://:{values['REDIS_PASSWORD']}@redis:6379/0",
        VERIFIER_REDIS_URL=f"redis://verification:{values['VERIFIER_REDIS_PASSWORD']}@redis:6379/0",
        VERIFIER_SEARCH_URL=f"http://verification:{values['VERIFIER_SEARCH_PASSWORD']}@search-reader:9200",
    )
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as f:
        f.write("".join(f"{k}={v}\n" for k, v in values.items()))
    print(
        "Private configuration generated. Create hashed accounts separately. No resources created and no ports published."
    )


if __name__ == "__main__":
    main()
