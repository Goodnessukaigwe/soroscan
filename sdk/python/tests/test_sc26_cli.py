"""Tests for the SC-26 `indexers` rate-limit CLI commands."""

import json

import pytest
from pytest_httpx import HTTPXMock

from soroscan.cli import main, build_parser


INDEXER = "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF"

SET_RESPONSE = {
    "status": "submitted",
    "tx_hash": "txratelimit001",
    "transaction_status": "pending",
    "error": None,
}


# ── Parser tests (no HTTP needed) ────────────────────────────────────────────

class TestIndexerRateLimitParser:
    def test_set_rate_limit_subcommand_exists(self):
        parser = build_parser()
        args = parser.parse_args(["indexers", "set-rate-limit", INDEXER, "100"])
        assert args.indexer == INDEXER
        assert args.max_events_per_ledger == 100
        assert args.output == "table"

    def test_get_rate_limit_subcommand_exists(self):
        parser = build_parser()
        args = parser.parse_args(["indexers", "get-rate-limit", INDEXER])
        assert args.indexer == INDEXER

    def test_indexers_requires_subcommand(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["indexers"])


# ── Integration tests (HTTP mocked) ──────────────────────────────────────────

class TestIndexerRateLimitCLI:
    def test_set_rate_limit_json_output(
        self,
        base_url: str,
        httpx_mock: HTTPXMock,
        capsys,
    ) -> None:
        httpx_mock.add_response(
            url=f"{base_url}/api/ingest/indexers/rate-limit/",
            method="POST",
            json=SET_RESPONSE,
            status_code=202,
        )

        exit_code = main([
            "--base-url", base_url,
            "indexers", "set-rate-limit", INDEXER, "100",
            "--output", "json",
        ])

        assert exit_code == 0
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "submitted"
        assert data["tx_hash"] == "txratelimit001"

    def test_get_rate_limit_table_output(
        self,
        base_url: str,
        httpx_mock: HTTPXMock,
        capsys,
    ) -> None:
        httpx_mock.add_response(
            url=f"{base_url}/api/ingest/indexers/{INDEXER}/rate-limit/",
            method="GET",
            json={"indexer": INDEXER, "max_events_per_ledger": 50},
            status_code=200,
        )

        exit_code = main([
            "--base-url", base_url,
            "indexers", "get-rate-limit", INDEXER,
        ])

        assert exit_code == 0
        output = capsys.readouterr().out
        assert INDEXER in output
        assert "50" in output

    def test_set_rate_limit_error_prints_to_stderr(
        self,
        base_url: str,
        httpx_mock: HTTPXMock,
        capsys,
    ) -> None:
        httpx_mock.add_response(
            url=f"{base_url}/api/ingest/indexers/rate-limit/",
            method="POST",
            json={"detail": "Not authorized"},
            status_code=403,
        )

        exit_code = main([
            "--base-url", base_url,
            "indexers", "set-rate-limit", INDEXER, "100",
        ])

        assert exit_code == 1
        assert "Error" in capsys.readouterr().err
