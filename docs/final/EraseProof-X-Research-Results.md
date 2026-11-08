# EraseProof X - research results and interpretation

Generated: 2026-11-08. All numbers in this historical section are recomputed with the current metric implementation from the retained raw Phase 4 batch, after digest and stored-summary validation. They describe that batch's source revision, not a cloud deployment or a population accuracy estimate. Current Phase 6 executions, including failed attempts, are recorded separately in `Phase-6-Validation.md`.

## Source and denominators

- Historical runtime: `61dd8e83c8a32d480dd7dc85d1a940ee8a879e46`.
- Raw source: `research/phase-4/results/61dd8e8-final/dataset.json`; evidence is retained in its adjacent ZIP.
- Initial failed batch: `research/phase-4/results/4959be5-initial/`, retained separately.
- One physical trial may contain several customers and phases. Counting 43 observations as 43 independent trials would be wrong.

The corrected batch contains **21 physical trials**, **16 scenarios**, **43 customer/phase observations**, 21 completed trials, 0 failed and 0 timed out. Ground truth is binary in 40 observations and unknown in 3. EraseProof X gives 39 conclusive predictions on known truth, with 1 known-truth abstention. It detects all 18 selected known residual cases; it does not establish that future unknown copies cannot exist.

## Internal comparisons

| Method | TP/FP/TN/FN | Precision | Recall | Known-truth conclusive coverage | Mean all-outcome seconds | Recorded data queries |
|---|---|---:|---:|---|---:|---:|
| api_ack | 0/1/21/18 | 0.00% | 0.00% | 40/40 | 0.01674 | 0 |
| workflow | 0/1/21/18 | 0.00% | 0.00% | 40/40 | 0.01674 | 0 |
| eraseproof | 18/0/21/0 | 100.00% | 100.00% | 39/40 | 5.84583 | 1252 |

The API baseline reads final request status. Completed-reported predicts absence; terminal failure is an incompleteness alarm, not direct proof of residue; nonterminal/unknown states abstain. The workflow baseline additionally checks the complete required task inventory and latest durable attempt outcomes. Neither directly probes the data stores. Their zero recorded *data-plane* queries do not imply zero control-plane/network work. These are deliberately defined internal monitors, not implementations or evaluations of commercial platforms.

For the independent verifier, a binary residual result is obtained from `RESIDUAL_DATA_DETECTED` or `FALSE_SUCCESS_DETECTED`; scoped absence maps to absent; other outcomes abstain. Precision and recall are calculated on jointly eligible binary truth and conclusive predictions. Coverage and full-positive detection yield keep the excluded denominators visible.

### Uncertainty and confidence intervals

- Precision: 18/18; descriptive Wilson 95% interval 82.41% to 100.00%.
- Recall: 18/18; descriptive Wilson 95% interval 82.41% to 100.00%.
- Conclusive known-truth coverage: 39/40 = 97.50%; interval 87.12% to 99.56%.
- False-positive count: 0. The conclusive-negative denominator is 21; do not silently count the known-negative abstention as an observed true negative.
- Unknown-oracle rows: 3; independent clearances under unknown truth: 0. The historical internal baselines each issued two such clearances.

Raw independent outcomes: `{"FALSE_SUCCESS_DETECTED": 18, "INCONCLUSIVE": 2, "PENDING_CONSISTENCY": 1, "UNSUPPORTED": 1, "VERIFIED_ABSENT": 21}`. There are two inconclusive observations, one unsupported observation and one pending observation; these are separate from the 39 jointly scorable binary decisions. A known-truth inconclusive outcome explains why 40 known cases yield 39 conclusive decisions.

### Timing and overhead

Mean all-outcome verifier latency is **5.84583 s**, median **6.91575 s**, p95 **8.00547 s**, n=43. True-residual detection timing has its own sample: n=18, mean 4.08391 s. Correct scoped-absence timing has n=21, mean 7.10305 s. These samples must not be interchanged. The p95 uses nearest rank and is descriptive for this small sample.

The verifier recorded **1,252 attempted data-plane commands**. This includes supported probe calls, not all control-plane queries, connections, network bytes, CPU or storage I/O. Crash-lost uncommitted observations are excluded. The framework detected **2 delayed reappearance cases** and exposed **18 false operational successes** in this selected batch.

