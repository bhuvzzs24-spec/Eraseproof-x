"""Reproducible per-run hash chain; not a signature or privileged-admin protection."""

from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import UUID


def canonical(value: object) -> str:
    def convert(item):
        if isinstance(item, UUID):
            return str(item)
        if isinstance(item, datetime):
            if item.tzinfo is None:
                raise ValueError("naive evidence time")
            return item.astimezone(timezone.utc).isoformat()
        raise TypeError("unsupported canonical value")

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=convert,
    )


def digest(value: object) -> str:
    return sha256(canonical(value).encode()).hexdigest()


def validate_chain(records: list[dict]) -> bool:
    previous = ""
    for sequence, record in enumerate(records, 1):
        body = record["body"]
        if record["sequence"] != sequence or record["previous_digest"] != previous:
            return False
        if body.get("sequence") != sequence or body.get("previous_digest") != previous:
            return False
        for key in ("run_id", "target", "round_no"):
            if key in record and str(record[key]) != str(body.get(key)):
                return False
        if digest(body) != record["digest"]:
            return False
        previous = record["digest"]
    return bool(records)
