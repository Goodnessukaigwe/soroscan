"""Pytest configuration and fixtures."""

from datetime import datetime, timedelta

import pytest


@pytest.fixture
def base_url() -> str:
    """Base URL for test API."""
    return "https://api.test.soroscan.io"


@pytest.fixture
def api_key() -> str:
    """Test API key."""
    return "test-api-key-12345"


@pytest.fixture
def sample_contract_data() -> dict:
    """Sample contract response data."""
    return {
        "id": 1,
        "contract_id": "CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
        "name": "Test Token",
        "description": "A test token contract",
        "abi_schema": None,
        "is_active": True,
        "last_indexed_ledger": 100000,
        "event_count": 42,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
    }


@pytest.fixture
def sample_event_data() -> dict:
    """Sample event response data."""
    return {
        "id": 1,
        "contract_id": "CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
        "contract_name": "Test Token",
        "event_type": "transfer",
        "payload": {"from": "GAAA...", "to": "GBBB...", "amount": "1000"},
        "payload_hash": "abc123def456",
        "ledger": 100000,
        "event_index": 0,
        "timestamp": "2026-01-01T12:00:00Z",
        "tx_hash": "tx123456",
        "schema_version": 1,
        "validation_status": "passed",
    }


@pytest.fixture
def sample_webhook_data() -> dict:
    """Sample webhook response data."""
    return {
        "id": 1,
        "contract": 1,
        "contract_id": "CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
        "event_type": "transfer",
        "target_url": "https://example.com/webhook",
        "is_active": True,
        "created_at": "2026-01-01T00:00:00Z",
        "last_triggered": None,
        "failure_count": 0,
    }


