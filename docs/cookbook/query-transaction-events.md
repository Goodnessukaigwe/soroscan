# Query Transaction Events

Use the transaction endpoint to fetch all contract events emitted in one transaction.

## REST

```bash
curl "https://api.soroscan.io/api/ingest/transactions/YOUR_TX_HASH/" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

## TypeScript

```typescript
const txEvents = await client.getTransactionEvents({ txId: "YOUR_TX_HASH" });
console.log(txEvents);
```
