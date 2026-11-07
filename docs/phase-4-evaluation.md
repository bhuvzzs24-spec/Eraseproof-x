# EraseProof X — Phase 4 completion and scientific evaluation

## A. Implementation and experimental scope

Phase 4 adds a reusable, opt-in local Docker fault framework, a 16-scenario versioned registry, a seeded resumable CLI runner, two faithful internal monitoring baselines, a separate direct-store oracle, statistical exports, measured comparison charts and protected read-only Phase 5 data contracts. Phase 1–3 services and tests are preserved. This is controlled experimental evidence for the working hypothesis, not a novelty claim, enterprise-product comparison, regulatory certification or proof about every copy of data.

Implementation revision: `61dd8e83c8a32d480dd7dc85d1a940ee8a879e46`. Branch: `main`. The curated data/documentation commit follows this runtime revision; its exact hash is recorded in the delivery manifest. Runtime and benchmark source are unchanged by that artifact commit.

### Framework and safeguards

`research_hooks.py` provides fixed before/after connector points, with exact synthetic-subject gates, skip/exit/error actions, and no-ops by default. `research_faults.py`, `research_admin.py` and `research_watchdog.py` implement bounded service pause/stop/restart, confirmed stale/duplicate publication, real post-mutation worker exit, SQL rollback, controlled residue and legacy reindex writes, verification SIGKILL and scoped restoration. There is no public HTTP fault endpoint. Normal Compose does not activate research flags.

Isolation checks require explicit opt-in, APP_ENV=demo, a named research project, configured and actual research container labels, a local Unix Docker engine and verified loopback API bindings. A database project lease excludes overlapping batches; a journal file lock excludes overlapping local executors. Watchdog ownership tokens prevent old restoration tasks from undoing later faults. Cleanup only targets recorded fixtures and fixed namespaces, preserving declared audit/erasure metadata. A privileged malicious operator is outside this threat model.

`research_runner.py` records committed source, configuration/catalog digests, seeded shuffled plan, actual UUIDs, workload, faults, oracle observations, predictions, timing, query counts, CPU/memory snapshots, safe error codes, cleanup and evidence references. Journals use atomic replacement, fsync and canonical digests. Failed, timed-out and interrupted attempts remain visible. Resume requires identical source/configuration, retains interrupted attempts and respects the original deadline. Full executor-kill/resume behavior is implemented and unit-tested; the actual Docker suite additionally tests exclusion of a concurrent lease owner. It is not presented as a separately executed batch-kill experiment.

Failure minimization is deferred: real replay multiplies trial cost and race reductions need an explicit non-monotonic preservation predicate. Recorded action timelines are available for a later bounded delta-debugging tool. The full frontend belongs to Phase 5 and was not built.

### Fair methods and independent truth

API acknowledgment uses final API completion or failure, not 202 acceptance. Workflow monitoring checks all six required targets and latest durable attempts, accepting successful recovered retries. Operational failure is an incompleteness alarm, not direct residue evidence; scoring it as a positive permits explicit measurement of privacy false alarms. Neither baseline receives fault assignments, oracle labels or stored personal fields. They share one operational metadata snapshot and may legitimately agree because the application atomically enforces completion invariants. No artificial weakness is added to distinguish them.

EraseProof X calls the real Phase 3 verifier and read-only adapters, preserving consistency windows, evidence chains and uncertainty. Each method sees the same fixture and phase. The oracle brackets method evaluation and marks changing truth pending. A separate privileged oracle inspects known fixture primary rows, API-known orders, known Redis keys, known search documents, analytics rows and event history. It imports no evaluated adapters/verdict aggregator and never treats the catalog expectation or verifier verdict as ground truth. It distinguishes ABSENT, RESIDUAL, PENDING, UNAVAILABLE and UNSUPPORTED. It is complete for the controlled footprint, not arbitrary unknown production copies.

## B. Actual benchmark outcomes

Final batch: **16 scenarios, 21 physical trials, 21 completed, 0 failed, 0 timed out, 0 interrupted**, with 43 customer/phase decision rows. Plan slots unexecuted: 0. Runtime: 814.7s. Fixed plan-order seed 20261107; registry/matrix record seeds 101 and 202 without post-hoc selection.

Oracle states: ABSENT=22, PENDING=1, RESIDUAL=18, UNAVAILABLE=2. Each method has the same rows. A physical trial may contain multiple correlated customer/phase decisions. These counts must not be reported as independent experimental replicates.

