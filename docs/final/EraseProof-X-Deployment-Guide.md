# EraseProof X - deployment, cost and operations guide

Generated: 2026-11-08. Tested runtime: `0e115298774c4b79ad4b7ec3aa343dd037700ae1`. Repository: https://github.com/bhuvzzs24-spec/Eraseproof-x.

**Public deployment: BLOCKED / PENDING OWNER APPROVAL. No cloud resources or public HTTPS URL have been created.** Current measured qualification and final source revision are recorded in `Phase-6-Validation.md` and the delivery manifest; a successful local or CI build is not public deployment.


## Selected proposal and alternatives

The smallest complete proposal is one always-on Linux x86 VM running the static frontend/gateway, seven APIs, durable workers and all four real infrastructure technologies (PostgreSQL, Redis, OpenSearch and RabbitMQ). Caddy terminates HTTPS; every business and datastore port stays private. Persistent named volumes hold PostgreSQL, Redis AOF, RabbitMQ, OpenSearch, gateway state and certificate state. Docker restart policies and the supplied systemd unit remove dependence on a developer terminal. This is a student-oriented single-host synthetic demonstration, with a single-host failure domain and a maintenance window for upgrades.

Current public price evidence was checked on 2026-11-08. Prices are not an account-specific checkout quote; stock, taxes, currency conversion and payment eligibility must be confirmed before ordering.

| Option | VM and resources requested | VM/month, net | IPv4/month | VM backups | Computed subtotal/month |
|---|---|---:|---:|---:|---:|
| Minimum proposal | Hetzner CX33, 4 shared vCPU, 8 GB RAM, 80 GB local disk | EUR 8.49 | EUR 0.50 | 20% = EUR 1.698 | **EUR 10.69** rounded |
| More headroom | Hetzner CX43, 8 shared vCPU, 16 GB RAM, 160 GB local disk | EUR 15.99 | EUR 0.50 | 20% = EUR 3.198 | **EUR 19.69** rounded |
| Alternative | DigitalOcean Basic, 4 vCPU, 8 GiB RAM, 160 GiB SSD | USD 48.00 | check account/location | weekly backup 20% = USD 9.60 | **USD 57.60** before additional charges |

