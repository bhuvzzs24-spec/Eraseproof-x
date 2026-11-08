# Measured Phase 4 comparison

Code commit: `0e115298774c4b79ad4b7ec3aa343dd037700ae1`

Physical trials: 21; complete: 21; failed: 0; timed out: 0; interrupted: 0.

| Method | TP | FP | TN | FN | Abstained on known truth | Coverage | Precision | Recall | FPR | FNR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| api_ack | 0 | 1 | 21 | 18 | 0 | 1.000 (n=40) | 0.000 (n=1) | 0.000 (n=18) | 0.045 (n=22) | 1.000 (n=18) |
| workflow | 0 | 1 | 21 | 18 | 0 | 1.000 (n=40) | 0.000 (n=1) | 0.000 (n=18) | 0.045 (n=22) | 1.000 (n=18) |
| eraseproof | 18 | 0 | 21 | 0 | 1 | 0.975 (n=40) | 1.000 (n=18) | 1.000 (n=18) | 0.000 (n=21) | 0.000 (n=18) |

Quality rates are conditional on binary oracle truth and a conclusive method prediction. Undefined denominators remain undefined. Full positive detection yield and abstentions are also exported; unknown oracle rows and failed trials are never counted as successful negatives.

Wilson 95% intervals, raw denominators, paired discordant counts, cluster-resampled differences, mean/median/nearest-rank p95 and per-scenario workload strata are in aggregate.json. Wilson intervals and paired exact calculations are descriptive under their independence assumptions; selected scenarios and correlated customers limit generalization. Cluster bootstrap retains rows within each physical trial.

These are internal architectural baselines, not commercial products. API and workflow monitors may legitimately agree because the backend atomically enforces workflow completion invariants. Resource snapshots cover the shared stack and are not attributed causal CPU/memory cost per method.
