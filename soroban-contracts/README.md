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

## SC-37 structured event retraction

`retract_structured_event` lets an indexer soft-revoke a structured event it
previously recorded via `record_structured_event`, without deleting the
original record or freeing up its `correlation_id` for reuse. This is useful
when a chain reorg invalidates an event or an indexer discovers it submitted
bad data, and off-chain consumers need a signal to hide or annotate the event
while preserving audit history and idempotency guarantees.

- Only the original submitting indexer, or the contract admin, may call
  `retract_structured_event` for a given `correlation_id`.
- Retracting an unknown `correlation_id` fails with `StructuredEventNotFound`.
- Retracting an already-retracted event fails with `AlreadyRetracted`.
- `structured_by_correlation` continues to return the original event
  unchanged after retraction.
- `is_structured_event_retracted` and `get_retraction` let callers check
  retraction status and inspect who retracted an event, when, and why.

The Python and TypeScript SDKs expose this as `retract_structured_event` and
`retractStructuredEvent`; both submit to `POST /api/record/retract/`. The
Python SDK also exposes a `soroscan retract-event <correlation_id>` CLI
command.

## Deploying to Testnet

```bash
soroban contract deploy \
  --wasm target/wasm32-unknown-unknown/release/soroscan_core.wasm \
  --source <YOUR_SECRET_KEY> \
  --rpc-url https://soroban-testnet.stellar.org \
  --network-passphrase "Test SDF Network ; September 2015"
```
