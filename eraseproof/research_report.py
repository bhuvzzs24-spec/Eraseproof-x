"""Validate and visualize measured datasets; no result generator or synthetic benchmark shortcut."""

from collections import defaultdict
from pathlib import Path
import argparse
import csv
import json
import random
from statistics import mean
from eraseproof.evidence import digest
from eraseproof.research_metrics import summarize


def load(path: Path) -> dict:
    data = json.loads(path.read_text())
    claimed = data.pop("dataset_digest")
    if digest(data) != claimed:
        raise ValueError("dataset digest mismatch")
    if data["format_version"] != "phase4-dataset-v1":
        raise ValueError("unsupported dataset format")
    if summarize(data["trials"]) != {
        k: v
        for k, v in data["summary"].items()
        if k not in ("planned_logical_trials", "unexecuted_logical_trials")
    }:
        raise ValueError("stored metrics disagree with raw measured rows")
    return data


def cluster_comparison(trials: list[dict], first: str, second: str, replicates=2000) -> dict:
    differences = []
    for trial in trials:
        rows = []
        for phase in trial.get("phases", []):
            truth = phase["oracle"]["state"]
            a = phase.get("methods", {}).get(first, {}).get("prediction", "ABSTAIN")
            b = phase.get("methods", {}).get(second, {}).get("prediction", "ABSTAIN")
            if truth in ("ABSENT", "RESIDUAL") and "ABSTAIN" not in (a, b):
                rows.append(int(b == truth) - int(a == truth))
        if rows:
            differences.append(mean(rows))
    if len(differences) < 2:
        return {
            "clusters": len(differences),
            "mean_difference": mean(differences) if differences else None,
            "bootstrap_95": None,
            "reason": "at least two physical trial clusters required",
        }
    rng = random.Random("phase4-bootstrap-v1:" + first + ":" + second)
    samples = sorted(mean(rng.choices(differences, k=len(differences))) for _ in range(replicates))
    return {
        "clusters": len(differences),
        "mean_difference": mean(differences),
        "bootstrap_95": [
            samples[int(0.025 * replicates)],
            samples[min(replicates - 1, int(0.975 * replicates))],
        ],
        "resamples": replicates,
        "seed": "phase4-bootstrap-v1:" + first + ":" + second,
        "estimand": "equally weighted physical-trial mean correctness difference on jointly conclusive rows; correlated rows remain together",
        "warning": "fixed selected synthetic scenarios; not a production-population confidence claim",
    }


