# Soroban Contracts

This folder contains all Soroban smart contracts for SoroScan.

## Contracts

### soroscan_core

The core contract that:
- Accepts event submissions from authorized indexers
- Emits standardized events for off-chain consumption
- Stores event counters and latest events by type

## Building

```bash
cd soroscan_core
cargo build --target wasm32-unknown-unknown --release
```

## Testing

Unit tests live in `soroscan_core/src/lib.rs` under `#[cfg(test)]` and use
`soroban_sdk::testutils` (`Env::default()`, `register_contract`, `mock_all_auths`).

| Test | Scenario | Expected |
|------|----------|----------|
| `test_initialize` | Deploy and init with admin | Admin set correctly |
| `test_add_indexer_as_admin` | Admin adds indexer | Indexer whitelisted |
| `test_add_indexer_as_non_admin` | Non-admin adds indexer | `ContractError::Unauthorized` |
| `test_record_event_whitelisted` | Whitelisted indexer records event | Event emitted, counter incremented |
| `test_record_event_not_whitelisted` | Non-whitelisted address records | `ContractError::IndexerNotFound` |
| `test_remove_indexer` | Admin removes indexer | Indexer no longer whitelisted |

Run all tests:

```bash
cd soroscan_core
cargo test
```

Expected output: all tests passing with no warnings.

## SC-38 structured events

`record_structured_event` adds an opt-in, backward-compatible event format. It
accepts the existing contract ID, event type, and SHA-256 payload hash plus a
non-zero `schema_version` and a 32-byte `correlation_id`. The correlation ID is
stored and rejects retries that would otherwise publish a duplicate event.

The Python and TypeScript SDKs expose this as `record_structured_event` and
`recordStructuredEvent`; both submit to `POST /api/record/structured/`.

## SC-26 indexer rate limiting

`set_indexer_rate_limit(admin, indexer, max_events_per_ledger)` lets the admin
cap how many events a given indexer may record in a single ledger. Passing
`max_events_per_ledger = 0` clears the limit, making the indexer unrestricted
again. `get_indexer_rate_limit(indexer)` returns the configured limit
(`None` if unrestricted), and `get_indexer_rate_usage(indexer)` returns the
number of events the indexer has already recorded in the current ledger.

`record_event` and `record_events_batch` both enforce the limit before
persisting new events, returning `ContractError::RateLimitExceeded` once an
indexer's per-ledger quota is exhausted. Usage counters reset automatically
when the ledger sequence advances.

The Python SDK exposes this as `set_indexer_rate_limit` /
`get_indexer_rate_limit`, backed by the Django endpoints
`POST /api/ingest/indexers/rate-limit/` and
`GET /api/ingest/indexers/<indexer>/rate-limit/`. The TypeScript SDK exposes
the equivalent `setIndexerRateLimit` / `getIndexerRateLimit` client methods.
The Python CLI exposes this as `soroscan indexers set-rate-limit` and
`soroscan indexers get-rate-limit`.

## Deploying to Testnet

```bash
soroban contract deploy \
  --wasm target/wasm32-unknown-unknown/release/soroscan_core.wasm \
  --source <YOUR_SECRET_KEY> \
  --rpc-url https://soroban-testnet.stellar.org \
  --network-passphrase "Test SDF Network ; September 2015"
```
