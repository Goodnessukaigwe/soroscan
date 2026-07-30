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

## SC-42 structured event revocation

`revoke_structured_event` lets an authorized, active indexer permanently mark a
previously recorded SC-38 structured event as revoked. The original record is
kept for audit purposes; the on-chain `revoked` flag and a `sc42`/`revoke`
contract event signal off-chain consumers to treat the event as invalid.

- Revoking an unknown `correlation_id` fails with `StructuredEventNotFound`.
- Revoking an already-revoked event fails with `AlreadyRevoked`.
- A paused indexer cannot revoke (`IndexerPaused`).
- `is_structured_event_revoked` returns whether a known event has been revoked.
- When the revoked event is the latest for its type, the
  `LatestStructuredByType` projection is updated in place.

The Python and TypeScript SDKs expose this as `revoke_structured_event` and
`revokeStructuredEvent`; both submit to `POST /api/record/structured/revoke/`.
The Python SDK also exposes a
`soroscan revoke-structured-event <correlation_id>` CLI command.

## Deploying to Testnet

```bash
soroban contract deploy \
  --wasm target/wasm32-unknown-unknown/release/soroscan_core.wasm \
  --source <YOUR_SECRET_KEY> \
  --rpc-url https://soroban-testnet.stellar.org \
  --network-passphrase "Test SDF Network ; September 2015"
```
