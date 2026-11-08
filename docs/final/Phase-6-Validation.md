# EraseProof X — Phase 6 validation record

Generated 2026-11-08. Runtime `0e115298774c4b79ad4b7ec3aa343dd037700ae1`. [Actual CI run 42396389635](https://github.com/bhuvzzs24-spec/Eraseproof-x/actions/runs/42396389635). The final documentation/source delivery commit is recorded separately in the delivery manifest.

**Public deployment: BLOCKED / PENDING OWNER APPROVAL. No cloud resources created, no public URL verified, and no remote SSH release executed.**

## Actual tests and CI

| Check | Observed result |
|---|---|
| Backend | 89 unit tests passed locally and in CI; 29 real Docker integration tests: success |
| Frontend | 16 tests, formatting, lint, TypeScript and production build passed; six standalone Chromium checks passed |
| Real browsers | Two hosted Chromium workflows: success; nine legacy Docker-backed browser workflows: success |
| Hosted qualification | Six actual authorization/deletion/backup/restart/privilege/logout check groups passed; local CI CA verified with TLS verification enabled in the Python client |
| Security | Source/dependency/container job: success; all nine scanned images have zero CRITICAL findings |
| Full runtime CI | All jobs passed.

The Docker tests ran on GitHub Actions against real PostgreSQL, Redis, RabbitMQ and OpenSearch. Docker is unavailable on the local Mac. The hosted stack used loopback-only HTTPS with a private CI certificate, not a public CA or public cloud domain. Browser ignoreHTTPSErrors is confined to that CI origin; the separate Python qualification validates the actual local CA. No production/provider/public-HTTPS/remote-release test is claimed.

## Actual hosted checks

- anonymous cannot read protected data; explicit guest session cannot delete or inject faults.
- real customer/order propagation, deletion, six-target independent absence and sanitized export.
- real PostgreSQL custom backup restored into a separate scratch database; four migrations and expected synthetic fixture verified; scratch removed.
- API, worker, PostgreSQL, Redis, broker and gateway restart/reconnect; persisted session and fresh six-target verification passed.
- runtime database role has no superuser/role/database/DDL privilege; OpenSearch read credential cannot delete an index.
- logout revokes session server-side.

## Measured performance and resource scope

- Compose creation/readiness: 53.543 seconds; image download/build excluded.
- Mixed API client timings: n=52, median 34.231 ms, maximum 443.828 ms. Polling, authorization and mutations are mixed; this is not a throughput/load test.
- Five paired real PostgreSQL list measurements, two existing verification records: 7 legacy SQL calls versus 3 summary calls; identical visible metadata. Median 14.621 ms versus 12.301 ms (15.86% lower in this tiny sample). Verification data-plane checks were unchanged.
- One Docker snapshot across 22 running containers: approximately 1801.3 MiB total reported container memory. This is not peak memory, a reservation, host overhead, a sustained-load profile or an SLA. Individual limits/CPU readings remain in the raw JSON.

The SQLite session persisted across gateway restart. Redis probe ACLs were re-created on Redis restart. PostgreSQL/broker/API/worker restart and a fresh six-target verification passed. The PostgreSQL custom dump was restored into an isolated scratch database, checked for all four migration versions and an expected synthetic fixture, then removed. The dump itself is not published. This does not establish a consistent four-store disaster recovery point, backup erasure or recovery on another cloud host.

## Security inventory and unresolved review

| Scanned artifact | CRITICAL | HIGH | HIGH with published fix | Scope |
|---|---:|---:|---:|---|
| Application runtime | 0 | 49 | 2 | Deployed artifact |
| Gateway | 0 | 49 | 2 | Deployed artifact |
| Derived PostgreSQL | 0 | 0 | 0 | Deployed artifact |
| Redis | 0 | 0 | 0 | Deployed artifact |
| RabbitMQ | 0 | 0 | 0 | Deployed artifact |
| Caddy | 0 | 2 | 1 | Deployed artifact |
| Python base | 0 | 49 | 2 | Base inventory; findings also appear in derived images |
| Node build stage | 0 | 6 | 6 | Build stage only |
| OpenSearch 3.9.0 | 0 | 82 | 82 | Deployed artifact |

Counts are per scanner artifact/package occurrence, not unique vulnerability IDs or independent defects; the Python base and derived-image findings overlap. Every finding is retained. The gate blocks fixed CRITICAL findings; no CVE suppression/waiver was added. High-severity findings remain unresolved and require review/remediation before publication or any stronger readiness claim. Some have published fixes.

The Python application images retain 49 HIGH occurrences each, including two fixed zlib1g advisories and unfixed util-linux-family findings. Caddy retains two HIGH occurrences, one with a published fix. OpenSearch retains 82 HIGH occurrences with fixes, mainly bundled Java libraries; replacing vendor-managed JARs without vendor support/compatibility qualification was not treated as a safe production upgrade. The Node builder retains six HIGH occurrences in bundled tooling. Network isolation and restricted APIs reduce exposure but do not prove these advisories unreachable. No blanket false-positive claim is made.

The passing source scan recorded 99 Bandit findings: 92 LOW, seven MEDIUM and zero HIGH severity. Both pinned Python requirement audits and the frontend npm audit reported no known dependency vulnerabilities at scan time. These results do not cover every installed system package or undiscovered vulnerability.

### Critical-finding remediation history

- Initial pinned infrastructure scan found CVE-2025-68121 in PostgreSQL gosu, plus CVE-2025-14813/CVE-2026-8763 in the earlier OpenSearch Bouncy Castle library.
- Upgrading to the upstream gosu 1.20 binary alone did not remediate it: the binary still embedded Go 1.24.6. The final image rebuilds the checksum-verified exact upstream source commit with a digest-pinned Go builder; actual scan metadata records Go 1.26.10. PostgreSQL remains the pinned 16 engine.
- Hosted search moved to digest-pinned OpenSearch 3.9.0, with real API, deletion, independent observation and restart qualification on fresh volumes. Existing older research volumes were not upgraded in place.
- Original vulnerable scan artifacts and failed CI runs remain identifiable; unused replaced binaries are not misreported as deployed artifacts.

## Earlier attempts, retained separately

| Runtime commit | Actual CI run | Outcome and correction |
|---|---|---|
| `7312b105` | [42385834829](https://github.com/bhuvzzs24-spec/Eraseproof-x/actions/runs/42385834829) | Legacy integration passed; hosted proxy IP collision and scanner setup failure; corrected IPAM allocation/checksum helper. |
| `04a82200` | [42390197998](https://github.com/bhuvzzs24-spec/Eraseproof-x/actions/runs/42390197998) | Legacy integration passed; actual critical image findings and runtime outbox RLS denial; corrected scoped role policies and provisioning dependencies. |
| `076216da` | [42394277561](https://github.com/bhuvzzs24-spec/Eraseproof-x/actions/runs/42394277561) | Build failed because of an incorrect upstream asset filename; filename verified and corrected. No hosted success claimed. |
| `e4c64784` | [42395771877](https://github.com/bhuvzzs24-spec/Eraseproof-x/actions/runs/42395771877) | Actual hosted backend/recovery passed; browser navigation race and still-vulnerable upstream helper binary failed. Rebuilt source and awaited actual navigation. |

No research trial was cancelled to make a final success claim. Earlier dataset files are stored under qualification/attempt-* and are not pooled with the final measured dataset. Source/CI revisions and stored digests remain attached to each batch.

## Current research matrix

Validated final runtime dataset: 21 physical trials across 16 scenarios, 43 customer/phase rows, 21 complete, 0 failed, 0 timed out. Verifier TP/FP/TN/FN = 18/0/21/0; known-truth conclusive coverage 39/40; unknown oracle rows 3. Mean all-outcome latency 6.16631 seconds; recorded data queries 1276.

This is a seeded synthetic CI regression batch, not a holdout failure-generalization study or commercial comparison. Historical Phase 4 results remain separate in the research report. Raw records, recomputed metrics and generated analysis are retained under qualification/final-research.

## Deployment and remaining work

No cloud resource, DNS record, VM, storage purchase or public listener was created. No provider credentials, production GitHub environment, SSH host or public domain was configured. Source push is authorized but does not authorize publication. The supplied workflow requires explicit owner review, exact green main SHA, pinned SSH host identity and a separate host approval record. Remote release execution and the public CA/host firewall/DNS/persistence checks remain unexecuted.

Proposal: one always-on Hetzner CX33 4-vCPU/8-GB/80-GB VM, IPv4 and VM backups: estimated EUR 10.69/month net (8.49 + 0.50 + 20% of VM). CX43 16-GB headroom: EUR 19.69/month net. Taxes, exchange rates, checkout availability, domain and separately approved off-host backup storage are additional/uncertain. No purchase is authorized. See the deployment guide for official price sources, exact host setup and teardown/cost controls.

Public demonstration additionally requires owner approval of provider/plan/region, spending ceiling, owned domain and read-only public scope, review of remaining HIGH findings, actual provisioning and genuine remote HTTPS/end-to-end/restart validation. Real-customer use remains unqualified: stronger identity/service isolation, retention/backup controls, independent security review and sustained workload/recovery qualification remain future work.

## Evidence navigation

- qualification/qualification.json: machine-readable status and scan counts.
- qualification/hosted/: actual validation, backup/restore metadata and five paired performance measurements.
- qualification/security/: full nine-image vulnerability inventories, both Python audits, npm audit and all Bandit findings.
- qualification/hosted-browser-results.json and screenshots/: actual browser results/captures.
- qualification/final-research/: final raw trials, evidence and generated analysis, when completed.
- Report-Build.md: reproducible PDF/diagram build and visual QA workflow.