### Confusion counts and uncertainty

Positive means eligible residual data. Confusion counts include only binary oracle truth and a conclusive method. Unknown oracle rows and abstentions are separate; undefined denominators remain undefined. All brackets below are descriptive Wilson 95% intervals.

| Method | TP | FP | TN | FN | Abstain on binary truth | Unknown truth | Clearance under unknown truth |
|---|---:|---:|---:|---:|---:|---:|---:|
| api_ack | 0 | 1 | 21 | 18 | 0 | 3 | 2 |
| workflow | 0 | 1 | 21 | 18 | 0 | 3 | 2 |
| eraseproof | 18 | 0 | 21 | 0 | 1 | 3 | 0 |

| Method | Precision | Recall | FPR | FNR | Conclusive coverage | Full positive yield |
|---|---|---|---|---|---|---|
| api_ack | 0/1 = 0.0% [0.0, 79.3] | 0/18 = 0.0% [0.0, 17.6] | 1/22 = 4.5% [0.8, 21.8] | 18/18 = 100.0% [82.4, 100.0] | 40/40 = 100.0% [91.2, 100.0] | 0/18 = 0.0% [0.0, 17.6] |
| workflow | 0/1 = 0.0% [0.0, 79.3] | 0/18 = 0.0% [0.0, 17.6] | 1/22 = 4.5% [0.8, 21.8] | 18/18 = 100.0% [82.4, 100.0] | 40/40 = 100.0% [91.2, 100.0] | 0/18 = 0.0% [0.0, 17.6] |
| eraseproof | 18/18 = 100.0% [82.4, 100.0] | 18/18 = 100.0% [82.4, 100.0] | 0/21 = 0.0% [0.0, 15.5] | 0/18 = 0.0% [0.0, 17.6] | 39/40 = 97.5% [87.1, 99.6] | 18/18 = 100.0% [82.4, 100.0] |

Verifier outcomes: FALSE_SUCCESS_DETECTED=18, INCONCLUSIVE=2, PENDING_CONSISTENCY=1, UNSUPPORTED=1, VERIFIED_ABSENT=21.

All six supported storage categories have actual probe records. The verifier recorded 1252 data-plane commands across 43 exported reports. Baselines issue zero store-verification queries, while sharing one operational API metadata fetch. Commands exclude oracle/control work and uncommitted probes lost during a worker crash. Per-store outcome tables are in aggregate.json; a positive root verdict can terminate while another target remains pending, so a checked target is not automatically a verified-absent target.

### Latency and measured overhead

| Method | Call-to-outcome distribution | Store commands |
|---|---|---:|
| api_ack | n=43; mean 0.017s; median 0.016s; p95 0.026s; population SD 0.004s | 0 |
| workflow | n=43; mean 0.017s; median 0.016s; p95 0.026s; population SD 0.004s | 0 |
| eraseproof | n=43; mean 5.846s; median 6.916s; p95 8.005s; population SD 2.416s | 1252 |

Residual detection: n=18; mean 4.084s; median 4.129s; p95 4.784s; population SD 0.397s.

Verified absence: n=21; mean 7.103s; median 6.978s; p95 7.533s; population SD 0.282s.

Deletion request to observed operational completion: n=36; mean 4.647s; median 3.468s; p95 7.919s; population SD 5.041s. This polling measurement can exceed the database completion time. Nearest-rank p95 is descriptive with small n. Latency includes real consistency waits and uncertainty outcomes; it is not a production SLO or a causal estimate of total system cost.

The observed mean independent-verifier call took 5.829s longer than the metadata baseline. This is a clear cost of real multi-store checks; whether it is acceptable depends on deployment requirements. Both latency distributions are plotted rather than reducing the comparison to one percentage.

CPU percent and memory usage are actual before/after Docker snapshots stored per trial. They describe the shared stack at those instants, not peak usage, integrated CPU time or per-method attribution. Faults change running service membership; no fabricated isolated CPU overhead or peak-memory claim is made.


### Actual shared-stack snapshots

Available CPU snapshots: 42; memory snapshots: 42; unavailable snapshot records: 0. These are sums across observed project containers, with varying service membership.

| Snapshot quantity | Mean | Median | Minimum | Maximum observed sample |
|---|---:|---:|---:|---:|
| Summed Docker CPU percent (100% = one core) | 27.18 | 16.79 | 7.27 | 107.96 |
| Summed container memory usage (MiB) | 1795.54 | 1791.43 | 1742.30 | 1864.32 |

