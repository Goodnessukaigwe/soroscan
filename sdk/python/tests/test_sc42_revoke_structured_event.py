"""SC-42 structured-event revocation SDK coverage."""

import json

import pytest
from pydantic import ValidationError
from pytest_httpx import HTTPXMock

from soroscan import AsyncSoroScanClient, SoroScanClient
from soroscan.models import RevokeStructuredEventRequest


def test_revoke_request_rejects_short_correlation_id() -> None:
    with pytest.raises(ValidationError):
        RevokeStructuredEventRequest(correlation_id="a" * 63)


def test_revoke_structured_event(base_url: str, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{base_url}/api/record/structured/revoke/",
        status_code=202,
        json={"status": "submitted", "tx_hash": "abc", "transaction_status": "PENDING"},
    )
    with SoroScanClient(base_url=base_url) as client:
        result = client.revoke_structured_event("b" * 64)

    assert result.status == "submitted"
    assert result.tx_hash == "abc"
    request = httpx_mock.get_requests()[0]
    assert json.loads(request.content) == {"correlation_id": "b" * 64}


def test_revoke_structured_event_failure(base_url: str, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{base_url}/api/record/structured/revoke/",
        status_code=202,
        json={
            "status": "failed",
            "error": "already revoked",
            "transaction_status": "FAILED",
        },
    )
    with SoroScanClient(base_url=base_url) as client:
        result = client.revoke_structured_event("d" * 64)

    assert result.status == "failed"
    assert result.error == "already revoked"


@pytest.mark.anyio
async def test_async_revoke_structured_event(base_url: str, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{base_url}/api/record/structured/revoke/",
        status_code=202,
        json={"status": "submitted", "tx_hash": "abc", "transaction_status": "PENDING"},
    )
    async with AsyncSoroScanClient(base_url=base_url) as client:
        result = await client.revoke_structured_event("e" * 64)

    assert result.tx_hash == "abc"
