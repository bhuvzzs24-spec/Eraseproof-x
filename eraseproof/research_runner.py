"""Seeded physical trials with an independent oracle, durable journals and honest failure retention."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import RLock
from uuid import uuid4
import argparse
import fcntl
import json
import os
import random
import subprocess
import time
import traceback

from eraseproof.evidence import digest, validate_chain
from eraseproof.research_models import catalog, matrix
from eraseproof.research_harness import Harness
from eraseproof.research_faults import Faults
from eraseproof.research_baselines import (
    api_acknowledgment,
    workflow_monitor,
    independent_prediction,
)
from eraseproof.research_metrics import summarize


class Runner:
    def __init__(self, harness: Harness, configuration: dict, output: Path, resume=False):
        self.h = harness
        self.output = output
        output.mkdir(parents=True, exist_ok=True)
        self.lock = (output / "runner.lock").open("a+")
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (output / "dataset.json").exists() and not resume:
            raise FileExistsError("results exist; use --resume or a fresh output directory")
        self.mutex = RLock()
        self.executor = str(uuid4())
        self.last_heartbeat = 0
        self.registry_version, self.registry = catalog()
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        if subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], text=True
        ).strip():
            raise RuntimeError("commit source changes before running a reproducible experiment")
        if resume:
            self.data = json.loads((output / "dataset.json").read_text())
            recorded = self.data.pop("dataset_digest")
            if digest(self.data) != recorded:
                raise ValueError("journal integrity mismatch")
            if self.data["experiment"]["configuration"] != configuration:
                raise ValueError("resume configuration differs")
            if self.data["experiment"]["code_commit"] != sha:
                raise ValueError("resume code revision differs; start a new batch")
        else:
            plan = []
            for entry in configuration["entries"]:
                for seed in entry["seeds"]:
                    for repeat in range(entry["repeats"]):
                        plan.append(
                            {
                                **entry,
                                "seed": seed,
                                "repeat": repeat,
                                "logical_key": f"{entry['scenario']}:{entry['tier']}:{seed}:{repeat}:{entry['consistency_profile']}",
                            }
                        )
            random.Random(20261107).shuffle(plan)
            self.data = {
                "format_version": "phase4-dataset-v1",
                "experiment": {
                    "id": str(uuid4()),
                    "state": "RUNNING",
                    "code_commit": sha,
                    "configuration": configuration,
                    "configuration_digest": digest(configuration),
                    "scenario_catalog_version": self.registry_version,
                    "scenario_catalog_digest": digest(
                        {k: v.model_dump() for k, v in self.registry.items()}
                    ),
                    "started_at_unix": time.time(),
                    "plan": plan,
                    "environment": self.h.environment(),
                },
                "trials": [],
            }
        self.experiment = self.data["experiment"]
        self.h.deadline = min(
            self.h.deadline,
            time.monotonic()
            + max(
                0,
                configuration["maximum_seconds"]
                - (time.time() - self.experiment["started_at_unix"]),
            ),
        )
        self.heartbeat()
        self.save()
        if resume:
            self.recover()

    def heartbeat(self):
        self.h.bridge(
            "lease",
            project=self.h.project,
            experiment_id=self.experiment["id"],
            executor_id=self.executor,
            release=False,
        )
        self.last_heartbeat = time.monotonic()

    def save(self, trial=None, remote=False):
        with self.mutex:
            if time.monotonic() - self.last_heartbeat > 30:
                self.heartbeat()
            self.data["summary"] = summarize(self.data["trials"])
            self.data["summary"]["planned_logical_trials"] = len(self.experiment["plan"])
            self.data["summary"]["unexecuted_logical_trials"] = len(
                {p["logical_key"] for p in self.experiment["plan"]}
                - {t["logical_key"] for t in self.data["trials"]}
            )
            payload = {**self.data, "dataset_digest": digest(self.data)}
            temporary = self.output / "dataset.tmp"
            with temporary.open("w") as stream:
                json.dump(payload, stream, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.output / "dataset.json")
            if remote:
                self.h.bridge("store", kind="experiment", body=self.experiment)
                if trial:
                    self.h.bridge("store", kind="trial", body=trial)

    def recover(self):
        for trial in self.data["trials"]:
            if trial["status"] != "RUNNING":
                continue
            trial["status"] = "INTERRUPTED"
            trial["error"] = {
                "code": "PRIOR_EXECUTOR_INTERRUPTED",
                "partial_results_preserved": True,
            }
            old = self.h.deadline
            self.h.deadline = max(old, time.monotonic() + 60)
            try:
                faults = Faults(self.h, trial, lambda: self.save(trial))
                errors = faults.restore()
                if trial.get("fixtures"):
                    self.h.bridge("cleanup", fixtures=trial["fixtures"])
                trial["cleanup"] = {
                    "status": "RESTORED" if not errors else "ERROR",
                    "errors": errors,
                }
                self.save(trial, True)
            finally:
                self.h.deadline = old

    def run(self):
        try:
            completed = {
                t["logical_key"] for t in self.data["trials"] if t["status"] == "COMPLETED"
            }
            for entry in self.experiment["plan"]:
                if entry["logical_key"] in completed:
                    continue
                if self.h.deadline <= time.monotonic():
                    break
                self.run_trial(entry)
            self.experiment["state"] = (
                "COMPLETED"
                if all(
                    any(
                        t["logical_key"] == p["logical_key"] and t["status"] == "COMPLETED"
                        for t in self.data["trials"]
                    )
                    for p in self.experiment["plan"]
                )
                else "FAILED"
            )
        except BaseException:
            self.experiment["state"] = "INTERRUPTED"
            raise
        finally:
            self.experiment["finished_at_unix"] = time.time()
            old = self.h.deadline
            self.h.deadline = max(old, time.monotonic() + 30)
            try:
                self.save(remote=True)
                self.h.bridge(
                    "lease",
                    project=self.h.project,
                    experiment_id=self.experiment["id"],
                    executor_id=self.executor,
                    release=True,
                )
            finally:
                self.h.deadline = old
                self.h.client.close()
                self.lock.close()
        return self.data

    def run_trial(self, entry: dict):
        scenario = self.registry[entry["scenario"]]
        tier = self.experiment["configuration"]["tiers"][entry["tier"]]
        attempts = [t for t in self.data["trials"] if t["logical_key"] == entry["logical_key"]]
        trial = {
            "id": str(uuid4()),
            "experiment_id": self.experiment["id"],
            "logical_key": entry["logical_key"],
            "attempt": len(attempts) + 1,
            "scenario_id": scenario.id,
            "scenario": scenario.model_dump(),
            "seed": entry["seed"],
            "tier": entry["tier"],
            "workload": tier,
            "consistency_profile": entry["consistency_profile"],
            "status": "RUNNING",
            "purpose": "benchmark",
            "started_at_unix": time.time(),
            "fixtures": [],
            "phases": [],
            "faults": [],
        }
        self.data["trials"].append(trial)
        self.save(trial, True)
        faults = Faults(self.h, trial, lambda: self.save(trial, True))
        old = self.h.deadline
        self.h.deadline = min(old, time.monotonic() + scenario.trial_timeout_seconds)
        try:
            trial["resources_before"] = self.h.resources()

            def remember(fixture):
                with self.mutex:
                    previous = next(
                        (
                            f
                            for f in trial["fixtures"]
                            if f["customer_id"] == fixture["customer_id"]
                        ),
                        None,
                    )
                    if previous is None:
                        trial["fixtures"].append(fixture)
                        trial["fixtures"].sort(key=lambda f: f["fixture_index"])
                    self.save(trial)

            fixtures = self.h.parallel(
                lambda i: self.h.fixture(
                    trial["id"], entry["seed"], i, tier["orders_per_customer"], remember
                ),
                range(tier["customers"]),
            )
            actions = scenario.actions
            if "sql_rollback" in actions:
                result = self.h.bridge(
                    "transaction_failure",
                    customer_id=fixtures[0]["customer_id"],
                    order_id=fixtures[0]["fault_id"],
                )
                faults.event("transaction_failure", "OBSERVED", **result)
            skip = [
                t for t, a in (("cache", "skip_cache"), ("search", "skip_search")) if a in actions
            ]
            ephemeral = None
            if skip:
                ephemeral = faults.ephemeral("skip", skip, "deletion.before_connector")
            if "error_after_cache" in actions:
                ephemeral = faults.ephemeral("error_after", ["cache"], "deletion.after_connector")
            if "crash_after_cache" in actions:
                faults.stop("search-consumer")
                ephemeral = faults.ephemeral("exit", ["cache"], "deletion.after_connector")
            if "pause_deletion" in actions:
                faults.stop("deletion-consumer")
            if "duplicate_stale" in actions:
                faults.event("duplicate_stale", "INTENDED")
                faults.event(
                    "duplicate_stale",
                    "ACTIVATED",
                    **self.h.bridge("publish_stale", fixtures=fixtures),
                )
            if "race_orders" in actions:
                with ThreadPoolExecutor(max_workers=4) as pool:
                    futures = [
                        pool.submit(self.race_order, fixture)
                        for fixture in fixtures
                        for _ in range(2)
                    ]
                    self.h.parallel(self.h.submit, fixtures)
                    for future in futures:
                        future.result()
            else:
                self.h.parallel(self.h.submit, fixtures)
            self.save(trial, True)
            if "pause_deletion" in actions:
                self.h.parallel(
                    lambda f: self.measure(trial, f, "pending", False, first_observation=True),
                    fixtures,
                )
                faults.restore()
            if "crash_after_cache" in actions:
                faults.wait_crash(ephemeral)
            statuses = self.h.parallel(self.h.wait_deletion, fixtures)
            trial["operational_states"] = [s["state"] for s in statuses]
            if ephemeral and "crash_after_cache" not in actions:
                faults.attest(ephemeral)
                faults.restore()
            time.sleep(
                min(
                    max(4, 7 if entry["consistency_profile"] == "extended" else 4),
                    self.h.remaining(),
                )
            )
            for action in ("analytics_residue", "order_field"):
                if action in actions:
                    faults.event(action, "INTENDED")
                    result = self.h.bridge("mutate", action=action, fixtures=fixtures)
                    faults.event(action, "ACTIVATED", **result)
            if "pause_redis" in actions:
                faults.pause("redis")
            if "omit_search_adapter" in actions:
                faults.stop("verification-worker")
            if "late_index" in actions:
                self.h.parallel(
                    lambda f: self.measure(trial, f, "before_reappearance", True), fixtures
                )
                delay = random.Random(entry["seed"]).uniform(0.2, 0.6)
                faults.event("late_index", "SCHEDULED", delay_seconds=delay)
                time.sleep(min(delay, self.h.remaining()))
                faults.event(
                    "late_index",
                    "ACTIVATED",
                    **self.h.bridge("mutate", action="late_index", fixtures=fixtures),
                )
            phase = (
                "reappeared"
                if "late_index" in actions
                else "converged"
                if "pause_deletion" in actions
                else "primary"
            )
            (
                self.h.parallel
                if not any(a in actions for a in ("omit_search_adapter", "crash_verifier"))
                else lambda fn, values: [fn(v) for v in values]
            )(
                lambda f: self.measure(
                    trial,
                    f,
                    phase,
                    True,
                    omit="omit_search_adapter" in actions,
                    crash="crash_verifier" in actions,
                    faults=faults,
                ),
                fixtures,
            )
            if "pause_redis" in actions or "late_index" in actions:
                faults.restore()
                if "late_index" in actions:
                    self.h.bridge("cleanup", fixtures=fixtures)
                self.h.parallel(lambda f: self.measure(trial, f, "recovered", True), fixtures)
            trial["status"] = "COMPLETED"
        except Exception as exc:
            trial["status"] = (
                "TIMED_OUT"
                if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired))
                else "FAILED"
            )
            trial["error"] = {
                "code": type(exc).__name__,
                "frames": [
                    {"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
                    for f in traceback.extract_tb(exc.__traceback__)
                ],
                "message": "trial failed; partial measurements retained; inspect bounded timeline and CI diagnostics",
            }
        finally:
            self.h.deadline = max(old, time.monotonic() + 60)
            try:
                errors = faults.restore()
                if trial["fixtures"]:
                    self.h.bridge("cleanup", fixtures=trial["fixtures"])
                trial["cleanup"] = {
                    "status": "RESTORED" if not errors else "ERROR",
                    "errors": errors,
                }
                if errors:
                    trial["status"] = "FAILED"
            except Exception as exc:
                trial["cleanup"] = {"status": "ERROR", "error_class": type(exc).__name__}
                trial["status"] = "FAILED"
            trial["resources_after"] = self.h.resources()
            trial["finished_at_unix"] = time.time()
            trial["elapsed_seconds"] = trial["finished_at_unix"] - trial["started_at_unix"]
            self.save(trial, True)
            self.h.deadline = old

    def race_order(self, fixture):
        response = self.h.client.post(
            "http://127.0.0.1:8001/v1/orders",
            json={"customer_id": fixture["customer_id"], "amount_cents": 1234},
            headers={"X-Operator-Token": os.getenv("OPERATOR_TOKEN", "")},
            timeout=10,
        )
        if response.status_code == 201:
            with self.mutex:
                fixture["order_ids"].append(response.json()["id"])
        elif response.status_code != 409:
            response.raise_for_status()

    def measure(
        self,
        trial,
        fixture,
        phase,
        eligible,
        first_observation=False,
        omit=False,
        crash=False,
        faults=None,
    ):
        before = self.h.oracle(fixture, eligible)
        started = time.monotonic()
        api_started = time.monotonic()
        metadata = self.h.deletion(fixture)
        api_elapsed = time.monotonic() - api_started
        selected = self.experiment["configuration"]["selected_methods"]
        if "eraseproof" not in selected:
            after = self.h.oracle(fixture, eligible)
            truth = (
                after
                if before["state"] == after["state"]
                else {"state": "PENDING", "targets": after["targets"], "transition_observed": True}
            )
            methods = {}
            if "api_ack" in selected:
                methods["api_ack"] = {
                    **api_acknowledgment(metadata),
                    "elapsed_seconds": api_elapsed,
                }
            if "workflow" in selected:
                methods["workflow"] = {**workflow_monitor(metadata), "elapsed_seconds": api_elapsed}
            row = {
                "phase": phase,
                "customer_id": fixture["customer_id"],
                "deletion_request_id": fixture["deletion_request_id"],
                "oracle": truth,
                "oracle_before": before,
                "oracle_after": after,
                "methods": methods,
                "same_fixture_for_all_methods": True,
                "observed_at_unix": time.time(),
            }
            with self.mutex:
                trial["phases"].append(row)
                self.save(trial, True)
            return
        if crash:
            self.verify_lock(trial)
        run = self.h.request(
            "POST",
            8006,
            f"/v1/deletions/{fixture['deletion_request_id']}/verifications",
            "verification",
            json={
                "idempotency_key": f"{trial['id']}:{fixture['customer_id']}:{phase}",
                "consistency_profile": trial["consistency_profile"],
            },
        )
        if omit:
            self.omitted_worker(run)
        if crash:
            self.crash_verifier(trial, run, faults)

        def read():
            return self.h.request("GET", 8006, f"/v1/verifications/{run['id']}", "verification")

        self.h.wait(
            read,
            lambda r: r["round_no"] > 0 and r["state"] == "WAITING"
            if first_observation
            else r["state"] == "FINISHED",
        )
        report = self.h.request(
            "GET", 8006, f"/v1/verifications/{run['id']}/report", "verification"
        )
        elapsed = time.monotonic() - started
        if not validate_chain(report["evidence"]):
            raise AssertionError("evidence integrity failure")
        after = self.h.oracle(fixture, eligible)
        truth = (
            after
            if before["state"] == after["state"]
            else {"state": "PENDING", "targets": after["targets"], "transition_observed": True}
        )
        methods = {
            "api_ack": api_acknowledgment(metadata),
            "workflow": workflow_monitor(metadata),
            "eraseproof": independent_prediction(report),
        }
        methods["api_ack"]["elapsed_seconds"] = api_elapsed
        methods["workflow"]["elapsed_seconds"] = api_elapsed
        methods["eraseproof"]["elapsed_seconds"] = elapsed
        methods = {key: value for key, value in methods.items() if key in selected}
        name = f"{run['id']}.json"
        folder = self.output / "evidence"
        folder.mkdir(exist_ok=True)
        (folder / name).write_text(json.dumps(report, indent=2) + "\n")
        row = {
            "phase": phase,
            "customer_id": fixture["customer_id"],
            "deletion_request_id": fixture["deletion_request_id"],
            "verification_id": run["id"],
            "oracle": truth,
            "oracle_before": before,
            "oracle_after": after,
            "methods": methods,
            "operational_state": metadata["state"],
            "evidence_file": "evidence/" + name,
            "observed_at_unix": time.time(),
            "same_fixture_for_all_methods": True,
        }
        with self.mutex:
            trial["phases"].append(row)
            self.save(trial, True)

    def omitted_worker(self, run):
        self.h.docker(
            "run",
            "--rm",
            "--no-deps",
            "-e",
            "ENABLE_TEST_FAULTS=1",
            "-e",
            "VERIFICATION_TEST_DISABLE_ADAPTERS=search",
            "verification-worker",
            "python",
            "-c",
            f"""
