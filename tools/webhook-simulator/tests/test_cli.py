import json

from tests.conftest import header_value
from webhook_simulator.cli import main
from webhook_simulator.payload import SAMPLE_EVENT, canonicalize
from webhook_simulator.signing import hmac_signature_header


def test_cli_dry_run_sample(capsys):
    code = main(
        [
            "--dry-run",
            "--sample",
            "--secret",
            "test-secret",
            "--url",
            "http://localhost:9999/webhook",
        ]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "Dry run" in output
    assert "X-SoroScan-Signature" in output
    assert SAMPLE_EVENT["event_type"] in output


def test_cli_delivers_and_prints_status(webhook_server, capsys):
    code = main(
        [
            "--url",
            webhook_server.base_url,
            "--sample",
            "--secret",
            "whsec_test",
            "--output",
            "json",
        ]
    )
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["success"] is True
    assert data["status"] == "success"
    assert data["http_status"] == 200
    assert data["ack_status"] == "valid"
    body = webhook_server.requests[0]["body"]
    assert body == canonicalize(SAMPLE_EVENT)
    sent_sig = header_value(webhook_server.requests[0]["headers"], "X-SoroScan-Signature")
    assert sent_sig == hmac_signature_header(body, "whsec_test")


def test_cli_event_file(tmp_path, webhook_server, capsys):
    event_file = tmp_path / "event.json"
    event_file.write_text(
        json.dumps({"event_type": "mint", "payload": {"n": 1}, "ledger": 7}),
        encoding="utf-8",
    )
    code = main(
        [
            "--url",
            webhook_server.base_url,
            "--event-file",
            str(event_file),
            "--secret",
            "s",
        ]
    )
    assert code == 0
    sent = json.loads(webhook_server.requests[0]["body"].decode("utf-8"))
    assert sent["event_type"] == "mint"
    assert sent["ledger"] == 7
    assert sent["payload"] == {"n": 1}
    assert "Delivery status" in capsys.readouterr().out


def test_cli_inline_json_event(webhook_server):
    code = main(
        [
            "--url",
            webhook_server.base_url,
            "--event",
            '{"event_type": "swap", "payload": {"pair": "XLM/USDC"}}',
            "--unsigned",
        ]
    )
    assert code == 0
    sent = json.loads(webhook_server.requests[0]["body"].decode("utf-8"))
    assert sent["event_type"] == "swap"
    assert sent["payload"] == {"pair": "XLM/USDC"}


def test_cli_ping(webhook_server):
    code = main(["--url", webhook_server.base_url, "--ping"])
    assert code == 0
    headers = webhook_server.requests[0]["headers"]
    body = json.loads(webhook_server.requests[0]["body"].decode("utf-8"))
    assert header_value(headers, "X-SoroScan-Event") == "ping"
    assert header_value(headers, "X-SoroScan-Signature") is None
    assert body["type"] == "ping"
    assert "timestamp" in body


def test_cli_failed_delivery_exit_code(webhook_server):
    webhook_server.status_code = 404
    code = main(["--url", webhook_server.base_url, "--sample", "--unsigned"])
    assert code == 1


def test_cli_missing_url_without_dry_run():
    code = main(["--sample"])
    assert code == 2


def test_cli_invalid_header():
    code = main(
        [
            "--dry-run",
            "--sample",
            "--url",
            "http://localhost/webhook",
            "--header",
            "not-a-header",
        ]
    )
    assert code == 2


def test_cli_json_dry_run(capsys):
    code = main(
        [
            "--dry-run",
            "--sample",
            "--secret",
            "abc",
            "--url",
            "http://localhost/webhook",
            "--output",
            "json",
        ]
    )
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["dry_run"] is True
    assert data["payload"]["event_type"] == "transfer"
    assert "sha256=" in data["headers"]["X-SoroScan-Signature"]


def test_cli_overrides(webhook_server):
    code = main(
        [
            "--url",
            webhook_server.base_url,
            "--sample",
            "--unsigned",
            "--event-type",
            "custom",
            "--ledger",
            "42",
        ]
    )
    assert code == 0
    sent = json.loads(webhook_server.requests[0]["body"].decode("utf-8"))
    assert sent["event_type"] == "custom"
    assert sent["ledger"] == 42
