# Setup Webhook

Use this recipe to receive push notifications whenever new events are indexed.

## Create a Webhook

```bash
curl -X POST "https://api.soroscan.io/api/ingest/webhooks/" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-app.com/webhooks/soroscan",
    "triggers": ["event.created"],
    "contract_id": "CCAAA...",
    "secret": "replace-with-random-secret"
  }'
```

## Verify Signature (Node.js)

```javascript
import crypto from "crypto";

export function verifySoroScanSignature(rawBody, signature, secret) {
  const expected = crypto.createHmac("sha256", secret).update(rawBody).digest("hex");
  return signature === expected;
}
```
