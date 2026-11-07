# Phase 5 read-only research contracts

Base URL: `http://localhost:8006/v1/research`. All routes require `X-Research-Token` and APP_ENV=demo; a missing/short token disables access with 403. The research token is separate from deletion, inspection and verification credentials. Only GET routes exist. Fault activation remains a gated local CLI operation.

| GET path | Response |
|---|---|
| `/scenarios` | `{version: string, items: Scenario[]}` from the versioned registry |
| `/experiments?limit=20&offset=0` | `{items: Experiment[]}` ordered by created_at descending then ID |
| `/experiments/{uuid}` | One Experiment, or 404 |
| `/experiments/{uuid}/trials?limit=20&offset=0` | `{items: [{body: Trial}]}` in logical_key/attempt order |
| `/experiments/{uuid}/summary` | Recomputed Summary, capped at 1,000 physical trials; 413 for larger exports |

List bounds: limit 1–100; offset 0–10,000. An empty trial or summary collection does not establish that an experiment exists; load its detail route for 404 handling. APIs read committed PostgreSQL research metadata and are not streaming progress feeds. Major trial transitions are mirrored; the local durable dataset is the most detailed execution journal.

An Experiment contains UUID id, state (RUNNING/COMPLETED/FAILED/INTERRUPTED), code_commit, configuration, configuration_digest, environment, created_at and nullable finished_at. Configuration holds matrix version, explicit entries/seeds/repeats/consistency profiles, workload tiers, maximum_seconds, concurrency and selected_methods. Environment records Python/platform/Docker/store versions. Never display credentials or add a fault-start button to these endpoints.

A Trial body contains id, experiment_id, logical_key, attempt, scenario_id, recorded scenario configuration, seed, tier, workload, consistency_profile, status, started_at_unix, finished_at_unix and elapsed_seconds. Status is RUNNING/COMPLETED/FAILED/TIMED_OUT/INTERRUPTED. Its fixtures contain opaque synthetic customer/order IDs, not personal fields. `faults[]` is a timestamped timeline of INTENDED/ACTIVATED/OBSERVED/RESTORED controls with bounded details. `cleanup` records restoration errors explicitly. Errors contain safe codes and, on corrected revisions, code frame locations without local variables or exception text.

Each `phases[]` row links phase, customer_id, deletion_request_id, verification_id, operational_state, oracle_before, oracle_after, oracle, methods, observed_at_unix and evidence_file. Baseline-only selections omit verification_id/evidence_file. Oracle has state ABSENT/RESIDUAL/PENDING/UNAVAILABLE/UNSUPPORTED, per-store observations, and a declared independent basis. Each target reports eligible_records, permitted_records or a safe error_class. The oracle never reads the verifier verdict.

`methods` is keyed by selected api_ack/workflow/eraseproof. Predictions are ABSENT/RESIDUAL/ABSTAIN; outcome retains the original operational or verifier outcome. Method objects include elapsed_seconds and data_queries. EraseProof additionally exposes targets, evidence_digests, probe_duration_ms and false_success. The baseline basis explicitly states that an operational alarm is not direct residue evidence.

Summary contains physical/completed/failed/timed_out/interrupted counts, decision_rows, scenario IDs, methods, paired comparisons, recovery, deletion_latency_seconds and retry_attempts. Each method has TP/FP/TN/FN; binary_oracle_rows, scored_rows, positive_abstentions, abstained_on_binary_rows, oracle_unknown_rows and clearance_with_unknown_oracle; explicit `{numerator, denominator, value, wilson_95}` proportion objects; outcome counts; timing distributions `{n,mean,median,p95,stdev_population}`; recorded_data_queries; storage_category_outcomes. Undefined metrics are JSON null and must render as undefined, never zero or success.

The offline aggregate adds provenance, per-scenario/tier strata and cluster_comparisons. The durable dataset adds format_version, experiment.plan, planned/unexecuted counts and a canonical dataset_digest. Retain failed physical attempts and code revisions separately. Do not pool correlated customer phases as independent experimental replicates or treat an unsupported scope as a clean deletion.

Evidence references are relative artifact paths, not public download URLs. Expand a curated evidence.zip beside dataset.json for offline resolution. Live verifier reports and timelines retain the existing verification-token authorization. The frontend must not invent a file-serving route or expose an unprotected evidence endpoint. Display the scope, observation time, uncertainty and code provenance beside every verdict; an old absence result does not prove future absence.
