# soroscan_core

The core Soroban smart contract for SoroScan. It accepts event submissions from
authorized indexers, emits standardized events for off-chain consumption, and
maintains per-contract event counters and recent-event buffers.

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Rust | 1.74+ | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| `wasm32-unknown-unknown` target | — | `rustup target add wasm32-unknown-unknown` |
| Stellar CLI (`stellar`) | 21+ | See [Stellar CLI docs](https://developers.stellar.org/docs/tools/stellar-cli) |

> **Note:** The Stellar CLI was previously distributed as `soroban`. If you have
> an older installation, replace `stellar` with `soroban` in the commands below.

---

## Building

### 1. Compile to WASM

Run from the `soroscan_core/` directory:

```bash
cargo build --target wasm32-unknown-unknown --release
```

The compiled binary is placed at:

```
target/wasm32-unknown-unknown/release/soroscan_core.wasm
```

### 2. Optimize the WASM binary (recommended)

The `Cargo.toml` release profile already applies size optimizations
(`opt-level = "z"`, `lto = true`, `strip = "symbols"`). For an additional
size reduction you can run the Stellar CLI optimizer:

```bash
stellar contract optimize \
  --wasm target/wasm32-unknown-unknown/release/soroscan_core.wasm
```

This produces an optimized file alongside the original:

```
target/wasm32-unknown-unknown/release/soroscan_core.optimized.wasm
```

---

## Running Tests

```bash
cargo test
```

All tests use `soroban-sdk`'s `testutils` feature (`Env::default()`,
`register_contract`, `mock_all_auths`) and run entirely off-chain — no network
connection is required.

---

## Deploying

### Testnet

```bash
stellar contract deploy \
  --wasm target/wasm32-unknown-unknown/release/soroscan_core.wasm \
  --source <YOUR_SECRET_KEY_OR_ALIAS> \
  --network testnet
```

Stellar CLI resolves `--network testnet` automatically when you have configured
it via `stellar network add`. To configure it manually:

```bash
stellar network add testnet \
  --rpc-url https://soroban-testnet.stellar.org \
  --network-passphrase "Test SDF Network ; September 2015"
```

### Futurenet / Custom RPC

```bash
stellar contract deploy \
  --wasm target/wasm32-unknown-unknown/release/soroscan_core.wasm \
  --source <YOUR_SECRET_KEY_OR_ALIAS> \
  --rpc-url <RPC_URL> \
  --network-passphrase "<NETWORK_PASSPHRASE>"
```

A successful deploy prints the new **contract ID** (a `C…` address). Copy it
into your environment configuration:

```bash
# django-backend/.env
SOROSCAN_CONTRACT_ID=CXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

### Initializing the contract

After deployment, call `initialize` to set the contract admin:

```bash
stellar contract invoke \
  --id <CONTRACT_ID> \
  --source <YOUR_SECRET_KEY_OR_ALIAS> \
  --network testnet \
  -- \
  initialize \
  --admin <ADMIN_ADDRESS>
```

---

## Quick Reference

```bash
# 1. Add the WASM target (once)
rustup target add wasm32-unknown-unknown

# 2. Build
cargo build --target wasm32-unknown-unknown --release

# 3. (Optional) Optimize
stellar contract optimize \
  --wasm target/wasm32-unknown-unknown/release/soroscan_core.wasm

# 4. Deploy to testnet
stellar contract deploy \
  --wasm target/wasm32-unknown-unknown/release/soroscan_core.wasm \
  --source <YOUR_SECRET_KEY_OR_ALIAS> \
  --network testnet

# 5. Initialize
stellar contract invoke \
  --id <CONTRACT_ID> \
  --source <YOUR_SECRET_KEY_OR_ALIAS> \
  --network testnet \
  -- initialize --admin <ADMIN_ADDRESS>
```

---

## Related

- [Soroban Contracts README](../README.md) — workspace-level build and test overview
- [SoroScan Django Backend](../../django-backend/) — ingestion layer and API
- [Stellar CLI documentation](https://developers.stellar.org/docs/tools/stellar-cli)
- [Soroban SDK documentation](https://developers.stellar.org/docs/smart-contracts)
