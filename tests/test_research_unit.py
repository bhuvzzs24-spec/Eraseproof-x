import ast
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import time
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from eraseproof.research_models import catalog, matrix, Scenario
from eraseproof.research_metrics import summarize, wilson, distribution
from eraseproof.research_baselines import api_acknowledgment, workflow_monitor
from eraseproof.research_oracle import combine, STORES
from eraseproof.research_hooks import checkpoint
from eraseproof.research_harness import Harness
from eraseproof.research_report import cluster_comparison
from eraseproof.research_api import router


def test_catalog_and_bounded_matrix():
    version, scenarios = catalog()
    ci = matrix("research/phase-4/config/ci.v1.json")
    assert version == "scenario-catalog-v1" and len(scenarios) >= 12
    assert {e.tier for e in ci.entries} == {"small", "medium", "large"}
    assert max(t.customers for t in ci.tiers.values()) <= 8
    sample = next(iter(scenarios.values())).model_dump()
    sample["actions"] = ["arbitrary_shell"]
    with pytest.raises(ValidationError):
        Scenario.model_validate(sample)


def test_seeded_workload_is_reproducible():
    import random

    first = [random.Random("101:0").randint(100, 20000) for _ in range(3)]
    second = [random.Random("101:0").randint(100, 20000) for _ in range(3)]
    assert first == second
    assert first[0] != random.Random("202:0").randint(100, 20000)


def test_oracle_is_independent_and_uncertainty_is_preserved():
    source = Path("eraseproof/research_oracle.py").read_text()
    imports = [n.module for n in ast.walk(ast.parse(source)) if isinstance(n, ast.ImportFrom)]
    assert not any(m and ("verification" in m or "research_baselines" in m) for m in imports)
    values = {t: {"state": "ABSENT"} for t in STORES}
    assert combine(values, True) == "ABSENT"
    assert combine(values, False) == "PENDING"
    assert combine({**values, "cache": {"state": "UNAVAILABLE"}}, True) == "UNAVAILABLE"
    assert combine({**values, "cache": {"state": "UNSUPPORTED"}}, True) == "UNSUPPORTED"
    assert (
        combine(
            {**values, "cache": {"state": "RESIDUAL"}, "search": {"state": "UNAVAILABLE"}}, True
        )
        == "RESIDUAL"
    )


def complete_metadata():
    return {
        "state": "COMPLETED_REPORTED",
        "tasks": [
            {
                "target": t,
                "state": "SUCCEEDED_REPORTED",
                "attempts": [{"outcome": "RETRY_WAIT"}, {"outcome": "SUCCEEDED_REPORTED"}],
            }
            for t in STORES
        ],
    }


def test_baselines_trust_declared_signals_without_weakening_recovery():
    value = complete_metadata()
    assert api_acknowledgment(value)["prediction"] == "ABSENT"
    assert workflow_monitor(value)["prediction"] == "ABSENT"
    failed = deepcopy(value)
    failed["state"] = "PARTIALLY_FAILED"
    failed["tasks"][0]["state"] = "FAILED_TERMINAL"
    assert api_acknowledgment(failed)["prediction"] == "RESIDUAL"
    assert workflow_monitor(failed)["prediction"] == "RESIDUAL"
    missing = deepcopy(value)
    missing["tasks"].pop()
    assert workflow_monitor(missing)["prediction"] == "ABSTAIN"
    assert api_acknowledgment(missing)["prediction"] == "ABSENT"
    assert api_acknowledgment({"state": "IN_PROGRESS"})["prediction"] == "ABSTAIN"


def test_wilson_intervals_and_distribution_edges():
    assert wilson(0, 0) is None
    assert wilson(0, 10) == pytest.approx([0, 0.2775328], abs=1e-6)
    assert wilson(10, 10) == pytest.approx([0.7224672, 1], abs=1e-6)
    assert wilson(5, 10) == pytest.approx([0.2365931, 0.7634069], abs=1e-6)
    assert distribution([])["median"] is None
    assert distribution(list(range(1, 21)))["p95"] == 19
    assert distribution([1, 3])["mean"] == 2


