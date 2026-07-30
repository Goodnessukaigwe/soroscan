"""Tests for SC-26: indexer per-ledger rate limiting."""

import pytest
from pytest_httpx import HTTPXMock

from soroscan import AsyncSoroScanClient, SoroScanClient
from soroscan.models import IndexerRateLimit, SetIndexerRateLimitResponse


INDEXER = "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF"

SET_RATE_LIMIT_RESPONSE = {
    "status": "submitted",
    "tx_hash": "txratelimit001",
    "transaction_status": "pending",
    "error": None,
}


# ── Sync client ───────────────────────────────────────────────────────────────


def test_set_indexer_rate_limit(base_url: str, httpx_mock: HTTPXMock) -> None:
    """set_indexer_rate_limit posts to the indexers/rate-limit endpoint."""
    httpx_mock.add_response(
        url=f"{base_url}/api/ingest/indexers/rate-limit/",
        method="POST",
        json=SET_RATE_LIMIT_RESPONSE,
        status_code=202,
    )

    with SoroScanClient(base_url=base_url) as client:
        result = client.set_indexer_rate_limit(indexer=INDEXER, max_events_per_ledger=100)

    assert isinstance(result, SetIndexerRateLimitResponse)
    assert result.status == "submitted"
    assert result.tx_hash == "txratelimit001"
    assert result.error is None

    request = httpx_mock.get_requests()[0]
    assert request.method == "POST"
    import json as _json

    body = _json.loads(request.content)
    assert body["indexer"] == INDEXER
    assert body["max_events_per_ledger"] == 100


def test_set_indexer_rate_limit_clear(base_url: str, httpx_mock: HTTPXMock) -> None:
    """Passing 0 clears the limit."""
    httpx_mock.add_response(
        url=f"{base_url}/api/ingest/indexers/rate-limit/",
        method="POST",
        json=SET_RATE_LIMIT_RESPONSE,
        status_code=202,
    )

    with SoroScanClient(base_url=base_url) as client:
        result = client.set_indexer_rate_limit(indexer=INDEXER, max_events_per_ledger=0)

    assert result.status == "submitted"


def test_get_indexer_rate_limit(base_url: str, httpx_mock: HTTPXMock) -> None:
    """get_indexer_rate_limit reads the configured limit."""
    httpx_mock.add_response(
        url=f"{base_url}/api/ingest/indexers/{INDEXER}/rate-limit/",
        method="GET",
        json={"indexer": INDEXER, "max_events_per_ledger": 50},
        status_code=200,
    )

    with SoroScanClient(base_url=base_url) as client:
        result = client.get_indexer_rate_limit(indexer=INDEXER)

    assert isinstance(result, IndexerRateLimit)
    assert result.indexer == INDEXER
    assert result.max_events_per_ledger == 50


def test_get_indexer_rate_limit_unrestricted(base_url: str, httpx_mock: HTTPXMock) -> None:
    """An indexer with no configured limit returns None."""
    httpx_mock.add_response(
        url=f"{base_url}/api/ingest/indexers/{INDEXER}/rate-limit/",
        method="GET",
        json={"indexer": INDEXER, "max_events_per_ledger": None},
        status_code=200,
    )

    with SoroScanClient(base_url=base_url) as client:
        result = client.get_indexer_rate_limit(indexer=INDEXER)

    assert result.max_events_per_ledger is None


def test_set_indexer_rate_limit_validation_error() -> None:
    """Negative limits are rejected client-side."""
    from pydantic import ValidationError

    from soroscan.models import SetIndexerRateLimitRequest

    with pytest.raises(ValidationError):
        SetIndexerRateLimitRequest(indexer=INDEXER, max_events_per_ledger=-1)


def test_set_indexer_rate_limit_unauthorized(base_url: str, httpx_mock: HTTPXMock) -> None:
    """Non-admin callers get a SoroScanAuthError."""
    from soroscan.exceptions import SoroScanAuthError

    httpx_mock.add_response(
        url=f"{base_url}/api/ingest/indexers/rate-limit/",
        method="POST",
        json={"detail": "Not authorized"},
        status_code=403,
    )

    with SoroScanClient(base_url=base_url) as client:
        with pytest.raises(SoroScanAuthError):
            client.set_indexer_rate_limit(indexer=INDEXER, max_events_per_ledger=10)


# ── Async client ──────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_async_set_indexer_rate_limit(base_url: str, httpx_mock: HTTPXMock) -> None:
    """Async set_indexer_rate_limit posts correctly and returns response."""
    httpx_mock.add_response(
        url=f"{base_url}/api/ingest/indexers/rate-limit/",
        method="POST",
        json=SET_RATE_LIMIT_RESPONSE,
        status_code=202,
    )

    async with AsyncSoroScanClient(base_url=base_url) as client:
        result = await client.set_indexer_rate_limit(indexer=INDEXER, max_events_per_ledger=100)

    assert isinstance(result, SetIndexerRateLimitResponse)
    assert result.status == "submitted"


@pytest.mark.anyio
async def test_async_get_indexer_rate_limit(base_url: str, httpx_mock: HTTPXMock) -> None:
    """Async get_indexer_rate_limit reads the configured limit."""
    httpx_mock.add_response(
        url=f"{base_url}/api/ingest/indexers/{INDEXER}/rate-limit/",
        method="GET",
        json={"indexer": INDEXER, "max_events_per_ledger": 25},
        status_code=200,
    )

    async with AsyncSoroScanClient(base_url=base_url) as client:
        result = await client.get_indexer_rate_limit(indexer=INDEXER)

    assert result.max_events_per_ledger == 25