import time
from uuid import UUID
from eraseproof.db import connection
from eraseproof.verification import execute
from eraseproof.verification_models import VerificationCommand
for _ in range(30):
 with connection() as db:r=db.execute('SELECT * FROM verification.runs WHERE id=%s',(UUID('{run["id"]}'),)).fetchone()
 if r['state']=='RUNNING':
  execute(VerificationCommand(event_id=r['active_message'],run_id=r['id'],round_no=r['round_no']));break
 time.sleep(.2)
else:raise RuntimeError('missing verification dispatch')
""",
            timeout=30,
        )

    def verify_lock(self, trial):
        application = "research-lock-" + trial["id"][:12]
        self.h.docker(
            "exec",
            "-d",
            "customer",
            "python",
            "-c",
            f"""
import time,psycopg
from eraseproof.config import DATABASE_URL
with psycopg.connect(DATABASE_URL,application_name='{application}') as db:
 db.execute('LOCK TABLE customer.customers IN ACCESS EXCLUSIVE MODE');time.sleep(15)
""",
        )
        self.h.wait(
            lambda: self.h.bridge("lock_status", application=application),
            lambda r: r["held"],
            seconds=5,
        )

    def crash_verifier(self, trial, run, faults):
        try:
            self.h.wait(
                lambda: self.h.request(
                    "GET", 8006, f"/v1/verifications/{run['id']}/timeline", "verification"
                ),
                lambda r: any(e["kind"] == "verification.probing" for e in r["items"]),
                seconds=10,
            )
            faults.event("verification_crash", "INTENDED")
            self.h.docker("kill", "-s", "SIGKILL", "verification-worker")
            faults.event("verification_crash", "ACTIVATED")
        finally:
            self.h.bridge("release_lock", application="research-lock-" + trial["id"][:12])
            self.h.docker("restart", "verification-worker")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", default="research/phase-4/config/ci.v1.json")
    parser.add_argument("--project", default="eraseproof-research")
    parser.add_argument("--output", default="work/phase4-ci")
    parser.add_argument("--scenario")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--tier", choices=["small", "medium", "large"], default="small")
    parser.add_argument(
        "--methods",
        nargs="+",
        choices=["api_ack", "workflow", "eraseproof"],
        default=["api_ack", "workflow", "eraseproof"],
    )
    parser.add_argument("--consistency-profile", choices=["default", "extended"])
    parser.add_argument("--concurrency", type=int, choices=range(1, 5))
    parser.add_argument("--max-seconds", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--repeats", type=int, choices=range(1, 11))
    args = parser.parse_args()
    if args.seed is not None and not 0 <= args.seed <= 2147483647:
        parser.error("seed must fit 0..2147483647")
    if args.seed is not None and not args.scenario:
        parser.error("--seed requires --scenario; full matrices record their explicit seed lists")
    if len(args.methods) != len(set(args.methods)):
        parser.error("methods must be unique")
    config = matrix(args.matrix).model_dump()
    if args.scenario:
        _, registry = catalog()
        if args.scenario not in registry:
            parser.error("unknown scenario")
        config["entries"] = [
            {
                "scenario": args.scenario,
                "tier": args.tier,
                "seeds": [args.seed if args.seed is not None else 101],
                "repeats": 1,
                "consistency_profile": args.consistency_profile or "default",
            }
        ]
    if args.consistency_profile:
        for entry in config["entries"]:
            entry["consistency_profile"] = args.consistency_profile
    if args.repeats:
        for entry in config["entries"]:
            entry["repeats"] = args.repeats
    if args.max_seconds is not None:
        if not 60 <= args.max_seconds <= 7200:
            parser.error("maximum seconds must be 60..7200")
        config["maximum_seconds"] = min(config["maximum_seconds"], args.max_seconds)
    if args.concurrency:
        config["concurrency"] = args.concurrency
    config["selected_methods"] = args.methods
    h = Harness(args.project, config["concurrency"], config["maximum_seconds"])
    runner = Runner(h, config, Path(args.output), args.resume)
    result = runner.run()
    print(json.dumps(result["summary"], indent=2))
    if result["experiment"]["state"] != "COMPLETED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
