"""Create/rotate one local hashed account. Never prints or accepts passwords in argv."""

import argparse
import getpass
import json
import os
import re
import secrets
from pathlib import Path
from eraseproof.hosted_security import password_hash


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", type=Path, required=True)
    p.add_argument("--username", required=True)
    p.add_argument("--role", choices=("readonly", "operator", "research"), required=True)
    args = p.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}", args.username):
        p.error("invalid username")
    password = getpass.getpass("New unique password (at least 16 characters): ")
    if (
        len(password) < 16
        or len(password) > 256
        or password != getpass.getpass("Confirm password: ")
    ):
        p.error("password length/confirmation failed")
    users = json.loads(args.file.read_text()) if args.file.exists() else {}
    salt = secrets.token_hex(16)
    users[args.username] = {"role": args.role, "salt": salt, "hash": password_hash(password, salt)}
    args.file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = args.file.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as f:
        f.write(json.dumps(users, indent=2))
    temporary.replace(args.file)
    args.file.chmod(0o600)
    print("Account stored; prior sessions for changed credentials are revoked on next request.")


if __name__ == "__main__":
    main()
