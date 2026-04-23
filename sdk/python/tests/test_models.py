"""Tests for Pydantic models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from soroscan.models import (
    ContractEvent,
    ContractStats,
    PaginatedResponse,
    RecordEventRequest,
    TrackedContract,
    WebhookSubscription,
)


def test_tracked_contract_model(sample_contract_data: dict) -> None:
    """Test TrackedContract model validation."""
    contract = TrackedContract.model_validate(sample_contract_data)

    assert contract.id == 1
    assert contract.contract_id == "CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF"
    assert contract.name == "Test Token"
    assert contract.is_active is True
    assert contract.event_count == 42
    assert isinstance(contract.created_at, datetime)


def test_contract_event_model(sample_event_data: dict) -> None:
    """Test ContractEvent model validation."""
    event = ContractEvent.model_validate(sample_event_data)

    assert event.id == 1
    assert event.event_type == "transfer"
    assert event.ledger == 100000
    assert event.validation_status == "passed"
    assert isinstance(event.timestamp, datetime)
    assert isinstance(event.payload, dict)


def test_webhook_subscription_model(sample_webhook_data: dict) -> None:
    """Test WebhookSubscription model validation."""
    webhook = WebhookSubscription.model_validate(sample_webhook_data)

    assert webhook.id == 1
    assert webhook.contract == 1
    assert webhook.target_url == "https://example.com/webhook"
    assert webhook.is_active is True
    assert webhook.failure_count == 0


def test_contract_stats_model() -> None:
    """Test ContractStats model validation."""
    data = {
        "contract_id": "CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
        "name": "Test Token",
        "total_events": 100,
        "unique_event_types": 5,
        "latest_ledger": 100000,
        "last_activity": "2026-01-01T12:00:00Z",
    }

    stats = ContractStats.model_validate(data)

    assert stats.total_events == 100
    assert stats.unique_event_types == 5
    assert stats.latest_ledger == 100000
    assert isinstance(stats.last_activity, datetime)


def test_paginated_response_model(
    sample_contract_data: dict,
    sample_paginated_response: dict,
) -> None:
    """Test PaginatedResponse model validation."""
    response_data = sample_paginated_response.copy()
    response_data["results"] = [sample_contract_data]

    from pydantic import TypeAdapter

    adapter = TypeAdapter(PaginatedResponse[TrackedContract])
    response = adapter.validate_python(response_data)

    assert response.count == 100
    assert response.next == "https://api.test.soroscan.io/api/events/?page=2"
    assert response.previous is None
    assert len(response.results) == 1
    assert isinstance(response.results[0], TrackedContract)


def test_record_event_request_model() -> None:
    """Test RecordEventRequest model validation."""
    data = {
        "contract_id": "CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
        "event_type": "transfer",
        "payload_hash": "abc123def456",
    }

    request = RecordEventRequest.model_validate(data)

    assert request.contract_id == "CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF"
    assert request.event_type == "transfer"
    assert request.payload_hash == "abc123def456"


def test_model_validation_error() -> None:
    """Test model validation with invalid data."""
    invalid_data = {
        "id": "not_an_int",  # Should be int
        "contract_id": "CCAAA...",
        "name": "Test",
    }

    with pytest.raises(ValidationError):
        TrackedContract.model_validate(invalid_data)


def test_model_required_fields() -> None:
    """Test that required fields are enforced."""
    incomplete_data = {
        "id": 1,
        # Missing required fields
    }

    with pytest.raises(ValidationError):
        TrackedContract.model_validate(incomplete_data)


def test_model_default_values() -> None:
    """Test model default values."""
    minimal_data = {
        "id": 1,
        "contract_id": "CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
        "name": "Test",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }

    contract = TrackedContract.model_validate(minimal_data)

    assert contract.description == ""
    assert contract.is_active is True
    assert contract.event_count == 0
