import ast
from copy import deepcopy
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from eraseproof.evidence import canonical, digest, validate_chain
from eraseproof.verification_models import (
    Outcome as O,
    aggregate,
    StartVerification,
    VerificationCommand,
)
from eraseproof.verification_api import router
from eraseproof.verification import policy
from eraseproof import verification_adapters as adapters


def test_formal_aggregation_truth_table():
    targets = {"customer", "cache", "search"}
    for values in product(
        [O.ABSENT, O.RESIDUAL, O.PENDING, O.INCONCLUSIVE, O.UNSUPPORTED], repeat=3
    ):
        data = dict(zip(sorted(targets), values))
        for reported in ("COMPLETED_REPORTED", "PARTIALLY_FAILED", "IN_PROGRESS"):
            result = aggregate(data, targets, reported)
            if O.RESIDUAL in values:
                assert result == (
                    O.FALSE_SUCCESS if reported == "COMPLETED_REPORTED" else O.RESIDUAL
                )
            elif O.UNSUPPORTED in values:
                assert result == O.UNSUPPORTED
            elif O.INCONCLUSIVE in values:
                assert result == O.INCONCLUSIVE
            elif O.PENDING in values:
                assert result == O.PENDING
            else:
                assert result == O.ABSENT
    assert (
        aggregate({"cache": O.ABSENT}, {"cache", "missing"}, "COMPLETED_REPORTED") == O.UNSUPPORTED
    )
    assert aggregate({}, set(), "COMPLETED_REPORTED") == O.INCONCLUSIVE


def test_scope_matches_all_six_real_handlers_and_retains_explicit_metadata():
    from eraseproof.deletion_models import TARGETS

    scope = policy()
    assert set(scope["targets"]) == set(TARGETS)
    assert all(
        s["required"] and s["required_status"] == "VERIFIED_ABSENT"
        for s in scope["targets"].values()
    )
    assert scope["absence_samples"] >= 2 and scope["grace_seconds"] >= 3
    assert scope["targets"]["orders"]["allowed_fact_fields"] == [
        "id",
        "customer_id",
        "amount_cents",
        "currency",
        "created_at",
    ]
    assert scope["excluded"] and "legacy RabbitMQ" in scope["excluded"][0]


def test_canonical_digest_and_chain_detect_corruption():
    timestamp = datetime(2026, 11, 6, tzinfo=timezone.utc)
    assert canonical({"b": 2, "a": 1}) == canonical({"a": 1, "b": 2})
    assert digest({"at": timestamp}) == digest({"at": timestamp.isoformat()})
    records = []
    previous = ""
    for number in (1, 2):
        body = {"sequence": number, "previous_digest": previous, "result": O.ABSENT, "count": 0}
        records.append(
            {"sequence": number, "body": body, "previous_digest": previous, "digest": digest(body)}
        )
        previous = records[-1]["digest"]
    assert validate_chain(records)
    damaged = deepcopy(records)
    damaged[0]["body"]["count"] = 1
    assert not validate_chain(damaged)
    assert not validate_chain(records[1:])
    with pytest.raises(ValueError):
        canonical({"x": float("nan")})
    with pytest.raises(ValueError):
        canonical({"at": datetime(2026, 1, 1)})


def test_strict_requests_commands_and_authorization(monkeypatch):
    with pytest.raises(ValidationError):
        StartVerification(idempotency_key="short")
    with pytest.raises(ValidationError):
        StartVerification(idempotency_key="valid-key", targets=["cache"])
    with pytest.raises(ValidationError):
        VerificationCommand(event_id=uuid4(), run_id=uuid4(), round_no=9)
    app = FastAPI()
    app.include_router(router)
    monkeypatch.setenv("APP_ENV", "demo")
    monkeypatch.setenv("VERIFICATION_TOKEN", "v" * 32)
    with TestClient(app) as client:
        path = f"/v1/deletions/{uuid4()}/verifications"
        assert client.post(path, json={}).status_code == 403
        assert client.post(path, json={}, headers={"X-Deletion-Token": "v" * 32}).status_code == 403
        assert (
            client.post(path, json={}, headers={"X-Verification-Token": "v" * 32}).status_code
            == 422
        )
        monkeypatch.setenv("APP_ENV", "production")
        assert (
            client.post(path, json={}, headers={"X-Verification-Token": "v" * 32}).status_code
            == 403
        )


def test_adapter_boundary_has_no_deletion_calls_or_mutating_queries():
    tree = ast.parse(Path("eraseproof/verification_adapters.py").read_text())
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any(m and ("deletion_connectors" in m or "deletion_worker" in m) for m in imports)
    source = Path("eraseproof/verification_adapters.py").read_text()
    assert "httpx.delete" not in source and "client.put" not in source
    assert "default_transaction_read_only=on" in source


def test_missing_capability_is_never_silently_ignored(monkeypatch):
    scope = policy()["targets"]["search"]
    monkeypatch.setenv("ENABLE_TEST_FAULTS", "1")
    monkeypatch.setenv("VERIFICATION_TEST_DISABLE_ADAPTERS", "search")
    result = adapters.probe("search", uuid4(), uuid4(), scope)
    assert result.outcome == O.UNSUPPORTED and not result.scope_complete
    assert result.query_count == 0
    monkeypatch.delenv("ENABLE_TEST_FAULTS")
    monkeypatch.setattr(
        adapters, "search_probe", lambda *a: ({"eligible_rows": 0, "permitted_markers": 1}, 2, True)
    )
    assert adapters.probe("search", uuid4(), uuid4(), scope).outcome == O.ABSENT