The initial batch contains 21 recorded physical trials with 17 completed and 4 failed. Failures are preserved, not removed from the study. Phase 5 also retained a separately cancelled CI batch with eight records (seven complete and one running at cancellation); it is not pooled into the historical results above.

## Why verification costs time

Operational monitors can return quickly because they read control metadata. Independent absence needs actual store coverage, an eligible consistency cutoff and repeated negative observations. The default policy waits three seconds and requires two eligible spaced negative samples; the extended policy increases the observation budget. A quick contradiction can finish a run before every other target converges. Slow or inaccessible stores produce uncertainty, not a cheaper fabricated success.

Stronger observation windows can detect later reappearance but increase latency and queries. The implementation provides bounded policies rather than a universal final-deletion time. It does not optimize away negative samples, scope checks or independent observations to improve benchmark numbers.

The Phase 6 list-read optimization targets only dashboard metadata. It replaces full per-run expansion in a recent-run list with a bounded summary query. The full report API and verifier data-plane checks are unchanged. CI records paired query counts and wall times over the same actual visible metadata. Results must be quoted from that artifact rather than predicted from a query plan.

## Oracle, reproducibility and failure interpretation

The privileged fixture oracle separately reads known controlled locations; evaluated baselines do not receive its labels and verifier adapters do not consume expected scenario answers. Bracket observations can mark truth unknown when stores are unavailable or transitions are ambiguous. The oracle and verifier still share a declared synthetic specification and host/infrastructure assumptions; they are not independent organizations or an adversarial cryptographic proof.

Seeds, configuration/catalog digests, source revision, physical/logical trial identities, attempts, workload tiers, fault activation/recovery, evidence IDs, cleanup and environment observations are retained. Project leases and watchdogs guard local fault execution. No automatic failure minimizer is implemented. A compact reproducer for a selected scenario is not delta-debugging or proof that a failing schedule is minimal.

Reproduce historical analysis with:

```sh
python -m eraseproof.research_report research/phase-4/results/61dd8e8-final/dataset.json --output work/final-historical-analysis
python -m eraseproof.research_report research/phase-4/results/4959be5-initial/dataset.json --output work/final-initial-analysis
```

A new actual experiment requires the separately marked isolated lab, registered scenario and explicit fault opt-in. Never use the hosted service project as a benchmark target. Production geography, real cloud tail latency, extended/stress tiers, arbitrary datastore discovery, native backups and unseen failure-model holdouts remain unestablished unless separately executed and recorded. No formal holdout claim is made from merely choosing a different seed in an already implemented scenario.

## Research context and claims avoided

[Li and Ni's SevDel preprint](https://arxiv.org/abs/2307.04316) studies SGX/blockchain and cryptographic deletion mechanisms; its authors note technical problems in the preprint record. [Hao, Clarke and Zorzo](https://eprint.iacr.org/2014/364) study verifiable encryption/key-deletion operations under hardware assumptions. Those properties differ from observational application-store checks; their experiments were not reproduced here. [Dynamo](https://www.allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf) provides relevant availability/consistency context, not an erasure guarantee implemented by this project.

Public product documentation establishes that orchestration and privacy workflows already exist. [OneTrust's deletion API](https://developer.onetrust.com/onetrust/reference/deletedatasubjectprofileusingdelete) documents asynchronous subject deletion and retained-receipt options. This is not a head-to-head test or evidence that a vendor cannot perform independent verification. EraseProof X has no measured commercial comparison, business adoption, real-user scale, compliance certification, patent or novelty proof.

### Phase 6 final runtime regression batch

The full green runtime CI at `0e115298774c4b79ad4b7ec3aa343dd037700ae1` executed 21 physical trials across 16 scenarios, producing 43 customer/phase observations. All 21 trials completed; 0 failed and 0 timed out. The independent verifier recorded TP/FP/TN/FN = 18/0/21/0, conclusive known-truth coverage 39/40, and 3 unknown-oracle observations. Mean all-outcome latency was 6.16631 seconds, with 1276 recorded data queries.

This is a separate seeded synthetic regression batch. It is not pooled with the historical Phase 4 batch, the four preceding Phase 6 attempts, or additional browser fixtures. It is not an unseen-failure holdout or a production workload study. The exact raw dataset, evidence, generated figures, stored-digest validation and recomputed metrics are retained under `qualification/final-research` and `qualification/current-research-metrics.json`. [The validation record](Phase-6-Validation.md) links the real CI run and tests.

