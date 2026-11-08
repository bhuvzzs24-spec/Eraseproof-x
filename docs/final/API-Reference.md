# EraseProof X - generated API reference

Generated from current source decorators on 2026-11-08. Conditional business routes are activated by the SERVICE setting; not every route is present in every API process. This reference does not imply public exposure.

| Source module | Method | Path | Handler |
|---|---|---|---|
| `api.py` | GET | `/health/live` | `live` |
| `api.py` | GET | `/health/ready` | `ready` |
| `api.py` | POST | `/v1/customers` | `create_customer` |
| `api.py` | GET | `/v1/customers/{customer_id}` | `get_customer` |
| `api.py` | GET | `/v1/customers/{customer_id}/propagation` | `propagation` |
| `api.py` | POST | `/v1/orders` | `create_order` |
| `api.py` | GET | `/v1/orders/{order_id}` | `get_order` |
| `api.py` | GET | `/v1/inspect/customers/{customer_id}` | `inspect_customer` |
| `dashboard_backend.py` | GET | `/v1/dashboard/snapshot` | `snapshot` |
| `dashboard_backend.py` | GET | `/v1/dashboard/customers` | `customers` |
| `dashboard_backend.py` | GET | `/v1/dashboard/verifications` | `runs` |
| `dashboard_backend.py` | GET | `/v1/dashboard/deletions` | `deletions` |
| `dashboard_backend.py` | GET | `/v1/dashboard/customers/{customer_id}/footprint` | `footprint` |
| `deletion_api.py` | POST | `/v1/deletions` | `create` |
| `deletion_api.py` | GET | `/v1/deletions` | `listing` |
| `deletion_api.py` | GET | `/v1/deletions/metrics` | `metrics` |
| `deletion_api.py` | GET | `/v1/deletions/{request_id}` | `status` |
| `deletion_api.py` | GET | `/v1/deletions/{request_id}/events` | `events` |
| `deletion_api.py` | POST | `/v1/deletions/{request_id}/retry` | `retry` |
| `verification_api.py` | POST | `/v1/deletions/{request_id}/verifications` | `start` |
| `verification_api.py` | GET | `/v1/deletions/{request_id}/verifications` | `history` |
| `verification_api.py` | GET | `/v1/verifications/{run_id}` | `status` |
| `verification_api.py` | GET | `/v1/verifications/{run_id}/evidence` | `evidence` |
| `verification_api.py` | GET | `/v1/verifications/{run_id}/report` | `report` |
| `verification_api.py` | GET | `/v1/verifications/{run_id}/timeline` | `timeline` |
| `research_api.py` | GET | `/v1/research/scenarios` | `scenarios` |
| `research_api.py` | GET | `/v1/research/experiments` | `experiments` |
| `research_api.py` | GET | `/v1/research/experiments/{experiment_id}` | `experiment` |
| `research_api.py` | GET | `/v1/research/experiments/{experiment_id}/trials` | `trials` |
| `research_api.py` | GET | `/v1/research/experiments/{experiment_id}/summary` | `summary` |
| `dashboard_gateway.py` | POST | `/api/session` | `login` |
| `dashboard_gateway.py` | GET | `/api/access` | `access` |
| `dashboard_gateway.py` | POST | `/api/session/guest` | `guest` |
| `dashboard_gateway.py` | GET | `/health/live` | `health_live` |
| `dashboard_gateway.py` | GET | `/health/ready` | `gateway_ready` |
| `dashboard_gateway.py` | GET | `/api/session` | `identity` |
| `dashboard_gateway.py` | DELETE | `/api/session` | `logout` |
| `dashboard_gateway.py` | GET | `/api/live/{service}/{path:path}` | `read_proxy` |
| `dashboard_gateway.py` | POST | `/api/live/{service}/{path:path}` | `write_proxy` |
| `dashboard_gateway.py` | GET | `/api/health` | `health` |
| `dashboard_gateway.py` | GET | `/api/policy` | `policy` |
| `dashboard_gateway.py` | GET | `/api/history` | `histories` |
| `dashboard_gateway.py` | GET | `/api/history/{key}` | `history` |
| `dashboard_gateway.py` | GET | `/api/history/{key}/evidence/{run_id}` | `historical_evidence` |
| `dashboard_gateway.py` | POST | `/api/research/jobs` | `launch` |
| `dashboard_gateway.py` | GET | `/api/research/scenarios` | `scenarios` |
| `dashboard_gateway.py` | GET | `/api/research/jobs` | `jobs` |
| `dashboard_gateway.py` | GET | `/api/research/jobs/{job_id}` | `job` |
| `dashboard_gateway.py` | GET | `/api/research/jobs/{job_id}/evidence/{run_id}` | `job_evidence` |
| `dashboard_gateway.py` | GET | `/{path:path}` | `frontend` |
| `search_reader.py` | GET | `/health/live` | `live` |
| `search_reader.py` | GET, POST, PUT, DELETE, PATCH | `/{path:path}` | `read` (only constrained GET/POST reads accepted; write methods rejected) |

Backend customer/order/projection ports remain private. Hosted source writes require the operator credential. Dashboard reads require inspection authorization; deletion, verification and research reads use their distinct service credentials. Gateway mutations require session role, exact Origin and CSRF. The search reader rejects administration and writes even though its catch-all handler receives those methods for explicit denial. Source/profile lookup and health routes are internal synthetic APIs, not public administration endpoints.