Maximum observed sample is not a measured process peak. No baseline-specific CPU subtraction is valid because all methods share the same trial stack.

### Scenario and workload results

| Scenario | Seeds | Physical completion | Phase rows | Oracle observations | Verifier observations |
|---|---|---|---:|---|---|
| ambiguous_reply | 101 | {'COMPLETED': 1} | 1 | {'ABSENT': 1} | {'VERIFIED_ABSENT': 1} |
| analytics_residue | 101 | {'COMPLETED': 1} | 1 | {'RESIDUAL': 1} | {'FALSE_SUCCESS_DETECTED': 1} |
| capability_gap | 101 | {'COMPLETED': 1} | 1 | {'ABSENT': 1} | {'UNSUPPORTED': 1} |
| concurrent_order_delete | 101 | {'COMPLETED': 1} | 3 | {'ABSENT': 3} | {'VERIFIED_ABSENT': 3} |
| crash_stale_combo | 101 | {'COMPLETED': 1} | 1 | {'ABSENT': 1} | {'VERIFIED_ABSENT': 1} |
| database_transaction | 101 | {'COMPLETED': 1} | 1 | {'ABSENT': 1} | {'VERIFIED_ABSENT': 1} |
| duplicate_reordered | 101 | {'COMPLETED': 1} | 1 | {'ABSENT': 1} | {'VERIFIED_ABSENT': 1} |
| false_ack_cache | 101, 202 | {'COMPLETED': 2} | 2 | {'RESIDUAL': 2} | {'FALSE_SUCCESS_DETECTED': 2} |
| false_ack_search | 202, 101 | {'COMPLETED': 2} | 6 | {'RESIDUAL': 6} | {'FALSE_SUCCESS_DETECTED': 6} |
| multiple_residuals | 101 | {'COMPLETED': 1} | 1 | {'RESIDUAL': 1} | {'FALSE_SUCCESS_DETECTED': 1} |
| normal_retention | 101, 202 | {'COMPLETED': 2} | 6 | {'ABSENT': 6} | {'VERIFIED_ABSENT': 6} |
| partial_order | 101 | {'COMPLETED': 1} | 6 | {'RESIDUAL': 6} | {'FALSE_SUCCESS_DETECTED': 6} |
| pending_delivery | 101 | {'COMPLETED': 1} | 2 | {'PENDING': 1, 'ABSENT': 1} | {'PENDING_CONSISTENCY': 1, 'VERIFIED_ABSENT': 1} |
| resurrection | 101, 202 | {'COMPLETED': 2} | 6 | {'ABSENT': 4, 'RESIDUAL': 2} | {'VERIFIED_ABSENT': 4, 'FALSE_SUCCESS_DETECTED': 2} |
| verification_crash | 101 | {'COMPLETED': 1} | 1 | {'ABSENT': 1} | {'VERIFIED_ABSENT': 1} |
| verification_outage | 101, 202 | {'COMPLETED': 2} | 4 | {'UNAVAILABLE': 2, 'ABSENT': 2} | {'INCONCLUSIVE': 2, 'VERIFIED_ABSENT': 2} |

| Workload tier | Trials | Customers | Known order IDs after races |
|---|---:|---:|---:|
| small | 15 | 15 | 30 |
| medium | 5 | 15 | 64 |
| large | 1 | 6 | 48 |

The largest configured trial is six customers with eight orders each; concurrency is bounded at four. This is a larger CI fixture, not an industrial scale claim. The extended matrix provides three seeds and repeated longer-profile workloads, but remains unexecuted.

### Recovery, difficult failures and demonstration

```json
{
  "phases_succeeded": 4,
  "phases_failed": 0,
  "reappearance_cases_detected": 2,
  "false_operational_success_exposed": 18
}
```

Recorded retry attempts beyond initial attempts: 3.

False-success trials show final operational completion while direct cache/search/analytics/order observations expose residue. Allowed-retention trials preserve non-personal fact fields and exact erasure markers without treating every remaining row as a privacy failure. Temporary store outages yield uncertainty, followed by fresh verification after restoration. The crash/stale-event combination tests post-mutation process exit plus delayed older delivery and recovery through existing lifecycle barriers. The supported order/deletion race exercises real accepted or rejected writes; it does not invent an unsupported profile-update API.

