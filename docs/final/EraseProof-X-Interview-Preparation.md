# EraseProof X - interview preparation

Generated: 2026-11-08. Answers describe the actual implementation and verified historical data; consult Phase-6-Validation.md for final current CI/deployment status.

## 1. What problem does the project solve?

It checks whether supported online stores agree with a deletion claim. A completed worker task is operational evidence; direct independent observations can reveal a residual copy.

## 2. Why not trust HTTP 200 or 202?

It proves only the documented local acceptance/commit boundary. The outbox, broker, projection worker and remote store can still lag or fail. 202 is explicitly queued work, not completed verification.

## 3. What is a transactional outbox?

A source transaction writes the business row and an event record together. A separate publisher sends committed records. This removes the database-commit versus message-publication dual-write gap, but delivery can repeat.

## 4. Why is delivery not exactly once?

A publisher or consumer can crash around confirmation/acknowledgment. Stable IDs, receipts, durable leases and idempotent store effects make retries safe; the project does not claim universal exactly-once execution.

## 5. How are duplicate events handled?

A consumer/event receipt key, advisory lock and idempotent target effect prevent repeated logical application. An external effect can occur before receipt commit, so the effect itself must tolerate retry.

## 6. Why keep tombstones?

A permanent subject barrier tells supported late writers not to recreate deleted projections. Removing the profile without a durable fence would allow a stale create event to resurrect it.

## 7. What happens if Redis writes arrive after a timeout?

The Redis Lua boundary checks an erasure marker atomically. A PostgreSQL lock alone cannot stop an already in-flight remote operation; the store-local fence matters.

## 8. Why retain an OpenSearch document?

An exact erased=true sentinel at external version 2 prevents a delayed version-1 create from replacing it. Physical document deletion alone can leave only temporary engine tombstones. The retained UUID is an explicit policy exclusion.

## 9. Why is the database shared?

It makes a student-sized system reproducible and provides a common coordination lock. It is a tradeoff: schemas are not independent database or service compromise boundaries.

## 10. Which six adapters exist?

Customer profile, order linkage/extra fields, Redis profile/derived keys, OpenSearch linked documents, analytics payloads and source event history. Four of those logical targets use PostgreSQL.

## 11. Does the verifier trust task success?

No. It reads supported stores. Task/request state helps establish consistency timing and determine whether a residual contradicts a completion claim; it is not absence evidence.

## 12. Why require repeated negatives?

A single negative may be observed before a delayed projection or refresh becomes visible. Eligible samples after the cutoff reduce that risk within a finite scope and budget; they do not prove permanent absence.

## 13. What is inconclusive?

A conclusion cannot be justified because of errors, deadlines or incomplete observations. It must not be merged with verified absence.

## 14. When is false success reported?

Eligible residual data is independently observed while the deletion request claims completion. Other targets may still be pending; one real contradiction is sufficient.

## 15. How is evidence protected?

Sanitized canonical records carry policy/adapter versions and predecessor/digest linkage. Integrity checks can detect certain modifications relative to the retained chain, not malicious administrator rewriting or physical erasure.

## 16. What is the ground-truth oracle?

A separate privileged fixture reader for controlled known locations. It brackets observations and can mark truth unknown. It does not hand labels to the evaluated methods, but it shares the synthetic specification and infrastructure.

## 17. What are the baseline methods?

An API-status monitor and a stricter workflow/attempt monitor. They issue no data-plane probes and are internal architectural baselines, not commercial privacy products.

## 18. What is the strongest measured result?

In the corrected historical batch: 21 trials, 43 customer/phase observations and 18 true-positive residual findings with 0 false positives among conclusive known-truth predictions. Coverage was 39/40. Always include scope and small-sample limits.

## 19. Why not simply say 100% accurate?

There are abstentions, unknown truth, selected scenarios and correlated phases/customers. Perfect observed precision/recall on a small conditional subset is not population accuracy or a guarantee.

## 20. How are confidence intervals computed?

The implementation uses Wilson intervals on explicit binomial proportions. The historical recall interval is much wider than the point estimate suggests, and correlated observations further limit interpretation.

## 21. What do 1,252 queries measure?

Recorded attempted verifier data-plane commands in the historical batch. They exclude many control-plane operations and do not measure total network cost, CPU, I/O or cloud billing.

## 22. Which performance optimization was added?

A recent-verification list now fetches only the summary metadata it renders rather than expanding every run and target. Full reports and store probes remain unchanged; quote actual paired CI measurements for the improvement.

## 23. How are roles enforced?

The gateway validates an opaque server-side session, current account role/version, exact Origin and CSRF on mutations. Source writes also require a private operator credential in hosted mode.

## 24. Can public users run a fault?

No. Public sessions are read-only, hosted startup forbids fault switches and hosted launch is denied even to a research account. New faults run only in a separately marked, explicitly authorized local lab.

## 25. Why is the frontend not Next.js?

The project already had Python services and a local research executor. React/Vite produces static assets served by the same-origin Python gateway, avoiding an unnecessary Node runtime while preserving typed client behavior and real workflows.

## 26. What happens on worker restart?

Durable SQL state, leases, broker redelivery, explicit acknowledgments and idempotent effects allow recovery. Actual restart tests are required; heartbeat liveness alone does not prove work progressed.

## 27. What did the Redis recovery change fix?

The read ACL had originally been provisioned into a running server. Hosted startup now regenerates the authenticated default and read-only identities from private configuration, so restart does not silently lose verifier access.

## 28. Can backups resurrect data?

Yes. An old backup can contain a deleted profile. The project tests a PostgreSQL restore into a scratch database but does not verify deletion from backups or cross-store disaster consistency.

## 29. Is the project deployed?

Only say yes if the validation record contains an owner-approved actual public HTTPS URL and independent remote workflow tests. At this Phase 6 preparation stage publication is pending approval.

## 30. Is it ready for real customer data?

No such claim is justified. It is a working synthetic research application with explicit remaining identity, isolation, retention, backup, operational and security-review requirements.

## 31. What would you change at larger scale?

Start from measured bottlenecks: bounded worker concurrency/fairness, connection management, per-service credentials, a shared session/rate service, stronger identity, workload qualification and independently managed data services. Do not remove correctness checks for speed.

## 32. What is your research contribution?

An inspectable experimental implementation that contrasts operational completion with scoped independent observations, preserves uncertainty and failure evidence, and compares explicit internal baselines on controlled real stores. It is not a claim to have invented deletion verification.