"""SC-37 structured-event retraction SDK coverage."""

import json

import pytest
from pydantic import ValidationError
from pytest_httpx import HTTPXMock

from soroscan import AsyncSoroScanClient, SoroScanClient
from soroscan.models import RetractStructuredEventRequest


def test_retract_request_rejects_short_correlation_id() -> None:
    with pytest.raises(ValidationError):
        RetractStructuredEventRequest(correlation_id="a" * 63)


def test_retract_request_defaults_reason_to_unspecified() -> None:
    request = RetractStructuredEventRequest(correlation_id="b" * 64)
    assert request.reason == "unspecified"


def test_retract_structured_event(base_url: str, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{base_url}/api/record/retract/",
        status_code=202,
        json={"status": "submitted", "tx_hash": "abc", "transaction_status": "PENDING"},
    )
    with SoroScanClient(base_url=base_url) as client:
        result = client.retract_structured_event("b" * 64, reason="reorg")

    assert result.status == "submitted"
    assert result.tx_hash == "abc"
    request = httpx_mock.get_requests()[0]
    assert json.loads(request.content) == {
        "correlation_id": "b" * 64,
        "reason": "reorg",
    }


def test_retract_structured_event_default_reason(base_url: str, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{base_url}/api/record/retract/",
        status_code=202,
        json={"status": "submitted", "tx_hash": "abc", "transaction_status": "PENDING"},
    )
    with SoroScanClient(base_url=base_url) as client:
        client.retract_structured_event("c" * 64)

    request = httpx_mock.get_requests()[0]
    assert json.loads(request.content)["reason"] == "unspecified"


def test_retract_structured_event_failure(base_url: str, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{base_url}/api/record/retract/",
        status_code=202,
        json={
            "status": "failed",
            "error": "already retracted",
            "transaction_status": "FAILED",
        },
    )
    with SoroScanClient(base_url=base_url) as client:
        result = client.retract_structured_event("d" * 64)

    assert result.status == "failed"
    assert result.error == "already retracted"


@pytest.mark.anyio
async def test_async_retract_structured_event(base_url: str, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{base_url}/api/record/retract/",
        status_code=202,
        json={"status": "submitted", "tx_hash": "abc", "transaction_status": "PENDING"},
    )
    async with AsyncSoroScanClient(base_url=base_url) as client:
        result = await client.retract_structured_event("e" * 64, reason="bad_data")

    assert result.tx_hash == "abc"
    request = httpx_mock.get_requests()[0]
    assert json.loads(request.content) == {
        "correlation_id": "e" * 64,
        "reason": "bad_data",
    }
