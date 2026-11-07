"""Explicit denominators, abstentions, Wilson intervals and paired descriptive comparisons."""

import math
from statistics import NormalDist, mean, median, pstdev
from itertools import combinations

METHODS = ("api_ack", "workflow", "eraseproof")


def wilson(successes: int, total: int, confidence: float = 0.95) -> list[float] | None:
    if not 0 <= successes <= total or not 0 < confidence < 1:
        raise ValueError("invalid proportion")
    if total == 0:
        return None
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0, center - radius), min(1, center + radius)]


def distribution(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "median": None, "p95": None, "stdev_population": None}
    ordered = sorted(values)
    return {
        "n": len(values),
        "mean": mean(values),
        "median": median(values),
        "p95": ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)],
        "stdev_population": pstdev(values),
        "p95_method": "nearest rank; small-sample descriptive only",
    }


def ratio(numerator: int, denominator: int) -> dict:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
        "wilson_95": wilson(numerator, denominator),
    }


def summarize(trials: list[dict]) -> dict:
    rows = [phase for trial in trials for phase in trial.get("phases", [])]
    result = {
        "physical_trials": len(trials),
        "completed_trials": sum(t["status"] == "COMPLETED" for t in trials),
        "failed_trials": sum(t["status"] == "FAILED" for t in trials),
        "timed_out_trials": sum(t["status"] == "TIMED_OUT" for t in trials),
        "interrupted_trials": sum(t["status"] == "INTERRUPTED" for t in trials),
        "decision_rows": len(rows),
        "scenarios": sorted({t["scenario_id"] for t in trials}),
        "methods": {},
        "paired": [],
        "trial_failures_are_not_removed": True,
        "latency_warning": "CPU/memory snapshots and nearest-rank p95 are descriptive; customers/phases in a trial are correlated.",
    }
    binary = [r for r in rows if r["oracle"]["state"] in ("ABSENT", "RESIDUAL")]
    selected = [m for m in METHODS if any(m in r.get("methods", {}) for r in rows)]
    for method in selected:
        tp = fp = tn = fn = abstain = unknown_clearance = 0
        outcomes = {}
        latencies = []
        queries = 0
        covered = set()
        for row in rows:
            prediction = row.get("methods", {}).get(
                method, {"prediction": "ABSTAIN", "outcome": "METHOD_ERROR", "data_queries": 0}
            )
            state = prediction["prediction"]
            truth = row["oracle"]["state"]
            outcome = prediction["outcome"]
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
            if truth not in ("ABSENT", "RESIDUAL"):
                unknown_clearance += int(state == "ABSENT")
                continue
            if state == "ABSTAIN":
                abstain += 1
                continue
            tp += int(truth == "RESIDUAL" and state == "RESIDUAL")
            fp += int(truth == "ABSENT" and state == "RESIDUAL")
            tn += int(truth == "ABSENT" and state == "ABSENT")
            fn += int(truth == "RESIDUAL" and state == "ABSENT")
        for row in rows:
            p = row.get("methods", {}).get(method, {})
            queries += p.get("data_queries", 0)
            covered.update(p.get("targets", {}))
            if p.get("elapsed_seconds") is not None:
                latencies.append(p["elapsed_seconds"])
        scored = tp + fp + tn + fn
        result["methods"][method] = {
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "binary_oracle_rows": len(binary),
            "scored_rows": scored,
            "abstained_on_binary_rows": abstain,
            "positive_oracle_rows": sum(r["oracle"]["state"] == "RESIDUAL" for r in binary),
            "positive_abstentions": sum(
                r["oracle"]["state"] == "RESIDUAL"
                and r.get("methods", {}).get(method, {}).get("prediction", "ABSTAIN") == "ABSTAIN"
                for r in binary
            ),
            "full_positive_detection_yield": ratio(
                tp, sum(r["oracle"]["state"] == "RESIDUAL" for r in binary)
            ),
            "precision": ratio(tp, tp + fp),
            "recall": ratio(tp, tp + fn),
            "false_positive_rate": ratio(fp, fp + tn),
            "false_negative_rate": ratio(fn, fn + tp),
            "coverage": ratio(scored, len(binary)),
            "abstention_rate": ratio(abstain, len(binary)),
            "oracle_unknown_rows": len(rows) - len(binary),
            "clearance_with_unknown_oracle": unknown_clearance,
            "outcomes": outcomes,
            "latency_seconds": distribution(latencies),
            "time_to_detection_seconds": distribution(
                [
                    r["methods"][method]["elapsed_seconds"]
                    for r in binary
                    if r.get("methods", {}).get(method, {}).get("prediction") == "RESIDUAL"
                    and r["oracle"]["state"] == "RESIDUAL"
                ]
            ),
            "time_to_verified_absence_seconds": distribution(
                [
                    r["methods"][method]["elapsed_seconds"]
                    for r in binary
                    if r.get("methods", {}).get(method, {}).get("prediction") == "ABSENT"
                    and r["oracle"]["state"] == "ABSENT"
                ]
            ),
            "recorded_data_queries": queries,
            "targets_with_reported_checks": sorted(covered),
            "storage_category_outcomes": {
                target: {
                    state: sum(
                        p.get("methods", {}).get(method, {}).get("targets", {}).get(target) == state
                        for p in rows
                    )
                    for state in sorted(
                        {
                            p.get("methods", {}).get(method, {}).get("targets", {}).get(target)
                            for p in rows
                            if target in p.get("methods", {}).get(method, {}).get("targets", {})
                        }
                    )
                }
                for target in sorted(covered)
            },
            "quality_denominator": "binary oracle AND conclusive method prediction; abstentions separate",
        }
    for first, second in combinations(selected, 2):
        a_only = b_only = both = 0
        for row in binary:
            a = row.get("methods", {}).get(first, {}).get("prediction", "ABSTAIN")
            b = row.get("methods", {}).get(second, {}).get("prediction", "ABSTAIN")
            if "ABSTAIN" in (a, b):
                continue
            ac = a == row["oracle"]["state"]
            bc = b == row["oracle"]["state"]
            both += 1
            a_only += int(ac and not bc)
            b_only += int(bc and not ac)
        discordant = a_only + b_only
        p = (
            min(
                1.0,
                2
                * sum(
                    math.comb(discordant, k) * 0.5**discordant
                    for k in range(min(a_only, b_only) + 1)
                ),
            )
            if discordant
            else 1.0
        )
        result["paired"].append(
            {
                "first": first,
                "second": second,
                "jointly_scorable_rows": both,
                "first_only_correct": a_only,
                "second_only_correct": b_only,
                "exact_discordant_binomial_p": p,
                "interpretation": "Exploratory paired sign/McNemar-style exact calculation; correlated fixtures and selected scenarios preclude population significance claims.",
            }
        )
    result["recovery"] = {
        "phases_succeeded": sum(
            r.get("phase") == "recovered"
            and r["oracle"]["state"] == "ABSENT"
            and r["methods"].get("eraseproof", {}).get("prediction") == "ABSENT"
            for r in rows
        ),
        "phases_failed": sum(
            r.get("phase") == "recovered"
            and not (
                r["oracle"]["state"] == "ABSENT"
                and r["methods"].get("eraseproof", {}).get("prediction") == "ABSENT"
            )
            for r in rows
        ),
        "reappearance_cases_detected": sum(
            r.get("phase") == "reappeared"
            and r["methods"].get("eraseproof", {}).get("prediction") == "RESIDUAL"
            for r in rows
        ),
        "false_operational_success_exposed": sum(
            r["methods"].get("eraseproof", {}).get("false_success", False) for r in rows
        ),
    }
    result["deletion_latency_seconds"] = distribution(
        [
            c["deletion_latency_seconds"]
            for t in trials
            for c in t.get("fixtures", [])
            if c.get("deletion_latency_seconds") is not None
        ]
    )
    result["retry_attempts"] = sum(
        c.get("retry_attempts", 0) for t in trials for c in t.get("fixtures", [])
    )
    return result
