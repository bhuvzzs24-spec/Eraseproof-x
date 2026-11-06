# Phase 1 requirements and boundaries

Historical baseline; [Phase 2 requirements and current behavior](phase2.md) extend deletion, authorization and lifecycle coordination below.

## Functional acceptance
| ID | User story | Acceptance criterion |
|---|---|---|
| F1 | As a researcher I create synthetic customers | Valid reserved-domain profile and outbox event commit together; invalid input rejected |
| F2 | I create orders linked to customers | Missing customer conflicts; positive integer cents and supported currency enforced |
| F3 | I observe asynchronous copies | Cache, search and analytics can be read separately with inspection token |
| F4 | I recover interrupted propagation | Unpublished rows persist; confirmed messages and manual acknowledgments; duplicate event effects converge |
| F5 | I inspect propagation | Outbox state, receipts and direct store responses distinguish present, absent and unknown |
| F6 | I reproduce experiments | Compose, versioned SQL migration, seed command, tests and documented reset provided |

## Nonfunctional requirements
Use UUID identities, UTC timestamps, bounded per-operation timeouts, JSON logs without payloads and correlation IDs. Outbox polling retries indefinitely with bounded per-attempt delay; failed individual publications are rescheduled after ten seconds. Consumer processing has five attempts then a durable dead-letter queue. Reconnect loops have three-second backoff. There is no exactly-once transport guarantee. Latency and throughput targets must be measured before setting numeric SLOs.

No production PII: API names must start `Synthetic ` and emails must use example.invalid. These syntactic controls do not guarantee users cannot type sensitive text. Use generated fixtures only. Public API access is local development only; this phase implements no user authentication, TLS or tenant isolation. Inspection is denied when no token is configured; Compose requires an explicit token and binds API ports to loopback. Database and broker credentials are local-only examples, never production secrets.

## Consistency and failure matrix
| Failure | Expected behavior | Observable signal |
|---|---|---|
| DB failure before commit | Neither source nor event exists | 503; transaction rollback |
| Broker unavailable | Source + outbox remain; publication resumes | pending event, attempts/error |
| Publisher dies after broker confirm before DB commit | Event can be delivered twice | stable event ID and receipts dedupe |
| Consumer dies before ack | Broker redelivers | durable receipt prevents duplicate logical effect |
| Consumer dies after external write before receipt | Write can repeat | deterministic key/document replacement |
| Target fails repeatedly | Five attempts then dead letter | queue depth and missing receipt |
| Search consumer stopped | Other stores progress; search absent | delayed state until restart |
| Inspection target unavailable | Unknown, never absent | state=unknown |

Customer and order source commits are strongly constrained within one PostgreSQL transaction. Separate schemas preserve logical ownership, but order-to-customer referential integrity deliberately couples source tables via an FK. Services never import another service's handlers. Cache/search/analytics converge asynchronously; a customer GET does not imply propagation. Receipts describe past processing and are not current-presence proof. Inspection requests are sequential and do not form a consistent distributed snapshot. Cache values have no TTL in this experiment to preserve residuals for later deletion studies. Search uses refresh=wait_for; the inspection route is a direct document GET, not a full query-coverage test.

Non-goals: deletion execution, deletion certification, fault control UI, benchmarks, frontend, arbitrary discovery, compliance/legal guarantees, production deployment, real payment processing. Event version 1 has immutable create-only profiles; updates and out-of-order version conflict resolution are deferred. API create requests lack replay keys: unique emails prevent duplicate customer identities but repeated order requests create separate orders. Clients must not blindly retry order POSTs.
