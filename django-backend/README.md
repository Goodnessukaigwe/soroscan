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
FRONTEND_BASE_URL=http://localhost:3000

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

## CDC Streaming

SoroScan can publish indexed events to Kafka, Pub/Sub, or SQS for downstream warehouses.

- default Kafka topic: `soroscan.events`
- schema subject: `soroscan.events-value`
- integration guide: `docs/cdc-streaming.md`

## Logging and Sentry

- **Log format**: Set `LOG_FORMAT=json` to emit structured JSON logs (one JSON object per line). Omit or leave unset for human-readable logs. Each JSON line includes `timestamp`, `levelname`, `name` (logger), and `message`; ingest logs also include `request_id`, `contract_id`, and `ledger_sequence` when available.
- **Sentry**: Optional. Set `SENTRY_DSN` to enable error and performance monitoring. If unset, the application starts normally and Sentry is not initialised. Celery task failures are reported to Sentry with task name context when the integration is enabled.
- **Performance traces**: When Sentry is enabled, `SENTRY_TRACES_SAMPLE_RATE` defaults to `0.1` (10%) to control cost; set in `.env` if needed.
- **PII**: Do not log personally identifiable information. Keep log messages and structured fields free of user emails, secret keys, or other sensitive data.

## API Endpoints

### Authentication

SoroScan uses JWT (JSON Web Token) authentication for write operations. Read endpoints remain public.

#### Obtaining Tokens

```bash
# Get access and refresh tokens
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "your_username", "password": "your_password"}'

# Response:
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

#### Using Access Tokens

```bash
# Include the access token in the Authorization header
curl -X POST http://localhost:8000/api/ingest/record/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..." \
  -H "Content-Type: application/json" \
  -d '{"contract_id": "CABC...", "event_type": "swap", "payload_hash": "abc123..."}'
```

#### Refreshing Tokens

```bash
# Get a new access token using the refresh token
curl -X POST http://localhost:8000/api/token/refresh/ \
  -H "Content-Type: application/json" \
  -d '{"refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."}'

# Response:
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

#### Token Lifetimes

- Access tokens expire after 15 minutes
- Refresh tokens expire after 7 days
- Tokens are signed using the SECRET_KEY environment variable

#### GraphQL Authentication

For GraphQL mutations, include the JWT token in the Authorization header:

```bash
curl -X POST http://localhost:8000/graphql/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..." \
  -H "Content-Type: application/json" \
  -d '{"query": "mutation { registerContract(contractId: \"CABC...\", name: \"My Contract\") { id contractId name } }"}'
```

### Interactive Documentation (Swagger / ReDoc)

SoroScan REST API comes with auto-generated interactive documentation:
- **Swagger UI**: `/api/docs/`
- **ReDoc UI**: `/api/redoc/`
- **OpenAPI Schema**: `/api/schema/`

### REST API

#### Public Endpoints (No Authentication Required)

- `GET /api/events/` - List events
- `GET /api/contracts/` - List tracked contracts
- `GET /api/ingest/health/` - Health check

#### Protected Endpoints (Authentication Required)

- `POST /api/ingest/record/` - Record a new event (requires JWT token)
- `POST /api/contracts/` - Create a tracked contract (requires JWT token)
- `PUT /api/contracts/{id}/` - Update a contract (requires JWT token)
- `PATCH /api/contracts/{id}/` - Partially update a contract (requires JWT token)
- `DELETE /api/contracts/{id}/` - Delete a contract (requires JWT token)
- `POST /api/webhooks/` - Create a webhook subscription (requires JWT token)
- `PUT /api/webhooks/{id}/` - Update a webhook (requires JWT token)
- `DELETE /api/webhooks/{id}/` - Delete a webhook (requires JWT token)

#### Authentication Endpoints

- `POST /api/token/` - Obtain JWT access and refresh tokens
- `POST /api/token/refresh/` - Refresh an access token

### GraphQL

- `POST /graphql/` - GraphQL endpoint

#### Public Queries (No Authentication Required)

- `contracts` - List all tracked contracts
- `contract(contractId)` - Get a specific contract
- `events(...)` - Query events with filtering and pagination
- `event(id)` - Get a specific event
- `contractStats(contractId)` - Get contract statistics
- `eventTypes(contractId)` - Get unique event types
- `eventTimeline(...)` - Grouped timeline query with bucket zoom/filter support

#### Protected Mutations (Authentication Required)

- `registerContract(contractId, name, description)` - Register a new contract
- `updateContract(contractId, name, description, isActive)` - Update a contract

Mutations require a valid JWT token in the Authorization header. Unauthenticated requests will receive an error response.

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
