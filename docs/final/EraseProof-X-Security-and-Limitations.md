# EraseProof X - security review and limitations

Generated: 2026-11-08. Tested runtime: `0e115298774c4b79ad4b7ec3aa343dd037700ae1`. Repository: https://github.com/bhuvzzs24-spec/Eraseproof-x.

**Public deployment: BLOCKED / PENDING OWNER APPROVAL. No cloud resources or public HTTPS URL have been created.** Current measured qualification and final source revision are recorded in `Phase-6-Validation.md` and the delivery manifest; a successful local or CI build is not public deployment.


## Threat model and implemented boundaries

The hosted package is a synthetic demonstration on an owner-controlled single Linux host. Anonymous visitors and authenticated operators are untrusted API clients. Host administrators, migration/provisioning code and the owner-managed credential file are trusted. A full host compromise can change data and evidence; the system does not solve that threat.

| Boundary | Implemented control | Qualification evidence |
|---|---|---|
| Browser identity | individual salted scrypt hashes; no shared role passwords in hosted mode | account login, invalid role, rotation/removal and session tests |
| Hosted cookies | random opaque token, hashed server record, `__Host-` name, Secure, HttpOnly, SameSite=Strict, one-hour expiry | actual cookie assertions and hosted HTTPS journey |
| Public demonstration | explicitly enabled 15-minute readonly session; no role parameter can elevate it | negative mutation/fault checks |
| Cookie mutations | exact configured Origin, CSRF token, validated body, server role check | direct unauthorized HTTP tests |
| Resource abuse | bounded body streaming, persistent minute-window quotas, bounded login hashing concurrency and guest creation | oversized chunked body and quota persistence tests |
| Service access | fixed proxy routes, private networks, no public datastore/business ports | rendered Compose validation and actual hosted stack |
| Database identity | resident non-owner DML role, separate verifier control and read-only probe roles; no runtime DDL/superuser | actual permission checks |
| Redis probe | separate key-scoped read ACL recreated on restart | fresh verification after actual Redis restart |
| Search probe | separate authenticated identifier-only reader; verifier excluded from native search network | write/admin/script rejection and actual six-target verification |
| Fault isolation | hosted startup rejects fault switches; launch denied unconditionally in hosted mode; no Docker socket in hosted containers | source/config tests and real unauthorized requests |
| Evidence privacy | sanitized typed observations, no raw profile exports, safe rendering | export assertions and actual downloaded reports |
| Release control | exact tested SHA, owner-reviewed GitHub environment, pinned SSH host keys, separate host origin/cost approval | prepared workflow and negative gate tests; remote deployment not executed |

Hosted password derivation uses random 16-byte salts and scrypt N=65536, r=8, p=2, with an explicit memory bound. At most two login hashes run concurrently. Per-account credential versions revoke sessions after account changes. Local legacy role-password login remains a trusted-lab compatibility feature and is rejected by hosted startup. This is not MFA, SSO, recovery-email identity or enterprise IAM.

Quotas use persistent SQLite minute windows, not a distributed sliding-window rate limiter. IP identity is accepted only through the pinned private proxy path; a distributed attacker can still exhaust a small demonstration host. Container limits bound damage but do not provide an availability SLA. The public guest path does not grant interactive experimentation quotas because it grants no destructive experimentation at all.

## Dependency and container review

The initial Phase 6 Python audit found 16 advisory entries, including duplicate feed aliases, over old pytest and Starlette versions. Affected packages were upgraded; the local upgraded requirements audit found no known vulnerabilities at that check. Exact tool output, unique identifiers, versions and CI container inventories are retained with validation artifacts. A clean vulnerability database result is not proof that code is vulnerability-free.

The CI source scan retains all Bandit findings and gates high-severity/high-confidence findings. Dependency audit results, npm audit, actual container scans and image digest pins are retained. The container gate rejects fixed CRITICAL findings; HIGH and unfixed findings still require explicit review before publication. Do not describe such findings as waived or remediated without the actual security artifact and owner review. Final scan counts and unresolved issues are in `Phase-6-Validation.md`.

Actual scans identified a fixed critical advisory in the stock PostgreSQL image's older Go-built gosu helper and two fixed critical advisories in the earlier OpenSearch image's Bouncy Castle library. The deployment now builds PostgreSQL from the same pinned engine base with checksum-verified upstream gosu 1.20 source rebuilt with pinned Go 1.26, and evaluates a newer digest-pinned OpenSearch image. The final deployed artifacts are scanned; the replaced stock helper is not deployed. The actual CI image scan passed with zero CRITICAL findings after source rebuilding; remaining HIGH findings are listed in the validation record. No vulnerability waiver was added. The original finding reports remain evidence.

No secret values are printed by configuration/account tools. Host files must remain private and excluded from Git/build contexts. Diagnostic text artifacts are redacted against actual ephemeral test credentials without changing test outcomes. Browser traces are disabled. Screenshots remain actual browser captures, not constructed evidence.

## Residual risks

- The single host and shared PostgreSQL instance are failure/administrative trust domains. Business components share a non-owner runtime role; this is not complete per-service or tenant isolation.
- The OpenSearch security plugin is disabled inside a dedicated private writer network. The verifier uses a separate restricted reader boundary. This is safer than a shared unauthenticated search network, but it is not native OpenSearch multi-tenant authorization. A compromised authorized writer or host administrator remains powerful.
- Private same-host links do not use independent per-service TLS certificates. Public TLS, SSH authentication, firewall rules and DNS must be verified on the actual approved host before publication.
- SQLite session/quota/audit storage targets one host and one gateway deployment. There is no cross-region session replication, MFA, self-service account recovery, tenant isolation or complete user-attributed business audit chain. Gateway audit identifies the authenticated account; existing business records retain their historical demo actor labels.
- Secrets are injected from private host configuration into restricted containers, not a fully managed cloud KMS. Image/environment inspection by an authorized Docker/host administrator can expose them. Docker access must remain privileged.
- Backups can contain old synthetic profiles and linkable identifiers. PostgreSQL backup restoration is tested only to an isolated scratch database. Entire cross-store disaster recovery, deletion from backups and physical erasure are not established.
- Permanent tombstones, manifest UUIDs, receipt/audit metadata and exact Redis/OpenSearch erasure sentinels are intentionally retained. These are policy exclusions, not claims that every byte or identifier was removed or that retained facts are legally anonymous.
- Bounded scans/searches can return inconclusive when coverage, limits, permissions or deadlines are insufficient. A query result cannot discover arbitrary unknown copies or establish future absence.
- Historical selected synthetic experiments are not real-world accuracy estimates, a formal proof, a commercial product comparison, a compliance certification or evidence of customer adoption.

## Publication and real-data decision

Public deployment is pending owner approval, actual available infrastructure, a domain, final scan review and genuine remote HTTPS/workflow validation. No cloud resource has been created, no bill incurred by provisioning and no public endpoint verified in this phase. Source push is not publication authorization.

This is a complete research-oriented working application within its supported lab/synthetic scope. It must not be labeled ready for production use with real customer data. That requires independent security and operational review, stronger identities and service separation, audited retention/restore procedures, ongoing vulnerability remediation and workload qualification beyond the tests recorded here.
