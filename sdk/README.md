# SoroScan SDKs

## SC-38 structured events

SC-38 adds a versioned, retry-safe event submission path. Provide a SHA-256
payload hash, a non-zero schema version, and a unique 32-byte hexadecimal
correlation ID. Reusing the correlation ID is rejected by the contract, so a
network retry cannot create a second event.

```python
client.record_structured_event(contract_id, "transfer", payload_hash, 1, correlation_id)
```

```ts
await client.recordStructuredEvent({ contractId, eventType: "transfer", payloadHash, schemaVersion: 1, correlationId });
```

## SC-26 indexer rate limits

SC-26 lets admins cap how many events an indexer may record per ledger.
`max_events_per_ledger = 0` clears the limit (unlimited). Both SDKs expose
set/get helpers backed by `POST /api/ingest/indexers/rate-limit/` and
`GET /api/ingest/indexers/<indexer>/rate-limit/`.

```python
client.set_indexer_rate_limit(indexer="GABC...", max_events_per_ledger=500)
limit = client.get_indexer_rate_limit("GABC...")
```

```ts
await client.setIndexerRateLimit({ indexer: "GABC...", maxEventsPerLedger: 500 });
const limit = await client.getIndexerRateLimit("GABC...");
```

Official SDKs for the SoroScan API - Stellar/Soroban event indexing.

## Strict type verification

```bash
cd typescript && npm run typecheck
cd ../python && python -m mypy soroscan
```

The TypeScript SDK enables `strict`, `strictNullChecks`, and
`noUncheckedIndexedAccess`, and contains no explicit `any` types. The Python
SDK uses mypy strict mode and requires annotations for every function.

## Available SDKs

### Python SDK

**Status**: ✅ Complete and ready for production

**Location**: `sdk/python/`

**Features**:
- Synchronous and asynchronous clients
- Full REST API coverage (15 endpoints)
- 100% type hint coverage with mypy strict
- Pydantic v2 models for type safety
- Comprehensive test suite (42+ tests)
- Python 3.10+ support

**Installation**:
```bash
pip install soroscan-sdk
```

**Quick Start**:
```python
from soroscan import SoroScanClient

client = SoroScanClient(base_url="https://api.soroscan.io", api_key="...")
events = client.get_events(contract_id="CCAAA...", event_type="transfer")
```

**Documentation**: See [python/README.md](python/README.md)

## Future SDKs

### JavaScript/TypeScript SDK
- Status: Planned
- Target: Node.js and browser support
- Features: TypeScript types, Promise-based API

### Rust SDK
- Status: Planned
- Target: Native Stellar/Soroban integration
- Features: Zero-cost abstractions, async/await

### Go SDK
- Status: Planned
- Target: Backend services
- Features: Goroutine support, context handling

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution guidelines.

## Support

- GitHub Issues: https://github.com/soroscan/soroscan/issues
- Email: team@soroscan.io
- Documentation: https://docs.soroscan.io

## License

All SDKs are released under the MIT License.
