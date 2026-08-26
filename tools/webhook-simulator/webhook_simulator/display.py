"""Human-readable and JSON rendering of delivery results."""

from __future__ import annotations

import json
from typing import Any

from webhook_simulator.delivery import DeliveryAttempt, DeliveryResult


def result_to_dict(result: DeliveryResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "success": result.success,
        "http_status": result.http_status,
        "reason": result.reason,
        "latency_ms": result.latency_ms,
        "acknowledged": result.acknowledged,
        "ack_status": result.ack_status,
        "url": result.url,
        "payload_bytes": result.payload_bytes,
        "attempt_count": result.attempt_count,
        "error": result.error,
        "request_headers": result.request_headers,
        "response_headers": result.response_headers,
        "response_body": result.response_body,
        "payload": result.payload,
        "attempts": [_attempt_to_dict(item) for item in result.attempts],
    }


def _attempt_to_dict(attempt: DeliveryAttempt) -> dict[str, Any]:
    return {
        "attempt_number": attempt.attempt_number,
        "http_status": attempt.http_status,
        "latency_ms": attempt.latency_ms,
        "acknowledged": attempt.acknowledged,
        "ack_status": attempt.ack_status,
        "error": attempt.error,
        "response_body": attempt.response_body,
        "response_headers": attempt.response_headers,
    }


def format_text(result: DeliveryResult) -> str:
    status_label = result.status.upper()
    lines = [
        f"Delivery status:  {status_label}",
        f"Success:          {str(result.success).lower()}",
        f"HTTP status:      {result.http_status if result.http_status is not None else 'n/a'}",
        f"Reason:           {result.reason}",
        f"Latency:          {result.latency_ms} ms",
        f"Acknowledged:     {result.ack_status}",
        f"URL:              {result.url}",
        f"Payload bytes:    {result.payload_bytes}",
        f"Attempts:         {result.attempt_count}",
    ]
    signature = result.request_headers.get("X-SoroScan-Signature")
    if signature:
        lines.append(f"HMAC signature:   {signature}")
    ed25519 = result.request_headers.get("X-Signature")
    if ed25519:
        lines.append(f"Ed25519 header:   {ed25519}")
    timestamp = result.request_headers.get("X-SoroScan-Timestamp")
    if timestamp:
        lines.append(f"Timestamp:        {timestamp}")

    if result.response_headers:
        lines.append("")
        lines.append("Response headers:")
        for key, value in result.response_headers.items():
            lines.append(f"  {key}: {value}")

    if result.response_body:
        lines.append("")
        lines.append("Response body:")
        lines.append(result.response_body)

    if result.error and result.status != "success":
        lines.append("")
        lines.append(f"Error: {result.error}")

    if result.attempt_count > 1:
        lines.append("")
        lines.append("Attempt history:")
        for attempt in result.attempts:
            status = attempt.http_status if attempt.http_status is not None else "error"
            extra = f" error={attempt.error}" if attempt.error else ""
            lines.append(
                f"  #{attempt.attempt_number}: HTTP {status} "
                f"({attempt.latency_ms} ms, ack={attempt.ack_status}){extra}"
            )

    return "\n".join(lines)


def format_json(result: DeliveryResult) -> str:
    return json.dumps(result_to_dict(result), indent=2, sort_keys=True)


def format_dry_run(
    url: str,
    payload: dict[str, Any],
    payload_bytes: bytes,
    headers: dict[str, str],
    *,
    output: str = "text",
) -> str:
    data = {
        "dry_run": True,
        "url": url,
        "payload": payload,
        "payload_bytes": len(payload_bytes),
        "body": payload_bytes.decode("utf-8"),
        "headers": headers,
    }
    if output == "json":
        return json.dumps(data, indent=2, sort_keys=True)
    lines = [
        "Dry run — request was not sent.",
        f"URL:            {url}",
        f"Payload bytes:  {len(payload_bytes)}",
        "",
        "Headers:",
    ]
    for key, value in headers.items():
        lines.append(f"  {key}: {value}")
    lines.extend(["", "Body:", payload_bytes.decode("utf-8")])
    return "\n".join(lines)
