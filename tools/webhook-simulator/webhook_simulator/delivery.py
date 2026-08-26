"""HTTP delivery of simulated webhook payloads."""

from __future__ import annotations

import http.client
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_ACK_HEADER = "X-SoroScan-Ack"
DEFAULT_ACK_VALUE = "ok"
RESPONSE_BODY_LIMIT = 4096
BACKOFF_EXPONENTIAL = "exponential"
BACKOFF_LINEAR = "linear"
BACKOFF_FIXED = "fixed"


@dataclass
class DeliveryAttempt:
    """One HTTP POST attempt."""

    attempt_number: int
    http_status: int | None
    latency_ms: int
    acknowledged: bool
    ack_status: str
    error: str | None = None
    response_body: str = ""
    response_headers: dict[str, str] = field(default_factory=dict)


@dataclass
class DeliveryResult:
    """Aggregate result shown to the user after one or more attempts."""

    url: str
    status: str
    http_status: int | None
    reason: str
    latency_ms: int
    acknowledged: bool
    ack_status: str
    success: bool
    payload: dict[str, Any]
    payload_bytes: int
    request_headers: dict[str, str]
    response_headers: dict[str, str]
    response_body: str
    error: str | None
    attempt_count: int
    attempts: list[DeliveryAttempt]


def calculate_backoff(attempt: int, strategy: str, base_seconds: int) -> int:
    """
    Retry delay in seconds. ``attempt`` is 0-based (first retry = 0).

    Mirrors ``ingest.tasks.calculate_backoff``.
    """
    if strategy == BACKOFF_LINEAR:
        return base_seconds * (attempt + 1)
    if strategy == BACKOFF_FIXED:
        return base_seconds
    return base_seconds * (2**attempt)


def validate_ack(
    response_headers: Mapping[str, str],
    *,
    header_name: str = DEFAULT_ACK_HEADER,
    expected_value: str = DEFAULT_ACK_VALUE,
) -> tuple[bool, str]:
    """
    Return ``(acknowledged, status)`` where status is valid | missing | invalid.

    Header lookup is case-insensitive. Matches ``_validate_webhook_ack``.
    """
    name = (header_name or DEFAULT_ACK_HEADER).strip()
    expected = (expected_value or DEFAULT_ACK_VALUE).strip()
    received: str | None = None
    for key, value in response_headers.items():
        if key.lower() == name.lower():
            received = value
            break
    if received is None:
        return (False, "missing")
    if received.strip().lower() != expected.lower():
        return (False, "invalid")
    return (True, "valid")


def _truncate_body(body: bytes | str) -> str:
    if isinstance(body, bytes):
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            text = body.decode("utf-8", errors="replace")
    else:
        text = body
    encoded = text.encode("utf-8")
    if len(encoded) > RESPONSE_BODY_LIMIT:
        return encoded[:RESPONSE_BODY_LIMIT].decode("utf-8", errors="replace") + "…"
    return text


def _post_once(
    url: str,
    payload_bytes: bytes,
    headers: Mapping[str, str],
    timeout: float,
) -> tuple[int, dict[str, str], bytes]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Target URL must be http:// or https://")
    if not parsed.hostname:
        raise ValueError("Target URL is missing a hostname")

    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    connection_cls = (
        http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    )
    connection = connection_cls(parsed.hostname, parsed.port, timeout=timeout)
    try:
        connection.request("POST", path, body=payload_bytes, headers=dict(headers))
        response = connection.getresponse()
        body = response.read()
        response_headers = {key: value for key, value in response.getheaders()}
        return int(response.status), response_headers, body
    finally:
        connection.close()


def deliver(
    url: str,
    payload_bytes: bytes,
    headers: Mapping[str, str],
    *,
    payload: dict[str, Any],
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    retries: int = 0,
    backoff_strategy: str = BACKOFF_EXPONENTIAL,
    backoff_base: int = 2,
    ack_header: str = DEFAULT_ACK_HEADER,
    ack_value: str = DEFAULT_ACK_VALUE,
    require_ack: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> DeliveryResult:
    """
    POST ``payload_bytes`` to ``url`` and collect delivery status.

    ``retries`` is the number of *additional* attempts after the first (production
    Celery task uses ``max_retries=5``). Success is HTTP 2xx, and — when
    ``require_ack`` is set — a matching acknowledgement header.
    """
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("Target URL must be http:// or https://")

    attempts: list[DeliveryAttempt] = []
    total_tries = max(1, retries + 1)
    last_error: str | None = None

    for index in range(total_tries):
        attempt_number = index + 1
        started = time.monotonic()
        http_status: int | None = None
        response_headers: dict[str, str] = {}
        response_body = ""
        error: str | None = None

        try:
            http_status, response_headers, raw_body = _post_once(
                url, payload_bytes, headers, timeout
            )
            response_body = _truncate_body(raw_body)
        except TimeoutError:
            error = f"Request timed out after {timeout}s"
        except OSError as exc:
            error = f"Connection error: {exc}"

        latency_ms = int((time.monotonic() - started) * 1000)
        acknowledged = False
        ack_status = "skipped"
        if http_status is not None:
            acknowledged, ack_status = validate_ack(
                response_headers, header_name=ack_header, expected_value=ack_value
            )

        http_ok = http_status is not None and 200 <= http_status < 300
        success = http_ok and (acknowledged if require_ack else True)
        if error is None and not http_ok:
            error = f"HTTP {http_status}" if http_status is not None else "No response"
        if error is None and http_ok and require_ack and not acknowledged:
            error = (
                f"Missing or invalid acknowledgement header "
                f"'{ack_header}: {ack_value}'"
            )

        attempt = DeliveryAttempt(
            attempt_number=attempt_number,
            http_status=http_status,
            latency_ms=latency_ms,
            acknowledged=acknowledged,
            ack_status=ack_status,
            error=error,
            response_body=response_body,
            response_headers=response_headers,
        )
        attempts.append(attempt)
        last_error = error

        if success:
            return _result_from_attempt(
                url=url,
                payload=payload,
                payload_bytes=len(payload_bytes),
                request_headers=dict(headers),
                attempts=attempts,
                success=True,
                status="success",
                reason="Delivered",
            )

        if index < total_tries - 1:
            delay = calculate_backoff(index, backoff_strategy, backoff_base)
            sleep(delay)

    last = attempts[-1]
    status = "failed"
    reason = last_error or "Delivery failed"
    if last.http_status is None:
        status = "error"
    return _result_from_attempt(
        url=url,
        payload=payload,
        payload_bytes=len(payload_bytes),
        request_headers=dict(headers),
        attempts=attempts,
        success=False,
        status=status,
        reason=reason,
    )


def _result_from_attempt(
    *,
    url: str,
    payload: dict[str, Any],
    payload_bytes: int,
    request_headers: dict[str, str],
    attempts: list[DeliveryAttempt],
    success: bool,
    status: str,
    reason: str,
) -> DeliveryResult:
    last = attempts[-1]
    return DeliveryResult(
        url=url,
        status=status,
        http_status=last.http_status,
        reason=reason,
        latency_ms=last.latency_ms,
        acknowledged=last.acknowledged,
        ack_status=last.ack_status,
        success=success,
        payload=payload,
        payload_bytes=payload_bytes,
        request_headers=request_headers,
        response_headers=last.response_headers,
        response_body=last.response_body,
        error=last.error,
        attempt_count=len(attempts),
        attempts=attempts,
    )
