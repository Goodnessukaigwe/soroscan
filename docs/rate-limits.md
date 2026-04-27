---
id: rate-limits
title: Rate Limits
sidebar_label: Rate Limits
---

SoroScan enforces rate limits to ensure fair usage and platform stability. This page explains the limits and how to monitor your usage.

## Default Limits

| Access Type | Limit |
|---|---|
| **Public (unauthenticated)** | 60 requests/minute |
| **Authenticated (API Key)** | 500 requests/minute |
| **Per-contract ingest** | Configurable via `max_events_per_minute` |

## How Rate Limiting Works

Rate limits are enforced using a rolling 60-second window tracked in Redis. Each request increments a counter keyed to your IP or API key. When the counter exceeds the limit, the API returns a `429 Too Many Requests` response.

### Response Headers

Every API response includes headers that help you monitor your usage:

```http
X-RateLimit-Limit: 500
X-RateLimit-Remaining: 432
X-RateLimit-Reset: 1714508459
```

The `Retry-After` header tells you exactly how many seconds until your limit resets (calculated as seconds remaining in the current minute).

## Checking Your Current Usage

### Via the REST API

Query the stats endpoint for any tracked contract to see ingest rate config:

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
  https://api.soroscan.io/api/ingest/contracts/YOUR_CONTRACT_ID/stats/
```

```json
{
  "contract_id": "CCAAA...",
  "total_events": 12500,
  "unique_event_types": 4,
  "latest_ledger": 512000,
  "last_activity": "2024-05-01T12:34:56Z"
}
```

### Via SDKs

#### Python

```python
from soroscan import SoroScanClient

client = SoroScanClient(base_url="https://api.soroscan.io", api_key="your-api-key")

stats = client.get_contract_stats("CCAAA...")
print(f"Total events indexed: {stats.total_events}")
print(f"Last activity: {stats.last_activity}")
```

#### TypeScript

```typescript
import { SoroScanClient } from "@soroscan/sdk";

const client = new SoroScanClient({
  baseUrl: "https://api.soroscan.io",
  apiKey: "your-api-key",
});

const stats = await client.getContractStats({ contractId: "CCAAA..." });
console.log(`Total events: ${stats.totalEvents}`);
console.log(`Last active: ${stats.lastActivity}`);
```

## Rate Limit Observability

You can compute current usage versus limit directly from response headers:

```text
usage = X-RateLimit-Limit - X-RateLimit-Remaining
```

Build dashboards around these metrics:

- `usage_percent = usage / X-RateLimit-Limit * 100`
- `remaining_requests = X-RateLimit-Remaining`
- `seconds_to_reset = X-RateLimit-Reset - now`

Track these over time to alert before saturation and plan scale-up.

## Handling 429 Responses

#### Python

```python
from soroscan.exceptions import RateLimitError
import time

try:
    events = client.get_events(contract_id="CCAAA...")
except RateLimitError as e:
    print(f"Rate limited. Retry after {e.retry_after} seconds.")
    time.sleep(e.retry_after)
```

#### TypeScript

```typescript
import { SoroScanError } from "@soroscan/sdk";

try {
  const events = await client.getEvents({ contractId: "CCAAA..." });
} catch (err) {
  if (err instanceof SoroScanError && err.statusCode === 429) {
    const retryAfter = parseInt(err.headers?.["retry-after"] ?? "60");
    console.log(`Rate limited. Retrying in ${retryAfter}s...`);
    await new Promise(resolve => setTimeout(resolve, retryAfter * 1000));
  }
}
```

## Updating Contract Ingest Limits

```bash
curl -X PUT \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"max_events_per_minute": 200}' \
  https://api.soroscan.io/api/ingest/contracts/YOUR_CONTRACT_ID/
```
