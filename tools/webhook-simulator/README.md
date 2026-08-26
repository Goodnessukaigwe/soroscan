# SoroScan Webhook Simulator

Standalone tool that delivers **production-shaped** SoroScan webhook payloads to a local endpoint. It does **not** require Django, Celery, Redis, or PostgreSQL.

Use it to exercise your receiver's signature checks, acknowledgement headers, timeouts, and retry handling before pointing a real subscription at it.

## What it sends

Deliveries match `dispatch_webhook` in `django-backend/soroscan/ingest/tasks.py`:

| Piece | Convention |
| --- | --- |
| Body | Canonical JSON envelope: `contract_id`, `event_type`, `payload`, `ledger`, `event_index`, `tx_hash` (`json.dumps(..., sort_keys=True)`) |
| `Content-Type` | `application/json` |
| `X-SoroScan-Signature` | `sha256=<hex>` HMAC of the raw body (or `sha1=` if requested) |
| `X-SoroScan-Timestamp` | timezone-aware ISO-8601 timestamp |
| `X-Signature` | optional `ed25519=<base64>` when a 32-byte hex seed is provided |
| Ping | `{"type": "ping", "timestamp": "..."}` with `X-SoroScan-Event: ping` |

Success is HTTP **2xx**. Pass `--require-ack` to also require `X-SoroScan-Ack: ok`, matching production SLA behaviour.

## Install (local)

```bash
cd tools/webhook-simulator
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```bash
# Sample transfer event
webhook-simulator --url http://localhost:8080/webhook --sample --secret test-secret

# Event file
webhook-simulator --url http://localhost:8080/webhook --event-file examples/sample-event.json --secret test-secret

# Inline JSON or stdin
webhook-simulator --url http://localhost:8080/webhook --event '{"event_type":"mint","payload":{"n":1}}'
cat examples/sample-event.json | webhook-simulator --url http://localhost:8080/webhook --event -

# Production ping payload
webhook-simulator --url http://localhost:8080/webhook --ping

# Inspect the signed request without sending
webhook-simulator --dry-run --sample --secret test-secret --url http://localhost:8080/webhook

# JSON output (script-friendly)
webhook-simulator --url http://localhost:8080/webhook --sample --secret test-secret --output json
```

Environment variables:

- `SOROSCAN_WEBHOOK_URL`
- `SOROSCAN_WEBHOOK_SECRET`
- `WEBHOOK_ED25519_SIGNING_SEED` (64 hex characters)

Run `webhook-simulator --help` for retries, backoff, acknowledgement, and extra headers.

## Local receiver

```bash
python examples/receiver.py
# in another terminal
webhook-simulator --url http://127.0.0.1:8080/webhook --sample --secret test-secret
```

The example receiver prints headers/body and responds with `200` plus `X-SoroScan-Ack: ok`.

## Docker

```bash
cd tools/webhook-simulator
docker compose build

# Hit a receiver on the host (Linux: host-gateway; Docker Desktop: host.docker.internal)
docker compose run --rm webhook-simulator \
  --url http://host.docker.internal:8080/webhook \
  --event-file /examples/sample-event.json \
  --secret test-secret
```

From the repository root, the same image is available as an optional Compose profile:

```bash
docker compose --profile tools run --rm webhook-simulator \
  --url http://host.docker.internal:8080/webhook --sample --secret test-secret
```

## Tests

```bash
cd tools/webhook-simulator
pip install -e ".[dev]"
pytest
```
