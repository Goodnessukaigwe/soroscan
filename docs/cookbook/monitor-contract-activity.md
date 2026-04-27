# Monitor Contract Activity

Monitor contract health using stats and timeline endpoints.

## Get Stats

```bash
curl "https://api.soroscan.io/api/ingest/contracts/CCAAA.../stats/" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

## Build a Basic Health Signal

Track these fields:

- `latest_ledger`: detect indexing lag.
- `last_activity`: detect inactivity windows.
- `total_events`: detect ingestion growth.

Alert when `last_activity` exceeds your SLA threshold.