def test_metrics_denominators_abstentions_and_failure_retention():
    phases = []
    for truth, prediction in [
        ("RESIDUAL", "RESIDUAL"),
        ("ABSENT", "RESIDUAL"),
        ("ABSENT", "ABSENT"),
        ("RESIDUAL", "ABSENT"),
        ("RESIDUAL", "ABSTAIN"),
        ("UNAVAILABLE", "ABSENT"),
    ]:
        phases.append(
            {
                "phase": "primary",
                "oracle": {"state": truth},
                "methods": {
                    "eraseproof": {
                        "prediction": prediction,
                        "outcome": "INCONCLUSIVE" if prediction == "ABSTAIN" else prediction,
                        "data_queries": 2,
                        "elapsed_seconds": 1,
                        "targets": {"cache": "checked"},
                    }
                },
            }
        )
    trials = [
        {"status": "COMPLETED", "scenario_id": "unit-metrics", "phases": phases},
        {"status": "TIMED_OUT", "scenario_id": "unit-timeout", "phases": []},
    ]
    result = summarize(trials)
    m = result["methods"]["eraseproof"]
    assert [m[k] for k in ("tp", "fp", "tn", "fn")] == [1, 1, 1, 1]
    assert m["coverage"]["value"] == 0.8 and m["abstained_on_binary_rows"] == 1
    assert m["precision"]["value"] == 0.5 and m["recall"]["value"] == 0.5
    assert m["full_positive_detection_yield"]["value"] == pytest.approx(1 / 3)
    assert m["clearance_with_unknown_oracle"] == 1
    assert result["physical_trials"] == 2 and result["timed_out_trials"] == 1
    assert set(result["methods"]) == {"eraseproof"}


def test_cluster_bootstrap_keeps_trial_units_and_fixed_seed():
    trials = [
        {
            "phases": [
                {
                    "oracle": {"state": "RESIDUAL"},
                    "methods": {"a": {"prediction": "ABSENT"}, "b": {"prediction": "RESIDUAL"}},
                }
            ]
        },
        {
            "phases": [
                {
                    "oracle": {"state": "ABSENT"},
                    "methods": {"a": {"prediction": "ABSENT"}, "b": {"prediction": "ABSENT"}},
                }
            ]
        },
    ]
    first = cluster_comparison(trials, "a", "b", 200)
    assert first == cluster_comparison(trials, "a", "b", 200)
    assert first["clusters"] == 2 and first["mean_difference"] == 0.5
    assert cluster_comparison(trials[:1], "a", "b")["bootstrap_95"] is None


def test_environment_guards_prevent_accidental_production_faults(monkeypatch):
    monkeypatch.delenv("ERASEPROOF_RESEARCH_FAULTS", raising=False)
    with pytest.raises(PermissionError):
        Harness("eraseproof-research-unit")
    monkeypatch.setenv("ERASEPROOF_RESEARCH_FAULTS", "1")
    with pytest.raises(PermissionError):
        Harness("ordinary-production-project")
    subject = uuid4()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_TEST_FAULTS", "1")
    monkeypatch.setenv("RESEARCH_ISOLATION_ID", "eraseproof-research-unit")
    monkeypatch.setenv("RESEARCH_HOOK_POINT", "deletion.before_connector")
    monkeypatch.setenv("RESEARCH_HOOK_TARGETS", "cache")
    monkeypatch.setenv("RESEARCH_FAULT_SUBJECTS", str(subject))
    monkeypatch.setenv("RESEARCH_HOOK_ACTION", "skip")
    assert checkpoint("deletion.before_connector", "cache", subject) is False
    monkeypatch.setenv("APP_ENV", "demo")
    assert checkpoint("deletion.before_connector", "cache", subject) is True
    assert checkpoint("deletion.before_connector", "cache", uuid4()) is False


