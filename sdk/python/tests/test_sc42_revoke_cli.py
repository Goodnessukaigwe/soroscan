"""Tests for the SC-38 record-structured-event and SC-42 revoke-structured-event CLI commands."""

import json

import pytest
from pytest_httpx import HTTPXMock

from soroscan.cli import main, build_parser


BASE_CONTRACT = "CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF"
EVENT_TYPE = "transfer"
PAYLOAD_HASH = "a" * 64
SCHEMA_VERSION = "1"
CORRELATION_ID = "b" * 64

SUBMITTED_RESPONSE = {
    "status": "submitted",
    "tx_hash": "txabc123",
    "transaction_status": "PENDING",
    "error": None,
}


# ── Parser tests (no HTTP needed) ────────────────────────────────────────────

class TestRecordStructuredEventParser:
    def test_record_structured_event_subcommand_exists(self):
        parser = build_parser()
        args = parser.parse_args([
            "record-structured-event",
            BASE_CONTRACT,
            EVENT_TYPE,
            PAYLOAD_HASH,
            SCHEMA_VERSION,
            CORRELATION_ID,
        ])
        assert args.contract_id == BASE_CONTRACT
        assert args.event_type == EVENT_TYPE
        assert args.payload_hash == PAYLOAD_HASH
        assert args.schema_version == 1
        assert args.correlation_id == CORRELATION_ID
        assert args.output == "table"

    def test_record_structured_event_missing_args_exits(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["record-structured-event", BASE_CONTRACT])


class TestRevokeStructuredEventParser:
    def test_revoke_structured_event_subcommand_exists(self):
        parser = build_parser()
        args = parser.parse_args(["revoke-structured-event", CORRELATION_ID])
        assert args.correlation_id == CORRELATION_ID
        assert args.output == "table"

    def test_revoke_structured_event_json_flag(self):
        parser = build_parser()
        args = parser.parse_args([
            "revoke-structured-event", CORRELATION_ID, "--output", "json",
        ])
        assert args.output == "json"

    def test_revoke_structured_event_missing_args_exits(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["revoke-structured-event"])


# ── Integration tests (HTTP mocked) ──────────────────────────────────────────

class TestRecordStructuredEventCLI:
    def test_record_structured_event_table_output(
        self, base_url: str, httpx_mock: HTTPXMock, capsys
    ) -> None:
        httpx_mock.add_response(
            url=f"{base_url}/api/record/structured/",
            method="POST",
            json=SUBMITTED_RESPONSE,
            status_code=202,
        )

        exit_code = main([
            "--base-url", base_url,
            "record-structured-event",
            BASE_CONTRACT,
            EVENT_TYPE,
            PAYLOAD_HASH,
            SCHEMA_VERSION,
            CORRELATION_ID,
        ])

        assert exit_code == 0
        output = capsys.readouterr().out
        assert "submitted" in output
        assert "txabc123" in output

    def test_record_structured_event_json_output(
        self, base_url: str, httpx_mock: HTTPXMock, capsys
    ) -> None:
        httpx_mock.add_response(
            url=f"{base_url}/api/record/structured/",
            method="POST",
            json=SUBMITTED_RESPONSE,
            status_code=202,
        )

        exit_code = main([
            "--base-url", base_url,
            "record-structured-event",
            BASE_CONTRACT,
            EVENT_TYPE,
            PAYLOAD_HASH,
            SCHEMA_VERSION,
            CORRELATION_ID,
            "--output", "json",
        ])

        assert exit_code == 0
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "submitted"
        assert data["tx_hash"] == "txabc123"


class TestRevokeStructuredEventCLI:
    def test_revoke_structured_event_table_output(
        self, base_url: str, httpx_mock: HTTPXMock, capsys
    ) -> None:
        httpx_mock.add_response(
            url=f"{base_url}/api/record/structured/revoke/",
            method="POST",
            json=SUBMITTED_RESPONSE,
            status_code=202,
        )

        exit_code = main([
            "--base-url", base_url,
            "revoke-structured-event",
            CORRELATION_ID,
        ])

        assert exit_code == 0
        output = capsys.readouterr().out
        assert "submitted" in output
        assert "txabc123" in output

    def test_revoke_structured_event_json_output(
        self, base_url: str, httpx_mock: HTTPXMock, capsys
    ) -> None:
        httpx_mock.add_response(
            url=f"{base_url}/api/record/structured/revoke/",
            method="POST",
            json=SUBMITTED_RESPONSE,
            status_code=202,
        )

        exit_code = main([
            "--base-url", base_url,
            "revoke-structured-event",
            CORRELATION_ID,
            "--output", "json",
        ])

        assert exit_code == 0
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "submitted"
        assert data["tx_hash"] == "txabc123"

    def test_revoke_structured_event_api_error_prints_to_stderr(
        self, base_url: str, httpx_mock: HTTPXMock, capsys
    ) -> None:
        httpx_mock.add_response(
            url=f"{base_url}/api/record/structured/revoke/",
            method="POST",
            json={"detail": "already revoked"},
            status_code=400,
        )

        exit_code = main([
            "--base-url", base_url,
            "revoke-structured-event",
            CORRELATION_ID,
        ])

        assert exit_code == 1
        assert "Error" in capsys.readouterr().err