def test_read_failures_and_incomplete_scope_never_become_absence(monkeypatch):
    scope = policy()["targets"]["search"]
    monkeypatch.setattr(adapters, "search_probe", lambda *a: ({"eligible_rows": 0}, 2, False))
    assert adapters.probe("search", uuid4(), uuid4(), scope).outcome == O.INCONCLUSIVE
    monkeypatch.setattr(adapters, "search_probe", lambda *a: ({"eligible_rows": 1}, 2, False))
    assert adapters.probe("search", uuid4(), uuid4(), scope).outcome == O.RESIDUAL

    def unavailable(*a):
        raise httpx.ConnectError("raw secret must never enter evidence")

    monkeypatch.setattr(adapters, "search_probe", unavailable)
    result = adapters.probe("search", uuid4(), uuid4(), scope)
    assert result.outcome == O.INCONCLUSIVE
    assert "secret" not in result.model_dump_json()


def test_search_queries_and_exact_marker_policy(monkeypatch):
    subject = uuid4()
    calls = []

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url):
            calls.append(("GET", url))
            return httpx.Response(
                200,
                json={
                    "found": True,
                    "_id": str(subject),
                    "_version": 2,
                    "_source": {"erased": True},
                },
                request=httpx.Request("GET", url),
            )

        def post(self, url, **kwargs):
            assert url.endswith("/_search") and kwargs["json"]["track_total_hits"]
            calls.append(("POST_SEARCH", url))
            return httpx.Response(
                200,
                json={
                    "_shards": {"failed": 0},
                    "hits": {"total": {"relation": "eq", "value": 0}, "hits": []},
                },
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(adapters.httpx, "Client", Client)
    result = adapters.probe("search", subject, uuid4(), policy()["targets"]["search"])
    assert result.outcome == O.ABSENT and result.summary["permitted_markers"] == 1
    assert result.query_count == 2 and len(calls) == 2


def test_control_message_metadata_must_be_typed_not_just_named():
    from eraseproof.verification_adapters import safe_control

    value = {
        "event_type": "verification.command",
        "version": 1,
        "event_id": str(uuid4()),
        "run_id": str(uuid4()),
        "round_no": 1,
    }
    assert safe_control("verification.command", value)
    assert not safe_control("verification.command", {**value, "run_id": "personal@example.invalid"})
    assert not safe_control("verification.command", {**value, "email": "personal@example.invalid"})
    assert not safe_control("customer.created", value)


def test_consistency_samples_and_anchor_changes():
    from datetime import timedelta
    from eraseproof.verification_models import consistency_result

    anchor = datetime(2026, 11, 6, tzinfo=timezone.utc)
    args = dict(
        reported_state="COMPLETED_REPORTED",
        anchor=anchor,
        created_at=anchor,
        observed_at=anchor + timedelta(seconds=5),
        grace_seconds=3,
        prior_streak=0,
        prior_anchor=None,
        minimum_samples=2,
    )
    assert consistency_result(O.ABSENT, **args) == (O.PENDING, 1, True)
    assert consistency_result(O.ABSENT, **{**args, "prior_streak": 1, "prior_anchor": anchor}) == (
        O.ABSENT,
        2,
        True,
    )
    assert consistency_result(
        O.RESIDUAL, **{**args, "observed_at": anchor + timedelta(seconds=1)}
    ) == (O.PENDING, 0, False)
    assert consistency_result(O.RESIDUAL, **args) == (O.RESIDUAL, 0, True)
    assert consistency_result(O.ABSENT, **{**args, "reported_state": "IN_PROGRESS"}) == (
        O.PENDING,
        0,
        False,
    )
    assert consistency_result(O.INCONCLUSIVE, **args) == (O.INCONCLUSIVE, 0, True)
    assert consistency_result(
        O.ABSENT, **{**args, "prior_streak": 5, "prior_anchor": anchor - timedelta(seconds=1)}
    ) == (O.PENDING, 1, True)


def test_receipt_metadata_cannot_hide_personal_text():
    from eraseproof.verification_adapters import safe_receipt

    value = {
        "consumer": "cache",
        "event_id": str(uuid4()),
        "customer_id": str(uuid4()),
        "processed_at": "2026-11-06T00:00:00Z",
    }
    assert safe_receipt(value)
    assert not safe_receipt({**value, "consumer": "personal@example.invalid"})
    assert not safe_receipt({**value, "email": "personal@example.invalid"})


def test_historical_order_scope_without_capture_is_inconclusive(monkeypatch):
    from contextlib import contextmanager

    class Result:
        def fetchone(self):
            return None

        def fetchall(self):
            return []

    class Database:
        def execute(self, *args):
            return Result()

    @contextmanager
    def read():
        yield Database()

    monkeypatch.setattr(adapters, "read_db", read)
    result = adapters.probe("orders", uuid4(), uuid4(), policy()["targets"]["orders"])
    assert result.outcome == O.INCONCLUSIVE
    assert result.summary["manifest_captured"] is False


def test_probe_spanning_grace_cutoff_is_pending_using_start_window():
    from datetime import timedelta
    from eraseproof.verification_models import Probe, consistency_result

    anchor = datetime(2026, 11, 6, tzinfo=timezone.utc)
    observation = Probe(
        started_at=anchor + timedelta(seconds=1),
        observed_at=anchor + timedelta(seconds=4),
        outcome=O.RESIDUAL,
        adapter="independent.search",
        category="indexed_profile",
        summary={"eligible_rows": 1},
        query_count=2,
        duration_ms=3000,
    )
    result, _, eligible = consistency_result(
        observation.outcome,
        reported_state="COMPLETED_REPORTED",
        anchor=anchor,
        observed_at=observation.started_at,
        created_at=anchor,
        grace_seconds=3,
        prior_streak=0,
        prior_anchor=None,
        minimum_samples=2,
    )
    assert result == O.PENDING and not eligible
