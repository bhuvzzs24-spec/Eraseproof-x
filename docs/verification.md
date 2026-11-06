# Verification record — 2026-11-06

## Implemented
Customer and order APIs; Redis cache projection; OpenSearch profile projection; analytics event projection; durable RabbitMQ routing; transactional SQL outbox; stable versioned event envelopes; consumer receipts; operational presence inspection; SQL migrations; JSON logging/correlation; liveness/readiness; local Compose infrastructure and CI.

The initially empty remote repository was inspected before writing files. Branch: main. Remote: https://github.com/bhuvzzs24-spec/Eraseproof-x. No existing commits or branches were overwritten.

## Local checks
Host Python 3.13.15. CI and Docker target Python 3.12. A workspace virtual environment stalled reading a dependency file; recreating it under /private/tmp resolved the problem.

Commands executed:
- `pip install -e '.[dev]'`: passed after fixing explicit setuptools package discovery.
- `ruff check .`: passed.
- `ruff format --check .`: passed.
- `pytest -v`: **12 passed, 2 skipped, 0 failed**. One upstream Starlette/AnyIO deprecation warning.
- `git diff --check`: passed.
- `docker compose version`: **blocked**, shell exit 127, `command not found: docker`.
- Event JSON Schema generated from the actual Pydantic models.
- Compose parsed with PyYAML and unit checks confirmed infrastructure ports are not published. This is not equivalent to Docker Compose validation.

Unit tests cover envelope round trips/rejections, customer API transaction intent, validation, correlation handling, inspection authorization, liveness, failed readiness, outbox confirmation/failure control flow and receipt deduplication. Unit doubles establish control flow only; they do not establish database durability or transport correctness.

The two integration tests require actual running Compose services. They cover idempotent migration reruns, source APIs, relational constraints, publication, all three projection stores, real duplicate event publication, repeat application, consumer restart and intentionally delayed search propagation. They are skipped by default; `RUN_INTEGRATION=1 pytest -m integration -v` requires Docker and a running stack. Docker integration CI is configured separately. No local real-infrastructure result is claimed.

## CI follow-up
The initial GitHub Actions run built images, applied migrations and reached healthy infrastructure/APIs, but `docker compose up --wait` rejected worker containers without health checks. Worker heartbeat checks were added rather than bypassing startup validation. The heartbeat tracks the publisher loop and consumer broker event loop; it is liveness instrumentation, not proof of useful delivery progress. CI is rerun on the fix.

## Limitations and future risks
- Local database migration execution and multi-service smoke are blocked by absent Docker/PostgreSQL. See GitHub Actions for remote execution status.
- Current observations are operational instrumentation, not independent deletion verification or atomic snapshots.
- Single-node infrastructure and shared DB credentials are local-lab tradeoffs, not highly available production infrastructure.
- APIs are development-only; no production identity, TLS, rate limiting or tenant isolation.
- Source create POST replay keys are deferred; do not blindly retry order POSTs.
- Phase 2 must address delayed-create resurrection, tombstone ordering, order retention, analytics payload deletion, outbox/receipt retention and DLQ replay policy.
- Exactly-once external effects are not claimed. Cache/search writes may repeat after a crash before receipt commit, with stable keys ensuring convergence for immutable create-only profiles.
- Crash-at-every-instruction, broker disk loss, partition matrices, malicious consumers, backup coverage and performance measurements remain future research work. Restart and delay tests are not exhaustive crash fault injection.
- Cryptographic deletion and independent verifier engines are deliberately absent.