def generate(dataset: Path, output: Path, plots=True) -> dict:
    data = load(dataset)
    output.mkdir(parents=True, exist_ok=True)
    summary = summarize(data["trials"])
    summary["provenance"] = {
        "code_commit": data["experiment"]["code_commit"],
        "configuration_digest": data["experiment"]["configuration_digest"],
        "dataset_digest": digest(data),
    }
    summary["cluster_comparisons"] = [
        {
            "first": p["first"],
            "second": p["second"],
            **cluster_comparison(data["trials"], p["first"], p["second"]),
        }
        for p in summary["paired"]
    ]
    strata = defaultdict(list)
    for t in data["trials"]:
        strata[(t["scenario_id"], t["tier"])].append(t)
    summary["strata"] = {
        f"{scenario}/{tier}": summarize(items) for (scenario, tier), items in strata.items()
    }
    (output / "aggregate.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (output / "decisions.csv").open("w", newline="") as stream:
        fields = [
            "trial_id",
            "scenario",
            "seed",
            "tier",
            "phase",
            "customer_id",
            "oracle",
            "method",
            "prediction",
            "outcome",
            "elapsed_seconds",
            "data_queries",
        ]
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for trial in data["trials"]:
            for phase in trial.get("phases", []):
                for method, prediction in phase["methods"].items():
                    writer.writerow(
                        dict(
                            trial_id=trial["id"],
                            scenario=trial["scenario_id"],
                            seed=trial["seed"],
                            tier=trial["tier"],
                            phase=phase["phase"],
                            customer_id=phase["customer_id"],
                            oracle=phase["oracle"]["state"],
                            method=method,
                            **{
                                key: prediction.get(key)
                                for key in (
                                    "prediction",
                                    "outcome",
                                    "elapsed_seconds",
                                    "data_queries",
                                )
                            },
                        )
                    )
    lines = [
        "# Measured Phase 4 comparison",
        "",
        f"Code commit: `{data['experiment']['code_commit']}`",
        "",
        f"Physical trials: {summary['physical_trials']}; complete: {summary['completed_trials']}; failed: {summary['failed_trials']}; timed out: {summary['timed_out_trials']}; interrupted: {summary['interrupted_trials']}.",
        "",
        "| Method | TP | FP | TN | FN | Abstained on known truth | Coverage | Precision | Recall | FPR | FNR |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    def cell(metric):
        return (
            "undefined"
            if metric["value"] is None
            else f"{metric['value']:.3f} (n={metric['denominator']})"
        )

    for name, m in summary["methods"].items():
        lines.append(
            f"| {name} | {m['tp']} | {m['fp']} | {m['tn']} | {m['fn']} | {m['abstained_on_binary_rows']} | {cell(m['coverage'])} | {cell(m['precision'])} | {cell(m['recall'])} | {cell(m['false_positive_rate'])} | {cell(m['false_negative_rate'])} |"
        )
    lines += [
        "",
        "Quality rates are conditional on binary oracle truth and a conclusive method prediction. Undefined denominators remain undefined. Full positive detection yield and abstentions are also exported; unknown oracle rows and failed trials are never counted as successful negatives.",
        "",
        "Wilson 95% intervals, raw denominators, paired discordant counts, cluster-resampled differences, mean/median/nearest-rank p95 and per-scenario workload strata are in aggregate.json. Wilson intervals and paired exact calculations are descriptive under their independence assumptions; selected scenarios and correlated customers limit generalization. Cluster bootstrap retains rows within each physical trial.",
        "",
        "These are internal architectural baselines, not commercial products. API and workflow monitors may legitimately agree because the backend atomically enforces workflow completion invariants. Resource snapshots cover the shared stack and are not attributed causal CPU/memory cost per method.",
    ]
    (output / "results.md").write_text("\n".join(lines) + "\n")
    if plots:
        plot(data, summary, output)
    return summary


def plot(data, summary, output):
    import os
    import tempfile

    os.environ.setdefault(
        "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "eraseproof-phase4-mpl")
    )
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = list(summary["methods"])
    colors = ["#6B7280", "#3478A5", "#167B63"]
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout="constrained")
    for i, (metric, title) in enumerate(
        (
            ("recall", "Residual detection recall (conclusive cases)"),
            ("coverage", "Conclusive coverage of known oracle cases"),
        )
    ):
        for j, name in enumerate(names):
            item = summary["methods"][name][metric]
            if item["value"] is None:
                axes[i].text(j, 0.04, "undefined", ha="center", rotation=90)
                continue
            value = item["value"]
            interval = item["wilson_95"]
            axes[i].bar(j, value, color=colors[j % len(colors)])
            axes[i].errorbar(
                j,
                value,
                yerr=[[value - interval[0]], [interval[1] - value]],
                fmt="none",
                color="#202830",
                capsize=4,
            )
            axes[i].text(
                j, min(1.06, value + 0.04), f"n={item['denominator']}", ha="center", fontsize=9
            )
        axes[i].set_xticks(range(len(names)), names, rotation=12)
        axes[i].set_ylim(0, 1.15)
        axes[i].set_title(title, fontsize=11)
        axes[i].set_ylabel("Proportion; descriptive Wilson 95% interval")
        axes[i].grid(axis="y", alpha=0.2)
    figure.suptitle("Measured synthetic scenarios — internal baselines", fontsize=13)
    figure.savefig(output / "quality-and-coverage.png", dpi=180)
    figure.savefig(output / "quality-and-coverage.pdf")
    plt.close(figure)
    latencies = {
        name: [
            p["methods"][name]["elapsed_seconds"]
            for t in data["trials"]
            for p in t.get("phases", [])
            if name in p["methods"]
        ]
        for name in names
    }
    figure, axis = plt.subplots(figsize=(8, 4.7), layout="constrained")
    for i, name in enumerate(names):
        ys = latencies[name]
        axis.scatter([i] * len(ys), ys, alpha=0.6, color=colors[i % len(colors)], s=24)
        if ys:
            axis.plot(
                [i - 0.2, i + 0.2], [sorted(ys)[len(ys) // 2]] * 2, color="black", linewidth=2
            )
    axis.set_xticks(range(len(names)), names)
    axis.set_yscale("log")
    axis.set_ylabel("Method call to outcome, seconds (log scale)")
    axis.set_title("Observed latency distribution, including uncertainty outcomes")
    axis.grid(axis="y", alpha=0.2)
    figure.savefig(output / "latency-distribution.png", dpi=180)
    figure.savefig(output / "latency-distribution.pdf")
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    summary = generate(args.dataset, args.output, not args.no_plots)
    print(
        json.dumps(
            {
                "physical_trials": summary["physical_trials"],
                "decision_rows": summary["decision_rows"],
                "output": str(args.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
