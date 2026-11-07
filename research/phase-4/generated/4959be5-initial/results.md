# Measured Phase 4 comparison

Code commit: `4959be5d4b249b5feacb7b430a8a42c6569eabfc`

Physical trials: 21; complete: 17; failed: 4; timed out: 0; interrupted: 0.

| Method | TP | FP | TN | FN | Abstained on known truth | Coverage | Precision | Recall | FPR | FNR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| api_ack | 0 | 1 | 19 | 9 | 0 | 1.000 (n=29) | 0.000 (n=1) | 0.000 (n=9) | 0.050 (n=20) | 1.000 (n=9) |
| workflow | 0 | 1 | 19 | 9 | 0 | 1.000 (n=29) | 0.000 (n=1) | 0.000 (n=9) | 0.050 (n=20) | 1.000 (n=9) |
| eraseproof | 9 | 0 | 19 | 0 | 1 | 0.966 (n=29) | 1.000 (n=9) | 1.000 (n=9) | 0.000 (n=19) | 0.000 (n=9) |

Quality rates are conditional on binary oracle truth and a conclusive method prediction. Undefined denominators remain undefined. Full positive detection yield and abstentions are also exported; unknown oracle rows and failed trials are never counted as successful negatives.

Wilson 95% intervals, raw denominators, paired discordant counts, cluster-resampled differences, mean/median/nearest-rank p95 and per-scenario workload strata are in aggregate.json. Wilson intervals and paired exact calculations are descriptive under their independence assumptions; selected scenarios and correlated customers limit generalization. Cluster bootstrap retains rows within each physical trial.

These are internal architectural baselines, not commercial products. API and workflow monitors may legitimately agree because the backend atomically enforces workflow completion invariants. Resource snapshots cover the shared stack and are not attributed causal CPU/memory cost per method.
