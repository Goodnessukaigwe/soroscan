# Filter by Event Type

Filter indexed events server-side to reduce payload size and improve latency.

## REST

```bash
curl "https://api.soroscan.io/api/ingest/events/?contract=CCAAA...&event_type=transfer" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

## Python

```python
events = client.get_events(contract_id="CCAAA...", event_type="transfer", first=50)
```

## TypeScript

```typescript
const events = await client.getEvents({
  contractId: "CCAAA...",
  eventType: "transfer",
  first: 50,
});
```