@pytest.fixture
def sample_paginated_response() -> dict:
    """Sample paginated response structure."""
    return {
        "count": 100,
        "next": "https://api.test.soroscan.io/api/events/?page=2",
        "previous": None,
        "results": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Soroban RPC Event Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def soroban_transfer_event() -> dict:
    """Mock Soroban transfer event JSON payload."""
    now = datetime.utcnow().isoformat() + "Z"
    return {
        "id": 101,
        "contract_id": "CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
        "contract_name": "Stellar USD",
        "event_type": "transfer",
        "payload": {
            "from": "GDZSTFXVV5FJ5LQHL5TWUC7PLUS4A3AFW4KX4HH4SJJNIBHCKPC5MEL",
            "to": "GBVVRXLMBTFBXVMAHQKQYKEDIYZGS5UYSQKTNQIAO7SEQEMM7KKBYZPL",
            "amount": "1000000000",
        },
        "payload_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "ledger": 150000,
        "event_index": 2,
        "timestamp": now,
        "tx_hash": "d1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        "schema_version": 1,
        "validation_status": "passed",
    }


@pytest.fixture
def soroban_mint_event() -> dict:
    """Mock Soroban mint event JSON payload."""
    now = datetime.utcnow().isoformat() + "Z"
    return {
        "id": 102,
        "contract_id": "CCBBB111222333444555666777888999AAABBBCCCDDDEEEFFF",
        "contract_name": "Test Token",
        "event_type": "mint",
        "payload": {
            "admin": "GDZSTFXVV5FJ5LQHL5TWUC7PLUS4A3AFW4KX4HH4SJJNIBHCKPC5MEL",
            "to": "GBVVRXLMBTFBXVMAHQKQYKEDIYZGS5UYSQKTNQIAO7SEQEMM7KKBYZPL",
            "amount": "5000000000",
        },
        "payload_hash": "2c26b46911185131006ba02f35e1d36cde8b347cd4f2f89802170831bb9e9f6e",
        "ledger": 150001,
        "event_index": 0,
        "timestamp": now,
        "tx_hash": "e1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        "schema_version": 1,
        "validation_status": "passed",
    }


@pytest.fixture
def soroban_burn_event() -> dict:
    """Mock Soroban burn event JSON payload."""
    now = datetime.utcnow().isoformat() + "Z"
    return {
        "id": 103,
        "contract_id": "CCBBB111222333444555666777888999AAABBBCCCDDDEEEFFF",
        "contract_name": "Test Token",
        "event_type": "burn",
        "payload": {
            "from": "GBVVRXLMBTFBXVMAHQKQYKEDIYZGS5UYSQKTNQIAO7SEQEMM7KKBYZPL",
            "amount": "1000000",
        },
        "payload_hash": "fcde2b2edba56bf408601fb721fe9b5348cc61f6f69f4ad3ff3ba5e1ef59d4f7",
        "ledger": 150002,
        "event_index": 1,
        "timestamp": now,
        "tx_hash": "f1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        "schema_version": 1,
        "validation_status": "passed",
    }


@pytest.fixture
def soroban_approve_event() -> dict:
    """Mock Soroban approve (allowance) event JSON payload."""
    now = datetime.utcnow().isoformat() + "Z"
    return {
        "id": 104,
        "contract_id": "CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
        "contract_name": "Stellar USD",
        "event_type": "approve",
        "payload": {
            "from": "GDZSTFXVV5FJ5LQHL5TWUC7PLUS4A3AFW4KX4HH4SJJNIBHCKPC5MEL",
            "spender": "GBVVRXLMBTFBXVMAHQKQYKEDIYZGS5UYSQKTNQIAO7SEQEMM7KKBYZPL",
            "current_allowance": "0",
            "new_allowance": "10000000000",
        },
        "payload_hash": "d4735fcea62e0f8f0b0e5b0f0b0e5b0f0b0e5b0f0b0e5b0f0b0e5b0f0b0e5b0",
        "ledger": 150003,
        "event_index": 0,
        "timestamp": now,
        "tx_hash": "a1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        "schema_version": 1,
        "validation_status": "passed",
    }


@pytest.fixture
def soroban_swap_event() -> dict:
    """Mock Soroban swap event JSON payload for DEX contract."""
    now = datetime.utcnow().isoformat() + "Z"
    return {
        "id": 105,
        "contract_id": "CCDDD111222333444555666777888999AAABBBCCCDDDEEEFFF",
        "contract_name": "Stellar DEX",
        "event_type": "swap",
        "payload": {
            "user": "GDZSTFXVV5FJ5LQHL5TWUC7PLUS4A3AFW4KX4HH4SJJNIBHCKPC5MEL",
            "token_in": "CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
            "token_out": "CCBBB111222333444555666777888999AAABBBCCCDDDEEEFFF",
            "amount_in": "1000000000",
            "amount_out": "950000000",
        },
        "payload_hash": "1b4f0e9851971998e732078544c11c82f590e44430672457b1df265b4ee3f50d",
        "ledger": 150004,
        "event_index": 1,
        "timestamp": now,
        "tx_hash": "b1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        "schema_version": 1,
        "validation_status": "passed",
    }


@pytest.fixture
def soroban_custom_event() -> dict:
    """Mock custom Soroban event JSON payload."""
    now = datetime.utcnow().isoformat() + "Z"
    return {
        "id": 106,
        "contract_id": "CCEEE111222333444555666777888999AAABBBCCCDDDEEEFFF",
        "contract_name": "Custom Contract",
        "event_type": "custom_action",
        "payload": {
            "actor": "GDZSTFXVV5FJ5LQHL5TWUC7PLUS4A3AFW4KX4HH4SJJNIBHCKPC5MEL",
            "action_type": "governance_vote",
            "proposal_id": 42,
            "vote": "yes",
            "weight": "5000000",
        },
        "payload_hash": "3e23e8160039594a33894f6564e1b1348bbd7a0088d42c4acb73eeaed59c009d",
        "ledger": 150005,
        "event_index": 0,
        "timestamp": now,
        "tx_hash": "c1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        "schema_version": 1,
        "validation_status": "passed",
    }


@pytest.fixture
def soroban_failed_event() -> dict:
    """Mock Soroban event with failed validation status."""
    now = datetime.utcnow().isoformat() + "Z"
    return {
        "id": 107,
        "contract_id": "CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
        "contract_name": "Stellar USD",
        "event_type": "transfer",
        "payload": {
            "from": "INVALID_ADDRESS",
            "to": "INVALID_ADDRESS",
            "amount": "999999999999999999999",
        },
        "payload_hash": "4d967a2a9637a0544750424099335183c0388d40eb2ff5ff471f8f5eee62a571",
        "ledger": 150006,
        "event_index": 1,
        "timestamp": now,
        "tx_hash": "d1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        "schema_version": 1,
        "validation_status": "failed",
    }


@pytest.fixture
def soroban_events_batch() -> list[dict]:
    """Mock batch of multiple Soroban events."""
    now = datetime.utcnow()
    events = []
    for i in range(5):
        events.append(
            {
                "id": 200 + i,
                "contract_id": "CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
                "contract_name": "Batch Contract",
                "event_type": f"event_type_{i}",
                "payload": {
                    "index": i,
                    "data": f"batch_data_{i}",
                    "timestamp": (now + timedelta(seconds=i)).isoformat() + "Z",
                },
                "payload_hash": f"{'0' * 63}{i}",
                "ledger": 150010 + i,
                "event_index": i,
                "timestamp": (now + timedelta(seconds=i)).isoformat() + "Z",
                "tx_hash": f"tx_batch_{i}",
                "schema_version": 1,
                "validation_status": "passed",
            }
        )
    return events

