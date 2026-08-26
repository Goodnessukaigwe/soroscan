"""Build canonical webhook bodies matching Django ``dispatch_webhook``.

Production deliveries serialize this envelope with ``json.dumps(..., sort_keys=True)``
(default separators ``(', ', ': ')``) and POST the resulting UTF-8 bytes.

See ``django-backend/soroscan/ingest/tasks.py`` (``dispatch_webhook``).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

PRODUCTION_EVENT_FIELDS: tuple[str, ...] = (
    "contract_id",
    "event_type",
    "payload",
    "ledger",
    "event_index",
    "tx_hash",
)

_FIELD_ALIASES: dict[str, str] = {
    "contractId": "contract_id",
    "eventType": "event_type",
    "eventIndex": "event_index",
    "txHash": "tx_hash",
}

SAMPLE_EVENT: dict[str, Any] = {
    "contract_id": "CCAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "event_type": "transfer",
    "payload": {
        "from": "GABCDEFGHIJKLMNOPQRSTUVWXYZ234567AAAAAAAAAAAAAA",
        "to": "GABCDEFGHIJKLMNOPQRSTUVWXYZ234567BBBBBBBBBBBBBB",
        "amount": "10000000",
    },
    "ledger": 123456,
    "event_index": 0,
    "tx_hash": "b" * 64,
}


def canonicalize(event_data: Mapping[str, Any]) -> bytes:
    """Return the exact UTF-8 body bytes used for HMAC and HTTP POST."""
    return json.dumps(dict(event_data), sort_keys=True).encode("utf-8")


def utc_now_iso() -> str:
    """Timezone-aware UTC timestamp, matching Django ``timezone.now().isoformat()``."""
    return datetime.now(timezone.utc).isoformat()


def build_ping_payload(timestamp: str | None = None) -> dict[str, Any]:
    """Minimal ping body matching ``ingest.tasks.ping_webhook``."""
    return {"type": "ping", "timestamp": timestamp or utc_now_iso()}


def _coerce_int(value: Any, field: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer, not a boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    try:
        return int(str(value), 10)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer, got {value!r}") from exc


def _normalize_keys(data: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in data.items():
        normalized[_FIELD_ALIASES.get(key, key)] = value
    return normalized


def normalize_event(
    data: Mapping[str, Any] | None = None,
    *,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Normalize caller input into the production webhook envelope.

    Accepts a full event object, camelCase aliases, or a raw payload dict
    (which is placed under ``payload``). Missing envelope fields get
    sensible sample defaults so a partial JSON file still delivers.
    """
    raw = _normalize_keys(data or {})
    extra = _normalize_keys(overrides or {})
    if not raw:
        raw = dict(SAMPLE_EVENT)

    looks_like_envelope = any(key in raw for key in PRODUCTION_EVENT_FIELDS)
    if looks_like_envelope:
        payload = raw.get("payload", {})
        if payload is None:
            payload = {}
        if not isinstance(payload, Mapping):
            raise ValueError("payload must be a JSON object")
        envelope_source = raw
    else:
        payload = raw
        envelope_source = {}

    event: dict[str, Any] = {
        "contract_id": extra.get(
            "contract_id",
            envelope_source.get("contract_id", SAMPLE_EVENT["contract_id"]),
        ),
        "event_type": extra.get(
            "event_type",
            envelope_source.get("event_type", SAMPLE_EVENT["event_type"]),
        ),
        "payload": dict(extra["payload"]) if "payload" in extra else dict(payload),
        "ledger": extra.get("ledger", envelope_source.get("ledger", SAMPLE_EVENT["ledger"])),
        "event_index": extra.get(
            "event_index",
            envelope_source.get("event_index", SAMPLE_EVENT["event_index"]),
        ),
        "tx_hash": extra.get(
            "tx_hash",
            envelope_source.get("tx_hash", SAMPLE_EVENT["tx_hash"]),
        ),
    }

    event["ledger"] = _coerce_int(event["ledger"], "ledger")
    event["event_index"] = _coerce_int(event["event_index"], "event_index")
    if not isinstance(event["contract_id"], str) or not event["contract_id"]:
        raise ValueError("contract_id must be a non-empty string")
    if not isinstance(event["event_type"], str) or not event["event_type"]:
        raise ValueError("event_type must be a non-empty string")
    if event["tx_hash"] is None:
        event["tx_hash"] = SAMPLE_EVENT["tx_hash"]
    event["tx_hash"] = str(event["tx_hash"])
    return event


def load_event_json(text: str) -> dict[str, Any]:
    """Parse a JSON object from a string."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON event data: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Event data must be a JSON object")
    return data
