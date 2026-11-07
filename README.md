# EraseProof X — Phases 1–3

A synthetic distributed e-commerce lab for studying false deletion success. Phase 1 creates and propagates records. Phase 2 performs durable deletion orchestration across six configured targets. Phase 3 independently probes all six supported targets and exports scoped evidence; it does not claim universal or irreversible erasure. Operational presence observations are not deletion proofs.

## Start
Requires Docker Engine/Desktop with Compose v2, approximately 6–8 GB available RAM, and Python 3.12+ for host tests. OpenSearch uses a 512 MB Java heap; total container memory exceeds that. On Linux set `sudo sysctl -w vm.max_map_count=262144` if OpenSearch reports a bootstrap failure. On macOS allocate sufficient Docker Desktop memory.

```sh
python3 scripts/configure_demo.py
# Creates .env once with private permissions and random independent credentials.
docker compose up --build -d --wait --wait-timeout 240
python3 -m venv .venv
. .venv/bin/activate
pip install -c requirements.lock -e '.[dev]'
make seed
```

Create a profile directly (use a new email each run):
```sh
curl -sS http://localhost:8000/v1/customers -H 'Content-Type: application/json' \
  -d '{"name":"Synthetic Customer Demo","email":"demo-001@example.invalid"}'
```
The response includes `id` and `event_id`. Replace CUSTOMER_UUID below. Export the token you set in `.env`:
```sh
set -a; . ./.env; set +a
curl -sS http://localhost:8000/v1/customers/CUSTOMER_UUID
curl -sS -H "X-Inspection-Token: $INSPECTION_TOKEN" http://localhost:8000/v1/customers/CUSTOMER_UUID/propagation
curl -sS -H "X-Inspection-Token: $INSPECTION_TOKEN" http://localhost:8002/v1/inspect/customers/CUSTOMER_UUID
curl -sS -H "X-Inspection-Token: $INSPECTION_TOKEN" http://localhost:8003/v1/inspect/customers/CUSTOMER_UUID
curl -sS -H "X-Inspection-Token: $INSPECTION_TOKEN" http://localhost:8004/v1/inspect/customers/CUSTOMER_UUID
curl -sS http://localhost:8001/v1/orders -H 'Content-Type: application/json' \
  -d '{"customer_id":"CUSTOMER_UUID","amount_cents":1299,"currency":"USD"}'
```
Verify publication timestamp, three customer-event receipts, matching store data and `present` states. A 201 source response alone is insufficient. Swagger is available at `/docs` on ports 8000–8004; liveness/readiness at `/health/live` and `/health/ready`.

## Checks and migrations
```sh
make lint
make test
# Requires the real running stack; set token to match .env first:
make smoke
make migrate
python scripts/event_schema.py
```
Compose runs transactional, advisory-locked SQL migrations before services. Migration IDs are recorded; reruns are no-ops. Forward migrations only; destructive experiments use `make reset`, which **deletes all stack volumes**, followed by startup and seed. Never use the reset on real data. CI has separate unit and Docker integration jobs; integration is not equivalent to mocked testing.

## Troubleshooting
`docker compose ps` and `docker compose logs --tail 100` expose startup and worker failures. A pending outbox indicates broker/publisher failure; a published event without receipts indicates a consumer problem. Inspect dead letters through `docker compose exec rabbitmq rabbitmqctl list_queues name messages_ready messages_unacknowledged`. Repair the dependency before intentionally replaying quarantined messages; automatic DLQ replay is not implemented. Worker reconnect loops tolerate infrastructure restarts; Worker health checks detect stale process/event-loop heartbeats; they do not attest to projection progress. Use propagation receipts plus queue depth to assess processing.

OpenSearch may need tens of seconds to initialize and remain yellow with one node. Security is disabled only inside the isolated local network; infrastructure ports are not published. APIs are loopback only. Destructive APIs require a separate random token and APP_ENV=demo; production hardening is deferred. If credentials change after first startup, persisted DB/broker credentials do not automatically change: reset the synthetic volumes or rotate credentials explicitly. Readiness checks storage dependencies and migrations; source APIs can accept writes during broker outages because the outbox provides durability.

See [research](docs/research.md), [requirements](docs/requirements.md), [architecture](docs/architecture.md) and [verification report](docs/verification.md).

## Phase 2 deletion

The deletion API runs at `http://localhost:8005/docs`. Read the [Phase 2 guide](docs/phase2.md) before destructive tests. `COMPLETED_REPORTED` means all six configured workers reported success; it is not independent verification. Orders retain transaction facts with `customer_id=null`; profile data and source event history are removed; Redis/OpenSearch retain minimal erasure markers to fence delayed writes. Search inspection exposes its retained marker explicitly. Irreversible UUID tombstones reject later writes and stale projection events.

```sh
set -a; . ./.env; set +a
python scripts/deletion_demo.py
# Actual outages, retry exhaustion/recovery, stale events and crash recovery:
RUN_INTEGRATION=1 pytest tests/test_deletion_integration.py -v
```

Upgrading an existing Phase 1 `.env`: add an independent `DELETION_TOKEN` of at least 24 random characters (for example `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`). Keep existing DB and broker passwords. The configuration helper never overwrites `.env`. Drain legacy Phase 1 broker queues and resolve payload-bearing dead letters before upgrading; Phase 2 publishes identifier-only references. See the migration/transport retention limitations in the guide.