def test_research_http_is_read_only_and_authorized(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    assert all(
        not (set(route.methods) & {"POST", "PUT", "PATCH", "DELETE"}) for route in router.routes
    )
    monkeypatch.setenv("APP_ENV", "demo")
    monkeypatch.setenv("RESEARCH_TOKEN", "r" * 32)
    with TestClient(app) as client:
        assert client.get("/v1/research/scenarios").status_code == 403
        response = client.get("/v1/research/scenarios", headers={"X-Research-Token": "r" * 32})
        assert response.status_code == 200 and response.json()["items"]


def test_extended_consistency_never_weakens_default():
    from eraseproof.verification import policy
    from eraseproof.verification_models import StartVerification

    default, extended = policy(), policy("extended")
    assert (
        extended["grace_seconds"] >= default["grace_seconds"]
        and extended["absence_samples"] == default["absence_samples"]
    )
    assert (
        StartVerification(
            idempotency_key="unit-window", consistency_profile="extended"
        ).consistency_profile
        == "extended"
    )
    with pytest.raises(ValidationError):
        StartVerification(idempotency_key="unit-window", consistency_profile="skip-consistency")


def test_resume_preserves_interrupted_attempt_and_detects_corruption(tmp_path, monkeypatch):
    import eraseproof.research_runner as module

    config = matrix("research/phase-4/config/ci.v1.json").model_dump()
    config["selected_methods"] = ["api_ack", "workflow", "eraseproof"]

    def git(args, **kwargs):
        return "a" * 40 + "\n" if "rev-parse" in args else ""

    monkeypatch.setattr(module.subprocess, "check_output", git)

    class FakeHarness:
        project = "eraseproof-research-unit"
        deadline = time.monotonic() + 900
        client = SimpleNamespace(close=lambda: None)

        def environment(self):
            return {"unit_fixture": True}

        def bridge(self, *args, **kwargs):
            return {"stored": True}

    runner = module.Runner(FakeHarness(), config, tmp_path)
    trial = {
        "id": str(uuid4()),
        "experiment_id": runner.experiment["id"],
        "logical_key": "unit:1",
        "attempt": 1,
        "scenario_id": "normal_retention",
        "seed": 101,
        "status": "RUNNING",
        "fixtures": [],
        "phases": [],
    }
    runner.data["trials"].append(trial)
    runner.save()
    runner.lock.close()
    resumed = module.Runner(FakeHarness(), config, tmp_path, True)
    assert resumed.data["trials"][0]["status"] == "INTERRUPTED"
    assert resumed.data["trials"][0]["error"]["partial_results_preserved"]
    resumed.lock.close()
    data = __import__("json").loads((tmp_path / "dataset.json").read_text())
    data["experiment"]["state"] = "forged"
    (tmp_path / "dataset.json").write_text(__import__("json").dumps(data))
    with pytest.raises(ValueError):
        module.Runner(FakeHarness(), config, tmp_path, True)


def test_measured_export_integrity_and_statistical_summary(tmp_path):
    import json
    from eraseproof.evidence import digest
    from eraseproof.research_report import generate

    trials = [
        {
            "id": str(uuid4()),
            "status": "COMPLETED",
            "scenario_id": "unit-only",
            "seed": 101,
            "tier": "small",
            "phases": [
                {
                    "phase": "primary",
                    "customer_id": str(uuid4()),
                    "oracle": {"state": "ABSENT"},
                    "methods": {
                        "api_ack": {
                            "prediction": "ABSENT",
                            "outcome": "COMPLETED_REPORTED",
                            "elapsed_seconds": 0.001,
                            "data_queries": 0,
                        }
                    },
                }
            ],
        }
    ]
    summary = summarize(trials)
    payload = {
        "format_version": "phase4-dataset-v1",
        "experiment": {"code_commit": "a" * 40, "configuration_digest": "b" * 64},
        "trials": trials,
        "summary": summary,
    }
    path = tmp_path / "unit-fixture.json"
    path.write_text(json.dumps({**payload, "dataset_digest": digest(payload)}))
    result = generate(path, tmp_path / "unit-generated", plots=False)
    assert result["methods"]["api_ack"]["tn"] == 1
    assert (tmp_path / "unit-generated" / "decisions.csv").read_text().count("\n") == 2
    corrupted = json.loads(path.read_text())
    corrupted["trials"][0]["status"] = "FAILED"
    path.write_text(json.dumps(corrupted))
    with pytest.raises(ValueError):
        generate(path, tmp_path / "invalid", plots=False)
