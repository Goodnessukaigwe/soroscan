# SoroScan Django Backend

REST and GraphQL API for indexing Soroban smart contract events.

## Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Start development server
daphne -b 0.0.0.0 -p 8000 soroscan.asgi:application

# For development with auto-reload
python manage.py runserver
```

## Running with ASGI (Production)

For WebSocket support in production, use an ASGI server:

```bash
# Using Daphne
daphne -b 0.0.0.0 -p 8000 soroscan.asgi:application

# Using Uvicorn
uvicorn soroscan.asgi:application --host 0.0.0.0 --port 8000
```

## Environment Variables

Create a `.env` file:

```env
DEBUG=True
SECRET_KEY=your-secret-key-here
DATABASE_URL=postgres://user:pass@localhost:5432/soroscan
REDIS_URL=redis://localhost:6379/0

# Stellar
SOROBAN_RPC_URL=https://soroban-testnet.stellar.org
STELLAR_NETWORK_PASSPHRASE=Test SDF Network ; September 2015
SOROSCAN_CONTRACT_ID=CCAAAA...
INDEXER_SECRET_KEY=SCXXXX...
```

## Running Celery Workers

```bash
# Start worker
celery -A soroscan worker -l info

# Start beat scheduler
celery -A soroscan beat -l info
```

## Logging and Sentry

- **Log format**: Set `LOG_FORMAT=json` to emit structured JSON logs (one JSON object per line). Omit or leave unset for human-readable logs. Each JSON line includes `timestamp`, `levelname`, `name` (logger), and `message`; ingest logs also include `request_id`, `contract_id`, and `ledger_sequence` when available.
- **Sentry**: Optional. Set `SENTRY_DSN` to enable error and performance monitoring. If unset, the application starts normally and Sentry is not initialised. Celery task failures are reported to Sentry with task name context when the integration is enabled.
- **Performance traces**: When Sentry is enabled, `SENTRY_TRACES_SAMPLE_RATE` defaults to `0.1` (10%) to control cost; set in `.env` if needed.
- **PII**: Do not log personally identifiable information. Keep log messages and structured fields free of user emails, secret keys, or other sensitive data.

## API Endpoints

### REST API

- `POST /api/ingest/record/` - Record a new event
- `GET /api/events/` - List events
- `GET /api/contracts/` - List tracked contracts

### GraphQL

- `POST /graphql/` - GraphQL endpoint

### WebSocket

- `ws://host/ws/events/<contract_id>/` - Real-time event streaming

## WebSocket Usage

Connect to a contract's event stream:

```javascript
// JavaScript example
const ws = new WebSocket("ws://localhost:8000/ws/events/CABC123.../");

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log("New event:", data);
};

ws.onerror = (error) => {
  console.error("WebSocket error:", error);
};

ws.onclose = (event) => {
  console.log("WebSocket closed:", event.code);
};
```

Filter by event type using query parameters:

```javascript
const ws = new WebSocket(
  "ws://localhost:8000/ws/events/CABC123.../?event_type=swap",
);
```

Python client example:

```python
import asyncio
import websockets
import json

async def listen_to_events():
    uri = "ws://localhost:8000/ws/events/CABC123.../"
    async with websockets.connect(uri) as websocket:
        while True:
            message = await websocket.recv()
            event = json.loads(message)
            print(f"Received event: {event}")

asyncio.run(listen_to_events())
```
