# Custom Webhook Subscriptions Tutorial

Webhooks allow your application to receive real-time, push-based HTTP notifications when smart contract events occur on the Stellar network. Instead of polling the SoroScan API, your server can immediately process events like token transfers, swaps, or custom contract states.

---

## 🛠️ Step 1: Register a Webhook Subscription

You can create a webhook subscription by making a `POST` request to the SoroScan REST API.

### Endpoint
`POST /api/webhooks/`

### Request Payload Fields
* `target_url` (String, Required): The public URL of your server's endpoint where SoroScan will send HTTP POST requests.
* `contract_id` (String, Required): The Soroban contract address you want to monitor (e.g., `CCAAA...`).
* `event_types` (Array of Strings, Optional): List of specific event symbols to filter for (e.g., `["transfer", "mint"]`). If omitted, all events for the contract are delivered.
* `filter_condition` (String, Optional): A filter expression to evaluate against event fields.

### Example cURL Request
```bash
curl -X POST https://api.soroscan.io/api/webhooks/ \
  -H "Authorization: Token your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "target_url": "https://your-domain.com/webhooks/soroscan",
    "contract_id": "CCAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "event_types": ["transfer"]
  }'
```

### Example JSON Response
```json
{
  "id": 42,
  "contract_id": "CCAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
  "target_url": "https://your-domain.com/webhooks/soroscan",
  "event_types": ["transfer"],
  "status": "active",
  "is_active": true,
  "created_at": "2026-07-28T14:15:00Z"
}
```

---

## 🧪 Step 2: Send a Test Webhook (Ping)

To verify that your webhook receiver is working and reachable, you can trigger a test delivery using the SoroScan API:

```bash
curl -X POST https://api.soroscan.io/api/webhooks/42/ping/ \
  -H "Authorization: Token your_api_key_here"
```

This will queue a background task in Celery to send a mock ping payload to your `target_url`.

---

## 🔒 Step 3: Verify Webhook Signatures

To ensure webhook events originate from SoroScan and have not been spoofed, SoroScan signs every webhook payload using **Ed25519**. The signature is sent in the **`X-Signature`** header in the following format:

```http
X-Signature: ed25519=SIGNATURE_IN_BASE64
```

You can obtain the platform's public key from the API metadata endpoint or your developer portal.

### Node.js (Express Native Verification)
Below is a copy-pasteable example of an Express receiver verifying the signature using the native `crypto` module (no external library required):

```javascript
const express = require('express');
const crypto = require('crypto');

const app = express();

// SoroScan Platform Public Key (obtain from developer portal)
const PLATFORM_PUBLIC_KEY_B64 = "YOUR_PLATFORM_PUBLIC_KEY_BASE64";

// We need raw request body bytes to verify the signature accurately
app.use(express.raw({ type: 'application/json' }));

app.post('/webhooks/soroscan', (req, res) => {
  const signatureHeader = req.headers['x-signature'];

  if (!signatureHeader || !signatureHeader.startsWith('ed25519=')) {
    console.error('Missing or invalid X-Signature header');
    return res.status(401).send('Unauthorized');
  }

  // Extract signature from header prefix "ed25519="
  const signatureB64 = signatureHeader.substring(8);
  const signature = Buffer.from(signatureB64, 'base64');
  const publicKeyBytes = Buffer.from(PLATFORM_PUBLIC_KEY_B64, 'base64');

  try {
    const publicKey = crypto.createPublicKey({
      key: publicKeyBytes,
      format: 'raw',
      type: 'ed25519',
    });

    const isVerified = crypto.verify(null, req.body, publicKey, signature);

    if (!isVerified) {
      console.warn('Signature verification failed');
      return res.status(401).send('Invalid signature');
    }

    // Process the verified payload
    const event = JSON.parse(req.body.toString());
    console.log('Verified event received:', event);

    res.status(200).send('Event processed');
  } catch (error) {
    console.error('Error verifying signature:', error);
    res.status(500).send('Internal Server Error');
  }
});

app.listen(3000, () => console.log('Webhook server listening on port 3000'));
```

