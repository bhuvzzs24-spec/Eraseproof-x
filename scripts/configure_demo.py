"""Create private demo credentials once; never overwrite an existing environment."""

import os
from pathlib import Path
import secrets

path = Path(".env")
try:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    raise SystemExit(
        ".env already exists; preserved. Add the documented new phase credentials explicitly if upgrading."
    )
with os.fdopen(descriptor, "w") as stream:
    for name in (
        "POSTGRES_PASSWORD",
        "RABBITMQ_PASSWORD",
        "INSPECTION_TOKEN",
        "DELETION_TOKEN",
        "VERIFICATION_TOKEN",
        "VERIFIER_DB_PASSWORD",
        "VERIFIER_CONTROL_PASSWORD",
        "VERIFIER_REDIS_PASSWORD",
    ):
        stream.write(f"{name}={secrets.token_urlsafe(32)}\n")
print("Created private demo .env with independent random credentials.")
