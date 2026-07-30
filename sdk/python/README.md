# SoroScan Python SDK

Official Python client for the [SoroScan API](https://soroscan.io) - Stellar/Soroban event indexing and querying.

## Features

- **Full API Coverage**: All SoroScan REST endpoints supported
- **Sync & Async**: Both synchronous and async clients via `httpx`
- **Type Safe**: 100% type hints with Pydantic v2 models
- **Python 3.10+**: Modern Python with full type checking support
- **Production Ready**: Comprehensive error handling and validation

## Installation

```bash
pip install soroscan-sdk
```

## Quick Start

### CLI

Installing the package exposes the `soroscan` command:

```bash
export SOROSCAN_API_KEY="your-api-key"
export SOROSCAN_BASE_URL="https://api.soroscan.io"

soroscan events --contract CCAAA... --event-type transfer --limit 10
soroscan events --contract CCAAA... --output json
soroscan webhooks list
soroscan webhooks test 1
soroscan contracts list --search token
soroscan contracts get 1 --output json
```

### Synchronous Client

```python
from soroscan import SoroScanClient

# Initialize client
client = SoroScanClient(
    base_url="https://api.soroscan.io",
    api_key="your-api-key"  # Optional
)

# Query events
events = client.get_events(
    contract_id="CCAAA...",
    event_type="transfer",
    ledger_min=100000,
    page_size=50
)

for event in events.results:
    print(f"{event.event_type} at ledger {event.ledger}")

# Register a contract
contract = client.create_contract(
    contract_id="CCAAA...",
    name="My Token Contract",
    description="ERC-20 style token"
)

# Get contract statistics
stats = client.get_contract_stats(contract.id)
print(f"Total events: {stats.total_events}")

# Close client when done
client.close()
```

### Async Client

```python
import asyncio
from soroscan import AsyncSoroScanClient

async def main():
    async with AsyncSoroScanClient(base_url="https://api.soroscan.io") as client:
        # Query events asynchronously
        events = await client.get_events(
            contract_id="CCAAA...",
            event_type="swap",
            page_size=100
        )
        
        # Create webhook subscription
        webhook = await client.create_webhook(
            contract_id=1,
            target_url="https://myapp.com/webhook",
            event_type="transfer"
        )
        
        print(f"Webhook created: {webhook.id}")

asyncio.run(main())
```

### Context Manager

```python
# Automatic cleanup with context manager
with SoroScanClient(base_url="https://api.soroscan.io") as client:
    contracts = client.get_contracts(is_active=True)
    print(f"Found {contracts.count} active contracts")
```

## API Reference

### Client Initialization

```python
SoroScanClient(
    base_url: str = "https://api.soroscan.io",
    api_key: str | None = None,
    timeout: float = 30.0
)
```

### Contracts

#### List Contracts
```python
client.get_contracts(
    is_active: bool | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50
) -> PaginatedResponse[TrackedContract]
```

#### Get Contract
```python
client.get_contract(contract_id: str) -> TrackedContract
```

#### Create Contract
```python
client.create_contract(
    contract_id: str,
    name: str,
    description: str = "",
    abi_schema: dict | None = None
) -> TrackedContract
```

#### Update Contract
```python
client.update_contract(
    contract_id: str,
    name: str | None = None,
    description: str | None = None,
    is_active: bool | None = None
) -> TrackedContract
```

#### Delete Contract
```python
client.delete_contract(contract_id: str) -> None
```

#### Get Contract Stats
```python
client.get_contract_stats(contract_id: str) -> ContractStats
```

### Events

#### Query Events
```python
client.get_events(
    contract_id: str | None = None,
    event_type: str | None = None,
    ledger: int | None = None,
    ledger_min: int | None = None,
    ledger_max: int | None = None,
    validation_status: Literal["passed", "failed"] | None = None,
    ordering: str = "-timestamp",
    page: int = 1,
    page_size: int = 50
) -> PaginatedResponse[ContractEvent]
```

#### Get Event
```python
client.get_event(event_id: int) -> ContractEvent
```

#### Record Event
```python
client.record_event(
    contract_id: str,
    event_type: str,
    payload_hash: str
) -> RecordEventResponse
```

### Webhooks

#### List Webhooks
```python
client.get_webhooks(
    page: int = 1,
    page_size: int = 50
) -> PaginatedResponse[WebhookSubscription]
```

#### Get Webhook
```python
client.get_webhook(webhook_id: int) -> WebhookSubscription
```

#### Create Webhook
```python
client.create_webhook(
    contract_id: int,
    target_url: str,
    event_type: str = ""
) -> WebhookSubscription
```

#### Update Webhook
```python
client.update_webhook(
    webhook_id: int,
    target_url: str | None = None,
    event_type: str | None = None,
    is_active: bool | None = None
) -> WebhookSubscription
```

#### Delete Webhook
```python
client.delete_webhook(webhook_id: int) -> None
```

#### Test Webhook
```python
client.test_webhook(webhook_id: int) -> dict[str, str]
```

### Indexer Rate Limits (SC-26)

Admins can cap how many events a given indexer account is allowed to record
per ledger. This protects the contract and downstream ingestion pipeline from
a single misbehaving or compromised indexer flooding the system.

#### Set Rate Limit
```python
client.set_indexer_rate_limit(
    indexer: str,
    max_events_per_ledger: int
) -> SetIndexerRateLimitResponse
```

Pass `max_events_per_ledger=0` to clear a previously configured limit and make
the indexer unrestricted again. Requires an admin-scoped API key.

#### Get Rate Limit
```python
client.get_indexer_rate_limit(indexer: str) -> IndexerRateLimit
```

`IndexerRateLimit.max_events_per_ledger` is `None` when the indexer is
unrestricted.

```python
# Cap an indexer to 500 events per ledger
client.set_indexer_rate_limit(
    indexer="GABCD...", max_events_per_ledger=500
)

limit = client.get_indexer_rate_limit("GABCD...")
print(f"Limit: {limit.max_events_per_ledger}")
```

CLI equivalent:
```bash
soroscan indexers set-rate-limit GABCD... 500
soroscan indexers get-rate-limit GABCD...
```

## Data Models

All response models are Pydantic v2 models with full type safety:

- `TrackedContract`: Registered contract details
- `ContractEvent`: Indexed event data
- `WebhookSubscription`: Webhook configuration
- `ContractStats`: Aggregate statistics
- `PaginatedResponse[T]`: Generic paginated wrapper
- `RecordEventResponse`: Event submission result

## Error Handling

The SDK provides a typed error hierarchy for handling different error scenarios. You can catch specific error types to handle them appropriately.

```python
from soroscan import (
    SoroScanClient,
    SoroScanRateLimitError,
    SoroScanValidationError,
    SoroScanAuthError,
    SoroScanNotFoundError,
    SoroScanTimeoutError,
    SoroScanConnectionError,
)

client = SoroScanClient(base_url="https://api.soroscan.io", api_key="your-key")

try:
    events = client.get_events(contract_id="CCAAA...")
except SoroScanRateLimitError as e:
    # Handle rate limit
    print(f"Rate limit: retry after {e.retry_after}s")
    print(f"Limit: {e.limit}, Remaining: {e.remaining}")
except SoroScanValidationError as e:
    # Handle validation error
    print(f"Invalid field: {e.field}")
    print(f"Value: {e.value}")
    print(f"Errors: {e.errors}")
except SoroScanAuthError as e:
    # Handle authentication error
    print(f"Authentication failed: {e.message}")
except SoroScanNotFoundError as e:
    # Handle not found error
    print(f"Resource not found: {e.resource_type} ({e.resource_id})")
except SoroScanTimeoutError as e:
    # Handle timeout error
    print(f"Request timed out after {e.timeout}s")
except SoroScanConnectionError as e:
    # Handle connection error
    print(f"Failed to connect to {e.url}")
except SoroScanAPIError as e:
    # Handle generic API error
    print(f"API error [{e.status_code}] {e.code}: {e.message}")
except SoroScanError as e:
    # Handle generic error
    print(f"Error: {e.message}")
```

### Error Types

| Error Type | Status Code | Use Case | Additional Properties |
|---|---|---|---|
| `SoroScanRateLimitError` | 429 | Rate limit exceeded | `retry_after`, `limit`, `remaining` |
| `SoroScanValidationError` | 400 | Request validation failed | `field`, `value`, `errors` |
| `SoroScanAuthError` | 401/403 | Authentication/authorization failed | - |
| `SoroScanNotFoundError` | 404 | Resource not found | `resource_type`, `resource_id` |
| `SoroScanServerError` | 5xx | Server error | - |
| `SoroScanTimeoutError` | - | Request timed out | `url`, `timeout` |
| `SoroScanConnectionError` | - | Connection failed | `url` |
| `SoroScanAPIError` | Other | Generic API error | - |

### Base Error Properties

All error types inherit from `SoroScanError` and include:

| Property | Type | Description |
|---|---|---|
| `message` | `str` | Human-readable error message |
| `status_code` | `int` | HTTP status code (for API errors) |
| `code` | `str` | Machine-readable error code from the API |
| `response_data` | `dict` | Optional additional context from the API |

## Advanced Usage

### Pagination

```python
# Iterate through all pages
page = 1
while True:
    response = client.get_events(page=page, page_size=100)
    
    for event in response.results:
        process_event(event)
    
    if not response.next:
        break
    page += 1
```

### Filtering Events

```python
# Complex event filtering
events = client.get_events(
    contract_id="CCAAA...",
    event_type="swap",
    ledger_min=1000000,
    ledger_max=2000000,
    validation_status="passed",
    ordering="-ledger",  # Descending by ledger
    page_size=100
)
```

### Async Batch Operations

```python
async def fetch_multiple_contracts(contract_ids: list[str]):
    async with AsyncSoroScanClient() as client:
        tasks = [client.get_contract(cid) for cid in contract_ids]
        contracts = await asyncio.gather(*tasks)
        return contracts
```

## Development

### Setup

```bash
# Clone repository
git clone https://github.com/soroscan/soroscan.git
cd soroscan/sdk/python

# Install with dev dependencies
pip install -e ".[dev]"
```

### Type Checking

```bash
mypy soroscan --strict
```

### Testing

```bash
pytest tests/ -v
```

### Linting

```bash
ruff check soroscan/
ruff format soroscan/
```

## Requirements

- Python 3.10+
- httpx >= 0.27.0
- pydantic >= 2.0.0

## License

MIT License - see LICENSE file for details

## Links

- [Documentation](https://docs.soroscan.io)
- [API Reference](https://api.soroscan.io/docs)
- [GitHub](https://github.com/soroscan/soroscan)
- [Issues](https://github.com/soroscan/soroscan/issues)

## Support

For questions and support:
- GitHub Issues: https://github.com/soroscan/soroscan/issues
- Email: team@soroscan.io