Reappearance first obtains an actual absence verdict, then introduces a delayed legacy writer outside normal barriers, and performs a new verification. This models a hostile/incompatible legacy writer; it does not claim the normal tombstone fence was defeated. Its recovered phase follows explicit scoped harness cleanup, not automatic production remediation. The ambiguous-reply case deliberately mutates Redis and reports connector failure, allowing operational alarms despite actual absence. Missing-capability scope is reported as unsupported, never a successful negative. These are observed behaviors; the per-scenario table and raw phases provide exact outcomes.

### Statistics and interpretation

The aggregate includes explicit denominators, Wilson intervals, paired discordant-binomial comparisons, trial-level clustered bootstrap differences, per-scenario/workload strata and latency distributions. The bootstrap resamples whole physical trials with a fixed seed, preserving within-trial correlation; its equally weighted trial estimand differs from pooled customer/phase rates. Small selected scenario sets, correlated phases and few seed repeats limit inference. A zero observed false-positive count does not establish zero population risk.

```json
[
  {
    "first": "api_ack",
    "second": "workflow",
    "clusters": 21,
    "mean_difference": 0,
    "bootstrap_95": [
      0,
      0
    ],
    "resamples": 2000,
    "seed": "phase4-bootstrap-v1:api_ack:workflow",
    "estimand": "equally weighted physical-trial mean correctness difference on jointly conclusive rows; correlated rows remain together",
    "warning": "fixed selected synthetic scenarios; not a production-population confidence claim"
  },
  {
    "first": "api_ack",
    "second": "eraseproof",
    "clusters": 20,
    "mean_difference": 0.43333333333333335,
    "bootstrap_95": [
      0.21666666666666667,
      0.6333333333333333
    ],
    "resamples": 2000,
    "seed": "phase4-bootstrap-v1:api_ack:eraseproof",
    "estimand": "equally weighted physical-trial mean correctness difference on jointly conclusive rows; correlated rows remain together",
    "warning": "fixed selected synthetic scenarios; not a production-population confidence claim"
  },
  {
    "first": "workflow",
    "second": "eraseproof",
    "clusters": 20,
    "mean_difference": 0.43333333333333335,
    "bootstrap_95": [
      0.21666666666666667,
      0.65
    ],
    "resamples": 2000,
    "seed": "phase4-bootstrap-v1:workflow:eraseproof",
    "estimand": "equally weighted physical-trial mean correctness difference on jointly conclusive rows; correlated rows remain together",
    "warning": "fixed selected synthetic scenarios; not a production-population confidence claim"
  }
]
```

The evidence can support a claim about these controlled fixtures and capability differences. It cannot establish general statistical superiority, a target 99.9% accuracy, a commercial competitor ranking or regulatory compliance. API/workflow equality is expected from the declared architecture. No comparable third-party product is presented as evaluated.

## C. Validation and retained unsuccessful attempts

Baseline before Phase 4: 49 local unit tests passed; 24 Docker tests deferred locally and preserved. Final local checks: Ruff format/check passed; 64 tests passed and 26 Docker tests skipped because Docker is unavailable locally. Final GitHub CI passed 64 unit tests and all 26 real Docker integration tests (90 total across separate selections), the executable Phase 3 demonstration, all 21 Phase 4 physical trials, measured-data validation, chart generation and teardown. No Docker tests were skipped in the remote integration selection. The complete workflow concluded success; its actual jobs and pass lines are retained in delivery CI JSON and test evidence. The original executable Phase 3 demo remains a prerequisite to the Phase 4 benchmark.

Initial actual run 42343185445 on 4959be5 executed all 21 physical trials: 17 completed and four failed. Both resurrection seeds, partial_order and analytics_residue encountered an action-name collision in fault journaling after mutation. All partial rows and cleanup records are retained under results/4959be5-initial, along with 32 real evidence reports. These are harness errors, not fabricated verifier false negatives. A regression test covers the exact returned admin payload. The final run repeats the same scenario/seed plan with a recorded 1,200-second ceiling to permit the previously interrupted phases. Revisions are analyzed separately, not cherry-picked into a combined success rate.

Run 42345076182 was explicitly cancelled before its benchmark step; GitHub marks that step skipped. No additional physical benchmark trials arose from that run. It was superseded when validation of downloaded measurements exposed Python 3.12/3.13 Wilson roundoff. Corrected analysis permits only relative 1e-13/absolute 1e-14 floating tolerance, while preserving exact structure/count agreement and raw journal digests. Endpoint rounding is bounded to keep the observed proportion inside its interval. Regression tests and successful regeneration of the actual initial dataset exercise these corrections.

