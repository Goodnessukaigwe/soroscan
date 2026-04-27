# Track Contract Events

Use this recipe to monitor events emitted by a single Soroban contract.

## Goal

Track `transfer` and `mint` events for one contract and process them in your app.

## Python

```python
from soroscan import SoroScanClient

client = SoroScanClient(base_url="https://api.soroscan.io", api_key="your-api-key")

events = client.get_events(contract_id="CCAAA...", event_type="transfer", first=25)
for event in events.items:
    print(event.ledger, event.event_type, event.tx_hash)
```

## TypeScript

```typescript
import { SoroScanClient } from "@soroscan/sdk";

const client = new SoroScanClient({
  baseUrl: "https://api.soroscan.io",
  apiKey: "your-api-key",
});

const events = await client.getEvents({
  contractId: "CCAAA...",
  eventType: "transfer",
  first: 25,
});

events.items.forEach((event) => {
  console.log(event.ledger, event.eventType, event.txHash);
});
```