## Phase 3 independent verification

The independent API runs at `http://localhost:8006/docs` with a separate `X-Verification-Token`. See the [Phase 3 guide](docs/phase3.md), [machine-readable scope](policies/scope-v1.json), and [validation record](docs/phase3-verification.md). It directly queries actual stores using read-only PostgreSQL/Redis identities, retains append-only evidence, distinguishes pending/unknown/unsupported outcomes, and detects contradictions with reported completion. Verification never remediates while collecting evidence.

```sh
set -a; . ./.env; set +a
python scripts/verification_demo.py
ERASEPROOF_TEST_FAULTS=1 python scripts/verification_demo.py --inject-synthetic-fault
RUN_INTEGRATION=1 ERASEPROOF_TEST_FAULTS=1 pytest -m integration -v
```

Upgrade existing `.env` files with fresh VERIFICATION_TOKEN, VERIFIER_DB_PASSWORD, VERIFIER_CONTROL_PASSWORD and VERIFIER_REDIS_PASSWORD values; the helper preserves existing files. Deletion admission now captures order UUID inventory before de-identification. Historical requests without that capture are inconclusive for complete order-field coverage. OpenSearch/Redis erasure markers and operational UUID metadata are explicitly permitted and remain visible. OpenSearch server-side read-only authentication is not provided by the existing private-network lab configuration; fixed read-only probe operations and this limitation are documented.

## Phase 4 reproducible fault research

The [Phase 4 protocol](research/phase-4/README.md) defines isolated CLI-only fault injection, seeded scenario/workload matrices, an independently coded fixture oracle, faithful API/workflow baselines, retained failed trials, statistical analysis and measured plots. The ordinary stack never enables fault hooks. Use the explicitly labeled research Compose overlay and project, following the protocol's exact startup commands.

```sh
ERASEPROOF_RESEARCH_FAULTS=1 python -m eraseproof.research_runner --project eraseproof-research \
 --scenario false_ack_cache --seed 101 --output work/phase4-one
python -m eraseproof.research_report work/phase4-one/dataset.json --output work/phase4-one-report
```

Research APIs on port 8006 are read-only and require a separate RESEARCH_TOKEN. No HTTP endpoint triggers faults. The extended matrix is provided for manual execution and must be labeled unexecuted until actual result artifacts exist. These are internal architectural baselines, not commercial platform benchmarks or compliance guarantees.

The [measured Phase 4 evaluation](docs/phase-4-evaluation.md) records a successful 16-scenario, 21-trial Docker batch with 43 customer/phase observations. EraseProof X detected 18 residual cases (0 observed FP/FN); both internal baselines missed those 18 and raised one operational false alarm. The verifier retained two inconclusive, one unsupported and one pending outcome. Conclusive coverage was 39/40 known-truth cases; precision/recall Wilson intervals were 82.4–100%, not a population guarantee. Mean verifier call latency was 5.846s versus 0.017s for the metadata baselines.

[Final raw trials and evidence](research/phase-4/results/61dd8e8-final/) · [Statistics and measured charts](research/phase-4/generated/61dd8e8-final/) · [Preserved initial failed batch](research/phase-4/results/4959be5-initial/) · [Phase 5 read-only contracts](docs/research-contracts.md). The final runtime [CI run](https://github.com/bhuvzzs24-spec/Eraseproof-x/actions/runs/42345268206) passed 64 unit and 26 Docker integration tests, the existing demo and the full CI matrix. The earlier harness error and its partial measurements remain inspectable.

## Phase 5 engineering dashboard

The [dashboard guide](docs/phase5.md) covers all nine workspaces, design tokens, server-enforced observer/operator/research roles, same-origin API integration, real research controls and browser tests. A React/TypeScript static build is served by the existing Python stack through a local gateway; backend credentials never enter the browser. Historical measurements are labeled separately from live telemetry. Nothing is publicly deployed.

```sh
python scripts/configure_dashboard.py
# Load both .env and .dashboard.env on the trusted host, then use the required source-write auth overlay:
set -a; . ./.env; . ./.dashboard.env; set +a
export COMPOSE_PROJECT_NAME=eraseproof-research-dashboard
export DASHBOARD_RESEARCH_PROJECT="$COMPOSE_PROJECT_NAME"
export COMPOSE_FILE=compose.yaml:compose.research.yaml:compose.dashboard.yaml
docker compose up --build -d --wait --wait-timeout 240
npm --prefix frontend ci
npm --prefix frontend run build
DASHBOARD_ORIGIN=http://127.0.0.1:8010 python scripts/start_dashboard.py
```

Open `http://127.0.0.1:8010` and sign in with a role password from the ignored, mode-0600 `.dashboard.env`. Research execution is disabled by default; the guide documents the additional explicit host gates. For development, run the gateway with Origin `http://127.0.0.1:3000` and `npm --prefix frontend run dev`. Do not expose ordinary trusted-lab backend ports or the Docker executor publicly.

Phase 5 delivery: [implementation and setup](docs/phase5.md) · [actual validation report](docs/phase5-validation.md) · [browser screenshots](docs/phase5-visuals.md).
