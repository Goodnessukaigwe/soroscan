# SoroScan API Reference

> Auto-generated from view docstrings — do **not** edit by hand.
> Re-generate with: `python manage.py generate_api_docs`

## Table of Contents

- [Analytics](#analytics)
- [Contracts](#contracts)
- [Dev](#dev)
- [General](#general)
- [Ingest](#ingest)
- [Meta](#meta)

---

## Analytics

### Return 7-day API key usage analytics from Redis-backed counters.

**Endpoint:** `/api/analytics/rate-limits/`  
**Methods:** `GET`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/analytics/rate-limits/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

## Contracts

### Return aggregate contract and event indexing snapshot statistics.

**Endpoint:** `/api/contracts/status/`  
**Methods:** `GET`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

**Response `200`:**
```json
{
  "total_contracts": 5,
  "active_contracts": 4,
  "paused_contracts": 1,
  "total_events_indexed": 12043,
  "last_event_timestamp": "2025-06-01T12:00:00Z",
  "events_per_minute": 7
}
```

---

## Dev

### Returns a high-level project summary for the Dev UI.

**Endpoint:** `/api/dev/summary/`  
**Methods:** `GET`  
**Auth required:** 🔓 No  

Response shape:
{
"unfinished_issues": {"count": int, "source": str},
"active_contributors": int,
"recent_prs": [{"id", "title", "state", "author"}, ...]
}

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/dev/summary/ \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

## General

### Liveness probe - app is running.

**Endpoint:** `/health/`  
**Methods:** `GET`  
**Auth required:** 🔓 No  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/health/ \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Readiness probe - DB and Redis are connected.

**Endpoint:** `/ready/`  
**Methods:** `GET`  
**Auth required:** 🔓 No  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/ready/ \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

## Ingest

### The default basic root view for DefaultRouter

**Endpoint:** `/api/ingest/`  
**Methods:** `GET` · `POST` · `PUT` · `PATCH` · `DELETE` · `HEAD`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `201` | Created |
| `400` | Validation error |
| `204` | No content |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/ingest/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Get recent ingest errors (admin only).

**Endpoint:** `/api/ingest/admin/ingest-errors/`  
**Methods:** `GET`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/ingest/admin/ingest-errors/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Admin endpoint exposing per-organization cost snapshots and budget state.

**Endpoint:** `/api/ingest/admin/organization-costs/`  
**Methods:** `GET`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/ingest/admin/organization-costs/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### ViewSet for managing API keys with tiered rate limiting.

**Endpoint:** `/api/ingest/api-keys/`  
**Methods:** `GET` · `POST`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `201` | Created |
| `400` | Validation error |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/ingest/api-keys/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### ViewSet for managing API keys with tiered rate limiting.

**Endpoint:** `/api/ingest/api-keys/{pk}/`  
**Methods:** `DELETE` · `GET` · `PATCH` · `PUT`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `204` | No content |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X DELETE \
  https://api.soroscan.io/api/ingest/api-keys/{pk}/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Query immutable admin audit trail entries.

**Endpoint:** `/api/ingest/audit-trail/`  
**Methods:** `GET`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

**Response `200`:**
```json
[
  {
    "id": 1,
    "username": "alice",
    "action": "update",
    "object_type": "TrackedContract",
    "object_id": "3",
    "timestamp": "2025-06-01T10:00:00Z",
    "ip_address": "1.2.3.4",
    "changes": {
      "is_active": [
        true,
        false
      ]
    }
  }
]
```

---

### GET /api/compliance-export/?from={iso}&to={iso}

**Endpoint:** `/api/ingest/compliance-export/`  
**Methods:** `GET`  
**Auth required:** ✅ Yes  

Returns a CSV audit trail of AuditLog entries for compliance auditors.
Staff only.

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/ingest/compliance-export/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### GET /api/contract/identity/

**Endpoint:** `/api/ingest/contract/identity/`  
**Methods:** `GET`  
**Auth required:** 🔓 No  

Returns the SoroScan contract ID and network information.
Allows clients to verify where events are coming from.

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |

#### Examples

**Response `200`:**
```json
{
  "contract_id": "CABC123...",
  "network_passphrase": "Test SDF Network ; September 2015",
  "rpc_url": "https://soroban-testnet.stellar.org"
}
```

---

### ViewSet for managing tracked contracts.

**Endpoint:** `/api/ingest/contracts/`  
**Methods:** `GET` · `POST`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `201` | Created |
| `400` | Validation error |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

**Response `200`:**
```json
{
  "count": 1,
  "results": [
    {
      "id": 1,
      "contract_id": "CABC123...",
      "name": "My Token Contract",
      "alias": "my-token",
      "is_active": true,
      "created_at": "2025-01-01T00:00:00Z"
    }
  ]
}
```

---

### ViewSet for managing tracked contracts.

**Endpoint:** `/api/ingest/contracts/completeness_dashboard/`  
**Methods:** `GET`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/ingest/contracts/completeness_dashboard/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### GET /api/contracts/<contract_id>/deployments/

**Endpoint:** `/api/ingest/contracts/{contract_id}/deployments/`  
**Methods:** `GET`  
**Auth required:** ✅ Yes  

Returns the full deployment history and ABI versions for a contract.
Includes compatibility warnings for breaking ABI changes.

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/ingest/contracts/{contract_id}/deployments/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Get event types and their counts for a specific contract.

**Endpoint:** `/api/ingest/contracts/{contract_id}/event-types/`  
**Methods:** `GET`  
**Auth required:** 🔓 No  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/ingest/contracts/{contract_id}/event-types/ \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Get the most recent events for a specific contract, newest first (SC-30).

**Endpoint:** `/api/ingest/contracts/{contract_id}/recent-events/`  
**Methods:** `GET`  
**Auth required:** 🔓 No  

Mirrors the bounded on-chain recent-events ring buffer exposed by the
SoroScan core contract's `recent_events` function, backed here by the
indexed event history for richer payload data. Accepts an optional
`limit` query parameter (1-20, default 10).

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `400` | Invalid `limit` parameter |
| `404` | Contract not found |

#### Examples

```bash
curl -X GET \
  "https://api.soroscan.io/api/ingest/contracts/{contract_id}/recent-events/?limit=10" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Redirect explorer requests to the frontend event explorer page.

**Endpoint:** `/api/ingest/contracts/{contract_id}/events/explorer/`  
**Methods:** `GET`  
**Auth required:** 🔓 No  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/ingest/contracts/{contract_id}/events/explorer/ \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Redirect timeline requests to the frontend contract timeline page.

**Endpoint:** `/api/ingest/contracts/{contract_id}/timeline/`  
**Methods:** `GET`  
**Auth required:** 🔓 No  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/ingest/contracts/{contract_id}/timeline/ \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Intentionally simple parent class for all views. Only implements

**Endpoint:** `/api/ingest/contracts/{contract_id}/vulnerability-impact/`  
**Methods:** `GET`  
**Auth required:** ✅ Yes  

dispatch-by-method and simple sanity checking.

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/ingest/contracts/{contract_id}/vulnerability-impact/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### ViewSet for managing tracked contracts.

**Endpoint:** `/api/ingest/contracts/{pk}/`  
**Methods:** `DELETE` · `GET` · `PATCH` · `PUT`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `204` | No content |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X DELETE \
  https://api.soroscan.io/api/ingest/contracts/{pk}/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### ViewSet for managing tracked contracts.

**Endpoint:** `/api/ingest/contracts/{pk}/completeness/`  
**Methods:** `GET`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/ingest/contracts/{pk}/completeness/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Get all events for a specific contract.

**Endpoint:** `/api/ingest/contracts/{pk}/events/`  
**Methods:** `GET`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/ingest/contracts/{pk}/events/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Get statistics for a contract.

**Endpoint:** `/api/ingest/contracts/{pk}/stats/`  
**Methods:** `GET`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/ingest/contracts/{pk}/stats/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Upload contract source code for verification.

**Endpoint:** `/api/ingest/contracts/{pk}/upload_source/`  
**Methods:** `POST`  
**Auth required:** ✅ Yes  

Accepts a file (Rust code or tarball) and optional ABI JSON.

#### Response Codes

| Code | Description |
|------|-------------|
| `201` | Created |
| `400` | Validation error |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X POST \
  https://api.soroscan.io/api/ingest/contracts/{pk}/upload_source/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Verify contract source against deployed bytecode.

**Endpoint:** `/api/ingest/contracts/{pk}/verify_source/`  
**Methods:** `POST`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `201` | Created |
| `400` | Validation error |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X POST \
  https://api.soroscan.io/api/ingest/contracts/{pk}/verify_source/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### GET  /api/deletion-requests/   — list all requests (staff) or own requests

**Endpoint:** `/api/ingest/deletion-requests/`  
**Methods:** `POST` · `GET`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `201` | Created |
| `400` | Validation error |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

**Request body:**
```json
{
  "subject_identifier": "user@example.com",
  "contract_ids": [
    "CABC123..."
  ]
}
```

**Response `201`:**
```json
{
  "id": 1,
  "requested_by": "alice",
  "subject_identifier": "user@example.com",
  "status": "pending",
  "requested_at": "2025-06-01T12:00:00Z"
}
```

---

### ViewSet for querying indexed events.

**Endpoint:** `/api/ingest/events/`  
**Methods:** `GET`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

**Response `200`:**
```json
{
  "count": 2,
  "results": [
    {
      "id": 42,
      "contract_id": "CABC123...",
      "event_type": "swap",
      "ledger": 12345,
      "timestamp": "2025-06-01T12:00:00Z",
      "tx_hash": "tx_abc...",
      "payload": {
        "from": "GAAA...",
        "to": "GBBB...",
        "amount": 1000
      }
    }
  ]
}
```

---

### Retrieve an archived event batch from S3 and re-import events into PostgreSQL.

**Endpoint:** `/api/ingest/events/restore-archive/`  
**Methods:** `POST`  
**Auth required:** ✅ Yes  
**Rate-limited:** ⚡ Yes  

#### Query Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `batch_id` | — | ID of the ArchivedEventBatch to restore |

#### Response Codes

| Code | Description |
|------|-------------|
| `201` | Created |
| `400` | Validation error |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X POST \
  https://api.soroscan.io/api/ingest/events/restore-archive/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Full-text and field-level search on contract event payloads.

**Endpoint:** `/api/ingest/events/search/`  
**Methods:** `GET`  
**Auth required:** ✅ Yes  

#### Query Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `q` | — | free-text substring match against JSON payload text |
| `contract_id` | — | filter by contract |
| `event_type` | — | filter by event type |
| `payload_contains` | — | JSON containment sub-string (fast with GIN index) |
| `payload_field` | — | dot-notation field path, e.g. decodedPayload.to |
| `payload_op` | — | operator: eq|neq|gte|lte|gt|lt|contains|startswith|in |
| `payload_value` | — | value for field comparison |
| `page` | — | / page_size  — pagination (max 1000 per page) |

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

**Response `200`:**
```json
{
  "count": 5,
  "page": 1,
  "page_size": 25,
  "results": [
    {
      "id": 42,
      "event_type": "swap",
      "ledger": 12345
    }
  ]
}
```

**Query string:** `?q=swap&contract_id=CABC123...&page=1&page_size=25`

---

### ViewSet for querying indexed events.

**Endpoint:** `/api/ingest/events/{pk}/`  
**Methods:** `GET`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/ingest/events/{pk}/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Health check endpoint.

**Endpoint:** `/api/ingest/health/`  
**Methods:** `GET`  
**Auth required:** 🔓 No  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |

#### Examples

**Response `200`:**
```json
{
  "status": "healthy",
  "service": "soroscan"
}
```

---

### List invocations with optional filters.

**Endpoint:** `/api/ingest/invocations/`  
**Methods:** `GET`  
**Auth required:** ✅ Yes  

#### Query Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `caller` | — | Filter by caller address |
| `function_name` | — | Filter by function name |
| `since` | — | ISO timestamp for start of range |
| `until` | — | ISO timestamp for end of range |
| `include_events` | — | Include nested events (default: false) |

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/ingest/invocations/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### ViewSet for querying contract invocations.

**Endpoint:** `/api/ingest/invocations/{pk}/`  
**Methods:** `GET`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/ingest/invocations/{pk}/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Return the list of Soroban networks supported by this indexer.

**Endpoint:** `/api/ingest/networks/`  
**Methods:** `GET`  
**Auth required:** 🔓 No  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/ingest/networks/ \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Record a new event by submitting a transaction to the SoroScan contract.

**Endpoint:** `/api/ingest/record/`  
**Methods:** `POST`  
**Auth required:** ✅ Yes  
**Rate-limited:** ⚡ Yes  

{
"contract_id": "CABC...",
"event_type": "swap",
"payload_hash": "abc123..."  // 64-char hex string
}

#### Response Codes

| Code | Description |
|------|-------------|
| `201` | Created |
| `400` | Validation error |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

**Request body:**
```json
{
  "contract_id": "CABC123...",
  "event_type": "swap",
  "payload_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
```

**Response `202`:**
```json
{
  "status": "submitted",
  "tx_hash": "abcd1234efgh5678",
  "transaction_status": "SUCCESS"
}
```

---

### Teams: multi-tenant organization of contracts and members.

**Endpoint:** `/api/ingest/teams/`  
**Methods:** `GET` · `POST`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `201` | Created |
| `400` | Validation error |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/ingest/teams/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Teams: multi-tenant organization of contracts and members.

**Endpoint:** `/api/ingest/teams/{pk}/`  
**Methods:** `DELETE` · `GET` · `PATCH` · `PUT`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `204` | No content |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X DELETE \
  https://api.soroscan.io/api/ingest/teams/{pk}/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Teams: multi-tenant organization of contracts and members.

**Endpoint:** `/api/ingest/teams/{pk}/members/`  
**Methods:** `POST`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `201` | Created |
| `400` | Validation error |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X POST \
  https://api.soroscan.io/api/ingest/teams/{pk}/members/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Return all events participating in the same atomic transaction.

**Endpoint:** `/api/ingest/transactions/{tx_id}/`  
**Methods:** `GET`  
**Auth required:** 🔓 No  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/ingest/transactions/{tx_id}/ \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### ViewSet for managing webhook subscriptions.

**Endpoint:** `/api/ingest/webhooks/`  
**Methods:** `GET` · `POST`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `201` | Created |
| `400` | Validation error |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

**Response `200`:**
```json
[
  {
    "id": 1,
    "target_url": "https://myapp.example.com/hooks/soroscan",
    "event_types": [
      "swap",
      "transfer"
    ],
    "is_active": true
  }
]
```

---

### ViewSet for managing webhook subscriptions.

**Endpoint:** `/api/ingest/webhooks/{pk}/`  
**Methods:** `DELETE` · `GET` · `PATCH` · `PUT`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `204` | No content |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X DELETE \
  https://api.soroscan.io/api/ingest/webhooks/{pk}/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### ViewSet for managing webhook subscriptions.

**Endpoint:** `/api/ingest/webhooks/{pk}/dry-run/`  
**Methods:** `POST`  
**Auth required:** ✅ Yes  

#### Response Codes

| Code | Description |
|------|-------------|
| `201` | Created |
| `400` | Validation error |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X POST \
  https://api.soroscan.io/api/ingest/webhooks/{pk}/dry-run/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Dispatch a background task that sends a test ping payload to the webhook

**Endpoint:** `/api/ingest/webhooks/{pk}/ping/`  
**Methods:** `POST`  
**Auth required:** ✅ Yes  

endpoint.  The task logs whether the target responded with HTTP 200.

#### Response Codes

| Code | Description |
|------|-------------|
| `201` | Created |
| `400` | Validation error |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X POST \
  https://api.soroscan.io/api/ingest/webhooks/{pk}/ping/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

### Send a test delivery directly to the webhook endpoint.

**Endpoint:** `/api/ingest/webhooks/{pk}/test/`  
**Methods:** `POST`  
**Auth required:** ✅ Yes  

The request is sent synchronously with a proper HMAC-SHA256 signature
so the subscriber can verify authenticity.  A 200 response from this
endpoint does NOT mean the delivery succeeded — check the response body
for the actual outcome.

#### Response Codes

| Code | Description |
|------|-------------|
| `201` | Created |
| `400` | Validation error |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

**Response `200`:**
```json
{
  "status": "test_webhook_queued"
}
```

---

## Meta

### Return real-time DB connection-pool stats for the ``default`` alias.

**Endpoint:** `/api/meta/db-pool/`  
**Methods:** `GET`  
**Auth required:** ✅ Yes  

The caller must be an active staff/superuser (Django ``is_staff=True``).
Regular authenticated users receive a 403 Forbidden.
Response keys
-------------
total      – total live DB connections for the current database
active     – live connections currently executing queries
idle       – live connections currently idle
wait_queue – live connections waiting on a DB wait event

#### Response Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `401` | Unauthorized – JWT token missing or invalid |

#### Examples

```bash
curl -X GET \
  https://api.soroscan.io/api/meta/db-pool/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

> Replace path parameters and supply a valid JWT in the Authorization header.

---

## Authentication

SoroScan uses **JWT Bearer tokens** for all authenticated endpoints.

```bash
# Obtain a token
curl -X POST https://api.soroscan.io/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secret"}'

# Use the token
curl https://api.soroscan.io/api/ingest/contracts/ \
  -H "Authorization: Bearer <access_token>"
```

Tokens expire; use `/api/token/refresh/` with the `refresh` token to renew.

---

## Rate Limiting

| Tier | Quota |
|------|-------|
| Anonymous | 60 req/min |
| Authenticated | 300 req/min |
| Ingest (custom API key) | Configurable per key |

Exceeded limits return HTTP **429 Too Many Requests**.

---

*Generated by `generate_api_docs` management command.*