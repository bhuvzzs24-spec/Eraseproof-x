# EraseProof X - user and demonstration guide

Generated: 2026-11-08. Tested runtime: `0e115298774c4b79ad4b7ec3aa343dd037700ae1`. Repository: https://github.com/bhuvzzs24-spec/Eraseproof-x.

**Public deployment: BLOCKED / PENDING OWNER APPROVAL. No cloud resources or public HTTPS URL have been created.** Current measured qualification and final source revision are recorded in `Phase-6-Validation.md` and the delivery manifest; a successful local or CI build is not public deployment.


## What an answer means

A deletion task can finish while a copy remains. The interface separates the deletion system's claim from independent store observations. `Completed reported` is blue operational metadata. `Verified absent - scoped` is a statement about the declared stores and observation time, not universal or permanent erasure. Pending, inconclusive and unsupported are not successful absence.

## Access

The trusted local lab uses the role passwords generated in `.dashboard.env`. The hosted package uses an individual username, account password and server-enforced role. Choosing a role does not grant it: the account record must match. A public read-only entry button appears only when the owner deliberately enables it. It creates an expiring read-only session, not an operator account. Privileged keys never enter browser storage; only the color theme is saved locally.

| Role | Available actions |
|---|---|
| Read-only/public demo | inspect authorized live synthetic state, architecture, historical results and sanitized reports |
| Operator | create synthetic fixtures/orders, request deletion, bounded retries, independent verification and exports |
| Research administrator | operator actions and isolated local-lab research when explicitly enabled; hosted faults are always disabled |

No production customer information belongs in this application. Source names must begin with `Synthetic ` and emails must use `example.invalid`. Random IDs are still pseudonymous identifiers, not proof of anonymity.

## Nine workspaces

1. **Command center:** actual live source counts, operational states, verification outcomes, findings, readiness and recent activity. A dash means unavailable/unobserved, not zero. Counts of requests and runs are different denominators and must not be read as a single success rate.
2. **Data topology:** select declared components to inspect role, categories, adapters and assumptions. Lines are architecture metadata, not live trace traffic. Some components have no separate live probe.
3. **Customer data explorer:** create an authorized synthetic fixture, inspect actual propagation and known order/metadata footprints, optionally add an order, then explicitly confirm deletion. A cleared link alone is not proof that every personal field was removed.
4. **Deletion operations:** filter requests, inspect six tasks, failures, durable attempts and the audit timeline. Retry only eligible failed tasks within the server budget. Tombstone admission cannot be undone as a harmless UI cancellation.
5. **Verification lab:** choose a request and default or extended consistency policy, start a real asynchronous run, follow target outcomes, inspect the captured scope and rerun with a new request key if appropriate.
6. **Failure investigator:** compare what orchestration reported against independent observations. A residual can terminate a run while other targets remain pending; that is a valid contradiction, not six verified negatives.
7. **Fault injection studio:** read registered scenarios and expected protocol labels. In an approved isolated local lab, confirm and execute the actual bounded runner. Hosted/public execution is denied even for a research account.
8. **Research benchmarks:** choose a labeled historical batch, actual live experiment or authorized local job. Inspect internal baselines, confusion matrices, intervals, coverage, sample sizes, timing, query counts, trials and reproduction metadata.
9. **Evidence explorer:** choose a run, filter target/outcome/digest or observation text, expand details and download JSON. Policy/adapter versions, time, scope completeness and evidence linkage matter as much as the outcome badge.

## Normal workflow

Inspect topology and actual readiness. Create a synthetic customer and wait for real cache/search/analytics propagation. Add an order if demonstrating retention. Request deletion and watch it converge to its actual reported state. Start verification; an HTTP 202 means accepted/queued, not completed. Wait for the finished outcome. Inspect all six supported target results and exclusions. Export the sanitized report and retain its run/policy IDs. A successful source deletion response alone is not the final answer.

If the connection fails during a write, do not repeatedly click create/delete. Refresh actual state first. Customer creation has no cross-request idempotency key; repeated requests can create different synthetic customers. Deletion and verification use server idempotency semantics. Mutation retries are not automatic.

## False-success demonstration

Use the saved actual `false_ack_cache` or `false_ack_search` case for public explanation. Show `COMPLETED_REPORTED` beside `FALSE_SUCCESS_DETECTED`, then open the real sanitized residual finding and fault timeline. Explain that the baseline trusts operational metadata while independent adapters read the stores.

To execute a new fault, use a separate explicitly marked local research project, not the hosted stack. The runner creates its own fixtures, applies the registered real fault, runs deletion/verification, saves results and restores/cleans fixtures. Saved evidence is a pre-cleanup observation. A new live check after cleanup can legitimately differ; never rewrite the saved report to hide that distinction.

## Reading uncertainty and limits

- Pending consistency: the required cutoff or repeated negative observations have not yet been satisfied.
- Inconclusive: errors, time/round budgets or incomplete observations prevent a conclusion. It is not absence.
- Unsupported: an adapter/scope is unavailable under the selected policy. It is not a healthy target.
- Residual detected: eligible data was observed in scope. If orchestration claimed completion, the contradiction is classified as false success.
- Verified absent: all required supported targets meet the captured policy in that run. Backups, unknown stores and future administrative writes remain outside the claim.

Live lists are bounded; run pickers show at most 100 recent records. Direct links retain an explicit linked-run option while the list loads or when the run is outside the page. Research job-source labels can lag by one five-second poll. Narrow tables scroll internally; use the light/dark toggle, keyboard focus and reduced-motion settings as needed. Sign out on shared machines.

## Demonstration walkthrough for an interview

Open the topology and explain outbox delivery. Create one synthetic profile and show propagation. Delete it, deliberately pause at `Completed reported`, and explain why this is only a claim. Run independent verification and explain grace/repeated observations. Open a saved actual false-success case and compare the two panels. Filter and export evidence. End with one limitation: this checks declared online logical scope, not backups or physical erasure. Do not claim an online URL or public cloud execution unless the deployment validation report actually records one.
