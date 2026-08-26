import json

import pytest

from webhook_simulator.payload import (
    SAMPLE_EVENT,
    build_ping_payload,
    canonicalize,
    load_event_json,
    normalize_event,
)


def test_canonicalize_matches_production_json_dumps():
    payload_bytes = canonicalize(SAMPLE_EVENT)
    expected = json.dumps(SAMPLE_EVENT, sort_keys=True).encode("utf-8")
    assert payload_bytes == expected
    # Production uses default separators with spaces, not compact JSON.
    assert b": " in payload_bytes
    assert b", " in payload_bytes


def test_normalize_event_uses_sample_defaults():
    event = normalize_event({})
    assert event["contract_id"] == SAMPLE_EVENT["contract_id"]
    assert event["event_type"] == SAMPLE_EVENT["event_type"]
    assert event["payload"] == SAMPLE_EVENT["payload"]
    assert event["ledger"] == SAMPLE_EVENT["ledger"]
    assert event["event_index"] == SAMPLE_EVENT["event_index"]
    assert event["tx_hash"] == SAMPLE_EVENT["tx_hash"]


def test_normalize_event_accepts_full_envelope():
    event = normalize_event(
        {
            "contract_id": "CTESTCONTRACT",
            "event_type": "mint",
            "payload": {"amount": "1"},
            "ledger": 9,
            "event_index": 2,
            "tx_hash": "ab",
        }
    )
    assert event["event_type"] == "mint"
    assert event["ledger"] == 9
    assert event["payload"] == {"amount": "1"}


def test_normalize_event_wraps_raw_payload():
    event = normalize_event({"amount": 42, "from": "Alice"})
    assert event["payload"] == {"amount": 42, "from": "Alice"}
    assert event["event_type"] == SAMPLE_EVENT["event_type"]


def test_normalize_event_camel_case_aliases():
    event = normalize_event(
        {
            "contractId": "CCUSTOM",
            "eventType": "swap",
            "eventIndex": 3,
            "txHash": "deadbeef",
            "payload": {"ok": True},
            "ledger": 11,
        }
    )
    assert event["contract_id"] == "CCUSTOM"
    assert event["event_type"] == "swap"
    assert event["event_index"] == 3
    assert event["tx_hash"] == "deadbeef"


def test_normalize_event_applies_overrides():
    event = normalize_event(
        {"event_type": "mint", "payload": {}},
        overrides={"event_type": "burn", "ledger": 100},
    )
    assert event["event_type"] == "burn"
    assert event["ledger"] == 100


def test_normalize_event_rejects_non_object_payload():
    with pytest.raises(ValueError, match="payload must be a JSON object"):
        normalize_event({"event_type": "x", "payload": ["not", "an", "object"]})


def test_load_event_json_rejects_arrays():
    with pytest.raises(ValueError, match="JSON object"):
        load_event_json("[1, 2]")


def test_load_event_json_rejects_invalid_json():
    with pytest.raises(ValueError, match="Invalid JSON"):
        load_event_json("{nope")


def test_build_ping_payload():
    ping = build_ping_payload(timestamp="2026-01-01T00:00:00+00:00")
    assert ping == {"type": "ping", "timestamp": "2026-01-01T00:00:00+00:00"}
