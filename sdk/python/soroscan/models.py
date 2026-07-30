"""Pydantic models for SoroScan API responses."""

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class TrackedContract(BaseModel):
    """Represents a tracked Soroban contract."""

    id: int
    contract_id: str = Field(..., description="Stellar contract address (C...)")
    name: str = Field(..., description="Human-readable contract name")
    description: str = Field(default="", description="Optional description")
    abi_schema: dict[str, Any] | None = Field(None, description="Optional ABI/schema")
    is_active: bool = Field(default=True, description="Whether indexing is active")
    last_indexed_ledger: int | None = Field(None, description="Last indexed ledger sequence")
    event_count: int = Field(default=0, description="Total number of events")
    created_at: datetime
    updated_at: datetime


class ContractEvent(BaseModel):
    """Represents an indexed contract event."""

    id: int
    contract_id: str = Field(..., description="Contract address that emitted the event")
    contract_name: str = Field(..., description="Contract name")
    event_type: str = Field(..., description="Event type/name (e.g., 'swap', 'transfer')")
    payload: dict[str, Any] = Field(..., description="Decoded event payload")
    payload_hash: str = Field(..., description="SHA-256 hash of the payload")
    ledger: int = Field(..., description="Ledger sequence number")
    event_index: int = Field(default=0, description="Event index within the ledger")
    timestamp: datetime = Field(..., description="Event timestamp")
    tx_hash: str = Field(..., description="Transaction hash")
    schema_version: int | None = Field(None, description="Schema version used for validation")
    validation_status: str = Field(default="passed", description="Validation result")


class WebhookSubscription(BaseModel):
    """Represents a webhook subscription."""

    id: int
    contract: int = Field(..., description="Contract ID")
    contract_id: str = Field(..., description="Contract address")
    event_type: str = Field(default="", description="Event type filter (empty = all events)")
    target_url: str = Field(..., description="URL to POST event data to")
    is_active: bool = Field(default=True, description="Whether webhook is active")
    created_at: datetime
    last_triggered: datetime | None = Field(None, description="Last trigger timestamp")
    failure_count: int = Field(default=0, description="Number of consecutive failures")


class ContractStats(BaseModel):
    """Aggregate statistics for a contract."""

    contract_id: str
    name: str
    total_events: int
    unique_event_types: int
    latest_ledger: int | None = None
    last_activity: datetime | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""

    count: int = Field(..., description="Total number of items")
    next: str | None = Field(None, description="URL to next page")
    previous: str | None = Field(None, description="URL to previous page")
    results: list[T] = Field(..., description="Page results")


class RecordEventRequest(BaseModel):
    """Request model for recording a new event."""

    contract_id: str = Field(..., max_length=56, description="Target contract address")
    event_type: str = Field(..., max_length=100, description="Event type name")
    payload_hash: str = Field(..., max_length=64, description="SHA-256 hash of payload (hex)")


class RecordEventResponse(BaseModel):
    """Response from recording an event."""

    status: str = Field(..., description="Submission status")
    tx_hash: str | None = Field(None, description="Transaction hash")
    transaction_status: str | None = Field(None, description="Transaction status")
    error: str | None = Field(None, description="Error message if failed")


# ── SC-38: Structured event recording ─────────────────────────────────────────

class StructuredEventRequest(BaseModel):
    """Request model for recording an SC-38 structured event."""

    contract_id: str = Field(..., max_length=56, description="Target contract address")
    event_type: str = Field(..., max_length=100, description="Event type name")
    payload_hash: str = Field(..., max_length=64, description="SHA-256 hash of payload (hex)")
    schema_version: int = Field(..., ge=1, description="Payload schema version (must be >= 1)")
    correlation_id: str = Field(
        ..., max_length=64, min_length=64, description="SHA-256-sized hex correlation ID"
    )


class StructuredEventResponse(BaseModel):
    """Response from recording an SC-38 structured event."""

    status: str = Field(..., description="Submission status")
    tx_hash: str | None = Field(None, description="Transaction hash")
    transaction_status: str | None = Field(None, description="Transaction status")
    error: str | None = Field(None, description="Error message if failed")


# ── SC-42: Structured event revocation ────────────────────────────────────────

class RevokeStructuredEventRequest(BaseModel):
    """Request model to revoke a previously recorded SC-38 structured event (SC-42)."""

    correlation_id: str = Field(
        ..., max_length=64, min_length=64, description="SHA-256-sized hex correlation ID"
    )


class RevokeStructuredEventResponse(BaseModel):
    """Response from revoking a structured event (SC-42)."""

    status: str = Field(..., description="Submission status")
    tx_hash: str | None = Field(None, description="Transaction hash")
    transaction_status: str | None = Field(None, description="Transaction status")
    error: str | None = Field(None, description="Error message if failed")


# ── SC-17: Contract event type info ───────────────────────────────────────────

class ContractEventTypeInfo(BaseModel):
    """Event type summary for a contract (SC-17)."""

    event_type: str = Field(..., description="Event type name")
    count: int = Field(..., description="Number of events of this type")
    first_seen: str = Field(..., description="ISO timestamp of first occurrence")
    last_seen: str = Field(..., description="ISO timestamp of last occurrence")


# ── SC-29: Batch event recording ──────────────────────────────────────────────

class EventEntry(BaseModel):
    """A single event entry for batch recording (SC-29)."""

    contract_id: str = Field(..., max_length=56, description="Target contract address")
    event_type: str = Field(..., max_length=100, description="Event type name")
    payload_hash: str = Field(..., max_length=64, description="SHA-256 hash of payload (hex)")


class RecordEventsBatchRequest(BaseModel):
    """Request model for batch event recording (SC-29). Max 25 entries."""

    events: list[EventEntry] = Field(..., min_length=1, max_length=25)


class RecordEventsBatchResponse(BaseModel):
    """Response from batch event recording (SC-29)."""

    status: str = Field(..., description="Submission status")
    total_events: int = Field(..., description="New total event count after batch")
    tx_hash: str | None = Field(None, description="Transaction hash")
    transaction_status: str | None = Field(None, description="Transaction status")
    error: str | None = Field(None, description="Error message if failed")
