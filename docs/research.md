# Research foundation

## Problem and motivation
A successful API response usually establishes a local fact, not a global invariant. An application may commit a deletion while replication trails behind, a cache still serves an older value, an index awaits refresh, or an asynchronous worker crashes before applying its command. A completion event can itself be premature or refer only to attempted work. EraseProof X is a synthetic laboratory for comparing such acknowledgments with direct observations of explicitly inventoried stores.

This is not a compliance product. It cannot establish physical erasure, discover arbitrary hidden copies, inspect backups, or prove an adversarial operator has destroyed data. Phase 1 creates data and exposes propagation; deletion and independent verification are later phases.

## Existing approaches and evidence
Reviewed 2026-11-06. These sources establish mechanisms and product capabilities, not comparative performance or novelty.

- [Ethyca Fides release documentation](https://www.ethyca.com/docs/releases/fides-2-X/2-43-1) describes orchestration of access, erasure and consent requests across connected systems. This is a relevant existing orchestration approach; we have not evaluated its residual-data detection.
- [OneTrust deletion API](https://developer.onetrust.com/onetrust/reference/deletedatasubjectprofileusingdelete) documents subject deletion and synchronization timing considerations. It does not establish that EraseProof is more capable.
- [RabbitMQ acknowledgments and confirms](https://www.rabbitmq.com/docs/confirms) separates broker acceptance of publications from consumer processing acknowledgments. Neither independently attests to all downstream data stores.
- [OpenSearch index API](https://docs.opensearch.org/latest/api-reference/document-apis/index-document/) describes refresh-dependent search visibility. Direct document lookup and search visibility are distinct observations.
- [SevDel research](https://arxiv.org/abs/2307.04316) studies verifiable cloud deletion using encryption, SGX and blockchain. Its trust assumptions differ from observational probes of ordinary application stores. We reviewed its abstract, not independently reproduced its results.
- [Deleting Secret Data with Public Verifiability](https://eprint.iacr.org/2014/364.pdf) is relevant cryptographic deletion research. Full methodology review and trust-assumption comparison remain on the research checklist; no performance claims are drawn from it here.

Practical techniques include read-after-command probes, inventory-based reconciliation, audit trails, cryptographic key destruction and trusted execution attestations. They establish different properties: an absent query result is bounded by query coverage, permissions, time and replica selection. Receipts can corroborate work but can be stale. Key destruction relies on key-copy and plaintext-copy assumptions.

## Hypothesis and evaluation protocol
H1: For inventoried online stores, repeated independent read adapters will detect a greater fraction of injected residual-data cases than trusting deletion API acknowledgments or completion events alone, under the same observation budget.

Phase 4 will compare three baselines: API acknowledgment, completion event, and direct verification. Establish ground truth through privileged fixture inspection separate from the tested verifier. Randomize failure schedules and record seeds, dependency versions, sample sizes and observation windows. Include no-fault controls; stratify worker crash, delayed queue, stale cache, index lag and network partition trials. Compare paired outcomes with confidence intervals. No results have been measured.

Metrics: residual detection recall (TP/(TP+FN)); false positive rate (FP/(FP+TN)); precision; unknown/timeout rate; detection latency p50/p95; propagation lag; duplicate side-effect count; retry/dead-letter count; throughput and probe overhead. Define unknown separately rather than interpreting inaccessible systems as absent. A future deletion deadline must be fixed before scoring; legitimate convergence inside that window is not a failure.

Checklist: review full cryptographic papers; add application-level deletion research and additional commercial primary documentation; establish retention and backup scope; publish benchmark fixtures and raw measurements; test replica-specific visibility and resurrection after delayed creation events.
