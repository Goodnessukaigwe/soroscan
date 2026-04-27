# Manage API Keys

API keys let you access authenticated endpoints and higher rate limits.

## Create a Key

```bash
curl -X POST "https://api.soroscan.io/api/ingest/api-keys/" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"production-worker"}'
```

## Key Handling Guidelines

- Store keys in a secret manager, not source control.
- Rotate keys on a regular cadence.
- Scope usage by environment (`dev`, `staging`, `prod`).