The VM amounts come from the [June 2026 Hetzner price adjustment](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/); separate [IPv4 pricing](https://docs.hetzner.com/cloud/servers/primary-ips/overview/) and [backup billing](https://docs.hetzner.com/cloud/billing/faq/) establish the calculated additions. The DigitalOcean alternative uses its [Droplet pricing](https://www.digitalocean.com/pricing/droplets) and [backup pricing](https://docs.digitalocean.com/products/backups/details/pricing/). Domain registration, optional off-host logical-dump storage, additional snapshots/volumes, excess traffic, taxes and payment/FX fees are additional and have not been purchased or quoted here.

Provider availability is not established by public documentation. The owner must confirm an available German/Finland location, account eligibility, exact resources and final invoice currency at checkout. The 8 GB option is a minimum low-concurrency proposal; actual CI resource snapshots and hosted validation are in the validation report. The 16 GB option gives safer operating headroom. Neither is a demonstrated capacity guarantee for production traffic.

Do not select a sleeping/free frontend platform as a substitute for resident workers and persistent stores. Render documents that [free web services sleep and lack persistent disks; free PostgreSQL expires](https://render.com/docs/free). Its [persistent disks require paid services](https://render.com/docs/disks). Separating every component into managed paid services offers operational benefits but adds service minimums and is not the smallest student-budget system. No managed service prices were invented. The same-origin Python gateway can serve the React build, so Vercel hosting is optional, not required for correctness.

### Service budget and persistence

| Service group | Initial configured limit/setting | Persistent material | Public access |
|---|---|---|---|
| PostgreSQL 16 | 768 MB container, 128 MB shared buffers, 100 connections | source, outbox, requests, tasks, evidence, research ledger | none |
| Redis 7.4 | 256 MB container, 128 MB maxmemory, noeviction | AOF, fences, authenticated ACL identities | none |
| RabbitMQ 4.1 | 512 MB container, 256 MiB high watermark | durable queues and messages | none; no management UI |
| OpenSearch 3.9.0 (digest-pinned) | 1536 MB container, 512 MB heap | customers index and versioned sentinels | search-private network only |
| Python APIs/workers | bounded 160 MB containers and 128 process limit | durable work is external | private only |
| Search reader | 128 MB, fixed identifier-only read contract | no application state | private only |
| Gateway | 256 MB, non-root, read-only root filesystem | persistent session/quota/audit volume | Caddy only |
| Caddy | 128 MB, minimal capabilities | certificates and CA state | 80/443 only after approval |

The hosted stack uses OpenSearch 3.9.0 pinned by image digest after the earlier 2.19.7 image failed the critical-vulnerability gate. This hosted qualification starts fresh synthetic volumes. It does not establish an in-place major-version migration for existing research volumes. The original local research stack remains separate; do not attach its older search volume to the hosted image.

These are configured limits, not measured steady-state requirements. Container limits do not reserve RAM; the host also needs memory, filesystem cache and monitoring. Watch actual peaks, free disk, queue backlog and OpenSearch heap. There is no autoscaler or automatic spend increase. Provider usage alerts are not hard spending caps. Stopping a Hetzner VM does not stop its billing; deleting the VM and any separately billed IP/storage requires a deliberate owner action.

## Approval checklist - not performed

Before any paid creation or public publication, the repository owner must approve the selected plan, region, cost ceiling, owned hostname, public read-only policy, backup scope and known security findings. The supplied `approval.example.json` deliberately has both authorization flags false. Existing account login or saved payment information does not replace that approval. No production GitHub environment or deployment variables existed at the Phase 6 audit.

Creating the VM, entering payment details, assigning DNS, opening public listeners and issuing a public certificate are pending. There is no current public URL and no verified cloud uptime. Only local/CI HTTPS with a local certificate has been prepared for testing.

## First deployment after explicit authorization

Prerequisites: approved Linux VM, Docker Engine/Compose >=2.24.4, Python 3.12+, git, SSH key authentication, enough disk/RAM, owned DNS and kernel `vm.max_map_count=262144` and `vm.overcommit_memory=1`. Keep SSH restricted to owner/trusted deployment access. Do not expose 5432, 6379, 5672, 9200 or 8000-8010. Use the provider firewall as well as host rules; Docker-published ports need deliberate review.

1. Clone the approved, CI-green commit on the approved VM. Do not start the local/research Compose files.
2. Create a private operations virtualenv and install the project with the committed constraints. Use the exact runtime revision recorded in the validation report.
3. Generate `/etc/eraseproof/hosted.env` on that host, without printing it:

```sh
sudo /path/to/ops-venv/bin/python scripts/configure_hosted.py \
  --domain YOUR_OWNED_HOSTNAME --email YOUR_ACME_CONTACT --directory /etc/eraseproof
sudo /path/to/ops-venv/bin/python scripts/manage_hosted_user.py \
  --file /etc/eraseproof/users.json --username owner --role operator
sudo chown 10001:10001 /etc/eraseproof/users.json
sudo chmod 0400 /etc/eraseproof/users.json
sudo chmod 0700 /etc/eraseproof
sudo chmod 0600 /etc/eraseproof/hosted.env
```

The password command prompts twice; do not put passwords in argv, shell history, GitHub issues or logs. Keep a separate owner record of the generated configuration and recovery material. The account file must be readable by container UID 10001 through its read-only file bind. Rotating the file must preserve those ownership/mode settings. Configure `DASHBOARD_PUBLIC_DEMO=1` only if read-only public access was approved.

4. Copy the approval example to `/etc/eraseproof/approval.json`, owned root and mode 0600. Only after actual owner consent record the true approval flags, exact `https://hostname`, provider/region, monthly ceiling and approval date. This is a process gate, not an API-enforced provider spending cap.
5. Install the audited `deploy/release.sh` as `/usr/local/sbin/eraseproof-release`, root-owned mode 0750. Restrict the deployment SSH account to this fixed command/sudo capability; never grant a public web container Docker access.
6. Point the owned hostname to the approved address and allow only approved public 80/443. Run the release command with the approved exact 40-character main commit. It checks the host approval, builds pinned images, preserves a pre-migration PostgreSQL dump, runs owner-only migrations/provisioning and starts the approved profile.
7. Install `deploy/eraseproof.service` and enable Docker/systemd startup. The start command rechecks the approval and uses existing images. Containers and volumes live on the server; Codex and the Mac are not runtime dependencies.
8. Qualify the actual public URL: verify a publicly trusted certificate, authentication, protected direct routes, real database-backed views, deletion/verification with authorized synthetic fixtures, exports, restarts and persistence. Shut down the developer Mac or test from another machine. Record this separately from CI results. Do not declare success based only on service status.

[Caddy's HTTPS documentation](https://caddyserver.com/docs/quick-starts/reverse-proxy) describes its certificate behavior; real issuance still requires correct DNS and reachable approved ports. Caddy uses TLS only at the public boundary here; same-host private container traffic is not end-to-end encrypted.

## Controlled CI/CD

The normal CI preserves all Phase 1-5 regression, Docker, benchmark and browser checks. Phase 6 adds dependency/source/container inventories and a separate real hosted-stack job. It tests local CA validation, private port configuration, per-account and guest boundaries, native stores, backup/restore, reconnection and hosted browser journeys. Images are pinned by registry digest in `deploy/images.lock.json`. Refreshing pins requires another actual scan and qualification, not blind `latest` deployment.

`approved-hosted-release` is prepared but no remote release has been performed. It requires an exact main revision with successful CI and a `production` GitHub environment requiring repository-owner review. SSH secrets are environment-scoped, host keys are pinned, and the remote command checks a separate host approval record. No environment or secrets have been created automatically.

For later approved updates, the owner can dispatch this workflow with the tested SHA without reopening Codex. Automatic release attempts after successful main CI require the separately enabled `AUTO_DEPLOY_AUTHORIZED=true` variable and still pass the protected environment and host gates. Leave the variable unset until that ongoing publication authorization is explicitly granted. Network access for a trusted GitHub runner/SSH path must also be configured and tested; that remote path is currently unverified.

## Operational runbook

### Startup and shutdown

Use `scripts/hosted_ops.py validate` to validate the resolved private configuration without printing credentials. `up-private` starts no public proxy. `publish` requires the separate owner approval record. `--existing-images` avoids rebuilding during service startup. Shut down with Compose `stop` to preserve data. Never use `down -v` on an approved persistent deployment as routine shutdown. That command is confined to disposable CI projects.

### Migrations and upgrades

`eraseproof.db.migrate()` holds a PostgreSQL transaction advisory lock and records each numbered migration once. The host release also uses a host lock and pauses business services during an upgrade. Migration/provisioning containers receive owner credentials; resident services do not. Take and verify a backup before a schema-changing release. There is no general down-migration mechanism. Do not run competing ad-hoc migrations from API replicas.

### PostgreSQL backup and recovery

```sh
python scripts/hosted_ops.py backup --env-file /etc/eraseproof/hosted.env \
  --backup /var/backups/eraseproof/approved-time.dump --output /private/path/backup-metadata.json
python scripts/hosted_ops.py restore-test --env-file /etc/eraseproof/hosted.env \
  --backup /var/backups/eraseproof/approved-time.dump
```

Dumps are created exclusively with mode 0600 and a checked PostgreSQL custom-dump header. The restore test creates a new randomly named scratch database, restores the dump, verifies all four migrations and optionally a known synthetic customer, then removes the scratch database. It never overwrites the active database. CI uses an actual backed-up fixture, not an empty schema-only demonstration.

Copy encrypted dumps to separately approved off-host storage and test retrieval. A same-disk dump alone is not disaster recovery. VM backups are useful but do not establish an application-consistent cross-store checkpoint. Redis AOF, RabbitMQ and OpenSearch volume restoration and exact cross-store recovery procedures require coordinated maintenance, reconciliation and separately recorded recovery exercises. Do not restore one store and assume a consistent whole-system state.

Restoring old data can resurrect a deleted profile. Preserve/reapply appropriate deletion fences and reconcile restored copies before reopening access. **The platform does not verify deletion from backups, snapshots or physical media.** Do not advertise backup erasure because a logical online probe returned absent.

### Failure recovery and queue investigation

Check `/health/live` and gateway readiness separately from authenticated `/api/health`. Seven ready APIs do not prove each worker is making progress. Inspect container health/heartbeats, request/task states, attempt leases, outbox age, queue ready/unacknowledged counts and dead letters. PostgreSQL leases recover stalled attempts; RabbitMQ redelivery and idempotent handlers tolerate repeated messages. Redis recreates verifier ACL identity on restart. Do not manually mark failed tasks successful or remove permanent tombstones to unblock a queue.

Use bounded Compose logs. Structured business logs omit payloads and raw exception messages. Inspect private operator audit data only with authorized host access; rotate/retain it according to the demonstration policy. Do not export sessions or private environment files in support bundles.

### Rotation, evidence retention, rollback and reset

Account password/role changes invalidate that account's sessions on the next request. For service secret rotation, provision new credentials consistently across the owner configuration, consumers and probe identities during maintenance and verify fresh work before removing old credentials. Do not change a password in only one URL.

Retain sanitized evidence with its policy, observations and digests. UUIDs and digests are linkable metadata, not legal anonymization. Tombstones must not be pruned blindly: they are part of the anti-resurrection protocol. A synthetic reset should create a new explicitly named project/volume set; deleting old volumes is a destructive owner action, not an anonymous UI feature.

Rollback only to a reviewed schema-compatible Phase 6 release. Retained release directories and Git SHA identify code, but old application code may not understand a new schema or hosted identity configuration. Restoring an active database is an explicit maintenance/destructive action requiring owner authorization; the supplied recovery test only restores a scratch database.

Set cost alerts, disk-space and memory alarms, backup-age alerts and expiry checks. Provider alerts do not stop overage billing. Remove separately billed addresses/volumes intentionally if retiring the deployment. No reliability/SLA, automatic failover, multi-region recovery or real-customer-data readiness is claimed.
