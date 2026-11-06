# EraseProof X — Phases 1–2

A synthetic distributed e-commerce lab for studying false deletion success. Phase 1 creates and propagates records. Phase 2 performs durable deletion orchestration across six configured targets. Independent verification is **not implemented**. Operational presence observations are not deletion proofs.

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