No completed unfavorable trial is removed. Failed/time-out/interrupted counts, planned versus unexecuted slots, method abstentions and unknown-oracle clearances remain explicit. No fake measurement generator or scenario-specific answer is supplied to the evaluated verifier. The retained initial run is part of the deliverable, not hidden CI history.

## D. GitHub, artifacts and reproduction

Full tested implementation commit: `61dd8e83c8a32d480dd7dc85d1a940ee8a879e46`.

[Full runtime CI and actual benchmark](https://github.com/bhuvzzs24-spec/Eraseproof-x/actions/runs/42345268206). [Repository](https://github.com/bhuvzzs24-spec/Eraseproof-x). Final delivery commit/push status is recorded in the separate delivery manifest after the measured files are committed. No force push is used.

Curated files: raw dataset plus evidence.zip under research/phase-4/results/61dd8e8-final; initial failed attempt under results/4959be5-initial; aggregate JSON, decision CSV, Markdown, PNG/PDF quality/coverage and latency figures under generated/<revision>. All evidence references resolve, all chains were revalidated, and the original raw dataset bytes remain unchanged.

Final raw dataset SHA-256: `9c87b20c35b4ce9fdb125d511158d9f53ead1f157f394aa2be5494b683fa958b`. Configuration digest: `3da32f826cbc0d8da3c4ceda18b4c16feb4c45c4a3741b9f6e801f549f68fcb7`. Canonical digest: `e2b8f7d148ad9d08c4d3857b40a673ae9b2c4e110f818fc298fcfa89769b84f3`. Hashes detect accidental modification, not forgery by a privileged administrator.

For exact startup, opt-in, seed, single scenario, CI/extended matrix, method selection, stronger consistency, resume, export, inspection and disposable-reset commands, see research/phase-4/README.md. The Phase 5 field-level API contract is docs/research-contracts.md. Normal startup does not expose fault controls. Key reproduction commands after starting the isolated Compose overlay and loading its synthetic .env are:

```sh
ERASEPROOF_RESEARCH_FAULTS=1 python -m eraseproof.research_runner --project eraseproof-research --scenario false_ack_cache --seed 101 --tier small --output work/phase4-one
ERASEPROOF_RESEARCH_FAULTS=1 python -m eraseproof.research_runner --project eraseproof-research --matrix research/phase-4/config/ci.v1.json --output work/phase4-ci
ERASEPROOF_RESEARCH_FAULTS=1 python -m eraseproof.research_runner --project eraseproof-research --matrix research/phase-4/config/extended.v1.json --output work/phase4-extended
python -m eraseproof.research_report work/phase4-ci/dataset.json --output work/phase4-generated
python -m eraseproof.research_report research/phase-4/results/61dd8e8-final/dataset.json --output work/revalidated-final
```

The offline regeneration command can validate curated results without Docker. Real replay requires Docker and the explicit research gate. A replay is a new measured run with new service-assigned IDs and scheduling, not a bitwise reproduction of timing. Use the same source/configuration to resume an interrupted batch, not a changed revision.

## E. Remaining work and deployment limits

- Extended and sustained-load matrices, broader seed coverage, full executor-kill replay, WAN/partition behavior and production workload generalization remain unexecuted.
- Failure minimization, frontend/UI and larger-scale experiment orchestration remain deferred. Phase 5 has protected read-only contracts, not a finished frontend.
- The oracle covers known fixtures and supported data planes. Backups, arbitrary unknown copies, exports and third-party systems are not verified absent.
- PostgreSQL service boundaries share the lab infrastructure; static demo tokens, broad harness privileges and private-lab OpenSearch security are not a production identity/security design. Before deployment, harden authentication/authorization, TLS and store roles, isolate credentials/networks, review audit retention and establish an operational restore/replay policy.
- Permitted tombstones, pseudonymous control metadata and retained order facts reflect a declared experimental policy. Removing a direct identifier alone does not establish real-world anonymity or legal permission.
- CPU/memory snapshots are sparse shared-stack observations; production resource attribution needs controlled profiling. Timing on ephemeral GitHub runners is noisy.
- Evidence chains and dataset hashes are integrity checks, not hardware attestation, proof of physical erasure, protection from malicious administrators or a claim about future non-reappearance.

Wilson reference: [NIST Engineering Statistics Handbook](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm). Scientific plots use Matplotlib Agg from actual measured data.