### Python (Flask Verification)
To verify webhook signatures in Python, use the standard `cryptography` library:

```python
import base64
from flask import Flask, request, jsonify
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

app = Flask(__name__)

PLATFORM_PUBLIC_KEY_B64 = "YOUR_PLATFORM_PUBLIC_KEY_BASE64"

def verify_signature(public_key_b64: str, signature_header: str, payload_bytes: bytes) -> bool:
    if not signature_header or not signature_header.startswith("ed25519="):
        return False
    try:
        signature_b64 = signature_header[8:]
        signature = base64.b64decode(signature_b64)
        public_key_bytes = base64.b64decode(public_key_b64)
        
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        public_key.verify(signature, payload_bytes)
        return True
    except Exception:
        return False

@app.route('/webhooks/soroscan', methods=['POST'])
def handle_webhook():
    signature_header = request.headers.get("X-Signature", "")
    payload_bytes = request.data  # Get raw body bytes

    if not verify_signature(PLATFORM_PUBLIC_KEY_B64, signature_header, payload_bytes):
        return "Invalid signature", 401

    event_data = request.get_json()
    print(f"Verified event: {event_data}")
    return "Success", 200

if __name__ == '__main__':
    app.run(port=5000)
```

---

## 🔍 Troubleshooting Failed Deliveries

If your webhook target is not receiving events as expected, consult the following steps.

### 1. Delivery Status and Logs
You can query the history of webhook attempts directly from SoroScan:
* Endpoint: `GET /api/webhooks/{id}/deliveries/`
* This endpoint returns the status of the last 30 days of deliveries, including the HTTP status code returned by your server, response headers, and connection errors.

### 2. Timeouts and Status Codes
* **Timeout Limits**: Your endpoint must respond to a webhook POST request within **5 seconds**. If your processing takes longer, process the event asynchronously (e.g., using a message queue) and immediately return `200 OK` to SoroScan.
* **Success Codes**: Only responses in the `2xx` range (e.g., `200 OK`, `202 Accepted`) are marked as successful. Any other status code (like `500` or `404`) is classified as a delivery failure.

### 3. Automatic Retries
SoroScan uses an exponential backoff policy for failed webhook deliveries:
* Failed attempts are retried up to **5 times**.
* If a webhook subscription experiences **5 consecutive failed attempts** (either due to timeouts or non-2xx status codes), SoroScan automatically **suspends** the webhook to conserve system resources.

### 4. Resuming Suspended Webhooks
Once a webhook has been suspended:
1. Fix the underlying issue on your endpoint server.
2. Reactivate the webhook by making a `PUT` or `PATCH` request to the subscription details:
   ```bash
   curl -X PATCH https://api.soroscan.io/api/webhooks/42/ \
     -H "Authorization: Token your_api_key_here" \
     -H "Content-Type: application/json" \
     -d '{"status": "active"}'
   ```
3. You can also manually trigger retries of failed deliveries in the administrative dashboard's dead-letter queue.

---

## 🧪 Local Webhook Simulator

You can exercise a receiver **without** running Django, Celery, Redis, or PostgreSQL. The standalone simulator in `tools/webhook-simulator/` POSTs the same JSON envelope and HMAC headers as production `dispatch_webhook`.

```bash
cd tools/webhook-simulator
pip install -e .
python examples/receiver.py
# in another terminal
webhook-simulator --url http://127.0.0.1:8080/webhook --sample --secret test-secret
```

Docker (hits a listener on the host):

```bash
docker compose -f tools/webhook-simulator/docker-compose.yml run --rm webhook-simulator \
  --url http://host.docker.internal:8080/webhook --sample --secret test-secret
```

The CLI prints delivery status, HTTP status, latency, acknowledgement (`X-SoroScan-Ack`), response headers, and a truncated response body. Use `--output json` for a machine-readable result, `--dry-run` to inspect the signed request, and `--help` for retries and Ed25519 (`X-Signature`) options. See `tools/webhook-simulator/README.md` for the full payload contract.
