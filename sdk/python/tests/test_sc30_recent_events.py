"""Tests for SC-30: per-contract recent events."""

import pytest
from pytest_httpx import HTTPXMock

from soroscan import AsyncSoroScanClient, SoroScanClient
from soroscan.models import ContractEvent

# ── Fixtures ──────────────────────────────────────────────────────────────────

CONTRACT_ID = "CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF"


def _event(event_type: str, ledger: int) -> dict:
    return {
        "id": ledger,
        "contract_id": CONTRACT_ID,
        "contract_name": "Test Contract",
        "event_type": event_type,
        "payload": {"amount": 100},
        "payload_hash": "a" * 64,
        "ledger": ledger,
        "event_index": 0,
        "timestamp": "2024-01-01T00:00:00Z",
        "tx_hash": "b" * 64,
        "schema_version": None,
        "validation_status": "passed",
    }


RECENT_EVENTS_RESPONSE = [_event("third", 102), _event("second", 101), _event("first", 100)]


# ── Sync client ───────────────────────────────────────────────────────────────


def test_get_contract_recent_events(base_url: str, httpx_mock: HTTPXMock) -> None:
    """get_contract_recent_events fetches from /api/contracts/<id>/recent-events/."""
    httpx_mock.add_response(
        url=f"{base_url}/api/contracts/{CONTRACT_ID}/recent-events/?limit=10",
        json=RECENT_EVENTS_RESPONSE,
    )

    with SoroScanClient(base_url=base_url) as client:
        events = client.get_contract_recent_events(CONTRACT_ID)

    assert len(events) == 3
    assert all(isinstance(e, ContractEvent) for e in events)
    assert [e.event_type for e in events] == ["third", "second", "first"]


def test_get_contract_recent_events_custom_limit(base_url: str, httpx_mock: HTTPXMock) -> None:
    """A custom limit is forwarded as a query parameter."""
    httpx_mock.add_response(
        url=f"{base_url}/api/contracts/{CONTRACT_ID}/recent-events/?limit=2",
        json=RECENT_EVENTS_RESPONSE[:2],
    )

    with SoroScanClient(base_url=base_url) as client:
        events = client.get_contract_recent_events(CONTRACT_ID, limit=2)

    assert len(events) == 2


def test_get_contract_recent_events_empty(base_url: str, httpx_mock: HTTPXMock) -> None:
    """An empty result set is a valid (non-error) response."""
    httpx_mock.add_response(
        url=f"{base_url}/api/contracts/{CONTRACT_ID}/recent-events/?limit=10",
        json=[],
    )

    with SoroScanClient(base_url=base_url) as client:
        events = client.get_contract_recent_events(CONTRACT_ID)

    assert events == []


def test_get_contract_recent_events_rejects_limit_too_low(base_url: str) -> None:
    with SoroScanClient(base_url=base_url) as client:
        with pytest.raises(ValueError):
            client.get_contract_recent_events(CONTRACT_ID, limit=0)


def test_get_contract_recent_events_rejects_limit_too_high(base_url: str) -> None:
    with SoroScanClient(base_url=base_url) as client:
        with pytest.raises(ValueError):
            client.get_contract_recent_events(CONTRACT_ID, limit=21)


def test_get_contract_recent_events_not_found(base_url: str, httpx_mock: HTTPXMock) -> None:
    from soroscan.exceptions import SoroScanNotFoundError

    httpx_mock.add_response(
        url=f"{base_url}/api/contracts/{CONTRACT_ID}/recent-events/?limit=10",
        json={"detail": "Not found."},
        status_code=404,
    )

    with SoroScanClient(base_url=base_url) as client:
        with pytest.raises(SoroScanNotFoundError):
            client.get_contract_recent_events(CONTRACT_ID)


# ── Async client ──────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_async_get_contract_recent_events(base_url: str, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{base_url}/api/contracts/{CONTRACT_ID}/recent-events/?limit=10",
        json=RECENT_EVENTS_RESPONSE,
    )

    async with AsyncSoroScanClient(base_url=base_url) as client:
        events = await client.get_contract_recent_events(CONTRACT_ID)

    assert len(events) == 3
    assert [e.event_type for e in events] == ["third", "second", "first"]


@pytest.mark.anyio
async def test_async_get_contract_recent_events_rejects_invalid_limit(base_url: str) -> None:
    async with AsyncSoroScanClient(base_url=base_url) as client:
        with pytest.raises(ValueError):
            await client.get_contract_recent_events(CONTRACT_ID, limit=100)
