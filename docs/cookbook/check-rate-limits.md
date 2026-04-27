# Check Rate Limits

Inspect rate limit headers to understand current usage vs limit.

## cURL Example

```bash
curl -i "https://api.soroscan.io/api/ingest/contracts/" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

Look for:

- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`

## Usage Formula

```text
usage = X-RateLimit-Limit - X-RateLimit-Remaining
usage_percent = usage / X-RateLimit-Limit * 100
```
