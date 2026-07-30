"""Tests for the SC-30 `contracts recent-events` CLI command."""

import json

import pytest
from pytest_httpx import HTTPXMock

from soroscan.cli import build_parser, main

CONTRACT_ID = "CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF"

RECENT_EVENTS_RESPONSE = [
    {
        "id": 2,
        "contract_id": CONTRACT_ID,
        "contract_name": "Test Contract",
        "event_type": "swap",
        "payload": {"amount": 100},
        "payload_hash": "a" * 64,
        "ledger": 102,
        "event_index": 0,
        "timestamp": "2024-01-01T00:00:00Z",
        "tx_hash": "b" * 64,
        "schema_version": None,
        "validation_status": "passed",
    },
    {
        "id": 1,
        "contract_id": CONTRACT_ID,
        "contract_name": "Test Contract",
        "event_type": "transfer",
        "payload": {"amount": 50},
        "payload_hash": "c" * 64,
        "ledger": 101,
        "event_index": 0,
        "timestamp": "2024-01-01T00:00:00Z",
        "tx_hash": "d" * 64,
        "schema_version": None,
        "validation_status": "passed",
    },
]


# ── Parser tests (no HTTP needed) ────────────────────────────────────────────

class TestRecentEventsParser:
    def test_recent_events_subcommand_exists(self):
        parser = build_parser()
        args = parser.parse_args(["contracts", "recent-events", CONTRACT_ID])
        assert args.contract_id == CONTRACT_ID
        assert args.limit == 10
        assert args.output == "table"

    def test_recent_events_custom_limit(self):
        parser = build_parser()
        args = parser.parse_args(
            ["contracts", "recent-events", CONTRACT_ID, "--limit", "5"]
        )
        assert args.limit == 5

    def test_recent_events_missing_contract_id_exits(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["contracts", "recent-events"])


# ── Integration tests (HTTP mocked) ──────────────────────────────────────────

class TestRecentEventsCLI:
    def test_recent_events_table_output(
        self,
        base_url: str,
        httpx_mock: HTTPXMock,
        capsys,
    ) -> None:
        httpx_mock.add_response(
            url=f"{base_url}/api/contracts/{CONTRACT_ID}/recent-events/?limit=10",
            json=RECENT_EVENTS_RESPONSE,
        )

        exit_code = main(
            ["--base-url", base_url, "contracts", "recent-events", CONTRACT_ID]
        )

        assert exit_code == 0
        output = capsys.readouterr().out
        assert "swap" in output
        assert "transfer" in output

    def test_recent_events_json_output(
        self,
        base_url: str,
        httpx_mock: HTTPXMock,
        capsys,
    ) -> None:
        httpx_mock.add_response(
            url=f"{base_url}/api/contracts/{CONTRACT_ID}/recent-events/?limit=5",
            json=RECENT_EVENTS_RESPONSE,
        )

        exit_code = main(
            [
                "--base-url", base_url,
                "contracts", "recent-events", CONTRACT_ID,
                "--limit", "5",
                "--output", "json",
            ]
        )

        assert exit_code == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 2
        assert data[0]["event_type"] == "swap"

    def test_recent_events_api_error_prints_to_stderr(
        self,
        base_url: str,
        httpx_mock: HTTPXMock,
        capsys,
    ) -> None:
        httpx_mock.add_response(
            url=f"{base_url}/api/contracts/{CONTRACT_ID}/recent-events/?limit=10",
            json={"detail": "Not found."},
            status_code=404,
        )

        exit_code = main(
            ["--base-url", base_url, "contracts", "recent-events", CONTRACT_ID]
        )

        assert exit_code == 1
        assert "Error" in capsys.readouterr().err
